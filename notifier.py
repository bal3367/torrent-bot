import asyncio
import os
import shutil
from telegram import Bot
from aria2_client import get_client, format_size, format_speed
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", 0))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/home/ubuntu/torrent_bot/downloads")
DISK_THRESHOLD = int(os.getenv("DISK_ALERT_THRESHOLD", 80))

_notified_gids: set[str] = set()
_disk_alerted = False


async def notify_loop(bot: Bot):
    global _disk_alerted
    tick = 0
    while True:
        await asyncio.sleep(15)
        try:
            _check_downloads(bot)
        except Exception:
            pass

        tick += 1
        if tick % 20 == 0:  # every 5 minutes (20 * 15s)
            try:
                await _check_disk(bot)
            except Exception:
                pass


def _check_downloads(bot: Bot):
    downloads = get_client().get_downloads()
    for dl in downloads:
        if dl.gid in _notified_gids:
            continue
        if dl.status == "complete" and not (dl.name or "").startswith("[METADATA]"):
            _notified_gids.add(dl.gid)
            name = dl.name or dl.gid
            size = format_size(dl.total_length)
            asyncio.create_task(
                bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f"Download selesai!\n"
                        f"Nama: {name}\n"
                        f"Ukuran: {size}\n"
                        f"Ketik /files untuk lihat file"
                    ),
                )
            )


async def _check_disk(bot: Bot):
    global _disk_alerted
    usage = shutil.disk_usage(DOWNLOAD_DIR)
    pct = (usage.used / usage.total) * 100
    if pct >= DISK_THRESHOLD and not _disk_alerted:
        _disk_alerted = True
        free = format_size(usage.free)
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"Peringatan: disk sudah {pct:.0f}% penuh!\nSisa: {free}",
        )
    elif pct < DISK_THRESHOLD - 5:
        _disk_alerted = False
