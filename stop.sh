#!/bin/bash
cd "$(dirname "$0")"

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

# Stop aria2c
if pgrep -x aria2c > /dev/null; then
    pkill -x aria2c
    echo "✅ aria2c stopped."
fi

# Stop cloudflared
if pgrep -x cloudflared > /dev/null; then
    pkill -x cloudflared
    echo "✅ cloudflared stopped."
fi
