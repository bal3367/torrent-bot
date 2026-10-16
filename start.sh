#!/bin/bash
set -e

cd "$(dirname "$0")"
source .env

# Start aria2c daemon
# - Sesi disimpan (aria2.session) supaya stop/restart/update tidak menghapus antrian download.
# - Log level notice di folder bot: tanpa --log-level aria2 menulis DEBUG (beberapa baris per 16 KB
#   yang diterima) dan, karena --daemon pindah ke /, filenya ada di /aria2.log dan cepat memenuhi disk.
# - DHT entry point + tracker cadangan: aria2 tidak punya bootstrap DHT bawaan, tanpa ini peer cuma
#   dari tracker bawaan torrent.
BOT_DIR="$(pwd)"
ARIA2_SESSION="$BOT_DIR/aria2.session"
touch "$ARIA2_SESSION"
BT_TRACKERS="udp://tracker.opentrackr.org:1337/announce,udp://open.stealth.si:80/announce,udp://tracker.torrent.eu.org:451/announce,udp://exodus.desync.com:6969/announce,udp://open.demonii.com:1337/announce,udp://tracker.openbittorrent.com:6969/announce,udp://explodie.org:6969/announce"
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
        --input-file="$ARIA2_SESSION" \
        --save-session="$ARIA2_SESSION" \
        --save-session-interval=30 \
        --force-save=false \
        --max-download-limit="${MAX_DOWNLOAD_SPEED:-0}" \
        --max-upload-limit="${MAX_UPLOAD_SPEED:-0}" \
        --continue=true \
        --max-connection-per-server=16 \
        --split=16 \
        --min-split-size=1M \
        --max-concurrent-downloads=5 \
        --bt-enable-lpd=true \
        --enable-dht=true \
        --dht-entry-point=dht.transmissionbt.com:6881 \
        --bt-tracker="$BT_TRACKERS" \
        --enable-peer-exchange=true \
        --bt-max-peers=100 \
        --seed-time=0 \
        --file-allocation=none \
        --bt-prioritize-piece=head,tail \
        --check-integrity=true \
        --auto-file-renaming=true \
        --daemon=true \
        --log="$BOT_DIR/aria2.log" \
        --log-level=notice
    echo "aria2c started."
    # Download yang diselamatkan stop.sh dari aria2 versi lama (tanpa sesi): tambahkan lagi,
    # aria2 melanjutkan dari file yang sudah ada (--continue + cek integritas).
    if [ -s "$BOT_DIR/pending_magnets.txt" ]; then
        sleep 2
        while IFS= read -r uri; do
            [ -z "$uri" ] && continue
            curl -s "http://localhost:${ARIA2_PORT:-6800}/jsonrpc" \
                -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"aria2.addUri\",\"params\":[\"token:$ARIA2_SECRET\",[\"$uri\"]]}" > /dev/null \
                && echo "↻ Dilanjutkan: ${uri:0:80}"
        done < "$BOT_DIR/pending_magnets.txt"
        mv "$BOT_DIR/pending_magnets.txt" "$BOT_DIR/pending_magnets.done"
    fi
fi

# Auto-detect port bebas mulai dari FILE_SERVER_PORT
_PORT="${FILE_SERVER_PORT:-8080}"
while ss -tlnp 2>/dev/null | grep -q ":$_PORT "; do
    echo "Port $_PORT sudah dipakai, coba $((_PORT+1))..."
    _PORT=$((_PORT + 1))
done
if [ "$_PORT" != "${FILE_SERVER_PORT:-8080}" ]; then
    echo "FILE_SERVER_PORT diubah ke $_PORT (port lama dipakai proses lain)"
    sed -i "s/^FILE_SERVER_PORT=.*/FILE_SERVER_PORT=$_PORT/" .env
    export FILE_SERVER_PORT=$_PORT
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
