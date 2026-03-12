import logging
import datetime
from aiohttp import web

from telegram_log_service.config import WEB_AUTH_TOKEN, BEST_METRIC_ALERT_COOLDOWN_SECONDS
from telegram_log_service.global_state import training_data
from telegram_log_service.data_manager import (
    save_training_data, cleanup_run_subscriptions, save_subscribers,
    alert_subscribers, all_runs_subscribers,
)
from telegram_log_service.alerting import (
    send_training_started_alert, send_training_finished_alert,
    send_training_resumed_alert, send_best_metric_changed_alert,
)

logger = logging.getLogger(__name__)

MAX_EVENT_HISTORY_SIZE = 10


def _new_run_info() -> dict:
    return {
        "latest_state": {"is_training": True},
        "latest_logs": {},
        "event_history": [],
        "start_time": None,
        "end_time": None,
        "last_log_timestamp": None,
        "last_heartbeat_timestamp": None,
        "heartbeat_enabled": False,
        "best_metric_name": "",
        "best_metric_value": None,
        "best_metric_step": None,
        "best_model_checkpoint": None,
        "current_activity": "Unknown",
        "alerts_sent": {
            "finished": False, "stalled": False,
            "started": False, "best_metric_changed": False,
        },
        "author_username": None,
        "metadata": {},
        "clearml_link": None,
        "last_best_metric_alert_time": None,
    }


def _add_event(history: list, event: dict):
    if len(history) >= MAX_EVENT_HISTORY_SIZE:
        history.pop(0)
    history.append(event)


