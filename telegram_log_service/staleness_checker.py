import asyncio
import datetime
import logging

from global_state import training_data
from alerting import send_stalled_alert, send_stalled_run_removed_alert
from data_manager import cleanup_run_subscriptions, save_training_data
from config import (
    STALL_ALERT_THRESHOLD_SECONDS,
    STALL_CHECK_INTERVAL_SECONDS,
    STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS,
    HEARTBEAT_STALL_THRESHOLD_SECONDS,
)

logger = logging.getLogger(__name__)


def _seconds_since(iso_timestamp: str) -> float:
    return (datetime.datetime.now() - datetime.datetime.fromisoformat(iso_timestamp)).total_seconds()


async def check_for_stalled_runs():
    """Periodically check active training runs for staleness and send alerts."""
    while True:
        try:
            await asyncio.sleep(STALL_CHECK_INTERVAL_SECONDS)
            now = datetime.datetime.now()
            logger.info("Running stalled run check...")

            projects_to_check = list(training_data.keys())
            for project_name in projects_to_check:
                runs_to_check = list(training_data.get(project_name, {}).keys())
                for run_id in runs_to_check:
                    if project_name not in training_data:
                        break
                    if run_id not in training_data.get(project_name, {}):
                        continue

                    run_info = training_data[project_name][run_id]
                    is_training = run_info.get("latest_state", {}).get("is_training", False)
                    has_finished = run_info.get("end_time") is not None

                    if not is_training or has_finished:
                        continue

                    # Pick the best timestamp and threshold for staleness
                    heartbeat_enabled = run_info.get("heartbeat_enabled", False)
                    if heartbeat_enabled and run_info.get("last_heartbeat_timestamp"):
                        check_ts = run_info["last_heartbeat_timestamp"]
                        threshold = HEARTBEAT_STALL_THRESHOLD_SECONDS
                    elif run_info.get("last_log_timestamp"):
                        check_ts = run_info["last_log_timestamp"]
                        threshold = STALL_ALERT_THRESHOLD_SECONDS
                    else:
                        logger.warning(
                            f"Run {project_name}/{run_id} is training "
                            "but has no timestamp to check."
                        )
                        continue

                    try:
                        time_since = _seconds_since(check_ts)
                    except ValueError:
                        logger.error(
                            f"Invalid timestamp for {project_name}/{run_id}: {check_ts}"
                        )
                        continue

                    if time_since > threshold:
                        if not run_info["alerts_sent"]["stalled"]:
                            logger.info(
                                f"Detected stalled run: {project_name}/{run_id}. "
                                f"Last activity {time_since:.0f}s ago "
                                f"(threshold: {threshold}s)."
                            )
                            await send_stalled_alert(project_name, run_id)

                        # Auto-remove if stalled too long
                        if (
                            STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS is not None
                            and run_info.get("stalled_since")
                        ):
                            try:
                                time_stalled = _seconds_since(run_info["stalled_since"])
                            except ValueError:
                                continue

                            if time_stalled > STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS:
                                logger.info(
                                    f"Auto-removing stalled run: "
                                    f"{project_name}/{run_id} "
                                    f"(stalled for {time_stalled:.0f}s)."
                                )
                                await send_stalled_run_removed_alert(project_name, run_id)
                                await cleanup_run_subscriptions(project_name, run_id)

                                del training_data[project_name][run_id]
                                if not training_data[project_name]:
                                    del training_data[project_name]

                                await save_training_data(training_data)
                    else:
                        if run_info["alerts_sent"]["stalled"]:
                            run_info["alerts_sent"]["stalled"] = False
                            run_info["stalled_since"] = None
                            logger.info(
                                f"Run {project_name}/{run_id} is no longer stalled."
                            )

        except asyncio.CancelledError:
            logger.info("Stalled run check task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in stalled run check task: {e}", exc_info=True)
