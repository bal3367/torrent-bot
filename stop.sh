#!/bin/bash
screen -S torrent_bot -X quit 2>/dev/null && echo "Bot stopped." || echo "Screen tidak ditemukan."
pkill -x aria2c 2>/dev/null && echo "aria2c stopped." || echo "aria2c tidak berjalan."
