import os
import asyncio
import sys
import logging
from logging.handlers import RotatingFileHandler
from aiohttp import web

from telegram_log_service.config import (
    WEB_SERVER_HOST, WEB_SERVER_PORT, STALL_ALERT_THRESHOLD_SECONDS,
    STALL_CHECK_INTERVAL_SECONDS, STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS,
    HEARTBEAT_STALL_THRESHOLD_SECONDS,
)
from telegram_log_service.data_manager import load_persistent_data, load_training_data_sync
from telegram_log_service.global_state import training_data
from telegram_log_service.web_handlers import receive_logs_handler
from telegram_log_service.staleness_checker import check_for_stalled_runs
from telegram_log_service.bot_handlers import dp, bot

LOG_FILE = "bot_events.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
formatter = logging.Formatter(LOG_FORMAT)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def health_handler(request):
    active_runs = sum(len(runs) for runs in training_data.values())
    return web.json_response({"status": "ok", "active_runs": active_runs})


async def main():
    """Start the Telegram bot, web server, and staleness checker."""
    load_persistent_data()

    # Restore training data from disk
    saved = load_training_data_sync()
    for project, runs in saved.items():
        training_data[project] = {}
        for run_id, run_info in runs.items():
            if "alerts_sent" in run_info and isinstance(run_info["alerts_sent"], dict):
                pass  # already correct
            training_data[project][run_id] = run_info

    web_app = web.Application(client_max_size=1024 * 1024 * 50)
    web_app.router.add_post("/api/logs", receive_logs_handler)
    web_app.router.add_get("/health", health_handler)
    runner = web.AppRunner(web_app)

    try:
        await runner.setup()
        site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
        aiohttp_task = asyncio.create_task(site.start())
        logger.info(
            f"Web server started on http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}"
        )

        logger.info("Starting Telegram bot polling...")
        polling_task = asyncio.create_task(dp.start_polling(bot))

        stalled_task = asyncio.create_task(check_for_stalled_runs())
        logger.info(
            f"Staleness checker started (log threshold={STALL_ALERT_THRESHOLD_SECONDS}s, "
            f"heartbeat threshold={HEARTBEAT_STALL_THRESHOLD_SECONDS}s, "
            f"interval={STALL_CHECK_INTERVAL_SECONDS}s)."
        )
        if STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS is not None:
            logger.info(
                f"Auto-remove enabled after {STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS}s."
            )

        await asyncio.gather(aiohttp_task, polling_task, stalled_task)

    except asyncio.CancelledError:
        logger.info("Main tasks cancelled. Shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Cleaning up...")
        if runner:
            await runner.cleanup()
        await bot.session.close()
        logger.info("Shutdown complete.")
        sys.stdout.flush()
        sys.stderr.flush()


if __name__ == "__main__":
    from telegram_log_service.__main__ import cli
    cli()
