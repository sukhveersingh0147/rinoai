# ai_bot.py - Complete AI-Powered Loader Selling Assistant Bot (with MongoDB Persistence)

import os
import sys
import json # JSON serialization ke liye
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
    CallbackContext
)
import telegram.error # Error handling ke liye upar import kiya gaya
# Zaroori hai: pip install python-telegram-bot google-genai pymongo
from google import genai 
from google.genai import types
from pymongo import MongoClient # MongoDB se connect karne ke liye

# --- ⚠️ CONFIGURATION - YAHAN BADLAO KAREIN ⚠️ ---

# 1. BotFather se mila hua API Token
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7720381469:AAHtCMMhJPGUlqOqeRk3sudRdaNGZrR5Qmw")

# 2. Google AI Studio se mila hua Gemini API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAXwb0iR180WxTlISzb98rbQByfElWUmEE")

# 3. MongoDB Connection URI (Atlas ya Local Server)
# FIX: Aapko yeh URI apne MongoDB Atlas ya local server se replace karna hoga
# **IMPORTANT FIX:** Password se `<` aur `>` hataye gaye hain.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://rino:rino123@rino.5eeugze.mongodb.net/?retryWrites=true&w=majority&appName=Rino") 

# 4. Admin ki Telegram User ID
ADMIN_USER_ID = 1351184742  # Aapki set ki hui ID

# --- BRANDING & OWNER PROMOTION ---
BOT_NAME = "Rino AI Bot"
OWNER_HANDLE = "@officialrino"

# --- DATABASE & MODEL SETUP ---
DB_NAME = 'telegram_bot_db'
ADMIN_SETTINGS_COLLECTION = 'admin_settings'
CHAT_HISTORY_COLLECTION = 'user_sessions'
SETTINGS_ID = 'system_instruction' # Admin setting ka fixed document ID

CHAT_MODEL = 'gemini-2.5-flash' 

# --- GLOBAL VARIABLES & STATE MANAGEMENT ---
# Database clients initialization
mongo_client = None
db = None
client = None # Gemini client

# MongoDB aur Gemini client initialize karte hain
try:
    # MongoDB setup
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    # Check if we can connect and perform a basic operation (optional but good practice)
    # Ping the server to check connectivity
    mongo_client.admin.command('ping') 
    print("✅ MongoDB se successfully connect ho gaya.")

    # Gemini setup
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    # Agar key galat hai toh program exit kar de
    print(f"❌ FATAL ERROR: Client initialization failed. Check Keys/URI. Error: {e}")
    print("Hint: MongoDB 'bad auth' error ka matlab hai ki aapke URI mein username ya password galat hai.")
    sys.exit(1)

# Conversation History ko in-memory store karte hain (short-term for active session)
conversation_history = {}
SETTING_INSTRUCTIONS = 1

# --- DATABASE HELPER FUNCTIONS ---

def load_system_instruction():
    """MongoDB se bot ka role/instruction load karta hai."""
    try:
        settings_doc = db[ADMIN_SETTINGS_COLLECTION].find_one({'_id': SETTINGS_ID})
        if settings_doc:
            print("✅ Admin instruction MongoDB se load ho gaya.")
            return settings_doc['instruction']
        else:
            # --- DEFAULT INSTRUCTION (RINO AI BOT BRANDING AUR PROMOTION KE SAATH) ---
            default_instruction = (
                f"Tum ek loader selling group ke liye ek bahut hi helpful aur professional sales assistant ho. "
                f"Tumhara naam **{BOT_NAME}** hai. Tumhe rates, features, aur payment process mein madad karni hai. "
                f"Jab bhi koi sales ya payment ki baat kare, toh owner {OWNER_HANDLE} ka promotion zaroor karo. "
                f"Promotion: Is bot ka owner {OWNER_HANDLE} hai, jo ki is group ka main admin bhi hai. "
                f"Sales ya custom deals ke liye unse seedha contact karein. Hamesha polite aur Hindi/Hinglish mein jawab do."
            )
            return default_instruction
    except Exception as e:
        print(f"❌ MongoDB Read Error (System Instruction): {e}")
        return "You are a highly helpful and professional sales assistant in a loader selling group. Respond in Hinglish."

def save_chat_history(chat_id, history_list):
    """Chat history ko MongoDB mein save karta hai."""
    try:
        db[CHAT_HISTORY_COLLECTION].update_one(
            {'_id': chat_id},
            {'$set': {'history': history_list}},
            upsert=True # Agar document nahi hai toh naya bana dega
        )
    except Exception as e:
        print(f"❌ MongoDB Write Error (Chat History): {e}")

