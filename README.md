# WireGuard 2FA Bootstrap für LibreELEC (privacyIDEA)

## Ziel

Dieses Projekt stellt eine **gehärtete WireGuard-Anbindung mit vorgeschalteter 2-Faktor-Authentifizierung (Push)** für **LibreELEC auf Raspberry Pi** bereit.

Die VPN-Verbindung wird **nur aufgebaut**, wenn:

- das Gerät **nicht bereits im Zielnetz erreichbar** ist
- die **2FA über privacyIDEA erfolgreich bestätigt** wurde

🔒 **Private Keys werden niemals persistent gespeichert.**
🔒 **Kein `wg-quick`, kein systemd, kein NetworkManager.**

---

## Architekturüberblick

```text
LibreELEC Boot
   │
   ├─ Prüfe: Zielnetz erreichbar?
   │      └─ Ja → kein VPN
   │      └─ Nein → weiter
   │
   ├─ Warte auf DNS / Netzwerk
   │
   ├─ privacyIDEA Push-2FA
   │      └─ Erfolgreich → Key freigeben
   │      └─ Fehlgeschlagen → Abbruch
   │
   |- Verbindung mit Key Store API - Auth mit HMAC Signatur
   |      └─ Key Store überprüft privacyIDEA ob Key freigegeben
   |         └─ Freigegeben → Key ausgeben
   |         └─ Nicht freigegeben → Abbruch
   |
   ├─ WireGuard Interface wg0
   │      ├─ Key nur im RAM
   │      ├─ IP & Routing setzen
   │      └─ VPN aktiv
   │
   └─ Shutdown:
          └─ wg0 vollständig entfernen
```

---

## Voraussetzungen

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
