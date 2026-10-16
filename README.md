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
bash ~/torrent_bot/uninstall.sh
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

## ⚙️ Jalan di VPS mana saja

Semua otomatis — path relatif ke folder bot, IP publik & user dideteksi sendiri. Override di `.env` kalau perlu:

| Variabel | Default | Keterangan |
|---|---|---|
| `DOWNLOAD_DIR` | `~/torrent_bot/downloads` | folder hasil download |
| `VPS_IP` | `auto` | IP publik, dideteksi saat start |
| `SSH_USER` / `SSH_PORT` / `SSH_HOST` | user bot / `22` / IP | dipakai di command SCP (Vast.ai: isi `SSH_PORT`) |
| `FILE_SERVER_PORT` | `8080` | kalau dipakai proses lain, otomatis pindah ke port bebas |

## 🛠 Self-heal (watchdog)

`make start` juga menjalankan watchdog (screen `torrent_watchdog`, log di `watchdog.log`). Tiap 30 detik ia mengecek:

- **aria2** tidak menjawab → start ulang (antrian download aman, tersimpan di `aria2.session`)
- **file server** mati → start ulang
- **link Cloudflare** tidak bisa dibuka 3× berturut-turut → tunnel start ulang, **link baru dikirim ke Telegram**
- **bot** mati → start ulang (kecuali sengaja berhenti karena bot yang sama aktif di VPS lain)

Setiap perbaikan dilaporkan ke Telegram.

## 🚀 Download kecepatan penuh (tanpa Cloudflare)

Link Cloudflare (`trycloudflare.com`) dibatasi kecepatannya. Kalau VPS punya port yang terbuka ke internet,
bot otomatis memakai link langsung `http://IP:port`:

- **Vast.ai:** `start.sh` membaca `VAST_TCP_PORT_*` + `PUBLIC_IPADDR`, memilih port terbuka yang masih kosong
  untuk file server, dan menulis `AUTO_DIRECT_BASE_URL` di `.env`. Belum ada port terbuka? Edit template
  instance → *Docker options* tambah mis. `-p 8000:8000` → buat instance baru dari template itu.
- **VPS biasa:** buka port `FILE_SERVER_PORT` di firewall, lalu isi `DIRECT_BASE_URL=http://IP:PORT` di `.env`.

