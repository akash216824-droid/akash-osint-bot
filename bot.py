import json
import os
import re
import sys
import time
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8979291976").split(",")]

# ---------- CHANNELS (सिर्फ 3 public channels) ----------
CHANNELS = [
    {"name": "Channel 1", "username": "@wftis_ak4sh", "link": "https://t.me/wftis_ak4sh"},
    {"name": "Channel 2", "username": "@Err9r403", "link": "https://t.me/Err9r403"},
    {"name": "Channel 3", "username": "@AkashOSINT", "link": "https://t.me/AkashOSINT"},
]

# ---------- GROUP (optional – button में दिखेगा, verify नहीं) ----------
GROUP_LINK = "https://t.me/+oRfAbV_UhstmZDdh"

# ---------- APIs ----------
API_NUMBER = "https://akash-number-lookup.vercel.app/info?key=DEMO&query={}"
API_IFSC = "https://vercei-kappa.vercel.app/ifsc?code={}"
API_PINCODE = "https://nitin-apis-update-birthday-spacial.vercel.app/api?type=pincode&search={}"
API_WEATHER = "https://nitin-wather-check-api.vercel.app/api?type=weather&search={}"
API_EMAIL = "https://travelers-creature-sarah-rogers.trycloudflare.com/search?q={}"
API_AADHAR = "https://adityaxapi-jrys.onrender.com/api/aadhar?key=BIRTHDAY&num={}"
API_IP = "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query={}"
API_PAN = "https://adityaxapi-jrys.onrender.com/api/pan?key=BIRTHDAY&pan={}"
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

def save_blocked(s):
    with open(BLOCK_FILE, "w") as f:
        json.dump(list(s), f)

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

def get_user_data(uid, name=None):
    data = load_data()
    k = str(uid)
    if k not in data:
        data[k] = {
            "coins": COINS_ON_START, "referrals": 0,
            "referred_by": None, "history": [],
            "name": name, "phone": None
        }
        save_data(data)
    elif name and not data[k].get("name"):
        data[k]["name"] = name
        save_data(data)
    return data[k]

def update_user_data(uid, nd):
    data = load_data()
    data[str(uid)] = nd
    save_data(data)


# ---------- AUTO-DELETE 24h ----------
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
    if changed:
        save_data(data)

def clean_old_queries():
    log = load_query_log()
    cutoff = datetime.now() - timedelta(hours=HISTORY_TTL_HOURS)
    new_log = []
    for e in log:
        try:
            ts = datetime.fromisoformat(e.get("timestamp", ""))
            if ts >= cutoff:
                new_log.append(e)
        except:
            new_log.append(e)
    if len(new_log) != len(log):
        save_query_log(new_log)

def auto_cleaner():
    while True:
        try:
            clean_old_history()
            clean_old_queries()
        except:
            pass
        time.sleep(600)


# ---------- VERIFICATION (सिर्फ 3 public channels) ----------
async def check_verification(user_id, context):
    """3 public channels check. Bot उन channels में admin होना चाहिए."""
    for ch in CHANNELS:
        try:
            member = await context.bot.get_chat_member(
                chat_id=ch["username"], user_id=user_id
            )
            status = getattr(member, "status", None)
            if status not in ["member", "administrator", "creator"]:
                return False, ch["name"]
        except Exception as e:
            err = str(e).lower()
            print(f"Verify error for {ch['username']}: {e}")
            # अगर bot channel में नहीं है या admin नहीं है – skip नहीं करें, false दें
            if "chat not found" in err or "not enough rights" in err or "bot is not a member" in err:
                return False, f"{ch['name']} (Bot not admin)"
            # user channel में नहीं है
            if "user not found" in err or "participant" in err:
                return False, ch["name"]
            # बाकी errors – safe तरीके से false दें
            return False, ch["name"]
    return True, None

async def is_verified(user_id, context):
    if user_id in ADMIN_IDS:
        return True
    if user_id in load_blocked():
        return False
    ok, _ = await check_verification(user_id, context)
    return ok


