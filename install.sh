#!/bin/bash
# ============================================
# Torrent Bot — Universal One-liner Installer
# Supports: Ubuntu, Debian, CentOS, AlmaLinux,
#           Rocky Linux, Fedora
#
# Usage (fresh VPS, 1 command):
#   curl -sL https://raw.githubusercontent.com/bal3367/torrent-bot/main/install.sh | bash
# ============================================
set -e

# ── Warna output ──────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
info() { echo -e "${BLUE}  ▶ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
err()  { echo -e "${RED}  ❌ $1${NC}"; exit 1; }

echo ""
echo -e "${BLUE}========================================"
echo "   Torrent Bot — Universal Installer"
echo -e "========================================${NC}"
echo ""

# ── Deteksi OS & package manager ──────────
detect_os() {
    if command -v apt-get &>/dev/null; then
        PKG_MANAGER="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MANAGER="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MANAGER="yum"
    else
        err "Package manager tidak dikenali (bukan apt/dnf/yum)"
    fi
    info "OS terdeteksi: $PKG_MANAGER"
}

# ── Install packages sesuai OS ────────────
install_pkg() {
    local pkgs="$@"
    case "$PKG_MANAGER" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y $pkgs
            ;;
        dnf)
            sudo dnf install -y $pkgs
            ;;
        yum)
            sudo yum install -y $pkgs
            ;;
    esac
}

# ── Sudo / root check ─────────────────────
if [ "$EUID" -ne 0 ] && ! command -v sudo &>/dev/null; then
    err "Butuh sudo atau root. Jalankan sebagai root atau install sudo."
fi
[ "$EUID" -eq 0 ] && SUDO="" || SUDO="sudo"

# ── Deteksi OS ────────────────────────────
detect_os

# ── 1. System packages ───────────────────
info "Installing system packages..."
if [ "$PKG_MANAGER" = "apt" ]; then
    $SUDO apt-get update -qq
    $SUDO apt-get install -y \
        git curl wget screen aria2 \
        python3 python3-pip python3-venv \
        jq unzip 2>/dev/null
else
    $SUDO $PKG_MANAGER install -y \
        git curl wget screen aria2 \
        python3 python3-pip \
        jq unzip 2>/dev/null || true
    # python3-venv untuk dnf/yum
    $SUDO $PKG_MANAGER install -y python3-virtualenv 2>/dev/null || \
    pip3 install virtualenv 2>/dev/null || true
fi
ok "System packages installed"

# ── 2. Cek Python version (minimal 3.10) ─
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo $PY_VER | cut -d. -f1)
PY_MINOR=$(echo $PY_VER | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    warn "Python $PY_VER terdeteksi (butuh 3.10+). Installing Python 3.11..."
    if [ "$PKG_MANAGER" = "apt" ]; then
        $SUDO apt-get install -y software-properties-common 2>/dev/null || true
        $SUDO add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
        $SUDO apt-get update -qq && $SUDO apt-get install -y python3.11 python3.11-venv python3.11-pip
        PYTHON_BIN="python3.11"
    else
        warn "Install Python 3.10+ secara manual untuk OS ini."
        PYTHON_BIN="python3"
    fi
else
    ok "Python $PY_VER ✅"
    PYTHON_BIN="python3"
fi

# ── 3. Install cloudflared ────────────────
if ! command -v cloudflared &>/dev/null; then
    info "Installing cloudflared..."
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  CF_ARCH="amd64" ;;
        aarch64) CF_ARCH="arm64" ;;
        armv7*)  CF_ARCH="arm" ;;
        *)       CF_ARCH="amd64" ;;
    esac
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}"
    curl -sL "$CF_URL" -o /tmp/cloudflared
    $SUDO mv /tmp/cloudflared /usr/local/bin/cloudflared
    $SUDO chmod +x /usr/local/bin/cloudflared
    ok "cloudflared installed ($(cloudflared --version 2>&1 | head -1))"
else
    ok "cloudflared sudah ada ($(cloudflared --version 2>&1 | head -1))"
fi

# ── 4. Clone / update repo ────────────────
INSTALL_DIR="$HOME/torrent_bot"
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repo sudah ada, update ke versi terbaru..."
    cd "$INSTALL_DIR"
    git pull origin main
    ok "Repo updated"
else
    info "Cloning torrent-bot repo..."
    git clone https://github.com/bal3367/torrent-bot.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "Repo cloned"
fi

# ── 5. Python venv + dependencies ─────────
info "Setting up Python environment..."
$PYTHON_BIN -m venv venv 2>/dev/null || $PYTHON_BIN -m virtualenv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -q -r requirements.txt
ok "Python dependencies installed"

# ── 6. Setup .env ─────────────────────────
mkdir -p downloads
if [ ! -f .env ]; then
    cp .env.example .env
    # Auto-detect public IP
    PUBLIC_IP=$(curl -s --max-time 5 https://ifconfig.me/ip 2>/dev/null \
             || curl -s --max-time 5 https://api.ipify.org 2>/dev/null \
             || curl -s --max-time 5 https://icanhazip.com 2>/dev/null \
             || echo "")
    [ -n "$PUBLIC_IP" ] && sed -i "s/VPS_IP=your_vps_public_ip/VPS_IP=$PUBLIC_IP/" .env \
                        && ok "VPS IP: $PUBLIC_IP"
    # Auto-set SERVER_LABEL dari hostname
    HOSTNAME_VAL=$(hostname 2>/dev/null || echo "VPS")
    sed -i "s/SERVER_LABEL=VPS-Main/SERVER_LABEL=$HOSTNAME_VAL/" .env
    ok "SERVER_LABEL: $HOSTNAME_VAL"
else
    ok ".env sudah ada, skip"
fi

# ── 7. Start bot ──────────────────────────
info "Starting bot..."
bash start.sh

echo ""
echo -e "${GREEN}========================================"
echo "  ✅ Torrent Bot berhasil diinstall!"
echo ""
echo "  Cek Telegram — notifikasi startup"
echo "  akan datang dalam ~20 detik."
echo ""
echo "  Perintah berguna:"
echo "    screen -r torrent_bot     # lihat log"
echo "    bash ~/torrent_bot/start.sh  # restart"
echo "    bash ~/torrent_bot/stop.sh   # stop"
echo -e "========================================${NC}"
echo ""
