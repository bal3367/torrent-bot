#!/bin/bash
set -e

echo "=== Torrent Bot Setup ==="

sudo apt update && sudo apt install -y aria2 python3-pip screen python3-venv

cd "$(dirname "$0")"

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p downloads

if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "Salin .env.example ke .env sudah dilakukan."
    echo "Edit .env dan isi BOT_TOKEN, ALLOWED_CHAT_ID, VPS_IP, dll."
else
    echo ".env sudah ada, skip."
fi

echo ""
echo "Setup selesai! Jalankan: ./start.sh"
