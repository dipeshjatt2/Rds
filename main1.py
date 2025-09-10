import os
import sqlite3
import logging
import random
import asyncio
import aiohttp
import html
import re
import json
import io
import time
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.enums import ParseMode, ChatMemberStatus, PollType
from pyrogram.errors import UserNotParticipant

# ------------------------------------------------------------------------------------ #
#                                     ── CONFIG ──                                     #
# ------------------------------------------------------------------------------------ #

# --- Basic Bot Config ---
API_ID = 22118129
API_HASH = "43c66e3314921552d9330a4b05b18800"
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# --- Userbot Config (for /poll2txt) ---
SESSION_STRING = os.environ.get("SESSION_STRING")

# --- AI Config ---
GEMINI_API_KEY = os.environ.get("aikey")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
STYLISH_SIGNATURE = "@andr0ipie9"

# --- Admin Config ---
ADMIN_IDS = [5203820046]

# --- Force Subscription ---
# Add your channel usernames (e.g., "my_channel") or public/private channel IDs.
FORCE_SUB_CHANNELS = {
    1: "python_noobx",
    2: "",  # Keep empty if not used
    3: "",
    4: "",
    5: ""
}

# --- Points System Config ---
REFERRAL_POINTS = 5
CMD_COST = 5  # Cost for using any main feature command
BONUS_MIN_POINTS = 1
BONUS_MAX_POINTS = 10
BONUS_COOLDOWN_HOURS = 24

# --- Other ---
TEMPLATE_HTML = "format2.html" # This HTML file must be in the same directory

