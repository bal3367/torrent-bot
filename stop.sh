#!/bin/bash
cd "$(dirname "$0")"

# Watchdog dulu — kalau tidak, dia menghidupkan lagi komponen yang sedang dimatikan di bawah.
screen -S torrent_watchdog -X quit 2>/dev/null && echo "✅ Watchdog stopped." || true

# Stop bot
if screen -list 2>/dev/null | grep -q "torrent_bot"; then
    screen -S torrent_bot -X quit
    echo "✅ Bot stopped."
else
    echo "Bot tidak sedang running."
fi

# Stop file server
if screen -list 2>/dev/null | grep -q "torrent_fileserver"; then
    screen -S torrent_fileserver -X quit
    echo "✅ File server stopped."
fi
pkill -f "python3 file_server.py" 2>/dev/null || true

# Stop cloudflared tunnel
if screen -list 2>/dev/null | grep -q "torrent_tunnel"; then
    screen -S torrent_tunnel -X quit
    echo "✅ Cloudflared tunnel stopped."
fi

# Stop aria2c
if pgrep -x aria2c > /dev/null; then
    [ -f .env ] && source .env
    # aria2 lama (tanpa --save-session) membuang antrian saat dimatikan: simpan dulu download yang
    # belum selesai sebagai magnet, start.sh menambahkannya lagi. aria2 baru menyimpan sesinya sendiri.
    if ! pgrep -af aria2c | grep -q -- "--save-session"; then
        curl -s "http://localhost:${ARIA2_PORT:-6800}/jsonrpc" -d "[
            {\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"aria2.tellActive\",\"params\":[\"token:$ARIA2_SECRET\",[\"infoHash\",\"bittorrent\",\"files\"]]},
            {\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"aria2.tellWaiting\",\"params\":[\"token:$ARIA2_SECRET\",0,1000,[\"infoHash\",\"bittorrent\",\"files\"]]}
        ]" | python3 -c '
import json, sys, urllib.parse
try:
    res = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for r in res:
    for d in r.get("result") or []:
        h = d.get("infoHash")
        if h:
            name = ((d.get("bittorrent") or {}).get("info") or {}).get("name", "")
            if name.startswith("[METADATA]"):
                continue
            print("magnet:?xt=urn:btih:" + h + ("&dn=" + urllib.parse.quote(name) if name else ""))
        else:
            uris = [u["uri"] for f in d.get("files") or [] for u in f.get("uris") or []]
            if uris:
                print(uris[0])
' | sort -u > pending_magnets.txt
        [ -s pending_magnets.txt ] && echo "💾 $(wc -l < pending_magnets.txt) download disimpan, dilanjutkan saat start." || rm -f pending_magnets.txt
    fi
    pkill -x aria2c
    # Tunggu aria2 keluar (dia menulis sesi saat berhenti) sebelum start.sh jalan lagi.
    for _ in $(seq 1 20); do pgrep -x aria2c > /dev/null || break; sleep 0.5; done
    echo "✅ aria2c stopped."
fi

# Stop cloudflared
if pgrep -x cloudflared > /dev/null; then
    pkill -x cloudflared
    echo "✅ cloudflared stopped."
fi
