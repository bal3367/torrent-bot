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

# Kill existing processes
screen -S torrent_bot -X quit 2>/dev/null || true
screen -S torrent_fileserver -X quit 2>/dev/null || true
screen -S torrent_tunnel -X quit 2>/dev/null || true
pkill -f "python3 main.py" 2>/dev/null || true
pkill -f "python3 file_server.py" 2>/dev/null || true
pkill -x cloudflared 2>/dev/null || true
rm -f tunnel_url.txt
sleep 1

# Start file server in its own screen
if [ -d venv ]; then
    screen -dmS torrent_fileserver bash -c "source venv/bin/activate && python3 file_server.py 2>&1 | tee -a fileserver.log"
else
    screen -dmS torrent_fileserver bash -c "python3 file_server.py 2>&1 | tee -a fileserver.log"
fi
echo "File server berjalan di screen 'torrent_fileserver' (port $FILE_SERVER_PORT)."

# Start cloudflared in its own screen
screen -dmS torrent_tunnel bash -c "bash start_tunnel.sh 2>&1 | tee -a tunnel.log"
echo "Cloudflared berjalan di screen 'torrent_tunnel'."

# Start bot in screen
if [ -d venv ]; then
    screen -dmS torrent_bot bash -c "source venv/bin/activate && python3 main.py 2>&1 | tee -a bot.log"
else
    screen -dmS torrent_bot bash -c "python3 main.py 2>&1 | tee -a bot.log"
fi
echo "Bot berjalan di screen 'torrent_bot'."
echo "Lihat log: tail -f bot.log  |  screen -r torrent_bot"
