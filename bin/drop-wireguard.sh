WG_INTERFACE=$1

if [ -z "$WG_INTERFACE" ]; then
    echo "Usage: $0 <interface>"
    exit 1
fi

ip link set down dev $WG_INTERFACE 2>/dev/null
ip link del $WG_INTERFACE 2>/dev/null