"""Cloudflare quick tunnel — expose local file server ke public HTTPS URL."""
import asyncio
import re

tunnel_url: str | None = None
_proc = None


async def start_tunnel(port: int) -> str | None:
    """
    Jalankan cloudflared quick tunnel ke localhost:port.
    Return public URL (https://xxxx.trycloudflare.com) atau None jika gagal.
    """
    global tunnel_url, _proc
    try:
        _proc = await asyncio.create_subprocess_exec(
            "cloudflared", "tunnel", "--url", f"http://localhost:{port}",
            "--no-autoupdate",
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        # Baca output sampai URL muncul (timeout 30 detik)
        while True:
            try:
                line = await asyncio.wait_for(_proc.stderr.readline(), timeout=30)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            decoded = line.decode(errors="ignore")
            match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', decoded)
            if match:
                tunnel_url = match.group()
                return tunnel_url
    except FileNotFoundError:
        # cloudflared tidak terinstall
        return None
    except Exception:
        return None
    return None