async def receive_logs_handler(request):
    """aiohttp handler for POST /api/logs."""
    # --- Auth ---
    if WEB_AUTH_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {WEB_AUTH_TOKEN}":
            return web.json_response(
                {"status": "error", "message": "Unauthorized"}, status=401
            )

    try:
        data = await request.json()
        if not data:
            return web.json_response(
                {"status": "error", "message": "No JSON data received"}, status=400
            )

        project_name = data.get("project_name")
        run_id = data.get("run_id")
        event_type = data.get("event_type")
        timestamp = data.get("timestamp")
        author_username = data.get("author_username")

        if not all([project_name, run_id, event_type, timestamp]):
            return web.json_response(
                {"status": "error", "message": "Missing required fields"},
                status=400,
            )

        logger.debug(
            f"Received log: Project={project_name}, Run={run_id}, "
            f"Event={event_type}, Author={author_username}"
        )

        # --- Extract metadata (unknown top-level keys) ---
        known_keys = {
            "project_name", "run_id", "event_type", "timestamp",
            "author_username", "trainer_state", "logs", "custom_data",
            "clearml_link",
        }
        metadata = {k: v for k, v in data.items() if k not in known_keys}

        # --- Ensure run exists ---
        is_new_run = False
        if project_name not in training_data:
            training_data[project_name] = {}
        if run_id not in training_data[project_name]:
            is_new_run = True
            training_data[project_name][run_id] = _new_run_info()

        run_info = training_data[project_name][run_id]

        if author_username:
            run_info["author_username"] = author_username
        if metadata:
            run_info["metadata"].update(metadata)

        clearml_link = data.get("clearml_link")
        if clearml_link:
            run_info["clearml_link"] = clearml_link

        # --- Stall resume detection ---
        was_stalled_and_resumed = False
        if (
            run_info["alerts_sent"]["stalled"]
            and run_info["latest_state"].get("is_training", False)
            and run_info.get("stalled_since") is not None
        ):
            was_stalled_and_resumed = True

        run_info["last_log_timestamp"] = datetime.datetime.now().isoformat()

        if was_stalled_and_resumed:
            run_info["alerts_sent"]["stalled"] = False
            run_info["stalled_since"] = None
            logger.info(
                f"Run {project_name}/{run_id} resumed logging. "
                "Resetting stalled alert flag."
            )
            await send_training_resumed_alert(project_name, run_id)

        # --- Handle event types ---
        if event_type == "heartbeat":
            run_info["last_heartbeat_timestamp"] = datetime.datetime.now().isoformat()
            run_info["heartbeat_enabled"] = True

        elif event_type == "trainer_log":
            run_info["latest_state"].update(data.get("trainer_state", {}))
            current_logs = data.get("logs", {})
            run_info["latest_logs"] = current_logs
            _add_event(run_info["event_history"], {
                "type": event_type,
                "timestamp": timestamp,
                "global_step": run_info["latest_state"].get("global_step"),
                "logs": current_logs,
            })

            run_info["current_activity"] = "Unknown"
            for key in current_logs:
                if "train" in key:
                    run_info["current_activity"] = "Training"
                if "eval" in key:
                    run_info["current_activity"] = "Evaluating"

            # --- Best metric tracking with cooldown ---
            cur_best = run_info["latest_state"].get("best_metric")
            cur_ckpt = run_info["latest_state"].get("best_model_checkpoint")
            best_ckpt_short = None
            if cur_ckpt:
                best_ckpt_short = cur_ckpt.rsplit("/", 1)[-1]
            old_best = run_info["best_metric_value"]

            if cur_best != old_best:
                global_step = run_info["latest_state"].get("global_step")
                run_info["best_metric_value"] = cur_best
                run_info["best_metric_step"] = global_step
                run_info["best_model_checkpoint"] = best_ckpt_short

                should_alert = True
                last_alert_time = run_info.get("last_best_metric_alert_time")
                if last_alert_time and BEST_METRIC_ALERT_COOLDOWN_SECONDS:
                    try:
                        elapsed = (
                            datetime.datetime.now()
                            - datetime.datetime.fromisoformat(last_alert_time)
                        ).total_seconds()
                        if elapsed < BEST_METRIC_ALERT_COOLDOWN_SECONDS:
                            should_alert = False
                    except ValueError:
                        pass

                if should_alert:
                    run_info["last_best_metric_alert_time"] = (
                        datetime.datetime.now().isoformat()
                    )
                    logger.info(
                        f"New best metric for {project_name}/{run_id}: "
                        f"{cur_best} at step {global_step}"
                    )
                    await send_best_metric_changed_alert(
                        project_name, run_id, cur_best, global_step,
                        old_best, best_ckpt_short,
                    )

        elif event_type == "custom_log":
            _add_event(run_info["event_history"], {
                "type": event_type,
                "timestamp": timestamp,
                "custom_data": data.get("custom_data", {}),
            })

        elif event_type == "training_started":
            _add_event(run_info["event_history"], {
                "type": event_type, "timestamp": timestamp,
                "trainer_state": data.get("trainer_state", {}),
            })
            run_info["start_time"] = timestamp
            run_info["latest_state"]["is_training"] = True
            run_info["current_activity"] = "Training"
            if is_new_run or not run_info["alerts_sent"]["started"]:
                # Auto-subscribe global subscribers to this new run
                for username in all_runs_subscribers:
                    if project_name not in alert_subscribers:
                        alert_subscribers[project_name] = {}
                    if run_id not in alert_subscribers[project_name]:
                        alert_subscribers[project_name][run_id] = set()
                    alert_subscribers[project_name][run_id].add(username)
                await save_subscribers()
                await send_training_started_alert(project_name, run_id)

        elif event_type == "training_finished":
            _add_event(run_info["event_history"], {
                "type": event_type, "timestamp": timestamp,
                "trainer_state": data.get("trainer_state", {}),
            })
            run_info["end_time"] = timestamp
            run_info["latest_state"]["is_training"] = False
            run_info["current_activity"] = "Finished"
            await send_training_finished_alert(project_name, run_id)
            await cleanup_run_subscriptions(project_name, run_id)

        else:
            _add_event(run_info["event_history"], {
                "type": event_type, "timestamp": timestamp,
                "trainer_state": data.get("trainer_state", {}),
            })

        # Persist after every meaningful event (not heartbeats)
        if event_type != "heartbeat":
            await save_training_data(training_data)

        return web.json_response({"status": "success", "message": "Log received"})

    except Exception as e:
        logger.exception("Error processing incoming log:")
        return web.json_response(
            {"status": "error", "message": str(e)}, status=500
        )
