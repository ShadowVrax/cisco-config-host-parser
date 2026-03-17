#!/usr/bin/env python3
"""
Cisco IOS / ASA / Nexus Config -> Hosts-style Interface List
Supports: dotted mask (IOS/ASA), CIDR (Nexus), HSRP/VRRP/GLBP VIPs,
          crypto map peers, no-IP VLAN SVIs, single file or folder batch.
"""

import os, re, sys
from datetime import datetime
from ipaddress import ip_interface, ip_network, ip_address
from typing import List, Tuple, Set

TABSTOP = 8
CIDR_GAP_SPACES = 2
EXTRA_HASH_TABS = 3
MAX_DESC_LEN = 45
SUPPORTED_EXTS = {".txt", ".cfg", ".conf", ".log", ".config", ".running-config"}

INTERFACE_START_RE = re.compile(r"^\s*interface\s+(?P<ifname>\S+)\s*$", re.IGNORECASE)
HOSTNAME_LINE_RE   = re.compile(r"^\s*hostname\s+(?P<hostname>\S+)\s*$", re.IGNORECASE)
DESC_RE            = re.compile(r"^\s*description\s+(?P<desc>.+?)\s*$", re.IGNORECASE)
NAMEIF_RE          = re.compile(r"^\s*nameif\s+(?P<nameif>\S+)\s*$", re.IGNORECASE)
VRF_MEMBER_RE      = re.compile(r"^\s*vrf\s+member\s+(?P<vrf>\S+)\s*$", re.IGNORECASE)
IPV4_MASK_RE       = re.compile(
    r"^\s*ip\s+address\s+(?P<ip>\d+\.\d+\.\d+\.\d+)\s+(?P<mask>\d+\.\d+\.\d+\.\d+)"
    r"(?:\s+secondary)?\s*$", re.IGNORECASE)
IPV4_CIDR_RE       = re.compile(
    r"^\s*ip\s+address\s+(?P<ip>\d+\.\d+\.\d+\.\d+)\/(?P<pfx>\d+)(?:\s+tag\s+\S+)?\s*$",
    re.IGNORECASE)
DHCP_RE            = re.compile(r"^\s*ip\s+address\s+dhcp", re.IGNORECASE)
BLOCK_END_RE       = re.compile(r"^\s*!\s*$|^\s*end\s*$", re.IGNORECASE)
HSRP_RE = re.compile(r"^\s*standby\s+\d+\s+ip\s+(?P<vip>\d+\.\d+\.\d+\.\d+)\s*$", re.IGNORECASE)
VRRP_RE = re.compile(r"^\s*vrrp\s+\d+\s+(?:ip|address)\s+(?P<vip>\d+\.\d+\.\d+\.\d+)\s*$", re.IGNORECASE)
GLBP_RE = re.compile(r"^\s*glbp\s+\d+\s+ip\s+(?P<vip>\d+\.\d+\.\d+\.\d+)\s*$", re.IGNORECASE)
CRYPTO_PEER_LINE_RE = re.compile(r"^\s*crypto\s+map\s+\S+\s+\d+\s+set\s+peer\s+(?P<peers>.+?)\s*$", re.IGNORECASE)
IPV4_TOKEN_RE       = re.compile(r"\d+\.\d+\.\d+\.\d+")

def abbreviate_iface_prefix(name):
    for long, short in [("TenGigabitEthernet","TenG"),("TenGigabit","TenG"),("GigabitEthernet","Gig")]:
        if re.match(f"^{long}", name, re.IGNORECASE):
            return re.sub(f"^{long}", short, name, flags=re.IGNORECASE)
    return name

def sanitize_iface(name):
    return abbreviate_iface_prefix(name or "").strip().replace("/", "-")

def no_space(text):
    return re.sub(r"\s+", "", text or "")

def mask_to_prefix(mask_str):
    return ip_interface(f"0.0.0.0/{mask_str}").network.prefixlen

def parse_hostname(lines):
    for l in lines:
        m = HOSTNAME_LINE_RE.match(l)
        if m: return m.group("hostname").strip()
    return "device"

def gather_config_files(path):
    path = os.path.expanduser(path)
    if os.path.isfile(path): return [path]
    if os.path.isdir(path):
        files = []
        for root, _, fnames in os.walk(path):
            for fn in fnames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in SUPPORTED_EXTS or not ext:
                    files.append(os.path.join(root, fn))
        return files
    raise FileNotFoundError(f"Path not found: {path}")

def is_vlan(ifn):  return re.match(r"^Vlan\d+$", ifn, re.IGNORECASE) is not None
def is_vlan1(ifn): return re.match(r"^Vlan1$",   ifn, re.IGNORECASE) is not None

def build_alias(hostname, ifname, desc_compact):
    parts = [hostname, sanitize_iface(ifname)]
    if desc_compact: parts.append(desc_compact)
    return "_".join(parts)

