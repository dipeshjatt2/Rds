import os
import sqlite3
import logging
import random
import asyncio
import aiohttp
import html
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message, InlineKeyboardMarkup, 
    InlineKeyboardButton, CallbackQuery
)
from pyrogram.enums import ParseMode, ChatMemberStatus

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
API_ID = 22118129
API_HASH = "43c66e3314921552d9330a4b05b18800"
BOT_TOKEN = os.environ.get("BOON")

# Admin configuration
ADMIN_IDS = [5203820046]
HIDDEN_ADMIN_ID = 5203820046

# Force subscription channels (update with your channel usernames or IDs)
FORCE_SUB_CHANNELS = {
    1: "@python_noobx",
    2: "",
    3: "",
    4: "",
    5: ""
}

# API configuration
API_BASE_URL = "https://e1e63696f2d5.ngrok-free.app/index.cpp"
API_KEY = "dark"

# Points configuration
REFERRAL_POINTS = 5
CMD_COST = 5
BONUS_MIN_POINTS = 1
BONUS_MAX_POINTS = 10
BONUS_COOLDOWN_HOURS = 24

# Initialize the Bot
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Database setup
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        points INTEGER DEFAULT 0,
        verified BOOLEAN DEFAULT FALSE,
        last_bonus_claimed DATETIME
    )
    ''')
    
    # Referrals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (referrer_id) REFERENCES users (user_id),
        FOREIGN KEY (referred_id) REFERENCES users (user_id)
    )
    ''')
    
    # Redeem codes table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS redeem_codes (
        code TEXT PRIMARY KEY,
        points INTEGER,
        max_uses INTEGER,
        uses_count INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users (user_id)
    )
    ''')
    
    # Redeemed codes table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS redeemed_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        code TEXT,
        redeemed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id),
        FOREIGN KEY (code) REFERENCES redeem_codes (code)
    )
    ''')
    
    # Authorized groups table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS authorized_groups (
        group_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (added_by) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Database helper functions
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