def load_chat_history(chat_id):
    """MongoDB se pichli chat history load karta hai."""
    try:
        session_doc = db[CHAT_HISTORY_COLLECTION].find_one({'_id': chat_id})
        if session_doc and session_doc.get('history'):
            return session_doc['history']
        return []
    except Exception as e:
        print(f"❌ MongoDB Read Error (Chat History): {e}")
        return []

# --- CORE HELPER FUNCTIONS ---

def is_admin(user_id):
    """Check karta hai ki user Admin hai ya nahi."""
    if ADMIN_USER_ID == 123456789:
        return False 
    return int(user_id) == int(ADMIN_USER_ID)

# --- TELEGRAM HANDLERS (ADMIN DM TRAINING) ---

async def get_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ko unki Telegram User ID bhejta hai."""
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"Aapki Telegram User ID hai: `{user_id}`\n\nIs ID ko `ai_bot.py` file mein `ADMIN_USER_ID` ki jagah use karein.", 
        parse_mode='Markdown'
    )

async def start_setting_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin se naye System Instructions lene ki prakriya shuru karta hai."""
    if update.message.chat.type != 'private' or not is_admin(update.effective_user.id):
        return ConversationHandler.END 
    
    await update.message.reply_text(
        "नमस्ते Admin. Ab aap naye **System Instructions** bhej sakte hain.\n"
        "Yeh instruction MongoDB mein save hoga aur bot ka role define karega.\n\n"
        "Jab aap instruction type kar lein, toh bhej dein. Agar cancel karna hai toh /cancel type karein."
    )
    
    return SETTING_INSTRUCTIONS

async def receive_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin dwara bheje gaye instructions ko MongoDB mein save karta hai."""
    new_instructions = update.message.text
    
    try:
        # MongoDB mein instruction save/update karte hain
        db[ADMIN_SETTINGS_COLLECTION].update_one(
            {'_id': SETTINGS_ID},
            {'$set': {'instruction': new_instructions}},
            upsert=True
        )
        
        # Sabhi chats ki history in-memory aur DB dono se clear karte hain taki naye settings apply ho
        conversation_history.clear()
        db[CHAT_HISTORY_COLLECTION].delete_many({})

        await update.message.reply_text(
            f"✅ **Success!** Naye System Instructions MongoDB mein save ho chuke hain.\n"
            "Sabhi chats ki history reset ho gayi hai. Bot ab naye role ke hisaab se respond karega."
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ MongoDB Write Error: {e}")

    return ConversationHandler.END

async def cancel_setting_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin training ko cancel karta hai."""
    if update.message.chat.type != 'private' or not is_admin(update.effective_user.id):
        return ConversationHandler.END
        
    await update.message.reply_text("Instruction update cancel kar diya gaya hai.")
    return ConversationHandler.END

