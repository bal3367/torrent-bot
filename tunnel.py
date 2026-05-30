"""Cloudflare tunnel URL reader — URL ditulis oleh start_tunnel.sh ke tunnel_url.txt."""
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

tunnel_url: str | None = None
_URL_FILE = Path(__file__).parent / "tunnel_url.txt"


async def start_tunnel(port: int) -> str | None:
    """Tunggu sampai start_tunnel.sh menulis URL ke tunnel_url.txt (max 40 detik)."""
    global tunnel_url
    _URL_FILE.unlink(missing_ok=True)
    logger.info(f"[tunnel] Waiting for cloudflared URL from {_URL_FILE} (port={port})")
    for _ in range(40):
        await asyncio.sleep(1)
        if _URL_FILE.exists():
            url = _URL_FILE.read_text().strip()
            if url.startswith("https://"):
                tunnel_url = url
                logger.info(f"[tunnel] ✅ Tunnel aktif: {tunnel_url}")
                return tunnel_url
    logger.error("[tunnel] ❌ Timeout — cloudflared URL tidak muncul dalam 40 detik")
    return None
