import os
import json
import math
import asyncio
import threading
from datetime import datetime, timezone, timedelta

import aiohttp
import urllib.request
from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = "8975538590:AAHDzhIrqOQsUS_zJk5HX8tjCgCP_uT27lQ"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")

ADMIN_ID = 8979291976
ADMIN_USERNAME = "@AK4SX"
DEVELOPER = "ᴀᴋᴀꜱʜ ᴏꜱɪɴᴛ"

FREE_CREDITS = 5
REFERRAL_BONUS = 1
CREDIT_PER_LOOKUP = 1

# ---------- Channels ----------
CHANNELS = [
    {"name": "Channel 1", "username": "@AK4SHOSINT", "link": "https://t.me/AK4SHOSINT"},
    {"name": "Channel 2", "username": "@Ak4sHoSiNtt", "link": "https://t.me/Ak4sHoSiNtt"},
    {"name": "Channel 3", "username": "@AK45HOSiNT", "link": "https://t.me/AK45HOSiNT"},
]

# ---------- API URLs ----------
API_NUMBER = "https://akash-number-lookup.vercel.app/api/search"
API_TG_TO_NUM = "https://akash-telegram-to-number.vercel.app/resolve"
API_AADHAR = ""
API_PAN = ""
API_EMAIL = ""
API_IFSC = ""
API_PINCODE = ""
API_IP = ""
API_WEATHER = ""

API_KEY = "DEMO"

RECORDS_PER_PAGE = 3
STATS_PER_PAGE = 15

USERS_FILE = "users.json"
QUERIES_FILE = "queries.json"
SUBS_FILE = "subscriptions.json"
APPROVED_GROUPS_FILE = "approved_groups.json"


# ============================================================
# FLASK HEALTH SERVER
# ============================================================

health_app = Flask(__name__)


@health_app.route("/")
def home():
    return "AKASH OSINT BOT ONLINE", 200


@health_app.route("/health")
def health():
    return "OK", 200


def run_health_server():
    port = int(os.getenv("PORT", "10000"))
    health_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ============================================================
# GIST PERSISTENCE
# ============================================================

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GIST_ID = os.getenv("GIST_ID", "")

GIST_FILENAME_MAP = {
    "users.json": "users",
    "queries.json": "queries",
    "subscriptions.json": "subscriptions",
    "approved_groups.json": "approved_groups",
}


def _gist_api_url():
    return f"https://api.github.com/gists/{GIST_ID}"


def _gist_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AkashOsintBot",
    }


def load_json(filename, default):
    key = GIST_FILENAME_MAP.get(filename)

    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                data = json.load(file)
                if data:
                    return data
    except Exception as error:
        print(f"LOCAL LOAD ERROR [{filename}]:", repr(error))

    if GITHUB_TOKEN and GIST_ID and key:
        try:
            req = urllib.request.Request(_gist_api_url(), headers=_gist_headers())
            with urllib.request.urlopen(req, timeout=10) as response:
                gist_data = json.loads(response.read().decode("utf-8"))
                files = gist_data.get("files", {})
                bot_file = files.get("bot_data.json")
                if bot_file:
                    content = bot_file.get("content", "{}")
                    all_data = json.loads(content)
                    return all_data.get(key, default)
        except Exception as error:
            print(f"GIST LOAD ERROR [{filename}]:", repr(error))

    return default


def save_json(filename, data):
    key = GIST_FILENAME_MAP.get(filename)

    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as error:
        print(f"LOCAL SAVE ERROR [{filename}]:", repr(error))

    if GITHUB_TOKEN and GIST_ID and key:
        try:
            req = urllib.request.Request(_gist_api_url(), headers=_gist_headers())
            with urllib.request.urlopen(req, timeout=10) as response:
                gist_data = json.loads(response.read().decode("utf-8"))

            files = gist_data.get("files", {})
            bot_file = files.get("bot_data.json")
            current_content = bot_file.get("content", "{}") if bot_file else "{}"

            try:
                all_data = json.loads(current_content)
            except json.JSONDecodeError:
                all_data = {}

            all_data[key] = data

            payload = json.dumps({
                "files": {
                    "bot_data.json": {
                        "content": json.dumps(all_data, ensure_ascii=False, indent=2)
                    }
                }
            }).encode("utf-8")

            req2 = urllib.request.Request(
                _gist_api_url(),
                data=payload,
                headers={**_gist_headers(), "Content-Type": "application/json"},
                method="PATCH",
            )
            with urllib.request.urlopen(req2, timeout=10) as response:
                print(f"GIST SAVE OK [{filename}]")
        except Exception as error:
            print(f"GIST SAVE ERROR [{filename}]:", repr(error))

    return True


# ============================================================
# DATA GETTERS
# ============================================================

def get_users():
    return load_json(USERS_FILE, {})


def save_users(data):
    save_json(USERS_FILE, data)


def get_queries():
    return load_json(QUERIES_FILE, [])


def save_queries(data):
    save_json(QUERIES_FILE, data)


def get_subscriptions():
    return load_json(SUBS_FILE, {})


def save_subscriptions(data):
    save_json(SUBS_FILE, data)


def get_approved_groups():
    return load_json(APPROVED_GROUPS_FILE, [])


def save_approved_groups(data):
    save_json(APPROVED_GROUPS_FILE, data)


# ============================================================
# USER REGISTRATION + CREDIT SYSTEM
# ============================================================