# --- TELEGRAM HANDLERS (GROUP & PRIVATE CHAT) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ke shuru hone par welcome message deta hai."""
    bot_link = f"https://t.me/{context.bot.username}"
    
    if update.message.chat.type == 'private':
         await update.message.reply_text(
            f'नमस्ते! मैं **{BOT_NAME}** हूँ, आपके Loader Selling Group का AI सहायक बॉट।\n'
            'Main group mein aapke sawalon ka jawab de sakta hoon.\n\n'
            f'Sales ya custom deals ke liye owner **{OWNER_HANDLE}** se seedha contact karein.\n\n'
            'Agar aap bot ko kisi aur group mein add karna chahte hain, toh is link ka use karein: [Add to Group]('
            f"{bot_link}?startgroup=true"
            ').\n\n'
            'Admin ke liye: `/set_instructions` (sirf DM mein)'
            , parse_mode='Markdown'
        )
    else: # Group chat
         await update.message.reply_text(
            f'नमस्ते! Main **{BOT_NAME}** hoon, aapke loader selling group ka AI assistant.\n'
            'Loader rates, features, ya kisi aur sawal ke liye mujhe **@mention** karein ya seedha message bhej dein.'
        )

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User message ko Gemini API ke paas bhejta hai aur jawab wapas bhejta hai."""
    chat_id = str(update.message.chat_id) # MongoDB IDs ke liye string use karte hain
    user_message = update.message.text
    
    bot_username = context.bot.username
    if update.message.chat.type == 'group':
        if not (f'@{bot_username}' in user_message or user_message.startswith(bot_username)):
            return 

    # History/Session Load Logic
    if chat_id not in conversation_history:
        # 1. System instruction MongoDB se load karte hain
        system_instruction = load_system_instruction()
        
        # 2. Pichli history MongoDB se load karte hain
        history_parts = load_chat_history(chat_id)
        
        # 3. Naya chat session create karte hain with loaded history
        chat_session = client.chats.create(
            model=CHAT_MODEL, 
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            ),
            # Loaded history ko list of Content objects mein convert karna padega
            history=history_parts 
        )
        conversation_history[chat_id] = chat_session
    
    chat_session = conversation_history[chat_id]
    
    try:
        # Gemini API call
        response = chat_session.send_message(user_message)
        
        # FIX: send_message directly use karte hain to avoid reply_text error
        await context.bot.send_message(chat_id=chat_id, text=response.text)

        # 4. Success ke baad, updated history ko MongoDB mein save karte hain
        # History objects ko simple dicts mein convert karte hain for MongoDB serialization
        history_to_save = [
            {'role': message.role, 'parts': [{'text': part.text} for part in message.parts]}
            for message in chat_session.get_history()
        ]
        save_chat_history(chat_id, history_to_save)

    except telegram.error.BadRequest as e:
        print(f"Telegram BadRequest Error for chat {chat_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Maaf kijiye, ek choti si gadbadi hui, lekin main phir se try karunga.")

    except Exception as e:
        print(f"General Error for chat {chat_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Maaf kijiye, abhi AI server se connect nahi ho pa raha ya network slow hai. Kripya thodi der baad koshish karein.")

# --- RESET COMMAND ---
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Current chat ki history in-memory aur database se clear karta hai."""
    chat_id = str(update.message.chat_id)
    
    if chat_id in conversation_history:
        del conversation_history[chat_id]
        
        # Database se bhi history delete karte hain
        try:
            db[CHAT_HISTORY_COLLECTION].delete_one({'_id': chat_id})
            await update.message.reply_text("✅ Chat history database aur memory se clear kar di gayi hai. Aap ek naya topic shuru kar sakte hain.")
        except Exception as e:
            print(f"❌ MongoDB Delete Error on reset: {e}")
            await update.message.reply_text("⚠️ Chat memory clear ho gayi, lekin database se delete karte samay error aaya.")
    else:
        await update.message.reply_text("Koi active chat history nahi thi.")
        
# --- GLOBAL ERROR HANDLER ---

async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a message to the admin."""
    print(f"🔥 Update {update} caused error {context.error}")

    if ADMIN_USER_ID and ADMIN_USER_ID != 123456789:
        error_message = f"🚨 Bot Error:\n\nError: {context.error}"
        try:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=error_message)
        except Exception as e:
            print(f"Could not send error message to admin: {e}")

# --- MAIN APPLICATION ENTRY POINT ---

def main():
    """Bot application ko chalaane ka main function."""
    print("🚀 Rino AI Bot shuru ho raha hai...")
    
    # Essential checks for token validity
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ ERROR: TELEGRAM_BOT_TOKEN ki value missing ya galat hai.")
        sys.exit(1)
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("❌ ERROR: GEMINI_API_KEY ki value missing ya galat hai.")
        sys.exit(1)
    if MONGO_URI == "mongodb://localhost:27017/":
        print("⚠️ WARNING: MONGO_URI default par set hai. Agar aap MongoDB Atlas use kar rahe hain, toh isko badlein.")
    if ADMIN_USER_ID == 123456789:
        print("⚠️ WARNING: ADMIN_USER_ID placeholder value (123456789) par set hai. Admin features kaam nahi karenge.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # 1. Add Global Error Handler (Top priority)
    application.add_error_handler(error_handler)
    
    # 2. Admin Training Conversation Handler
    admin_training_handler = ConversationHandler(
        entry_points=[
            CommandHandler("set_instructions", start_setting_instructions, filters=filters.User(ADMIN_USER_ID) & filters.ChatType.PRIVATE)
        ],
        states={
            SETTING_INSTRUCTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_instructions)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_setting_instructions, filters=filters.User(ADMIN_USER_ID) & filters.ChatType.PRIVATE)
        ]
    )
    
    # 3. Add Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command)) # FIXED: reset_command ab defined hai
    application.add_handler(CommandHandler("get_my_id", get_id_command))
    application.add_handler(admin_training_handler)
    
    # 4. Main AI Response Handler (Hamesha last mein rakhein)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    
    print("✅ Polling shuru. Rino AI Bot ab Telegram messages ka intezaar kar raha hai...")
    application.run_polling(poll_interval=3, close_loop=False)

if __name__ == '__main__':
    import telegram.error
    main()