# --- Initialize Bot ---
app = Client("combined_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global State ---
user_state = {}  # Tracks interactive command flows (e.g., for /htmk)
user_sessions = {} # Tracks active /poll2txt scraping sessions

# ------------------------------------------------------------------------------------ #
#                                 ── DATABASE SETUP ──                                 #
# ------------------------------------------------------------------------------------ #

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            points INTEGER DEFAULT 10,
            verified BOOLEAN DEFAULT FALSE,
            last_bonus_claimed TIMESTAMP
        )
    ''')
    # Referrals table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    ''')
    # Redeem codes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            points INTEGER,
            max_uses INTEGER,
            uses INTEGER DEFAULT 0,
            created_by INTEGER
        )
    ''')
    # Track who used which code
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS redeemed_users (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def get_db_connection():
    return sqlite3.connect('bot_database.db')

def add_user(user_id: int, username: str, first_name: str, last_name: str = ""):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
        (user_id, username, first_name, last_name)
    )
    conn.commit()
    conn.close()

def get_user_points(user_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_user_points(user_id: int, points: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET points = points + ? WHERE user_id = ?',
        (points, user_id)
    )
    conn.commit()
    conn.close()

def set_user_verified(user_id: int, status: bool = True):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET verified = ? WHERE user_id = ?', (status, user_id)
    )
    conn.commit()
    conn.close()

def add_referral(referrer_id: int, referred_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
            (referrer_id, referred_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError: # referred_id is UNIQUE
        return False
    finally:
        conn.close()

def get_referral_count(user_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def create_redeem_code(code: str, points: int, max_uses: int, created_by: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO redeem_codes (code, points, max_uses, created_by) VALUES (?, ?, ?, ?)',
        (code, points, max_uses, created_by)
    )
    conn.commit()
    conn.close()

def get_redeem_code(code: str) -> Optional[Tuple]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, points, max_uses, uses FROM redeem_codes WHERE code = ?', (code,))
    result = cursor.fetchone()
    conn.close()
    return result

def use_redeem_code(user_id: int, code: str) -> bool:
    """Marks a code as used by a user and increments the use count."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if user already redeemed this code
        cursor.execute('SELECT 1 FROM redeemed_users WHERE user_id = ? AND code = ?', (user_id, code))
        if cursor.fetchone():
            return False # Already redeemed

        cursor.execute('INSERT INTO redeemed_users (user_id, code) VALUES (?, ?)', (user_id, code))
        cursor.execute('UPDATE redeem_codes SET uses = uses + 1 WHERE code = ?', (code,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error using redeem code: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_last_bonus_claim(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET last_bonus_claimed = ? WHERE user_id = ?',
        (datetime.now(), user_id)
    )
    conn.commit()
    conn.close()

def can_claim_bonus(user_id: int) -> Tuple[bool, Optional[timedelta]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT last_bonus_claimed FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        last_claimed_time = datetime.strptime(result[0].split('.')[0], '%Y-%m-%d %H:%M:%S')
        cooldown = timedelta(hours=BONUS_COOLDOWN_HOURS)
        if datetime.now() > last_claimed_time + cooldown:
            return True, None
        else:
            time_left = (last_claimed_time + cooldown) - datetime.now()
            return False, time_left
    return True, None # Never claimed before


# ------------------------------------------------------------------------------------ #
#                               ── UTILITY FUNCTIONS ──                                #
# ------------------------------------------------------------------------------------ #

# --- Force Sub & Points Utilities ---
def generate_redeem_code(length=8):
    import string
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def check_user_joined_channel(user_id: int, channel: str) -> bool:
    try:
        await app.get_chat_member(channel, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Error checking channel '{channel}': {e}")
        return False # Assume not joined if there's an error

async def check_all_channels(user_id: int) -> List[Tuple[int, str]]:
    unjoined_channels = []
    active_channels = {k: v for k, v in FORCE_SUB_CHANNELS.items() if v}
    if not active_channels:
        return [] # No force sub configured
        
    for idx, channel in active_channels.items():
        if not await check_user_joined_channel(user_id, channel):
            unjoined_channels.append((idx, channel))
    return unjoined_channels

def create_force_sub_keyboard(unjoined_channels: List[Tuple[int, str]]) -> InlineKeyboardMarkup:
    keyboard = []
    for idx, channel in unjoined_channels:
        url = f"https://t.me/{channel.lstrip('@')}"
        keyboard.append([InlineKeyboardButton(f"➡️ Join Channel {idx}", url=url)])
    keyboard.append([InlineKeyboardButton("✅ I Have Joined", callback_data="verify_joined")])
    return InlineKeyboardMarkup(keyboard)

def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus"), InlineKeyboardButton("💰 My Points", callback_data="my_points")],
        [InlineKeyboardButton("🛒 Buy Points", url="https://t.me/andr0idpie9")] # Update with your username
    ]
    return InlineKeyboardMarkup(keyboard)

async def is_authorized_and_has_points(message: Message) -> bool:
    """A single function to check force sub and points before running a command."""
    user_id = message.from_user.id
    
    # 1. Check Force Subscription
    unjoined = await check_all_channels(user_id)
    if unjoined:
        keyboard = create_force_sub_keyboard(unjoined)
        await message.reply_text(
            "**Hold on!** 🛑\n\nYou must join our channel(s) to use my commands.\n\n"
            "Please join the channel(s) below and then click the verify button.",
            reply_markup=keyboard
        )
        return False
        
    # 2. Check Points
    current_points = get_user_points(user_id)
    if current_points < CMD_COST:
        await message.reply_text(
            f"**Insufficient Points!** 😥\n\n"
            f"You need **{CMD_COST} points** to use this command, but you only have **{current_points} points**.\n\n"
            "You can earn more points via referrals, daily bonuses, or by redeeming a code."
        )
        return False
        
    # 3. Deduct Points and Proceed
    update_user_points(user_id, -CMD_COST)
    await message.reply_text(f"✅ Access granted! **{CMD_COST} points** have been deducted. Your new balance is **{current_points - CMD_COST}**.", quote=True, parse_mode=ParseMode.MARKDOWN)
    return True

# --- Parsing & HTML Helpers ---
def parse_format_dash(txt: str):
    """Q#: ... with dash-prefixed options and Ex: explanation"""
    questions = []
    blocks = re.split(r'(?m)^Q\d+:\s', txt)
    for block in blocks:
        if not block.strip():
            continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        qtext = lines[0]
        opts = []
        correct = -1
        explanation = ""
        for i, l in enumerate(lines[1:]):
            if l.startswith("-"):
                option_text = l.lstrip("-").strip()
                has_tick = "✅" in option_text
                option_text = option_text.replace("✅", "").strip()
                opts.append(option_text)
                if has_tick:
                    correct = len(opts) - 1
            elif l.lower().startswith("ex:"):
                explanation = re.sub(r'(?i)^ex:\s*', '', l).strip()
        questions.append({
            "text": qtext,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })
    return questions

def parse_format1(txt: str):
    """Definition style, supports (a)(b)(c)... unlimited"""
    questions = []
    chunks = re.split(r'(?m)^\s*\d+\.\s', txt)
    chunks = [c.strip() for c in chunks if c.strip()]
    for chunk in chunks:
        # Split at the first option like (a) or (b)
        m_def = re.split(r'\s*\([a-zA-Z]\)', chunk, maxsplit=1)
        if len(m_def) < 2:
            continue
        definition = m_def[0].strip()
        opts = []
        correct = -1
        # Find all options and the explanation
        for match in re.finditer(r'\(([a-zA-Z])\)\s*(.*?)(?=(\([a-zA-Z]\)|Ex:|$))', chunk, flags=re.S):
            raw = match.group(2).strip()
            has_tick = '✅' in raw
            raw = raw.replace('✅', '').strip()
            opts.append(raw)
            if has_tick:
                correct = len(opts) - 1
        m_ex = re.search(r'Ex\s*:\s*[“"]?(.*?)[”"]?\s*$', chunk, flags=re.S)
        explanation = m_ex.group(1).strip() if m_ex else ""
        questions.append({
            "text": definition,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })
    return questions

def parse_format2(txt: str):
    """Numbered + a) b) style"""
    questions = []
    blocks = re.split(r'(?m)^\d+\.\s*', txt)
    for block in blocks:
        if not block.strip():
            continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        qtext = lines[0]
        opts = []
        correct = -1
        for i, l in enumerate(lines[1:]):
            has_tick = '✅' in l
            l = l.replace('✅', '').strip()
            if re.match(r'^[a-fA-F]\)', l):
                l = l[2:].strip()
                opts.append(l)
                if has_tick:
                    correct = len(opts) - 1
        questions.append({"text": qtext, "options": opts, "correctIndex": correct, "explanation": "", "reference": ""})
    return questions

def parse_format3(txt: str):
    """Direct JSON quizData"""
    try:
        m = re.search(r'const\s+quizData\s*=\s*({.*});', txt, flags=re.S)
        if not m:
            return []
        obj = json.loads(m.group(1))
        return obj.get("questions", [])
    except Exception:
        return []

def parse_format4(txt: str):
    """Q + options line by line, blank line separates questions"""
    questions = []
    blocks = re.split(r'\n\s*\n', txt.strip())
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        qtext = lines[0]
        opts = []
        correct = -1
        for i, l in enumerate(lines[1:]):
            has_tick = '✅' in l
            l = l.replace('✅', '').strip()
            opts.append(l)
            if has_tick:
                correct = i
        questions.append({"text": qtext, "options": opts, "correctIndex": correct, "explanation": "", "reference": ""})
    return questions

def parse_csv(path: str):
    """CSV format parser"""
    questions = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            opts = []
            for i in range(1, 11):  # support up to 10 options
                val = row.get(f"Option {i}", "")
                if val and val.strip():
                    opts.append(val.strip())
            try:
                correct_idx = int(row.get("Correct Index", 0)) - 1
            except (ValueError, TypeError):
                correct_idx = 0
            
            if not (0 <= correct_idx < len(opts)):
                correct_idx = 0

            questions.append({
                "text": row.get("Question (Exam Info)", "").strip(),
                "options": opts,
                "correctIndex": correct_idx,
                "explanation": row.get("Explanation", "").strip(),
                "reference": ""
            })
    return questions

def detect_and_parse(txt: str):
    if "const quizData" in txt:
        return parse_format3(txt)
    if "Definition:" in txt or re.search(r'\([a-zA-Z]\)', txt):
        return parse_format1(txt)
    if re.search(r'^\s*\d+\.\s+.*\na\)', txt, flags=re.M):
        return parse_format2(txt)
    if re.search(r'(?m)^Q\d+:\s', txt) and "-" in txt:
        return parse_format_dash(txt)
    if '✅' in txt and '\n\n' in txt: # Likely format 4
         return parse_format4(txt)
    return []

def replace_questions_in_template(html: str, questions, minutes: int, negative: float):
    questions_js = json.dumps(questions, ensure_ascii=False, indent=2)
    new_settings_and_questions = (
        f"const quizData = {{\n"
        f"  settings: {{ totalTimeSec: {minutes * 60}, negativeMarkPerWrong: {negative} }},\n"
        f"  questions: {questions_js}\n"
        f"}};"
    )
    
    # Replace the entire quizData block
    updated_html = re.sub(
        r'const\s+quizData\s*=\s*{.*?};',
        new_settings_and_questions,
        html,
        flags=re.DOTALL
    )
    return updated_html


# ------------------------------------------------------------------------------------ #
#                                  ── BOT HANDLERS ──                                  #
# ------------------------------------------------------------------------------------ #

# --- Main & Core Handlers ---

@app.on_message(filters.command(["start", "help"]))
async def start_handler(client, message: Message):
    user = message.from_user
    add_user(user.id, user.username, user.first_name, user.last_name or "")
    
    # Handle referral
    if len(message.command) > 1:
        try:
            referrer_id = int(message.command[1])
            if referrer_id != user.id:
                if add_referral(referrer_id, user.id):
                    update_user_points(referrer_id, REFERRAL_POINTS)
                    await message.reply_text(f"Welcome! You were referred and have started with extra points.")
                    try:
                        await client.send_message(
                            referrer_id,
                            f"🎉 Congratulations! {user.first_name} joined using your referral link. You've earned {REFERRAL_POINTS} points!"
                        )
                    except Exception as e:
                        logger.warning(f"Could not notify referrer {referrer_id}: {e}")
        except ValueError:
            pass # Invalid referral code

    # Check force subscription
    unjoined = await check_all_channels(user.id)
    if unjoined:
        keyboard = create_force_sub_keyboard(unjoined)
        await message.reply_text(
            "**Welcome!** 👋\n\nTo use this bot, you must first join our partner channel(s). "
            "It helps us keep the service free!\n\nPlease join and then click 'I Have Joined'.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        set_user_verified(user.id, False)
    else:
        set_user_verified(user.id, True)
        await message.reply_text(
            f"**Welcome back, {user.first_name}!** ✅\n\n"
            "You are all set! Here's what I can do:\n\n"
            "» **/htmk**: Convert a `.txt` or `.csv` file into an HTML quiz.\n"
            "» **/shufftxt**: Shuffle questions and options in a quiz file.\n"
            "» **/txqz**: Send quiz questions from text as native Telegram polls.\n"
            "» **/poll2txt**: Scrape polls from a channel into a text file.\n"
            "» **/ai**: Generate MCQs on any topic using AI.\n"
            "» **/arrange**: Reformat unstructured text into a clean quiz format using AI.\n\n"
            f"Each command costs **{CMD_COST} points**. Use the menu below to manage your points.",
            reply_markup=create_main_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

@app.on_callback_query(filters.regex("^verify_joined$"))
async def verify_joined_handler(client, callback_query: CallbackQuery):
    user = callback_query.from_user
    unjoined = await check_all_channels(user.id)
    
    if unjoined:
        await callback_query.answer("You haven't joined all the required channels yet. Please join them and try again.", show_alert=True)
    else:
        set_user_verified(user.id, True)
        # Re-trigger start handler to show the main menu
        await callback_query.message.delete()
        # Create a fake message object to pass to start_handler
        class FakeMessage:
            def __init__(self, user, reply_method):
                self.from_user = user
                self.command = ['start']
                self.reply_text = reply_method
        
        await start_handler(client, FakeMessage(user, callback_query.message.reply_text))

# --- Points & Referral Callback Handlers ---

@app.on_callback_query(filters.regex("^referral_link$"))
async def referral_link_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    bot_username = (await app.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    referral_count = get_referral_count(user_id)
    total_earned = referral_count * REFERRAL_POINTS
    
    text = (
        f"🔗 **Your Referral Link** 🔗\n\n"
        f"`{referral_link}`\n\n"
        f"Share this link with your friends. You'll get **{REFERRAL_POINTS} points** for each user who joins!\n\n"
        f"👥 **Total Referrals:** {referral_count}\n"
        f"💰 **Total Earned:** {total_earned} points"
    )
    await callback_query.answer(text, show_alert=True, cache_time=5)


@app.on_callback_query(filters.regex("^daily_bonus$"))
async def daily_bonus_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    can_claim, time_left = can_claim_bonus(user_id)
    
    if can_claim:
        bonus_points = random.randint(BONUS_MIN_POINTS, BONUS_MAX_POINTS)
        update_user_points(user_id, bonus_points)
        update_last_bonus_claim(user_id)
        current_points = get_user_points(user_id)
        await callback_query.answer(
            f"🎉 You claimed your daily bonus of {bonus_points} points!\n\n"
            f"Your new balance is {current_points} points.",
            show_alert=True
        )
    else:
        hours, rem = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        await callback_query.answer(
            f"You have already claimed your bonus. Please wait {hours}h {minutes}m to claim again.",
            show_alert=True
        )

@app.on_callback_query(filters.regex("^my_points$"))
async def my_points_handler(client, callback_query: CallbackQuery):
    points = get_user_points(callback_query.from_user.id)
    await callback_query.answer(f"You currently have {points} points.", show_alert=True)

# --- Command Handlers ---

@app.on_message(filters.command("redeem"))
async def redeem_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: `/redeem YOUR_CODE`")
        return
        
    user_id = message.from_user.id
    code_str = message.command[1]
    
    code_data = get_redeem_code(code_str)
    if not code_data:
        await message.reply_text("❌ Invalid redeem code.")
        return
        
    code, points, max_uses, uses = code_data
    if uses >= max_uses:
        await message.reply_text("❌ This code has reached its maximum usage limit.")
        return
        
    if use_redeem_code(user_id, code):
        update_user_points(user_id, points)
        await message.reply_text(f"✅ Success! **{points} points** have been added to your account.")
    else:
        await message.reply_text("❌ You have already redeemed this code.")

# --- PROTECTED FEATURE HANDLERS ---

@app.on_message(filters.command("shufftxt"))
async def shufftxt_handler(client, message: Message):
    if not await is_authorized_and_has_points(message):
        return
    
    target_msg = None
    if message.reply_to_message and message.reply_to_message.document:
        target_msg = message.reply_to_message
    elif message.document:
        target_msg = message
    else:
        await message.reply_text(
            "⚠️ Please reply to a `.txt` or `.csv` file with `/shufftxt`, or send the file with the command as a caption."
        )
        return

    file_path = await target_msg.download()
    
    try:
        if file_path.lower().endswith(".csv"):
            questions = parse_csv(file_path)
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            questions = detect_and_parse(content)
        
        if not questions:
            await message.reply_text("❌ Could not parse any questions from the file. Please check the format.")
            return
            
        random.shuffle(questions) # Shuffle question order
        
        output_lines = []
        for i, q in enumerate(questions, 1):
            output_lines.append(f"{i}. {q['text']}")
            
            # Reverse options and adjust correct index
            original_options = q['options']
            original_correct_index = q['correctIndex']
            
            shuffled_options = original_options[::-1]
            new_correct_index = (len(original_options) - 1) - original_correct_index

            for j, opt in enumerate(shuffled_options):
                mark = "✅" if j == new_correct_index else ""
                output_lines.append(f"({chr(97+j)}) {opt} {mark}")
            
            if q.get('explanation'):
                output_lines.append(f"Ex: {q['explanation']}")
            
            output_lines.append("") # Blank line separator
            
        output_content = "\n".join(output_lines)
        
        output_file = io.BytesIO(output_content.encode('utf-8'))
        output_file.name = f"shuffled_{os.path.basename(file_path)}"
        
        await message.reply_document(output_file, caption="✅ Here is your shuffled quiz file.")
        
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.on_message(filters.command("htmk"))
async def htmk_command_handler(client, message: Message):
    if not await is_authorized_and_has_points(message):
        return
        
    user_state[message.from_user.id] = {"flow": "html", "step": "waiting_for_file"}
    await message.reply_text(
        "✅ OK! Please send me the `.txt` or `.csv` file you want to convert to an HTML quiz."
    )
    
@app.on_message(filters.command("txqz"))
async def txqz_handler(client, message: Message):
    if not await is_authorized_and_has_points(message):
        return

    content = None
    if message.reply_to_message:
        if message.reply_to_message.text:
            content = message.reply_to_message.text
        elif message.reply_to_message.document:
            try:
                file_path = await message.reply_to_message.download()
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                os.remove(file_path)
            except Exception as e:
                await message.reply_text(f"❌ Error downloading document: {str(e)}")
                return
    
    if not content:
        await message.reply_text("⚠️ Please reply to a text message or a `.txt` document with `/txqz`.")
        return
        
    questions = detect_and_parse(content)
    if not questions:
        await message.reply_text("❌ Could not parse any questions from the provided text.")
        return

    await message.reply_text(f"✅ Found {len(questions)} questions. I will now send them as polls.")

    for i, q in enumerate(questions):
        if not q.get('options') or q.get('correctIndex', -1) == -1:
            await message.reply_text(f"Skipping question {i+1} due to missing options or correct answer.")
            continue
            
        try:
            await client.send_poll(
                chat_id=message.chat.id,
                question=q['text'],
                options=q['options'],
                type=PollType.QUIZ,
                correct_option_id=q['correctIndex'],
                explanation=q.get('explanation', '')
            )
            await asyncio.sleep(1) # Avoid rate limits
        except Exception as e:
            await message.reply_text(f"❌ Failed to send question {i+1}: {e}")
            break

@app.on_message(filters.command("poll2txt"))
async def poll2txt_handler(client, message: Message):
    # This command doesn't cost points to initiate, as it requires a userbot
    # The actual scraping and file generation can be considered the "costly" part
    # For simplicity, we'll keep it free for now.
    user_id = message.from_user.id
    if not SESSION_STRING:
        await message.reply_text("❌ **Userbot Not Configured!**\n\nThis feature is disabled because the bot owner has not configured a Userbot session.")
        return
        
    if not message.reply_to_message:
        await message.reply_text("⚠️ **Usage:**\nReply to the *first message* of a quiz (e.g., a 'Start Quiz' button message from a bot) with the command `/poll2txt`.")
        return
        
    if user_id in user_sessions and user_sessions[user_id].get('is_running', False):
        await message.reply_text("⚠️ You already have a scraping session in progress. Please wait for it to finish.")
        return

    # Userbot logic would be here. As it's complex and requires a separate client,
    # we'll just show a placeholder message for this implementation.
    await message.reply_text("⚙️ **Poll Scraper Initiated**\n\nA userbot would now start scraping the polls. This feature requires complex implementation with a second Pyrogram client and is not fully included in this script.")

@app.on_message(filters.command("ai"))
async def ai_handler(client, message: Message):
    if not await is_authorized_and_has_points(message):
        return

    if not GEMINI_API_KEY:
        await message.reply_text("❌ AI Error: `GEMINI_API_KEY` is not configured by the bot owner.")
        return

    try:
        parts = re.findall(r'"([^"]*)"|(\S+)', message.text)
        args = [p[0] or p[1] for p in parts][1:] # [1:] to skip the command itself

        if len(args) < 2:
            raise ValueError("Not enough arguments")

        topic = args[0]
        num_questions = int(args[1])
        language = args[2] if len(args) > 2 else "English"

    except (ValueError, IndexError):
        await message.reply_text(
            "**Invalid Format!** Please use the correct format.\n\n"
            "**Usage:**\n"
            '`/ai "Your Topic" <Number of Questions> "Language"`\n\n'
            "**Examples:**\n"
            '`/ai "Indian History" 10 "Hindi"`\n'
            '`/ai "Quantum Physics" 5 "English"`'
        )
        return

    if not (1 <= num_questions <= 50):
        await message.reply_text("❌ Please specify a number of questions between 1 and 50.")
        return

    status_msg = await message.reply_text(f"🧠 Generating **{num_questions}** MCQs about **{topic}** in **{language}**... Please wait.")

    prompt = f"""
    You are an expert MCQ generator for competitive exams. Generate exactly {num_questions} high-quality multiple-choice questions about the topic "{topic}" in the specified language: "{language}".

    **Strict Rules:**
    1. Each question must be numbered (1., 2., etc.).
    2. Each question must have exactly 4 options: (a), (b), (c), (d).
    3. Place a ✅ emoji **immediately after** the text of the single correct option.
    4. The position of the correct option (✅) must be randomized across questions.
    5. After the options, add a brief explanation prefixed with "Ex:".
    6. Every explanation **MUST** end with the signature: {STYLISH_SIGNATURE}
    7. The entire output must be a single markdown code block (```).
    8. If the language is bilingual (e.g., "Hindi and English"), provide the question and options in both languages using slashes.

    **Example Format:**
    ```
    1. Who founded the Tughlaq Dynasty? / तुग़लक वंश की स्थापना किसने की?
    (a) Alauddin Khilji / अलाउद्दीन खिलजी
    (b) Ghiyasuddin Tughlaq / घियासुद्दीन तुग़लक ✅
    (c) Bahlol Lodhi / बहलोल लोधी
    (d) Khizr Khan / खिज़र खान
    Ex: Ghiyasuddin Tughlaq founded the dynasty in 1320. {STYLISH_SIGNATURE}
    ```
    """

    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {'Content-Type': 'application/json'}
        params = {'key': GEMINI_API_KEY}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    generated_text = data['candidates'][0]['content']['parts'][0]['text']
                    await status_msg.edit_text(generated_text)
                else:
                    error_text = await response.text()
                    await status_msg.edit_text(f"❌ **API Error:** Failed to generate MCQs. Status: {response.status}\n\n`{error_text}`")

    except Exception as e:
        await status_msg.edit_text(f"❌ An unexpected error occurred: {e}")

@app.on_message(filters.command("arrange"))
async def arrange_handler(client, message: Message):
    if not await is_authorized_and_has_points(message):
        return

    if not GEMINI_API_KEY:
        await message.reply_text("❌ AI Error: `GEMINI_API_KEY` is not configured by the bot owner.")
        return

    if not (message.reply_to_message and message.reply_to_message.document):
        await message.reply_text("⚠️ Please reply to a `.txt` file with the `/arrange` command.")
        return

    doc = message.reply_to_message.document
    if doc.file_size > 80 * 1024: # 80 KB limit
        await message.reply_text("❌ File is too large. Please use a file smaller than 80 KB.")
        return

    status_msg = await message.reply_text("📥 Downloading and processing file...")
    file_path = await message.reply_to_message.download()

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw_text_content = f.read()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error reading file: {e}")
        return
    finally:
        os.remove(file_path)

    await status_msg.edit_text("🤖 Sending content to AI for reformatting... Please wait.")

    prompt = f"""
    You are a data formatting expert. Your task is to convert the raw text data provided below into a clean, numbered list of quiz questions.

    **REQUIRED OUTPUT FORMAT RULES:**
    - Each question must be numbered (1., 2., etc.).
    - Each question must have all its options listed below it, prefixed with (a), (b), (c), (d), etc.
    - You **MUST** identify the single correct option for each question and place a ✅ emoji right after it.
    - The position of the correct answer (✅) should be varied across questions.
    - After the options, you **MUST** include a brief explanation prefixed with "Ex:". If no explanation is in the source, create a concise one.
    - Every explanation line **MUST** end with the signature: {STYLISH_SIGNATURE}
    - The entire output **MUST** be enclosed in a single markdown code block (```).

    ---
    **RAW TEXT CONTENT TO REFORMAT:**
    ---
    {raw_text_content}
    ---

    Now, arrange the text above according to all the rules specified.
    """

    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {'Content-Type': 'application/json'}
        params = {'key': GEMINI_API_KEY}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    arranged_text = data['candidates'][0]['content']['parts'][0]['text']
                    await status_msg.edit_text(arranged_text)
                else:
                    error_text = await response.text()
                    await status_msg.edit_text(f"❌ **API Error:** Failed to arrange text. Status: {response.status}\n\n`{error_text}`")
    except Exception as e:
        await status_msg.edit_text(f"❌ An unexpected error occurred: {e}")
    
# --- Document Handler for /htmk flow ---

@app.on_message(filters.document, group=1)
async def document_handler(client, message: Message):
    uid = message.from_user.id
    if user_state.get(uid, {}).get("flow") != "html":
        return  # This file is not for us, ignore it.

    # Check if the template file exists
    if not os.path.exists(TEMPLATE_HTML):
        await message.reply_text(f"❌ **Configuration Error:** The template file `{TEMPLATE_HTML}` was not found on the server.")
        user_state.pop(uid, None)
        return

    file_path = await message.download()
    
    try:
        # Determine parser based on file extension
        if file_path.lower().endswith(".csv"):
            questions = parse_csv(file_path)
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            questions = detect_and_parse(content)

        if not questions:
            await message.reply_text("❌ Could not parse any questions from the file. Please ensure it is in a supported format.")
            return

        user_state[uid]['questions'] = questions
        user_state[uid]['step'] = 'waiting_for_time'
        await message.reply_text(
            f"✅ Successfully parsed **{len(questions)}** questions!\n\n"
            "Now, please enter the total time for the quiz in **minutes**."
        )

    except Exception as e:
        await message.reply_text(f"An error occurred while processing the file: {e}")
        user_state.pop(uid, None) # Reset state on error
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# --- Text Message Handler for state machine (/htmk flow) ---

@app.on_message(
    filters.text & ~filters.command([
        "start", "help", "redeem", "shufftxt", "htmk", "txqz",
        "poll2txt", "ai", "arrange", "gen"
    ]),
    group=2
)
async def text_handler_for_flow(client, message: Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
        
    state = user_state[uid]
    
    if state.get("flow") == "html":
        if state.get("step") == 'waiting_for_time':
            try:
                minutes = int(message.text)
                if not (1 <= minutes <= 180):
                    raise ValueError("Time out of range")
                state['minutes'] = minutes
                state['step'] = 'waiting_for_negative'
                await message.reply_text("✅ Time set!\n\nNow, enter the negative marking for each wrong answer (e.g., `0.25`, `1`, or `0` for no negative marking).")
            except ValueError:
                await message.reply_text("❌ Invalid input. Please enter a whole number for minutes (e.g., 30).")

        elif state.get("step") == 'waiting_for_negative':
            try:
                negative = float(message.text)
                if not (0 <= negative <= 10):
                    raise ValueError("Negative marking out of range")
                    
                await message.reply_text("⏳ Generating your HTML file...")
                
                with open(TEMPLATE_HTML, 'r', encoding='utf-8') as f:
                    template_content = f.read()

                final_html = replace_questions_in_template(template_content, state['questions'], state['minutes'], negative)
                
                output_file = io.BytesIO(final_html.encode('utf-8'))
                output_file.name = "quiz.html"
                
                await message.reply_document(output_file, caption=f"✅ Your HTML quiz is ready!\n\n**Time:** {state['minutes']} mins\n**Negative Marking:** {negative}")
                user_state.pop(uid, None) # End of flow

            except ValueError:
                await message.reply_text("❌ Invalid input. Please enter a valid number for negative marking (e.g., 0.25).")
            except Exception as e:
                await message.reply_text(f"❌ An error occurred while creating the HTML file: {e}")
                user_state.pop(uid, None) # Reset state on error

# --- Admin Commands ---

@app.on_message(filters.command("gen") & filters.user(ADMIN_IDS))
async def generate_code_handler(client, message: Message):
    try:
        _, points_str, uses_str = message.command
        points = int(points_str)
        max_uses = int(uses_str)
    except (ValueError, IndexError):
        await message.reply_text("Usage: `/gen <points> <max_uses>`")
        return

    code = generate_redeem_code()
    create_redeem_code(code, points, max_uses, message.from_user.id)
    
    await message.reply_text(
        f"✅ Redeem code generated!\n\n"
        f"**Code:** `{code}`\n"
        f"**Points:** {points}\n"
        f"**Max Uses:** {max_uses}",
        parse_mode=ParseMode.MARKDOWN
    )

# ------------------------------------------------------------------------------------ #
#                                     ── RUN BOT ──                                    #
# ------------------------------------------------------------------------------------ #

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.critical("Error: BOT_TOKEN environment variable not set.")
    else:
        init_db()
        logger.info("Bot is starting...")
        app.run()
        idle()
        logger.info("Bot stopped.")
