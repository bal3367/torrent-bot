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
import tunnel as tun
import servers as srv

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
        ["🖥 Server List"],
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


MENU_TEXTS = {"📥 Tambah Torrent", "📋 List Download", "📁 Browse File", "💾 Storage", "🖥 Server List"}


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
    elif text == "🖥 Server List":
        await cmd_servers(update, ctx)


@auth
async def handle_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Single handler untuk semua free-text input: torrent link & tambah server."""
    if ctx.user_data.get("waiting_for_server"):
        ctx.user_data["waiting_for_server"] = False
        text = update.message.text.strip()
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2:
            await update.message.reply_text(
                "Format salah. Gunakan: `LABEL | IP | PORT`", parse_mode="Markdown"
            )
            return
        label = parts[0]
        ip = parts[1]
        port = parts[2] if len(parts) > 2 else "8080"
        server_list = srv.get_servers()
        server_list.append({
            "label": label, "ip": ip, "file_server_port": port,
            "tunnel_url": None, "active": True, "notes": "",
        })
        srv.save_servers(server_list)
        statuses = await srv.check_all_online(server_list)
        text_out, buttons = _server_list_text_buttons(server_list, statuses)
        await update.message.reply_text(
            f"✅ Server *{label}* (`{ip}`) ditambahkan!\n\n" + text_out,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif ctx.user_data.get("waiting_for_link"):
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
    import urllib.parse
    base_url = tun.tunnel_url or f"http://{VPS_IP}:{FILE_SERVER_PORT}"
    label_link = "🌐 Download (CF)" if tun.tunnel_url else "⬇ HTTP Link"

    if path.is_dir():
        zip_name = filename + ".zip"
        zip_path = Path(DOWNLOAD_DIR) / zip_name
        zip_exists = zip_path.exists()
        zip_link = f"{base_url}/{urllib.parse.quote(zip_name)}"
        link = f"{base_url}/{urllib.parse.quote(filename)}"
        scp_flag = "-r"  # rekursif untuk folder
        scp_target = f"{DOWNLOAD_DIR}/{filename}/"
        buttons = [
            [InlineKeyboardButton(label_link, url=link)],
            [InlineKeyboardButton(
                f"📦 {'Download ZIP' if zip_exists else 'Buat ZIP'} ({size})",
                callback_data=f"makezip:{filename}" if not zip_exists else f"zipready:{filename}",
            )],
            [InlineKeyboardButton("📋 SCP Command", callback_data=f"scpcmd:{filename}")],
            [InlineKeyboardButton("🗑 Hapus Folder", callback_data=f"confirmdelete:{filename}")],
            [InlineKeyboardButton("← Kembali ke File", callback_data="menu:files")],
        ]
        info = f"📁 *{filename}*\nUkuran: {size} ({sum(1 for _ in path.rglob('*') if _.is_file())} file)"
        if zip_exists:
            info += f"\n✅ ZIP sudah ada → [download]({zip_link})"
    else:
        link = f"{base_url}/{urllib.parse.quote(filename)}"
        buttons = [
            [
                InlineKeyboardButton(label_link, url=link),
                InlineKeyboardButton("📤 Kirim TG", callback_data=f"sendtg:{filename}"),
            ],
            [InlineKeyboardButton("📋 SCP Command", callback_data=f"scpcmd:{filename}")],
            [InlineKeyboardButton("🗑 Hapus", callback_data=f"confirmdelete:{filename}")],
            [InlineKeyboardButton("← Kembali ke File", callback_data="menu:files")],
        ]
        info = f"📄 *{filename}*\nUkuran: {size}\n🔗 `{link}`"

    await query.edit_message_text(
        info,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
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
        # File terlalu besar — kirim link CF tunnel atau fallback SCP
        import urllib.parse
        base_url = tun.tunnel_url or f"http://{VPS_IP}:{FILE_SERVER_PORT}"
        link = f"{base_url}/{urllib.parse.quote(filename)}"
        scp_cmd = f"scp ubuntu@{VPS_IP}:'{DOWNLOAD_DIR}/{filename}' ./"
        if tun.tunnel_url:
            msg = (
                f"📦 *{filename}*\n"
                f"Ukuran: {a2.format_size(size_bytes)}\n\n"
                f"🌐 *Download via browser* (klik link):\n"
                f"{link}"
            )
        else:
            msg = (
                f"⚠️ *File terlalu besar untuk Telegram* ({a2.format_size(size_bytes)})\n\n"
                f"*Cara 1 — HTTP* (buka port 8080 di cloud console):\n`{link}`\n\n"
                f"*Cara 2 — SCP* (pakai terminal/WinSCP):\n`{scp_cmd}`"
            )
        await query.message.reply_text(msg, parse_mode="Markdown")


async def cb_scpcmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Kirim SCP command siap pakai untuk Windows PowerShell / Linux terminal."""
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    path = Path(DOWNLOAD_DIR) / filename

    # Cek apakah zip sudah ada, prioritaskan zip
    zip_name = filename + ".zip"
    zip_path = Path(DOWNLOAD_DIR) / zip_name
    if zip_path.exists():
        target = f"{DOWNLOAD_DIR}/{zip_name}"
        flag = ""
        display_name = zip_name
    elif path.is_dir():
        target = f"{DOWNLOAD_DIR}/{filename}/"
        flag = "-r "
        display_name = filename + "/ (semua file)"
    else:
        target = f"{DOWNLOAD_DIR}/{filename}"
        flag = ""
        display_name = filename

    cmd_win = f'scp {flag}ubuntu@{VPS_IP}:"{target}" "C:\\Users\\YourName\\Downloads\\"'
    cmd_mac = f"scp {flag}ubuntu@{VPS_IP}:'{target}' ~/Downloads/"

    await query.message.reply_text(
        f"📋 *SCP Command — Download Langsung (Speed Penuh)*\n"
        f"File: `{display_name}`\n\n"
        f"*Windows PowerShell:*\n"
        f"`{cmd_win}`\n\n"
        f"*Mac / Linux Terminal:*\n"
        f"`{cmd_mac}`\n\n"
        f"💡 Ganti `YourName` sesuai username Windows kamu.\n"
        f"Port 22 SSH selalu terbuka — works di semua VPS provider.",
        parse_mode="Markdown",
    )


