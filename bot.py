import json
import os
import re
import sys
import time
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ---------- ENVIRONMENT VARIABLES ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8875132519:AAEJNNuZqaLD2qV_5G6mFLTEmkavL20eXlg")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8979291976").split(",")]

# ---------- CHANNELS ----------
CHANNELS = [
    {"name": "Channel 1", "username": "@wftis_ak4sh", "link": "https://t.me/wftis_ak4sh"},
    {"name": "Channel 2", "username": "@Err9r403", "link": "https://t.me/Err9r403"},
    {"name": "Channel 3", "username": "@AkashOSINT", "link": "https://t.me/AkashOSINT"},
    {"name": "Group GC", "username": "+oRfAbV_UhstmZDdh", "link": "https://t.me/+oRfAbV_UhstmZDdh"}
]

# ---------- API URLs ----------
API_NUMBER = "https://akash-number-lookup.vercel.app/info?key=DEMO&query={}"
API_IFSC = "https://vercei-kappa.vercel.app/ifsc?code={}"
API_PINCODE = "https://nitin-apis-update-birthday-spacial.vercel.app/api?type=pincode&search={}"
API_WEATHER = "https://nitin-wather-check-api.vercel.app/api?type=weather&search={}"
API_EMAIL = "https://travelers-creature-sarah-rogers.trycloudflare.com/search?q={}"
API_AADHAR = "https://akash-adhar-lookup.vercel.app/info?key=DEMO&query={}"
API_IP = "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query={}"
API_PAN = "https://counted-developing-parade-man.trycloudflare.com/pan-info?pan={}"
API_TG_TO_NUM = "https://akash-tg-num.vercel.app/info?key=DEMO&query={}"

COINS_ON_START = 5
COST_PER_LOOKUP = 1
REFERRAL_BONUS = 1
HISTORY_LIMIT = 10
HISTORY_TTL_HOURS = 24

DATA_FILE = "user_data.json"
BLOCK_FILE = "blocked_users.json"
QUERY_LOG_FILE = "query_log.json"
ACCESS_FILE = "access_users.json"
MAX_LOG_ENTRIES = 200

ADMIN_USERNAME = "@AK4SX"


# ---------- AUTO-CLEAN ----------
def clean_old_history():
    data = load_data()
    cutoff = datetime.now() - timedelta(hours=HISTORY_TTL_HOURS)
    changed = False
    for uid, info in data.items():
        history = info.get("history", [])
        new_history = []
        for entry in history:
            m = re.match(r"^(.*)\s*\((\d{4}-\d{2}-\d{2}T.*)\)$", entry)
            if m:
                try:
                    ts = datetime.fromisoformat(m.group(2))
                    if ts >= cutoff:
                        new_history.append(entry)
                    else:
                        changed = True
                except:
                    new_history.append(entry)
            else:
                new_history.append(entry)
        info["history"] = new_history[-HISTORY_LIMIT:]
        if len(new_history) != len(history):
            changed = True
    if changed:
        save_data(data)


def clean_old_queries():
    log = load_query_log()
    cutoff = datetime.now() - timedelta(hours=HISTORY_TTL_HOURS)
    new_log = []
    for entry in log:
        try:
            ts = datetime.fromisoformat(entry.get("timestamp", ""))
            if ts >= cutoff:
                new_log.append(entry)
        except:
            new_log.append(entry)
    if len(new_log) != len(log):
        save_query_log(new_log)


def auto_cleaner():
    while True:
        try:
            clean_old_history()
            clean_old_queries()
        except Exception as e:
            print("Auto-cleaner error:", e)
        time.sleep(600)


# ---------- DATA ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_blocked():
    if os.path.exists(BLOCK_FILE):
        with open(BLOCK_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_blocked(b):
    with open(BLOCK_FILE, "w") as f:
        json.dump(list(b), f)

def load_query_log():
    if os.path.exists(QUERY_LOG_FILE):
        with open(QUERY_LOG_FILE, "r") as f:
            return json.load(f)
    return []

def save_query_log(log):
    with open(QUERY_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)

def load_access():
    if os.path.exists(ACCESS_FILE):
        with open(ACCESS_FILE, "r") as f:
            return json.load(f)
    return {"collaborators": [], "moderators": []}

def save_access(a):
    with open(ACCESS_FILE, "w") as f:
        json.dump(a, f, indent=2)

def is_collaborator(uid):
    return uid in load_access().get("collaborators", [])

def is_moderator(uid):
    return uid in load_access().get("moderators", [])

def has_special_access(uid):
    return is_collaborator(uid) or is_moderator(uid)

def get_user_data(user_id, name=None):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "coins": COINS_ON_START, "referrals": 0,
            "referred_by": None, "history": [],
            "name": name, "phone": None
        }
        save_data(data)
    elif name and not data[uid].get("name"):
        data[uid]["name"] = name
        save_data(data)
    return data[uid]

