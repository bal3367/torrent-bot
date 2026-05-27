import aria2p
import os
from dotenv import load_dotenv

load_dotenv()

_client: aria2p.API | None = None


def get_client() -> aria2p.API:
    global _client
    if _client is None:
        _client = aria2p.API(
            aria2p.Client(
                host=os.getenv("ARIA2_HOST", "http://localhost"),
                port=int(os.getenv("ARIA2_PORT", 6800)),
                secret=os.getenv("ARIA2_SECRET", ""),
            )
        )
    return _client


def add_magnet(uri: str) -> str:
    dl = get_client().add_magnet(uri)
    return dl.gid


def add_uri(uri: str) -> str:
    """Tambah magnet link ATAU direct URL (.torrent HTTP/HTTPS)."""
    if uri.strip().startswith("magnet:"):
        dl = get_client().add_magnet(uri)
    else:
        dl = get_client().add_uris([uri])
    return dl.gid


def add_torrent_file(path: str) -> str:
    dl = get_client().add_torrent(path)
    return dl.gid


def list_downloads() -> list[aria2p.Download]:
    return get_client().get_downloads()


def get_download(gid: str) -> aria2p.Download | None:
    try:
        return get_client().get_download(gid)
    except Exception:
        return None


def pause_download(gid: str) -> bool:
    dl = get_download(gid)
    if dl:
        dl.pause()
        return True
    return False


def resume_download(gid: str) -> bool:
    dl = get_download(gid)
    if dl:
        dl.resume()
        return True
    return False


def cancel_download(gid: str) -> bool:
    dl = get_download(gid)
    if dl:
        get_client().remove([dl], force=True)
        get_client().remove_files([dl])
        return True
    return False


def set_download_dir(new_dir: str) -> bool:
    """Ubah folder download aria2c via RPC tanpa restart."""
    try:
        get_client().client.call("aria2.changeGlobalOption", {"dir": new_dir})
        return True
    except Exception:
        return False


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_speed(bps: float) -> str:
    return format_size(int(bps)) + "/s"
