import asyncio
import os
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
FILE_SERVER_PORT = int(os.getenv("FILE_SERVER_PORT") or 8080)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


async def start_file_server():
    app = web.Application()
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
