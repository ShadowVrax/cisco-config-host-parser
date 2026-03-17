# cisco-config-host-parser

> Parse Cisco IOS, ASA & Nexus running configs into a clean, aligned hosts-style IP documentation file.
>
> Written by [ShadowVrax](https://github.com/ShadowVrax)

---

## The Problem

In large network environments, keeping an accurate record of every interface IP address across dozens of switches, routers, and firewalls is tedious and error-prone. Engineers copy-paste from `show ip interface brief`, miss secondary addresses, forget HSRP VIPs, and the document is out of date before the change window closes.

This script reads the device's own running config — the source of truth — and generates a clean, aligned hosts-style output file automatically.

---

## What It Does

Given one or more Cisco running config files (IOS, ASA, or Nexus), it produces a text file where each line follows this pattern:

```
<ip-address>    <hostname>_<interface>_<description>    #<network>/<prefix>
```

Example output:

```
10.0.10.1       CORE-SW-01_Vlan10_Management              #10.0.10.0/24
10.0.20.1       CORE-SW-01_Vlan20_ServerFarm              #10.0.20.0/24
10.0.20.254     CORE-SW-01_Vlan20_ServerFarm_VIP          #10.0.20.0/24
10.0.30.1       CORE-SW-01_Vlan30_VoIP                    #10.0.30.0/24
10.0.0.1        CORE-SW-01_Gig0-0_uplink-to-BORDER-01     #10.0.0.0/30
10.0.0.5        CORE-SW-01_Gig0-1_uplink-to-BORDER-02     #10.0.0.4/30
10.1.1.1        CORE-SW-01_loopback0_RouterID             #10.1.1.1/32
                CORE-SW-01_Vlan99_Quarantine
203.0.113.10    CORE-SW-01_Peer_IP
```

---

## Supported Platforms

The script auto-detects config format — no manual flags needed:

| Platform | Format | Notes |
|---|---|---|
| Cisco IOS / IOS-XE | Dotted subnet mask | Routers, Catalyst switches |
| Cisco ASA / FTD | Dotted mask + `nameif` | Firewalls |
| Cisco Nexus (NX-OS) | CIDR slash notation | Data center, VRF-aware |

---

## Features

- **HSRP / VRRP / GLBP VIP detection** — VIPs tagged with `_VIP`, subnet inferred from primary IP
- **Crypto map peer extraction** — IPsec peer IPs appear at the bottom as `<hostname>_Peer_IP`
- **No-IP SVI inventory** — VLANs with no IP still appear as alias-only lines (free VLAN inventory)
- **Batch processing** — pass a folder to consolidate an entire site into one timestamped file
- **Column-aligned output** — the `#CIDR` column is perfectly padded across all rows
- **Zero dependencies** — Python 3.6+ standard library only, no `pip install` needed

---

## Requirements

- Python 3.6 or later
- A Cisco running config saved as a plain text file

To export a running config from your device:

```
show running-config
```

Save the output as a `.txt`, `.cfg`, `.conf`, `.log`, `.config`, or `.running-config` file. Files with no extension are also supported. Most config backup tools (Oxidized, RANCID, SolarWinds) archive these automatically — point the script directly at those files.

---

## Usage

### Single device

```bash
python3 convert_hostfile.py CORE-SW-01.cfg
# Output: CORE-SW-01_interfaces_hosts.txt
```

### Entire folder of configs

```bash
python3 convert_hostfile.py /backups/configs/
# Output: interfaces_hosts_20260304_142301.txt
```

### Optional: make it executable

```bash
chmod +x convert_hostfile.py
./convert_hostfile.py CORE-SW-01.cfg
```

---

## Practical Use Cases

```bash
# Append to your team hosts file for name resolution during troubleshooting
cat CORE-SW-01_interfaces_hosts.txt >> /etc/hosts

# Find all IPs in a subnet
grep "#10.0.20" interfaces_hosts_20260304.txt

# Find all HSRP/VRRP/GLBP VIPs across the environment
grep "_VIP" interfaces_hosts_20260304.txt

# Find all IPsec crypto peers
grep "_Peer_IP" interfaces_hosts_20260304.txt

# Diff two runs to see what changed between config backups
diff interfaces_hosts_20260303.txt interfaces_hosts_20260304.txt
```

---

## Blog Post

Full write-up with detailed parsing explanation and platform examples:
[Automating Interface Documentation: Parsing Cisco IOS, ASA & Nexus Configs into a Hosts File](https://shadowvrax.me/blog/automating-interface-documentation)

---

## License

MIT — free to use, modify, and distribute.

