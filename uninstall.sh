#!/bin/bash
# Torrent Bot — Uninstaller
set -e

# Ketika dijalankan via "curl | bash", $0 adalah bash/stdin bukan path file.
# Selalu hardcode ke lokasi instalasi standar.
INSTALL_DIR="/home/ubuntu/torrent_bot"
# Fallback: kalau dijalankan langsung dari dalam folder bot
if [ -f "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/main.py" ]; then
    INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Safety check — jangan hapus root/home directory
if [ "$INSTALL_DIR" = "/" ] || [ "$INSTALL_DIR" = "$HOME" ] || [ "$INSTALL_DIR" = "/root" ] || [ "$INSTALL_DIR" = "/home" ]; then
    echo "❌ ERROR: INSTALL_DIR tidak aman: $INSTALL_DIR — batalkan uninstall."
    exit 1
fi

if [ ! -f "$INSTALL_DIR/main.py" ]; then
    echo "❌ ERROR: main.py tidak ditemukan di $INSTALL_DIR — bukan folder torrent bot."
    exit 1
fi
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
info() { echo -e "${BLUE}  ▶ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }

echo ""
echo -e "${RED}========================================"
echo "   Torrent Bot — Uninstaller"
echo -e "========================================${NC}"
echo ""

# ── Konfirmasi ────────────────────────────
read -r -p "  Yakin mau uninstall Torrent Bot? [y/N] " CONFIRM
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "  Dibatalkan."; exit 0; }
echo ""

# ── Tanya hapus downloads? ───────────────
REMOVE_DOWNLOADS=false
DOWNLOAD_DIR=""
if [ -f "$INSTALL_DIR/.env" ]; then
    DOWNLOAD_DIR=$(grep '^DOWNLOAD_DIR=' "$INSTALL_DIR/.env" | cut -d= -f2-)
fi
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$INSTALL_DIR/downloads}"

if [ -d "$DOWNLOAD_DIR" ]; then
    DL_SIZE=$(du -sh "$DOWNLOAD_DIR" 2>/dev/null | cut -f1)
    read -r -p "  Hapus folder downloads ($DOWNLOAD_DIR, $DL_SIZE)? [y/N] " DEL_DL
    [[ "$DEL_DL" =~ ^[Yy]$ ]] && REMOVE_DOWNLOADS=true
fi
echo ""

# ── 1. Stop bot ───────────────────────────
info "Stopping bot..."
if screen -list 2>/dev/null | grep -q "torrent_bot"; then
    screen -S torrent_bot -X quit 2>/dev/null || true
    ok "Screen session stopped"
else
    echo "  Bot tidak sedang running."
fi
pkill -f "python3 main.py" 2>/dev/null || true
pkill -f "python3 -m torrent_bot" 2>/dev/null || true

# ── 2. Stop aria2c ────────────────────────
info "Stopping aria2c..."
if pgrep -x aria2c > /dev/null 2>&1; then
    pkill -x aria2c 2>/dev/null || true
    ok "aria2c stopped"
else
    echo "  aria2c tidak running."
fi

# ── 3. Stop cloudflared ───────────────────
info "Stopping cloudflared..."
if pgrep -x cloudflared > /dev/null 2>&1; then
    pkill -x cloudflared 2>/dev/null || true
    ok "cloudflared stopped"
else
    echo "  cloudflared tidak running."
fi

# ── 4. Hapus downloads (opsional) ─────────
if [ "$REMOVE_DOWNLOADS" = true ] && [ -d "$DOWNLOAD_DIR" ]; then
    info "Menghapus folder downloads..."
    rm -rf "$DOWNLOAD_DIR"
    ok "Downloads dihapus"
else
    [ -d "$DOWNLOAD_DIR" ] && warn "Downloads dipertahankan di: $DOWNLOAD_DIR"
fi

# ── 5. Hapus folder bot ───────────────────
info "Menghapus folder bot: $INSTALL_DIR"
cd "$HOME" 2>/dev/null || cd /tmp
rm -rf "$INSTALL_DIR"
ok "Folder bot dihapus"

echo ""
echo -e "${GREEN}========================================"
echo "  ✅ Torrent Bot berhasil diuninstall."
echo -e "========================================${NC}"
echo ""