def register_user(user, referred_by=None):
    users = get_users()
    uid = str(user.id)

    if uid not in users:
        users[uid] = {
            "user_id": user.id,
            "name": user.full_name,
            "username": user.username,
            "credits": FREE_CREDITS,
            "referrals": 0,
            "referred_by": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_users(users)

        if referred_by and str(referred_by) in users and str(referred_by) != uid:
            users[uid]["referred_by"] = int(referred_by)
            users[str(referred_by)]["credits"] = users[str(referred_by)].get("credits", 0) + REFERRAL_BONUS
            users[str(referred_by)]["referrals"] = users[str(referred_by)].get("referrals", 0) + 1
            save_users(users)
    else:
        users[uid]["name"] = user.full_name
        users[uid]["username"] = user.username
        save_users(users)

    return users[uid]


def get_user(user_id):
    users = get_users()
    return users.get(str(user_id))


def update_credits(user_id, delta):
    users = get_users()
    uid = str(user_id)
    if uid not in users:
        return
    users[uid]["credits"] = max(0, users[uid].get("credits", 0) + delta)
    save_users(users)


def has_subscription(user_id):
    subs = get_subscriptions()
    uid = str(user_id)
    if uid not in subs:
        return False
    expiry_str = subs[uid].get("expires_at")
    if not expiry_str:
        return False
    try:
        expiry = datetime.fromisoformat(expiry_str)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry > datetime.now(timezone.utc)
    except Exception:
        return False


def has_access(user_id):
    if user_id == ADMIN_ID:
        return True
    if has_subscription(user_id):
        return True
    user = get_user(user_id)
    if user and user.get("credits", 0) > 0:
        return True
    return False


def deduct_credit(user_id):
    if user_id == ADMIN_ID:
        return
    if has_subscription(user_id):
        return
    update_credits(user_id, -CREDIT_PER_LOOKUP)


def refund_credit(user_id):
    if user_id == ADMIN_ID:
        return
    if has_subscription(user_id):
        return
    update_credits(user_id, +CREDIT_PER_LOOKUP)


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard(user_id):
    if user_id == ADMIN_ID:
        rows = [
            [
                KeyboardButton("📱 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ", style="primary"),
                KeyboardButton("🔢 ᴛɢ ᴛᴏ ɴᴜᴍ", style="primary"),
            ],
            [
                KeyboardButton("🪪 ᴀᴀᴅʜᴀʀ", style="primary"),
                KeyboardButton("💳 ᴘᴀɴ", style="primary"),
                KeyboardButton("🏦 ɪꜰꜱᴄ", style="primary"),
            ],
            [
                KeyboardButton("📍 ᴘɪɴ ᴄᴏᴅᴇ", style="primary"),
                KeyboardButton("🌐 ɪᴘ", style="primary"),
                KeyboardButton("📧 ᴇᴍᴀɪʟ", style="primary"),
            ],
            [
                KeyboardButton("☁️ ᴡᴇᴀᴛʜᴇʀ", style="primary"),
                KeyboardButton("👤 ᴍʏ ᴀᴄᴄᴏᴜɴᴛ", style="primary"),
            ],
            [
                KeyboardButton("⚙️ ʙᴏᴛ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ", style="danger"),
            ],
        ]
        return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)

    rows = [
        [
            KeyboardButton("📱 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ", style="primary"),
            KeyboardButton("🔢 ᴛɢ ᴛᴏ ɴᴜᴍ", style="primary"),
        ],
        [
            KeyboardButton("🪪 ᴀᴀᴅʜᴀʀ", style="primary"),
            KeyboardButton("💳 ᴘᴀɴ", style="primary"),
            KeyboardButton("🏦 ɪꜰꜱᴄ", style="primary"),
        ],
        [
            KeyboardButton("📍 ᴘɪɴ ᴄᴏᴅᴇ", style="primary"),
            KeyboardButton("🌐 ɪᴘ", style="primary"),
            KeyboardButton("📧 ᴇᴍᴀɪʟ", style="primary"),
        ],
        [
            KeyboardButton("☁️ ᴡᴇᴀᴛʜᴇʀ", style="primary"),
            KeyboardButton("👤 ᴍʏ ᴀᴄᴄᴏᴜɴᴛ", style="primary"),
        ],
        [
            KeyboardButton("🔗 ᴇᴀʀɴ ꜰʀᴇᴇ ᴄʀᴇᴅɪᴛ", style="primary"),
            KeyboardButton("💳 ʙᴜʏ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ", style="success"),
        ],
        [
            KeyboardButton("❓ ʜᴇʟᴘ", style="success"),
        ],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def channel_join_keyboard():
    rows = []
    for ch in CHANNELS:
        rows.append([InlineKeyboardButton(f"📢 ᴊᴏɪɴ {ch['name']}", url=ch["link"], style="primary")])
    rows.append([InlineKeyboardButton("✅ ɪ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ", callback_data="check_joined", style="success")])
    return InlineKeyboardMarkup(rows)


def buy_subscription_keyboard():
    """Only Buy Subscription button linking to admin."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💳 ʙᴜʏ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ",
                url=f"https://t.me/{ADMIN_USERNAME.lstrip('@')}",
                style="success",
            )
        ]
    ])


def pagination_keyboard(number, page, total):
    total_pages = max(1, math.ceil(total / RECORDS_PER_PAGE))
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️ ᴘʀᴇᴠɪᴏᴜꜱ", callback_data=f"lookup:{number}:{page - 1}", style="primary"))
    buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="lookup:page", style="success"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("ɴᴇxᴛ ▶️", callback_data=f"lookup:{number}:{page + 1}", style="primary"))
    return InlineKeyboardMarkup([buttons])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 ꜱᴛᴀᴛꜱ", callback_data="admin:stats", style="primary"),
            InlineKeyboardButton("🔎 Qᴜᴇʀʏꜱᴄᴏᴘᴇ", callback_data="admin:queries", style="primary"),
        ],
        [
            InlineKeyboardButton("💰 ɢɪᴠᴇ ᴄʀᴇᴅɪᴛ", callback_data="admin:give_credit", style="success"),
            InlineKeyboardButton("💎 ɢɪᴠᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ", callback_data="admin:give_sub", style="success"),
        ],
        [InlineKeyboardButton("📤 ʙᴏᴛ ᴍᴇꜱꜱᴇɴɢᴇʀ", callback_data="admin:messenger", style="primary")],
        [InlineKeyboardButton("🗑️ ᴄʟᴇᴀʀ Qᴜᴇʀʏꜱᴄᴏᴘᴇ", callback_data="admin:clear_queries", style="danger")],
    ])


def messenger_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 ᴛᴇxᴛ ᴍᴇꜱꜱᴀɢᴇ", callback_data="messenger:text", style="primary")],
        [
            InlineKeyboardButton("🖼️ ᴘʜᴏᴛᴏ", callback_data="messenger:photo", style="primary"),
            InlineKeyboardButton("🎬 ᴠɪᴅᴇᴏ", callback_data="messenger:video", style="primary"),
        ],
        [InlineKeyboardButton("📄 ᴅᴏᴄᴜᴍᴇɴᴛ", callback_data="messenger:document", style="primary")],
        [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="danger")],
    ])


# ============================================================
# CHANNEL CHECK
# ============================================================

async def is_member_of_all_channels(user_id, context):
    for ch in CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch["username"], user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as error:
            print(f"Channel check error [{ch['username']}]:", repr(error))
            return False
    return True


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    referred_by = None
    if context.args and context.args[0].isdigit():
        referred_by = int(context.args[0])

    user_data = register_user(user, referred_by)

    member = await is_member_of_all_channels(user.id, context)
    if not member:
        await update.message.reply_text(
            "🔐 ᴘʟᴇᴀꜱᴇ ᴊᴏɪɴ ᴀʟʟ ᴄʜᴀɴɴᴇʟꜱ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ʙᴏᴛ.\n\n"
            "ᴀꜰᴛᴇʀ ᴊᴏɪɴɪɴɢ, ᴘʀᴇꜱꜱ ✅ ɪ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ.",
            reply_markup=channel_join_keyboard(),
        )
        return

    if user.id == ADMIN_ID:
        credits_line = "💰 ᴄʀᴇᴅɪᴛꜱ: ♾️ ᴜɴʟɪᴍɪᴛᴇᴅ"
        sub_line = "💎 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ: ♾️ ꜰʀᴇᴇ"
    else:
        credits_line = f"💰 ᴄʀᴇᴅɪᴛꜱ: {user_data.get('credits', 0)}"
        sub_line = "💎 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ: " + ("✅ ᴀᴄᴛɪᴠᴇ" if has_subscription(user.id) else "❌ ɴᴏɴᴇ")

    await update.message.reply_text(
        f"👋 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴀᴋᴀꜱʜ ᴏꜱɪɴᴛ ʙᴏᴛ.\n\n"
        f"👤 ᴜꜱᴇʀ ɪᴅ: {user.id}\n"
        f"{credits_line}\n"
        f"{sub_line}\n\n"
        f"ᴄʜᴏᴏꜱᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ꜰʀᴏᴍ ᴛʜᴇ ᴍᴇɴᴜ.",
        reply_markup=main_keyboard(user.id),
    )


# ============================================================
# CLOSE
# ============================================================

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("waiting_type", None)
    context.user_data.pop("messenger_mode", None)
    context.user_data.pop("admin_action", None)
    await update.message.reply_text("🔙 ᴋᴇʏʙᴏᴀʀᴅ ʜɪᴅᴅᴇɴ.", reply_markup=ReplyKeyboardRemove())


# ============================================================
# CHECK JOINED
# ============================================================

async def check_joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    member = await is_member_of_all_channels(user.id, context)
    if not member:
        await query.edit_message_text(
            "❌ ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴀʟʟ ᴄʜᴀɴɴᴇʟꜱ ʏᴇᴛ.\n\nᴘʟᴇᴀꜱᴇ ᴊᴏɪɴ ᴀʟʟ ᴀɴᴅ ᴘʀᴇꜱꜱ ✅ ɪ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ ᴀɢᴀɪɴ.",
            reply_markup=channel_join_keyboard(),
        )
        return

    await query.edit_message_text("✅ ᴀʟʟ ᴠᴇʀɪꜰɪᴇᴅ! ᴜꜱᴇ /start ᴛᴏ ᴀᴄᴄᴇꜱꜱ ᴛʜᴇ ʙᴏᴛ.")


# ============================================================
# HELP
# ============================================================

async def show_help(update: Update):
    await update.message.reply_text(
        "𝑵𝒆𝒆𝒅 𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒄𝒆?\n\n"
        "𝑭𝒐𝒓 𝒔𝒖𝒑𝒑𝒐𝒓𝒕, 𝒊𝒔𝒔𝒖𝒆𝒔 𝒐𝒓 𝒈𝒆𝒏𝒆𝒓𝒂𝒍 "
        "𝒊𝒏𝒒𝒖𝒊𝒓𝒊𝒆𝒔, 𝒑𝒍𝒆𝒂𝒔𝒆 𝒄𝒐𝒏𝒕𝒂𝒄𝒕 𝒕𝒉𝒆 𝒂𝒅𝒎𝒊𝒏.\n\n"
        f"👨‍💻 𝑨𝒅𝒎𝒊𝒏 ~ {ADMIN_USERNAME}"
    )


# ============================================================
# MY ACCOUNT
# ============================================================

async def show_my_account(update: Update):
    user = update.effective_user
    user_data = get_user(user.id) or {}

    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👤 𝗬𝗼𝘂𝗿 𝗔𝗰𝗰𝗼𝘂𝗻𝘁\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 𝗡𝗮𝗺𝗲      • {user_data.get('name') or 'N/A'}\n"
            f"🆔 𝗨𝘀𝗲𝗿 𝗜𝗗   • {user.id}\n"
            f"🏷️ 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲  • @{user_data.get('username') or 'N/A'}\n"
            f"💰 ᴄʀᴇᴅɪᴛꜱ    • ♾️ ᴜɴʟɪᴍɪᴛᴇᴅ\n"
            f"💎 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ • ♾️ ꜰʀᴇᴇ\n\n"
            f"├ 🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️"
        )
        return

    credits = user_data.get("credits", 0)
    referrals = user_data.get("referrals", 0)
    sub_status = "✅ ᴀᴄᴛɪᴠᴇ" if has_subscription(user.id) else "❌ ɴᴏɴᴇ"

    sub_expiry = ""
    if has_subscription(user.id):
        subs = get_subscriptions()
        expiry_str = subs.get(str(user.id), {}).get("expires_at", "")
        if expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str)
                sub_expiry = f"\n📅 ᴇxᴘɪʀᴇꜱ: {expiry.strftime('%d-%m-%Y')}"
            except Exception:
                pass

    await update.message.reply_text(
        "👤 𝗬𝗼𝘂𝗿 𝗔𝗰𝗰𝗼𝘂𝗻𝘁\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 𝗡𝗮𝗺𝗲      • {user_data.get('name') or 'N/A'}\n"
        f"🆔 𝗨𝘀𝗲𝗿 𝗜𝗗   • {user.id}\n"
        f"🏷️ 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲  • @{user_data.get('username') or 'N/A'}\n"
        f"💰 ᴄʀᴇᴅɪᴛꜱ    • {credits}\n"
        f"👥 ʀᴇꜰᴇʀʀᴀʟꜱ • {referrals}\n"
        f"💎 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ • {sub_status}{sub_expiry}\n\n"
        f"├ 🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️"
    )


# ============================================================
# REFERRAL (only link + message — no stats, no buy button)
# ============================================================

async def show_referral(update: Update, context):
    user = update.effective_user
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start={user.id}"

    await update.message.reply_text(
        "🔗 𝗬𝗼𝘂𝗿 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗟𝗶𝗻𝗸\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{link}\n\n"
        f"💰 ᴇᴀʀɴ {REFERRAL_BONUS} ᴄʀᴇᴅɪᴛ ᴘᴇʀ ʀᴇꜰᴇʀʀᴀʟ"
    )


# ============================================================
# BUY SUBSCRIPTION (direct admin link only)
# ============================================================

async def show_buy_subscription(update: Update):
    await update.message.reply_text(
        "𝑺𝒖𝒃𝒔𝒄𝒓𝒊𝒑𝒕𝒊𝒐𝒏 𝑹𝒆𝒒𝒖𝒊𝒓𝒆𝒅?\n\n"
        "𝑻𝒐 𝒑𝒖𝒓𝒄𝒉𝒂𝒔𝒆 𝒂 𝒑𝒍𝒂𝒏, 𝒂𝒄𝒕𝒊𝒗𝒂𝒕𝒆 𝒚𝒐𝒖𝒓 "
        "𝒔𝒖𝒃𝒔𝒄𝒓𝒊𝒑𝒕𝒊𝒐𝒏 𝒐𝒓 𝒈𝒆𝒕 𝒑𝒍𝒂𝒏-𝒓𝒆𝒍𝒂𝒕𝒆𝒅 "
        "𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒄𝒆, 𝒑𝒍𝒆𝒂𝒔𝒆 𝒄𝒐𝒏𝒕𝒂𝒄𝒕 𝒕𝒉𝒆 𝒂𝒅𝒎𝒊𝒏.\n\n"
        f"👨🏻‍💻 𝑨𝒅𝒎𝒊𝒏 ~ {ADMIN_USERNAME}",
        reply_markup=buy_subscription_keyboard(),
    )


# ============================================================
# NORMALIZE NUMBER
# ============================================================

def clean_number(text):
    if not text:
        return ""
    number = text.strip()
    for char in [" ", "-", "(", ")", "."]:
        number = number.replace(char, "")
    if number.startswith("+91"):
        number = number[3:]
    if number.startswith("91") and len(number) == 12:
        number = number[2:]
    return number


# ============================================================
# API CALL HELPER
# ============================================================

async def call_api(url, params):
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                raw = await response.text()
                print("=" * 50)
                print("API URL:", url)
                print("API STATUS:", response.status)
                print("API RESPONSE:", raw[:2000])
                print("=" * 50)
                if response.status != 200:
                    return None, f"HTTP {response.status}"
                try:
                    return json.loads(raw), None
                except json.JSONDecodeError:
                    return None, "Invalid JSON"
    except asyncio.TimeoutError:
        return None, "Timeout"
    except Exception as error:
        print("API ERROR:", repr(error))
        return None, str(error)


def extract_records(data):
    if not isinstance(data, dict):
        return []
    for key in ["data", "results", "records"]:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    if any(key in data for key in ["name", "mobile", "phone", "phoneNumber"]):
        return [data]
    return []


def save_query(user, number, query_type="number"):
    queries = get_queries()
    queries.append({
        "user_id": user.id,
        "name": user.full_name,
        "username": user.username,
        "number": number,
        "type": query_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    queries = queries[-100:]
    save_queries(queries)


# ============================================================
# SUBSCRIPTION REQUIRED MESSAGE
# ============================================================

SUBSCRIPTION_MSG = (
    "𝑺𝒖𝒃𝒔𝒄𝒓𝒊𝒑𝒕𝒊𝒐𝒏 𝑹𝒆𝒒𝒖𝒊𝒓𝒆𝒅?\n\n"
    "💰 ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴇɴᴏᴜɢʜ ᴄʀᴇᴅɪᴛꜱ.\n\n"
    "👇 ᴄʜᴏᴏꜱᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ:\n\n"
    "🔗 ɪɴᴠɪᴛᴇ ꜰʀɪᴇɴᴅꜱ ᴛᴏ ᴇᴀʀɴ ꜰʀᴇᴇ ᴄʀᴇᴅɪᴛꜱ\n"
    "💳 ᴏʀ ʙᴜʏ ᴀ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰʀᴏᴍ ᴀᴅᴍɪɴ\n\n"
    f"👨🏻‍💻 𝑨𝒅𝒎𝒊𝒏 ~ {ADMIN_USERNAME}"
)


# ============================================================
# FORMAT NUMBER RECORD
# ============================================================

def make_safe_record(record):
    if not isinstance(record, dict):
        return {"aadhar": "N/A", "mobile": "N/A", "name": "N/A",
                "father": "N/A", "address": "N/A", "alt_mobile": "N/A",
                "circle": "N/A", "email": "N/A"}

    mobile = record.get("mobile") or record.get("phone") or record.get("phoneNumber")
    name = record.get("name") or record.get("full_name") or record.get("fullName")
    father = record.get("father") or record.get("father_name") or record.get("fatherName")
    address = record.get("address")
    alternate = (record.get("alt_mobile") or record.get("alternate")
                 or record.get("alternate_mobile") or record.get("alternateMobile"))
    aadhar = record.get("aadhar") or record.get("aadhaar") or record.get("aadhaar_number")
    circle = record.get("circle") or record.get("operator_circle") or record.get("region") or "N/A"
    circle = str(circle).replace("&amp;", "&")
    email = record.get("email") or record.get("Email") or None

    return {
        "aadhar": str(aadhar) if aadhar else "N/A",
        "mobile": str(mobile) if mobile else "N/A",
        "name": str(name) if name else "N/A",
        "father": str(father) if father else "N/A",
        "address": str(address) if address else "N/A",
        "alt_mobile": str(alternate) if alternate else "N/A",
        "circle": circle,
        "email": str(email) if email else "N/A",
    }


def format_single_record(record, index, total):
    return (
        f"👤 ʀᴇᴄᴏʀᴅ {index}/{total}\n"
        f"├🪪 ᴀᴀᴅʜᴀᴀʀ: {record['aadhar']}\n"
        f"├📱 ᴍᴏʙɪʟᴇ: {record['mobile']}\n"
        f"├👤 ɴᴀᴍᴇ: {record['name']}\n"
        f"├👨 ꜰᴀᴛʜᴇʀ: {record['father']}\n"
        f"├🏠 ᴀᴅᴅʀᴇꜱꜱ: {record['address']}\n"
        f"├📲 ᴀʟᴛ ᴍᴏʙɪʟᴇ: {record['alt_mobile']}\n"
        f"└📡 ᴄɪʀᴄʟᴇ: {record['circle']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )


def build_page(records, number, page):
    total = len(records)
    total_pages = max(1, math.ceil(total / RECORDS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * RECORDS_PER_PAGE
    end = start + RECORDS_PER_PAGE
    page_records = records[start:end]

    lines = [
        "📋 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ",
        "━━━━━━━━━━━━━━━━━━",
        f"📲ɴᴜᴍʙᴇʀ: {number}",
        f"📊 ᴛᴏᴛᴀʟ ʀᴇᴄᴏʀᴅꜱ: {total}",
        f"📄 ᴘᴀɢᴇ: {page + 1}/{total_pages}",
        "🚀 ꜱᴛᴀᴛᴜꜱ: ꜱᴜᴄᴄᴇꜱꜱ",
        "━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for position, record in enumerate(page_records, start=start + 1):
        lines.append(format_single_record(record, position, total))
        lines.append("")
    lines.append(f"🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️")
    return "\n".join(lines)


# ============================================================
# NUMBER LOOKUP
# ============================================================

async def process_number(update, context, number):
    user = update.effective_user
    clean = clean_number(number)

    if not clean.isdigit() or len(clean) != 10:
        await update.message.reply_text("❌ ᴘʟᴇᴀꜱᴇ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ 10-ᴅɪɢɪᴛ ᴍᴏʙɪʟᴇ ɴᴜᴍʙᴇʀ.")
        return

    deduct_credit(user.id)
    save_query(user, clean, "number")
    searching = await update.message.reply_text("🔎 ꜱᴇᴀʀᴄʜɪɴɢ...")

    params = {"key": API_KEY, "query": clean}
    data, error = await call_api(API_NUMBER, params)

    if error:
        refund_credit(user.id)
        await searching.edit_text(f"❌ ᴀᴘɪ ᴇʀʀᴏʀ: {error}\n\n💰 ᴄʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ.")
        return

    records = extract_records(data)
    safe_records = [make_safe_record(record) for record in records]

    if not safe_records:
        refund_credit(user.id)
        await searching.edit_text(
            "📋 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📲ɴᴜᴍʙᴇʀ: {clean}\n"
            "📊 ᴛᴏᴛᴀʟ ʀᴇᴄᴏʀᴅꜱ: 0\n"
            "🚀 ꜱᴛᴀᴛᴜꜱ: ɴᴏ ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ\n\n"
            "💰 ᴄʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ."
        )
        return

    context.user_data["lookup_records"] = safe_records
    context.user_data["lookup_number"] = clean
    text = build_page(safe_records, clean, 0)
    keyboard = pagination_keyboard(clean, 0, len(safe_records))
    await searching.edit_text(text, reply_markup=keyboard)


# ============================================================
# TG TO NUM
# ============================================================

async def process_tg_to_num(update, context, tg_id):
    user = update.effective_user
    clean = "".join(char for char in tg_id if char.isdigit())

    if not clean or len(clean) < 5:
        await update.message.reply_text("❌ ᴘʟᴇᴀꜱᴇ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴜꜱᴇʀ ɪᴅ.")
        return

    deduct_credit(user.id)
    save_query(user, clean, "tg_to_num")
    searching = await update.message.reply_text("🔎 ꜱᴇᴀʀᴄʜɪɴɢ...")

    params = {"key": API_KEY, "query": clean}
    data, error = await call_api(API_TG_TO_NUM, params)

    if error:
        refund_credit(user.id)
        await searching.edit_text(f"❌ ᴀᴘɪ ᴇʀʀᴏʀ: {error}\n\n💰 ᴄʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ.")
        return

    if not isinstance(data, dict) or "Telegram ID" not in data:
        refund_credit(user.id)
        await searching.edit_text("🔎 𝗡𝗼 𝗗𝗮𝘁𝗮 𝗙𝗼𝘂𝗻𝗱\n\n💰 ᴄʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ.")
        return

    text = (
        f"🆔 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺 𝗜𝗗 • {data.get('Telegram ID', 'N/A')}\n"
        f"📞 𝗣𝗵𝗼𝗻𝗲 • {data.get('Phone', 'N/A')}\n"
        f"🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 • {data.get('Country', 'N/A')}\n"
        f"📡 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 𝗖𝗼𝗱𝗲 • {data.get('Country Code', 'N/A')}\n\n"
        f"├ 🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️"
    )
    await searching.edit_text(text)


# ============================================================
# GENERIC LOOKUP
# ============================================================

async def process_generic_lookup(update, context, api_url, query_text, title, icon):
    user = update.effective_user

    if not api_url:
        await update.message.reply_text(f"⚠️ {icon} {title} ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
        return

    deduct_credit(user.id)
    save_query(user, query_text, title.lower())
    searching = await update.message.reply_text(f"🔎 ꜱᴇᴀʀᴄʜɪɴɢ {title}...")

    params = {"key": API_KEY, "query": query_text}
    data, error = await call_api(api_url, params)

    if error:
        refund_credit(user.id)
        await searching.edit_text(f"❌ ᴀᴘɪ ᴇʀʀᴏʀ: {error}\n\n💰 ᴄʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ.")
        return

    records = extract_records(data)
    if not records:
        refund_credit(user.id)
        await searching.edit_text(f"{icon} 𝗡𝗼 𝗗𝗮𝘁𝗮 𝗙𝗼𝘂𝗻𝗱\n\n💰 ᴄʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ.")
        return

    lines = [f"{icon} {title.upper()} 𝗟𝗢𝗢𝗞𝗨𝗣", "━━━━━━━━━━━━━━━━━━"]
    for index, record in enumerate(records, start=1):
        lines.append(f"📄 ʀᴇᴄᴏʀᴅ {index}")
        for key, value in record.items():
            if value is None or value == "":
                continue
            clean_key = str(key).replace("_", " ").title()
            lines.append(f"├ {clean_key} • {value}")
        lines.append("──────────────")
    lines.append(f"├ 🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...ᴛʀᴜɴᴄᴀᴛᴇᴅ."
    await searching.edit_text(text)


# ============================================================
# PAGINATION
# ============================================================

async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "lookup:page":
        return
    if not data.startswith("lookup:"):
        return

    parts = data.split(":")
    if len(parts) != 3:
        return

    number = parts[1]
    try:
        page = int(parts[2])
    except ValueError:
        return

    records = context.user_data.get("lookup_records", [])
    stored_number = context.user_data.get("lookup_number")

    if stored_number != number:
        await query.edit_message_text("❌ ꜱᴇꜱꜱɪᴏɴ ᴇxᴘɪʀᴇᴅ.")
        return
    if not records:
        await query.edit_message_text("❌ ɴᴏ ʀᴇᴄᴏʀᴅꜱ.")
        return

    total_pages = max(1, math.ceil(len(records) / RECORDS_PER_PAGE))
    if page < 0 or page >= total_pages:
        return

    text = build_page(records, number, page)
    keyboard = pagination_keyboard(number, page, len(records))
    await query.edit_message_text(text, reply_markup=keyboard)


# ============================================================
# BOT MANAGEMENT
# ============================================================

async def bot_management(update: Update):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ ᴀᴅᴍɪɴ ᴏɴʟʏ.")
        return
    await update.message.reply_text("⚙️ 𝗕𝗼𝘁 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁\n\nꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ:", reply_markup=admin_keyboard())


# ============================================================
# ADMIN STATS
# ============================================================

async def admin_stats(query, page=0):
    if query.from_user.id != ADMIN_ID:
        await query.answer("ᴀᴅᴍɪɴ ᴏɴʟʏ.", show_alert=True)
        return

    users = get_users()
    user_list = list(users.values())
    total_users = len(user_list)

    total_pages = max(1, math.ceil(total_users / STATS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * STATS_PER_PAGE
    end = start + STATS_PER_PAGE
    page_users = user_list[start:end]

    lines = [
        "📊 𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗦",
        "━━━━━━━━━━━━━━━━━━",
        f"👥 ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ • {total_users}",
        f"📄 ᴘᴀɢᴇ • {page + 1}/{total_pages}",
        "━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, record in enumerate(page_users, start=start + 1):
        username = record.get("username")
        username_text = f"@{username}" if username else "N/A"
        credits = record.get("credits", 0)
        subs = get_subscriptions()
        sub_status = "✅" if str(record.get("user_id")) in subs else "❌"

        lines.extend([
            f"#{i}",
            f'👤 𝗡𝗮𝗺𝗲 • "{record.get("name") or "N/A"}"',
            f'🆔 𝗨𝘀𝗲𝗿 𝗜𝗗 • "{record.get("user_id")}"',
            f'🏷️ 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲 • "{username_text}"',
            f'💰 ᴄʀᴇᴅɪᴛꜱ • {credits}',
            f'💎 ꜱᴜʙ • {sub_status}',
            "━━━━━━━━━━━━━━━━━━",
        ])

    text = "\n".join(lines)

    row1 = []
    if page > 0:
        row1.append(InlineKeyboardButton("⬅️ ᴘʀᴇᴠ", callback_data=f"admin:stats:{page - 1}", style="primary"))
    row1.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="admin:stats:nop", style="success"))
    if page < total_pages - 1:
        row1.append(InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"admin:stats:{page + 1}", style="primary"))

    buttons = [row1, [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="danger")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ============================================================
# ADMIN QUERY SCOPE
# ============================================================

async def admin_queries(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("ᴀᴅᴍɪɴ ᴏɴʟʏ.", show_alert=True)
        return

    queries = get_queries()
    if not queries:
        await query.edit_message_text(
            "🔎 𝗤𝘂𝗲𝗿𝘆𝗦𝗰𝗼𝗽𝗲\n\nɴᴏ Qᴜᴇʀɪᴇꜱ ʀᴇᴄᴏʀᴅᴇᴅ.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="primary")]]),
        )
        return

    recent = list(reversed(queries))[:20]
    lines = ["🔎 𝗤𝗨𝗘𝗥𝗬𝗦𝗖𝗢𝗣𝗘", "━━━━━━━━━━━━━━━━━━"]
    for index, item in enumerate(recent, start=1):
        lines.extend([
            f"#{index}",
            f"👤 {item.get('name') or 'N/A'}",
            f"🆔 `{item.get('user_id', 'N/A')}`",
            f"📞 {item.get('type', 'number').upper()} • `{item.get('number', 'N/A')}`",
            "──────────────",
        ])
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...ᴛʀᴜɴᴄᴀᴛᴇᴅ."
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="primary")]]),
    )


# ============================================================
# CLEAR QUERIES
# ============================================================

async def clear_queries(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("ᴀᴅᴍɪɴ ᴏɴʟʏ.", show_alert=True)
        return
    save_queries([])
    await query.edit_message_text(
        "✅ Qᴜᴇʀʏꜱᴄᴏᴘᴇ ᴄʟᴇᴀʀᴇᴅ.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="primary")]]),
    )


# ============================================================
# ADMIN CALLBACK
# ============================================================

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("ᴀᴅᴍɪɴ ᴏɴʟʏ.", show_alert=True)
        return
    await query.answer()

    data = query.data

    if data == "admin:stats":
        await admin_stats(query, 0)
    elif data.startswith("admin:stats:"):
        page_str = data.split(":")[-1]
        if page_str == "nop":
            return
        try:
            page = int(page_str)
        except ValueError:
            return
        await admin_stats(query, page)
    elif data == "admin:queries":
        await admin_queries(query)
    elif data == "admin:clear_queries":
        await clear_queries(query)
    elif data == "admin:give_credit":
        context.user_data["admin_action"] = "give_credit"
        await query.edit_message_text(
            "💰 ɢɪᴠᴇ ᴄʀᴇᴅɪᴛ\n\nꜱᴇɴᴅ ɪɴ ꜰᴏʀᴍᴀᴛ:\n`USER_ID CREDITS`\n\nᴇxᴀᴍᴘʟᴇ: `8979291976 10`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="danger")]]),
        )
    elif data == "admin:give_sub":
        context.user_data["admin_action"] = "give_sub"
        await query.edit_message_text(
            "💎 ɢɪᴠᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ\n\nꜱᴇɴᴅ ɪɴ ꜰᴏʀᴍᴀᴛ:\n`USER_ID DAYS`\n\nᴇxᴀᴍᴘʟᴇ: `8979291976 30`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="admin:back", style="danger")]]),
        )
    elif data == "admin:messenger":
        await query.edit_message_text(
            "📤 𝗕𝗼𝘁 𝗠𝗲𝘀𝘀𝗲𝗻𝗴𝗲𝗿\n\nᴡʜᴀᴛ ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ꜱᴇɴᴅ?\n\n"
            "📝 ᴛᴇxᴛ ᴍᴇꜱꜱᴀɢᴇ\n🖼️ ᴘʜᴏᴛᴏ\n🎬 ᴠɪᴅᴇᴏ\n📄 ᴅᴏᴄᴜᴍᴇɴᴛ",
            reply_markup=messenger_keyboard(),
        )
    elif data == "admin:back":
        await query.edit_message_text(
            "⚙️ 𝗕𝗼𝘁 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁\n\nꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ:",
            reply_markup=admin_keyboard(),
        )


# ============================================================
# MESSENGER CALLBACK
# ============================================================

async def messenger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("ᴀᴅᴍɪɴ ᴏɴʟʏ.", show_alert=True)
        return
    await query.answer()

    if query.data == "messenger:text":
        context.user_data["messenger_mode"] = "text"
        await query.edit_message_text("📝 ꜱᴇɴᴅ ᴛʜᴇ ᴛᴇxᴛ ᴍᴇꜱꜱᴀɢᴇ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ᴄᴀɴᴄᴇʟ", callback_data="admin:messenger", style="danger")]]))
    elif query.data == "messenger:photo":
        context.user_data["messenger_mode"] = "photo"
        await query.edit_message_text("🖼️ ꜱᴇɴᴅ ᴛʜᴇ ᴘʜᴏᴛᴏ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ᴄᴀɴᴄᴇʟ", callback_data="admin:messenger", style="danger")]]))
    elif query.data == "messenger:video":
        context.user_data["messenger_mode"] = "video"
        await query.edit_message_text("🎬 ꜱᴇɴᴅ ᴛʜᴇ ᴠɪᴅᴇᴏ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ᴄᴀɴᴄᴇʟ", callback_data="admin:messenger", style="danger")]]))
    elif query.data == "messenger:document":
        context.user_data["messenger_mode"] = "document"
        await query.edit_message_text("📄 ꜱᴇɴᴅ ᴛʜᴇ ᴅᴏᴄᴜᴍᴇɴᴛ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ᴄᴀɴᴄᴇʟ", callback_data="admin:messenger", style="danger")]]))


# ============================================================
# BROADCAST
# ============================================================

async def broadcast_to_users(context, message_type, content, caption=""):
    users = get_users()
    sent = 0
    failed = 0
    for user_id_str in users.keys():
        try:
            user_id = int(user_id_str)
            if message_type == "text":
                await context.bot.send_message(chat_id=user_id, text=content)
            elif message_type == "photo":
                await context.bot.send_photo(chat_id=user_id, photo=content, caption=caption or None)
            elif message_type == "video":
                await context.bot.send_video(chat_id=user_id, video=content, caption=caption or None)
            elif message_type == "document":
                await context.bot.send_document(chat_id=user_id, document=content, caption=caption or None)
            sent += 1
        except Exception as error:
            print(f"Broadcast error [{user_id_str}]:", repr(error))
            failed += 1
    return sent, failed


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    if not user or user.id != ADMIN_ID:
        return
    mode = context.user_data.get("messenger_mode")
    if not mode:
        return
    context.user_data.pop("messenger_mode", None)

    caption = message.caption or ""
    sent = 0
    failed = 0

    if mode == "photo" and message.photo:
        sent, failed = await broadcast_to_users(context, "photo", message.photo[-1].file_id, caption)
    elif mode == "video" and message.video:
        sent, failed = await broadcast_to_users(context, "video", message.video.file_id, caption)
    elif mode == "document" and message.document:
        sent, failed = await broadcast_to_users(context, "document", message.document.file_id, caption)
    else:
        await message.reply_text("❌ ᴡʀᴏɴɢ ᴍᴇᴅɪᴀ ᴛʏᴘᴇ.")
        return

    await message.reply_text(f"✅ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴅᴏɴᴇ\n\n📤 ꜱᴇɴᴛ: {sent}\n❌ ꜰᴀɪʟᴇᴅ: {failed}")


# ============================================================
# GROUP PROTECTION
# ============================================================

async def group_protection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    change = update.my_chat_member
    if not change:
        return
    chat = change.chat
    new_member = change.new_chat_member
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    if new_member.status not in ["member", "administrator"]:
        return
    approved = get_approved_groups()
    if chat.id in approved:
        return
    try:
        await context.bot.send_message(chat_id=chat.id, text="❌ ᴛʜɪꜱ ʙᴏᴛ ɪꜱ ɴᴏᴛ ᴀᴘᴘʀᴏᴠᴇᴅ ꜰᴏʀ ᴛʜɪꜱ ɢʀᴏᴜᴘ.")
        await context.bot.leave_chat(chat_id=chat.id)
    except Exception as error:
        print("GROUP PROTECTION ERROR:", repr(error))


# ============================================================
# TEXT HANDLER
# ============================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    if not user or not message:
        return

    text = message.text.strip() if message.text else ""

    # Back
    if text in ["🔙 ʙᴀᴄᴋ", "⬅️ ʙᴀᴄᴋ", "Back", "back", "/back"]:
        context.user_data.pop("waiting_type", None)
        context.user_data.pop("messenger_mode", None)
        context.user_data.pop("admin_action", None)
        await message.reply_text("🔙 ᴋᴇʏʙᴏᴀʀᴅ ʜɪᴅᴅᴇɴ.", reply_markup=ReplyKeyboardRemove())
        return

    # Messenger Text Mode
    if user.id == ADMIN_ID and context.user_data.get("messenger_mode") == "text":
        context.user_data.pop("messenger_mode", None)
        sent, failed = await broadcast_to_users(context, "text", text)
        await message.reply_text(f"✅ ᴍᴇꜱꜱᴀɢᴇ ꜱᴇɴᴛ\n\n📤 ꜱᴇɴᴛ: {sent}\n❌ ꜰᴀɪʟᴇᴅ: {failed}")
        return

    # Admin: give_credit
    if user.id == ADMIN_ID and context.user_data.get("admin_action") == "give_credit":
        context.user_data.pop("admin_action", None)
        parts = text.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            target_id = int(parts[0])
            amount = int(parts[1])
            users = get_users()
            if str(target_id) in users:
                users[str(target_id)]["credits"] = users[str(target_id)].get("credits", 0) + amount
                save_users(users)
                await message.reply_text(f"✅ ᴀᴅᴅᴇᴅ {amount} ᴄʀᴇᴅɪᴛꜱ ᴛᴏ `{target_id}`.", parse_mode="Markdown")
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"💰 ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇᴅ {amount} ᴄʀᴇᴅɪᴛꜱ ꜰʀᴏᴍ ᴀᴅᴍɪɴ!",
                        reply_markup=main_keyboard(target_id),
                    )
                except Exception as e:
                    print("Notify error:", repr(e))
            else:
                await message.reply_text("❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.")
        else:
            await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ꜰᴏʀᴍᴀᴛ. ᴜꜱᴇ: `USER_ID CREDITS`", parse_mode="Markdown")
        return

    # Admin: give_sub
    if user.id == ADMIN_ID and context.user_data.get("admin_action") == "give_sub":
        context.user_data.pop("admin_action", None)
        parts = text.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            target_id = int(parts[0])
            days = int(parts[1])
            subs = get_subscriptions()
            expires = datetime.now(timezone.utc) + timedelta(days=days)
            subs[str(target_id)] = {
                "user_id": target_id,
                "expires_at": expires.isoformat(),
                "activated_at": datetime.now(timezone.utc).isoformat(),
            }
            save_subscriptions(subs)
            await message.reply_text(f"✅ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ꜰᴏʀ `{target_id}` ꜰᴏʀ {days} ᴅᴀʏꜱ.", parse_mode="Markdown")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"💎 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ!\n\nᴠᴀʟɪᴅ ꜰᴏʀ {days} ᴅᴀʏꜱ.",
                    reply_markup=main_keyboard(target_id),
                )
            except Exception as e:
                print("Notify error:", repr(e))
        else:
            await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ꜰᴏʀᴍᴀᴛ. ᴜꜱᴇ: `USER_ID DAYS`", parse_mode="Markdown")
        return

    # Channel check
    member = await is_member_of_all_channels(user.id, context)
    if not member:
        await message.reply_text("🔐 ᴘʟᴇᴀꜱᴇ ᴊᴏɪɴ ᴀʟʟ ᴄʜᴀɴɴᴇʟꜱ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ʙᴏᴛ.", reply_markup=channel_join_keyboard())
        return

    # Non-access buttons
    if text == "❓ ʜᴇʟᴘ":
        await show_help(update)
        return
    if text == "👤 ᴍʏ ᴀᴄᴄᴏᴜɴᴛ":
        await show_my_account(update)
        return
    if text == "🔗 ᴇᴀʀɴ ꜰʀᴇᴇ ᴄʀᴇᴅɪᴛ" and user.id != ADMIN_ID:
        await show_referral(update, context)
        return
    if text == "💳 ʙᴜʏ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ" and user.id != ADMIN_ID:
        await show_buy_subscription(update)
        return
    if text == "⚙️ ʙᴏᴛ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ" and user.id == ADMIN_ID:
        await bot_management(update)
        return

    # Lookup buttons
    lookup_buttons = [
        "📱 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ", "🔢 ᴛɢ ᴛᴏ ɴᴜᴍ",
        "🪪 ᴀᴀᴅʜᴀʀ", "💳 ᴘᴀɴ",
        "🏦 ɪꜰꜱᴄ", "📍 ᴘɪɴ ᴄᴏᴅᴇ",
        "🌐 ɪᴘ", "📧 ᴇᴍᴀɪʟ", "☁️ ᴡᴇᴀᴛʜᴇʀ"
    ]

    if text in lookup_buttons:
        if not has_access(user.id):
            await message.reply_text(SUBSCRIPTION_MSG, reply_markup=buy_subscription_keyboard())
            return

        if text == "📱 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ":
            context.user_data["waiting_type"] = "number"
            await message.reply_text("📞 ꜱᴇɴᴅ 10-ᴅɪɢɪᴛ ɴᴜᴍʙᴇʀ:")
        elif text == "🔢 ᴛɢ ᴛᴏ ɴᴜᴍ":
            context.user_data["waiting_type"] = "tg_to_num"
            await message.reply_text("🔢 ꜱᴇɴᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴜꜱᴇʀ ɪᴅ:")
        elif text == "🪪 ᴀᴀᴅʜᴀʀ":
            if not API_AADHAR:
                await message.reply_text(f"⚠️ ᴀᴀᴅʜᴀʀ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "aadhar"
            await message.reply_text("🪪 ꜱᴇɴᴅ 12-ᴅɪɢɪᴛ ᴀᴀᴅʜᴀʀ ɴᴜᴍʙᴇʀ:")
        elif text == "💳 ᴘᴀɴ":
            if not API_PAN:
                await message.reply_text(f"⚠️ ᴘᴀɴ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "pan"
            await message.reply_text("💳 ꜱᴇɴᴅ ᴘᴀɴ ɴᴜᴍʙᴇʀ:")
        elif text == "🏦 ɪꜰꜱᴄ":
            if not API_IFSC:
                await message.reply_text(f"⚠️ ɪꜰꜱᴄ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "ifsc"
            await message.reply_text("🏦 ꜱᴇɴᴅ ɪꜰꜱᴄ ᴄᴏᴅᴇ:")
        elif text == "📍 ᴘɪɴ ᴄᴏᴅᴇ":
            if not API_PINCODE:
                await message.reply_text(f"⚠️ ᴘɪɴ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "pincode"
            await message.reply_text("📍 ꜱᴇɴᴅ ᴘɪɴ ᴄᴏᴅᴇ:")
        elif text == "🌐 ɪᴘ":
            if not API_IP:
                await message.reply_text(f"⚠️ ɪᴘ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "ip"
            await message.reply_text("🌐 ꜱᴇɴᴅ ɪᴘ ᴀᴅᴅʀᴇꜱꜱ:")
        elif text == "📧 ᴇᴍᴀɪʟ":
            if not API_EMAIL:
                await message.reply_text(f"⚠️ ᴇᴍᴀɪʟ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "email"
            await message.reply_text("📧 ꜱᴇɴᴅ ᴇᴍᴀɪʟ ᴀᴅᴅʀᴇꜱꜱ:")
        elif text == "☁️ ᴡᴇᴀᴛʜᴇʀ":
            if not API_WEATHER:
                await message.reply_text(f"⚠️ ᴡᴇᴀᴛʜᴇʀ ᴀᴘɪ ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.\n\nᴄᴏɴᴛᴀᴄᴛ {ADMIN_USERNAME}")
                return
            context.user_data["waiting_type"] = "weather"
            await message.reply_text("☁️ ꜱᴇɴᴅ ᴄɪᴛʏ ɴᴀᴍᴇ:")
        return

    # Waiting for input
    waiting = context.user_data.get("waiting_type")
    if waiting == "number":
        context.user_data.pop("waiting_type", None)
        await process_number(update, context, text)
        return
    if waiting == "tg_to_num":
        context.user_data.pop("waiting_type", None)
        await process_tg_to_num(update, context, text)
        return
    if waiting == "aadhar":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_AADHAR, text, "Aadhar", "🪪")
        return
    if waiting == "pan":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_PAN, text, "Pan", "💳")
        return
    if waiting == "ifsc":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_IFSC, text, "IFSC", "🏦")
        return
    if waiting == "pincode":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_PINCODE, text, "Pin Code", "📍")
        return
    if waiting == "ip":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_IP, text, "IP", "🌐")
        return
    if waiting == "email":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_EMAIL, text, "Email", "📧")
        return
    if waiting == "weather":
        context.user_data.pop("waiting_type", None)
        await process_generic_lookup(update, context, API_WEATHER, text, "Weather", "☁️")
        return

    await message.reply_text("ᴘʟᴇᴀꜱᴇ ᴄʜᴏᴏꜱᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ꜰʀᴏᴍ ᴛʜᴇ ᴍᴇɴᴜ.", reply_markup=main_keyboard(user.id))


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("BOT ERROR:", repr(context.error))


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 50)
    print("AKASH OSINT BOT")
    print("=" * 50)

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("close", close_command))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_media))
    app.add_handler(CallbackQueryHandler(check_joined_callback, pattern="^check_joined$"))
    app.add_handler(CallbackQueryHandler(pagination_callback, pattern=r"^lookup:"))
    app.add_handler(CallbackQueryHandler(messenger_callback, pattern=r"^messenger:"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    app.add_handler(ChatMemberHandler(group_protection, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
