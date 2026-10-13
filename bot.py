import os
import json
import math
import asyncio
import threading
from datetime import datetime, timezone

import aiohttp
from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
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

# ---------- Channels to join ----------
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

USERS_FILE = "users.json"
VERIFIED_FILE = "verified.json"
QUERIES_FILE = "queries.json"
APPROVED_GROUPS_FILE = "approved_groups.json"


# ============================================================
# FLASK HEALTH SERVER FOR RENDER
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
    health_app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(filename, default):
    try:
        if not os.path.exists(filename):
            return default
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as error:
        print(f"JSON LOAD ERROR [{filename}]:", repr(error))
        return default


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        return True
    except Exception as error:
        print(f"JSON SAVE ERROR [{filename}]:", repr(error))
        return False


# ============================================================
# USER DATA
# ============================================================

def get_users():
    return load_json(USERS_FILE, {})


def save_users(data):
    save_json(USERS_FILE, data)


def get_verified():
    return load_json(VERIFIED_FILE, {})


def save_verified(data):
    save_json(VERIFIED_FILE, data)


def get_queries():
    return load_json(QUERIES_FILE, [])


def save_queries(data):
    save_json(QUERIES_FILE, data)


def get_approved_groups():
    return load_json(APPROVED_GROUPS_FILE, [])


def save_approved_groups(data):
    save_json(APPROVED_GROUPS_FILE, data)


# ============================================================
# USER REGISTRATION
# ============================================================

