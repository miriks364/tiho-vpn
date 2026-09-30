#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Use sudo bash install-bot.sh'; exit 1; }
[[ -f /etc/tiho.env && -d /opt/tiho/venv ]] || { echo 'Install the VPN server first: install.sh'; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
[[ ! -f /etc/systemd/system/tiho-bot.service ]] || { echo 'Bot already installed. Follow update instructions, do not overwrite data.'; exit 1; }
install -m 644 "$HERE"/{billing.py,bot.py,payments_admin.py,requirements.txt} /opt/tiho/
/opt/tiho/venv/bin/pip install -r /opt/tiho/requirements.txt
if [[ ! -f /etc/tiho-bot.env ]]; then python3 "$HERE/setup_bot.py"; fi
# Initialize billing tables before starting concurrent processes.
set -a
source /etc/tiho.env
set +a
(cd /opt/tiho && /opt/tiho/venv/bin/python -c 'import billing; billing.init()')
cat > /etc/systemd/system/tiho-bot.service <<'UNIT'
[Unit]
Description=Tiho VPN Telegram Stars bot
Wants=network-online.target tiho.service
After=network-online.target tiho.service
[Service]
Type=simple
User=root
WorkingDirectory=/opt/tiho
EnvironmentFile=/etc/tiho.env
EnvironmentFile=/etc/tiho-bot.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/tiho/venv/bin/python bot.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/tiho
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
[Install]
WantedBy=multi-user.target
UNIT
cat > /usr/local/bin/tiho-payments <<'ADMIN'
#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Use sudo'; exit 1; }
set -a
source /etc/tiho.env
set +a
cd /opt/tiho
exec /opt/tiho/venv/bin/python payments_admin.py "$@"
ADMIN
chmod 755 /usr/local/bin/tiho-payments
chmod 644 /etc/systemd/system/tiho-bot.service
if [[ -f "$HERE/../release/Tiho-VPN-0.2.0-debug.apk" ]]; then
    install -d -m 755 /var/www/tiho/download
    install -m 644 "$HERE/../release/Tiho-VPN-0.2.0-debug.apk" /var/www/tiho/download/tiho.apk
else
    echo 'WARNING: APK missing; copy release APK to /var/www/tiho/download/tiho.apk'
fi
systemctl daemon-reload
systemctl enable --now tiho-bot
printf '\nBot installed. Check: systemctl status tiho-bot; journalctl -u tiho-bot -n 50\n'
