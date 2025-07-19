import logging
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

# === Logging Setup ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# === Initialize Bot ===
app = Client(
    "GeminiLogBot",
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

# === AI Handler for All Chats ===
@app.on_message(filters.text)
async def ai_handler(client: Client, message: Message):
    user_input = message.text

    await client.send_chat_action(message.chat.id, ChatAction.TYPING)

    # Initial reply
    thinking_msg = await message.reply("🧠 *Thinking...*", quote=True)

    # Get Gemini response
    ai_response = get_gemini_flash_response(user_input)
    parts = split_response(ai_response)

    # Send response (edit or split if needed)
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

    # === Log to Channel ===
    try:
        user = message.from_user
        user_info = f"[{user.first_name}](tg://user?id={user.id}) (`{user.id}`)"
        chat_type = message.chat.type.name
        await client.send_message(
            LOG_CHANNEL_ID,
            f"📝 **New Prompt** from {user_info}\n"
            f"**Chat Type:** `{chat_type}`\n"
            f"**Prompt:** `{user_input}`\n"
            f"**AI Response:**\n{ai_response}"
        )
    except Exception as e:
        logging.warning(f"Failed to log message: {e}")

if __name__ == "__main__":
    print("🚀 Gemini Bot is running with log support and split-message fix...")
    app.run()
