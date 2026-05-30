#!/bin/bash
# Jalankan cloudflared dan simpan URL ke tunnel_url.txt
# Script ini dijalankan di screen sendiri supaya survive bot restart

cd "$(dirname "$0")"
source .env

PORT="${FILE_SERVER_PORT:-8080}"
URL_FILE="$(dirname "$0")/tunnel_url.txt"

# Hapus URL lama
rm -f "$URL_FILE"

echo "[tunnel] Starting cloudflared → localhost:$PORT"

cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate 2>&1 | while IFS= read -r line; do
    echo "$line"
    # Tangkap URL trycloudflare.com dan simpan ke file
    if echo "$line" | grep -qo 'https://[a-z0-9-]*\.trycloudflare\.com'; then
        url=$(echo "$line" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com')
        echo "$url" > "$URL_FILE"
        echo "[tunnel] ✅ URL saved: $url"
    fi
done
