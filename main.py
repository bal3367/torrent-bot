import asyncio
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import aria2_client as a2
from file_server import start_file_server
from notifier import notify_loop

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", 0))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/home/ubuntu/torrent_bot/downloads")
VPS_IP = os.getenv("VPS_IP", "localhost")
FILE_SERVER_PORT = os.getenv("FILE_SERVER_PORT", "8080")


def auth(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != ALLOWED_CHAT_ID:
            await update.message.reply_text("Akses ditolak.")
            return
        await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


@auth
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "Torrent Bot siap!\n\n"
        "/add <magnet/url> — tambah torrent\n"
        "  kirim file .torrent langsung ke chat\n"
        "/list — lihat download aktif\n"
        "/pause <GID> — pause download\n"
        "/resume <GID> — resume download\n"
        "/cancel <GID> — batalkan download\n"
        "/files — lihat file tersimpan\n"
        "/link <nama_file> — buat link download\n"
        "/delete <nama_file> — hapus file\n"
        "/storage — cek disk usage"
    )
    await update.message.reply_text(text)


@auth
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /add <magnet: atau https://...torrent>")
        return
    uri = ctx.args[0]
    try:
        gid = a2.add_magnet(uri)
        await update.message.reply_text(f"Ditambahkan!\nGID: {gid}")
    except Exception as e:
        await update.message.reply_text(f"Gagal: {e}")


@auth
async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".torrent"):
        return
    msg = await update.message.reply_text("Mendownload file .torrent...")
    file = await ctx.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        try:
            gid = a2.add_torrent_file(tmp.name)
            await msg.edit_text(f"Ditambahkan!\nGID: {gid}")
        except Exception as e:
            await msg.edit_text(f"Gagal: {e}")
        finally:
            os.unlink(tmp.name)


@auth
async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    downloads = a2.list_downloads()
    active = [d for d in downloads if d.status in ("active", "waiting", "paused")]
    if not active:
        await update.message.reply_text("Tidak ada download aktif.")
        return
    lines = []
    for d in active:
        name = (d.name or d.gid)[:40]
        pct = d.progress if hasattr(d, "progress") else 0
        speed = a2.format_speed(d.download_speed) if d.status == "active" else d.status
        lines.append(f"{name}\n  GID: {d.gid} | {pct:.1f}% | {speed}")
    await update.message.reply_text("\n\n".join(lines))


@auth
async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /pause <GID>")
        return
    ok = a2.pause_download(ctx.args[0])
    await update.message.reply_text("Di-pause." if ok else "GID tidak ditemukan.")


@auth
async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /resume <GID>")
        return
    ok = a2.resume_download(ctx.args[0])
    await update.message.reply_text("Dilanjutkan." if ok else "GID tidak ditemukan.")


@auth
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /cancel <GID>")
        return
    ok = a2.cancel_download(ctx.args[0])
    await update.message.reply_text("Dibatalkan." if ok else "GID tidak ditemukan.")


@auth
async def cmd_files(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    entries = sorted(Path(DOWNLOAD_DIR).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not entries:
        await update.message.reply_text("Folder download kosong.")
        return
    buttons = []
    for e in entries[:20]:
        size = a2.format_size(e.stat().st_size) if e.is_file() else "dir"
        label = f"{'[D]' if e.is_dir() else ''}{e.name[:35]} ({size})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"fileinfo:{e.name}")])
    await update.message.reply_text(
        "File tersimpan (20 terbaru):",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_fileinfo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    path = Path(DOWNLOAD_DIR) / filename
    if not path.exists():
        await query.edit_message_text("File tidak ditemukan.")
        return
    size = a2.format_size(path.stat().st_size) if path.is_file() else "-"
    link = f"http://{VPS_IP}:{FILE_SERVER_PORT}/{filename}"
    buttons = [
        [
            InlineKeyboardButton("Link download", url=link),
            InlineKeyboardButton("Hapus", callback_data=f"confirmdelete:{filename}"),
        ]
    ]
    await query.edit_message_text(
        f"Nama: {filename}\nUkuran: {size}\nLink: {link}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_confirmdelete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    buttons = [
        [
            InlineKeyboardButton("Ya, hapus", callback_data=f"dodelete:{filename}"),
            InlineKeyboardButton("Batal", callback_data="canceldelete"),
        ]
    ]
    await query.edit_message_text(
        f"Hapus '{filename}'? Ini tidak bisa dibatalkan.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_dodelete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    path = Path(DOWNLOAD_DIR) / filename
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        await query.edit_message_text(f"'{filename}' berhasil dihapus.")
    except Exception as e:
        await query.edit_message_text(f"Gagal hapus: {e}")


async def cb_canceldelete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Penghapusan dibatalkan.")


@auth
async def cmd_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /link <nama_file>")
        return
    filename = " ".join(ctx.args)
    path = Path(DOWNLOAD_DIR) / filename
    if not path.exists():
        await update.message.reply_text("File tidak ditemukan.")
        return
    link = f"http://{VPS_IP}:{FILE_SERVER_PORT}/{filename}"
    await update.message.reply_text(f"Link download:\n{link}")


@auth
async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /delete <nama_file>")
        return
    filename = " ".join(ctx.args)
    path = Path(DOWNLOAD_DIR) / filename
    if not path.exists():
        await update.message.reply_text("File tidak ditemukan.")
        return
    buttons = [
        [
            InlineKeyboardButton("Ya, hapus", callback_data=f"dodelete:{filename}"),
            InlineKeyboardButton("Batal", callback_data="canceldelete"),
        ]
    ]
    await update.message.reply_text(
        f"Hapus '{filename}'? Ini tidak bisa dibatalkan.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@auth
async def cmd_storage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    usage = shutil.disk_usage(DOWNLOAD_DIR)
    pct = (usage.used / usage.total) * 100
    text = (
        f"Disk usage: {pct:.1f}%\n"
        f"Terpakai: {a2.format_size(usage.used)}\n"
        f"Bebas: {a2.format_size(usage.free)}\n"
        f"Total: {a2.format_size(usage.total)}"
    )
    await update.message.reply_text(text)


async def post_init(app: Application):
    asyncio.create_task(start_file_server())
    asyncio.create_task(notify_loop(app.bot))


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("files", cmd_files))
    app.add_handler(CommandHandler("link", cmd_link))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("storage", cmd_storage))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(cb_fileinfo, pattern=r"^fileinfo:"))
    app.add_handler(CallbackQueryHandler(cb_confirmdelete, pattern=r"^confirmdelete:"))
    app.add_handler(CallbackQueryHandler(cb_dodelete, pattern=r"^dodelete:"))
    app.add_handler(CallbackQueryHandler(cb_canceldelete, pattern=r"^canceldelete$"))

    print("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
