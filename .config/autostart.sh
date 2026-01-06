#!/bin/sh

( 
  chmod -R 700 /storage/bin
  chmod 600 /storage/.config/ks_shared_secret
  rm /storage/logs/wg2fa.log
  python3 /storage/bin/wg2fa_advanced.py
) &