def _create_zip_sync(src_path: Path, zip_path: Path):
    """Buat zip dari folder (sync, dijalankan di thread pool)."""
    import zipfile
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for file in src_path.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(src_path.parent))


async def cb_makezip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mulai buat ZIP dari folder, kirim notifikasi saat selesai."""
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    src_path = Path(DOWNLOAD_DIR) / filename
    zip_name = filename + ".zip"
    zip_path = Path(DOWNLOAD_DIR) / zip_name

    if not src_path.exists():
        await query.message.reply_text("Folder tidak ditemukan.")
        return

    if zip_path.exists():
        # Sudah ada, langsung kirim link
        import urllib.parse
        base_url = tun.tunnel_url or f"http://{VPS_IP}:{FILE_SERVER_PORT}"
        link = f"{base_url}/{urllib.parse.quote(zip_name)}"
        await query.message.reply_text(
            f"✅ ZIP sudah ada!\n🌐 Download: {link}", parse_mode="Markdown"
        )
        return

    # Hitung ukuran & estimasi waktu
    total = sum(f.stat().st_size for f in src_path.rglob("*") if f.is_file())
    msg = await query.message.reply_text(
        f"⏳ *Membuat ZIP...*\n"
        f"📦 {filename}\n"
        f"Ukuran: {a2.format_size(total)}\n\n"
        f"Mohon tunggu, ini mungkin butuh beberapa menit...",
        parse_mode="Markdown",
    )

    # Jalankan zip di thread pool agar tidak block bot
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _create_zip_sync, src_path, zip_path)
    except Exception as e:
        await msg.edit_text(f"❌ Gagal buat ZIP: {e}")
        return

    zip_size = a2.format_size(zip_path.stat().st_size)
    import urllib.parse
    base_url = tun.tunnel_url or f"http://{VPS_IP}:{FILE_SERVER_PORT}"
    link = f"{base_url}/{urllib.parse.quote(zip_name)}"
    scp_win = f'scp ubuntu@{VPS_IP}:"{DOWNLOAD_DIR}/{zip_name}" "C:\\Users\\YourName\\Downloads\\"'
    await msg.edit_text(
        f"✅ *ZIP selesai!*\n"
        f"📦 `{zip_name}`\n"
        f"Ukuran: {zip_size}\n\n"
        f"🌐 *Browser (CF Tunnel):*\n{link}\n\n"
        f"⚡ *PowerShell (speed penuh):*\n`{scp_win}`",
        parse_mode="Markdown",
    )


async def cb_zipready(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ZIP sudah ada — langsung kirim link."""
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    zip_name = filename + ".zip"
    zip_path = Path(DOWNLOAD_DIR) / zip_name
    import urllib.parse
    base_url = tun.tunnel_url or f"http://{VPS_IP}:{FILE_SERVER_PORT}"
    link = f"{base_url}/{urllib.parse.quote(zip_name)}"
    size = a2.format_size(zip_path.stat().st_size) if zip_path.exists() else "?"
    await query.message.reply_text(
        f"📦 *{zip_name}*\nUkuran: {size}\n\n🌐 Download: {link}",
        parse_mode="Markdown",
    )


