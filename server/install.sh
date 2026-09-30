#!/usr/bin/env bash
# For a dedicated, clean Ubuntu 22.04/24.04 VPS only. Run locally on the VPS.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && ( "$VERSION_ID" == 22.04 || "$VERSION_ID" == 24.04 ) ]] || { echo 'Only Ubuntu 22.04 / 24.04 supported'; exit 1; }
: "${DOMAIN:?Set DOMAIN=vpn.example.com}"
: "${PUBLIC_IPV4:?Set PUBLIC_IPV4 to your VPS public IPv4}"
[[ "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ && "$DOMAIN" == *.* ]] || { echo 'Invalid domain'; exit 1; }
python3 -c 'import ipaddress,sys; assert ipaddress.ip_address(sys.argv[1]).version==4' "$PUBLIC_IPV4"
[[ ! -e /etc/tiho.env && ! -e /etc/wireguard/wg0.conf && ! -e /etc/caddy/Caddyfile ]] || { echo 'Existing installation/config found. Refusing to overwrite.'; exit 1; }
IFACE=$(ip -4 route show default | awk 'NR==1 {print $5}')
[[ "$IFACE" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 1
HERE=$(cd "$(dirname "$0")" && pwd)
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg
install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /etc/apt/keyrings/caddy-stable.gpg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
apt-get update
apt-get install -y wireguard-tools iptables python3-venv caddy
install -d -m 700 /etc/wireguard /var/lib/tiho
install -d -m 755 /opt/tiho
install -d -m 755 /var/www/tiho/web-app
install -m 644 "$HERE"/{api.py,core.py,admin.py,requirements.txt} /opt/tiho/
[[ -d "$HERE/../server/web_app" ]] && install -m 644 "$HERE"/../server/web_app/* /var/www/tiho/web-app/
install -m 755 "$HERE/firewall.sh" /usr/local/bin/tiho-firewall
python3 -m venv /opt/tiho/venv
/opt/tiho/venv/bin/pip install -r /opt/tiho/requirements.txt
umask 077
PRIVATE=$(wg genkey)
PUBLIC=$(printf '%s' "$PRIVATE" | wg pubkey)
SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
cat > /etc/wireguard/wg0.conf <<WG
[Interface]
Address = 10.66.0.1/16
ListenPort = 51820
PrivateKey = $PRIVATE
PostUp = /usr/local/bin/tiho-firewall up $IFACE
PostDown = /usr/local/bin/tiho-firewall down $IFACE
WG
cat > /etc/tiho.env <<ENV
TIHO_DB=/var/lib/tiho/tiho.db
TIHO_SECRET=$SECRET
WG_PUBLIC_KEY=$PUBLIC
WG_ENDPOINT=$PUBLIC_IPV4:51820
ENV
cat > /etc/sysctl.d/90-tiho.conf <<SYS
net.ipv4.ip_forward=1
SYS
sysctl --system >/dev/null
cat > /etc/systemd/system/tiho.service <<'UNIT'
[Unit]
Description=Tiho VPN subscription API
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=root
WorkingDirectory=/opt/tiho
EnvironmentFile=/etc/tiho.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStartPre=/usr/bin/wg-quick up wg0
ExecStart=/opt/tiho/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1 --no-access-log
ExecStopPost=-/usr/bin/wg-quick down wg0
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/tiho /run
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
    request_body {
        max_size 4KB
    }
    header {
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "no-referrer"
    }
    handle /web-app* {
        root * /var/www/tiho
        header Content-Type text/html
        file_server {
            hide .env .db
        }
    }
    handle /download/* {
        root * /var/www/tiho
        header Content-Type application/vnd.android.package-archive
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:8000
    }
}
CADDY
chmod 644 /etc/caddy/Caddyfile /etc/systemd/system/tiho.service /etc/sysctl.d/90-tiho.conf
cat > /usr/local/bin/tiho-admin <<'ADMIN'
#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Use sudo'; exit 1; }
set -a
source /etc/tiho.env
set +a
cd /opt/tiho
exec /opt/tiho/venv/bin/python admin.py "$@"
ADMIN
chmod 755 /usr/local/bin/tiho-admin
# Preserve existing SSH/firewall rules; provider firewall is configured separately.
if command -v ufw >/dev/null && ufw status | grep -q 'Status: active'; then
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 51820/udp
fi
systemctl daemon-reload
systemctl enable --now tiho
systemctl enable caddy
systemctl restart caddy
printf '\nAPI: https://%s\nNext: sudo tiho-admin issue --days 30\n' "$DOMAIN"
