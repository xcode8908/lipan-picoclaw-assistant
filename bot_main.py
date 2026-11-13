import os
import sys
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import requests

from tools.downloader import is_media_url, download_media, download_audio
from tools.search import web_search
from tools.fleet import get_fleet_report
import memory

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "9261150155:AAF3KURDsHJb1x9WTuR8Efw21Vx4ztubj_8")
OWNER_ID = int(os.environ.get("TELEGRAM_OWNER_ID", "7198790563"))
FREELLM_KEY = os.environ.get("FREELLM_KEY", "sk-cp-9b5527df917c6e6463295c54976b382c027519fab2d12768")
FREELLM_URL = os.environ.get("FREELLM_URL", "https://freellmapi-dab8.onrender.com/v1/chat/completions")
PORT = int(os.environ.get("PORT", 10000))

bot = telebot.TeleBot(BOT_TOKEN)

# ---------------------------------------------------------
# Safe Message Sender (Never Fails, No Markdown Crashes)
# ---------------------------------------------------------
def safe_send_message(chat_id, text, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        print(f"[Send Error] HTML parse failed, falling back to plain text: {e}")
        # Strip simple HTML tags for fallback
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "`").replace("</code>", "`")
        return bot.send_message(chat_id, plain, parse_mode=None, reply_markup=reply_markup)

def safe_reply_to(message, text, reply_markup=None):
    try:
        return bot.reply_to(message, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        print(f"[Reply Error] HTML parse failed, falling back to plain text: {e}")
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "`").replace("</code>", "`")
        return bot.reply_to(message, plain, parse_mode=None, reply_markup=reply_markup)

def safe_edit_message(chat_id, message_id, text, reply_markup=None):
    try:
        return bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        print(f"[Edit Error] HTML parse failed, falling back to plain text: {e}")
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "`").replace("</code>", "`")
        return bot.edit_message_text(plain, chat_id=chat_id, message_id=message_id, parse_mode=None, reply_markup=reply_markup)

# ---------------------------------------------------------
# 1. Healthcheck Server (0ms Keep-Alive & Sentry Watchdog)
# ---------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "status": "ok",
            "bot": "@lipan_apex_bot",
            "owner": "Lipan",
            "uptime_sec": int(time.time() - START_TIME)
        }
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, format, *args):
        return  # Silent access logs to prevent clutter

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"[Boot] Healthcheck server listening on port {PORT}...")
    server.serve_forever()

# ---------------------------------------------------------
# 2. Security Whitelist Decorator
# ---------------------------------------------------------
def owner_only(func):
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        if user_id != OWNER_ID:
            print(f"[Security] Unauthorized access attempt from ID: {user_id}")
            safe_reply_to(
                message,
                "🔒 <b>Access Restricted</b>\n\nYeh bot sirf <b>Lipan (@xcode8908)</b> ke liye reserved private AI assistant hai."
            )
            return
        return func(message, *args, **kwargs)
    return wrapper

# ---------------------------------------------------------
# 3. AI Brain (FreeLLM API with Gemini Flash)
# ---------------------------------------------------------
SYSTEM_PROMPT = """You are Lipan's elite personal AI assistant (@lipan_apex_bot), running on PicoClaw Worker 5.
You are loyal, sharp, knowledgeable, and speak in friendly, energetic Hinglish.
Lipan is a developer and cloud enthusiast who manages multiple Render workers, Linux cloud PCs, and Telegram bots.
Always give direct, actionable, concise, and smart answers. Never give robotic or generic AI disclaimers."""

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
    payload = {
        "model": "gemini-1.5-flash",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }

    try:
        resp = requests.post(FREELLM_URL, headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            return f"⚠️ AI Gateway Error (HTTP {resp.status_code}): {resp.text[:150]}"
    except Exception as e:
        return f"⚠️ AI Connection Error: {str(e)}"

# ---------------------------------------------------------
# 4. Interactive Keyboards
# ---------------------------------------------------------
def get_main_menu_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("📊 Fleet & Server Status", callback_data="cb_status")
    b2 = types.InlineKeyboardButton("📋 My Saved Notes", callback_data="cb_notes")
    b3 = types.InlineKeyboardButton("🔍 Web Search Help", callback_data="cb_search_help")
    b4 = types.InlineKeyboardButton("🧹 Clear Conversation", callback_data="cb_clear")
    b5 = types.InlineKeyboardButton("ℹ️ All Bot Features", callback_data="cb_help")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5)
    return markup

def get_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Fleet Status", "📋 My Notes")
    markup.row("ℹ️ Help Menu", "🧹 Clear Context")
    return markup