def _server_list_text_buttons(servers: list[dict], statuses: list[bool]):
    """Build teks + inline buttons untuk server list."""
    if not servers:
        return "🖥 *Server List*\n\nBelum ada server terdaftar.", [
            [InlineKeyboardButton("➕ Tambah Server", callback_data="srv:add")],
        ]
    lines = ["🖥 *Server List*\n"]
    buttons = []
    for i, (s, online) in enumerate(zip(servers, statuses)):
        status = "✅ Online" if online else "❌ Offline"
        active_icon = "" if s.get("active", True) else " ⏸"
        lines.append(f"{i+1}. *{s['label']}*{active_icon} — {status}")
        row = [
            InlineKeyboardButton(
                f"{'⏸ Disable' if s.get('active', True) else '▶ Enable'}",
                callback_data=f"srv:toggle:{i}",
            ),
            InlineKeyboardButton("📋 Info", callback_data=f"srv:info:{i}"),
            InlineKeyboardButton("🗑", callback_data=f"srv:confirmdelete:{i}"),
        ]
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("➕ Tambah Server", callback_data="srv:add"),
        InlineKeyboardButton("🔄 Refresh", callback_data="srv:refresh"),
    ])
    return "\n".join(lines), buttons


@auth
async def cmd_servers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tampilkan server list dengan status online."""
    msg = await update.message.reply_text("🔄 Mengecek status server...")
    servers = srv.get_servers()
    statuses = await srv.check_all_online(servers) if servers else []
    text, buttons = _server_list_text_buttons(servers, statuses)
    await msg.edit_text(text, parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(buttons))


async def cb_srv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handler semua callback srv:*"""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 2)
    action = parts[1]
    idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    servers = srv.get_servers()

    if action == "refresh":
        await query.edit_message_text("🔄 Mengecek status server...")
        statuses = await srv.check_all_online(servers) if servers else []
        text, buttons = _server_list_text_buttons(servers, statuses)
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "toggle" and idx is not None:
        servers[idx]["active"] = not servers[idx].get("active", True)
        srv.save_servers(servers)
        statuses = await srv.check_all_online(servers)
        text, buttons = _server_list_text_buttons(servers, statuses)
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "info" and idx is not None:
        s = servers[idx]
        ip = s.get("ip", "?")
        port = s.get("file_server_port", "8080")
        tunnel = s.get("tunnel_url") or "-"
        active = "✅ Enabled" if s.get("active", True) else "⏸ Disabled"
        scp_win = f'scp -r ubuntu@{ip}:"/home/ubuntu/torrent_bot/downloads/" "C:\\Users\\YourName\\Downloads\\"'
        scp_mac = f"scp -r ubuntu@{ip}:'/home/ubuntu/torrent_bot/downloads/' ~/Downloads/"
        text = (
            f"🖥 *{s['label']}*\n"
            f"IP: `{ip}:{port}`\n"
            f"CF Tunnel: `{tunnel}`\n"
            f"Status: {active}\n"
            f"Catatan: {s.get('notes') or '-'}\n\n"
            f"*SCP Windows:*\n`{scp_win}`\n\n"
            f"*SCP Mac/Linux:*\n`{scp_mac}`"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    "⏸ Disable" if s.get("active", True) else "▶ Enable",
                    callback_data=f"srv:toggle:{idx}",
                ),
                InlineKeyboardButton("🗑 Hapus Server", callback_data=f"srv:confirmdelete:{idx}"),
            ],
            [InlineKeyboardButton("← Server List", callback_data="srv:refresh")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "confirmdelete" and idx is not None:
        s = servers[idx]
        is_self = s.get("ip") == VPS_IP
        warning = (
            "\n\n⚠️ *Ini adalah VPS yang sedang running!*\n"
            "Bot akan langsung STOP setelah dihapus."
            if is_self else ""
        )
        buttons = [
            [
                InlineKeyboardButton("🛑 Ya, hapus & stop", callback_data=f"srv:dodelete:{idx}"),
                InlineKeyboardButton("Batal", callback_data="srv:refresh"),
            ]
        ]
        await query.edit_message_text(
            f"Hapus server *{s['label']}* (`{s.get('ip', '?')}`) dari daftar?{warning}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action == "dodelete" and idx is not None:
        removed = servers.pop(idx)
        is_self = removed.get("ip") == VPS_IP
        srv.save_servers(servers)

        if is_self:
            # Hapus diri sendiri — stop bot setelah kirim konfirmasi
            await query.edit_message_text(
                f"🛑 *{removed['label']}* dihapus dari daftar.\n"
                f"Bot di VPS ini akan berhenti dalam 3 detik...",
                parse_mode="Markdown",
            )
            async def _stop_self():
                await asyncio.sleep(3)
                import signal, os as _os
                _os.kill(_os.getpid(), signal.SIGTERM)
            asyncio.create_task(_stop_self())
        else:
            statuses = await srv.check_all_online(servers) if servers else []
            text, buttons = _server_list_text_buttons(servers, statuses)
            await query.edit_message_text(
                f"✅ Server *{removed['label']}* dihapus.\n\n" + text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    elif action == "add":
        ctx.user_data["waiting_for_server"] = True
        await query.edit_message_text(
            "➕ *Tambah Server Baru*\n\n"
            "Kirim data server dalam format:\n"
            "`LABEL | IP | PORT`\n\n"
            "Contoh:\n`VPS-SG | 1.2.3.4 | 8080`\n\n"
            "_(Port default: 8080)_",
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
    # Start Cloudflare tunnel
    cf_url = await tun.start_tunnel(int(FILE_SERVER_PORT))
    # Auto-register VPS ini ke server list
    import socket
    _hostname = socket.gethostname()
    _label = os.getenv("SERVER_LABEL", _hostname)
    srv.register_self(_label, VPS_IP, FILE_SERVER_PORT, cf_url)
    # Startup notification
    try:
        import socket
        hostname = socket.gethostname()
        try:
            with urllib.request.urlopen("https://ifconfig.me/ip", timeout=5) as r:
                pub_ip = r.read().decode().strip()
        except Exception:
            pub_ip = VPS_IP
        tunnel_line = f"🌐 Download Server: {cf_url}" if cf_url else "⚠️ Tunnel gagal start (cloudflared tidak terinstall?)"
        await app.bot.send_message(
            chat_id=ALLOWED_CHAT_ID,
            text=(
                f"🟢 *Torrent Bot Online!*\n"
                f"🖥 Host: `{hostname}`\n"
                f"📡 IP: `{pub_ip}`\n"
                f"📂 Dir: `{DOWNLOAD_DIR}`\n"
                f"{tunnel_line}\n\n"
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
        handle_text_input,
    ))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(cb_mainmenu, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(cb_dlaction, pattern=r"^dlaction:"))
    app.add_handler(CallbackQueryHandler(cb_fileinfo, pattern=r"^fileinfo:"))
    app.add_handler(CallbackQueryHandler(cb_sendtg, pattern=r"^sendtg:"))
    app.add_handler(CallbackQueryHandler(cb_makezip, pattern=r"^makezip:"))
    app.add_handler(CallbackQueryHandler(cb_zipready, pattern=r"^zipready:"))
    app.add_handler(CallbackQueryHandler(cb_scpcmd, pattern=r"^scpcmd:"))
    app.add_handler(CommandHandler("servers", cmd_servers))
    app.add_handler(CallbackQueryHandler(cb_srv, pattern=r"^srv:"))
    app.add_handler(CallbackQueryHandler(cb_confirmdelete, pattern=r"^confirmdelete:"))
    app.add_handler(CallbackQueryHandler(cb_dodelete, pattern=r"^dodelete:"))
    app.add_handler(CallbackQueryHandler(cb_canceldelete, pattern=r"^canceldelete$"))

    print("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
