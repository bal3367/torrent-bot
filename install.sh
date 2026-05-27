#!/bin/bash
# ============================================
# Torrent Bot — One-liner installer
# Usage:
#   curl -sL https://raw.githubusercontent.com/bal3367/torrent-bot/main/install.sh | bash
# ============================================
set -e

echo "========================================"
echo "   Torrent Bot — One-liner Install"
echo "========================================"

# Install git jika belum ada
if ! command -v git &> /dev/null; then
    sudo apt update -qq && sudo apt install -y git
fi

# Clone atau update
if [ -d "$HOME/torrent_bot/.git" ]; then
    echo "▶ Repo sudah ada, update ke versi terbaru..."
    cd "$HOME/torrent_bot"
    git pull origin main
else
    echo "▶ Cloning repo..."
    git clone https://github.com/bal3367/torrent-bot.git "$HOME/torrent_bot"
    cd "$HOME/torrent_bot"
fi

# Jalankan setup (install deps, detect IP, auto-fill .env)
bash setup.sh

echo ""
echo "▶ Starting bot..."
bash start.sh

echo ""
echo "========================================"
echo "  ✅ Bot berjalan!"
echo "  Cek Telegram untuk notifikasi startup."
echo ""
echo "  Perintah berguna:"
echo "    screen -r torrent_bot   # lihat log"
echo "    cd ~/torrent_bot && bash start.sh   # restart"
echo "========================================"
