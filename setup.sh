#!/bin/bash
set -e

echo "========================================"
echo "   Torrent Bot — Auto Setup"
echo "========================================"

# 1. System dependencies
sudo apt update -qq && sudo apt install -y aria2 python3-pip screen python3-venv curl jq 2>/dev/null

# 2. Install cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "▶ Installing cloudflared..."
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
        -o /tmp/cloudflared
    sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
    sudo chmod +x /usr/local/bin/cloudflared
    echo "  cloudflared installed ✅"
fi

cd "$(dirname "$0")"

# 3. Python venv + dependencies
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# 4. Download folder
mkdir -p downloads

# 5. Setup .env — auto-detect VPS IP
if [ ! -f .env ]; then
    cp .env.example .env
    # Auto-detect public IP
    PUBLIC_IP=$(curl -s --max-time 5 https://ifconfig.me/ip 2>/dev/null || echo "")
    if [ -n "$PUBLIC_IP" ]; then
        sed -i "s/VPS_IP=your_vps_public_ip/VPS_IP=$PUBLIC_IP/" .env
        echo "  VPS IP auto-detected: $PUBLIC_IP ✅"
    fi

    echo ""
    echo "========================================"
    echo "  ⚠️  Satu langkah lagi:"
    echo "  Edit .env dan isi:"
    echo "    BOT_TOKEN=<token dari @BotFather>"
    echo "    SERVER_LABEL=<nama VPS ini, misal: VPS-SG>"
    echo "========================================"
    echo ""
    echo "Setelah edit .env, jalankan: ./start.sh"
else
    echo ".env sudah ada ✅"
    echo ""
    echo "Setup selesai! Jalankan: ./start.sh"
fi
