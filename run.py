"""Process entrypoint: Flask + APScheduler + Discord bot in one process.

Flask runs inside a daemon thread so the Discord bot can own the main
thread's asyncio event loop (discord.py expects that).
"""
from __future__ import annotations

import logging
import os
import threading

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app import scheduler as sched_mod
from app import bot as bot_mod

log = logging.getLogger("run")


def _run_flask() -> None:
    app = create_app()
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    log.info("flask listening on http://%s:%d", host, port)
    app.run(host=host, port=port, use_reloader=False, threaded=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    )

    # 1) Flask in a background thread.
    flask_thread = threading.Thread(target=_run_flask, name="flask", daemon=True)
    flask_thread.start()

    # 2) Scheduler in its own background thread.
    sched_mod.start()

    # 3) Discord bot on the main thread (owns the event loop).
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        log.warning("DISCORD_BOT_TOKEN not set — running without the bot")
        flask_thread.join()
        return
    bot_mod.run_bot_blocking(token)


if __name__ == "__main__":
    main()
