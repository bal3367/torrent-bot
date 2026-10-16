import asyncio
import os
import re
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
FILE_SERVER_PORT = int(os.getenv("FILE_SERVER_PORT") or 8080)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# Skrip download PowerShell yang dibuat bot (main.py _ps_download), dilayani di /_dl/<id>.txt sebagai
# text/plain supaya `irm <link> | iex` di Windows PowerShell 5.1 menerimanya sebagai teks.
DL_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dlscripts")


async def _dl_script(request):
    name = request.match_info["name"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.txt", name):
        raise web.HTTPNotFound()
    path = os.path.join(DL_SCRIPT_DIR, name)
    if not os.path.isfile(path):
        raise web.HTTPNotFound()
    with open(path, encoding="ascii") as f:
        return web.Response(text=f.read(), content_type="text/plain", charset="utf-8")


async def start_file_server():
    app = web.Application()
    app.router.add_get("/_dl/{name}", _dl_script)  # sebelum add_static("/"), yang menangkap semua path
    app.router.add_static("/", path=DOWNLOAD_DIR, show_index=True, follow_symlinks=True)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", FILE_SERVER_PORT)
    await site.start()
    print(f"File server running on port {FILE_SERVER_PORT}")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(start_file_server())
