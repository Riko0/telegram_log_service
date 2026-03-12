import os
import json
import logging

import aiofiles

from config import (
    WHITELIST_FILE, USER_INFO_FILE, ADMIN_TELEGRAM_NAME,
    SUBSCRIBERS_FILE, ALL_SUBSCRIBERS_FILE, TRAINING_DATA_FILE,
)

logger = logging.getLogger(__name__)

whitelisted_users: set = set()
user_id_to_info: dict = {}
alert_subscribers: dict = {}
all_runs_subscribers: set = set()
username_to_chat_id: dict = {}


# ---------------------------------------------------------------------------
# Synchronous load (used at startup before the event loop is running)
# ---------------------------------------------------------------------------

def _load_json_sync(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                data = json.load(f)
                logger.info(f"Loaded data from {filename}")
                return data
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {filename}. Returning empty data.")
        except Exception as e:
            logger.error(f"Unexpected error loading {filename}: {e}")
    else:
        logger.info(f"File {filename} not found. Returning empty data.")
    return {}


def load_persistent_data():
    """Load whitelist, user info, and subscribers from JSON files at startup."""
    global whitelisted_users, user_id_to_info, alert_subscribers, all_runs_subscribers

    loaded = _load_json_sync(WHITELIST_FILE)
    whitelisted_users.clear()
    if isinstance(loaded, (list, set)):
        whitelisted_users.update(set(loaded))
    else:
        logger.warning(f"Whitelist data from {WHITELIST_FILE} is not a list. Initializing empty.")

    loaded = _load_json_sync(USER_INFO_FILE)
    user_id_to_info.clear()
    if isinstance(loaded, dict):
        user_id_to_info.update({int(k): v for k, v in loaded.items()})
    else:
        logger.warning(f"User info from {USER_INFO_FILE} is not a dict. Initializing empty.")

    loaded = _load_json_sync(SUBSCRIBERS_FILE)
    alert_subscribers.clear()
    if isinstance(loaded, dict):
        for project, runs in loaded.items():
            if isinstance(runs, dict):
                alert_subscribers[project] = {}
                for run, subs_list in runs.items():
                    if isinstance(subs_list, (list, set)):
                        alert_subscribers[project][run] = set(subs_list)
    else:
        logger.warning(f"Subscribers from {SUBSCRIBERS_FILE} is not a dict. Initializing empty.")

    loaded = _load_json_sync(ALL_SUBSCRIBERS_FILE)
    all_runs_subscribers.clear()
    if isinstance(loaded, (list, set)):
        all_runs_subscribers.update(set(loaded))

    if ADMIN_TELEGRAM_NAME and ADMIN_TELEGRAM_NAME not in whitelisted_users:
        whitelisted_users.add(ADMIN_TELEGRAM_NAME)

    rebuild_username_to_chat_id()

    logger.info(f"Whitelist reloaded: {whitelisted_users}")
    logger.info(f"User info reloaded: {user_id_to_info}")
    subscriber_summary = {
        proj: {run: list(subs) for run, subs in runs.items()}
        for proj, runs in alert_subscribers.items()
    }
    logger.info(f"Subscribers reloaded: {subscriber_summary}")
    logger.info(f"All runs subscribers reloaded: {all_runs_subscribers}")


def load_training_data_sync():
    """Load training_data from disk at startup. Returns a dict."""
    loaded = _load_json_sync(TRAINING_DATA_FILE)
    if isinstance(loaded, dict):
        return loaded
    return {}


# ---------------------------------------------------------------------------
# Async save helpers
# ---------------------------------------------------------------------------

async def _save_json_async(data, filename):
    try:
        async with aiofiles.open(filename, "w") as f:
            await f.write(json.dumps(data, indent=2, default=str))
        logger.debug(f"Data saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving data to {filename}: {e}")


async def save_whitelist_and_user_info():
    await _save_json_async(list(whitelisted_users), WHITELIST_FILE)
    await _save_json_async(
        {str(k): v for k, v in user_id_to_info.items()}, USER_INFO_FILE
    )


async def save_subscribers():
    subscribers_to_save = {}
    for project, runs in alert_subscribers.items():
        subscribers_to_save[project] = {
            run: list(subs) for run, subs in runs.items()
        }
    await _save_json_async(subscribers_to_save, SUBSCRIBERS_FILE)
    await _save_json_async(list(all_runs_subscribers), ALL_SUBSCRIBERS_FILE)


async def save_training_data(training_data):
    """Persist training_data to disk."""
    serializable = {}
    for project, runs in training_data.items():
        serializable[project] = {}
        for run_id, run_info in runs.items():
            info_copy = dict(run_info)
            if "alerts_sent" in info_copy:
                info_copy["alerts_sent"] = dict(info_copy["alerts_sent"])
            serializable[project][run_id] = info_copy
    await _save_json_async(serializable, TRAINING_DATA_FILE)


# ---------------------------------------------------------------------------
# Reverse lookup
# ---------------------------------------------------------------------------

def rebuild_username_to_chat_id():
    """Rebuild the username -> chat_id mapping from user_id_to_info."""
    username_to_chat_id.clear()
    for uid, uinfo in user_id_to_info.items():
        uname = uinfo.get("username")
        if uname:
            username_to_chat_id[uname] = uid


def register_user(user_id: int, username: str, full_name: str):
    """Register or update a user's info and rebuild the reverse lookup."""
    user_id_to_info[user_id] = {"username": username, "full_name": full_name}
    rebuild_username_to_chat_id()


# ---------------------------------------------------------------------------
# Subscription cleanup
# ---------------------------------------------------------------------------

async def cleanup_run_subscriptions(project_name: str, run_id: str):
    """Remove subscription entries for a run that no longer exists."""
    if project_name in alert_subscribers:
        alert_subscribers[project_name].pop(run_id, None)
        if not alert_subscribers[project_name]:
            del alert_subscribers[project_name]
    await save_subscribers()
