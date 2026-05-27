#!/bin/bash
set -e

cd "$(dirname "$0")"
source .env

# Start aria2c daemon
if pgrep -x aria2c > /dev/null; then
    echo "aria2c sudah berjalan."
else
    mkdir -p "$DOWNLOAD_DIR"
    aria2c \
        --enable-rpc \
        --rpc-listen-all=false \
        --rpc-listen-port="${ARIA2_PORT:-6800}" \
        --rpc-secret="$ARIA2_SECRET" \
        --dir="$DOWNLOAD_DIR" \
        --max-download-limit="${MAX_DOWNLOAD_SPEED:-0}" \
        --max-upload-limit="${MAX_UPLOAD_SPEED:-0}" \
        --continue=true \
        --max-connection-per-server=16 \
        --split=16 \
        --min-split-size=1M \
        --max-concurrent-downloads=5 \
        --bt-enable-lpd=true \
        --enable-dht=true \
        --enable-peer-exchange=true \
        --bt-max-peers=100 \
        --seed-time=0 \
        --file-allocation=none \
        --bt-prioritize-piece=head,tail \
        --check-integrity=true \
        --auto-file-renaming=true \
        --daemon=true \
        --log=aria2.log
    echo "aria2c started."
fi

# Start bot in screen
if screen -list | grep -q "torrent_bot"; then
    echo "Screen 'torrent_bot' sudah berjalan. Gunakan: screen -r torrent_bot"
else
    if [ -d venv ]; then
        screen -S torrent_bot -dm bash -c "source venv/bin/activate && python3 main.py"
    else
        screen -S torrent_bot -dm python3 main.py
    fi
    echo "Bot berjalan di screen 'torrent_bot'."
    echo "Lihat log: screen -r torrent_bot"
fi