def register_user(user):
    users = get_users()
    user_id = str(user.id)

    users[user_id] = {
        "user_id": user.id,
        "name": user.full_name,
        "username": user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    save_users(users)


def is_verified(user_id):
    verified = get_verified()
    return str(user_id) in verified


# ============================================================
# MAIN KEYBOARD
# ============================================================

def main_keyboard(user_id):
    rows = [
        [
            KeyboardButton("📱 Number Lookup"),
            KeyboardButton("🔢 TG to Num"),
        ],
        [
            KeyboardButton("🪪 Aadhar"),
            KeyboardButton("💳 Pan"),
        ],
        [
            KeyboardButton("🏦 IFSC"),
            KeyboardButton("📍 Pin Code"),
        ],
        [
            KeyboardButton("🌐 IP"),
            KeyboardButton("📧 Email"),
        ],
        [
            KeyboardButton("☁️ Weather"),
            KeyboardButton("👤 My Contact"),
        ],
        [
            KeyboardButton("❓ Help"),
        ],
    ]

    if user_id == ADMIN_ID:
        rows.append(
            [
                KeyboardButton("⚙️ Bot Management"),
            ]
        )

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


# ============================================================
# CONTACT VERIFICATION KEYBOARD
# ============================================================

def contact_keyboard():
    keyboard = [
        [
            KeyboardButton(
                "📱 Share My Contact",
                request_contact=True,
            )
        ]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# CHANNEL JOIN KEYBOARD
# ============================================================

def channel_join_keyboard():
    rows = []
    for ch in CHANNELS:
        rows.append(
            [InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch["link"])]
        )
    rows.append(
        [InlineKeyboardButton("✅ I Have Joined", callback_data="check_joined")]
    )
    return InlineKeyboardMarkup(rows)


# ============================================================
# CHECK CHANNEL MEMBERSHIP
# ============================================================

async def is_member_of_all_channels(user_id, context):
    for ch in CHANNELS:
        try:
            member = await context.bot.get_chat_member(
                chat_id=ch["username"],
                user_id=user_id,
            )
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

    register_user(user)

    member = await is_member_of_all_channels(user.id, context)

    if not member:
        await update.message.reply_text(
            "🔐 Please join all channels to use this bot.\n\n"
            "After joining, press ✅ I Have Joined.",
            reply_markup=channel_join_keyboard(),
        )
        return

    if not is_verified(user.id):
        await update.message.reply_text(
            "🔐 Verification required.\n\n"
            "Please share your own Telegram contact using the button below.",
            reply_markup=contact_keyboard(),
        )
        return

    await update.message.reply_text(
        f"👋 Welcome to AKASH OSINT Bot.\n\n"
        f"👤 User ID: {user.id}\n"
        f"✅ You are verified!\n\n"
        f"Choose an option from the menu below.",
        reply_markup=main_keyboard(user.id),
    )


# ============================================================
# CHECK JOINED CALLBACK
# ============================================================

async def check_joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    member = await is_member_of_all_channels(user.id, context)

    if not member:
        await query.edit_message_text(
            "❌ You haven't joined all channels yet.\n\n"
            "Please join all and press ✅ I Have Joined again.",
            reply_markup=channel_join_keyboard(),
        )
        return

    if not is_verified(user.id):
        await query.edit_message_text(
            "✅ Channels verified!\n\n"
            "Now please share your contact using /start",
        )
        return

    await query.edit_message_text(
        "✅ All verified! Use /start to access the bot."
    )


# ============================================================
# CONTACT VERIFICATION
# ============================================================

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if not user or not message or not message.contact:
        return

    contact = message.contact

    if contact.user_id != user.id:
        await message.reply_text(
            "❌ Please share your own Telegram contact.",
            reply_markup=contact_keyboard(),
        )
        return

    verified = get_verified()
    verified[str(user.id)] = {
        "user_id": user.id,
        "name": user.full_name,
        "username": user.username,
        "contact": contact.phone_number,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    save_verified(verified)

    await message.reply_text(
        "✅ Verification successful!\n\n"
        "You can now use the bot.",
        reply_markup=main_keyboard(user.id),
    )


# ============================================================
# HELP
# ============================================================

async def show_help(update: Update):
    await update.message.reply_text(
        "𝑵𝒆𝒆𝒅 𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒄𝒆?\n\n"
        "𝑭𝒐𝒓 𝒔𝒖𝒑𝒑𝒐𝒓𝒕, 𝒊𝒔𝒔𝒖𝒆𝒔 𝒐𝒓 𝒈𝒆𝒏𝒆𝒓𝒂𝒍 "
        "𝒊𝒏𝒒𝒖𝒊𝒓𝒊𝒆𝒔, 𝒑𝒍𝒆𝒂𝒔𝒆 𝒄𝒐𝒏𝒕𝒂𝒄𝒕 𝒕𝒉𝒆 𝒂𝒅𝒎𝒊𝒏.\n\n"
        f"👨‍💻 𝑨𝒅𝒎𝒊𝒏 ~ {ADMIN_USERNAME}\n"
        f"🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️"
    )


# ============================================================
# MY CONTACT
# ============================================================

async def show_my_contact(update: Update):
    user = update.effective_user
    verified = get_verified()
    record = verified.get(str(user.id))

    if not record:
        await update.message.reply_text(
            "❌ You are not verified yet.",
            reply_markup=contact_keyboard(),
        )
        return

    contact = record.get("contact")
    await update.message.reply_text(
        "👤 𝗬𝗼𝘂𝗿 𝗖𝗼𝗻𝘁𝗮𝗰𝘁\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 𝗡𝗮𝗺𝗲      • {record.get('name') or 'N/A'}\n"
        f"🆔 𝗨𝘀𝗲𝗿 𝗜𝗗   • {record.get('user_id')}\n"
        f"🏷️ 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲  • @{record.get('username') or 'N/A'}\n"
        f"☎️ 𝗖𝗼𝗻𝘁𝗮𝗰𝘁   • {contact or 'N/A'}\n\n"
        f"├ 🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️"
    )


# ============================================================
# NUMBER NORMALIZATION
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
                print("API RESPONSE:", raw[:3000])
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


# ============================================================
# API RECORD EXTRACTION
# ============================================================

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


# ============================================================
# SAFE RECORD FORMAT
# ============================================================

def make_safe_record(record):
    if not isinstance(record, dict):
        return {
            "aadhar": "N/A", "mobile": "N/A", "name": "N/A",
            "father": "N/A", "address": "N/A",
            "alt_mobile": "N/A", "circle": "N/A", "email": "N/A",
        }

    mobile = record.get("mobile") or record.get("phone") or record.get("phoneNumber")
    name = record.get("name") or record.get("full_name") or record.get("fullName")
    father = record.get("father") or record.get("father_name") or record.get("fatherName")
    address = record.get("address")
    alternate = (
        record.get("alt_mobile") or record.get("alternate")
        or record.get("alternate_mobile") or record.get("alternateMobile")
    )
    aadhar = record.get("aadhar") or record.get("aadhaar") or record.get("aadhaar_number")
    circle = (
        record.get("circle") or record.get("operator_circle")
        or record.get("region") or "N/A"
    )
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


# ============================================================
# FORMAT ONE RECORD
# ============================================================

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


# ============================================================
# BUILD PAGINATION PAGE
# ============================================================

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
# PAGINATION KEYBOARD
# ============================================================

def pagination_keyboard(number, page, total):
    total_pages = max(1, math.ceil(total / RECORDS_PER_PAGE))
    buttons = []

    if page > 0:
        buttons.append(
            InlineKeyboardButton("◀️ Previous", callback_data=f"lookup:{number}:{page - 1}")
        )

    buttons.append(
        InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="lookup:page")
    )

    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton("Next ▶️", callback_data=f"lookup:{number}:{page + 1}")
        )

    return InlineKeyboardMarkup([buttons])


