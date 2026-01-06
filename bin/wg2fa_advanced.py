#!/usr/bin/env python3
import base64
import hashlib
import hmac
import urllib.request
import urllib.parse
import json
import socket
import subprocess
import time
import sys
import logging
import os
import asyncio

# ----------------- Konfiguration -----------------
HOME_GATEWAY = "192.168.0.1"
SERVER_IP = "192.168.0.2"

PRIVACYIDEA_HOST = "host.example.com"
PRIVACYIDEA_CHECK_URL = f"https://{PRIVACYIDEA_HOST}/validate/check"
PRIVACYIDEA_POLL_URL = f"https://{PRIVACYIDEA_HOST}/validate/polltransaction"
PRIVACYIDEA_USER = "user"
PRIVACYIDEA_TOKEN = "1234asdf"
PRIVACYIDEA_REALM = "example.com"

WG_INTERFACE = "wg0"
WG_CONF_PATH = "/storage/.config/wireguard/callhome.conf"
WG_IP_ADDRESS = "192.168.0.101/32"
WG_NETWORK = "192.168.0.0/24"

KS_HOST = "ks.example.com"
KS_URL = f"https://{KS_HOST}/mfa-check"
KS_SHARED_SECRET_PATH = "/storage/.config/ks_shared_secret"

TIMEOUT = 60
POLL_INTERVAL = 2
LOG_FILE = "/storage/logs/wg2fa.log"
DNS_TIMEOUT = 180

KODI_OSD = True  # True = Popup Meldungen in Kodi


logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
# --------------------------------------------------

# -------------- Central Functions -----------------

def kodi_notify(message):
    if KODI_OSD:
        subprocess.run([
            "kodi-send",
            "--action",
            f'Notification("VPN", "{message}", 5000)'
        ])

def log(message, level="info", log_only=False):

    if not log_only:
        print(message)
        kodi_notify(message)
    
    if level == "info":
        logging.info(message)
    elif level == "error":
        logging.error(message)
    elif level == "warning":
        logging.warning(message)

def cleanup_wg(interface):
    subprocess.run(["sh","/storage/bin/drop-wireguard.sh", interface], check=False)
    log(f"Altes Interface {interface} entfernt", "info", True)

def bring_up_wireguard(key):
    cleanup_wg(WG_INTERFACE)
    try:
        subprocess.run(["sh","/storage/bin/start-wireguard.sh", WG_INTERFACE, WG_CONF_PATH, key, WG_IP_ADDRESS, WG_NETWORK], check=True)
        log(f"WireGuard Interface {WG_INTERFACE} hochgefahren", "info")
    except subprocess.CalledProcessError as e:
        log(f"Fehler WireGuard hochfahren: {e}", "error")
        cleanup_wg(WG_INTERFACE)
        sys.exit(1)

def die(msg):
    log("[-] " + msg)
    cleanup_wg(WG_INTERFACE)
    sys.exit(1)
# --------------------------------------------------

async def in_home_network():
    try:
        subprocess.run(
            ["ping", "-c", "1", "-W", "1", HOME_GATEWAY],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

async def server_reachable():
    try:
        subprocess.run(
            ["ping", "-c", "1", "-W", "1", SERVER_IP],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def wait_for_dns(host, timeout):
    print(f"[+] Waiting for DNS resolution of {host}...")
    start = time.time()
    while True:
        try:
            ip = socket.gethostbyname(host)
            print(f"[+] DNS resolved: {host} -> {ip}")
            logging.info(f"DNS resolved {host} -> {ip}")
            return
        except socket.gaierror:
            if time.time() - start > timeout:
                print("[-] DNS timeout")
                logging.info(f"DNS timeout {host}")
                sys.exit(1)
            time.sleep(2)



def trigger_push():
    """Push-Token auslösen via /validate/check"""
    params = {
        "user": PRIVACYIDEA_USER,
        "pass": PRIVACYIDEA_TOKEN
    }
    if PRIVACYIDEA_REALM:
        params["realm"] = PRIVACYIDEA_REALM
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(PRIVACYIDEA_CHECK_URL, data=data, method="POST")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req) as response:
            resp_data = json.loads(response.read().decode())
            # Transaction ID für Polling
            log(resp_data["detail"], "info", True)
            txid = resp_data["detail"]["multi_challenge"][0]["transaction_id"]
            logging.info(f"transaction_id={txid}")
            log(f"transaction_id={txid}", "info", True)
            log("Push auf Smartphone ausgelöst")
            return txid
    except Exception as e:
        log("Fehler beim Push auslösen", "error")
        log(str(e), "error", True)
        sys.exit(1)

def create_ks_signature(payload):
    timestamp = int(time.time())
    shared_secret = open(KS_SHARED_SECRET_PATH).read().strip()
    string_to_sign = (str(timestamp) + json.dumps(payload)).replace(' ', '')
    log(f"String to sign: {string_to_sign}", "info", True)
    digest = hmac.new(
        shared_secret.encode(),
        string_to_sign.encode(),
        hashlib.sha512
    ).digest()
    return {"signature": base64.b64encode(digest).decode(), "timestamp": timestamp}

def get_private_key(txid):
    params = {
        "txid": txid,
        "username": PRIVACYIDEA_USER,
        "pass": PRIVACYIDEA_TOKEN,
        "realm": PRIVACYIDEA_REALM
    }
    authorization_data= create_ks_signature(params)

    log(f"KS Signature created at {authorization_data['timestamp']}", "info", True)
    log(f"Signature: {authorization_data['signature']}", "info", True)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"PI-TX {authorization_data['timestamp']}:{authorization_data['signature']}"
    }

    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(KS_URL, data=data, method="POST", headers=headers)
    log(f"Request to KS_URL: {KS_URL} with data: {params} and headers: {headers}", "info", True)
    try:
        with urllib.request.urlopen(req) as response:
            resp_data = json.loads(response.read().decode())
            return resp_data.get("privateKey")
    except Exception as e:
        log("Fehler beim Abrufen des privaten Schlüssels", "error")
        log(str(e), "error", True)
        sys.exit(1)

def poll_push(txid):
    """Polling bis Push bestätigt"""
    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        log(f"Polling push for {txid}", "info", True)
        params = {"transaction_id": txid}
        data = urllib.parse.urlencode(params)
        req = urllib.request.Request(PRIVACYIDEA_POLL_URL+"?"+data)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req) as response:
                resp_data = json.loads(response.read().decode())
                log(resp_data, "info", True)
                result = resp_data.get("result", {})
                if result.get("value") is True and result.get("authentication") == "ACCEPT":
                    log("Push bestätigt, VPN wird aktiviert", "info")
                    return get_private_key(txid)
        except Exception as e:
            log(f"Polling Fehler: {e}", "warning", True)
        time.sleep(POLL_INTERVAL)
    log("Timeout: Push nicht bestätigt", "warning")
    return False

async def main():

    if os.geteuid() != 0:
        die("Dieses Skript muss als root ausgeführt werden", "error")

    if await in_home_network() and await server_reachable():
        die("Home network detected – skipping WireGuard")

    wait_for_dns(PRIVACYIDEA_HOST, DNS_TIMEOUT)
    txid = trigger_push()

    log("Bitte Authentifizierung auf Smartphone bestätigen...", "info")

    WG_PRIVATE_KEY = poll_push(txid)

    if WG_PRIVATE_KEY:
        bring_up_wireguard(WG_PRIVATE_KEY)
    else:
        log("Push nicht bestätigt, VPN nicht gestartet", "warning")
        cleanup_wg(WG_INTERFACE)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())