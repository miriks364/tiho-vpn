#!/usr/bin/env bash
# IPv4 egress only; clients must not reach VPS services, metadata or private networks.
set -euo pipefail
ACTION=${1:?}; IFACE=${2:?}
[[ "$IFACE" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 1
cleanup() {
    iptables -D FORWARD -j TIHO_FWD 2>/dev/null || true
    iptables -F TIHO_FWD 2>/dev/null || true
    iptables -X TIHO_FWD 2>/dev/null || true
    iptables -t nat -D POSTROUTING -s 10.66.0.0/16 -o "$IFACE" -j MASQUERADE 2>/dev/null || true
    iptables -D INPUT -i wg0 -j DROP 2>/dev/null || true
}
case "$ACTION" in
    down) cleanup; exit 0;;
    up) cleanup;;
    *) exit 1;;
esac
iptables -N TIHO_FWD
iptables -A TIHO_FWD -i "$IFACE" -o wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -A TIHO_FWD -o wg0 -j DROP
for NET in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 240.0.0.0/4; do
    iptables -A TIHO_FWD -i wg0 -d "$NET" -j DROP
done
iptables -A TIHO_FWD -i wg0 -o "$IFACE" -s 10.66.0.0/16 -j ACCEPT
iptables -A TIHO_FWD -i wg0 -j DROP
iptables -I FORWARD 1 -j TIHO_FWD
iptables -t nat -A POSTROUTING -s 10.66.0.0/16 -o "$IFACE" -j MASQUERADE
iptables -I INPUT 1 -i wg0 -j DROP
