#!/bin/sh

WG_INTERFACE=$1
WG_CONF_PATH=$2
WG_KEY=$3
WG_IP_ADDRESS=$4
WG_NETWORK=$5

if [ -z "$WG_KEY" ] || [ -z "$WG_INTERFACE" ] || [ -z "$WG_CONF_PATH" ] || [ -z "$WG_IP_ADDRESS" ] || [ -z "$WG_NETWORK" ]; then
  echo "Usage: start-wireguard.sh <WG_INTERFACE> <WG_CONF_PATH> <WG_KEY> <WG_IP_ADDRESS> <WG_NETWORK>"
  echo "All parameters are required"
  exit 1
fi
ip link add $WG_INTERFACE type wireguard
wg setconf $WG_INTERFACE $WG_CONF_PATH
wg set $WG_INTERFACE private-key <(echo "$WG_KEY")
ip addr add $WG_IP_ADDRESS dev $WG_INTERFACE
ip link set up dev $WG_INTERFACE
ip route add $WG_NETWORK dev $WG_INTERFACE
