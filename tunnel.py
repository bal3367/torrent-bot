"""Cloudflare tunnel URL reader — URL ditulis oleh start_tunnel.sh ke tunnel_url.txt."""
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

tunnel_url: str | None = None
_URL_FILE = Path(__file__).parent / "tunnel_url.txt"


def current_url() -> str | None:
    """URL tunnel terbaru dari tunnel_url.txt (dibaca ulang tiap dipanggil).

    File ini ditulis start_tunnel.sh yang jalan di screen sendiri, jadi URL bisa
    muncul setelah bot start, dan bot yang restart sendirian tetap dapat URL-nya.
    """
    global tunnel_url
    try:
        url = _URL_FILE.read_text().strip()
        if url.startswith("https://"):
            tunnel_url = url
    except FileNotFoundError:
        pass
    return tunnel_url


async def start_tunnel(port: int) -> str | None:
    """Tunggu sampai start_tunnel.sh menulis URL ke tunnel_url.txt (max 40 detik).

    File TIDAK dihapus di sini: start.sh / start_tunnel.sh sudah menghapus URL lama
    sebelum cloudflared start. Menghapusnya di sini bikin URL yang sudah ditulis
    cloudflared (kalau cloudflared lebih cepat dari bot) hilang selamanya.
    """
    logger.info(f"[tunnel] Waiting for cloudflared URL from {_URL_FILE} (port={port})")
    for _ in range(40):
        if current_url():
            logger.info(f"[tunnel] ✅ Tunnel aktif: {tunnel_url}")
            return tunnel_url
        await asyncio.sleep(1)
    logger.error("[tunnel] ❌ Timeout — cloudflared URL belum muncul dalam 40 detik (link akan dicek ulang saat diklik)")
    return None
