import datetime
import logging
from typing import Optional

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from bot_handlers import bot
from global_state import training_data
from data_manager import (
    alert_subscribers, whitelisted_users, all_runs_subscribers, username_to_chat_id,
)
from config import STALL_ALERT_THRESHOLD_SECONDS, HEARTBEAT_STALL_THRESHOLD_SECONDS
import message_builders as mb

logger = logging.getLogger(__name__)


async def _send_alert_to_subscribers(
    project_name: str, run_id: str, message: str, alert_type: str,
):
    """Send an alert to all subscribers of a run (specific + global)."""
    run_info = training_data[project_name][run_id]

    recipients: set = set()
    if project_name in alert_subscribers and run_id in alert_subscribers[project_name]:
        recipients.update(alert_subscribers[project_name][run_id])
    recipients.update(all_runs_subscribers)
    final_recipients = recipients.intersection(whitelisted_users)

    for username in final_recipients:
        chat_id = username_to_chat_id.get(username)
        if chat_id:
            try:
                await bot.send_message(
                    chat_id=chat_id, text=message, parse_mode=ParseMode.HTML,
                )
                logger.info(
                    f"Sent '{alert_type}' alert for {project_name}/{run_id} "
                    f"to @{username} (chat {chat_id})"
                )
            except TelegramAPIError as e:
                logger.error(
                    f"Failed to send '{alert_type}' alert to @{username} "
                    f"(chat {chat_id}): {e}"
                )
        else:
            logger.warning(
                f"No chat ID for @{username} to send '{alert_type}' alert "
                f"for {project_name}/{run_id}."
            )

    # Update alert flags
    if alert_type == "started":
        run_info["alerts_sent"]["started"] = True
    elif alert_type == "finished":
        run_info["alerts_sent"]["finished"] = True
    elif alert_type == "stalled":
        run_info["alerts_sent"]["stalled"] = True
        run_info["stalled_since"] = datetime.datetime.now().isoformat()


async def send_training_started_alert(project_name: str, run_id: str):
    run_info = training_data[project_name][run_id]
    if run_info["alerts_sent"]["started"]:
        return
    msg = mb.alert_training_started(project_name, run_id, run_info)
    await _send_alert_to_subscribers(project_name, run_id, msg, "started")


async def send_training_finished_alert(project_name: str, run_id: str):
    run_info = training_data[project_name][run_id]
    if run_info["alerts_sent"]["finished"]:
        return
    msg = mb.alert_training_finished(project_name, run_id, run_info)
    await _send_alert_to_subscribers(project_name, run_id, msg, "finished")


async def send_stalled_alert(project_name: str, run_id: str):
    run_info = training_data[project_name][run_id]
    if run_info["alerts_sent"]["stalled"]:
        return
    heartbeat = run_info.get("heartbeat_enabled", False)
    threshold = HEARTBEAT_STALL_THRESHOLD_SECONDS if heartbeat else STALL_ALERT_THRESHOLD_SECONDS
    msg = mb.alert_stalled(project_name, run_id, run_info, threshold)
    await _send_alert_to_subscribers(project_name, run_id, msg, "stalled")


async def send_training_resumed_alert(project_name: str, run_id: str):
    run_info = training_data[project_name][run_id]
    msg = mb.alert_resumed(project_name, run_id, run_info)
    await _send_alert_to_subscribers(project_name, run_id, msg, "resumed")


async def send_best_metric_changed_alert(
    project_name: str,
    run_id: str,
    new_best_value: float,
    new_best_step: int,
    old_best_value: Optional[float] = None,
    best_metric_checkpoint: Optional[str] = None,
):
    run_info = training_data[project_name][run_id]
    msg = mb.alert_best_metric_changed(
        project_name, run_id, run_info,
        new_best_value, new_best_step, old_best_value, best_metric_checkpoint,
    )
    await _send_alert_to_subscribers(project_name, run_id, msg, "best_metric_changed")


async def send_stalled_run_removed_alert(project_name: str, run_id: str):
    run_info = training_data[project_name][run_id]
    msg = mb.alert_stalled_run_removed(project_name, run_id, run_info)
    await _send_alert_to_subscribers(project_name, run_id, msg, "stalled_removed")