def update_user_data(user_id, new_data):
    data = load_data()
    data[str(user_id)] = new_data
    save_data(data)


# ---------- VERIFICATION ----------
async def is_member(user_id, context):
    for ch in CHANNELS:
        try:
            if ch["username"].startswith("+"):
                continue
            member = await context.bot.get_chat_member(chat_id=ch["username"], user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            print(f"Membership check error for {ch['username']}: {e}")
            return False
    return True

async def is_verified(user_id, context):
    if user_id in ADMIN_IDS:
        return True
    if user_id in load_blocked():
        return False
    return await is_member(user_id, context)


# ---------- KEYBOARDS ----------
def get_user_keyboard():
    buttons = [
        ["📱 𝘕𝘶𝘮𝘣𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱", "🪪 𝘈𝘥𝘩𝘢𝘢𝘳 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["💳 𝘗𝘢𝘯 𝘓𝘰𝘰𝘬𝘶𝘱", "🏦 𝘐𝘍𝘚𝘊 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["📍 𝘗𝘪𝘯 𝘊𝘰𝘥𝘦", "🌐 𝘐𝘗 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["📧 𝘌𝘮𝘢𝘪𝘭 𝘓𝘰𝘰𝘬𝘶𝘱", "☁️ 𝘞𝘦𝘢𝘵𝘩𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["🔢 𝘛𝘎 𝘵𝘰 𝘕𝘶𝘮", "👤 𝘔𝘺 𝘈𝘤𝘤𝘰𝘶𝘯𝘵"],
        ["🔗 𝘙𝘦𝘧𝘦𝘳𝘳𝘢𝘭", "💬 𝘏𝘦𝘭𝘱"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_admin_keyboard():
    buttons = [
        ["📱 𝘕𝘶𝘮𝘣𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱", "🪪 𝘈𝘥𝘩𝘢𝘢𝘳 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["💳 𝘗𝘢𝘯 𝘓𝘰𝘰𝘬𝘶𝘱", "🏦 𝘐𝘍𝘚𝘊 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["📍 𝘗𝘪𝘯 𝘊𝘰𝘥𝘦", "🌐 𝘐𝘗 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["📧 𝘌𝘮𝘢𝘪𝘭 𝘓𝘰𝘰𝘬𝘶𝘱", "☁️ 𝘞𝘦𝘢𝘵𝘩𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱"],
        ["🔢 𝘛𝘎 𝘵𝘰 𝘕𝘶𝘮", "👤 𝘔𝘺 𝘈𝘤𝘤𝘰𝘶𝘯𝘵"],
        ["🛠️ 𝘉𝘰𝘵 𝘔𝘢𝘯𝘢𝘨𝘦𝘮𝘦𝘯𝘵", "🔐 𝑴𝒐𝒅𝒆𝒓𝒂𝒕𝒐𝒓 𝑨𝒄𝒄𝒆𝒔𝒔"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_bot_management_menu():
    """Simplified menu – only 4 main buttons"""
    keyboard = [
        [InlineKeyboardButton("🎁 Give Coin", callback_data="admin_givecoin")],
        [InlineKeyboardButton("🎁 Give All Coin", callback_data="admin_giveallcoins")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📊 QueryScope", callback_data="admin_query_scope")],
        [InlineKeyboardButton("🤖 Bot Messenger", callback_data="admin_bot_messenger")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_moderator_menu():
    keyboard = [
        [InlineKeyboardButton("👥 𝑨𝒅𝒅 𝑪𝒐𝒍𝒍𝒂𝒃𝒐𝒓𝒂𝒕𝒐𝒓𝒔", callback_data="mod_add_collab")],
        [InlineKeyboardButton("🛡️ 𝑨𝒅𝒅 𝑴𝒐𝒅𝒆𝒓𝒂𝒕𝒐𝒓𝒔", callback_data="mod_add_mod")],
        [InlineKeyboardButton("🔓 𝑹𝒆𝒎𝒐𝒗𝒆 𝑨𝒄𝒄𝒆𝒔𝒔", callback_data="mod_remove")],
        [InlineKeyboardButton("📋 𝑳𝒊𝒔𝒕 𝑨𝒄𝒄𝒆𝒔𝒔", callback_data="mod_list")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]])

def get_bot_messenger_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Text Message", callback_data="msg_text")],
        [InlineKeyboardButton("🖼️ Photo", callback_data="msg_photo")],
        [InlineKeyboardButton("🎥 Video", callback_data="msg_video")],
        [InlineKeyboardButton("🎵 Audio", callback_data="msg_audio")],
        [InlineKeyboardButton("📄 Document", callback_data="msg_document")],
        [InlineKeyboardButton("🎞️ GIF", callback_data="msg_gif")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_keyboard(user_id=None):
    if user_id and user_id in ADMIN_IDS:
        return get_admin_keyboard()
    return get_user_keyboard()


# ---------- FORMAT FUNCTIONS ----------
def format_number_output(data):
    if not data: return "❌ No data found."
    if "error" in data: return f"❌ {data['error']}"
    total = data.get("total_records", 0)
    results = data.get("data", [])
    if total == 0 or not results:
        return "❌ No data found for this number."
    clean_results = []
    for record in results:
        clean_record = {k: v for k, v in record.items() if v is not None and v != "" and v != "N/A"}
        if clean_record:
            clean_results.append(clean_record)
    if not clean_results:
        return "❌ No data found for this number."
    clean_data = {
        "total_records": len(clean_results),
        "data": clean_results,
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**Number Lookup**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_aadhar_output(data):
    if not data: return "❌ No data found."
    if "error" in data: return f"❌ {data['error']}"
    total = data.get("total_records", 0)
    results = data.get("data", [])
    if total == 0 or not results:
        return "❌ No data found for this Aadhar."
    clean_data = {
        "total_records": len(results),
        "data": results,
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**Aadhar Lookup**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_tg_to_num_output(data):
    if not data: return "❌ No data found."
    if "error" in data: return f"❌ {data['error']}"
    tg_id = data.get("Telegram ID")
    phone = data.get("Phone")
    country = data.get("Country")
    country_code = data.get("Country Code")
    if not phone:
        return "❌ No data found for this Telegram ID."
    clean_data = {
        "Telegram ID": tg_id, "Phone": phone,
        "Country": country or "N/A", "Country Code": country_code or "N/A",
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**TG to Num Lookup**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_ifsc_output(data):
    if not data: return "❌ No data found."
    if "success" in data and data["success"] == False:
        return "❌ Invalid IFSC code or no data found."
    ifsc_data = data.get("data", data) if isinstance(data.get("data"), dict) else data
    clean_data = {k: v for k, v in ifsc_data.items() if v is not None and v != ""}
    if not clean_data: return "❌ No data found for this IFSC."
    clean_data["developer"] = "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    return "**IFSC Lookup**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_pincode_output(data):
    if not data or data.get("status") != "success":
        return "❌ No data found for this PIN code."
    clean_data = {
        "status": data.get("status"), "pincode": data.get("pincode", "N/A"),
        "total_records_found": data.get("total_records_found") or data.get("total_records") or 1,
        "delivery_status": data.get("delivery_status") or "N/A",
        "district": data.get("district") or "N/A",
        "division": data.get("division") or "N/A",
        "region": data.get("region") or "N/A",
        "state": data.get("state") or "N/A",
        "country": data.get("country") or "India",
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**PIN Code Search**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_weather_output(data):
    if not data or not data.get("success") or not data.get("data"):
        return "❌ No weather data found."
    w = data["data"]
    clean_data = {
        "city": w.get("city", {}).get("searched"),
        "temperature": w.get("current", {}).get("temperature", {}).get("actual_c"),
        "feels_like": w.get("current", {}).get("temperature", {}).get("feels_like_c"),
        "humidity": w.get("current", {}).get("atmosphere", {}).get("humidity_percent"),
        "wind": w.get("current", {}).get("wind", {}).get("speed_kmh"),
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**Weather Check**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_email_output(data):
    if not data: return "❌ No data found."
    results = data.get("results") or data.get("data") or []
    if not results: return "❌ No data found."
    return "**Email Info**\n```json\n" + json.dumps(results, indent=4, ensure_ascii=False) + "\n```"

def format_ip_output(data):
    if not data: return "❌ No data found."
    return "**IP Info**\n```json\n" + json.dumps(data, indent=4, ensure_ascii=False) + "\n```"

def format_pan_output(data):
    if not data: return "❌ No data found."
    results = data.get("data", [])
    if not results: return "❌ No data found."
    clean_data = {
        "total_records": len(results),
        "data": results,
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**PAN Info**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"


# ---------- QUERY LOGGING ----------
def log_query(user_id, name, query_type, query_input):
    log = load_query_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id, "name": name or "Unknown",
        "type": query_type, "query": query_input
    })
    if len(log) > MAX_LOG_ENTRIES:
        log = log[-MAX_LOG_ENTRIES:]
    save_query_log(log)


# ---------- PERFORM LOOKUP ----------
async def perform_lookup(update, context, lookup_type, input_text):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    name = user_data.get("name", "Unknown")

    special = has_special_access(user_id)

    if user_id not in ADMIN_IDS and not special:
        if user_data["coins"] < COST_PER_LOOKUP:
            await update.message.reply_text("❌ Not enough coins. Earn via referrals!")
            return
        user_data["coins"] -= COST_PER_LOOKUP

    if lookup_type == "number":
        digits = re.sub(r"\D", "", input_text)
        if len(digits) == 10:
            digits = "91" + digits
        elif len(digits) == 12 and digits.startswith("91"):
            pass
        else:
            await update.message.reply_text("❌ Invalid number. Please send 10-digit Indian mobile number.")
            return
        url = API_NUMBER.format(digits)
    elif lookup_type == "aadhar":
        url = API_AADHAR.format(input_text)
    elif lookup_type == "tg_to_num":
        url = API_TG_TO_NUM.format(input_text)
    elif lookup_type == "ifsc":
        url = API_IFSC.format(input_text)
    elif lookup_type == "pincode":
        url = API_PINCODE.format(input_text)
    elif lookup_type == "weather":
        url = API_WEATHER.format(input_text)
    elif lookup_type == "email":
        url = API_EMAIL.format(input_text)
    elif lookup_type == "ip":
        url = API_IP.format(input_text)
    elif lookup_type == "pan":
        url = API_PAN.format(input_text)
    else:
        await update.message.reply_text("Unknown lookup.")
        return

    try:
        response = requests.get(url, timeout=25)
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = {"_raw": response.text}
    except Exception:
        await update.message.reply_text("❌ No results found or service unavailable. Please try again later.")
        return

    if lookup_type == "number":
        result = format_number_output(data)
    elif lookup_type == "aadhar":
        result = format_aadhar_output(data)
    elif lookup_type == "tg_to_num":
        result = format_tg_to_num_output(data)
    elif lookup_type == "ifsc":
        result = format_ifsc_output(data)
    elif lookup_type == "pincode":
        result = format_pincode_output(data)
    elif lookup_type == "weather":
        result = format_weather_output(data)
    elif lookup_type == "email":
        result = format_email_output(data)
    elif lookup_type == "ip":
        result = format_ip_output(data)
    elif lookup_type == "pan":
        result = format_pan_output(data)
    else:
        result = "Unknown"

    timestamp = datetime.now().isoformat()
    entry = f"{lookup_type.upper()}: {input_text} ({timestamp})"
    if len(user_data["history"]) >= HISTORY_LIMIT:
        user_data["history"].pop(0)
    user_data["history"].append(entry)
    update_user_data(user_id, user_data)

    log_query(user_id, name, lookup_type, input_text)

    try:
        await update.message.reply_text(result, parse_mode="Markdown", reply_markup=get_keyboard(user_id))
    except Exception as e:
        print("Send error:", e)
        await update.message.reply_text("⚠️ Response delay. Please try again.")


# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        first_name = user.first_name or "User"

        get_user_data(user_id, first_name)

        ref = context.args[0] if context.args else None
        if ref and ref.isdigit() and int(ref) != user_id:
            data = load_data()
            uid = str(user_id)
            if uid not in data:
                data[uid] = {
                    "coins": COINS_ON_START, "referrals": 0,
                    "referred_by": int(ref), "history": [],
                    "name": first_name, "phone": None
                }
                save_data(data)
                if str(ref) in data:
                    data[str(ref)]["coins"] += REFERRAL_BONUS
                    data[str(ref)]["referrals"] += 1
                    save_data(data)

        if user_id in load_blocked():
            await update.message.reply_text("⛔ You are blocked from using this bot.")
            return

        if await is_verified(user_id, context):
            welcome = (
                f"ʜᴇʏ 👋 {first_name}\n\n"
                f"ʏᴏᴜʀ ɪᴅ ~ {user_id} ❤️\n\n"
                f"ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴀᴋᴀsʜ ᴏsɪɴᴛ ʙᴏᴛ 🧑‍💻\n"
                f"ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ."
            )
            await update.message.reply_text(welcome, reply_markup=get_keyboard(user_id))
            return

        keyboard = []
        keyboard.append([InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟣", url=CHANNELS[0]["link"])])
        keyboard.append([InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟤", url=CHANNELS[1]["link"])])
        keyboard.append([InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟥", url=CHANNELS[2]["link"])])
        keyboard.append([InlineKeyboardButton("👥 𝘫𝘰𝘪𝘯 𝘨𝘳𝘰𝘶𝘱", url=CHANNELS[3]["link"])])
        keyboard.append([InlineKeyboardButton("✅ Verify", callback_data="verify")])
        await update.message.reply_text(
            "Please join all channels & group to use this bot:\n\nAfter joining, press the Verify button.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print("Start error:", e)
        try:
            await update.message.reply_text("⚠️ Connection issue. Please try /start again.")
        except:
            pass


# ---------- RESTART & SETPHONE ----------
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await update.message.reply_text("🔄 Restarting...")
        os.execv(sys.executable, ['python'] + sys.argv)
    else:
        await update.message.reply_text("❌ Not authorized.")

async def setphone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Usage: `/setphone +917250385668`", parse_mode="Markdown")
        return
    phone = " ".join(context.args).strip()
    if len(re.sub(r'\D', '', phone)) < 10:
        await update.message.reply_text("❌ Invalid phone.")
        return
    data = load_data()
    uid = str(user_id)
    if uid in data:
        data[uid]["phone"] = phone
        save_data(data)
        await update.message.reply_text(f"✅ Phone set to: `{phone}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ /start first")


# ---------- VERIFY CALLBACK ----------
async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    user_id = query.from_user.id

    if user_id in load_blocked():
        await query.edit_message_text("⛔ You are blocked.")
        return

    try:
        if await is_member(user_id, context):
            await query.edit_message_text(
                "✅ Verification successful!\n\nNow use /start again to access the bot.",
                reply_markup=None
            )
        else:
            await query.edit_message_text(
                "❌ You haven't joined all channels & group yet.\nPlease join and press Verify again.",
                reply_markup=query.message.reply_markup
            )
    except Exception as e:
        print("Verify error:", e)


# ---------- BOT MANAGEMENT CALLBACKS ----------
async def bot_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.edit_message_text("⛔ You are not authorized.")
        return

    data = query.data

    if data == "admin_back":
        await query.edit_message_text("🔙 Back to main menu.\nType /start to return.", reply_markup=None)
        return
    elif data == "admin_close":
        await query.edit_message_text("❌ Menu closed. Type /start to reopen.", reply_markup=None)
        return
    elif data == "admin_bot_messenger":
        await query.edit_message_text("🤖 **Bot Messenger**\n\nSelect type:", reply_markup=get_bot_messenger_keyboard())
        return
    elif data == "admin_givecoin":
        context.user_data["admin_action"] = "givecoin"
        await query.edit_message_text("🎁 **Give Coin**\n\nSend: `USER_ID AMOUNT`", parse_mode="Markdown", reply_markup=get_back_keyboard())
        return
    elif data == "admin_giveallcoins":
        context.user_data["admin_action"] = "giveallcoins"
        await query.edit_message_text("🎁 **Give All Coin**\n\nSend amount (e.g., `10`)", parse_mode="Markdown", reply_markup=get_back_keyboard())
        return
    elif data == "admin_query_scope":
        clean_old_queries()
        log = load_query_log()
        if not log:
            msg = "📊 No activity in last 24 hours."
        else:
            recent = log[-20:][::-1]
            lines = []
            for entry in recent:
                lines.append(f"👤 {entry.get('name','?')} (ID: `{entry.get('user_id','?')}`)")
                lines.append(f"🔍 {entry.get('type','').upper()}: `{entry.get('query','')}`")
                lines.append("")
            msg = "📊 **QueryScope (Last 24h)**\n\n" + "\n".join(lines)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
        return
    elif data == "admin_stats":
        stats = load_data()
        total = len(stats)
        total_coins = sum(d.get("coins", 0) for d in stats.values())
        blocked = len(load_blocked())
        access = load_access()
        msg = (f"📊 **Bot Statistics**\n"
               f"👥 Total Users: {total}\n"
               f"🪙 Total Coins: {total_coins}\n"
               f"🚫 Blocked: {blocked}\n"
               f"👥 Collaborators: {len(access.get('collaborators', []))}\n"
               f"🛡️ Moderators: {len(access.get('moderators', []))}")
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
        return


# ---------- MODERATOR ACCESS CALLBACKS ----------
async def moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.edit_message_text("⛔ Not authorized.")
        return

    data = query.data

    if data == "mod_add_collab":
        context.user_data["admin_action"] = "add_collab"
        await query.edit_message_text("👥 **Add Collaborator**\n\nSend User ID for unlimited access.", reply_markup=get_back_keyboard())
        return
    elif data == "mod_add_mod":
        context.user_data["admin_action"] = "add_mod"
        await query.edit_message_text("🛡️ **Add Moderator**\n\nSend User ID for unlimited access.", reply_markup=get_back_keyboard())
        return
    elif data == "mod_remove":
        context.user_data["admin_action"] = "remove_access"
        await query.edit_message_text("🔓 **Remove Access**\n\nSend User ID to remove special access.", reply_markup=get_back_keyboard())
        return
    elif data == "mod_list":
        access = load_access()
        collabs = access.get("collaborators", [])
        mods = access.get("moderators", [])
        msg = "📋 **Special Access List**\n\n"
        msg += "👥 **Collaborators:**\n"
        msg += "\n".join([f"`{c}`" for c in collabs]) if collabs else "None"
        msg += "\n\n🛡️ **Moderators:**\n"
        msg += "\n".join([f"`{m}`" for m in mods]) if mods else "None"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
        return
    elif data == "admin_back":
        await query.edit_message_text("🔙 Back to main menu.", reply_markup=None)
        return


# ---------- BOT MESSENGER CALLBACKS ----------
async def messenger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.edit_message_text("⛔ Not authorized.")
        return

    data = query.data

    if data == "msg_text":
        context.user_data["admin_action"] = "msg_text"
        await query.edit_message_text("📝 **Send Text**\n\nType message:", reply_markup=get_back_keyboard())
    elif data == "msg_photo":
        context.user_data["admin_action"] = "msg_photo"
        await query.edit_message_text("🖼️ **Send Photo**", reply_markup=get_back_keyboard())
    elif data == "msg_video":
        context.user_data["admin_action"] = "msg_video"
        await query.edit_message_text("🎥 **Send Video**", reply_markup=get_back_keyboard())
    elif data == "msg_audio":
        context.user_data["admin_action"] = "msg_audio"
        await query.edit_message_text("🎵 **Send Audio**", reply_markup=get_back_keyboard())
    elif data == "msg_document":
        context.user_data["admin_action"] = "msg_document"
        await query.edit_message_text("📄 **Send Document**", reply_markup=get_back_keyboard())
    elif data == "msg_gif":
        context.user_data["admin_action"] = "msg_gif"
        await query.edit_message_text("🎞️ **Send GIF**", reply_markup=get_back_keyboard())
    elif data == "admin_back":
        await query.edit_message_text("🔙 Back to main menu.", reply_markup=None)


# ---------- HANDLE MESSAGES ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    if not await is_verified(user_id, context):
        keyboard = []
        keyboard.append([InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟣", url=CHANNELS[0]["link"])])
        keyboard.append([InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟤", url=CHANNELS[1]["link"])])
        keyboard.append([InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟥", url=CHANNELS[2]["link"])])
        keyboard.append([InlineKeyboardButton("👥 𝘫𝘰𝘪𝘯 𝘨𝘳𝘰𝘶𝘱", url=CHANNELS[3]["link"])])
        keyboard.append([InlineKeyboardButton("✅ Verify", callback_data="verify")])
        await update.message.reply_text(
            "⚠️ You must join all channels & group.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ADMIN ACTIONS
    if user_id in ADMIN_IDS and context.user_data.get("admin_action"):
        action = context.user_data["admin_action"]

        if action == "msg_text":
            if text:
                data = load_data()
                count = 0
                for uid in data:
                    try:
                        await context.bot.send_message(chat_id=int(uid), text=text)
                        count += 1
                    except: pass
                await update.message.reply_text(f"📝 Sent to {count} users.")
                context.user_data.pop("admin_action")
                return

        elif action == "givecoin":
            parts = text.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                target = int(parts[0]); amount = int(parts[1])
                data = load_data()
                if str(target) in data:
                    data[str(target)]["coins"] += amount
                    save_data(data)
                    await update.message.reply_text(f"✅ Added {amount} coins to `{target}`.", parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ User not found.")
            else:
                await update.message.reply_text("❌ Format: `USER_ID AMOUNT`", parse_mode="Markdown")
            context.user_data.pop("admin_action")
            return

        elif action == "giveallcoins":
            if text.isdigit():
                amount = int(text)
                data = load_data()
                count = 0
                for uid in data:
                    data[uid]["coins"] += amount
                    count += 1
                save_data(data)
                await update.message.reply_text(f"✅ Added {amount} coins to {count} users.")
            else:
                await update.message.reply_text("❌ Send a number.")
            context.user_data.pop("admin_action")
            return

        elif action == "add_collab":
            if text.isdigit():
                target = int(text)
                access = load_access()
                if target not in access["collaborators"]:
                    access["collaborators"].append(target)
                    if target in access["moderators"]:
                        access["moderators"].remove(target)
                    save_access(access)
                    await update.message.reply_text(f"✅ `{target}` added as **Collaborator**.", parse_mode="Markdown")
                else:
                    await update.message.reply_text("ℹ️ Already a Collaborator.")
            else:
                await update.message.reply_text("❌ Invalid ID.")
            context.user_data.pop("admin_action")
            return

        elif action == "add_mod":
            if text.isdigit():
                target = int(text)
                access = load_access()
                if target not in access["moderators"]:
                    access["moderators"].append(target)
                    if target in access["collaborators"]:
                        access["collaborators"].remove(target)
                    save_access(access)
                    await update.message.reply_text(f"✅ `{target}` added as **Moderator**.", parse_mode="Markdown")
                else:
                    await update.message.reply_text("ℹ️ Already a Moderator.")
            else:
                await update.message.reply_text("❌ Invalid ID.")
            context.user_data.pop("admin_action")
            return

        elif action == "remove_access":
            if text.isdigit():
                target = int(text)
                access = load_access()
                removed = False
                if target in access["collaborators"]:
                    access["collaborators"].remove(target); removed = True
                if target in access["moderators"]:
                    access["moderators"].remove(target); removed = True
                save_access(access)
                if removed:
                    await update.message.reply_text(f"🔓 Access removed from `{target}`.", parse_mode="Markdown")
                else:
                    await update.message.reply_text("ℹ️ No special access.")
            else:
                await update.message.reply_text("❌ Invalid ID.")
            context.user_data.pop("admin_action")
            return

    # HELP MENU
    if text == "💬 𝘏𝘦𝘭𝘱":
        help_msg = (
            "𝑵𝒆𝒆𝒅 𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒄𝒆?\n\n"
            "𝑭𝒐𝒓 𝒔𝒖𝒑𝒑𝒐𝒓𝒕, 𝒊𝒔𝒔𝒖𝒆𝒔 𝒐𝒓 𝒈𝒆𝒏𝒆𝒓𝒂𝒍 𝒊𝒏𝒒𝒖𝒊𝒓𝒊𝒆𝒔, 𝒑𝒍𝒆𝒂𝒔𝒆 𝒄𝒐𝒏𝒕𝒂𝒄𝒕 𝒕𝒉𝒆 𝒂𝒅𝒎𝒊𝒏.\n\n"
            f"👨‍💻 𝑨𝒅𝒎𝒊𝒏 ~ {ADMIN_USERNAME}"
        )
        await update.message.reply_text(help_msg)
        return

    # LOOKUP COMMANDS
    if text == "📱 𝘕𝘶𝘮𝘣𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("📞 Send 10-digit number (e.g., 7250385668):")
        context.user_data["lookup_type"] = "number"
    elif text == "🏦 𝘐𝘍𝘚𝘊 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("🏦 Send IFSC code:")
        context.user_data["lookup_type"] = "ifsc"
    elif text == "📍 𝘗𝘪𝘯 𝘊𝘰𝘥𝘦":
        await update.message.reply_text("📮 Send PIN code:")
        context.user_data["lookup_type"] = "pincode"
    elif text == "☁️ 𝘞𝘦𝘢𝘵𝘩𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("🌤️ Send city name:")
        context.user_data["lookup_type"] = "weather"
    elif text == "📧 𝘌𝘮𝘢𝘪𝘭 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("📧 Send email:")
        context.user_data["lookup_type"] = "email"
    elif text == "🪪 𝘈𝘥𝘩𝘢𝘢𝘳 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("🆔 Send 12-digit Aadhar:")
        context.user_data["lookup_type"] = "aadhar"
    elif text == "🌐 𝘐𝘗 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("🌐 Send IP address:")
        context.user_data["lookup_type"] = "ip"
    elif text == "💳 𝘗𝘢𝘯 𝘓𝘰𝘰𝘬𝘶𝘱":
        await update.message.reply_text("🆔 Send PAN number:")
        context.user_data["lookup_type"] = "pan"
    elif text == "🔢 𝘛𝘎 𝘵𝘰 𝘕𝘶𝘮":
        await update.message.reply_text("🔢 Send Telegram User ID:")
        context.user_data["lookup_type"] = "tg_to_num"
    elif text == "👤 𝘔𝘺 𝘈𝘤𝘤𝘰𝘶𝘯𝘵":
        user_data = get_user_data(user_id)
        account_data = {
            "𝙪𝙨𝙚𝙧 𝙞𝙙": str(user_id),
            "𝙣𝙖𝙢𝙚": user_data.get("name", "Unknown"),
            "𝙘𝙤𝙞𝙣𝙨": user_data.get("coins", 0),
            "𝙧𝙚𝙛𝙚𝙧𝙧𝙖𝙡𝙨": user_data.get("referrals", 0)
        }
        msg = "**👤 My Account**\n```json\n" + json.dumps(account_data, indent=2, ensure_ascii=False) + "\n```"
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif text == "🔗 𝘙𝘦𝘧𝘦𝘳𝘳𝘢𝘭":
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await update.message.reply_text(f"🔗 **Referral Link**\n\nEarn {REFERRAL_BONUS} coins per referral!\n\n{ref_link}")
    elif text == "🛠️ 𝘉𝘰𝘵 𝘔𝘢𝘯𝘢𝘨𝘦𝘮𝘦𝘯𝘵" and user_id in ADMIN_IDS:
        await update.message.reply_text("🛠️ Bot Management:", reply_markup=get_bot_management_menu())
    elif text == "🔐 𝑴𝒐𝒅𝒆𝒓𝒂𝒕𝒐𝒓 𝑨𝒄𝒄𝒆𝒔𝒔" and user_id in ADMIN_IDS:
        await update.message.reply_text("🔐 Moderator Access:", reply_markup=get_moderator_menu())
    else:
        if context.user_data.get("lookup_type"):
            lookup_type = context.user_data.pop("lookup_type")
            await perform_lookup(update, context, lookup_type, text)
        else:
            await update.message.reply_text("🤖 Use the buttons or /start.")


# ---------- MEDIA HANDLERS ----------
async def handle_messenger_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_photo":
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        data = load_data(); count = 0
        for uid in data:
            try:
                await context.bot.send_photo(chat_id=int(uid), photo=photo, caption=caption)
                count += 1
            except: pass
        await update.message.reply_text(f"🖼️ Sent to {count} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_video":
        video = update.message.video.file_id
        caption = update.message.caption or ""
        data = load_data(); count = 0
        for uid in data:
            try:
                await context.bot.send_video(chat_id=int(uid), video=video, caption=caption)
                count += 1
            except: pass
        await update.message.reply_text(f"🎥 Sent to {count} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_audio":
        audio = update.message.audio.file_id
        caption = update.message.caption or ""
        data = load_data(); count = 0
        for uid in data:
            try:
                await context.bot.send_audio(chat_id=int(uid), audio=audio, caption=caption)
                count += 1
            except: pass
        await update.message.reply_text(f"🎵 Sent to {count} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_document":
        doc = update.message.document.file_id
        caption = update.message.caption or ""
        data = load_data(); count = 0
        for uid in data:
            try:
                await context.bot.send_document(chat_id=int(uid), document=doc, caption=caption)
                count += 1
            except: pass
        await update.message.reply_text(f"📄 Sent to {count} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_gif":
        if update.message.animation:
            gif = update.message.animation.file_id
            caption = update.message.caption or ""
            data = load_data(); count = 0
            for uid in data:
                try:
                    await context.bot.send_animation(chat_id=int(uid), animation=gif, caption=caption)
                    count += 1
                except: pass
            await update.message.reply_text(f"🎞️ Sent to {count} users.")
            context.user_data.pop("admin_action")


# ---------- FLASK ----------
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!", 200

@app.route('/ping')
def ping():
    return "Pong!", 200

def run_web():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))


# ---------- MAIN ----------
def main():
    threading.Thread(target=auto_cleaner, daemon=True).start()
    threading.Thread(target=run_web, daemon=True).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("restart", restart))
    application.add_handler(CommandHandler("setphone", setphone))

    # IMPORTANT: Specific patterns first
    application.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    application.add_handler(CallbackQueryHandler(moderator_callback, pattern="^mod_"))
    application.add_handler(CallbackQueryHandler(messenger_callback, pattern="^msg_"))
    application.add_handler(CallbackQueryHandler(bot_management_callback, pattern="^admin_"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    admin_id = ADMIN_IDS[0] if ADMIN_IDS else None
    if admin_id:
        application.add_handler(MessageHandler(filters.PHOTO & filters.User(admin_id), handle_messenger_photo))
        application.add_handler(MessageHandler(filters.VIDEO & filters.User(admin_id), handle_messenger_video))
        application.add_handler(MessageHandler(filters.AUDIO & filters.User(admin_id), handle_messenger_audio))
        application.add_handler(MessageHandler(filters.Document.ALL & filters.User(admin_id), handle_messenger_document))
        application.add_handler(MessageHandler(filters.ANIMATION & filters.User(admin_id), handle_messenger_gif))

    application.run_polling(poll_interval=1.0, timeout=30)

if __name__ == "__main__":
    main()
