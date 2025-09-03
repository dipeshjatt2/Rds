import asyncio
import json
import os 
import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, PollType  # Added PollType import

# ── CONFIG ──
API_ID = 22118129
API_HASH = "43c66e3314921552d9330a4b05b18800"
BOT_TOKEN = os.environ.get("BOT_TOKEN")

app = Client("quizbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary memory storage for quiz creation
user_state = {}

# ── START COMMAND ──
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text(
        "👋 Welcome! Use /create to make an anonymous quiz."
    )

# ── CREATE QUIZ ──
@app.on_message(filters.command("create"))
async def create_quiz(client, message: Message):
    user_state[message.from_user.id] = {"step": "question"}
    await message.reply_text("✍️ Send me your quiz question:")

# ── MESSAGE HANDLER ──
@app.on_message(filters.text & ~filters.command(["start", "create", "txqz"]))
async def handle_message(client, message: Message):
    uid = message.from_user.id

    if uid not in user_state:
        return  # not in quiz creation flow

    state = user_state[uid]

    # Step 1: Question
    if state["step"] == "question":
        state["question"] = message.text
        state["options"] = []
        state["step"] = "option1"
        await message.reply_text("✅ Question saved!\n\nNow send Option 1:")
        return

    # Step 2: Options (4 options total)
    if state["step"].startswith("option"):
        if message.text in state["options"]:
            await message.reply_text("⚠️ This option already exists. Send a different one.")
            return

        state["options"].append(message.text)

        if len(state["options"]) < 4:
            state["step"] = f"option{len(state['options'])+1}"
            await message.reply_text(
                f"Option {len(state['options'])} saved! Now send Option {len(state['options'])+1}:"
            )
        else:
            state["step"] = "correct"
            await message.reply_text(
                "👌 All 4 options saved!\n\nNow send the number of the correct option (1-4):"
            )
        return

    # Step 3: Correct answer
    if state["step"] == "correct":
        try:
            correct = int(message.text.strip()) - 1   # Convert 1–4 → 0–3
            if correct not in [0, 1, 2, 3]:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ Please send a valid number (1-4).")
            return

        state["correct_option_id"] = correct

        # Send final quiz with explicit quiz parameters
        try:
            await client.send_poll(
                chat_id=message.chat.id,
                question=state["question"],
                options=state["options"],
                type=PollType.QUIZ,  # Changed to use PollType enum instead of string
                correct_option_id=correct,
                is_anonymous=True,
                allows_multiple_answers=False,
                protect_content=False
            )
            await message.reply_text("🎉 Quiz started! Answer fast for higher score 🏆")
        except Exception as e:
            await message.reply_text(f"❌ Error creating quiz: {str(e)}")

        # Clear state
        del user_state[uid]
        return

# ── TXQZ HANDLER ──
@app.on_message(filters.command("txqz"))
async def txqz(client, message: Message):
    content = None
    if message.reply_to_message and message.reply_to_message.document:
        try:
            file_path = await message.reply_to_message.download()
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            await message.reply_text(f"❌ Error downloading document: {str(e)}")
            return
    elif len(message.text.strip()) > len('/txqz'):
        content = message.text[message.text.find('/txqz') + len('/txqz'):].strip()
    else:
        await message.reply_text("⚠️ Please provide quiz text after /txqz or reply to a text document.")
        return

    if not content:
        await message.reply_text("⚠️ No content found.")
        return

    questions = []
    try:
        # Try parsing as JSON format
        if 'const quizData' in content:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            json_str = content[json_start:json_end]
            data = json.loads(json_str)
            for item in data['questions']:
                q = {
                    'question': item['text'].strip(),
                    'options': [],
                    'correct': item['correctIndex'],
                    'explanation': item['explanation'].strip() + ' ' + item['reference'].strip()
                }
                for opt in item['options']:
                    if opt.startswith('🔘'):
                        paren_end = opt.find(')')
                        if paren_end != -1:
                            option_text = opt[paren_end + 1:].strip()
                            q['options'].append(option_text)
                if q['options'] and q['correct'] < len(q['options']):
                    questions.append(q)
    except json.JSONDecodeError:
        pass  # Not JSON, try numbered format

    if not questions:
        # Parse numbered format
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r'^[Qq]?\d+\.', line):
                q = {
                    'question': re.sub(r'^[Qq]?\d+\.', '', line).strip(),
                    'options': [],
                    'correct': -1,
                    'explanation': ''
                }
                i += 1
                while i < len(lines):
                    l = lines[i].strip()
                    if re.match(r'^\([a-z]\)', l):
                        match = re.match(r'^\(([a-z])\)\s*(.*?)(?:\s*✅)?$', l)
                        if match:
                            opt = match.group(2).strip()
                            is_correct = '✅' in lines[i]
                            q['options'].append(opt)
                            if is_correct:
                                q['correct'] = len(q['options']) - 1
                        i += 1
                    elif l.startswith('Ex:'):
                        q['explanation'] = re.sub(r'^Ex:', '', l).strip()
                        i += 1
                        break
                    elif re.match(r'^[Qq]?\d+\.', l):
                        break
                    else:
                        i += 1
                if q['correct'] != -1 and q['options']:
                    questions.append(q)
            else:
                i += 1

    if not questions:
        await message.reply_text("❌ Unable to parse any quizzes from the provided content.")
        return

    for q in questions:
        try:
            await client.send_poll(
                chat_id=message.chat.id,
                question=q['question'],
                options=q['options'],
                type=PollType.QUIZ,
                correct_option_id=q['correct'],
                is_anonymous=True,
                allows_multiple_answers=False,
                protect_content=False,
                explanation=q['explanation'] if q['explanation'] else None,
                explanation_parse_mode=ParseMode.DEFAULT
            )
        except Exception as e:
            await message.reply_text(f"❌ Error sending quiz: {str(e)}")
        await asyncio.sleep(300)  # Small delay to avoid rate limits

    await message.reply_text("🎉 All quizzes sent!")

# ── RUN BOT ──
print("Bot is running...")
app.run()