# ---------------------------------------------------------
# 5. Telegram Command Handlers
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
@owner_only
def cmd_start(message):
    text = (
        "👑 <b>Namaste Lipan Bhai! Welcome to @lipan_apex_bot</b>\n\n"
        "Main hoon aapka dedicated <b>Personal PicoClaw AI Assistant</b>.\n"
        "⚡ <b>Status:</b> 24/7 Live | 0ms Keep-Alive | Lifetime Free ($0)\n"
        "💾 <b>Memory:</b> Neon PostgreSQL (Encrypted & Private)\n\n"
        "🚀 <b>Aap Mere Saath Kya Kar Sakte Hain:</b>\n"
        "• 🎥 <b>Any Video Link Bhejo</b> (Insta Reel / YouTube / X) → Direct original MP4 video download ho jayegi.\n"
        "• 📊 <b>/status</b> → Saare 6 workers, Alpine Cloud PC & Sentry ka live health card.\n"
        "• 📝 <b>/note &lt;name&gt; &lt;text&gt;</b> → Secret notes / passwords save karo.\n"
        "• 📋 <b>/notes</b> → Saare saved notes dekho.\n"
        "• 🔍 <b>/search &lt;query&gt;</b> → Live web search karo.\n"
        "• 💬 <b>Normal message</b> bhejo → Smart AI assistant reply karega!\n\n"
        "<i>Neeche buttons par click karke direct use karein:</i>"
    )
    safe_reply_to(message, text, reply_markup=get_main_menu_keyboard())

@bot.message_handler(commands=['status'])
@owner_only
def cmd_status(message):
    wait_msg = safe_reply_to(message, "⏳ <i>Checking entire fleet health via Sentry Watchdog...</i>")
    report = get_fleet_report()
    # Format report into clean HTML
    html_report = f"<b>🛡️ Lipan Fleet Live Status:</b>\n\n<pre>{report}</pre>"
    safe_edit_message(message.chat.id, wait_msg.message_id, html_report, reply_markup=get_main_menu_keyboard())

@bot.message_handler(commands=['ping'])
@owner_only
def cmd_ping(message):
    safe_reply_to(message, "🏓 <b>Pong!</b> 0ms Active & Ready for your command, Lipan bhai! ⚡")