def parse_device(content):
    lines = content.splitlines()
    hostname = parse_hostname(lines)
    entries, no_ip_vlan_aliases, peer_ips = [], [], set()
    i, n = 0, len(lines)
    while i < n:
        m = INTERFACE_START_RE.match(lines[i])
        if not m: i += 1; continue
        ifname = m.group("ifname").strip()
        if is_vlan1(ifname):
            i += 1
            while i < n and not (INTERFACE_START_RE.match(lines[i]) or BLOCK_END_RE.match(lines[i])): i += 1
            continue
        desc = asa_nameif = vrf_member = None
        ipv4s_mask, ipv4s_cidr, vips = [], [], []
        has_dhcp = False
        i += 1
        while i < n:
            l = lines[i]
            if INTERFACE_START_RE.match(l) or BLOCK_END_RE.match(l): break
            if (md := DESC_RE.match(l)):    desc = md.group("desc").strip()
            if (mn := NAMEIF_RE.match(l)) and not asa_nameif: asa_nameif = mn.group("nameif").strip()
            if (mv := VRF_MEMBER_RE.match(l)) and not vrf_member: vrf_member = mv.group("vrf").strip()
            if (mm := IPV4_MASK_RE.match(l)): ipv4s_mask.append((mm.group("ip"), mm.group("mask")))
            if (mc := IPV4_CIDR_RE.match(l)): ipv4s_cidr.append((mc.group("ip"), int(mc.group("pfx"))))
            elif DHCP_RE.match(l): has_dhcp = True
            for rex in (HSRP_RE, VRRP_RE, GLBP_RE):
                if (mv2 := rex.match(l)): vips.append(mv2.group("vip"))
            i += 1
        desc_compact = no_space(desc if desc else (asa_nameif or ""))[:MAX_DESC_LEN]
        if is_vlan(ifname) and not (ipv4s_mask or ipv4s_cidr or has_dhcp):
            no_ip_vlan_aliases.append(build_alias(hostname, ifname, desc_compact))
        for ip, mask in ipv4s_mask:
            pfx = mask_to_prefix(mask)
            net = ip_network(f"{ip}/{pfx}", strict=False)
            entries.append((ip, build_alias(hostname, ifname, desc_compact), f"{net.network_address}/{pfx}"))
        for ip, pfx in ipv4s_cidr:
            net = ip_network(f"{ip}/{pfx}", strict=False)
            entries.append((ip, build_alias(hostname, ifname, desc_compact), f"{net.network_address}/{pfx}"))
        inferred_cidr = ""
        if ipv4s_mask:
            pfx0 = mask_to_prefix(ipv4s_mask[0][1])
            net0 = ip_network(f"{ipv4s_mask[0][0]}/{pfx0}", strict=False)
            inferred_cidr = f"{net0.network_address}/{pfx0}"
        elif ipv4s_cidr:
            net0 = ip_network(f"{ipv4s_cidr[0][0]}/{ipv4s_cidr[0][1]}", strict=False)
            inferred_cidr = f"{net0.network_address}/{ipv4s_cidr[0][1]}"
        for vip in vips:
            entries.append((vip, build_alias(hostname, ifname, desc_compact) + "_VIP", inferred_cidr))
    for l in lines:
        if (mc := CRYPTO_PEER_LINE_RE.match(l)):
            for iptok in IPV4_TOKEN_RE.findall(mc.group("peers")): peer_ips.add(iptok)
    existing_ips = {ip for ip, _, _ in entries}
    peer_entries = [(pip, f"{hostname}_Peer_IP") for pip in
                    sorted(peer_ips - existing_ips, key=lambda x: int(ip_address(x)._ip))]
    alias_start_col = max((len((ip+"		").expandtabs(TABSTOP)) for ip,_,_ in entries), default=TABSTOP*3)
    max_alias_len   = max([len(a) for _,a,_ in entries] + [len(a) for a in no_ip_vlan_aliases], default=0)
    target_hash_col = alias_start_col + max_alias_len + CIDR_GAP_SPACES + (EXTRA_HASH_TABS * TABSTOP)
    return hostname, entries, no_ip_vlan_aliases, peer_entries, alias_start_col, target_hash_col

def write_output(out_path, entries, no_ip_vlan_aliases, peer_entries, alias_start_col, target_hash_col):
    tabs_for_alias_only = max(1, (alias_start_col + TABSTOP - 1) // TABSTOP)
    alias_only_prefix = "\t" * tabs_for_alias_only
    with open(out_path, "w", encoding="utf-8") as out:
        for ip, alias, cidr in entries:
            prefix = f"{ip}\t\t{alias}"
            pad = max(1, target_hash_col - len(prefix.expandtabs(TABSTOP)))
            out.write(f"{prefix}{' ' * pad}#{cidr}\n" if cidr else f"{prefix}\n")
        for alias in no_ip_vlan_aliases:
            out.write(f"{alias_only_prefix}{alias}\n")
        for pip, palias in peer_entries:
            out.write(f"{pip}\t\t{palias}\n")
    return out_path

def main():
    try:
        path = sys.argv[1] if len(sys.argv) > 1 else input("Config file or folder: ").strip().strip('"')
        if not path: sys.exit(1)
        files = gather_config_files(path)
        if not files: print("No config files found."); sys.exit(1)
        if len(files) == 1:
            with open(files[0], encoding="utf-8", errors="ignore") as fh: content = fh.read()
            _, entries, no_ip, peers, a_col, h_col = parse_device(content)
            base = os.path.splitext(files[0])[0]
            print("Wrote:", write_output(f"{base}_interfaces_hosts.txt", entries, no_ip, peers, a_col, h_col))
        else:
            all_e, all_n, all_p, a_col, h_col = [], [], [], TABSTOP*3, TABSTOP*8
            for f in files:
                try:
                    with open(f, encoding="utf-8", errors="ignore") as fh: content = fh.read()
                    _, e, n, p, ac, hc = parse_device(content)
                    all_e += e; all_n += n; all_p += p
                    a_col = max(a_col, ac); h_col = max(h_col, hc)
                except Exception as ex: print(f"! {f}: {ex}")
            all_e.sort(key=lambda t: int(ip_address(t[0])._ip))
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            print("Wrote:", write_output(
                os.path.join(os.path.abspath(path), f"interfaces_hosts_{stamp}.txt"),
                all_e, all_n, all_p, a_col, h_col))
    except KeyboardInterrupt: print("\nInterrupted.")

if __name__ == "__main__":
    main()
