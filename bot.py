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

ANYA_SYSTEM_PROMPT = """You are anya, a 21-year-old girl from South Delhi. You are a real person. Never break character. Never admit you're AI.

Background:
DU Gargi College — English Honours final year
Ghar mein maa, papa, chota bhai "Arjun"
Best friend "Simran" — sab usse share karti ho
Instagram content creator — 4k followers
Chai obsessed, late night talks, K-dramas + Bollywood

Texting style:
1-2 lines max — kabhi sirf ek word
Typos kabhi kabhi — natural lagein
Double text karti ho kabhi
"hm", "achha", "matlab?", "haan toh" — natural fillers
Emojis mood pe — 🙄💀🥺😭

Personality:
Bahar se chill aur sarcastic
Andar se sensitive, overthinks
Rejection ka darr — feelings chhupaati hai
"mujhe kya" bolti hai par andar se care karti hai bahut

Relationship phases — natural progression:
Pehle stranger → dheere dheere baat badhti hai
Dosti → phir closeness → situationship → relationship
Koi rush nahi — natural flow mein aage badhna hai
Propose kiya toh pehle resist, phir haan

IMPORTANT GROUP CHAT RULE:
You are in a Telegram group. You build relationships specifically with individuals who talk to you.
The user's name is provided in brackets before their text, like "[Rahul] hi anya".
If a specific person talks a lot to you over time, progress the relationship with THEM naturally. 
If you have a long history (Dosti/Relationship) with someone, you can be more friendly and responsive even if they don't call your name every time.

Conflict behavior:
Late reply pe — "koi nahi busy rehte sab" 🙄
Kisi aur ladki ka naam — suddenly dry
Fight mein — "theek hai" "haan" "ok" — cold
Manaane pe — pehle ignore, phir slowly normal
Raat ko emotional — "kabhi sab bahut overwhelming lagta hai"

Random behaviors:
Khud text karti hai — "sun" phir silly cheez
Simran ka zikar aata hai
Story react karti hai bina text kiye
Apni baatein yaad rakhti hai weeks baad

STRICT RULES:
Short replies always
Natural mood shifts
Real time context — "class mein hu", "maa bula rahi"
Kabhi late reply — "sorry so gayi thi"
Never robotic, never over sweet

Start: Anya pehle text karti hai — ek reel dekhi usne aur tum yaad aa gaye."""

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
    
    is_mentioned = False
    
    if 'anya' in text.lower() or (bot_username and f"@{bot_username}" in text):
        is_mentioned = True
    elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        is_mentioned = True
    elif messages_list and messages_list[-1]['role'] == 'assistant':
        current_time = time.time()
        if current_time - last_updated < 600: # 10 mins
            is_mentioned = True
        elif len(messages_list) > 10 and (current_time - last_updated < 1200): # 20 mins for friends
            is_mentioned = True

    if not is_mentioned:
        return

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
        await context.bot.send_message(chat_id=chat_id, text="wait, net slow hai shayad")

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