# ============================================================
# SAVE QUERY
# ============================================================

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
    queries = queries[-25:]
    save_queries(queries)


# ============================================================
# NUMBER LOOKUP
# ============================================================

async def process_number(update, context, number):
    user = update.effective_user
    clean = clean_number(number)

    if not clean.isdigit() or len(clean) != 10:
        await update.message.reply_text(
            "❌ Please send a valid 10-digit mobile number.\n\nExample:\n9876543210"
        )
        return

    save_query(user, clean, "number")

    searching = await update.message.reply_text("🔎 Searching authorized/test records...")

    params = {"key": API_KEY, "query": clean}
    data, error = await call_api(API_NUMBER, params)

    if error:
        await searching.edit_text(f"❌ API Error: {error}\n\nPlease try again later.")
        return

    records = extract_records(data)
    safe_records = [make_safe_record(record) for record in records]

    if not safe_records:
        await searching.edit_text(
            "📋 ɴᴜᴍʙᴇʀ ʟᴏᴏᴋᴜᴘ\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📲ɴᴜᴍʙᴇʀ: {clean}\n"
            "📊 ᴛᴏᴛᴀʟ ʀᴇᴄᴏʀᴅꜱ: 0\n"
            "🚀 ꜱᴛᴀᴛᴜꜱ: ɴᴏ ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ\n\n"
            "No authorized/test record was found."
        )
        return

    context.user_data["lookup_records"] = safe_records
    context.user_data["lookup_number"] = clean

    text = build_page(safe_records, clean, 0)
    keyboard = pagination_keyboard(clean, 0, len(safe_records))

    await searching.edit_text(text, reply_markup=keyboard)


# ============================================================
# TG TO NUM LOOKUP
# ============================================================

async def process_tg_to_num(update, context, tg_id):
    user = update.effective_user
    clean = "".join(char for char in tg_id if char.isdigit())

    if not clean or len(clean) < 5:
        await update.message.reply_text(
            "❌ Please send a valid Telegram User ID.\n\nExample:\n5437510481"
        )
        return

    save_query(user, clean, "tg_to_num")

    searching = await update.message.reply_text("🔎 Searching TG to Num...")

    params = {"key": API_KEY, "query": clean}
    data, error = await call_api(API_TG_TO_NUM, params)

    if error:
        await searching.edit_text(f"❌ API Error: {error}\n\nPlease try again later.")
        return

    if not isinstance(data, dict) or "Telegram ID" not in data:
        await searching.edit_text("🔎 𝗡𝗼 𝗗𝗮𝘁𝗮 𝗙𝗼𝘂𝗻𝗱")
        return

    text = (
        "📱 𝗧𝗚 𝘁𝗼 𝗡𝘂𝗺 𝗟𝗼𝗼𝗸𝘂𝗽\n"
        "━━━━━━━━━━━━━━━━━━\n"
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
    if not api_url:
        await update.message.reply_text(
            f"⚠️ {icon} {title} API is not yet configured.\n\n"
            f"Please contact admin: {ADMIN_USERNAME}"
        )
        return

    user = update.effective_user
    save_query(user, query_text, title.lower())

    searching = await update.message.reply_text(f"🔎 Searching {title}...")

    params = {"key": API_KEY, "query": query_text}
    data, error = await call_api(api_url, params)

    if error:
        await searching.edit_text(f"❌ API Error: {error}\n\nPlease try again later.")
        return

    records = extract_records(data)

    if not records:
        await searching.edit_text(f"{icon} 𝗡𝗼 𝗗𝗮𝘁𝗮 𝗙𝗼𝘂𝗻𝗱")
        return

    lines = [
        f"{icon} {title.upper()} 𝗟𝗢𝗢𝗞𝗨𝗣",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for index, record in enumerate(records, start=1):
        lines.append(f"📄 Record {index}")
        for key, value in record.items():
            if value is None or value == "":
                continue
            clean_key = str(key).replace("_", " ").title()
            lines.append(f"├ {clean_key} • {value}")
        lines.append("──────────────")

    lines.append(f"├ 🛠️ ᴅᴇᴠᴇʟᴏᴘᴇʀ: {DEVELOPER} • 🛰️")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...output truncated."

    await searching.edit_text(text)


# ============================================================
# PAGINATION CALLBACK
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
        await query.edit_message_text(
            "❌ This lookup session has expired.\n\nPlease perform a new lookup."
        )
        return

    if not records:
        await query.edit_message_text("❌ No lookup records available.")
        return

    total_pages = max(1, math.ceil(len(records) / RECORDS_PER_PAGE))
    if page < 0 or page >= total_pages:
        return

    text = build_page(records, number, page)
    keyboard = pagination_keyboard(number, page, len(records))
    await query.edit_message_text(text, reply_markup=keyboard)


# ============================================================
# ADMIN MANAGEMENT
# ============================================================

def admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Stats", callback_data="admin:stats"),
                InlineKeyboardButton("🔎 QueryScope", callback_data="admin:queries"),
            ],
            [
                InlineKeyboardButton("🗑️ Clear QueryScope", callback_data="admin:clear_queries"),
            ],
        ]
    )


