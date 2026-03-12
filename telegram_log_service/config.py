import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set. Please set the environment variable or add it to your .env file.")
    sys.exit(1)

WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", 5000))
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_AUTH_TOKEN = os.getenv("WEB_AUTH_TOKEN")

STALL_ALERT_THRESHOLD_SECONDS = int(os.getenv("STALL_ALERT_THRESHOLD_SECONDS", 1800))
STALL_CHECK_INTERVAL_SECONDS = 180
STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS = int(os.getenv("STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS", 3600))

HEARTBEAT_STALL_THRESHOLD_SECONDS = int(os.getenv("HEARTBEAT_STALL_THRESHOLD_SECONDS", 300))
BEST_METRIC_ALERT_COOLDOWN_SECONDS = int(os.getenv("BEST_METRIC_ALERT_COOLDOWN_SECONDS", 300))

ADMIN_TELEGRAM_NAME = os.getenv("ADMIN_TELEGRAM_NAME")
if ADMIN_TELEGRAM_NAME:
    ADMIN_TELEGRAM_NAME = str(ADMIN_TELEGRAM_NAME)
else:
    logger.warning("ADMIN_TELEGRAM_NAME is not set in .env. No initial admin will be set.")

WHITELIST_FILE = "whitelist.json"
USER_INFO_FILE = "user_info.json"
SUBSCRIBERS_FILE = "subscribers.json"
ALL_SUBSCRIBERS_FILE = "all_subscribers.json"
TRAINING_DATA_FILE = "training_data.json"
