#!/bin/bash
# Torrent Bot — start semua komponen, atau satu komponen saja.
#   bash start.sh              → (re)start semua: aria2, file server, tunnel, bot, watchdog
#   bash start.sh aria2|fileserver|tunnel|bot|watchdog
#                              → (re)start komponen itu saja (dipakai watchdog.sh untuk self-heal)
# Jalan di VPS mana saja: semua path relatif ke folder bot, user/IP/port dideteksi sendiri
# kalau tidak diisi di .env (lihat .env.example).

cd "$(dirname "$0")"
BOT_DIR="$(pwd)"
[ -f .env ] || { echo "❌ .env tidak ada — copy dari .env.example dulu."; exit 1; }
set -a; source .env; set +a

# ── Default global (berlaku kalau .env kosong) ─────────────────────────────
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$BOT_DIR/downloads}"
ARIA2_PORT="${ARIA2_PORT:-6800}"
FILE_SERVER_PORT="${FILE_SERVER_PORT:-8080}"
# Port tidak valid di .env (mis. 72299 dari percobaan lama) = file server tidak bisa jalan sama sekali.
if ! [[ "$FILE_SERVER_PORT" =~ ^[0-9]+$ ]] || [ "$FILE_SERVER_PORT" -lt 1 ] || [ "$FILE_SERVER_PORT" -gt 65535 ]; then
    echo "FILE_SERVER_PORT=$FILE_SERVER_PORT tidak valid → pakai 8080"
    FILE_SERVER_PORT=8080
fi
export DOWNLOAD_DIR ARIA2_PORT FILE_SERVER_PORT
mkdir -p "$DOWNLOAD_DIR"

if [ -d venv ]; then PY_RUN="source venv/bin/activate && python3"; else PY_RUN="python3"; fi