def get_verify_keyboard():
    kb = [
        [InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟣", url=CHANNELS[0]["link"])],
        [InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟤", url=CHANNELS[1]["link"])],
        [InlineKeyboardButton("📢 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝟥", url=CHANNELS[2]["link"])],
        [InlineKeyboardButton("👥 𝘫𝘰𝘪𝘯 𝘨𝘳𝘰𝘶𝘱", url=GROUP_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify")]
    ]
    return InlineKeyboardMarkup(kb)


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
    kb = [
        [InlineKeyboardButton("🎁 Give Coin", callback_data="admin_givecoin")],
        [InlineKeyboardButton("🎁 Give All Users Coin", callback_data="admin_giveallcoins")],
        [InlineKeyboardButton("🤖 Bot Messenger", callback_data="admin_bot_messenger")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📊 QueryScope", callback_data="admin_query_scope")],
        [InlineKeyboardButton("🚫 Block User", callback_data="admin_block")],
        [InlineKeyboardButton("✅ Unblock User", callback_data="admin_unblock")],
        [InlineKeyboardButton("👥 All Users", callback_data="admin_all_users")],
        [InlineKeyboardButton("🚫 Blocked Users", callback_data="admin_blocked_users")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(kb)

def get_moderator_menu():
    kb = [
        [InlineKeyboardButton("👥 𝑨𝒅𝒅 𝑪𝒐𝒍𝒍𝒂𝒃𝒐𝒓𝒂𝒕𝒐𝒓𝒔", callback_data="mod_add_collab")],
        [InlineKeyboardButton("🛡️ 𝑨𝒅𝒅 𝑴𝒐𝒅𝒆𝒓𝒂𝒕𝒐𝒓𝒔", callback_data="mod_add_mod")],
        [InlineKeyboardButton("🔓 𝑹𝒆𝒎𝒐𝒗𝒆 𝑨𝒄𝒄𝒆𝒔𝒔", callback_data="mod_remove")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(kb)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]])

def get_bot_messenger_keyboard():
    kb = [
        [InlineKeyboardButton("📝 Text Message", callback_data="msg_text")],
        [InlineKeyboardButton("🖼️ Photo", callback_data="msg_photo")],
        [InlineKeyboardButton("🎥 Video", callback_data="msg_video")],
        [InlineKeyboardButton("🎵 Audio/Song", callback_data="msg_audio")],
        [InlineKeyboardButton("📄 Document", callback_data="msg_document")],
        [InlineKeyboardButton("🎞️ GIF", callback_data="msg_gif")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(kb)

def get_keyboard(user_id=None):
    if user_id and user_id in ADMIN_IDS:
        return get_admin_keyboard()
    return get_user_keyboard()


# ---------- FORMAT ----------
def format_number_output(data):
    if not data: return "❌ No data found."
    if "error" in data: return f"❌ {data['error']}"
    total = data.get("total_records", 0)
    results = data.get("data", [])
    if total == 0 or not results:
        return "❌ No data found for this number."
    clean_results = []
    for record in results:
        clean_record = {}
        for k, v in record.items():
            if v is not None and v != "" and v != "N/A":
                clean_record[k] = v
        if "email" not in clean_record:
            clean_record["email"] = record.get("email") or record.get("Email") or None
        if clean_record:
            clean_results.append(clean_record)
    if not clean_results:
        return "❌ No data found for this number."
    clean_data = {"total_records": len(clean_results), "data": clean_results,
                  "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"}
    return "**Number Lookup**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_aadhar_output(data):
    if not data:
        return "❌ No data found."

    if "error" in data:
        return f"❌ {data['error']}"

    # New API structure
    count = data.get("count", 0)
    results = data.get("data", [])

    if count == 0 or not results:
        return "❌ No data found for this Aadhar."

    # Clean records – सिर्फ जरूरी fields
    clean_results = []
    for record in results:
        name = record.get("name")
        phone = record.get("phoneNumber")
        other = record.get("otherNumber")
        address = record.get("address")
        father = record.get("fathersName")
        aadhar = record.get("aadharNumber")

        # Skip अगर name खाली है और phone भी नहीं
        if not name and not phone:
            continue

        clean_record = {}
        if name:
            clean_record["name"] = name
        if father:
            clean_record["fathersName"] = father
        if phone:
            # Format with +91
            digits = re.sub(r"\D", "", str(phone))
            if len(digits) == 10:
                clean_record["phoneNumber"] = "+91" + digits
            elif digits.startswith("91") and len(digits) == 12:
                clean_record["phoneNumber"] = "+" + digits
            else:
                clean_record["phoneNumber"] = "+" + digits

        if other:
            o_digits = re.sub(r"\D", "", str(other))
            if len(o_digits) == 10:
                clean_record["otherNumber"] = "+91" + o_digits
            elif o_digits.startswith("91") and len(o_digits) == 12:
                clean_record["otherNumber"] = "+" + o_digits
            else:
                clean_record["otherNumber"] = "+" + o_digits

        if address:
            clean_record["address"] = address.strip()
        if aadhar:
            clean_record["aadharNumber"] = aadhar
        clean_record["source"] = "inddata"

        if clean_record:
            clean_results.append(clean_record)

    if not clean_results:
        return "❌ No data found for this Aadhar."

    clean_data = {
        "total_records": len(clean_results),
        "data": clean_results,
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }

    out = "**Aadhar Lookup**\n```json\n"
    out += json.dumps(clean_data, indent=4, ensure_ascii=False)
    out += "\n```"
    return out
def format_tg_to_num_output(data):
    if not data: return "❌ No data found."
    if "error" in data: return f"❌ {data['error']}"
    tg_id = data.get("Telegram ID"); phone = data.get("Phone")
    country = data.get("Country"); cc = data.get("Country Code")
    if not phone: return "❌ No data found."
    clean_data = {"Telegram ID": tg_id, "Phone": phone, "Country": country or "N/A",
                  "Country Code": cc or "N/A", "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"}
    return "**TG to Num**\n```json\n" + json.dumps(clean_data, indent=4, ensure_ascii=False) + "\n```"

def format_ifsc_output(data):
    if not data: return "❌ No data found."
    if "success" in data and data["success"] == False: return "❌ Invalid IFSC."
    ifsc_data = data.get("data", data) if isinstance(data.get("data"), dict) else data
    clean = {k: v for k, v in ifsc_data.items() if v is not None and v != ""}
    if not clean: return "❌ No data found."
    clean["developer"] = "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    return "**IFSC**\n```json\n" + json.dumps(clean, indent=4, ensure_ascii=False) + "\n```"

def format_pincode_output(data):
    if not data or data.get("status") != "success":
        return "❌ No data found."
    clean = {
        "status": data.get("status"), "pincode": data.get("pincode", "N/A"),
        "total_records_found": data.get("total_records_found") or 1,
        "delivery_status": data.get("delivery_status") or "N/A",
        "district": data.get("district") or "N/A", "division": data.get("division") or "N/A",
        "region": data.get("region") or "N/A", "state": data.get("state") or "N/A",
        "country": data.get("country") or "India",
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**PIN Code**\n```json\n" + json.dumps(clean, indent=4, ensure_ascii=False) + "\n```"

def format_weather_output(data):
    if not data or not data.get("success") or not data.get("data"):
        return "❌ No weather data."
    w = data["data"]
    clean = {
        "city": w.get("city", {}).get("searched"),
        "temperature": w.get("current", {}).get("temperature", {}).get("actual_c"),
        "feels_like": w.get("current", {}).get("temperature", {}).get("feels_like_c"),
        "humidity": w.get("current", {}).get("atmosphere", {}).get("humidity_percent"),
        "wind": w.get("current", {}).get("wind", {}).get("speed_kmh"),
        "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"
    }
    return "**Weather**\n```json\n" + json.dumps(clean, indent=4, ensure_ascii=False) + "\n```"

def format_email_output(data):
    if not data: return "❌ No data found."
    results = data.get("results") or data.get("data") or []
    if not results: return "❌ No data found."
    return "**Email**\n```json\n" + json.dumps(results, indent=4, ensure_ascii=False) + "\n```"

def format_ip_output(data):
    if not data: return "❌ No data found."
    return "**IP**\n```json\n" + json.dumps(data, indent=4, ensure_ascii=False) + "\n```"

def format_pan_output(data):
    if not data: return "❌ No data found."
    results = data.get("data", [])
    if not results: return "❌ No data found."
    clean = {"total_records": len(results), "data": results, "developer": "𐙚 𓆩𝘼𝙠𝙖𝙨𝗵 𝙊𝙨𝙞𝙣𝙩𓆪𓂃🧑💻🎀⃤"}
    return "**PAN**\n```json\n" + json.dumps(clean, indent=4, ensure_ascii=False) + "\n```"


def log_query(user_id, name, qtype, qinput):
    log = load_query_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id, "name": name or "Unknown",
        "type": qtype, "query": qinput
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
            await update.message.reply_text("❌ Invalid number.")
            return
        url = API_NUMBER.format(digits)
    elif lookup_type == "aadhar": url = API_AADHAR.format(input_text)
    elif lookup_type == "tg_to_num": url = API_TG_TO_NUM.format(input_text)
    elif lookup_type == "ifsc": url = API_IFSC.format(input_text)
    elif lookup_type == "pincode": url = API_PINCODE.format(input_text)
    elif lookup_type == "weather": url = API_WEATHER.format(input_text)
    elif lookup_type == "email": url = API_EMAIL.format(input_text)
    elif lookup_type == "ip": url = API_IP.format(input_text)
    elif lookup_type == "pan": url = API_PAN.format(input_text)
    else:
        await update.message.reply_text("Unknown lookup.")
        return

    try:
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        try: data = r.json()
        except: data = {"_raw": r.text}
    except Exception:
        await update.message.reply_text("❌ No results or service unavailable.")
        return

    if lookup_type == "number": result = format_number_output(data)
    elif lookup_type == "aadhar": result = format_aadhar_output(data)
    elif lookup_type == "tg_to_num": result = format_tg_to_num_output(data)
    elif lookup_type == "ifsc": result = format_ifsc_output(data)
    elif lookup_type == "pincode": result = format_pincode_output(data)
    elif lookup_type == "weather": result = format_weather_output(data)
    elif lookup_type == "email": result = format_email_output(data)
    elif lookup_type == "ip": result = format_ip_output(data)
    elif lookup_type == "pan": result = format_pan_output(data)
    else: result = "Unknown"

    ts = datetime.now().isoformat()
    entry = f"{lookup_type.upper()}: {input_text} ({ts})"
    if len(user_data["history"]) >= HISTORY_LIMIT:
        user_data["history"].pop(0)
    user_data["history"].append(entry)
    update_user_data(user_id, user_data)
    log_query(user_id, name, lookup_type, input_text)

    await update.message.reply_text(result, parse_mode="Markdown", reply_markup=get_keyboard(user_id))


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
            k = str(user_id)
            if k not in data:
                data[k] = {"coins": COINS_ON_START, "referrals": 0,
                           "referred_by": int(ref), "history": [],
                           "name": first_name, "phone": None}
                save_data(data)
                if str(ref) in data:
                    data[str(ref)]["coins"] += REFERRAL_BONUS
                    data[str(ref)]["referrals"] += 1
                    save_data(data)

        if user_id in load_blocked():
            await update.message.reply_text("⛔ You are blocked.")
            return

        ok, _ = await check_verification(user_id, context)
        if ok:
            welcome = (
                f"ʜᴇʏ 👋 {first_name}\n\n"
                f"ʏᴏᴜʀ ɪᴅ ~ {user_id} ❤️\n\n"
                f"ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴀᴋᴀsʜ ᴏsɪɴᴛ ʙᴏᴛ 🧑‍💻\n"
                f"ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ."
            )
            await update.message.reply_text(welcome, reply_markup=get_keyboard(user_id))
        else:
            await update.message.reply_text(
                "⚠️ Please join the 3 channels to use this bot.\n\n"
                "After joining, press ✅ Verify.",
                reply_markup=get_verify_keyboard()
            )
    except Exception as e:
        print("Start error:", e)


# ---------- VERIFY CALLBACK ----------
async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer("Checking...", show_alert=False)
        user_id = query.from_user.id

        if user_id in load_blocked():
            await query.edit_message_text("⛔ You are blocked.")
            return

        ok, missing = await check_verification(user_id, context)
        if ok:
            await query.edit_message_text(
                "✅ Verification successful!\n\n"
                "Now use /start to access the bot.",
                reply_markup=None
            )
        else:
            await query.edit_message_text(
                f"❌ You haven't joined **{missing}** yet.\n\n"
                "Please join all 3 channels and press ✅ Verify again.",
                parse_mode="Markdown",
                reply_markup=get_verify_keyboard()
            )
    except Exception as e:
        print("Verify error:", e)


# ---------- ADMIN CALLBACKS ----------
async def bot_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if uid not in ADMIN_IDS:
        await q.edit_message_text("⛔ Not authorized.")
        return
    d = q.data

    if d == "admin_back":
        await q.edit_message_text("🔙 Main menu. Type /start.", reply_markup=None)
    elif d == "admin_close":
        await q.edit_message_text("❌ Closed.", reply_markup=None)
    elif d == "admin_bot_messenger":
        await q.edit_message_text("🤖 **Bot Messenger**\n\nSelect type:", reply_markup=get_bot_messenger_keyboard())
    elif d == "admin_givecoin":
        context.user_data["admin_action"] = "givecoin"
        await q.edit_message_text("🎁 Send: `USER_ID AMOUNT`", parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif d == "admin_giveallcoins":
        context.user_data["admin_action"] = "giveallcoins"
        await q.edit_message_text("🎁 Send amount:", reply_markup=get_back_keyboard())
    elif d == "admin_query_scope":
        clean_old_queries()
        log = load_query_log()
        if not log:
            msg = "📊 No activity (24h)."
        else:
            lines = []
            for e in log[-20:][::-1]:
                lines.append(f"👤 {e.get('name','?')} (`{e.get('user_id','?')}`)")
                lines.append(f"🔍 {e.get('type','').upper()}: `{e.get('query','')}`")
                lines.append("")
            msg = "📊 **QueryScope (24h)**\n\n" + "\n".join(lines)
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif d == "admin_stats":
        stats = load_data()
        total = len(stats)
        coins = sum(v.get("coins", 0) for v in stats.values())
        acc = load_access()
        msg = (f"📊 **Stats**\n👥 Users: {total}\n🪙 Coins: {coins}\n"
               f"🚫 Blocked: {len(load_blocked())}\n"
               f"👥 Collaborators: {len(acc.get('collaborators',[]))}\n"
               f"🛡️ Moderators: {len(acc.get('moderators',[]))}")
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif d == "admin_block":
        context.user_data["admin_action"] = "block"
        await q.edit_message_text("🚫 Send User ID:", reply_markup=get_back_keyboard())
    elif d == "admin_unblock":
        context.user_data["admin_action"] = "unblock"
        await q.edit_message_text("✅ Send User ID:", reply_markup=get_back_keyboard())
    elif d == "admin_blocked_users":
        bs = load_blocked()
        msg = "🚫 Blocked:\n" + "\n".join(str(x) for x in bs) if bs else "✅ No blocked users."
        await q.edit_message_text(msg, reply_markup=get_back_keyboard())
    elif d == "admin_all_users":
        alld = load_data()
        if not alld:
            msg = "No users."
        else:
            lines = [f"`{k}` {v.get('name','?')}" for k, v in alld.items()]
            msg = "👥 **All Users**\n\n" + "\n".join(lines)
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())


async def moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id not in ADMIN_IDS:
        await q.edit_message_text("⛔ Not authorized.")
        return
    d = q.data
    if d == "mod_add_collab":
        context.user_data["admin_action"] = "add_collab"
        await q.edit_message_text("👥 Send User ID:", reply_markup=get_back_keyboard())
    elif d == "mod_add_mod":
        context.user_data["admin_action"] = "add_mod"
        await q.edit_message_text("🛡️ Send User ID:", reply_markup=get_back_keyboard())
    elif d == "mod_remove":
        context.user_data["admin_action"] = "remove_access"
        await q.edit_message_text("🔓 Send User ID:", reply_markup=get_back_keyboard())
    elif d == "admin_back":
        await q.edit_message_text("🔙 Main menu.", reply_markup=None)


async def messenger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id not in ADMIN_IDS:
        await q.edit_message_text("⛔ Not authorized.")
        return
    d = q.data
    if d == "msg_text":
        context.user_data["admin_action"] = "msg_text"
        await q.edit_message_text("📝 Type message:", reply_markup=get_back_keyboard())
    elif d == "msg_photo":
        context.user_data["admin_action"] = "msg_photo"
        await q.edit_message_text("🖼️ Send photo:", reply_markup=get_back_keyboard())
    elif d == "msg_video":
        context.user_data["admin_action"] = "msg_video"
        await q.edit_message_text("🎥 Send video:", reply_markup=get_back_keyboard())
    elif d == "msg_audio":
        context.user_data["admin_action"] = "msg_audio"
        await q.edit_message_text("🎵 Send audio:", reply_markup=get_back_keyboard())
    elif d == "msg_document":
        context.user_data["admin_action"] = "msg_document"
        await q.edit_message_text("📄 Send document:", reply_markup=get_back_keyboard())
    elif d == "msg_gif":
        context.user_data["admin_action"] = "msg_gif"
        await q.edit_message_text("🎞️ Send GIF:", reply_markup=get_back_keyboard())
    elif d == "admin_back":
        await q.edit_message_text("🔙 Main menu.", reply_markup=None)


# ---------- HANDLE MESSAGES ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip() if update.message.text else ""

        ok, _ = await check_verification(user_id, context)
        if not ok:
            await update.message.reply_text(
                "⚠️ You must join all 3 channels to use this bot.\n\n"
                "After joining, press ✅ Verify.",
                reply_markup=get_verify_keyboard()
            )
            return

        if user_id in ADMIN_IDS and context.user_data.get("admin_action"):
            a = context.user_data["admin_action"]

            if a == "msg_text":
                if text:
                    data = load_data(); c = 0
                    for uid in data:
                        try:
                            await context.bot.send_message(chat_id=int(uid), text=text)
                            c += 1
                        except: pass
                    await update.message.reply_text(f"📝 Sent to {c} users.")
                    context.user_data.pop("admin_action")
                return

            if a == "givecoin":
                parts = text.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    t, amt = int(parts[0]), int(parts[1])
                    data = load_data()
                    if str(t) in data:
                        data[str(t)]["coins"] += amt
                        save_data(data)
                        await update.message.reply_text(f"✅ Added {amt} coins to `{t}`.", parse_mode="Markdown")
                    else:
                        await update.message.reply_text("❌ User not found.")
                else:
                    await update.message.reply_text("❌ Format: `USER_ID AMOUNT`", parse_mode="Markdown")
                context.user_data.pop("admin_action")
                return

            if a == "giveallcoins":
                if text.isdigit():
                    amt = int(text); data = load_data(); c = 0
                    for uid in data:
                        data[uid]["coins"] += amt; c += 1
                    save_data(data)
                    await update.message.reply_text(f"✅ Added {amt} coins to {c} users.")
                else:
                    await update.message.reply_text("❌ Send a number.")
                context.user_data.pop("admin_action")
                return

            if a == "block":
                if text.isdigit():
                    b = load_blocked(); b.add(int(text)); save_blocked(b)
                    await update.message.reply_text(f"🚫 Blocked {text}.")
                else:
                    await update.message.reply_text("❌ Invalid ID.")
                context.user_data.pop("admin_action")
                return

            if a == "unblock":
                if text.isdigit():
                    b = load_blocked(); b.discard(int(text)); save_blocked(b)
                    await update.message.reply_text(f"✅ Unblocked {text}.")
                else:
                    await update.message.reply_text("❌ Invalid ID.")
                context.user_data.pop("admin_action")
                return

            if a == "add_collab":
                if text.isdigit():
                    t = int(text); acc = load_access()
                    if t not in acc["collaborators"]:
                        acc["collaborators"].append(t)
                        if t in acc["moderators"]: acc["moderators"].remove(t)
                        save_access(acc)
                        await update.message.reply_text(f"✅ `{t}` is now Collaborator.", parse_mode="Markdown")
                    else:
                        await update.message.reply_text("ℹ️ Already Collaborator.")
                else:
                    await update.message.reply_text("❌ Invalid ID.")
                context.user_data.pop("admin_action")
                return

            if a == "add_mod":
                if text.isdigit():
                    t = int(text); acc = load_access()
                    if t not in acc["moderators"]:
                        acc["moderators"].append(t)
                        if t in acc["collaborators"]: acc["collaborators"].remove(t)
                        save_access(acc)
                        await update.message.reply_text(f"✅ `{t}` is now Moderator.", parse_mode="Markdown")
                    else:
                        await update.message.reply_text("ℹ️ Already Moderator.")
                else:
                    await update.message.reply_text("❌ Invalid ID.")
                context.user_data.pop("admin_action")
                return

            if a == "remove_access":
                if text.isdigit():
                    t = int(text); acc = load_access(); r = False
                    if t in acc["collaborators"]: acc["collaborators"].remove(t); r = True
                    if t in acc["moderators"]: acc["moderators"].remove(t); r = True
                    save_access(acc)
                    await update.message.reply_text(f"🔓 Removed access from `{t}`." if r else "ℹ️ No access.", parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ Invalid ID.")
                context.user_data.pop("admin_action")
                return

        if text == "💬 𝘏𝘦𝘭𝘱":
            await update.message.reply_text(
                "𝑵𝒆𝒆𝒅 𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒄𝒆?\n\n"
                "𝑭𝒐𝒓 𝒔𝒖𝒑𝒑𝒐𝒓𝒕, 𝒊𝒔𝒔𝒖𝒆𝒔 𝒐𝒓 𝒈𝒆𝒏𝒆𝒓𝒂𝒍 𝒊𝒏𝒒𝒖𝒊𝒓𝒊𝒆𝒔, 𝒑𝒍𝒆𝒂𝒔𝒆 𝒄𝒐𝒏𝒕𝒂𝒄𝒕 𝒕𝒉𝒆 𝒂𝒅𝒎𝒊𝒏.\n\n"
                f"👨‍💻 𝑨𝒅𝒎𝒊𝒏 ~ {ADMIN_USERNAME}"
            )
            return

        if text == "📱 𝘕𝘶𝘮𝘣𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("📞 Send 10-digit number:")
            context.user_data["lookup_type"] = "number"
        elif text == "🏦 𝘐𝘍𝘚𝘊 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("🏦 Send IFSC:")
            context.user_data["lookup_type"] = "ifsc"
        elif text == "📍 𝘗𝘪𝘯 𝘊𝘰𝘥𝘦":
            await update.message.reply_text("📮 Send PIN code:")
            context.user_data["lookup_type"] = "pincode"
        elif text == "☁️ 𝘞𝘦𝘢𝘵𝘩𝘦𝘳 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("🌤️ Send city:")
            context.user_data["lookup_type"] = "weather"
        elif text == "📧 𝘌𝘮𝘢𝘪𝘭 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("📧 Send email:")
            context.user_data["lookup_type"] = "email"
        elif text == "🪪 𝘈𝘥𝘩𝘢𝘢𝘳 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("🆔 Send 12-digit Aadhar:")
            context.user_data["lookup_type"] = "aadhar"
        elif text == "🌐 𝘐𝘗 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("🌐 Send IP:")
            context.user_data["lookup_type"] = "ip"
        elif text == "💳 𝘗𝘢𝘯 𝘓𝘰𝘰𝘬𝘶𝘱":
            await update.message.reply_text("🆔 Send PAN:")
            context.user_data["lookup_type"] = "pan"
        elif text == "🔢 𝘛𝘎 𝘵𝘰 𝘕𝘶𝘮":
            await update.message.reply_text("🔢 Send Telegram ID:")
            context.user_data["lookup_type"] = "tg_to_num"
        elif text == "👤 𝘔𝘺 𝘈𝘤𝘤𝘰𝘶𝘯𝘵":
            ud = get_user_data(user_id)
            msg = (
                f"👤 **My Account**\n\n"
                f"🆔 User ID: `{user_id}`\n"
                f"👤 Name: {ud.get('name', 'Unknown')}\n"
                f"🪙 Coins: {ud.get('coins', 0)}\n"
                f"👥 Referrals: {ud.get('referrals', 0)}"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        elif text == "🔗 𝘙𝘦𝘧𝘦𝘳𝘳𝘢𝘭":
            ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
            await update.message.reply_text(f"🔗 **Referral Link**\n\nEarn {REFERRAL_BONUS} coin per referral!\n\n{ref_link}")
        elif text == "🛠️ 𝘉𝘰𝘵 𝘔𝘢𝘯𝘢𝘨𝘦𝘮𝘦𝘯𝘵" and user_id in ADMIN_IDS:
            await update.message.reply_text("🛠️ Bot Management:", reply_markup=get_bot_management_menu())
        elif text == "🔐 𝑴𝒐𝒅𝒆𝒓𝒂𝒕𝒐𝒓 𝑨𝒄𝒄𝒆𝒔𝒔" and user_id in ADMIN_IDS:
            await update.message.reply_text("🔐 Moderator Access:", reply_markup=get_moderator_menu())
        else:
            if context.user_data.get("lookup_type"):
                lt = context.user_data.pop("lookup_type")
                await perform_lookup(update, context, lt, text)
            else:
                await update.message.reply_text("🤖 Use the buttons or /start.")
    except Exception as e:
        print("Handle error:", e)


# ---------- MEDIA ----------
async def handle_messenger_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_photo":
        photo = update.message.photo[-1].file_id
        cap = update.message.caption or ""
        data = load_data(); c = 0
        for uid in data:
            try:
                await context.bot.send_photo(chat_id=int(uid), photo=photo, caption=cap)
                c += 1
            except: pass
        await update.message.reply_text(f"🖼️ Sent to {c} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_video":
        v = update.message.video.file_id
        cap = update.message.caption or ""
        data = load_data(); c = 0
        for uid in data:
            try:
                await context.bot.send_video(chat_id=int(uid), video=v, caption=cap)
                c += 1
            except: pass
        await update.message.reply_text(f"🎥 Sent to {c} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_audio":
        a = update.message.audio.file_id
        cap = update.message.caption or ""
        data = load_data(); c = 0
        for uid in data:
            try:
                await context.bot.send_audio(chat_id=int(uid), audio=a, caption=cap)
                c += 1
            except: pass
        await update.message.reply_text(f"🎵 Sent to {c} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_document":
        d = update.message.document.file_id
        cap = update.message.caption or ""
        data = load_data(); c = 0
        for uid in data:
            try:
                await context.bot.send_document(chat_id=int(uid), document=d, caption=cap)
                c += 1
            except: pass
        await update.message.reply_text(f"📄 Sent to {c} users.")
        context.user_data.pop("admin_action")

async def handle_messenger_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if context.user_data.get("admin_action") == "msg_gif":
        if update.message.animation:
            g = update.message.animation.file_id
            cap = update.message.caption or ""
            data = load_data(); c = 0
            for uid in data:
                try:
                    await context.bot.send_animation(chat_id=int(uid), animation=g, caption=cap)
                    c += 1
                except: pass
            await update.message.reply_text(f"🎞️ Sent to {c} users.")
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
        .read_timeout(30).write_timeout(30)
        .connect_timeout(30).pool_timeout(30)
        .build()
    )

    # Delete webhook first (important – ensures no conflict)
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.delete_webhook(drop_pending_updates=True))
        print("Webhook deleted successfully")
    except Exception as e:
        print(f"Webhook delete error: {e}")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("restart", restart))
    application.add_handler(CommandHandler("setphone", setphone))

    application.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    application.add_handler(CallbackQueryHandler(bot_management_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(moderator_callback, pattern="^mod_"))
    application.add_handler(CallbackQueryHandler(messenger_callback, pattern="^msg_"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    admin_id = ADMIN_IDS[0] if ADMIN_IDS else None
    if admin_id:
        application.add_handler(MessageHandler(filters.PHOTO & filters.User(admin_id), handle_messenger_photo))
        application.add_handler(MessageHandler(filters.VIDEO & filters.User(admin_id), handle_messenger_video))
        application.add_handler(MessageHandler(filters.AUDIO & filters.User(admin_id), handle_messenger_audio))
        application.add_handler(MessageHandler(filters.Document.ALL & filters.User(admin_id), handle_messenger_document))
        application.add_handler(MessageHandler(filters.ANIMATION & filters.User(admin_id), handle_messenger_gif))

    application.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True
    )


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in ADMIN_IDS:
        await update.message.reply_text("🔄 Restarting...")
        os.execv(sys.executable, ['python'] + sys.argv)
    else:
        await update.message.reply_text("❌ Not authorized.")


async def setphone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Usage: `/setphone +917250385668`", parse_mode="Markdown")
        return
    phone = " ".join(context.args).strip()
    if len(re.sub(r'\D', '', phone)) < 10:
        await update.message.reply_text("❌ Invalid phone.")
        return
    data = load_data()
    k = str(uid)
    if k in data:
        data[k]["phone"] = phone
        save_data(data)
        await update.message.reply_text(f"✅ Phone: `{phone}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ /start first")


if __name__ == "__main__":
    main()
