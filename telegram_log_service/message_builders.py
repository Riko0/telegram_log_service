"""
Shared message formatting helpers for Telegram (HTML parse mode).

All functions return strings ready for bot.send_message(parse_mode=ParseMode.HTML).
"""

import json
from typing import Any, Dict, Optional

from telegram_log_service.utils import escape_html


# ---------------------------------------------------------------------------
# Status views
# ---------------------------------------------------------------------------

def _status_line(run_info: dict) -> tuple:
    """Return (emoji, text) describing a run's status."""
    end_time = run_info.get("end_time")
    stalled_since = run_info.get("stalled_since")
    is_training = run_info.get("latest_state", {}).get("is_training", False)

    if end_time:
        return "\u2705", "Finished"
    if stalled_since:
        return "\U0001f534", "Stalled"
    if is_training:
        return "\u25b6\ufe0f", "Training"
    return "\U0001f7e2", "Idle"


def format_run_summary(project_name: str, run_id: str, run_info: dict) -> str:
    """Compact one-run summary for the /status list view."""
    emoji, status_text = _status_line(run_info)
    latest_step = run_info.get("latest_state", {}).get("global_step", "N/A")
    best = run_info.get("best_metric_value")
    author = run_info.get("author_username")

    lines = [
        f"    Run ID: <code>{escape_html(run_id)}</code>",
        f"    Status: {emoji} {escape_html(status_text)}",
    ]
    if author:
        lines.append(f"    Author: @{escape_html(author)}")
    if latest_step != "N/A":
        lines.append(f"    Last Step: <code>{escape_html(str(latest_step))}</code>")
    if best is not None:
        lines.append(f"    Best Metric: <code>{best:.4f}</code>")
    return "\n".join(lines)


def format_run_status(project_name: str, run_id: str, run_info: dict) -> str:
    """Single-run detailed status for /status <project> <run>."""
    emoji, status_text = _status_line(run_info)
    state = run_info.get("latest_state", {})
    author = run_info.get("author_username")

    stalled_since = run_info.get("stalled_since")
    if stalled_since:
        status_text = f"Stalled since <code>{escape_html(stalled_since)}</code>"

    lines = [f"\U0001f4ca <b>Status for {escape_html(project_name)}/{escape_html(run_id)}</b>"]
    if author:
        lines.append(f"Author: @{escape_html(author)}")
    lines.append(f"Status: {emoji} {status_text}")
    lines.append(f"Activity: <code>{escape_html(run_info.get('current_activity', 'Idle'))}</code>")
    lines.append(f"Started: <code>{escape_html(run_info.get('start_time', 'N/A'))}</code>")

    end_time = run_info.get("end_time")
    if end_time:
        lines.append(f"Finished: <code>{escape_html(end_time)}</code>")

    epoch = state.get("epoch", "N/A")
    if epoch != "N/A":
        lines.append(f"Latest Epoch: <code>{escape_html(str(epoch))}</code>")
    step = state.get("global_step", "N/A")
    if step != "N/A":
        lines.append(f"Latest Step: <code>{escape_html(str(step))}</code>")

    last_log = run_info.get("last_log_timestamp", "N/A")
    if last_log != "N/A":
        lines.append(f"Last Log: <code>{escape_html(last_log)}</code>")

    clearml = run_info.get("clearml_link")
    if clearml:
        lines.append(f'ClearML: <a href="{escape_html(clearml)}">View in ClearML</a>')

    best = run_info.get("best_metric_value")
    if best is not None:
        lines.append("")
        lines.append("<b>Best Metric:</b>")
        lines.append(f"Value: <code>{best:.4f}</code>")
        lines.append(f"Step: <code>{escape_html(str(run_info.get('best_metric_step', 'N/A')))}</code>")
        lines.append(f"Checkpoint: <code>{escape_html(str(run_info.get('best_model_checkpoint', 'N/A')))}</code>")
    else:
        lines.append("")
        lines.append("<i>No best metric reported yet.</i>")

    return "\n".join(lines)