async def bot_management(update: Update):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return

    await update.message.reply_text(
        "⚙️ 𝗕𝗼𝘁 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁\n\nSelect an option:",
        reply_markup=admin_keyboard(),
    )


# ============================================================
# ADMIN STATS
# ============================================================

async def admin_stats(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("Admin only.", show_alert=True)
        return

    users = get_users()
    verified = get_verified()

    lines = [
        "📊 𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗦",
        "━━━━━━━━━━━━━━━━━━",
        f"👥 Total Users • {len(users)}",
        f"✅ Verified Users • {len(verified)}",
        "",
    ]

    for record in verified.values():
        username = record.get("username")
        username_text = f"@{username}" if username else "N/A"
        lines.extend([
            f'👤 𝗡𝗮𝗺𝗲      • "{record.get("name") or "N/A"}"',
            f'🆔 𝗨𝘀𝗲𝗿 𝗜𝗗   • "{record.get("user_id")}"',
            f'🏷️ 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲  • "{username_text}"',
            f'☎️ 𝗖𝗼𝗻𝘁𝗮𝗰𝘁   • "{record.get("contact") or "N/A"}"',
            "━━━━━━━━━━━━━━━━━━",
        ])

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n\n...output truncated."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="admin:back")]]
        ),
    )


# ============================================================
# ADMIN QUERY SCOPE
# ============================================================

async def admin_queries(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("Admin only.", show_alert=True)
        return

    queries = get_queries()

    if not queries:
        await query.edit_message_text(
            "🔎 𝗤𝘂𝗲𝗿𝘆𝗦𝗰𝗼𝗽𝗲\n\nNo queries recorded.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="admin:back")]]
            ),
        )
        return

    lines = ["🔎 𝗤𝗨𝗘𝗥𝗬𝗦𝗖𝗢𝗣𝗘", "━━━━━━━━━━━━━━━━━━"]

    for index, item in enumerate(reversed(queries), start=1):
        number = str(item.get("number", ""))
        qtype = item.get("type", "number").upper()

        if len(number) > 4:
            display_number = "*" * (len(number) - 4) + number[-4:]
        else:
            display_number = "****"

        lines.extend([
            f"#{index}",
            f"👤 {item.get('name') or 'N/A'}",
            f"🆔 {item.get('user_id')}",
            f"📞 {qtype} • {display_number}",
            "──────────────",
        ])

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n\n...output truncated."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="admin:back")]]
        ),
    )


# ============================================================
# CLEAR QUERIES
# ============================================================

async def clear_queries(query):
    if query.from_user.id != ADMIN_ID:
        await query.answer("Admin only.", show_alert=True)
        return

    save_queries([])

    await query.edit_message_text(
        "✅ QueryScope cleared.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="admin:back")]]
        ),
    )


