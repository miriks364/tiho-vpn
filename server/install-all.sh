#!/usr/bin/env bash
# Clean Ubuntu VPS: sudo env DOMAIN=vpn.example.com PUBLIC_IPV4=203.0.113.10 bash server/install-all.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
bash "$HERE/install.sh"
bash "$HERE/install-bot.sh"
