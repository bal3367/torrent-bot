#!/bin/bash
cd "$(dirname "$0")"

# Stop bot
if screen -list | grep -q "torrent_bot"; then
    screen -S torrent_bot -X quit
    echo "✅ Bot stopped."
else
    echo "Bot tidak sedang running."
fi

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
