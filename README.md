# 🤖 Torrent Bot

Telegram bot untuk download torrent via VPS — auto Cloudflare tunnel, server list, ZIP & SCP transfer.

## 🚀 Install

```bash
git clone https://github.com/bal3367/torrent-bot.git ~/torrent_bot && ~/torrent_bot/install.sh
```

Setelah install selesai → cek Telegram, bot langsung kirim notifikasi online + link download.

## 🔄 Update ke versi terbaru

```bash
cd ~/torrent_bot && make update
```

## 🛠 Commands

```bash
make              # install & start
make start        # start bot
make stop         # stop bot
make restart      # restart bot
make update       # pull update terbaru & restart
make uninstall    # hapus bot dari VPS
```

## 🗑 Uninstall

```bash
bash /home/ubuntu/torrent_bot/uninstall.sh
```

Atau satu command langsung dari internet:

```bash
curl -sL https://raw.githubusercontent.com/bal3367/torrent-bot/main/uninstall.sh | bash
```

Script akan tanya konfirmasi, minta pilihan hapus downloads atau tidak, lalu stop semua proses (bot, aria2c, cloudflared) dan hapus folder bot.

## ⚠️ Multi-VPS

Bot pakai 1 token → hanya **1 VPS boleh running sekaligus**.
Mau pindah VPS? Stop dulu bot lama via Telegram → 🖥 Server List → 🗑 (auto stop).

## 📱 Fitur Bot

| Fitur | Keterangan |
|-------|-----------|
| 📥 Tambah Torrent | Kirim magnet link / .torrent URL / upload file |
| 📋 List Download | Progress + speed + ukuran real-time |
| 📁 Browse File | Browse & download file hasil download |
| 📦 Zip Folder | Gabungkan semua file jadi 1 ZIP |
| 📋 SCP Command | Command PowerShell untuk download ke PC |
| 🌐 CF Tunnel | Auto public HTTPS URL tiap startup |
| 🖥 Server List | Manage multi-VPS, toggle, delete = stop |
