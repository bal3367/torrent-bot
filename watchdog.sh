#!/bin/bash
# Torrent Bot — watchdog / self-heal. Dijalankan start.sh di screen 'torrent_watchdog'.
# Tiap CHECK_EVERY detik:
#   aria2      : RPC tidak menjawab                      → start ulang aria2 (antrian aman, ada sesi)
#   file server: http://127.0.0.1:PORT/ bukan 200        → start ulang file server
#   tunnel     : link publik (trycloudflare) tidak 200 3x berturut-turut, atau belum ada link
#                setelah 2 menit                         → start ulang tunnel (link baru)
#   bot        : proses main.py hilang                   → start ulang bot
# Setiap perbaikan + setiap link baru dikirim ke Telegram, jadi link mati tidak dipakai terus.

cd "$(dirname "$0")"
CHECK_EVERY="${WATCHDOG_INTERVAL:-30}"
TUNNEL_FAIL_LIMIT=3
TUNNEL_NO_URL_LIMIT=120

load_env() { set -a; source .env; set +a; ARIA2_PORT="${ARIA2_PORT:-6800}"; FILE_SERVER_PORT="${FILE_SERVER_PORT:-8080}"; }
log() { echo "[watchdog] $(date '+%F %T') $*"; }
tg() {
    [ -n "$BOT_TOKEN" ] && [ -n "$ALLOWED_CHAT_ID" ] || return 0
    curl -s --max-time 10 "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
        --data-urlencode "chat_id=$ALLOWED_CHAT_ID" --data-urlencode "text=$1" \
        --data-urlencode "disable_web_page_preview=true" > /dev/null || true
}
heal() { log "PERBAIKI: $1 — $2"; tg "🛠 Auto-fix ($(hostname)): $1 — $2"; bash start.sh "$1"; }

tunnel_fails=0
no_url_since=""
last_url=""
log "mulai (cek tiap ${CHECK_EVERY}s)"
sleep "${WATCHDOG_STARTUP_DELAY:-20}"  # beri waktu start.sh menyalakan semuanya dulu

while true; do
    load_env

    # aria2
    if ! curl -s --max-time 5 "http://127.0.0.1:$ARIA2_PORT/jsonrpc" \
         -d "{\"jsonrpc\":\"2.0\",\"id\":\"wd\",\"method\":\"aria2.getVersion\",\"params\":[\"token:$ARIA2_SECRET\"]}" | grep -q '"version"'; then
        heal aria2 "RPC aria2 tidak menjawab"
    fi

    # file server
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$FILE_SERVER_PORT/")
    if [ "$code" != "200" ]; then
        heal fileserver "port $FILE_SERVER_PORT jawab '$code'"
        load_env
        tunnel_fails=0
    fi

    # tunnel
    if command -v cloudflared >/dev/null 2>&1; then
        url=$(cat tunnel_url.txt 2>/dev/null)
        if [ -z "$url" ]; then
            [ -z "$no_url_since" ] && no_url_since=$(date +%s)
            if [ $(( $(date +%s) - no_url_since )) -ge $TUNNEL_NO_URL_LIMIT ]; then
                heal tunnel "belum dapat link Cloudflare selama ${TUNNEL_NO_URL_LIMIT}s"
                no_url_since=""
            fi
        else
            no_url_since=""
            pcode=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -I "$url/")
            if [ "$pcode" = "200" ]; then
                tunnel_fails=0
                if [ "$url" != "$last_url" ]; then
                    [ -n "$last_url" ] && tg "🔗 Link download baru ($(hostname)): $url
Link lama sudah tidak berlaku — klik ulang file di bot untuk dapat command baru."
                    log "tunnel OK: $url"
                    last_url="$url"
                fi
            else
                tunnel_fails=$((tunnel_fails + 1))
                log "tunnel gagal ($tunnel_fails/$TUNNEL_FAIL_LIMIT): $url jawab '$pcode'"
                if [ $tunnel_fails -ge $TUNNEL_FAIL_LIMIT ]; then
                    heal tunnel "link $url tidak bisa dibuka (jawab '$pcode')"
                    tunnel_fails=0
                fi
            fi
        fi
    fi

    # bot — kecuali dia sengaja mengalah ke instance lain dengan token yang sama (Conflict, lihat
    # main.py): menghidupkannya lagi bikin dua server saling rebut terus. `bash start.sh` / `make
    # restart` menghapus penanda itu.
    if ! pgrep -f "python3 main.py" > /dev/null; then
        if [ -f yielded.flag ]; then
            [ -z "$yield_logged" ] && log "bot berhenti karena instance lain aktif (yielded.flag) — tidak di-restart" && yield_logged=1
        else
            heal bot "proses bot mati"
        fi
    fi

    sleep "$CHECK_EVERY"
done
