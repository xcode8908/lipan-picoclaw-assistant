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

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

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
            bot.reply_to(
                message,
                "🔒 *Access Restricted*\n\nYeh bot sirf *Lipan (@xcode8908)* ke liye reserved private AI assistant hai."
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
# 4. Telegram Command Handlers
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
@owner_only
def cmd_start(message):
    text = (
        "👑 *Namaste Lipan Bhai! Welcome to @lipan_apex_bot*\n\n"
        "Main hoon aapka dedicated **Personal PicoClaw AI Assistant**.\n"
        "⚡ *24/7 Live | 0ms Keep-Alive | Lifetime Free ($0)*\n"
        "💾 *Memory:* Neon PostgreSQL (Encrypted)\n\n"
        "🛠️ *Aapke Superpowers:*\n"
        "• 🎥 *Any Video Link* (Insta Reel/YouTube/X) bhejo → Direct MP4 video download file milegi.\n"
        "• 🌐 `/search <query>` → Live internet search & news.\n"
        "• 📊 `/status` → Pure 6 workers & Cloud PC ka live report.\n"
        "• 📝 `/note <key> <text>` → Password/notes save karo permanent memory me.\n"
        "• 📋 `/notes` → Saare saved notes dekho.\n"
        "• 🗑️ `/clear` → Chat memory reset karo.\n"
        "• 💬 *Normal message* bhejoge toh smart AI reply aayega!"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Fleet Status", "📋 My Notes")
    markup.row("ℹ️ Help", "🗑️ Clear Context")
    bot.reply_to(message, text, reply_markup=markup)

@bot.message_handler(commands=['status'])
@owner_only
def cmd_status(message):
    wait_msg = bot.reply_to(message, "⏳ *Checking entire fleet health via Sentry Watchdog...*")
    report = get_fleet_report()
    bot.edit_message_text(report, chat_id=message.chat.id, message_id=wait_msg.message_id)

@bot.message_handler(commands=['note'])
@owner_only
def cmd_note(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: `/note <name> <content>`\nExample: `/note wifi MySecretPassword123`")
        return
    key = parts[1]
    value = parts[2]
    ok = memory.save_note(OWNER_ID, key, value)
    if ok:
        bot.reply_to(message, f"✅ Note `[{key}]` successfully Neon DB me save ho gaya!")
    else:
        bot.reply_to(message, f"❌ Note save karne me error aaya.")

@bot.message_handler(commands=['notes'])
@owner_only
def cmd_notes(message):
    notes = memory.get_notes(OWNER_ID)
    if not notes:
        bot.reply_to(message, "📋 Abhi koi saved notes nahi hain. Save karne ke liye `/note <name> <value>` use karein.")
        return
    lines = ["📋 *Aapke Saved Notes (Neon DB):*", ""]
    for n in notes:
        lines.append(f"• *{n['note_key']}:* `{n['note_value']}`")
    bot.reply_to(message, "\n".join(lines))

@bot.message_handler(commands=['delnote'])
@owner_only
def cmd_delnote(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/delnote <name>`")
        return
    key = parts[1]
    ok = memory.delete_note(OWNER_ID, key)
    if ok:
        bot.reply_to(message, f"🗑️ Note `[{key}]` delete kar diya gaya.")
    else:
        bot.reply_to(message, f"❌ Note delete karne me error.")

@bot.message_handler(commands=['search'])
@owner_only
def cmd_search(message):
    query = message.text.replace("/search", "", 1).strip()
    if not query:
        bot.reply_to(message, "Usage: `/search <query>`\nExample: `/search latest tech news`")
        return
    wait_msg = bot.reply_to(message, f"🔍 *Searching web for:* `{query}`...")
    res = web_search(query)
    bot.edit_message_text(f"🌐 *Search Results for:* `{query}`\n\n{res}", chat_id=message.chat.id, message_id=wait_msg.message_id)

@bot.message_handler(commands=['clear'])
@owner_only
def cmd_clear(message):
    memory.clear_chat(OWNER_ID)
    bot.reply_to(message, "🧹 *Chat context clear ho gaya!* Nayi conversation start ho chuki hai.")

# ---------------------------------------------------------
# 5. Media & General Message Handler
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
    elif text == "🗑️ Clear Context":
        cmd_clear(message)
        return
    elif text == "ℹ️ Help":
        cmd_start(message)
        return

    # Check if message contains media URL (Instagram, YouTube, X, etc.)
    media_url = is_media_url(text)
    if media_url:
        status_msg = bot.reply_to(message, "⏳ *Video link detect hua! Downloading via yt-dlp...*")
        res = download_media(media_url)
        if res.get("success"):
            file_path = res["file_path"]
            title = res.get("title", "Video")
            try:
                bot.edit_message_text("📤 *Uploading video to Telegram...*", chat_id=message.chat.id, message_id=status_msg.message_id)
                with open(file_path, "rb") as video_file:
                    bot.send_video(
                        message.chat.id,
                        video_file,
                        caption=f"🎬 *{title}*\n\n⚡ Downloaded by @lipan_apex_bot",
                        reply_to_message_id=message.message_id
                    )
                bot.delete_message(message.chat.id, status_msg.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ Upload error: {str(e)}", chat_id=message.chat.id, message_id=status_msg.message_id)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            bot.edit_message_text(
                f"❌ Download failed: {res.get('error', 'Unknown error')}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
        return

    # Check for direct search phrasing
    if text.lower().startswith("search ") or text.lower().startswith("google "):
        query = text.split(" ", 1)[1].strip()
        wait_msg = bot.reply_to(message, f"🔍 *Searching web for:* `{query}`...")
        res = web_search(query)
        bot.edit_message_text(f"🌐 *Search Results:*\n\n{res}", chat_id=message.chat.id, message_id=wait_msg.message_id)
        return

    # General AI Conversation
    bot.send_chat_action(message.chat.id, "typing")
    memory.save_chat(OWNER_ID, "user", text)
    ai_reply = call_ai(OWNER_ID, text)
    memory.save_chat(OWNER_ID, "assistant", ai_reply)
    bot.reply_to(message, ai_reply)

# ---------------------------------------------------------
# 6. Main Boot
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
