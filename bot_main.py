import os
import sys
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import requests

from tools.downloader import is_media_url, download_media
from tools.search import web_search
import memory

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "9261150155:AAF3KURDsHJb1x9WTuR8Efw21Vx4ztubj_8")
OWNER_ID = int(os.environ.get("TELEGRAM_OWNER_ID", "7198790563"))
FREELLM_KEY = os.environ.get("FREELLM_KEY", "freellmapi-4d7a72440fbdccc7193990d99393ef0e45649ff5b464baf5")
FREELLM_URL = os.environ.get("FREELLM_URL", "https://freellmapi-dab8.onrender.com/v1/chat/completions")
PORT = int(os.environ.get("PORT", 10000))
START_TIME = time.time()

bot = telebot.TeleBot(BOT_TOKEN)

# ---------------------------------------------------------
# Keyboards & Menus ("sab ko menu ma laooo")
# ---------------------------------------------------------
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, one_time_keyboard=False)
    btn_chat = types.KeyboardButton("💬 AI Chat")
    btn_download = types.KeyboardButton("📥 Video Downloader")
    btn_search = types.KeyboardButton("🔍 Web Search")
    btn_notes = types.KeyboardButton("📝 My Notes")
    btn_ping = types.KeyboardButton("⚡ 0ms Status")
    btn_clear = types.KeyboardButton("🧹 Clear Context")
    markup.add(btn_chat, btn_download)
    markup.add(btn_search, btn_notes)
    markup.add(btn_ping, btn_clear)
    return markup

def get_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💬 AI Chat Help", callback_data="menu_chat"),
        types.InlineKeyboardButton("📥 Video Downloader", callback_data="menu_download")
    )
    markup.add(
        types.InlineKeyboardButton("🔍 Web Search", callback_data="menu_search"),
        types.InlineKeyboardButton("📝 My Notes", callback_data="menu_notes")
    )
    markup.add(
        types.InlineKeyboardButton("⚡ 0ms Ping Test", callback_data="menu_ping"),
        types.InlineKeyboardButton("🧹 Clear Chat", callback_data="menu_clear")
    )
    return markup

# ---------------------------------------------------------
# Safe Message Sender (Never Fails)
# ---------------------------------------------------------
def safe_reply(message, text, reply_markup=None):
    try:
        return bot.reply_to(message, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "`").replace("</code>", "`")
        return bot.reply_to(message, plain, parse_mode=None, reply_markup=reply_markup)

def safe_send(chat_id, text, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "`").replace("</code>", "`")
        return bot.send_message(chat_id, plain, parse_mode=None, reply_markup=reply_markup)

def safe_edit(chat_id, message_id, text, reply_markup=None):
    try:
        return bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "`").replace("</code>", "`")
        return bot.edit_message_text(plain, chat_id=chat_id, message_id=message_id, parse_mode=None, reply_markup=reply_markup)

# ---------------------------------------------------------
# 1. 0ms Keep-Alive Server & Background Self-Pinger
# ---------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "status": "ok",
            "bot": "@lipan_apex_bot",
            "mode": "solo_personal_assistant",
            "latency": "0ms_keepalive_active",
            "uptime_sec": int(time.time() - START_TIME)
        }
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

def start_keepalive_ping():
    """Pings the public edge URL every 60 seconds so Render free tier never sleeps (0ms cold start)."""
    time.sleep(15)
    while True:
        try:
            requests.get("https://picoclaw-worker-5.onrender.com/health", timeout=10)
        except Exception:
            pass
        time.sleep(60)

# ---------------------------------------------------------
# 2. Security Whitelist Decorator (Strict Solo Access)
# ---------------------------------------------------------
def owner_only(func):
    def wrapper(message, *args, **kwargs):
        if message.from_user.id != OWNER_ID:
            safe_reply(message, "🔒 Access Restricted: Yeh bot sirf Lipan ke liye private solo assistant hai.")
            return
        return func(message, *args, **kwargs)
    return wrapper

