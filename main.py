import asyncio
import json
import aiohttp 
import os
import re
import io
import random
import time
import csv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, PollType

# ── CONFIG ──
# Using configuration from the first bot, as requested.
API_ID = 22118129
API_HASH = "43c66e3314921552d9330a4b05b18800"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SESSION_STRING = os.environ.get("SESSION_STRING") # ── CONFIG ──
# ... (your existing API_ID, API_HASH, BOT_TOKEN, etc.) ...


# --- [NEW] AI Configuration ---
GEMINI_API_KEY = os.environ.get("aikey") # This is the line you requested
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
STYLISH_SIGNATURE = "@DIPESHCHOUDHARYBOT" # Stylish "by yourname"


# This HTML template file must be in the same directory as the bot script.
TEMPLATE_HTML = "format2.html"

app = Client("combined_quiz_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ── GLOBAL STATE & CONSTANTS ──
# Unified state management for all bot functions.
user_state = {}
user_sessions = {} # Tracks active /poll2txt scraping sessions
# ─── HELPER FUNCTIONS (PARSING & HTML) ───
# These functions are from the second bot for the HTML generation feature.
# shuffling txt logic       
@app.on_message(filters.command("shufftxt"))
async def shufftxt_handler(client, message: Message):
    """
    Usage:
      - Reply to a .txt or .csv file with the command: /shufftxt
      - OR send the file with caption "/shufftxt" (so message.document is the same message)
    Behavior:
      - Parses the file using your detect_and_parse / parse_csv
      - Randomly shuffles the question order
      - Reverses options for each question (first option <-> last option) and adjusts correctIndex
      - Sends back a shuffled .txt file (keeps ✅ marks and Ex: if present)
    """
    # Find the message that contains the file
    target_msg = None
    if message.reply_to_message and message.reply_to_message.document:
        target_msg = message.reply_to_message
    elif message.document:
        target_msg = message
    else:
        await message.reply_text(
            "⚠️ Please reply to a `.txt` or `.csv` file with /shufftxt, or send the file with caption `/shufftxt`."
        )
        return

    doc = target_msg.document
    fname = (doc.file_name or "file").lower()
    if not (fname.endswith(".txt") or fname.endswith(".csv")):
        await message.reply_text("❌ Unsupported file type. Please use a `.txt` or `.csv` file.")
        return

    try:
        # Download and parse the file
        path = await target_msg.download()
        if fname.endswith(".csv"):
            questions = parse_csv(path)
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            questions = detect_and_parse(txt)
        
        try:
            os.remove(path)
        except Exception:
            pass

        if not questions:
            await message.reply_text(
                "❌ Could not parse any questions from the file. Make sure the format is supported (see /htmk)."
            )
            return

        # --- [NEW] DATA CLEANUP: FIX MISPLACED EXPLANATIONS ---
        # This loop corrects data where the parser may have mistakenly included
        # the "Ex:" line as one of the options.
        for q in questions:
            explanation_text = None
            # Find and extract the explanation from the options list
            for opt in q.get("options", []):
                if opt.strip().startswith("Ex:"):
                    # Store the explanation text (without the "Ex: " prefix)
                    explanation_text = opt.strip().replace("Ex:", "").strip()
                    break  # Found it

            # If an explanation was found in the options...
            if explanation_text:
                # ...assign it to the correct 'explanation' key
                q["explanation"] = explanation_text
                # ...and create a new 'options' list that filters out the explanation line
                q["options"] = [opt for opt in q.get("options", []) if not opt.strip().startswith("Ex:")]

        # --- SHUFFLE LOGIC ---
        random.shuffle(questions)
        for q in questions:
            opts = q.get("options", [])
            ci = q.get("correctIndex", -1)
            if len(opts) > 1:
                opts.reverse()
                if ci is not None and ci != -1:
                    q["correctIndex"] = len(opts) - 1 - ci
                else:
                    q["correctIndex"] = -1

        # --- RECONSTRUCT THE OUTPUT FILE ---
        out_lines = []
        for i, q in enumerate(questions, start=1):
            qtext = q.get("text", "").replace("\r", "")
            out_lines.append(f"{i}. {qtext}")
            for idx, opt in enumerate(q.get("options", [])):
                prefix = f"({chr(97 + idx)})"
                mark = " ✅" if idx == q.get("correctIndex", -1) else ""
                out_lines.append(f"{prefix} {opt}{mark}")
            # This part now works correctly because the explanation is in the right place
            if q.get("explanation"):
                out_lines.append(f"Ex: {q.get('explanation')}")
            out_lines.append("")

        # --- SEND THE RESULT ---
        final_txt = "\n".join(out_lines).strip()
        file_obj = io.BytesIO(final_txt.encode("utf-8"))
        base = os.path.splitext(os.path.basename(fname))[0]
        file_obj.name = f"shuffled_{base}.txt"

        await message.reply_document(file_obj, caption="✅ Shuffled questions generated successfully!")

    except Exception as e:
        await message.reply_text(f"❌ An error occurred while processing the file: {e}")

#dg

def parse_format_dash(txt: str):
    """Q#: ... with dash-prefixed options and Ex: explanation"""
    questions = []
    blocks = re.split(r'(?m)^Q\d+:\s*', txt)  # Split on Q1:, Q2:, etc.
    for block in blocks:
        if not block.strip():
            continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        qtext = lines[0]  # first line after Q#: is question
        opts = []
        correct = -1
        explanation = ""
        for i, l in enumerate(lines[1:], start=1):
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
    chunks = re.split(r'(?m)^\s*\d+\.\s*', txt)
    chunks = [c.strip() for c in chunks if c.strip()]
    for chunk in chunks:
        m_def = re.split(r'\([a-zA-Z]\)', chunk, maxsplit=1)
        if len(m_def) < 2:
            continue
        definition = m_def[0].strip()
        opts = []
        correct = -1
        for match in re.finditer(r'\(([a-zA-Z])\)\s*(.*?)(?=(\([a-zA-Z]\)|Ex:|$))', chunk, flags=re.S):
            raw = match.group(2).strip()
            has_tick = '✅' in raw
            raw = raw.replace('✅','').strip()
            opts.append(raw)
            if has_tick:
                correct = len(opts)-1
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
        if not block.strip(): continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines: continue
        qtext = lines[0]
        opts = []; correct = -1
        for i,l in enumerate(lines[1:]):
            has_tick = '✅' in l
            l = l.replace('✅','').strip()
            if l[:2].lower() in ["a)","b)","c)","d)","e)","f)"]:
                l = l[2:].strip()
            opts.append(l)
            if has_tick: correct = len(opts)-1
        questions.append({"text":qtext,"options":opts,"correctIndex":correct,"explanation":"","reference":""})
    return questions

def parse_format3(txt: str):
    """Direct JSON quizData"""
    try:
        m = re.search(r'const\s+quizData\s*=\s*({.*});', txt, flags=re.S)
        if not m: return []
        obj = json.loads(m.group(1))
        return obj.get("questions",[])
    except Exception:
        return []

def parse_format4(txt: str):
    """Q + options line by line, blank line separates questions"""
    questions=[]
    blocks = re.split(r'\n\s*\n', txt.strip())
    for block in blocks:
        lines=[l.strip() for l in block.splitlines() if l.strip()]
        if not lines: continue
        qtext=lines[0]
        opts=[];correct=-1
        for i,l in enumerate(lines[1:]):
            has_tick='✅' in l
            l=l.replace('✅','').strip()
            opts.append(l)
            if has_tick: correct=i
        questions.append({"text":qtext,"options":opts,"correctIndex":correct,"explanation":"","reference":""})
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
            except:
                correct_idx = 0
            if correct_idx < 0 or correct_idx >= len(opts):
                correct_idx = 0
            questions.append({
                "text": row.get("Question (Exam Info)", "").strip(),
                "options": opts,
                "correctIndex": correct_idx,
                "explanation": row.get("Explanation", "").strip(),
                "reference": ""
            })
    return questions

def detect_and_parse(txt:str):
    if "const quizData" in txt:
        return parse_format3(txt)
    if "Definition:" in txt or re.search(r'\([a-zA-Z]\)', txt):
        return parse_format1(txt)
    if re.search(r'^\s*\d+\.\s+.*\na\)', txt, flags=re.M):
        return parse_format2(txt)
    if re.search(r'✅', txt) and not ("(a)" in txt):
        return parse_format4(txt)
    if re.search(r'(?m)^Q\d+:\s', txt) and "-" in txt:
        return parse_format_dash(txt)    
    return []

def replace_questions_in_template(html: str, questions, minutes:int, negative:float):
    start_qd = html.find("const quizData")
    if start_qd == -1: raise ValueError("quizData not found")
    tail = html[start_qd:]
    start_q = tail.find("questions"); start_q+=start_qd
    m_open = re.search(r'questions\s*:\s*\[', html[start_q:], flags=re.S)
    if not m_open: raise ValueError("questions array not found")
    q_arr_open = start_q + m_open.start()
    i = q_arr_open + m_open.group(0).rfind('[')+1
    depth=1
    while i < len(html):
        if html[i]=='[': depth+=1
        elif html[i]==']': depth-=1
        if depth==0: break
        i+=1
    q_arr_end=i
    questions_js = json.dumps(questions, ensure_ascii=False, indent=2)
    new_block = f"settings: {{ totalTimeSec: {minutes*60}, negativeMarkPerWrong: {negative} }},\n  questions: {questions_js}"
    before = html[:q_arr_open-1]
    after = html[q_arr_end+1:]
    return before+new_block+after


# ─── BOT HANDLERS ───

@app.on_message(filters.command(["start", "help"]))
async def start_handler(_, message: Message):
    await message.reply_text(
        "👋 **Welcome!**\n\n"
        "Here's what I can do:\n\n"
        "🔹 **/create** - Create a quiz poll manually, one step at a time.\n"
        "🔹 **/txqz** - Paste text or reply to a file to create multiple quiz polls at once.\n"
        "🔹 **/htmk** - Convert a quiz from a `.txt` or `.csv` file into an interactive HTML file."
    )

# ── 1. Manual Quiz Creation (/create) ──

@app.on_message(filters.command("create"))
async def create_quiz(client, message: Message):
    user_state[message.from_user.id] = {"flow": "create", "step": "question"}
    await message.reply_text("✍️ Send me your quiz question:")

# ── 2. Text-to-Poll Sender (/txqz) ──

@app.on_message(filters.command("txqz"))
async def txqz(client, message: Message):
    content = None
    if message.reply_to_message and message.reply_to_message.document:
        try:
            file_path = await message.reply_to_message.download()
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            os.remove(file_path)
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
        # Try parsing as JSON format (from bot 1)
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
                    'explanation': (item.get('explanation', '').strip() + ' ' + item.get('reference', '').strip()).strip()
                }
                for opt in item['options']:
                    q['options'].append(opt.strip())
                if q['options'] and q['correct'] < len(q['options']):
                    questions.append(q)
    except json.JSONDecodeError:
        pass  # Not JSON, try other formats

    if not questions:
        # Parse numbered format (from bot 1)
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
                explanation=q['explanation'] if q['explanation'] else None,
                explanation_parse_mode=ParseMode.DEFAULT
            )
        except Exception as e:
            await message.reply_text(f"❌ Error sending quiz: {str(e)}")
        await asyncio.sleep(3)  # Small delay to avoid rate limits

    await message.reply_text("🎉 All quizzes sent!")


