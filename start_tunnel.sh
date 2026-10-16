#!/bin/bash
# Jalankan cloudflared dan simpan URL ke tunnel_url.txt
# Script ini dijalankan di screen sendiri supaya survive bot restart.
# cloudflared (quick tunnel) bisa putus/keluar sendiri; dulu screen-nya ikut selesai, tunnel_url.txt
# tetap berisi URL mati dan bot terus membagikan link yang kena Error 1033. Sekarang: loop, URL lama
# dihapus begitu cloudflared berhenti, cloudflared dijalankan lagi dan URL barunya disimpan.

cd "$(dirname "$0")"
source .env

PORT="${FILE_SERVER_PORT:-8080}"
URL_FILE="$(pwd)/tunnel_url.txt"

while true; do
    rm -f "$URL_FILE"
    echo "[tunnel] $(date '+%F %T') Starting cloudflared → localhost:$PORT"
    cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate 2>&1 | while IFS= read -r line; do
        echo "$line"
        # Tangkap URL trycloudflare.com dan simpan ke file
        if echo "$line" | grep -qo 'https://[a-z0-9-]*\.trycloudflare\.com'; then
            url=$(echo "$line" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com')
            echo "$url" > "$URL_FILE"
            echo "[tunnel] ✅ URL saved: $url"
        fi
    done
    rm -f "$URL_FILE"
    echo "[tunnel] $(date '+%F %T') cloudflared berhenti — URL lama dihapus, start ulang dalam 5 detik"
    sleep 5
done
