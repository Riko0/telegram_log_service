# telegram-log-service

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**telegram-log-service** — a server that receives ML training logs via HTTP and sends real-time alerts through a Telegram bot. Designed to work with [messenger-logger-callback](https://github.com/Riko0/messenger_logger_callback).

## Architecture

```
Training Script                      Telegram Log Service                 Telegram
┌──────────────────┐   HTTP POST    ┌─────────────────────┐             ┌──────────┐
│ MessengerLogger  │ ─────────────> │ /api/logs handler   │             │          │
│ or Callback      │   /api/logs    │   ↓                 │   Bot API   │ Telegram │
│ + heartbeat      │                │ global_state        │ ──────────> │ Users    │
└──────────────────┘                │   ↓                 │             │          │
                                    │ alerting → bot      │             └──────────┘
                                    │ staleness_checker   │
                                    └─────────────────────┘
```

**Flow:**
1. Training scripts send JSON events (logs, status updates, heartbeats) to `POST /api/logs`.
2. The web handler updates in-memory run state and triggers alerts when appropriate.
3. The Telegram bot sends alerts to subscribed users and responds to commands.
4. A background staleness checker detects crashed/stalled runs.

## Prerequisites

- Python 3.8+
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))

## Installation

### From source (pip)

```bash
git clone https://github.com/Riko0/telegram_log_service.git
cd telegram_log_service
pip install .
```

### Configure

```bash
cp .env.example .env
# Edit .env and fill in your TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_NAME
```

### Run

After installing, the `telegram-log-service` command is available system-wide:

```bash
telegram-log-service
```

Or using the Python module:

```bash
python -m telegram_log_service
```

## Docker

```bash
# From the telegram_log_service directory:
chmod +x deploy/docker/build_docker.sh deploy/scripts/startup.sh
./deploy/docker/build_docker.sh
```

The Docker image installs the package via `pip install .` and runs `telegram-log-service` as the entry point. Pass your `.env` file via `--env-file`.

## Configuration

All settings are via environment variables (or `.env` file). See `.env.example` for a complete template.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram bot token from BotFather |
| `WEB_SERVER_HOST` | No | `0.0.0.0` | Bind address for the HTTP server |
| `WEB_SERVER_PORT` | No | `5000` | Port for the HTTP server |
| `WEB_AUTH_TOKEN` | No | — | If set, `/api/logs` requires `Authorization: Bearer <token>` |
| `STALL_ALERT_THRESHOLD_SECONDS` | No | `1800` | Seconds without logs before a run is considered stalled |
| `STALLED_RUN_AUTO_REMOVE_THRESHOLD_SECONDS` | No | `3600` | Seconds before a stalled run is auto-removed |
| `HEARTBEAT_STALL_THRESHOLD_SECONDS` | No | `300` | Stall threshold for runs sending heartbeats (shorter) |
| `BEST_METRIC_ALERT_COOLDOWN_SECONDS` | No | `300` | Minimum seconds between best-metric alerts per run |
| `ADMIN_TELEGRAM_NAME` | No | — | Telegram username (without @) for admin commands |

## API

### `POST /api/logs`

Receives training events. Requires `Authorization: Bearer <token>` header if `WEB_AUTH_TOKEN` is set.

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `project_name` | string | Project identifier |
| `run_id` | string | Unique run identifier |
| `event_type` | string | One of: `training_started`, `trainer_log`, `epoch_ended`, `training_finished`, `custom_log`, `heartbeat` |
| `timestamp` | string | ISO 8601 timestamp |

**Optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `author_username` | string | Who started the run |
| `trainer_state` | object | Training state (`global_step`, `epoch`, `is_training`, `best_metric`, etc.) |
| `logs` | object | Metric key-value pairs (for `trainer_log`) |
| `custom_data` | object | Arbitrary data (for `custom_log`) |
| `clearml_link` | string | URL to ClearML dashboard for this run |

Any other top-level keys are stored as run metadata.

### `GET /health`

Returns server status:

```json
{"status": "ok", "active_runs": 3}
```

## Bot Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Register with the bot, auto-subscribe to all runs |
| `/help` | Show available commands |
| `/status` | List all active training runs |
| `/status <project> <run_id>` | Get status of a specific run |
| `/full_status` | Detailed status for all runs |
| `/full_status <project> <run_id>` | Detailed status for a specific run |
| `/subscribe` | Subscribe to all current and future runs |
| `/subscribe <project> <run_id>` | Subscribe to a specific run |
| `/unsubscribe` | Unsubscribe from all alerts |
| `/unsubscribe <project> <run_id>` | Unsubscribe from a specific run |
| `/list_subscriptions` | List your current subscriptions |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/add_user <username>` | Add a user to the whitelist |
| `/remove_user <username>` | Remove a user from the whitelist |
| `/list_users` | List all whitelisted users |
| `/remove_run <project> <run_id>` | Manually remove a training run |

## Alerts

The bot sends alerts to subscribed users when:

| Alert | When |
|-------|------|
| Training Started | A new run sends its first `training_started` event |
| Training Finished | A run sends `training_finished` |
| Training Stalled | No logs/heartbeats received beyond the threshold |
| Training Resumed | A stalled run starts sending logs again |
| Best Metric Changed | `best_metric` improves (with cooldown to avoid spam) |
| Run Removed | A stalled run is auto-removed after prolonged inactivity |

If ClearML is detected, alerts include a direct link to the ClearML dashboard.

## Heartbeat

When the client library sends heartbeat events (every ~60 seconds by default), the server uses a shorter stall threshold (`HEARTBEAT_STALL_THRESHOLD_SECONDS`, default 300s) for faster crash detection. Runs without heartbeats use the standard `STALL_ALERT_THRESHOLD_SECONDS` (default 1800s). This is fully backwards-compatible -- old clients work the same as before.

## Data Persistence

- **Whitelist, subscribers, user info** are saved to JSON files and survive restarts.
- **Training run data** is saved to `training_data.json` on every meaningful event (not heartbeats) and restored on startup.

## Related Projects

- **[messenger-logger-callback](https://github.com/Riko0/messenger_logger_callback)** — the client library that sends training logs to this service. `pip install messenger-logger-callback`

## License

MIT