# ============================================================
# ADMIN CALLBACK
# ============================================================

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.from_user.id != ADMIN_ID:
        await query.answer("Admin only.", show_alert=True)
        return

    await query.answer()

    if query.data == "admin:stats":
        await admin_stats(query)
    elif query.data == "admin:queries":
        await admin_queries(query)
    elif query.data == "admin:clear_queries":
        await clear_queries(query)
    elif query.data == "admin:back":
        await query.edit_message_text(
            "⚙️ 𝗕𝗼𝘁 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁\n\nSelect an option:",
            reply_markup=admin_keyboard(),
        )


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

    status = new_member.status
    if status not in ["member", "administrator"]:
        return

    approved = get_approved_groups()
    if chat.id in approved:
        return

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="❌ This bot is not approved for this group.\n\nThe bot will leave now.",
        )
        await context.bot.leave_chat(chat_id=chat.id)
        print("Left unapproved group:", chat.id, chat.title)
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

    member = await is_member_of_all_channels(user.id, context)
    if not member:
        await message.reply_text(
            "🔐 Please join all channels to use this bot.\n\n"
            "After joining, press ✅ I Have Joined.",
            reply_markup=channel_join_keyboard(),
        )
        return

    if not is_verified(user.id):
        await message.reply_text(
            "🔐 Please verify first by sharing your own contact.",
            reply_markup=contact_keyboard(),
        )
        return

    text = message.text.strip()

    # ---------- Lookup buttons ----------

    if text == "📱 Number Lookup":
        context.user_data["waiting_type"] = "number"
        await message.reply_text("📞 Send 10-digit number:\n\nExample:\n9876543210")
        return

    if text == "🔢 TG to Num":
        context.user_data["waiting_type"] = "tg_to_num"
        await message.reply_text("🔢 Send Telegram User ID:\n\nExample:\n5437510481")
        return

    if text == "🪪 Aadhar":
        if not API_AADHAR:
            await message.reply_text(f"⚠️ Aadhar API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "aadhar"
        await message.reply_text("🪪 Send 12-digit Aadhar number:")
        return

    if text == "💳 Pan":
        if not API_PAN:
            await message.reply_text(f"⚠️ Pan API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "pan"
        await message.reply_text("💳 Send PAN number (e.g. ABCDE1234F):")
        return

    if text == "🏦 IFSC":
        if not API_IFSC:
            await message.reply_text(f"⚠️ IFSC API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "ifsc"
        await message.reply_text("🏦 Send IFSC code (e.g. SBIN0001234):")
        return

    if text == "📍 Pin Code":
        if not API_PINCODE:
            await message.reply_text(f"⚠️ Pin Code API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "pincode"
        await message.reply_text("📍 Send PIN code (e.g. 110001):")
        return

    if text == "🌐 IP":
        if not API_IP:
            await message.reply_text(f"⚠️ IP API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "ip"
        await message.reply_text("🌐 Send IP address (e.g. 8.8.8.8):")
        return

    if text == "📧 Email":
        if not API_EMAIL:
            await message.reply_text(f"⚠️ Email API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "email"
        await message.reply_text("📧 Send email address:")
        return

    if text == "☁️ Weather":
        if not API_WEATHER:
            await message.reply_text(f"⚠️ Weather API not configured yet.\n\nContact {ADMIN_USERNAME}")
            return
        context.user_data["waiting_type"] = "weather"
        await message.reply_text("☁️ Send city name (e.g. Delhi):")
        return

    # ---------- Other buttons ----------

    if text == "👤 My Contact":
        await show_my_contact(update)
        return

    if text == "❓ Help":
        await show_help(update)
        return

    if text == "⚙️ Bot Management":
        await bot_management(update)
        return

    # ---------- Waiting for input ----------

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

    await message.reply_text(
        "Please choose an option from the menu.",
        reply_markup=main_keyboard(user.id),
    )


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
    print("Starting...")
    print("=" * 50)

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CallbackQueryHandler(check_joined_callback, pattern="^check_joined$"))
    app.add_handler(CallbackQueryHandler(pagination_callback, pattern=r"^lookup:"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    app.add_handler(ChatMemberHandler(group_protection, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
