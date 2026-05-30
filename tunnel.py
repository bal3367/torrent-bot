"""Cloudflare quick tunnel — expose local file server ke public HTTPS URL."""
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

tunnel_url: str | None = None
_proc = None


async def _drain(stream):
    """Terus baca stream agar pipe tidak penuh dan cloudflared tidak mati."""
    try:
        while True:
            line = await stream.readline()
            if not line:
                break
    except Exception:
        pass


async def start_tunnel(port: int) -> str | None:
    """
    Jalankan cloudflared quick tunnel ke localhost:port.
    Return public URL (https://xxxx.trycloudflare.com) atau None jika gagal.
    """
    global tunnel_url, _proc
    try:
        logger.info(f"[tunnel] Starting cloudflared tunnel → localhost:{port}")
        _proc = await asyncio.create_subprocess_exec(
            "cloudflared", "tunnel", "--url", f"http://localhost:{port}",
            "--no-autoupdate",
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
        )
        found_url = None
        while True:
            try:
                line = await asyncio.wait_for(_proc.stderr.readline(), timeout=30)
            except asyncio.TimeoutError:
                logger.error("[tunnel] Timeout 30s — cloudflared tidak mengeluarkan URL")
                break
            if not line:
                logger.warning("[tunnel] cloudflared stderr closed tanpa URL")
                break
            decoded = line.decode(errors="ignore").strip()
            if decoded:
                logger.info(f"[tunnel] cloudflared: {decoded}")
            match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', decoded)
            if match:
                found_url = match.group()
                break

        if found_url:
            tunnel_url = found_url
            logger.info(f"[tunnel] ✅ Tunnel aktif: {tunnel_url}")
            asyncio.create_task(_drain(_proc.stderr))
            return tunnel_url

        logger.error("[tunnel] ❌ Gagal dapat URL dari cloudflared")

    except FileNotFoundError:
        logger.error("[tunnel] cloudflared tidak terinstall (FileNotFoundError)")
        return None
    except Exception as e:
        logger.error(f"[tunnel] Exception: {e}")
        return None
    return None
