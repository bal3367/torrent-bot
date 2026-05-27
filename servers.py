"""Server registry — manage multiple VPS instances."""
import json
import asyncio
import os
from pathlib import Path

SERVERS_FILE = Path(__file__).parent / "servers.json"


def _load() -> list[dict]:
    if SERVERS_FILE.exists():
        try:
            return json.loads(SERVERS_FILE.read_text())
        except Exception:
            pass
    return []


def _save(servers: list[dict]):
    SERVERS_FILE.write_text(json.dumps(servers, indent=2))


def get_servers() -> list[dict]:
    return _load()


def save_servers(servers: list[dict]):
    _save(servers)


def register_self(label: str, ip: str, file_server_port: str, tunnel_url: str | None = None):
    """Register atau update entry VPS ini di servers.json."""
    servers = _load()
    # Cari berdasarkan IP
    for s in servers:
        if s.get("ip") == ip:
            s["tunnel_url"] = tunnel_url
            s["label"] = label or s.get("label", ip)
            _save(servers)
            return
    # Belum ada, tambah baru
    servers.append({
        "label": label or ip,
        "ip": ip,
        "file_server_port": file_server_port,
        "tunnel_url": tunnel_url,
        "active": True,
        "notes": "",
    })
    _save(servers)


async def check_online(server: dict, timeout: float = 4.0) -> bool:
    """Cek apakah server bisa dijangkau via HTTP (file server)."""
    import urllib.request
    import urllib.error

    urls_to_try = []
    if server.get("tunnel_url"):
        urls_to_try.append(server["tunnel_url"])
    ip = server.get("ip")
    port = server.get("file_server_port", "8080")
    if ip:
        urls_to_try.append(f"http://{ip}:{port}/")

    loop = asyncio.get_event_loop()

    def _try_url(url):
        try:
            req = urllib.request.urlopen(url, timeout=timeout)
            req.close()
            return True
        except Exception:
            return False

    for url in urls_to_try:
        ok = await loop.run_in_executor(None, _try_url, url)
        if ok:
            return True
    return False


async def check_all_online(servers: list[dict]) -> list[bool]:
    """Check semua server secara paralel."""
    results = await asyncio.gather(*[check_online(s) for s in servers])
    return list(results)