# ── 3. HTML Quiz Generator (/htmk) ──

@app.on_message(filters.command("htmk"))
async def htmk_command_handler(client, message: Message):
    """Initiates the HTML creation flow."""
    user_state[message.from_user.id] = {"flow": "html", "step": "waiting_for_file"}
    await message.reply_text(
        "✅ OK! Please send me the `.txt` or `.csv` file you want to convert to an HTML quiz."
    )

@app.on_message(filters.document, group=1)
async def document_handler(client, message: Message):
    """Handles file uploads specifically for the /htmk flow."""
    uid = message.from_user.id
    if user_state.get(uid, {}).get("step") != "waiting_for_file":
        return  # This file is not for us, ignore it.

    filename = message.document.file_name.lower()
    if not (filename.endswith(".txt") or filename.endswith(".csv")):
        await message.reply_text("❌ Invalid file type. Please send a `.txt` or `.csv` file.")
        return

    try:
        path = await message.download()
        if filename.endswith(".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            questions = detect_and_parse(txt)
        else: # .csv
            questions = parse_csv(path)
        os.remove(path)

        if not questions:
            await message.reply_text("❌ Could not parse any questions from the file. Please check the format.")
            del user_state[uid]
            return
        
        # Update state and move to the next step
        user_state[uid] = {
            "flow": "html",
            "step": "time",
            "questions": questions
        }
        await message.reply_text(f"✅ Parsed {len(questions)} questions.\n\nNow send the test time in **minutes**:")

    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")
        if uid in user_state:
            del user_state[uid]


# ── 4. Main State Machine for Text Messages ──
# ── 5. Poll Scraper (/poll2txt) ──


import re # Make sure this is at the top of your file

MAX_POLLS = 100 # Set the maximum number of polls to fetch

async def run_scraper(main_bot_client: Client, user_message: Message, replied_message: Message):
    """
    This helper function manages the entire userbot scraping process,
    now updated with active poll answering to capture correct answers.
    """
    user_id = user_message.from_user.id
    chat_id = user_message.chat.id
    status_msg = await main_bot_client.send_message(chat_id, "🚀 **Starting scraper...**\n\nInitializing user session.")

    scraped_data = {"polls": [], "stop_reason": ""}
    scraping_finished = asyncio.Event()

    userbot = None # Define userbot here to access it in finally block
    try:
        if not SESSION_STRING:
            await status_msg.edit("❌ **Error:** `SESSION_STRING` is not configured by the bot owner.")
            return

        # 1. Extract deep link URL from the button
        if not (replied_message.reply_markup and replied_message.reply_markup.inline_keyboard):
            raise ValueError("Replied message has no buttons.")
        
        button_url = replied_message.reply_markup.inline_keyboard[0][0].url
        match = re.search(r"t\.me/([^?]+)\?start=(.+)", button_url)
        if not match:
            raise ValueError("The button does not contain a valid QuizBot start link.")
            
        bot_username = match.group(1)
        start_token = match.group(2)
        await status_msg.edit(f"✅ **Link identified!**\n\nBot: `@{bot_username}`\nAction: Starting quiz...")

        userbot = Client("userbot_session_" + str(user_id), session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

        @userbot.on_message(filters.poll & filters.private)
        async def poll_handler(_, poll_message: Message):
            """
            This handler now actively votes on polls to determine the correct answer
            before capturing the data.
            """
            # Ensure the poll is from the correct bot we are interacting with
            if not poll_message.from_user or poll_message.from_user.username.lower() != bot_username.lower():
                return

            # --- NEW LOGIC TO ACTIVELY ANSWER POLLS ---
            correct_index = 0 # Default to 0 as a fallback
            try:
                # 1. Vote on the poll with the first option to trigger the result
                await userbot.vote_poll(
                    chat_id=poll_message.chat.id,
                    message_id=poll_message.id,
                    options=[0]
                )
                
                # 2. Wait a moment for Telegram to process the vote and update the poll
                await asyncio.sleep(2)
                
                # 3. Re-fetch the message to get the updated poll object
                updated_message = await userbot.get_messages(
                    chat_id=poll_message.chat.id,
                    message_id=poll_message.id
                )
                
                # 4. Reliably get the correct_option_id from the updated poll
                if updated_message and updated_message.poll:
                    correct_index = updated_message.poll.correct_option_id
                    if correct_index is None: # Fallback if still not available
                        correct_index = 0
            except Exception:
                # If voting or fetching fails, we'll just use the fallback index
                correct_index = 0
            # --- END OF NEW LOGIC ---

            # Use the original poll object for text content, but the new correct_index
            poll = poll_message.poll
            data = {
                "text": poll.question,
                "options": [opt.text for opt in poll.options],
                "correctIndex": correct_index,
                "explanation": getattr(poll, "explanation", "") or ""
            }
            scraped_data["polls"].append(data)
            
            # Update progress
            try:
                await status_msg.edit(f"📥 **Scraping in progress...**\n\nAnswered and collected **{len(scraped_data['polls'])}/{MAX_POLLS}** polls.")
            except: # Ignore errors if message is same
                pass

            if len(scraped_data["polls"]) >= MAX_POLLS:
                scraped_data["stop_reason"] = f"Reached max limit of {MAX_POLLS} polls."
                scraping_finished.set()

        # Start the userbot client
        await userbot.start()
        
        # 2. Send the /start command to the QuizBot
        await userbot.send_message(bot_username, f"/start {start_token}")
        await status_msg.edit("▶️ Sent `/start` command to QuizBot. Waiting for a response...")
        await asyncio.sleep(3)

        # 3. Find the "I am ready" message and click it
        clicked_ready = False
        async for msg in userbot.get_chat_history(bot_username, limit=5):
            if msg.reply_markup and msg.reply_markup.inline_keyboard:
                await msg.click(0) # Click the first button found
                await status_msg.edit("👍 Clicked **I am ready** button. Now answering and capturing polls...")
                clicked_ready = True
                break
        
        if not clicked_ready:
            raise ValueError("Could not find the 'I am ready' button after starting the quiz.")

        # 4. Wait for polls to arrive (with a timeout)
        try:
            await asyncio.wait_for(scraping_finished.wait(), timeout=120) 
        except asyncio.TimeoutError:
            scraped_data["stop_reason"] = "Timeout: No new polls received for 2 minutes."

    except Exception as e:
        await status_msg.edit(f"❌ **An error occurred:**\n`{str(e)}`")
        return
    finally:
        # Stop the userbot and clean up
        if userbot and userbot.is_connected:
            await userbot.stop()
        if user_id in user_sessions:
            del user_sessions[user_id]
        await status_msg.edit(f"🛑 **Scraping Finished!**\n\nReason: {scraped_data.get('stop_reason', 'N/A')}\nTotal polls collected: {len(scraped_data['polls'])}\n\nFormatting data...")

    # --- Format and Send Data ---
    if not scraped_data["polls"]:
        await status_msg.edit("🤷 No polls were collected. Nothing to send.")
        return

    try:
        lines = []
        for idx, q in enumerate(scraped_data["polls"], start=1):
            lines.append(f"{idx}. {q['text']}")
            options_text = [f"  ({chr(97 + i)}) {opt}" for i, opt in enumerate(q['options'])]
            lines.extend(options_text)
            
            if q['correctIndex'] is not None and q['correctIndex'] < len(q['options']):
                correct_char = chr(97 + q['correctIndex'])
                lines.append(f"  Correct: ({correct_char})")
            if q['explanation']:
                lines.append(f"  Ex: {q['explanation']}")
            lines.append("")

        content = "\n".join(lines)
        output_file = f"quiz_data_{user_id}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

        await status_msg.delete()
        await main_bot_client.send_document(
            chat_id=chat_id,
            document=output_file,
            caption="🎉 **Here is your formatted quiz data!**"
        )
        os.remove(output_file)

    except Exception as e:
        await main_bot_client.send_message(chat_id, f"❌ Failed to format and send the file.\nError: {e}")


@app.on_message(filters.command("poll2txt"))
async def poll2txt_handler(client, message: Message):
    """
    Initiates the poll scraping process.
    Usage: Reply to a quiz bot's 'Start' message with /poll2txt
    """
    user_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("⚠️ **Usage:** Please reply to a message that contains a 'Start Quiz' button with the command `/poll2txt`.")
        return

    if user_id in user_sessions:
        await message.reply_text("⏳ You already have an active scraping session. Please wait for it to complete.")
        return

    user_sessions[user_id] = True 
    asyncio.create_task(run_scraper(client, message, message.reply_to_message))

# ── 6. [NEW] AI MCQ Generator (/ai) ──

@app.on_message(filters.command("ai"))
async def generate_ai_mcqs(client, message: Message):
    """
    Generates MCQs using the Gemini AI API.
    Usage: /ai [topic] [amount]
    Example: /ai "Indian History" 30
    """
    if not GEMINI_API_KEY:
        await message.reply_text("âŒ **AI Error:** `aikey` (GEMINI_API_KEY) is not configured by the bot owner.")
        return

    # --- 1. Parse Input ---
    try:
        parts = message.text.split(None, 2)
        if len(parts) < 3:
            await message.reply_text("âŒ **Usage:** `/ai [Topic Name] [Amount]`\n**Example:** `/ai \"Indian History\" 30`")
            return
        
        # Combine parts [1] and [2...n-1] as the topic if it's not quoted
        amount_str = parts[-1]
        topic = " ".join(parts[1:-1])
        
        # Check if topic is quoted
        if message.text.count('"') == 2:
             topic = re.search(r'"(.*?)"', message.text).group(1)
             # Get amount after the closing quote
             amount_str = message.text.split(f'"{topic}"', 1)[-1].strip()
        
        if not topic:
             await message.reply_text("âŒ No topic provided. Usage: `/ai [Topic] [Amount]`")
             return

        amount = int(amount_str)
        if amount <= 0 or amount > 50: # Set a reasonable limit
            await message.reply_text("âŒ Please provide an amount between 1 and 50.")
            return

    except (ValueError, TypeError):
        await message.reply_text("âŒ **Invalid Format:** Usage: `/ai [Topic Name] [Amount]`\n**Example:** `/ai \"Gupta Empire\" 20`")
        return
    except Exception as e:
        await message.reply_text(f"Error parsing command: {e}")
        return

    status_msg = await message.reply_text(f"ðŸ¤“ **Generating {amount} MCQs for \"{topic}\"...**\nThis may take a moment.")

    # --- 2. Build AI Prompt ---
    prompt_text = f"""Create {amount} MCQs on the topic {topic} in both English and Hindi (bilingual format) at a medium level.
Format:

Each question must be numbered (1., 2., etc.)
Each question should have exactly 4 options: (a), (b), (c), (d).

Place a âœ… emoji next to the single correct option. Ensure the correct option's position is randomized/shuffled across questions (e.g., not always (a) or (b)).

After each question, add a brief explanation under Ex: (max 200 characters).

Every explanation MUST end with the text: {STYLISH_SIGNATURE}

Output everything inside a single markdown code block (```). Keep everything concise.

Example format:
1. Who founded the Tughlaq Dynasty? / à¤¤à¥à¤—à¤²à¤• à¤µà¤‚à¤¶ à¤•à¥€ à¤¸à¥à¤¥à¤¾à¤ªà¤¨à¤¾ à¤•à¤¿à¤¸à¤¨à¥‡ à¤•à¥€?
(a) Ghiyasuddin Tughlaq / à¤—à¤¼à¤¿à¤¯à¤¾à¤¸à¥à¤¦à¥à¤¦à¥€à¤¨ à¤¤à¥à¤—à¤²à¤• âœ…
(b) Alauddin Khilji / à¤…à¤²à¤¾à¤‰à¤¦à¥à¤¦à¥€à¤¨ à¤–à¤¿à¤²à¤œà¥€
(c) Bahlol Lodhi / à¤¬à¤¹à¤²à¥‹à¤² à¤²à¥‹à¤¦à¥€
(d) Khizr Khan / à¤–à¤¼à¤¿à¤œà¥à¤° à¤–à¤¼à¤¾à¤¨
Ex: Ghiyasuddin Tughlaq founded the dynasty in 1320. {STYLISH_SIGNATURE}

2. Next question...
(a) Option...
...and so on.

Now make the MCQs for the topic: {topic}
"""

    # --- 3. Call Gemini API ---
    headers = {
        'Content-Type': 'application/json',
        'X-goog-api-key': GEMINI_API_KEY
    }
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
         "generationConfig": {
            "temperature": 0.5,
            "topK": 1,
            "topP": 1,
            "maxOutputTokens": 8192, # Increased token limit for large requests
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload, headers=headers, timeout=1800) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    await status_msg.edit(f"âŒ **API Error: {resp.status}**\nFailed to get data from AI.\n`{error_text}`")
                    return
                
                response_json = await resp.json()

    except asyncio.TimeoutError:
         await status_msg.edit("😄 **Request Timed Out:** The AI took too long to respond.")
         return
    except Exception as e:
        await status_msg.edit(f"âŒ **HTTP Request Failed:**\n`{str(e)}`")
        return

    # --- 4. Parse Response and Create File ---
    try:
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        
        # Clean the text: remove markdown code block fences
        clean_text = re.sub(r'^```(markdown|text|)?\s*|\s*```$', '', raw_text, flags=re.MULTILINE | re.DOTALL).strip()

        if not clean_text or len(clean_text) < 50:
             await status_msg.edit(f"âŒ **Empty Response:** The AI returned an empty or invalid response.\n`{response_json}`")
             return

        # Create the file name as requested
        topic_cleaned = re.sub(r'[^a-zA-Z0-9]', '', topic.replace(" ", "_"))
        if len(topic_cleaned) > 50: topic_cleaned = topic_cleaned[:50] # Truncate long filenames
        filename = f"{topic_cleaned}_mcqs_by_{message.from_user.id}.txt"

        # Create file in memory
        file_data = io.BytesIO(clean_text.encode('utf-8'))
        file_data.name = filename

        # --- 5. Upload File ---
        await message.reply_document(
            document=file_data,
            caption=f"âœ… Here are your {amount} MCQs on **{topic}**!"
        )
        await status_msg.delete() # Success, so delete the status message

    except (KeyError, IndexError, TypeError):
        await status_msg.edit(f"âŒ **Failed to Parse AI Response.**\nCould not find text in the response.\n`{response_json}`")
    except Exception as e:
        await status_msg.edit(f"âŒ **An error occurred processing the file:**\n`{str(e)}`")


@app.on_message(filters.text & ~filters.command(["start", "help", "ai", "create", "txqz", "htmk"]))
async def handle_message(client, message: Message):
    uid = message.from_user.id
    if uid not in user_state:
        return

    state = user_state[uid]
    flow = state.get("flow")

    # --- Flow for /create ---
    if flow == "create":
        if state["step"] == "question":
            state["question"] = message.text
            state["options"] = []
            state["step"] = "option1"
            await message.reply_text("✅ Question saved!\n\nNow send **Option 1**:")
            return

        if state["step"].startswith("option"):
            if message.text in state["options"]:
                await message.reply_text("⚠️ This option already exists. Send a different one.")
                return
            state["options"].append(message.text)
            if len(state["options"]) < 4:
                next_opt_num = len(state['options']) + 1
                state["step"] = f"option{next_opt_num}"
                await message.reply_text(f"Option {len(state['options'])} saved! Now send **Option {next_opt_num}**:")
            else:
                state["step"] = "correct"
                await message.reply_text("👌 All 4 options saved!\n\nNow send the number of the **correct option (1-4)**:")
            return

        if state["step"] == "correct":
            try:
                correct = int(message.text.strip()) - 1
                if correct not in [0, 1, 2, 3]: raise ValueError
            except ValueError:
                await message.reply_text("❌ Please send a valid number (1-4).")
                return
            state["correct_option_id"] = correct
            try:
                await client.send_poll(
                    chat_id=message.chat.id,
                    question=state["question"],
                    options=state["options"],
                    type=PollType.QUIZ,
                    correct_option_id=correct,
                    is_anonymous=True
                )
            except Exception as e:
                await message.reply_text(f"❌ Error creating quiz: {str(e)}")
            del user_state[uid] # End of flow
            return

    # --- Flow for /htmk ---
    elif flow == "html":
        if state["step"] == "time":
            try:
                state["time"] = int(message.text.strip())
                state["step"] = "negative"
                await message.reply_text("⏰ Time saved!\n\nNow send the **negative marks** per wrong answer (e.g., `0.25` or `0` for none):")
            except ValueError:
                await message.reply_text("❌ Please send a valid integer for minutes.")
            return

        elif state["step"] == "negative":
            try:
                state["negative"] = float(message.text.strip())
                state["step"] = "shuffle"
                await message.reply_text("➖ Negative marks saved!\n\nDo you want to **shuffle** questions and options? (yes/no):")
            except ValueError:
                await message.reply_text("❌ Please send a valid number for negative marks (e.g., 0.25).")
            return

        elif state["step"] == "shuffle":
            ans = message.text.strip().lower()
            if ans not in ["yes", "no"]:
                await message.reply_text("❌ Please send either `yes` or `no`.")
                return
            if ans == "yes":
                random.shuffle(state["questions"])
                for q in state["questions"]:
                    if len(q["options"]) > 1:
                        correct_opt_text = q["options"][q["correctIndex"]]
                        random.shuffle(q["options"])
                        q["correctIndex"] = q["options"].index(correct_opt_text)
                await message.reply_text("🔀 Questions and options have been shuffled.")
            state["step"] = "filename"
            await message.reply_text("📄 Finally, send a **filename** for your quiz (without the .html extension):")
            return

        elif state["step"] == "filename":
            name = re.sub(r'[^A-Za-z0-9_\- ]+', '', message.text.strip())
            if not name:
                await message.reply_text("❌ That's not a valid filename. Please try again.")
                return
            out_name = f"{name}.html"
            try:
                with open(TEMPLATE_HTML, "r", encoding="utf-8", errors="ignore") as f:
                    html_template = f.read()
                
                final_html = replace_questions_in_template(
                    html_template, state["questions"], state["time"], state["negative"]
                ).encode("utf-8")
                
                file_obj = io.BytesIO(final_html)
                file_obj.name = out_name
                
                await message.reply_document(file_obj, caption=f"✅ Here is your quiz: **{out_name}**")
            except FileNotFoundError:
                await message.reply_text(f"❌ **Error:** The template file `{TEMPLATE_HTML}` was not found.")
            except Exception as e:
                await message.reply_text(f"❌ An error occurred while generating the HTML file: {e}")
            
            del user_state[uid] # End of flow
            return
#end

# ── RUN BOT ──
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
    else:
        print("Bot is running...")
        app.run()
