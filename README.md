# WireGuard 2FA Bootstrap für LibreELEC (privacyIDEA)

## Ziel

This Project provides a **hardened WireGuard connection with preemptive 2-factor authentication (Push)** for **LibreELEC on Raspberry Pi** or other linux systems.

The VPN connection is **only established** if:

- the device is **not already reachable in the target network**
- the **2FA via privacyIDEA is successfully confirmed**

🔒 **Private Keys are never persistently stored.**
🔒 **No `wg-quick`, no systemd, no NetworkManager.**

---

## Architecture Overview

```text
LibreELEC Boot
   │
   ├─ Check: Target network reachable?
   │      └─ Yes → no VPN
   │      └─ No → continue
   │
   ├─ Wait for DNS / Network
   │
   ├─ privacyIDEA Push-2FA
   │      └─ Success → Release key
   │      └─ Failure → Abort
   │
   |- Connection with Key Store API - Auth with HMAC Signature
   |      └─ Key Store checks with privacyIDEA if key is released
   |         └─ Released → Output key
   |         └─ Not released → Abort
   |
   ├─ WireGuard Interface
   │      ├─ Key only in RAM
   │      ├─ Set IP & Routing
   │      └─ VPN active
   │
   └─ Shutdown:
          └─ wireguard interface completely removed
```

---

## Requirements

### Hardware

- Raspberry Pi 3 / 4 / 5
- LibreELEC (current stable Version)

### Server

- privacyIDEA ≥ 3.x
- Key Store API --> [MfaCheckApi](https://github.com/js-webdev/MfaCheckApi)
- WireGuard-Server

### Client (LibreELEC)

- `wg` (WireGuard Userspace Tool)
- `ip` (iproute2)
- Python 3 (standardmäßig vorhanden)

❗ `pip`, `systemd`, `wg-quick` are **not required**, since they're not available (preinstalled) on LibreELEC anyway

---

## Repository Contens (short)

```text
.
├─ .config/wireguard/example.callhome.conf    # WireGuard Peer-Config (ohne PrivateKey)
├─ .config/autostart.sh                       # LibreELEC autostart script
├─ .config/autostop.sh                        # LibreELEC autostop script
├─ .config/example.ks_shared_secret           # Key Store shared secret for HMAC Authorization
├─ bin/wg2fa_advanced.py                      # 2FA + VPN Bootstrap Script
├─ bin/drop-wireguard.sh                      # simple script to remove a ip interface
├─ bin/start-wireguard.sh                     # steps to open the wireguard connection
└─ README.md
```

---

## Security principles

### 1. No persistent private key

- The WireGuard private key resides **only in RAM**
- Passed exclusively via `stdin`
- Lost completely after reboot or shutdown

### 2. No VPN in the internal network

- If the target network is reachable → **VPN is not started**
- Prevents:

  - unnecessary tunnels
  - bypassing 2FA

### 3. 2FA is mandatory

- Without successful push confirmation:

  - no key
  - no interface
  - no routing

### 4. Minimal Tunnel

- no Full-Tunnel
- Only explicit `AllowedIPs`
- No DNS manipulation unless explicitly desired

---

## privacyIDEA Configuration (Short)

- User Resolver: **editable (e.g. SQLResolver)**
- Token: **Push Token**
- Policy:

  - `push_firebase_configuration` (if Push is used)
  - Enrollment Policy for Push

- Testable via:

```sh
curl -X POST https://<PI-HOST>/validate/check \
  -d "user=<USER>" \
  -d "pass=push"
  -d "realm=<REALM>"
```

---

## WireGuard Client Config (`example.callhome.conf`)

❗ **Without PrivateKey**

```ini
[Interface]
Address = 192.168.0.101/24

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = <SERVER_IP>:51820
AllowedIPs = 192.168.0.0/24
PersistentKeepalive = 25
```

---

## Boot Process

1. Script waits for functional DNS
2. Checks if target network is reachable
3. Triggers privacyIDEA Push
4. Waits for confirmation
5. Retrieves WireGuard Private Key from Key Store API
6. Manually sets up WireGuard Interface:

   - `ip link add`
   - `wg setconf`
   - `wg set private-key`
   - `ip addr add`
   - `ip route add`

---

## Shutdown Behavior

On shutdown, the following is **always** executed:

```sh
ip link del wg0
```

✔ Key deleted
✔ Interface removed
✔ No leftovers

---

## Threat Model (Short)

| Attack             | Mitigated       |
| ------------------ | --------------- |
| Cloning SD card    | ✔ no key        |
| Reboot without 2FA | ✔ no VPN        |
| Manual `wg up`     | ✔ no key        |
| Network spoofing   | ✔ push required |
| Persistent Tunnel  | ✔ network check |

---

## Target Audience

- Headless LibreELEC systems
- Locations without physical security
- Zero-Trust VPN Bootstrap
- Homelab / Edge devices

---

## Diagram

```text
User / Admin
     |
     |  (Device boot)
     v
+-------------------+
|   LibreELEC OS    |
+-------------------+
         |
         | Start wg2fa_advanced.py
         v
+---------------------------+
| Network Initialization   |
+---------------------------+
         |
         | Wait for DNS / default route
         |-----------------------------------+
         |                                   |
         | (DNS not ready)                   | (DNS ready)
         | sleep + retry                     v
         |                           +--------------------+
         |                           | DNS resolved       |
         |                           +--------------------+
         |                                   |
         |                                   v
         |                           +--------------------+
         |                           | Target network     |
         |                           | reachable?         |
         |                           +--------------------+
         |                                   |
         |               +-------------------+-------------------+
         |               |                                       |
         |        (YES: already in LAN)                    (NO)
         |               |                                       |
         |               v                                       v
         |     +-------------------+                   +----------------------+
         |     | Skip VPN entirely |                   | Trigger privacyIDEA  |
         |     +-------------------+                   | Push authentication  |
         |                                               +----------------------+
         |                                                       |
         |                                                       v
         |                                       +-----------------------------+
         |                                       | Mobile device receives push |
         |                                       +-----------------------------+
         |                                                       |
         |                                     User confirms     v
         |                                       +-----------------------------+
         |                                       | privacyIDEA validates push  |
         |                                       +-----------------------------+
         |                                                       |
         |                               +-----------------------+-----------------------+
         |                               |                                               |
         |                         (FAILED / TIMEOUT)                               (OK)
         |                               |                                               |
         |                               v                                               v
         |                    +----------------------+                     +-------------------------------+
         |                    | Abort, no VPN        |     (Denied)        | Request Wireguard Private Key |
         |                    | No interface created |  <--------------    | from Key Store API.           |
         |                    +----------------------+                     +-------------------------------+
         |                                                                               | (OK)
         |                                                                               v
         |                                                                  +-------------------------------+
         |                                                                  | Release WireGuard key         |
         |                                                                  | (in RAM only)                 |
         |                                                                  +-------------------------------+
         |                                                                               |
         |                                                                               v
         |                                                            +------------------------------+
         |                                                            | run bin/start/wireguard.sh   |
         |                                                            +------------------------------+
         |                                                                               |
         |                                                                               v
         |                                                            +------------------------------+
         |                                                            | VPN active                  |
         |                                                            +------------------------------+
         |
         v
+---------------------------+
| Normal device operation  |
+---------------------------+
         |
         | Shutdown / Reboot
         v
+---------------------------+
| shutdown_cleanup.sh      |
+---------------------------+
         |
         | ip link del wg0
         v
+---------------------------+
| Clean system state       |
+---------------------------+
```