def format_run_full_status(project_name: str, run_id: str, run_info: dict) -> str:
    """Detailed status with metadata, logs, event history for /full_status."""
    state = run_info.get("latest_state", {})
    author = run_info.get("author_username")
    metadata = run_info.get("metadata", {})
    latest_logs = run_info.get("latest_logs", {})

    lines = [f"\U0001f4c8 <b>Full Status for {escape_html(project_name)}/{escape_html(run_id)}</b>", ""]
    if author:
        lines.append(f"Author: @{escape_html(author)}")

    event_history = run_info.get("event_history", [])
    last_update = event_history[-1]["timestamp"] if event_history else "N/A"
    lines.append(f"  <b>Last Update:</b> <code>{escape_html(last_update)}</code>")
    lines.append(f"  <b>Global Step:</b> <code>{escape_html(str(state.get('global_step', 'N/A')))}</code>")

    epoch_val = state.get("epoch", "N/A")
    epoch_str = f"{epoch_val:.2f}" if isinstance(epoch_val, (int, float)) else str(epoch_val)
    lines.append(f"  <b>Epoch:</b> <code>{escape_html(epoch_str)}</code>")

    is_training = state.get("is_training", False)
    if is_training:
        lines.append("  <b>Current Activity:</b> <code>Training</code> \U0001f680")
    elif run_info.get("end_time"):
        lines.append("  <b>Current Activity:</b> <code>Finished</code> \u2705")
    else:
        lines.append("  <b>Current Activity:</b> <code>Not Training (Potentially Evaluating/Paused)</code> \U0001f504")

    stalled = run_info.get("alerts_sent", {}).get("stalled", False)
    lines.append(f"  <b>Stalled:</b> <code>{escape_html(str(stalled))}</code>")
    if stalled and run_info.get("stalled_since"):
        lines.append(f"  <b>Stalled Since:</b> <code>{escape_html(run_info['stalled_since'])}</code>")

    best = run_info.get("best_metric_value")
    best_step = run_info.get("best_metric_step", "N/A")
    best_ckpt = run_info.get("best_model_checkpoint", "N/A")
    if best is not None:
        lines.append(f"  <b>Best Metric:</b> <code>{best:.4f}</code>")
    else:
        lines.append(f"  <b>Best Metric:</b> <code>N/A</code>")
    lines.append(f"  <b>Best Metric Checkpoint:</b> <code>{escape_html(str(best_ckpt or 'N/A'))}</code>")
    lines.append(f"  <b>Best Metric Step:</b> <code>{escape_html(str(best_step or 'N/A'))}</code>")

    clearml = run_info.get("clearml_link")
    if clearml:
        lines.append(f'  <b>ClearML:</b> <a href="{escape_html(clearml)}">View in ClearML</a>')
    lines.append("")

    if metadata:
        lines.append("<b>Metadata:</b>")
        for key, value in metadata.items():
            lines.append(f"  - <code>{escape_html(key)}</code>: <code>{escape_html(str(value))}</code>")
        lines.append("")

    lines.append("<b>Latest Logs:</b>")
    if latest_logs:
        for key, value in latest_logs.items():
            if isinstance(value, float):
                lines.append(f"  - <code>{escape_html(key)}</code>: <code>{value:.4f}</code>")
            else:
                lines.append(f"  - <code>{escape_html(key)}</code>: <code>{escape_html(str(value))}</code>")
    else:
        lines.append("  <i>No specific logs for this step.</i>")

    lines.append("")
    lines.append("<b>Event History (last 5):</b>")
    if event_history:
        for event in event_history[-5:]:
            etype = event.get("type", "N/A")
            ets = escape_html(event.get("timestamp", "N/A"))
            if etype == "trainer_log":
                step = escape_html(str(event.get("global_step", "N/A")))
                lines.append(f"  - <code>{ets}</code>: <code>Trainer Log</code> at step <code>{step}</code>")
            elif etype == "custom_log":
                raw = json.dumps(event.get("custom_data", {}))
                summary = escape_html(raw[:50] + "..." if len(raw) > 50 else raw)
                lines.append(f"  - <code>{ets}</code>: <code>Custom Log</code>: <code>{summary}</code>")
            else:
                nice = escape_html(etype.replace("_", " ").title())
                lines.append(f"  - <code>{ets}</code>: <b>{nice}</b>")
    else:
        lines.append("  <i>No events recorded.</i>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Alert messages
# ---------------------------------------------------------------------------

def _clearml_line(run_info: dict) -> str:
    link = run_info.get("clearml_link")
    if link:
        return f'\n<a href="{escape_html(link)}">View in ClearML</a>'
    return ""


def _author_line(run_info: dict) -> str:
    author = run_info.get("author_username")
    if author:
        return f"\nAuthor: @{escape_html(author)}"
    return ""


def _status_command(project_name: str, run_id: str) -> str:
    return f"\nUse <code>/status {escape_html(project_name)} {escape_html(run_id)}</code> for live updates."


def alert_training_started(project_name: str, run_id: str, run_info: dict) -> str:
    start_time = escape_html(run_info.get("start_time", "N/A"))
    msg = (
        f"\U0001f680 <b>New Training Started!</b> \U0001f680\n"
        f"Project: <code>{escape_html(project_name)}</code>\n"
        f"Run ID: <code>{escape_html(run_id)}</code>"
        f"{_author_line(run_info)}\n"
        f"Started at: <code>{start_time}</code>"
        f"{_clearml_line(run_info)}"
        f"{_status_command(project_name, run_id)}"
    )
    return msg


def alert_training_finished(project_name: str, run_id: str, run_info: dict) -> str:
    start_time = escape_html(run_info.get("start_time", "N/A"))
    end_time = escape_html(run_info.get("end_time", "N/A"))
    msg = (
        f"\U0001f389 <b>Training Finished!</b> \U0001f389\n"
        f"Project: <code>{escape_html(project_name)}</code>\n"
        f"Run ID: <code>{escape_html(run_id)}</code>"
        f"{_author_line(run_info)}\n"
        f"Started: <code>{start_time}</code>\n"
        f"Finished: <code>{end_time}</code>"
        f"{_clearml_line(run_info)}"
        f"{_status_command(project_name, run_id)}"
    )
    return msg


def alert_stalled(project_name: str, run_id: str, run_info: dict, threshold: int) -> str:
    last_log = escape_html(run_info.get("last_log_timestamp", "N/A"))
    msg = (
        f"\u26a0\ufe0f <b>Training Stalled!</b> \u26a0\ufe0f\n"
        f"Project: <code>{escape_html(project_name)}</code>\n"
        f"Run ID: <code>{escape_html(run_id)}</code>"
        f"{_author_line(run_info)}\n"
        f"No updates received for over <code>{threshold}</code> seconds.\n"
        f"Last log at: <code>{last_log}</code>\n\n"
        f"Check your training script for issues or an unexpected exit."
    )
    return msg


def alert_resumed(project_name: str, run_id: str, run_info: dict) -> str:
    last_log = escape_html(run_info.get("last_log_timestamp", "N/A"))
    msg = (
        f"\u2705 <b>Training Resumed!</b> \u2705\n"
        f"Project: <code>{escape_html(project_name)}</code>\n"
        f"Run ID: <code>{escape_html(run_id)}</code>"
        f"{_author_line(run_info)}\n"
        f"This run was previously detected as stalled and is now receiving logs again.\n"
        f"Latest log received at: <code>{last_log}</code>"
        f"{_status_command(project_name, run_id)}"
    )
    return msg


def alert_best_metric_changed(
    project_name: str,
    run_id: str,
    run_info: dict,
    new_value: float,
    new_step: int,
    old_value: Optional[float],
    checkpoint: Optional[str],
) -> str:
    old_str = f"{old_value:.4f}" if isinstance(old_value, (int, float)) else str(old_value)
    msg = (
        f"\U0001f3c6 <b>New Best Metric!</b> \U0001f3c6\n"
        f"Project: <code>{escape_html(project_name)}</code>\n"
        f"Run ID: <code>{escape_html(run_id)}</code>"
        f"{_author_line(run_info)}\n"
        f"Best model checkpoint: <code>{escape_html(str(checkpoint))}</code>\n"
        f"Best Metric has improved to <code>{new_value:.4f}</code> "
        f"at step <code>{new_step}</code> from <code>{old_str}</code>."
        f"{_clearml_line(run_info)}"
        f"{_status_command(project_name, run_id)}"
    )
    return msg


# ---------------------------------------------------------------------------
# Paginated sending helper
# ---------------------------------------------------------------------------

async def send_paginated(message, text_blocks: list, parse_mode=None, max_length: int = 4096):
    """Send multiple text blocks, splitting into messages to stay under Telegram's limit."""
    from aiogram.exceptions import TelegramAPIError
    import logging

    _logger = logging.getLogger(__name__)
    current_parts = []
    current_len = 0

    for block in text_blocks:
        if current_len + len(block) + 1 > max_length and current_parts:
            try:
                await message.reply("\n".join(current_parts), parse_mode=parse_mode)
            except TelegramAPIError as e:
                _logger.error(f"Failed to send paginated message: {e}")
            current_parts = []
            current_len = 0
        current_parts.append(block)
        current_len += len(block) + 1

    if current_parts:
        try:
            await message.reply("\n".join(current_parts), parse_mode=parse_mode)
        except TelegramAPIError as e:
            _logger.error(f"Failed to send paginated message: {e}")
