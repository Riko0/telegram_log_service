import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart, Command

from config import TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_NAME
from data_manager import (
    whitelisted_users, user_id_to_info, save_whitelist_and_user_info,
    alert_subscribers, load_persistent_data, save_subscribers,
    all_runs_subscribers, register_user, rebuild_username_to_chat_id,
    cleanup_run_subscriptions, save_training_data,
)
from global_state import training_data
from utils import escape_html
import message_builders as mb

logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def whitelisted_only(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if not whitelisted_users:
            logger.warning("Whitelist empty, reloading from files.")
            load_persistent_data()
        username = message.from_user.username
        if username and username in whitelisted_users:
            return await func(message, *args, **kwargs)
        logger.warning(
            f"Unauthorized access by {message.from_user.id} "
            f"(@{username}): {message.text}"
        )
        try:
            await message.reply(
                "\U0001f6ab <b>Access Denied</b>\n"
                "You are not authorized to use this bot. "
                "Please contact an administrator to be added to the whitelist.\n\n"
                "If you do not have a Telegram username, please set one to use this bot.",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError as e:
            logger.error(f"Failed to send access denied: {e}")
    return wrapper


def admin_only(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if not whitelisted_users:
            load_persistent_data()
        if message.from_user.username == ADMIN_TELEGRAM_NAME:
            return await func(message, *args, **kwargs)
        logger.warning(
            f"Admin access denied for @{message.from_user.username}: {message.text}"
        )
        try:
            await message.reply(
                "\U0001f6ab <b>Admin Access Required</b>\n"
                "You do not have administrative privileges.",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError as e:
            logger.error(f"Failed to send admin denied: {e}")
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_run(run_id: str):
    """Search for run_id across all projects. Returns list of (project, run_info)."""
    matches = []
    for project_name, runs in training_data.items():
        if run_id in runs:
            matches.append((project_name, runs[run_id]))
    return matches


HELP_TEXT = (
    "Here are the available commands:\n"
    "/status &lt;project_name&gt; &lt;run_id&gt; - Get status of a specific run\n"
    "/status - List all active runs\n"
    "/full_status &lt;project_name&gt; &lt;run_id&gt; - Get full status of a specific run\n"
    "/full_status - List all active runs (full)\n"
    "/subscribe &lt;project_name&gt; &lt;run_id&gt; - Subscribe to a specific run\n"
    "/subscribe - Subscribe to all current and future runs\n"
    "/unsubscribe &lt;project_name&gt; &lt;run_id&gt; - Unsubscribe from a specific run\n"
    "/unsubscribe - Unsubscribe from all alerts\n"
    "/list_subscriptions - List your subscriptions\n"
    "/help - Show this message"
)

ADMIN_HELP_TEXT = (
    "\n\n<b>Admin Commands:</b>\n"
    "/add_user &lt;username&gt; - Add user to whitelist\n"
    "/remove_user &lt;username&gt; - Remove user from whitelist\n"
    "/list_users - List whitelisted users\n"
    "/remove_run &lt;project_name&gt; &lt;run_id&gt; - Remove a training run"
)


async def _resolve_run(message: types.Message, args: list):
    """Parse args to find a unique (project_name, run_id). Returns tuple or None."""
    if len(args) == 2:
        project_name, run_id = args
        if project_name in training_data and run_id in training_data[project_name]:
            return project_name, run_id
        await message.reply(
            f"Run <code>{escape_html(project_name)}/{escape_html(run_id)}</code> not found.",
            parse_mode=ParseMode.HTML,
        )
        return None

    if len(args) == 1:
        run_id = args[0]
        matches = _find_run(run_id)
        if not matches:
            await message.reply(
                f"Run <code>{escape_html(run_id)}</code> not found in any project.",
                parse_mode=ParseMode.HTML,
            )
            return None
        if len(matches) > 1:
            lines = [
                f"- <code>{escape_html(p)}/{escape_html(run_id)}</code>"
                for p, _ in matches
            ]
            await message.reply(
                f"Multiple runs with ID <code>{escape_html(run_id)}</code> found. "
                f"Please specify the project:\n" + "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )
            return None
        return matches[0][0], run_id

    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username

    logger.info(f"/start from {user_id} ({full_name}, @{username})")

    if not username:
        await message.reply(
            "Welcome! To use this bot, you need to set a public Telegram username.",
            parse_mode=ParseMode.HTML,
        )
        return

    register_user(user_id, username, full_name)
    await save_whitelist_and_user_info()

    if username not in whitelisted_users:
        await message.reply(
            f"Hello, {escape_html(full_name)}! \U0001f44b\n"
            "\U0001f6ab <b>Access Denied</b>\n"
            "You are not authorized. Contact an administrator to be added.",
            parse_mode=ParseMode.HTML,
        )
        return

    auto_msg = ""
    if username not in all_runs_subscribers:
        all_runs_subscribers.add(username)
        for proj, runs in training_data.items():
            for rid in runs:
                alert_subscribers.setdefault(proj, {}).setdefault(rid, set()).add(username)
        await save_subscribers()
        logger.info(f"@{username} auto-subscribed to all runs via /start.")
        auto_msg = "\n\n<i>You have been automatically subscribed to all current and future runs.</i>"
    else:
        auto_msg = "\n\n<i>You are already subscribed to all current and future runs.</i>"

    text = (
        f"Hello, {escape_html(full_name)}! \U0001f44b\n"
        "You are whitelisted and registered to receive alerts.\n\n"
        f"{HELP_TEXT}{auto_msg}"
    )
    if username == ADMIN_TELEGRAM_NAME:
        text += ADMIN_HELP_TEXT

    try:
        await message.reply(text, parse_mode=ParseMode.HTML)
    except TelegramAPIError as e:
        logger.error(f"Failed to send /start reply: {e}")


@dp.message(Command("help"))
@whitelisted_only
async def help_command(message: types.Message, **kwargs):
    text = HELP_TEXT
    if message.from_user.username == ADMIN_TELEGRAM_NAME:
        text += ADMIN_HELP_TEXT
    try:
        await message.reply(text, parse_mode=ParseMode.HTML)
    except TelegramAPIError as e:
        logger.error(f"Failed to send /help: {e}")


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

@dp.message(Command("status"))
@whitelisted_only
async def status_command(message: types.Message, **kwargs):
    args = message.text.split()[1:]

    if args:
        resolved = await _resolve_run(message, args)
        if not resolved:
            return
        project_name, run_id = resolved
        run_info = training_data[project_name][run_id]
        text = mb.format_run_status(project_name, run_id, run_info)
        try:
            await message.reply(text, parse_mode=ParseMode.HTML)
        except TelegramAPIError as e:
            logger.error(f"Failed to send status: {e}")
        return

    # List all runs
    if not training_data:
        await message.reply("There are no active training runs reported yet.", parse_mode=ParseMode.HTML)
        return

    blocks = []
    for proj_name, runs in training_data.items():
        if not runs:
            continue
        lines = [f"\U0001f4e6 <b>Project: {escape_html(proj_name)}</b>"]
        for rid, rinfo in runs.items():
            lines.append(mb.format_run_summary(proj_name, rid, rinfo))
            lines.append("")
        blocks.append("\n".join(lines))

    if not blocks:
        await message.reply("There are no active training runs reported yet.", parse_mode=ParseMode.HTML)
        return

    await mb.send_paginated(message, blocks, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# /full_status
# ---------------------------------------------------------------------------

@dp.message(Command("full_status"))
@whitelisted_only
async def full_status_command(message: types.Message, **kwargs):
    args = [a for a in message.text.split(maxsplit=3)[1:] if a]

    if not training_data:
        await message.reply("<i>No training runs have been reported yet.</i>", parse_mode=ParseMode.HTML)
        return

    if args:
        resolved = await _resolve_run(message, args)
        if not resolved:
            return
        project_name, run_id = resolved
        run_info = training_data[project_name][run_id]
        text = mb.format_run_full_status(project_name, run_id, run_info)
        try:
            await message.reply(text, parse_mode=ParseMode.HTML)
        except TelegramAPIError as e:
            logger.error(f"Failed to send full_status: {e}")
        return

    blocks = []
    for proj_name, runs in training_data.items():
        for rid, rinfo in runs.items():
            blocks.append(mb.format_run_full_status(proj_name, rid, rinfo))

    await mb.send_paginated(message, blocks, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# /subscribe
# ---------------------------------------------------------------------------

@dp.message(Command("subscribe"))
@whitelisted_only
async def subscribe_command(message: types.Message, **kwargs):
    args = message.text.split()[1:]
    username = message.from_user.username
    if not username:
        await message.reply("You must have a Telegram username to subscribe.", parse_mode=ParseMode.HTML)
        return

    if len(args) == 0:
        if username in all_runs_subscribers:
            await message.reply("You are already subscribed to all runs.", parse_mode=ParseMode.HTML)
            return
        all_runs_subscribers.add(username)
        for proj, runs in training_data.items():
            for rid in runs:
                alert_subscribers.setdefault(proj, {}).setdefault(rid, set()).add(username)
        await save_subscribers()
        logger.info(f"@{username} subscribed to all runs.")
        await message.reply("Subscribed to all current and future training runs.", parse_mode=ParseMode.HTML)

    elif len(args) == 2:
        project_name, run_id = args
        if project_name not in training_data or run_id not in training_data[project_name]:
            await message.reply(
                f"Run <code>{escape_html(project_name)}/{escape_html(run_id)}</code> not found.",
                parse_mode=ParseMode.HTML,
            )
            return
        if username in alert_subscribers.get(project_name, {}).get(run_id, set()):
            await message.reply(
                f"Already subscribed to <code>{escape_html(project_name)}/{escape_html(run_id)}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return
        alert_subscribers.setdefault(project_name, {}).setdefault(run_id, set()).add(username)
        await save_subscribers()
        logger.info(f"@{username} subscribed to {project_name}/{run_id}")
        await message.reply(
            f"Subscribed to <code>{escape_html(project_name)}/{escape_html(run_id)}</code>.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply(
            "Usage: <code>/subscribe &lt;project_name&gt; &lt;run_id&gt;</code> "
            "or <code>/subscribe</code> for all runs.",
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# /unsubscribe
# ---------------------------------------------------------------------------

@dp.message(Command("unsubscribe"))
@whitelisted_only
async def unsubscribe_command(message: types.Message, **kwargs):
    args = message.text.split()[1:]
    username = message.from_user.username
    if not username:
        await message.reply("You must have a Telegram username.", parse_mode=ParseMode.HTML)
        return

    if len(args) == 0:
        found = username in all_runs_subscribers or any(
            username in subs
            for proj_runs in alert_subscribers.values()
            for subs in proj_runs.values()
        )
        if not found:
            await message.reply("You are not subscribed to any alerts.", parse_mode=ParseMode.HTML)
            return

        all_runs_subscribers.discard(username)
        for proj in list(alert_subscribers.keys()):
            for rid in list(alert_subscribers[proj].keys()):
                alert_subscribers[proj][rid].discard(username)
                if not alert_subscribers[proj][rid]:
                    del alert_subscribers[proj][rid]
            if not alert_subscribers.get(proj):
                del alert_subscribers[proj]
        await save_subscribers()
        logger.info(f"@{username} unsubscribed from all alerts.")
        await message.reply("Unsubscribed from all alerts.", parse_mode=ParseMode.HTML)

    elif len(args) == 2:
        project_name, run_id = args
        if (
            project_name not in alert_subscribers
            or run_id not in alert_subscribers[project_name]
            or username not in alert_subscribers[project_name][run_id]
        ):
            await message.reply(
                f"You are not subscribed to <code>{escape_html(project_name)}/{escape_html(run_id)}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return
        alert_subscribers[project_name][run_id].discard(username)
        if not alert_subscribers[project_name][run_id]:
            del alert_subscribers[project_name][run_id]
            if not alert_subscribers[project_name]:
                del alert_subscribers[project_name]
        await save_subscribers()
        logger.info(f"@{username} unsubscribed from {project_name}/{run_id}")
        await message.reply(
            f"Unsubscribed from <code>{escape_html(project_name)}/{escape_html(run_id)}</code>.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply(
            "Usage: <code>/unsubscribe &lt;project_name&gt; &lt;run_id&gt;</code> "
            "or <code>/unsubscribe</code> for all.",
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# /list_subscriptions (with stale cleanup)
# ---------------------------------------------------------------------------

@dp.message(Command("list_subscriptions"))
@whitelisted_only
async def list_subscriptions_command(message: types.Message, **kwargs):
    username = message.from_user.username
    if not username:
        await message.reply("You must have a Telegram username.", parse_mode=ParseMode.HTML)
        return

    subs = []
    if username in all_runs_subscribers:
        subs.append("<b>All current and future runs</b>")

    # Filter out stale subscriptions while listing
    stale_entries = []
    for proj, runs in alert_subscribers.items():
        for rid, subscribers in runs.items():
            if username in subscribers:
                if proj in training_data and rid in training_data[proj]:
                    subs.append(f"<code>{escape_html(proj)}/{escape_html(rid)}</code>")
                else:
                    stale_entries.append((proj, rid))

    # Prune stale subscriptions
    for proj, rid in stale_entries:
        alert_subscribers[proj][rid].discard(username)
        if not alert_subscribers[proj][rid]:
            del alert_subscribers[proj][rid]
        if not alert_subscribers.get(proj):
            del alert_subscribers[proj]
    if stale_entries:
        await save_subscribers()

    if subs:
        text = "<b>Your Subscriptions:</b>\n" + "\n".join(subs)
    else:
        text = "You are not subscribed to any training runs."

    try:
        await message.reply(text, parse_mode=ParseMode.HTML)
    except TelegramAPIError as e:
        logger.error(f"Failed to send subscriptions: {e}")


# ---------------------------------------------------------------------------
# Admin: /add_user
# ---------------------------------------------------------------------------

@dp.message(Command("add_user"))
@admin_only
async def add_user_command(message: types.Message, **kwargs):
    args = message.text.split(maxsplit=2)[1:]
    if not args:
        await message.reply(
            "Usage: <code>/add_user &lt;username&gt;</code>\n\n"
            "The user must send <code>/start</code> after being added.",
            parse_mode=ParseMode.HTML,
        )
        return

    uname = args[0].lstrip("@")
    if not uname:
        await message.reply("Invalid username.", parse_mode=ParseMode.HTML)
        return
    if uname in whitelisted_users:
        await message.reply(
            f"User <code>@{escape_html(uname)}</code> is already whitelisted.",
            parse_mode=ParseMode.HTML,
        )
        return

    whitelisted_users.add(uname)
    await save_whitelist_and_user_info()
    logger.info(f"Admin @{message.from_user.username} added @{uname} to whitelist.")
    await message.reply(
        f"\u2705 User <code>@{escape_html(uname)}</code> added to whitelist.\n\n"
        "Tell them to send <code>/start</code> to complete registration.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Admin: /remove_user
# ---------------------------------------------------------------------------

@dp.message(Command("remove_user"))
@admin_only
async def remove_user_command(message: types.Message, **kwargs):
    args = message.text.split()[1:]
    if len(args) != 1:
        await message.reply("Usage: <code>/remove_user &lt;username&gt;</code>", parse_mode=ParseMode.HTML)
        return

    uname = args[0].lstrip("@")
    if not uname:
        await message.reply("Invalid username.", parse_mode=ParseMode.HTML)
        return
    if uname == ADMIN_TELEGRAM_NAME:
        await message.reply("The primary admin cannot be removed.", parse_mode=ParseMode.HTML)
        return
    if uname not in whitelisted_users:
        await message.reply(
            f"User <code>@{escape_html(uname)}</code> is not in the whitelist.",
            parse_mode=ParseMode.HTML,
        )
        return

    whitelisted_users.discard(uname)

    uid_to_remove = None
    for uid, uinfo in list(user_id_to_info.items()):
        if uinfo.get("username") == uname:
            uid_to_remove = uid
            break
    if uid_to_remove:
        user_id_to_info.pop(uid_to_remove, None)
    rebuild_username_to_chat_id()
    await save_whitelist_and_user_info()

    all_runs_subscribers.discard(uname)
    for proj in list(alert_subscribers.keys()):
        for rid in list(alert_subscribers[proj].keys()):
            alert_subscribers[proj][rid].discard(uname)
            if not alert_subscribers[proj][rid]:
                del alert_subscribers[proj][rid]
        if not alert_subscribers.get(proj):
            del alert_subscribers[proj]
    await save_subscribers()

    logger.info(f"Admin removed @{uname} from whitelist.")
    await message.reply(
        f"User <code>@{escape_html(uname)}</code> removed from whitelist.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Admin: /list_users
# ---------------------------------------------------------------------------

@dp.message(Command("list_users"))
@admin_only
async def list_users_command(message: types.Message, **kwargs):
    if not whitelisted_users:
        await message.reply("The whitelist is empty.", parse_mode=ParseMode.HTML)
        return

    lines = ["<b>Whitelisted Users:</b>"]
    for uname in sorted(whitelisted_users):
        registered = False
        is_admin = ""
        for uid, uinfo in user_id_to_info.items():
            if uinfo.get("username") == uname:
                registered = True
                break
        reg_text = "\u2705 Registered" if registered else "\u274c Not Registered"
        if uname == ADMIN_TELEGRAM_NAME:
            is_admin = " (Admin)"
        lines.append(f"- <code>@{escape_html(uname)}</code> ({reg_text}){is_admin}")

    lines.append("\n<i>Users become 'Registered' after they send /start.</i>")

    try:
        await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)
    except TelegramAPIError as e:
        logger.error(f"Failed to send user list: {e}")


# ---------------------------------------------------------------------------
# Admin: /remove_run
# ---------------------------------------------------------------------------

@dp.message(Command("remove_run"))
@admin_only
async def remove_run_command(message: types.Message, **kwargs):
    args = message.text.split()[1:]
    if len(args) != 2:
        await message.reply(
            "Usage: <code>/remove_run &lt;project_name&gt; &lt;run_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    project_name, run_id = args
    if project_name not in training_data or run_id not in training_data[project_name]:
        await message.reply(
            f"Run <code>{escape_html(project_name)}/{escape_html(run_id)}</code> not found.",
            parse_mode=ParseMode.HTML,
        )
        return

    del training_data[project_name][run_id]
    if not training_data[project_name]:
        del training_data[project_name]

    await cleanup_run_subscriptions(project_name, run_id)
    await save_training_data(training_data)

    logger.info(f"Admin removed run {project_name}/{run_id}.")
    await message.reply(
        f"\u2705 Run <code>{escape_html(project_name)}/{escape_html(run_id)}</code> removed.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Catch-all
# ---------------------------------------------------------------------------

@dp.message(F.text)
@whitelisted_only
async def echo_message(message: types.Message):
    await message.reply(
        "I respond to specific commands. "
        "Use /status, /subscribe, /unsubscribe, /list_subscriptions, or /help.",
        parse_mode=ParseMode.HTML,
    )