@bot.message_handler(commands=['note'])
@owner_only
def cmd_note(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        safe_reply_to(message, "💡 <b>Usage:</b> <code>/note &lt;name&gt; &lt;content&gt;</code>\n<b>Example:</b> <code>/note wifi MySecretPass123</code>")
        return
    key = parts[1]
    value = parts[2]
    ok = memory.save_note(OWNER_ID, key, value)
    if ok:
        safe_reply_to(message, f"✅ Note <b>[{key}]</b> successfully Neon DB me save ho gaya!")
    else:
        safe_reply_to(message, "❌ Note save karne me database error aaya.")

@bot.message_handler(commands=['notes'])
@owner_only
def cmd_notes(message):
    notes = memory.get_notes(OWNER_ID)
    if not notes:
        safe_reply_to(message, "📋 Abhi koi saved notes nahi hain. Naya note save karne ke liye likhein:\n<code>/note &lt;name&gt; &lt;value&gt;</code>")
        return
    lines = ["📋 <b>Aapke Saved Notes (Neon DB):</b>\n"]
    for n in notes:
        lines.append(f"• <b>{n['note_key']}:</b> <code>{n['note_value']}</code>")
    safe_reply_to(message, "\n".join(lines))

@bot.message_handler(commands=['delnote'])
@owner_only
def cmd_delnote(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        safe_reply_to(message, "💡 <b>Usage:</b> <code>/delnote &lt;name&gt;</code>")
        return
    key = parts[1]
    ok = memory.delete_note(OWNER_ID, key)
    if ok:
        safe_reply_to(message, f"🗑️ Note <b>[{key}]</b> delete kar diya gaya.")
    else:
        safe_reply_to(message, "❌ Note delete karne me error.")

@bot.message_handler(commands=['search'])
@owner_only
def cmd_search(message):
    query = message.text.replace("/search", "", 1).strip()
    if not query:
        safe_reply_to(message, "💡 <b>Usage:</b> <code>/search &lt;query&gt;</code>\n<b>Example:</b> <code>/search latest gold rate today</code>")
        return
    wait_msg = safe_reply_to(message, f"🔍 <i>Searching web for: {query}...</i>")
    res = web_search(query)
    safe_edit_message(message.chat.id, wait_msg.message_id, f"🌐 <b>Search Results for:</b> <code>{query}</code>\n\n{res}")

@bot.message_handler(commands=['clear'])
@owner_only
def cmd_clear(message):
    memory.clear_chat(OWNER_ID)
    safe_reply_to(message, "🧹 <b>Chat context clear ho gaya!</b> Nayi fresh conversation start ho chuki hai.")

# ---------------------------------------------------------
# 6. Callback Query Handler (Inline Button Taps)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 Access Restricted", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    if call.data == "cb_status":
        wait_msg = safe_send_message(chat_id, "⏳ <i>Checking entire fleet health via Sentry Watchdog...</i>")
        report = get_fleet_report()
        safe_edit_message(chat_id, wait_msg.message_id, f"<b>🛡️ Lipan Fleet Live Status:</b>\n\n<pre>{report}</pre>", reply_markup=get_main_menu_keyboard())

    elif call.data == "cb_notes":
        notes = memory.get_notes(OWNER_ID)
        if not notes:
            safe_send_message(chat_id, "📋 Abhi koi saved notes nahi hain. Likh kar bhejein:\n<code>/note &lt;name&gt; &lt;value&gt;</code>", reply_markup=get_main_menu_keyboard())
        else:
            lines = ["📋 <b>Aapke Saved Notes (Neon DB):</b>\n"]
            for n in notes:
                lines.append(f"• <b>{n['note_key']}:</b> <code>{n['note_value']}</code>")
            safe_send_message(chat_id, "\n".join(lines), reply_markup=get_main_menu_keyboard())

    elif call.data == "cb_clear":
        memory.clear_chat(OWNER_ID)
        safe_send_message(chat_id, "🧹 <b>Chat context clear ho gaya!</b>", reply_markup=get_main_menu_keyboard())

    elif call.data == "cb_search_help":
        safe_send_message(chat_id, "🔍 <b>Web Search Kaise Karein:</b>\n\nChat me likhein:\n<code>/search &lt;query&gt;</code>\nYa seedha likhein:\n<code>search gold rate today</code>", reply_markup=get_main_menu_keyboard())

    elif call.data == "cb_help":
        cmd_start(call.message)

# ---------------------------------------------------------
# 7. Media & General Message Handler
# ---------------------------------------------------------
@bot.message_handler(func=lambda msg: True)
@owner_only
def handle_all_messages(message):
    text = message.text.strip()

    # Quick Keyboard triggers
    if text == "📊 Fleet Status":
        cmd_status(message)
        return
    elif text == "📋 My Notes":
        cmd_notes(message)
        return
    elif text == "🧹 Clear Context":
        cmd_clear(message)
        return
    elif text == "ℹ️ Help Menu":
        cmd_start(message)
        return

    # Check if message contains media URL (Instagram, YouTube, X, etc.)
    media_url = is_media_url(text)
    if media_url:
        status_msg = safe_reply_to(message, "⏳ <b>Video link detect hua!</b> <i>Downloading video file via yt-dlp...</i>")
        res = download_media(media_url)
        if res.get("success"):
            file_path = res["file_path"]
            title = res.get("title", "Video")
            try:
                safe_edit_message(message.chat.id, status_msg.message_id, "📤 <b>Uploading video to Telegram...</b>")
                with open(file_path, "rb") as video_file:
                    bot.send_video(
                        message.chat.id,
                        video_file,
                        caption=f"🎬 <b>{title}</b>\n\n⚡ Downloaded by @lipan_apex_bot",
                        parse_mode="HTML",
                        reply_to_message_id=message.message_id
                    )
                bot.delete_message(message.chat.id, status_msg.message_id)
            except Exception as e:
                safe_edit_message(message.chat.id, status_msg.message_id, f"❌ Upload error: {str(e)}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            safe_edit_message(
                message.chat.id,
                status_msg.message_id,
                f"❌ Download failed: {res.get('error', 'Unknown error')}"
            )
        return

    # Check for direct search phrasing
    if text.lower().startswith("search ") or text.lower().startswith("google "):
        query = text.split(" ", 1)[1].strip()
        wait_msg = safe_reply_to(message, f"🔍 <i>Searching web for: {query}...</i>")
        res = web_search(query)
        safe_edit_message(message.chat.id, wait_msg.message_id, f"🌐 <b>Search Results for:</b> <code>{query}</code>\n\n{res}")
        return

    # General AI Conversation
    bot.send_chat_action(message.chat.id, "typing")
    memory.save_chat(OWNER_ID, "user", text)
    ai_reply = call_ai(OWNER_ID, text)
    memory.save_chat(OWNER_ID, "assistant", ai_reply)
    safe_reply_to(message, ai_reply, reply_markup=get_reply_keyboard())

# ---------------------------------------------------------
# 8. Main Boot
# ---------------------------------------------------------
if __name__ == "__main__":
    START_TIME = time.time()
    print("==========================================================")
    print("🤖 Starting Lipan Personal PicoClaw Assistant (@lipan_apex_bot)")
    print(f"👑 Owner ID: {OWNER_ID}")
    print("==========================================================")

    # Start Health Server in background thread
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    # Start Telegram Polling loop with resilient auto-reconnect
    print("[Bot] Connecting to Telegram API...")
    while True:
        try:
            bot.infinity_polling(timeout=25, long_polling_timeout=25)
        except Exception as e:
            print(f"[Error] Polling error: {e}. Reconnecting in 5s...")
            time.sleep(5)