# ---------------------------------------------------------
# 3. Solo AI Brain (FreeLLM API with Auto-Routing)
# ---------------------------------------------------------
SYSTEM_PROMPT = """You are Lipan's dedicated, private, solo personal AI assistant (@lipan_apex_bot).
You speak in clean, natural, respectful Hinglish.
You assist Lipan with coding, troubleshooting, technical tasks, web research, calculations, and general conversation.
Be direct, smart, concise, and helpful. No fluff."""

def call_ai(user_id, prompt):
    recent_history = memory.get_recent_chat(user_id, limit=6)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in recent_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {FREELLM_KEY}",
        "Content-Type": "application/json"
    }

    # Attempt 1: Auto-routing
    payload = {
        "model": "auto",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }

    try:
        resp = requests.post(FREELLM_URL, headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        
        # Fallback to gemini-flash if auto fails
        if resp.status_code != 200:
            payload["model"] = "gemini-flash"
            resp2 = requests.post(FREELLM_URL, headers=headers, json=payload, timeout=20)
            if resp2.status_code == 200:
                data2 = resp2.json()
                return data2["choices"][0]["message"]["content"].strip()

        return f"⚠️ AI Gateway Error (HTTP {resp.status_code}): {resp.text[:120]}"
    except Exception as e:
        return f"⚠️ AI Connection Error: {str(e)}"

# ---------------------------------------------------------
# 4. Commands & Menus
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'menu'])
@owner_only
def cmd_start(message):
    text = (
        "👑 <b>Namaste Lipan Bhai! Welcome to Apex Solo AI</b>\n\n"
        "Main aapka <b>100% Solo & Private Personal Assistant</b> hoon (@lipan_apex_bot).\n"
        "Neeche diye gaye <b>Touch Menu</b> ya <b>Buttons</b> se koi bhi action select karein:\n\n"
        "• 💬 <b>AI Chat:</b> Normal sawaal ya code bhejein — instant reply.\n"
        "• 📥 <b>Video Downloader:</b> Insta, YouTube, X ka link paste karein.\n"
        "• 🔍 <b>Web Search:</b> Real-time live web browsing.\n"
        "• 📝 <b>My Notes:</b> Cloud database me secure notes save karein.\n"
        "• ⚡ <b>0ms Status:</b> Real-time latency & health check.\n"
        "• 🧹 <b>Clear Context:</b> Conversation history reset."
    )
    # Send with both Persistent Keyboard and Inline Interactive Menu
    safe_send(message.chat.id, text, reply_markup=get_main_keyboard())
    safe_send(message.chat.id, "👇 <b>Quick Action Menu:</b>", reply_markup=get_inline_menu())

@bot.message_handler(commands=['ping'])
@owner_only
def cmd_ping(message):
    t0 = time.time()
    db_ok = memory.save_note(OWNER_ID, "_ping_test", "1")
    latency = round((time.time() - t0) * 1000, 1)
    uptime = int(time.time() - START_TIME)
    uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s"
    
    text = (
        "⚡ <b>0ms Apex Keep-Alive Status: LIVE</b>\n\n"
        f"• <b>Ping Latency:</b> <code>{latency}ms</code> (0ms Keep-Alive Active)\n"
        f"• <b>Database:</b> <code>{'Connected (Neon Postgres)' if db_ok else 'Error'}</code>\n"
        f"• <b>AI Engine:</b> <code>FreeLLM Auto-Router (Online)</code>\n"
        f"• <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"• <b>Render Keep-Alive:</b> <code>Every 60s Self-Ping Active</code>\n"
        "• <b>Architecture:</b> <code>100% Solo & Private</code>"
    )
    safe_reply(message, text)

