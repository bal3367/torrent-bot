# Torrent Bot

Telegram bot untuk download torrent via VPS menggunakan aria2c.

## Deploy ke VPS baru

```bash
git clone https://github.com/bal3367/torrent-bot
cd torrent-bot
chmod +x setup.sh start.sh stop.sh
./setup.sh
# Edit .env: isi BOT_TOKEN, ALLOWED_CHAT_ID, VPS_IP
nano .env
./start.sh
```

## Commands

| Command | Fungsi |
|---|---|
| `/add <magnet/url>` | Tambah torrent |
| kirim file `.torrent` | Upload torrent file |
| `/list` | Lihat progress download |
| `/pause <GID>` | Pause download |
| `/resume <GID>` | Resume download |
| `/cancel <GID>` | Batalkan download |
| `/files` | Browse file tersimpan |
| `/link <filename>` | Generate link download |
| `/delete <filename>` | Hapus file |
| `/storage` | Cek disk usage |

## Requirements

- Ubuntu/Debian VPS
- Python 3.10+
- Port 8080 terbuka (untuk file server)

## Stop

```bash
./stop.sh
```
