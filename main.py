import asyncio
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
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


def reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📥 Tambah Torrent", "📋 List Download"],
        ["📁 Browse File",    "💾 Storage"],
    ], resize_keyboard=True)


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Tambah Torrent", callback_data="menu:add")],
        [InlineKeyboardButton("📋 List Download", callback_data="menu:list")],
        [InlineKeyboardButton("📁 Browse File", callback_data="menu:files")],
        [InlineKeyboardButton("💾 Storage", callback_data="menu:storage")],
    ])


def back_button():
    return [[InlineKeyboardButton("← Menu", callback_data="menu:main")]]


@auth
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Torrent Bot siap! Pilih menu:",
        reply_markup=reply_keyboard(),
    )


@auth
async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Menu utama:",
        reply_markup=reply_keyboard(),
    )


MENU_TEXTS = {"📥 Tambah Torrent", "📋 List Download", "📁 Browse File", "💾 Storage"}


@auth
async def handle_reply_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📥 Tambah Torrent":
        ctx.user_data["waiting_for_link"] = True
        await update.message.reply_text("Kirim magnet link atau URL .torrent:")
    elif text == "📋 List Download":
        await cmd_list(update, ctx)
    elif text == "📁 Browse File":
        await cmd_files(update, ctx)
    elif text == "💾 Storage":
        await cmd_storage(update, ctx)


@auth
async def handle_torrent_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("waiting_for_link"):
        return
    ctx.user_data["waiting_for_link"] = False
    uri = update.message.text.strip()
    try:
        gid = a2.add_uri(uri)
        await update.message.reply_text(f"Ditambahkan!\nGID: {gid}")
    except Exception as e:
        await update.message.reply_text(f"Gagal: {e}")


