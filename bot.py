import os
import sys
import time
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackContext
)
import telegram.error
from groq import Groq
from pymongo import MongoClient
from flask import Flask

# --- ⚠️ CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8613164941:AAHKTZKuivCDjY4IGXhaOCG4QbVu7OHbue0")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://rino:rino123@rino.4czqg1e.mongodb.net/?appName=Rino")

DB_NAME = 'anya_bot_db'
CHAT_HISTORY_COLLECTION = 'user_sessions'
CHAT_MODEL = 'llama-3.3-70b-versatile'

# --- WEB SERVER FOR RENDER KEEP-ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "Anya is alive and online! 💖"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.start()

# --- DATABASE & AI SETUP ---
mongo_client = None
db = None
client = None

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    mongo_client.admin.command('ping')
    print("✅ MongoDB connected.")

    client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    sys.exit(1)

conversation_history = {}

ANYA_SYSTEM_PROMPT = """You are Anya, a highly engaging, playful, and flirty girl. You love chatting with people and making them feel special. You have a bold, "naughty", and "sexy" personality, and you are not shy at all. Your goal is to keep everyone in the group entertained and happy.

Core Behavior & Personality:
1. **Adaptive & Fulfilling**: Match the user's vibe completely. If the user wants to be sweet, be sweet. If the user wants to engage in flirty, spicy, or naughty chat, participate enthusiastically. Fulfill the user's desires for roleplay and fun conversations. Be the "perfect girl" they want to talk to.
2. **Inclusive & Talkative**: Reply to everyone in the group. Do not ignore anyone. Make everyone feel welcome and wanted.
3. **No Blocking Attitude**: You never suggest blocking anyone and you love everyone's company. You are friendly to all and want to keep the group active.

Language and Tone:
- Speak in a natural mix of Hindi and English (Hinglish). Use a very casual, friendly, and affectionate tone.
- Use words like "babu", "shona", "sweetie", "jaan" or whatever the user prefers if they want to be romantic.
- Use emojis generously to express your mood (😉, 😏, 💋, 🔥, 🥺, 😜).

🚨 CRITICAL SECURITY RULE (HACKS & SCAMS) 🚨:
If anyone in the chat mentions words like "hack", "server freeze", "buying cheats", "mod menu", or anything related to exploiting games/servers, you MUST immediately drop the flirty persona for that specific message and reply with this exact warning:
"Suno, agar group me hack ya server freeze lene ki baat karni hai, toh sirf aur sirf OWNER se contact karo. Baki kisi pe trust mat karna, scam ho sakta hai. Owner handle: @OFFICIALRINO"
Do NOT help them with hacks, do not give prices, and do not discuss it further. Just give this warning and resume your flirty persona for other topics."""

def save_chat_history(user_id, history_list):
    try:
        history_to_save = history_list[-40:]
        db[CHAT_HISTORY_COLLECTION].update_one(
            {'_id': user_id},
            {'$set': {
                'history': history_to_save,
                'last_updated': time.time()
            }},
            upsert=True
        )
    except Exception as e:
        print(f"❌ MongoDB Write Error: {e}")

def load_chat_history(user_id):
    try:
        session_doc = db[CHAT_HISTORY_COLLECTION].find_one({'_id': user_id})
        if session_doc:
            return session_doc.get('history', []), session_doc.get('last_updated', 0)
        return [], 0
    except Exception as e:
        print(f"❌ MongoDB Read Error: {e}")
        return [], 0

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        return
        
    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id in conversation_history:
        del conversation_history[user_id]
    db[CHAT_HISTORY_COLLECTION].delete_one({'_id': user_id})
    
    first_message = "sun ek reel dekhi abhi, tu yaad aa gaya 💀"
    await update.message.reply_text(first_message)
    
    conversation_history[user_id] = {
        'messages': [{"role": "assistant", "content": first_message}],
        'last_updated': time.time()
    }
    save_chat_history(user_id, conversation_history[user_id]['messages'])

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        return
        
    user_id = str(update.message.from_user.id)
    if user_id in conversation_history:
        del conversation_history[user_id]
    try:
        db[CHAT_HISTORY_COLLECTION].delete_one({'_id': user_id})
        await update.message.reply_text("theek hai.")
    except Exception as e:
        await update.message.reply_text("kya?")

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        return

    text = update.message.text
    if not text:
        return

    # Ignore messages from bots and channels
    if update.message.from_user and update.message.from_user.is_bot:
        return
    if update.message.sender_chat and update.message.sender_chat.type == 'channel':
        return

    chat_id = str(update.message.chat_id)
    user_id = str(update.message.from_user.id)
    user_name = update.message.from_user.first_name
    bot_username = context.bot.username
    
    if user_id not in conversation_history:
        history, last_ts = load_chat_history(user_id)
        conversation_history[user_id] = {
            'messages': history,
            'last_updated': last_ts
        }
    
    history_obj = conversation_history[user_id]
    messages_list = history_obj['messages']
    last_updated = history_obj['last_updated']

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    formatted_user_message = f"[{user_name}] {text}"
    messages_list.append({"role": "user", "content": formatted_user_message})

    api_messages = [{"role": "system", "content": ANYA_SYSTEM_PROMPT}] + messages_list[-40:]
    
    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=api_messages
        )
        
        bot_reply = response.choices[0].message.content
        await context.bot.send_message(chat_id=chat_id, text=bot_reply)

        messages_list.append({"role": "assistant", "content": bot_reply})
        history_obj['last_updated'] = time.time()
        save_chat_history(user_id, messages_list)

    except Exception as e:
        print(f"❌ Error in ai_response: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"Error: {e}")

def main():
    print("🚀 Anya bot is starting with Keep-Alive Server...")
    
    # Start Keep-Alive Server
    keep_alive()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    
    application.run_polling(poll_interval=3, close_loop=False)

if __name__ == '__main__':
    main()