port_busy() {
    if command -v ss >/dev/null 2>&1; then ss -tln 2>/dev/null | grep -q ":$1 "
    else (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; fi
}

# ── aria2 ──────────────────────────────────────────────────────────────────
# - Sesi disimpan (aria2.session) supaya stop/restart/update tidak menghapus antrian download.
# - Log level notice di folder bot (tanpa --log-level aria2 menulis DEBUG; --daemon pindah ke /).
# - DHT entry point + tracker cadangan: aria2 tidak punya bootstrap DHT bawaan.
ARIA2_SESSION="$BOT_DIR/aria2.session"
# HTTP/HTTPS (TCP) dulu: banyak container/VPS (Vast.ai) memblokir UDP keluar, jadi DHT dan tracker udp://
# mati di sana — tanpa tracker TCP, magnet tanpa tracker bawaan dapat 0 peer.
BT_TRACKERS="http://tracker.opentrackr.org:1337/announce,https://tracker.gbitt.info:443/announce,http://tracker.bt4g.com:2095/announce,http://open.acgnxtracker.com:80/announce,https://tracker.lilithraws.org:443/announce,http://tracker.files.fm:6969/announce,https://trackers.mlsub.net:443/announce,http://bt.okmp3.ru:2710/announce,https://tracker.tamersunion.org:443/announce,udp://tracker.opentrackr.org:1337/announce,udp://open.stealth.si:80/announce,udp://tracker.torrent.eu.org:451/announce,udp://exodus.desync.com:6969/announce,udp://open.demonii.com:1337/announce,udp://explodie.org:6969/announce"
start_aria2() {
    if pgrep -x aria2c > /dev/null; then
        pkill -x aria2c   # SIGTERM: aria2 menulis sesinya dulu sebelum keluar
        for _ in $(seq 1 20); do pgrep -x aria2c > /dev/null || break; sleep 0.5; done
    fi
    touch "$ARIA2_SESSION"
    aria2c \
        --enable-rpc \
        --rpc-listen-all=false \
        --rpc-listen-port="$ARIA2_PORT" \
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
    # Download yang diselamatkan stop.sh dari aria2 versi lama (tanpa sesi): tambahkan lagi.
    if [ -s "$BOT_DIR/pending_magnets.txt" ]; then
        sleep 2
        while IFS= read -r uri; do
            [ -z "$uri" ] && continue
            curl -s "http://127.0.0.1:$ARIA2_PORT/jsonrpc" \
                -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"aria2.addUri\",\"params\":[\"token:$ARIA2_SECRET\",[\"$uri\"]]}" > /dev/null \
                && echo "↻ Dilanjutkan: ${uri:0:80}"
        done < "$BOT_DIR/pending_magnets.txt"
        mv "$BOT_DIR/pending_magnets.txt" "$BOT_DIR/pending_magnets.done"
    fi
}

# ── Port yang dibuka ke internet (Vast.ai dll.) → link download langsung tanpa Cloudflare ──
# Vast.ai memberi VAST_TCP_PORT_<port dalam>=<port luar> + PUBLIC_IPADDR (di env container; sesi SSH
# kadang tidak membawanya, jadi /proc/1/environ juga dibaca). Port dalam pertama yang terbuka dan masih
# kosong dipakai untuk file server, dan AUTO_DIRECT_BASE_URL=http://IP:port_luar ditulis ke .env.
# DIRECT_BASE_URL yang diisi manual di .env selalu menang.
set_env_key() {  # set_env_key KEY VALUE → tulis/ganti di .env
    if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else echo "$1=$2" >> .env; fi
}
host_env() { { env; tr '\0' '\n' < /proc/1/environ 2>/dev/null; } | grep -E '^(VAST_TCP_PORT_[0-9]+|PUBLIC_IPADDR)=' | sort -u; }
pick_open_port() {
    AUTO_DIRECT_BASE_URL=""
    [ -n "$DIRECT_BASE_URL" ] && return  # diatur manual di .env
    local pub; pub=$(host_env | sed -n 's/^PUBLIC_IPADDR=//p' | head -1)
    [ -z "$pub" ] && return
    local line int ext
    for line in $(host_env | grep '^VAST_TCP_PORT_'); do
        int=${line#VAST_TCP_PORT_}; int=${int%%=*}; ext=${line#*=}
        # Konvensi Vast.ai: "port" > 65535 (mis. 72299) bukan port sungguhan, artinya port acak yang
        # nomornya SAMA di dalam & luar container → dengarkan di port luar itu sendiri.
        [ "$int" -gt 65535 ] 2>/dev/null && int=$ext
        case "$int" in 22|"$ARIA2_PORT") continue ;; esac
        if ! port_busy "$int"; then
            FILE_SERVER_PORT=$int
            AUTO_DIRECT_BASE_URL="http://$pub:$ext"
            echo "Port terbuka ke internet: $int → $AUTO_DIRECT_BASE_URL (link langsung, tanpa Cloudflare)"
            return
        fi
        echo "Port terbuka $int (luar $ext) sedang dipakai: $( (ss -tlnp 2>/dev/null | grep ":$int " | grep -o 'users:(([^)]*' | head -1) || echo '?')"
    done
    echo "⚠️  Tidak ada port terbuka yang kosong — download lewat Cloudflare saja (lihat README: buka port di Vast.ai)."
}

# ── File server ────────────────────────────────────────────────────────────
start_fileserver() {
    screen -S torrent_fileserver -X quit 2>/dev/null || true
    pkill -f "python3 file_server.py" 2>/dev/null || true
    sleep 1
    # Port bebas dicari SETELAH file server lama mati — dulu dicek sebelumnya, jadi port file server
    # sendiri dianggap "dipakai" dan naik satu tiap restart (8080 → 8081 → …).
    pick_open_port
    set_env_key AUTO_DIRECT_BASE_URL "$AUTO_DIRECT_BASE_URL"
    local p="$FILE_SERVER_PORT"
    while port_busy "$p"; do echo "Port $p dipakai proses lain, coba $((p+1))..."; p=$((p + 1)); done
    # Selalu tulis ke .env: tunnel (start_tunnel.sh) dan watchdog membaca port dari .env. Dulu cuma ditulis
    # kalau berubah di loop ini, jadi port pilihan pick_open_port tidak pernah masuk .env → tunnel &
    # watchdog menunjuk port lama, watchdog terus me-restart file server yang sebenarnya sehat.
    FILE_SERVER_PORT=$p; export FILE_SERVER_PORT
    set_env_key FILE_SERVER_PORT "$p"
    screen -dmS torrent_fileserver bash -c "$PY_RUN file_server.py 2>&1 | tee -a fileserver.log"
    echo "File server berjalan di screen 'torrent_fileserver' (port $FILE_SERVER_PORT)."
}

# ── Cloudflare tunnel ──────────────────────────────────────────────────────
start_tunnel() {
    screen -S torrent_tunnel -X quit 2>/dev/null || true
    pkill -x cloudflared 2>/dev/null || true
    rm -f tunnel_url.txt
    sleep 1
    if ! command -v cloudflared >/dev/null 2>&1; then
        echo "⚠️  cloudflared tidak terpasang — link download pakai http://IP:port (jalankan install.sh)."
        return
    fi
    screen -dmS torrent_tunnel bash -c "bash start_tunnel.sh 2>&1 | tee -a tunnel.log"
    echo "Cloudflared berjalan di screen 'torrent_tunnel'."
}

# ── Bot ────────────────────────────────────────────────────────────────────
start_bot() {
    rm -f yielded.flag  # start manual / watchdog = instance ini yang aktif lagi
    screen -S torrent_bot -X quit 2>/dev/null || true
    pkill -f "python3 main.py" 2>/dev/null || true
    sleep 1
    screen -dmS torrent_bot bash -c "$PY_RUN main.py 2>&1 | tee -a bot.log"
    echo "Bot berjalan di screen 'torrent_bot'."
}

# ── Watchdog (self-heal) ───────────────────────────────────────────────────
start_watchdog() {
    screen -S torrent_watchdog -X quit 2>/dev/null || true
    screen -dmS torrent_watchdog bash -c "bash watchdog.sh 2>&1 | tee -a watchdog.log"
    echo "Watchdog berjalan di screen 'torrent_watchdog' (cek & perbaiki otomatis tiap 30 detik)."
}

case "${1:-all}" in
    aria2)      start_aria2 ;;
    fileserver) start_fileserver ;;
    tunnel)     start_tunnel ;;
    bot)        start_bot ;;
    watchdog)   start_watchdog ;;
    all)
        screen -S torrent_watchdog -X quit 2>/dev/null || true  # jangan sampai watchdog ikut restart di tengah jalan
        pgrep -x aria2c > /dev/null && echo "aria2c sudah berjalan." || start_aria2
        start_fileserver
        start_tunnel
        start_bot
        start_watchdog
        echo "Lihat log: tail -f bot.log  |  tail -f watchdog.log"
        ;;
    *) echo "Pemakaian: bash start.sh [all|aria2|fileserver|tunnel|bot|watchdog]"; exit 1 ;;
esac