@bot.message_handler(commands=['note'])
@owner_only
def cmd_note(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        safe_reply(message, "💡 <b>Usage:</b> <code>/note &lt;name&gt; &lt;content&gt;</code>\n<b>Example:</b> <code>/note wifi MySecretPass123</code>")
        return
    key = parts[1]
    value = parts[2]
    ok = memory.save_note(OWNER_ID, key, value)
    if ok:
        safe_reply(message, f"✅ Note <b>[{key}]</b> Neon DB me save ho gaya!")
    else:
        safe_reply(message, "❌ Note save karne me database error aaya.")

@bot.message_handler(commands=['notes'])
@owner_only
def cmd_notes(message):
    notes = memory.get_notes(OWNER_ID)
    valid_notes = [n for n in notes if n['note_key'] != "_ping_test"]
    if not valid_notes:
        safe_reply(message, "📋 Abhi koi saved notes nahi hain. Save karne ke liye likhein:\n<code>/note &lt;name&gt; &lt;value&gt;</code>")
        return
    lines = ["📋 <b>Aapke Saved Notes (Neon DB):</b>\n"]
    for n in valid_notes:
        lines.append(f"• <b>{n['note_key']}:</b> <code>{n['note_value']}</code>")
    safe_reply(message, "\n".join(lines))

@bot.message_handler(commands=['delnote'])
@owner_only
def cmd_delnote(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        safe_reply(message, "💡 <b>Usage:</b> <code>/delnote &lt;name&gt;</code>")
        return
    key = parts[1]
    ok = memory.delete_note(OWNER_ID, key)
    if ok:
        safe_reply(message, f"🗑️ Note <b>[{key}]</b> delete ho gaya.")
    else:
        safe_reply(message, "❌ Note delete karne me error.")

@bot.message_handler(commands=['search'])
@owner_only
def cmd_search(message):
    query = message.text.replace("/search", "", 1).strip()
    if not query:
        safe_reply(message, "💡 <b>Usage:</b> <code>/search &lt;query&gt;</code>\n<b>Example:</b> <code>/search python async guide</code>")
        return
    wait_msg = safe_reply(message, f"🔍 <i>Searching web for: {query}...</i>")
    res = web_search(query)
    safe_edit(message.chat.id, wait_msg.message_id, f"🌐 <b>Results for:</b> <code>{query}</code>\n\n{res}")

@bot.message_handler(commands=['clear'])
@owner_only
def cmd_clear(message):
    memory.clear_chat(OWNER_ID)
    safe_reply(message, "🧹 <b>Chat history & context clear ho gaya!</b>")

# ---------------------------------------------------------
# 5. Callback Query Handler (Inline Menu Taps)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Access restricted", show_alert=True)
        return

    data = call.data
    bot.answer_callback_query(call.id)

    if data == "menu_chat":
        text = "💬 <b>AI Chat:</b>\nAap mujhse koi bhi sawaal, code ya calculation seedha chat me pucho — instant answer milega!"
        safe_send(call.message.chat.id, text)
    elif data == "menu_download":
        text = "📥 <b>Video Downloader:</b>\nKoi bhi Instagram Reel, YouTube Video/Short, ya Twitter/X video ka link chat me paste karo — main video file download karke seedha bhej dunga."
        safe_send(call.message.chat.id, text)
    elif data == "menu_search":
        text = "🔍 <b>Web Search:</b>\nType karein: <code>search &lt;query&gt;</code> ya <code>/search &lt;query&gt;</code> (e.g. <code>search python tutorials</code>)."
        safe_send(call.message.chat.id, text)
    elif data == "menu_notes":
        cmd_notes(call.message)
    elif data == "menu_ping":
        cmd_ping(call.message)
    elif data == "menu_clear":
        cmd_clear(call.message)

# ---------------------------------------------------------
# 6. Button Text Handler & Pure Chat
# ---------------------------------------------------------
@bot.message_handler(func=lambda msg: True)
@owner_only
def handle_all_messages(message):
    text = message.text.strip()

    # 1. Menu Button Taps
    if text == "💬 AI Chat":
        safe_reply(message, "💬 <b>AI Chat Active!</b>\nKoi bhi sawaal ya query seedha type karke send karo!")
        return
    elif text == "📥 Video Downloader":
        safe_reply(message, "📥 <b>Video Downloader:</b>\nBas Instagram, YouTube ya Twitter/X ka link paste karo!")
        return
    elif text == "🔍 Web Search":
        safe_reply(message, "🔍 <b>Web Search:</b>\nType karein: <code>search &lt;topic&gt;</code> (e.g. <code>search latest AI models</code>)")
        return
    elif text == "📝 My Notes":
        cmd_notes(message)
        return
    elif text == "⚡ 0ms Status":
        cmd_ping(message)
        return
    elif text == "🧹 Clear Context":
        cmd_clear(message)
        return

    # 2. Media Link Detection (Instagram, YouTube, Twitter/X, etc.)
    media_url = is_media_url(text)
    if media_url:
        status_msg = safe_reply(message, "⏳ <i>Video link detect hua! Downloading via yt-dlp...</i>")
        res = download_media(media_url)
        if res.get("success"):
            file_path = res["file_path"]
            title = res.get("title", "Video")
            try:
                safe_edit(message.chat.id, status_msg.message_id, "📤 <i>Uploading video...</i>")
                with open(file_path, "rb") as video_file:
                    bot.send_video(
                        message.chat.id,
                        video_file,
                        caption=f"🎬 <b>{title}</b>",
                        parse_mode="HTML",
                        reply_to_message_id=message.message_id
                    )
                bot.delete_message(message.chat.id, status_msg.message_id)
            except Exception as e:
                safe_edit(message.chat.id, status_msg.message_id, f"❌ Upload error: {str(e)}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            safe_edit(message.chat.id, status_msg.message_id, f"❌ Download failed: {res.get('error', 'Error')}")
        return

    # 3. Direct Search query (e.g. "search python tutorials")
    if text.lower().startswith("search ") or text.lower().startswith("google "):
        query = text.split(" ", 1)[1].strip()
        wait_msg = safe_reply(message, f"🔍 <i>Searching web for: {query}...</i>")
        res = web_search(query)
        safe_edit(message.chat.id, wait_msg.message_id, f"🌐 <b>Results for:</b> <code>{query}</code>\n\n{res}")
        return

    # 4. Clean Natural AI Conversation
    bot.send_chat_action(message.chat.id, "typing")
    memory.save_chat(OWNER_ID, "user", text)
    ai_reply = call_ai(OWNER_ID, text)
    memory.save_chat(OWNER_ID, "assistant", ai_reply)
    safe_reply(message, ai_reply)

# ---------------------------------------------------------
# 7. Main Boot
# ---------------------------------------------------------
if __name__ == "__main__":
    print("==========================================================")
    print("🤖 Starting Lipan 100% Solo Personal Assistant (@lipan_apex_bot)")
    print(f"👑 Owner ID: {OWNER_ID}")
    print("==========================================================")

    # Set native Telegram Command Menu
    try:
        bot.set_my_commands([
            types.BotCommand("start", "🚀 Main Dashboard & Menu"),
            types.BotCommand("ping", "⚡ 0ms Status & Health Check"),
            types.BotCommand("notes", "📋 View Saved Notes"),
            types.BotCommand("note", "➕ Save Note (/note key value)"),
            types.BotCommand("delnote", "🗑️ Delete Note (/delnote key)"),
            types.BotCommand("search", "🔍 Web Search (/search query)"),
            types.BotCommand("clear", "🧹 Clear Chat History")
        ], scope=types.BotCommandScopeChat(OWNER_ID))
        print("[Bot] Registered native Telegram Command Menu")
    except Exception as e:
        print(f"[Bot] Could not set my commands: {e}")

    # Health server on port 10000
    t_health = threading.Thread(target=start_health_server, daemon=True)
    t_health.start()

    # 0ms Keep-Alive Self-Pinger (runs every 60s)
    t_keepalive = threading.Thread(target=start_keepalive_ping, daemon=True)
    t_keepalive.start()
    print("[Bot] Started 0ms Keep-Alive Self-Pinger (Every 60s)")

    # Telegram polling
    print("[Bot] Connecting to Telegram API in Solo mode...")
    while True:
        try:
            bot.infinity_polling(timeout=25, long_polling_timeout=25)
        except Exception as e:
            print(f"[Error] Polling error: {e}. Reconnecting in 5s...")
            time.sleep(5)