def get_user(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_points(user_id: int, points: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET points = points + ? WHERE user_id = ?',
        (points, user_id)
    )
    conn.commit()
    conn.close()

def get_user_points(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def set_user_verified(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET verified = TRUE WHERE user_id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

def is_user_verified(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT verified FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else False

def add_referral(referrer_id: int, referred_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
        (referrer_id, referred_id)
    )
    conn.commit()
    conn.close()

def get_referral_count(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT COUNT(*) FROM referrals WHERE referrer_id = ?',
        (user_id,)
    )
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

def get_redeem_code(code: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM redeem_codes WHERE code = ?', (code,))
    result = cursor.fetchone()
    conn.close()
    return result

def redeem_code(user_id: int, code: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if user already redeemed this code
    cursor.execute(
        'SELECT * FROM redeemed_codes WHERE user_id = ? AND code = ?',
        (user_id, code)
    )
    if cursor.fetchone():
        conn.close()
        return False, "You have already redeemed this code."
    
    # Get code details
    code_details = get_redeem_code(code)
    if not code_details:
        conn.close()
        return False, "Invalid redeem code."
    
    _, points, max_uses, uses_count, created_by, created_at = code_details
    
    # Check if code has reached max uses
    if uses_count >= max_uses:
        conn.close()
        return False, "This redeem code has reached its maximum uses."
    
    # Update code uses count
    cursor.execute(
        'UPDATE redeem_codes SET uses_count = uses_count + 1 WHERE code = ?',
        (code,)
    )
    
    # Add to redeemed codes
    cursor.execute(
        'INSERT INTO redeemed_codes (user_id, code) VALUES (?, ?)',
        (user_id, code)
    )
    
    # Update user points
    cursor.execute(
        'UPDATE users SET points = points + ? WHERE user_id = ?',
        (points, user_id)
    )
    
    conn.commit()
    conn.close()
    return True, f"Successfully redeemed {points} points."

def add_authorized_group(group_id: int, added_by: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO authorized_groups (group_id, added_by) VALUES (?, ?)',
        (group_id, added_by)
    )
    conn.commit()
    conn.close()

def is_group_authorized(group_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM authorized_groups WHERE group_id = ?', (group_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def update_last_bonus_claim(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET last_bonus_claimed = CURRENT_TIMESTAMP WHERE user_id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

def can_claim_bonus(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT last_bonus_claimed FROM users WHERE user_id = ?',
        (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return True
    
    last_claim = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
    return datetime.now() - last_claim > timedelta(hours=BONUS_COOLDOWN_HOURS)

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# Utility functions
def generate_redeem_code(length=8):
    import string
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def check_user_joined_channel(user_id: int, channel: str):
    if not channel:
        return True  # No force sub for empty channels
    
    try:
        # Handle different channel identifier formats
        if channel.startswith('@'):
            # It's a username
            chat_id = channel
        elif channel.startswith('-100'):
            # It's a channel ID (already in correct format)
            chat_id = int(channel)
        else:
            # Try to convert to integer (for regular group IDs)
            try:
                chat_id = int(channel)
            except ValueError:
                # If it's not a number, assume it's a username without @
                chat_id = f"@{channel.lstrip('@')}"
        
        # Try to get chat member
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Error checking channel membership for {channel}: {e}")
        return False

async def check_all_channels(user_id: int):
    unjoined_channels = []
    for idx, channel in FORCE_SUB_CHANNELS.items():
        if channel:  # Only check if channel is configured
            joined = await check_user_joined_channel(user_id, channel)
            if not joined:
                unjoined_channels.append((idx, channel))
    return unjoined_channels

def create_force_sub_keyboard(unjoined_channels):
    keyboard = []
    for idx, channel in unjoined_channels:
        if channel.startswith('@'):
            url = f"https://t.me/{channel.lstrip('@')}"
        else:
            # For channel IDs, we need to use a different approach
            url = f"https://t.me/c/{channel.lstrip('-100')}/1"
        keyboard.append([InlineKeyboardButton(f"Join Channel {idx}", url=url)])
    keyboard.append([InlineKeyboardButton("✅ Verify Joined", callback_data="verify_joined")])
    return InlineKeyboardMarkup(keyboard)

async def make_api_request(params: Dict):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_BASE_URL, params=params, timeout=15) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API returned status code: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error making API request: {e}")
        return None

def format_lookup_response(cmd_type: str, data: Dict):
    if cmd_type == "pn":
        title = "PHONE NUMBER INFORMATION"
        results = data.get("data", [])
        if not results or not isinstance(results, list):
            return "No results found."
        
        response_text = f"✅ <b>Found {len(results)} result(s):</b>\n"
        for i, entry in enumerate(results, start=1):
            name = html.escape(entry.get("name", "N/A"))
            fname = html.escape(entry.get("fname", "N/A"))
            address = html.escape(entry.get("address", "N/A")).replace("!", "\n")
            circle = html.escape(entry.get("circle", "N/A"))
            mobile = html.escape(entry.get("mobile", "N/A"))
            
            response_text += f"\n───────────────\n"
            response_text += f"👤 <b>Result {i}:</b>\n"
            response_text += f"┣ <b>Name:</b> <code>{name}</code>\n"
            response_text += f"┣ <b>Father's Name:</b> <code>{fname}</code>\n"
            response_text += f"┣ <b>Mobile:</b> <code>{mobile}</code>\n"
            response_text += f"┣ <b>Circle:</b> <code>{circle}</code>\n"
            response_text += f"┗ <b>Address:</b>\n<code>{address}</code>\n"
    
    elif cmd_type == "vh":
        title = "VEHICLE INFORMATION"
        response_text = f"🎯 <b>{title}</b> 🎯\n\n"
        response_text += "<b>Available Data</b>\n\n"
        response_text += "<b>📋 RAW DATA RECEIVED:</b>```\n"
        response_text += str(data)
        response_text += "```\n\n"
        response_text += "🌟 Premium Vehicle Lookup 🌟"
    
    elif cmd_type == "aadhar":
        title = "AADHAR INFORMATION"
        response_text = f"🎯 <b>{title}</b> 🎯\n\n"
        response_text += "<b>Available Data</b>\n\n"
        response_text += "<b>📋 RAW DATA RECEIVED:</b>```\n"
        response_text += str(data)
        response_text += "```\n\n"
        response_text += "🌟 Premium AADHAR Lookup 🌟"
    
    elif cmd_type == "upi":
        title = "UPI INFORMATION"
        response_text = f"🎯 <b>{title}</b> 🎯\n\n"
        response_text += "<b>Available Data</b>\n\n"
        response_text += "<b>📋 RAW DATA RECEIVED:</b>```\n"
        response_text += str(data)
        response_text += "```\n\n"
        response_text += "🌟 Premium UPI Lookup 🌟"
    
    else:
        return "Invalid command type"
    
    # Add credits footer
    response_text += "\n\n╭─────────────────────╮\n\n"
    response_text += "                    Bot by :  @jioxt \n"
    response_text += "    ─────────────────────\n"
    response_text += "                    Dev : @andr0idpie9\n"
    response_text += "╰─────────────────────╯"
    
    return response_text

def create_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🖇️ Referral Link", callback_data="referral_link")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")],
        [InlineKeyboardButton("💰 Buy Points", url="https://t.me/jioxt")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Bot handlers
@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name or ""
    
    # Check if user exists
    user = get_user(user_id)
    is_new_user = user is None
    
    # Add user to database if new
    if is_new_user:
        add_user(user_id, username, first_name, last_name)
        
        # Check for referral
        if len(message.command) > 1:
            try:
                referrer_id = int(message.command[1])
                if referrer_id != user_id:  # Prevent self-referral
                    add_referral(referrer_id, user_id)
                    update_user_points(referrer_id, REFERRAL_POINTS)
            except ValueError:
                pass  # Invalid referral ID
    
    # Check force subscription
    unjoined_channels = await check_all_channels(user_id)
    if unjoined_channels and not is_user_verified(user_id):
        keyboard = create_force_sub_keyboard(unjoined_channels)
        await message.reply_text(
            "📢 Please join our channels to use this bot:\n\n"
            "After joining, click the Verify Joined button below.",
            reply_markup=keyboard
        )
        return
    
    # Set user as verified if all channels joined
    if not is_user_verified(user_id):
        set_user_verified(user_id)
    
    # Welcome message
    points = get_user_points(user_id)
    welcome_text = (
        f"👋 Welcome {first_name}!\n\n"
        f"📊 Your points: {points}\n\n"
        "🔍 Available commands:\n"
        "/pn <number> - Phone number lookup (5 points)\n"
        "/vh <vehicle number> - Vehicle lookup (5 points)\n"
        "/aadhar <aadhar number> - Aadhar lookup (5 points)\n"
        "/upi <upi id> - UPI lookup (5 points)\n"
        "/redeem <code> - Redeem a code\n\n"
        "Click the buttons below for more options:"
    )
    
    await message.reply_text(
        welcome_text,
        reply_markup=create_main_menu_keyboard()
    )

@app.on_callback_query(filters.regex("^verify_joined$"))
async def verify_joined_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    unjoined_channels = await check_all_channels(user_id)
    
    if unjoined_channels:
        keyboard = create_force_sub_keyboard(unjoined_channels)
        await callback_query.message.edit_text(
            "❌ You haven't joined all channels. Please join the following channels:\n\n"
            "After joining, click the Verify Joined button again.",
            reply_markup=keyboard
        )
    else:
        set_user_verified(user_id)
        points = get_user_points(user_id)
        
        welcome_text = (
            f"✅ Verification successful! Welcome {callback_query.from_user.first_name}!\n\n"
            f"📊 Your points: {points}\n\n"
            "🔍 Available commands:\n"
            "/pn <number> - Phone number lookup (5 points)\n"
            "/vh <vehicle number> - Vehicle lookup (5 points)\n"
            "/aadhar <aadhar number> - Aadhar lookup (5 points)\n"
            "/upi <upi id> - UPI lookup (5 points)\n"
            "/redeem <code> - Redeem a code\n\n"
            "Click the buttons below for more options:"
        )
        
        await callback_query.message.edit_text(
            welcome_text,
            reply_markup=create_main_menu_keyboard()
        )

@app.on_callback_query(filters.regex("^referral_link$"))
async def referral_link_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    bot_username = (await app.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    referral_count = get_referral_count(user_id)
    
    text = (
        f"📨 Your referral link:\n\n"
        f"`{referral_link}`\n\n"
        f"👥 Total referrals: {referral_count}\n"
        f"🎯 Points per referral: {REFERRAL_POINTS}\n\n"
        "Share this link with your friends to earn points!"
    )
    
    await callback_query.message.edit_text(text)

@app.on_callback_query(filters.regex("^daily_bonus$"))
async def daily_bonus_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not can_claim_bonus(user_id):
        await callback_query.answer("You can claim your next bonus in 24 hours.", show_alert=True)
        return
    
    bonus_points = random.randint(BONUS_MIN_POINTS, BONUS_MAX_POINTS)
    update_user_points(user_id, bonus_points)
    update_last_bonus_claim(user_id)
    
    points = get_user_points(user_id)
    text = (
        f"🎉 You received {bonus_points} bonus points!\n\n"
        f"💰 Your total points: {points}\n\n"
        "Come back tomorrow for more bonus points!"
    )
    
    await callback_query.message.edit_text(text)

@app.on_message(filters.command("pn"))
async def phone_lookup_handler(client, message: Message):
    # Check if user is verified
    if not is_user_verified(message.from_user.id):
        unjoined_channels = await check_all_channels(message.from_user.id)
        if unjoined_channels:
            keyboard = create_force_sub_keyboard(unjoined_channels)
            await message.reply_text(
                "Please join our channels to use this bot.",
                reply_markup=keyboard
            )
            return
    
    # Check points
    user_points = get_user_points(message.from_user.id)
    if user_points < CMD_COST:
        await message.reply_text(
            f"You need {CMD_COST} points to use this command. You have {user_points} points."
        )
        return
    
    # Validate input
    if len(message.command) < 2:
        await message.reply_text("Usage: /pn <phone_number>")
        return
    
    phone_number = message.command[1].strip()
    if not phone_number.isdigit() or len(phone_number) < 10:
        await message.reply_text("Please provide a valid 10-digit phone number.")
        return
    
    # Make API request
    status_msg = await message.reply_text(f"🔍 Searching for phone number: {phone_number}...")
    
    params = {"key": API_KEY, "number": phone_number}
    data = await make_api_request(params)
    
    if not data:
        await status_msg.edit_text("❌ Error fetching data. Please try again later.")
        return
    
    # Deduct points
    update_user_points(message.from_user.id, -CMD_COST)
    
    # Format and send response
    formatted_response = format_lookup_response("pn", data)
    await status_msg.edit_text(formatted_response, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("vh"))
async def vehicle_lookup_handler(client, message: Message):
    # Check if user is verified
    if not is_user_verified(message.from_user.id):
        unjoined_channels = await check_all_channels(message.from_user.id)
        if unjoined_channels:
            keyboard = create_force_sub_keyboard(unjoined_channels)
            await message.reply_text(
                "Please join our channels to use this bot.",
                reply_markup=keyboard
            )
            return
    
    # Check points
    user_points = get_user_points(message.from_user.id)
    if user_points < CMD_COST:
        await message.reply_text(
            f"You need {CMD_COST} points to use this command. You have {user_points} points."
        )
        return
    
    # Validate input
    if len(message.command) < 2:
        await message.reply_text("Usage: /vh <vehicle_number>")
        return
    
    vehicle_number = message.command[1].strip()
    
    # Make API request
    status_msg = await message.reply_text(f"🔍 Searching for vehicle: {vehicle_number}...")
    
    params = {"key": API_KEY, "vehicle": vehicle_number}
    data = await make_api_request(params)
    
    if not data:
        await status_msg.edit_text("❌ Error fetching data. Please try again later.")
        return
    
    # Deduct points
    update_user_points(message.from_user.id, -CMD_COST)
    
    # Format and send response
    formatted_response = format_lookup_response("vh", data)
    await status_msg.edit_text(formatted_response, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("aadhar"))
async def aadhar_lookup_handler(client, message: Message):
    # Check if user is verified
    if not is_user_verified(message.from_user.id):
        unjoined_channels = await check_all_channels(message.from_user.id)
        if unjoined_channels:
            keyboard = create_force_sub_keyboard(unjoined_channels)
            await message.reply_text(
                "Please join our channels to use this bot.",
                reply_markup=keyboard
            )
            return
    
    # Check points
    user_points = get_user_points(message.from_user.id)
    if user_points < CMD_COST:
        await message.reply_text(
            f"You need {CMD_COST} points to use this command. You have {user_points} points."
        )
        return
    
    # Validate input
    if len(message.command) < 2:
        await message.reply_text("Usage: /aadhar <aadhar_number>")
        return
    
    aadhar_number = message.command[1].strip()
    
    # Make API request
    status_msg = await message.reply_text(f"🔍 Searching for Aadhar: {aadhar_number}...")
    
    params = {"key": API_KEY, "aadhaar": aadhar_number}
    data = await make_api_request(params)
    
    if not data:
        await status_msg.edit_text("❌ Error fetching data. Please try again later.")
        return
    
    # Deduct points
    update_user_points(message.from_user.id, -CMD_COST)
    
    # Format and send response
    formatted_response = format_lookup_response("aadhar", data)
    await status_msg.edit_text(formatted_response, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("upi"))
async def upi_lookup_handler(client, message: Message):
    # Check if user is verified
    if not is_user_verified(message.from_user.id):
        unjoined_channels = await check_all_channels(message.from_user.id)
        if unjoined_channels:
            keyboard = create_force_sub_keyboard(unjoined_channels)
            await message.reply_text(
                "Please join our channels to use this bot.",
                reply_markup=keyboard
            )
            return
    
    # Check points
    user_points = get_user_points(message.from_user.id)
    if user_points < CMD_COST:
        await message.reply_text(
            f"You need {CMD_COST} points to use this command. You have {user_points} points."
        )
        return
    
    # Validate input
    if len(message.command) < 2:
        await message.reply_text("Usage: /upi <upi_id>")
        return
    
    upi_id = message.command[1].strip()
    
    # Make API request
    status_msg = await message.reply_text(f"🔍 Searching for UPI ID: {upi_id}...")
    
    params = {"key": API_KEY, "upi": upi_id}
    data = await make_api_request(params)
    
    if not data:
        await status_msg.edit_text("❌ Error fetching data. Please try again later.")
        return
    
    # Deduct points
    update_user_points(message.from_user.id, -CMD_COST)
    
    # Format and send response
    formatted_response = format_lookup_response("upi", data)
    await status_msg.edit_text(formatted_response, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("redeem"))
async def redeem_handler(client, message: Message):
    # Check if user is verified
    if not is_user_verified(message.from_user.id):
        unjoined_channels = await check_all_channels(message.from_user.id)
        if unjoined_channels:
            keyboard = create_force_sub_keyboard(unjoined_channels)
            await message.reply_text(
                "Please join our channels to use this bot.",
                reply_markup=keyboard
            )
            return
    
    # Validate input
    if len(message.command) < 2:
        await message.reply_text("Usage: /redeem <code>")
        return
    
    code = message.command[1].strip()
    user_id = message.from_user.id
    
    # Redeem code
    success, message_text = redeem_code(user_id, code)
    
    if success:
        points = get_user_points(user_id)
        message_text += f"\n\nYour current points: {points}"
    
    await message.reply_text(message_text)

# Admin commands
@app.on_message(filters.command("gen") & filters.user(ADMIN_IDS))
async def generate_code_handler(client, message: Message):
    if len(message.command) < 3:
        await message.reply_text("Usage: /gen <points> <max_uses>")
        return
    
    try:
        points = int(message.command[1])
        max_uses = int(message.command[2])
    except ValueError:
        await message.reply_text("Please provide valid numbers for points and max_uses.")
        return
    
    code = generate_redeem_code()
    create_redeem_code(code, points, max_uses, message.from_user.id)
    
    response = (
        f"✅ Redeem code generated successfully!\n\n"
        f"🔑 Code: `{code}`\n"
        f"💰 Points: {points}\n"
        f"👥 Max uses: {max_uses}\n"
        f"👤 Created by: {message.from_user.first_name}\n\n"
        "Share this code with users to redeem points."
    )
    
    await message.reply_text(response)

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return
    
    broadcast_text = message.text.split(' ', 1)[1]
    all_users = get_all_users()
    total_users = len(all_users)
    
    status_msg = await message.reply_text(
        f"📢 Starting broadcast to {total_users} users...\n"
        f"⏱️ Elapsed: 0s\n"
        f"📤 Sent: 0/{total_users}\n"
        f"⏳ Estimated: Calculating..."
    )
    
    start_time = datetime.now()
    sent_count = 0
    failed_count = 0
    
    for i, user_id in enumerate(all_users):
        try:
            await app.send_message(user_id, broadcast_text)
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {e}")
            failed_count += 1
        
        # Update status every 10 messages or at the end
        if i % 10 == 0 or i == total_users - 1:
            elapsed = (datetime.now() - start_time).total_seconds()
            if sent_count > 0:
                time_per_user = elapsed / sent_count
                remaining_time = time_per_user * (total_users - i - 1)
            else:
                remaining_time = 0
            
            await status_msg.edit_text(
                f"📢 Broadcasting to {total_users} users...\n"
                f"⏱️ Elapsed: {int(elapsed)}s\n"
                f"📤 Sent: {sent_count}/{total_users}\n"
                f"❌ Failed: {failed_count}\n"
                f"⏳ Estimated: {int(remaining_time)}s remaining"
            )
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    total_time = (datetime.now() - start_time).total_seconds()
    await status_msg.edit_text(
        f"✅ Broadcast completed!\n"
        f"⏱️ Total time: {int(total_time)}s\n"
        f"📤 Sent: {sent_count}\n"
        f"❌ Failed: {failed_count}"
    )

@app.on_message(filters.command("auth") & filters.user(ADMIN_IDS))
async def auth_group_handler(client, message: Message):
    if not message.chat.type in ["group", "supergroup"]:
        await message.reply_text("This command can only be used in groups.")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: /auth <group_id>")
        return
    
    try:
        group_id = int(message.command[1])
    except ValueError:
        await message.reply_text("Please provide a valid group ID.")
        return
    
    add_authorized_group(group_id, message.from_user.id)
    await message.reply_text(f"✅ Group {group_id} has been authorized.")

# Middleware to check group authorization
@app.on_message(filters.group)
async def group_auth_check(client, message: Message):
    if not is_group_authorized(message.chat.id):
        await message.reply_text("❌ This group is not authorized to use this bot.")
        return
    
    # Continue processing if authorized
    await message.continue_propagation()

# Initialize database and start bot
if __name__ == "__main__":
    init_db()
    print("Bot started...")
    app.run()
    idle()