async def cb_mainmenu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "main":
        await query.edit_message_text("Menu utama:", reply_markup=main_menu_keyboard())

    elif action == "add":
        await query.edit_message_text(
            "Cara tambah torrent:\n\n"
            "1. Kirim pesan: /add <magnet link atau URL .torrent>\n"
            "2. Atau kirim file .torrent langsung ke chat ini",
            reply_markup=InlineKeyboardMarkup(back_button()),
        )

    elif action == "list":
        downloads = a2.list_downloads()
        active = [d for d in downloads if d.status in ("active", "waiting", "paused") and not (d.name or "").startswith("[METADATA]")]
        if not active:
            await query.edit_message_text(
                "Tidak ada download aktif.",
                reply_markup=InlineKeyboardMarkup(back_button()),
            )
            return
        buttons = []
        lines = []
        for d in active:
            name = (d.name or d.gid)[:35]
            pct = d.progress if hasattr(d, "progress") else 0
            done = a2.format_size(d.completed_length)
            total = a2.format_size(d.total_length) if d.total_length else "?"
            speed = a2.format_speed(d.download_speed) if d.status == "active" else f"⏸ {d.status}"
            lines.append(f"{name}\n  {done} / {total} ({pct:.1f}%) | {speed}")
            buttons.append([
                InlineKeyboardButton("⏸", callback_data=f"dlaction:pause:{d.gid}"),
                InlineKeyboardButton("▶", callback_data=f"dlaction:resume:{d.gid}"),
                InlineKeyboardButton("❌", callback_data=f"dlaction:cancel:{d.gid}"),
                InlineKeyboardButton(name[:20], callback_data=f"dlaction:noop:{d.gid}"),
            ])
        buttons += back_button()
        await query.edit_message_text(
            "\n\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action == "files":
        p = Path(DOWNLOAD_DIR)
        entries = sorted(p.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True) if p.exists() else []
        if not entries:
            await query.edit_message_text(
                "Folder download kosong.",
                reply_markup=InlineKeyboardMarkup(back_button()),
            )
            return
        buttons = []
        for e in entries[:20]:
            size = a2.format_size(e.stat().st_size) if e.is_file() else "dir"
            label = f"{'[D] ' if e.is_dir() else ''}{e.name[:32]} ({size})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"fileinfo:{e.name}")])
        buttons += back_button()
        await query.edit_message_text(
            "File tersimpan (20 terbaru):",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action == "storage":
        usage = shutil.disk_usage(DOWNLOAD_DIR)
        pct = (usage.used / usage.total) * 100
        text = (
            f"Disk usage: {pct:.1f}%\n"
            f"Terpakai: {a2.format_size(usage.used)}\n"
            f"Bebas: {a2.format_size(usage.free)}\n"
            f"Total: {a2.format_size(usage.total)}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_button()))


async def cb_dlaction(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":", 2)
    action, gid = parts[1], parts[2]

    if action == "pause":
        ok = a2.pause_download(gid)
        await query.answer("⏸ Di-pause." if ok else "Gagal.", show_alert=True)
    elif action == "resume":
        ok = a2.resume_download(gid)
        await query.answer("▶ Dilanjutkan." if ok else "Gagal.", show_alert=True)
    elif action == "cancel":
        ok = a2.cancel_download(gid)
        await query.answer("❌ Dibatalkan." if ok else "Gagal.", show_alert=True)
    elif action == "noop":
        await query.answer()
        return

    # Refresh list setelah aksi
    downloads = a2.list_downloads()
    active = [d for d in downloads if d.status in ("active", "waiting", "paused") and not (d.name or "").startswith("[METADATA]")]
    if not active:
        await query.edit_message_text(
            "Tidak ada download aktif.",
            reply_markup=InlineKeyboardMarkup(back_button()),
        )
        return
    buttons = []
    lines = []
    for d in active:
        name = (d.name or d.gid)[:35]
        pct = d.progress if hasattr(d, "progress") else 0
        done = a2.format_size(d.completed_length)
        total = a2.format_size(d.total_length) if d.total_length else "?"
        speed = a2.format_speed(d.download_speed) if d.status == "active" else f"⏸ {d.status}"
        lines.append(f"{name}\n  {done} / {total} ({pct:.1f}%) | {speed}")
        buttons.append([
            InlineKeyboardButton("⏸", callback_data=f"dlaction:pause:{d.gid}"),
            InlineKeyboardButton("▶", callback_data=f"dlaction:resume:{d.gid}"),
            InlineKeyboardButton("❌", callback_data=f"dlaction:cancel:{d.gid}"),
            InlineKeyboardButton(name[:20], callback_data=f"dlaction:noop:{d.gid}"),
        ])
    buttons += back_button()
    await query.edit_message_text(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@auth
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Penggunaan: /add <magnet: atau https://...torrent>")
        return
    uri = ctx.args[0]
    try:
        gid = a2.add_uri(uri)
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
    active = [d for d in downloads if d.status in ("active", "waiting", "paused") and not (d.name or "").startswith("[METADATA]")]
    if not active:
        await update.message.reply_text("Tidak ada download aktif.")
        return
    lines = []
    for d in active:
        name = (d.name or d.gid)[:40]
        pct = d.progress if hasattr(d, "progress") else 0
        done = a2.format_size(d.completed_length)
        total = a2.format_size(d.total_length) if d.total_length else "?"
        speed = a2.format_speed(d.download_speed) if d.status == "active" else f"⏸ {d.status}"
        lines.append(f"{name}\n  GID: {d.gid}\n  {done} / {total} ({pct:.1f}%) | {speed}")
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
    if path.is_file():
        size_bytes = path.stat().st_size
    else:
        size_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    size = a2.format_size(size_bytes)
    link = f"http://{VPS_IP}:{FILE_SERVER_PORT}/{filename}"
    buttons = [
        [
            InlineKeyboardButton("⬇ HTTP Link", url=link),
            InlineKeyboardButton("📤 Kirim TG", callback_data=f"sendtg:{filename}"),
        ],
        [InlineKeyboardButton("🗑 Hapus", callback_data=f"confirmdelete:{filename}")],
        [InlineKeyboardButton("← Kembali ke File", callback_data="menu:files")],
        back_button()[0],
    ]
    await query.edit_message_text(
        f"📄 *{filename}*\nUkuran: {size}\nHTTP: `{link}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_sendtg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    path = Path(DOWNLOAD_DIR) / filename
    if not path.exists():
        await query.message.reply_text("File tidak ditemukan.")
        return

    # Hitung total ukuran
    if path.is_file():
        size_bytes = path.stat().st_size
    else:
        size_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    LIMIT = 45 * 1024 * 1024  # 45 MB

    if size_bytes <= LIMIT:
        # Kirim langsung via Telegram
        msg = await query.message.reply_text("📤 Mengirim file, mohon tunggu...")
        try:
            with open(path, "rb") as f:
                await ctx.bot.send_document(
                    chat_id=ALLOWED_CHAT_ID,
                    document=f,
                    filename=filename,
                )
            await msg.edit_text(f"✅ File '{filename}' berhasil dikirim!")
        except Exception as e:
            await msg.edit_text(f"❌ Gagal kirim: {e}")
    else:
        # File terlalu besar — kirim instruksi
        link = f"http://{VPS_IP}:{FILE_SERVER_PORT}/{filename}"
        scp_path = f"{DOWNLOAD_DIR}/{filename}"
        scp_cmd = f"scp ubuntu@{VPS_IP}:'{scp_path}' ./"
        await query.message.reply_text(
            f"⚠️ *File terlalu besar untuk Telegram* ({a2.format_size(size_bytes)})\n"
            f"Batas upload bot: 45 MB\n\n"
            f"*Cara 1 — HTTP* (buka port 8080 di cloud console dulu):\n"
            f"`{link}`\n\n"
            f"*Cara 2 — SCP* (langsung bisa, pakai terminal):\n"
            f"`{scp_cmd}`",
            parse_mode="Markdown",
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
        await query.edit_message_text(
            f"'{filename}' berhasil dihapus.",
            reply_markup=InlineKeyboardMarkup(back_button()),
        )
    except Exception as e:
        await query.edit_message_text(f"Gagal hapus: {e}")


async def cb_canceldelete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Penghapusan dibatalkan.",
        reply_markup=InlineKeyboardMarkup(back_button()),
    )


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
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    asyncio.create_task(start_file_server())
    asyncio.create_task(notify_loop(app.bot))
    # Startup notification
    try:
        import socket
        hostname = socket.gethostname()
        try:
            with urllib.request.urlopen("https://ifconfig.me/ip", timeout=5) as r:
                pub_ip = r.read().decode().strip()
        except Exception:
            pub_ip = VPS_IP
        await app.bot.send_message(
            chat_id=ALLOWED_CHAT_ID,
            text=(
                f"🟢 *Torrent Bot Online!*\n"
                f"🖥 Host: `{hostname}`\n"
                f"📡 IP: `{pub_ip}`\n"
                f"📂 Dir: `{DOWNLOAD_DIR}`\n\n"
                f"Ketik /start untuk melihat commands."
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("files", cmd_files))
    app.add_handler(CommandHandler("link", cmd_link))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("storage", cmd_storage))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f"^({'|'.join(MENU_TEXTS)})$"),
        handle_reply_buttons,
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_torrent_link,
    ))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(cb_mainmenu, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(cb_dlaction, pattern=r"^dlaction:"))
    app.add_handler(CallbackQueryHandler(cb_fileinfo, pattern=r"^fileinfo:"))
    app.add_handler(CallbackQueryHandler(cb_sendtg, pattern=r"^sendtg:"))
    app.add_handler(CallbackQueryHandler(cb_confirmdelete, pattern=r"^confirmdelete:"))
    app.add_handler(CallbackQueryHandler(cb_dodelete, pattern=r"^dodelete:"))
    app.add_handler(CallbackQueryHandler(cb_canceldelete, pattern=r"^canceldelete$"))

    print("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
