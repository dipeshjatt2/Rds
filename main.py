# Add these with your other imports at the top of the file
import zipfile
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from datetime import datetime 
import platform 
import psutil
import convertapi
import html
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
CONVERTAPI_TOKEN = os.environ.get("CONVERTAPI_SECRET")
# --- [NEW] AI Configuration ---
GEMINI_API_KEY = os.environ.get("aikey") # This is the line you requested
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
STYLISH_SIGNATURE = "@andr0idpie9" # Stylish "by yourname"
BOT_START_TIME = datetime.now()

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
 # <-- Make sure this import is at the top of your script with the others!
@app.on_message(filters.command("ping"))
async def ping_handler(client, message: Message):
    """
    Shows the bot's and system's current status.
    """
    # --- Start timing for ping calculation ---
    start_time = time.time()
    status_msg = await message.reply_text("Pinging...")
    end_time = time.time()
    ping = f"{(end_time - start_time) * 1000:.2f}ms"

    # --- Get System Information ---
    system = f"{platform.system()} {platform.release()}"
    architecture = f"{platform.architecture()[0]}"
    
    # --- Get Resource Usage ---
    cpu_usage = f"{psutil.cpu_percent(interval=0.5)}%"
    
    # RAM
    ram = psutil.virtual_memory()
    ram_used_gb = ram.used / (1024**3)
    ram_total_gb = ram.total / (1024**3)
    ram_usage = f"{ram_used_gb:.2f}GB / {ram_total_gb:.2f}GB ({ram.percent}%)"

    # Disk
    disk = psutil.disk_usage('/')
    disk_used_gb = disk.used / (1024**3)
    disk_total_gb = disk.total / (1024**3)
    disk_usage = f"{disk_used_gb:.2f}GB / {disk_total_gb:.2f}GB ({disk.percent}%)"
    
    # --- Get Time & Uptime ---
    uptime = str(datetime.now() - BOT_START_TIME).split('.')[0] # Removes microseconds
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- Prepare the final message ---
    response_text = f"""```
┏━━━━━━━⍟
┃ 𝐒𝐲𝐬𝐭𝐞𝐦 𝐒𝐭𝐚𝐭𝐮𝐬
┗━━━━━━━━━━━⊛```
[☆] 𝐏𝐢𝐧𝐠 ➳ {ping}
[☆] 𝐒𝐲𝐬𝐭𝐞𝐦 ➳ {system}
[☆] 𝐀𝐫𝐜𝐡𝐢𝐭𝐞𝐜𝐭𝐮𝐫𝐞 ➳ {architecture}
──────── ⸙ ─────────
[☆] 𝐂𝐏𝐔 𝐔𝐬𝐚𝐠𝐞 ➳ {cpu_usage}
[☆] 𝐑𝐀𝐌 𝐔𝐬𝐚𝐠𝐞 ➳ {ram_usage}
[☆] 𝐃𝐢𝐬𝐤 𝐔𝐬𝐚𝐠𝐞 ➳ {disk_usage}
──────── ⸙ ─────────
[☆] 𝐔𝐩𝐭𝐢𝐦𝐞 ➳ {uptime}
[☆] 𝐓𝐢𝐦𝐞 ➳ {current_time}
──────── ⸙ ─────────```
[☆] 𝐁𝐨𝐭 𝐁𝐲 ➳ ⏤‌ @andr0idpie9```"""

    # --- Edit the message with the final stats ---
    await status_msg.edit_text(response_text)

    
# ── PHONE LOOKUP HANDLER (/ph) ──

@app.on_message(filters.command("ph"))
async def phone_lookup_handler(client, message: Message):
    """
    Looks up a phone number via the specified API and formats the result.
    Usage: /ph [number]
    """
    # 1. Validate Input
    try:
        command_parts = message.text.split(None, 1)
        if len(command_parts) < 2:
            await message.reply_text("<b>Usage:</b> <code>/ph [number]</code>\n\nPlease provide a phone number to search.", parse_mode=ParseMode.HTML)
            return
        
        phone_number = command_parts[1].strip()
        # Basic check to ensure it looks like a number
        if not phone_number.isdigit() or len(phone_number) < 10:
             await message.reply_text("<b>Invalid number.</b> Please provide a valid 10-digit mobile number.", parse_mode=ParseMode.HTML)
             return
    except Exception:
        await message.reply_text("Error parsing your command. Please check the format.")
        return

    status_msg = await message.reply_text(f"🔍 <b>Searching details for:</b> <code>{phone_number}</code>...", parse_mode=ParseMode.HTML)

    # 2. Define API details and make the request
    API_URL = "https://osint.stormx.pw/index.cpp"
    PARAMS = {
        "key": "dark",
        "number": phone_number
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Set a 15-second timeout for the request
            async with session.get(API_URL, params=PARAMS, timeout=15) as resp:
                
                if resp.status != 200:
                    await status_msg.edit(f"❌ <b>API Error:</b> Received status code <code>{resp.status}</code>. The service might be down.", parse_mode=ParseMode.HTML)
                    return
                
                # Get the response as JSON
                data = await resp.json()

    except aiohttp.ClientConnectorError:
        await status_msg.edit("❌ <b>Network Error:</b> Could not connect to the service. The (ngrok) API may be offline.", parse_mode=ParseMode.HTML)
        return
    except asyncio.TimeoutError:
        await status_msg.edit("❌ <b>Request Timed Out:</b> The server took too long to respond.", parse_mode=ParseMode.HTML)
        return
    except (json.JSONDecodeError, aiohttp.ContentTypeError):
         await status_msg.edit("❌ <b>API Error:</b> The server returned invalid data (expected JSON).", parse_mode=ParseMode.HTML)
         return
    except Exception as e:
        await status_msg.edit(f"❌ <b>An unexpected error occurred:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return

    # 3. Parse and Format the Response
    try:
        results = data.get("data")
        if not results or not isinstance(results, list):
            await status_msg.edit(f"🤷 <b>No results found</b> for <code>{phone_number}</code>.", parse_mode=ParseMode.HTML)
            return

        # Start building the formatted output message
        response_text = f"✅ <b>Found {len(results)} result(s) for <code>{phone_number}</code>:</b>\n"
        
        for i, entry in enumerate(results, start=1):
            # Use html.escape to safely display data, even if it contains < or >
            name = html.escape(entry.get("name", "N/A"))
            fname = html.escape(entry.get("fname", "N/A"))
            # Replace '!' separators in the address with newlines for readability
            address = html.escape(entry.get("address", "N/A")).replace("!", "\n")
            circle = html.escape(entry.get("circle", "N/A"))
            mobile = html.escape(entry.get("mobile", "N/A"))
            
            # Append each formatted result to the message
            response_text += f"\n───────────────\n"
            response_text += f"👤 <b>Result {i}:</b>\n"
            response_text += f"┣ <b>Name:</b> <code>{name}</code>\n"
            response_text += f"┣ <b>Father's Name:</b> <code>{fname}</code>\n"
            response_text += f"┣ <b>Mobile:</b> <code>{mobile}</code>\n"
            response_text += f"┣ <b>Circle:</b> <code>{circle}</code>\n"
            response_text += f"┗ <b>Address:</b>\n<code>{address}</code>\n"

        # Edit the original status message with the final formatted results
        await status_msg.edit(response_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await status_msg.edit(f"❌ <b>Error formatting data:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)



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

        "──────────────────────────\n"
        "🤖 **AI Commands**\n"
        "🔹 **/ai** - Generates new MCQs from any topic.\n"
        "🔹 **/arrange** - [Reply] Uses AI to reformat a `.txt` file into a quiz.\n\n"
        "──────────────────────────\n"
        
        "🔂 **Conversion & Scraping**\n"
        "🔹 **/txqz** - Paste text or reply to a file to create multiple quiz polls.\n"
        "🔹 **/poll2txt** - [Reply] Scrapes a quiz bot start message to get all polls.\n\n"
        
        "──────────────────────────\n"
        
        "⚙️ **Utility**\n"
        "🔹 **/htmk** - Convert a quiz file (`.txt` or `.csv`) into an interactive HTML file.\n"
        "🔹 **/shufftxt** - [Reply] Shuffles questions and options in a quiz file.\n"
        "🔹 **/create** - Create a single quiz poll manually.\n\n"
        
        "──────────────────────────\n"
        "🧑‍💻 **Developer:** @andr0idpie9"
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
    This helper function manages the entire userbot scraping process.
    
    [MODIFIED - V6]:
      - [CRITICAL FIX]: Corrected the get_messages call from 'message_id=' to 'message_ids='.
        This was causing the scraper to fail its fetch, skip all logic, 
        and default to option 0 every time. This should fix the core bug.
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
            This handler uses the exact answer-fetching logic from Script 2 (save_poll).
            """
            # Any poll in this private session MUST be from the quiz bot.
            
            # --- [START: EXACT LOGIC FROM SCRIPT 2 'save_poll'] ---
            poll = poll_message.poll
            correct_index = None

            try:
                # 1. Vote on the poll with the first option
                await userbot.vote_poll(
                    chat_id=poll_message.chat.id,
                    message_id=poll_message.id,
                    options=[0] # Vote for option index 0
                )
                
                # 2. WAIT 5 SECONDS (Matching Script 2 logic)
                await asyncio.sleep(5) 
                
                # 3. Re-fetch the message to get the updated poll data
                # [FIXED HERE]: Changed 'message_id' to 'message_ids'
                updated_message = await userbot.get_messages(
                    chat_id=poll_message.chat.id,
                    message_ids=poll_message.id 
                )
                
                # 4. Reliably get the correct_option_id using all fallbacks
                if updated_message and updated_message.poll:
                    updated_poll = updated_message.poll
                    
                    # Method 1: Primary check (the direct attribute)
                    correct_index = getattr(updated_poll, "correct_option_id", None)

                    # Method 2: Fallback to voter_count (from Script 2)
                    if correct_index is None:
                        for i, option in enumerate(updated_poll.options):
                            voter_count = getattr(option, "voter_count", 0)
                            if voter_count > 0:
                                correct_index = i
                                break

                    # Method 3: Fallback to 0 if still nothing (from Script 2)
                    if correct_index is None and updated_poll.type == PollType.QUIZ: # Use Enum
                        correct_index = 0

            except Exception as e:
                print(f"[Scraper Error] Failed to vote or fetch update: {e}")
                # Fallback to original poll data if voting fails entirely
                correct_index = getattr(poll_message.poll, "correct_option_id", None)
            
            # Final Fallback: If still no correct index, set to 0 for quiz polls (from Script 2)
            if correct_index is None and poll.type == PollType.QUIZ:
                correct_index = 0
            # --- [END: EXACT LOGIC FROM SCRIPT 2 'save_poll'] ---

            data = {
                "text": poll.question,
                "options": [opt.text for opt in poll.options],
                "correctIndex": correct_index, # This will now be the TRUE index
                "explanation": getattr(poll, "explanation", "") or ""
            }
            scraped_data["polls"].append(data)
            
            # Update progress status
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
        await status_msg.edit("▶️ Sent `/start` command. Waiting for bot's reply...")
        await asyncio.sleep(4) # Give the bot time to reply

        # --- [NEW FEATURE LOGIC] ---
        # Check the bot's reply for "already took quiz"
        clicked_ready = False
        last_message = None
        async for msg in userbot.get_chat_history(bot_username, limit=1):
            last_message = msg

        if not last_message:
            raise ValueError("Bot did not reply to the /start command.")

        # CASE 1: We already took the quiz
        if last_message.text and "you already took this quiz" in last_message.text.lower():
            await status_msg.edit("👍 Quiz already taken. Clicking 'Try Again'...")
            
            if not (last_message.reply_markup and last_message.reply_markup.inline_keyboard):
                raise ValueError("'Try Again' button not found on 'already taken' message.")
            
            # Click "Try Again" (Button 0)
            await last_message.click(0) 
            
            await status_msg.edit("⏳ Waiting for 'I am ready' confirmation...")
            await asyncio.sleep(3) # Wait for the new message to appear

            # Now fetch the NEW last message (which must be the 'I am ready' prompt)
            ready_message = None
            async for msg in userbot.get_chat_history(bot_username, limit=1):
                ready_message = msg
            
            if not (ready_message and ready_message.reply_markup and ready_message.reply_markup.inline_keyboard):
                raise ValueError("Could not find the 'I am ready' button after clicking 'Try Again'.")
            
            await ready_message.click(0) # Click "I am ready" (Button 0)
            await status_msg.edit("👍 Clicked **I am ready**. Now answering and capturing polls...")
            clicked_ready = True

        # CASE 2: This is a fresh quiz (the message has the 'I am ready' button)
        elif last_message.reply_markup and last_message.reply_markup.inline_keyboard:
            await status_msg.edit("👍 Fresh quiz. Clicking **I am ready** button...")
            await last_message.click(0) # Click "I am ready"
            clicked_ready = True
        
        else:
            # Neither "already taken" nor a button prompt? Error.
            raise ValueError(f"Bot replied with an unknown message (no buttons found). Text: {last_message.text[:100]}")
        
        if not clicked_ready:
            raise ValueError("A critical error occurred and the 'I am ready' button was not clicked.")
        # --- [END OF NEW FEATURE LOGIC] ---


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
        # Only edit the status message if it hasn't been deleted or encountered an error
        try:
            await status_msg.edit(f"🛑 **Scraping Finished!**\n\nReason: {scraped_data.get('stop_reason', 'N/A')}\nTotal polls collected: {len(scraped_data['polls'])}\n\nFormatting data...")
        except:
            pass # Ignore if message was already deleted or inaccessible

    # --- Format and Send Data (Matching /data4 format) ---
    if not scraped_data["polls"]:
        await status_msg.edit("🤷 No polls were collected. Nothing to send.")
        return

    try:
        lines = []
        option_labels = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"] # Labels from /data4

        for idx, q in enumerate(scraped_data["polls"], start=1):
            # 1. Question text
            lines.append(f"{idx}. {q['text']}")

            # 2. Options (with ✅ checkmark)
            for i, option in enumerate(q.get("options", [])):
                correct_mark = " ✅" if q.get("correctIndex") == i else ""
                label = option_labels[i] if i < len(option_labels) else str(i + 1)
                lines.append(f"({label}) {option}{correct_mark}")

            # 3. Explanation (with quotes, matching /data4)
            explanation = q.get("explanation", "")
            if explanation:
                lines.append(f"Ex: “{explanation}”") # Using curly quotes from /data4
            else:
                lines.append("Ex: ") # If no explanation, match the format "Ex: "

            # 4. Blank line after "Ex:"
            lines.append("")
            
            # 5. Extra blank line (between questions)
            lines.append("")

        content = "\n".join(lines).strip() # Use strip() to remove the trailing blank lines
        
        output_file = f"quiz_data_{user_id}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

        await status_msg.delete()
        await main_bot_client.send_document(
            chat_id=chat_id,
            document=output_file,
            caption="🎉 **Here is your formatted quiz data!** (Format /data4)"
        )
        os.remove(output_file)

    except Exception as e:
        await main_bot_client.send_message(chat_id, f"❌ Failed to format and send the file.\nError: {e}")


@app.on_message(filters.command("poll2txt"))
async def poll2txt_handler(client, message: Message):
    """
    Initiates the poll scraping process.
    Usage: Reply to a quiz bot's 'Start message with /poll2txt
    """
    user_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("⚠️ **Usage:** Please reply to a message that contains a 'Start Quiz' button with the command `/poll2txt`.")
        return

    if user_id in user_sessions:
        await message.reply_text("⏳ You already have an active scraping session. Please wait for it to complete.")
        return

    user_sessions[user_id] = True 
    # This line is correct and contains no SyntaxError
    asyncio.create_task(run_scraper(client, message, message.reply_to_message))

#ocr
@app.on_message(filters.command("ocr"))
async def ocr_handler(client, message: Message):
    """
    Converts PDF to text using ConvertAPI.
    Usage: Reply to a PDF file with /ocr
    """
    try:
        # Check if ConvertAPI is configured        
        if not CONVERTAPI_TOKEN:
            await message.reply_text("❌ **OCR Error:** CONVERTAPI_TOKEN is not configured.")
            return

        # Check if user replied to a message with a PDF
        if not message.reply_to_message or not message.reply_to_message.document:
            await message.reply_text("⚠️ **Usage:** Please reply to a PDF file with /ocr")
            return

        # Check file type and size
        doc = message.reply_to_message.document
        fname = doc.file_name or "file.pdf"
        fname_lower = fname.lower()
        
        if not fname_lower.endswith(".pdf"):
            await message.reply_text("❌ Unsupported file type. Please reply to a PDF file.")
            return
        
        if doc.file_size > 2 * 1024 * 1024:
            await message.reply_text("❌ **File Too Large:** The PDF must be under 2MB.")
            return

        status_msg = await message.reply_text("📥 Downloading PDF file...")
        pdf_path = None

        try:
            # Download the PDF file
            pdf_path = await message.reply_to_message.download()
            
            await status_msg.edit("🔍 Converting PDF to text... (This may take a few minutes)")

            # Read the PDF file as bytes
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()

            # Prepare the request to ConvertAPI
            url = "https://v2.convertapi.com/convert/pdf/to/txt"
            params = {"Secret": CONVERTAPI_TOKEN, "StoreFile": "true"}
            files = {"File": (fname, pdf_data, "application/pdf")}

            # Send the conversion request
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, data=files, timeout=600) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API error: Status {response.status}")
                    
                    result_data = await response.json()
                    
                    # Safely check for files in response
                    files_list = result_data.get("Files") or []
                    if not files_list:
                        raise Exception("No output file received from conversion")
                    
                    # Download the converted text
                    output_url = files_list[0].get("Url", "")
                    if not output_url:
                        raise Exception("No download URL in response")
                    
                    async with session.get(output_url) as txt_response:
                        if txt_response.status != 200:
                            raise Exception(f"Download failed: Status {txt_response.status}")
                        
                        text_content = await txt_response.text()

            # Check if text content is valid
            if not text_content or not text_content.strip():
                await status_msg.edit("❌ Converted text is empty. PDF might be image-based.")
                return

            # Create and send the text file
            file_obj = io.BytesIO(text_content.encode("utf-8"))
            base_name = os.path.splitext(fname)[0]
            file_obj.name = f"{base_name}_converted.txt"

            await message.reply_document(file_obj, caption="✅ PDF converted to text!")
            await status_msg.delete()

        except asyncio.TimeoutError:
            await status_msg.edit("❌ Conversion timeout (10 minutes exceeded)")
        except aiohttp.ClientError as e:
            error_msg = f"Network error: {type(e).__name__}"
            await status_msg.edit(f"❌ {error_msg}")
        except Exception as e:
            # Safe error message handling
            error_type = type(e).__name__
            error_desc = str(e) or "No details"
            await status_msg.edit(f"❌ Conversion error: {error_type} - {error_desc}")
            
        finally:
            # Clean up temporary file
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except:
                    pass

    except Exception as e:
        # Global error handler
        error_type = type(e).__name__
        await message.reply_text(f"❌ Unexpected error: {error_type}")
# ── 6. [NEW] AI MCQ Generator (/ai) ──
@app.on_message(filters.command("ai"))
async def generate_ai_mcqs(client, message: Message):
    """
    Generates MCQs using the Gemini AI API.
    Handles quoted/unquoted topics, encoding, and optional language flag.
    Usage:
      /ai "Indian History" 30 "Hindi"
      /ai Modern Physics 25 "English"
      /ai Gupta Empire 20 "Hindi and English"
    """
    if not GEMINI_API_KEY:
        await message.reply_text("❌ **AI Error:** `GEMINI_API_KEY` is not configured by the bot owner.")
        return

    # --- 1. Robust Input Parser ---
    try:
        command_parts = message.text.split(None, 1)
        if len(command_parts) < 2:
            await message.reply_text(
                "❌ **Usage:** `/ai [Topic Name] [Amount] [Language]`\n"
                "**Example 1:** `/ai \"Indian History\" 30 \"Hindi\"`\n"
                "**Example 2:** `/ai Gupta Empire 20 \"Hindi and English\"`"
            )
            return

        args_text = command_parts[1].strip()
        topic, amount_str, language = "", "", "Hindi and English"  # default bilingual

        # Regex for quoted topic and optional language
        quote_match = re.search(r'^"(.*?)"\s+(\d+)(?:\s+"(.*?)")?\s*$', args_text)
        if quote_match:
            topic = quote_match.group(1)
            amount_str = quote_match.group(2)
            if quote_match.group(3):
                language = quote_match.group(3).strip()
        else:
            # Split into parts, expecting ... topic amount [language]
            parts = args_text.rsplit(None, 2)
            if len(parts) >= 2 and parts[-2].isdigit():
                topic = parts[0].strip().strip('"')
                amount_str = parts[-2]
                if len(parts) == 3:
                    language = parts[-1].strip('"')
            else:
                await message.reply_text(
                    "❌ **Invalid Format.** Amount (number) must come before language.\n"
                    "**Example 1:** `/ai \"Gupta Empire\" 20 \"Hindi\"`\n"
                    "**Example 2:** `/ai Gupta Empire 20 \"Hindi and English\"`"
                )
                return

        if not topic:
            await message.reply_text("❌ No topic provided. Please specify a topic.")
            return

        amount = int(amount_str)
        if amount <= 0 or amount > 500:
            await message.reply_text("❌ Please provide an amount between 1 and 500.")
            return

    except Exception as e:
        await message.reply_text(f"⚠️ Error parsing command: {e}")
        return

    status_msg = await message.reply_text(
        f"⏳ **Generating {amount} MCQs for `{topic}` in {language}...**\nThis may take a moment."
    )

    # --- 2. Build AI Prompt ---
    prompt_text = f"""Create {amount} MCQs on the topic {topic} in **{language}** at a difficult level.
Format:

Each question must be numbered (1., 2., etc.)
Each question should have exactly 4 options: (a), (b), (c), (d).

Place a ✅ emoji next to the single correct option. Ensure the correct option's position is randomized/shuffled across questions (e.g., not always (a) or (b)).

After each question, add a brief explanation under "Ex:" (max 200 characters).

Every explanation MUST end with the text: {STYLISH_SIGNATURE}

Output everything inside a single markdown code block (```). Keep everything concise.

Example format:
1. Who founded the Tughlaq Dynasty? / तुग़लक वंश की स्थापना किसने की?
(a) Ghiyasuddin Tughlaq / घियासुद्दीन तुग़लक ✅
(b) Alauddin Khilji / अलाउद्दीन खिलजी
(c) Bahlol Lodhi / बहलोल लोधी
(d) Khizr Khan / खिज़र खान
Ex: Ghiyasuddin Tughlaq founded the dynasty in 1320. {STYLISH_SIGNATURE}

Now make the MCQs for the topic: {topic}
"""

    # --- 3. Call Gemini API (with ENCODING FIX) ---
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
            "maxOutputTokens": 8192,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload, headers=headers, timeout=1800) as resp:
                response_bytes = await resp.read()

                if resp.status != 200:
                    error_text = response_bytes.decode('utf-8', errors='ignore')
                    await status_msg.edit(f"❌ **API Error: {resp.status}**\nFailed to get data from AI.\n`{error_text}`")
                    return
                
                response_text = response_bytes.decode('utf-8')
                response_json = json.loads(response_text)

    except asyncio.TimeoutError:
         await status_msg.edit("❌ **Request Timed Out:** The AI took too long to respond.")
         return
    except Exception as e:
        await status_msg.edit(f"❌ **HTTP Request Failed:**\n`{str(e)}`")
        return

    # --- 4. Parse Response and Create File ---
    try:
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        clean_text = re.sub(r'^```(markdown|text|)?\s*|\s*```$', '', raw_text, flags=re.MULTILINE | re.DOTALL).strip()

        if not clean_text or len(clean_text) < 50:
             await status_msg.edit(f"❌ **Empty Response:** The AI returned an empty or invalid response.\n`{response_json}`")
             return

        topic_cleaned = re.sub(r'[^a-zA-Z0-9]', '', topic.replace(" ", "_"))
        if len(topic_cleaned) > 50: topic_cleaned = topic_cleaned[:50]
        filename = f"{topic_cleaned}_{language.replace(' ', '_')}_mcqs_by_{message.from_user.id}.txt"

        file_data = io.BytesIO(clean_text.encode('utf-8-sig'))
        file_data.name = filename

        await message.reply_document(
            document=file_data,
            caption=f"✅ Here are your {amount} MCQs on `{topic}` in **{language}**!"
        )
        await status_msg.delete()

    except (KeyError, IndexError, TypeError):
        await status_msg.edit(f"❌ **Failed to Parse AI Response.**\nCould not find text in the response.\nFull Response: `{response_json}`")
    except Exception as e:
        await status_msg.edit(f"❌ **An error occurred processing the file:**\n`{str(e)}`")

# ── 7. [NEW] AI Content Arranger (/arrange) ──
@app.on_message(filters.command("arrange"))
async def arrange_handler(client, message: Message):
    """
    Handles the /arrange command.
    Usage: Reply to a .txt file (max 80KB) with /arrange.
    The bot will send the text content to the AI and ask it to reformat
    it into the standardized quiz format.
    """
    # --- 1. Check API Key ---
    if not GEMINI_API_KEY:
        await message.reply_text("❌ **AI Error:** `GEMINI_API_KEY` is not configured by the bot owner.")
        return

    # --- 2. Validate Input Message ---
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.document:
        await message.reply_text(
            "⚠️ **Usage:** Please reply to a `.txt` file with the command `/arrange`."
        )
        return

    doc = target_msg.document
    fname = (doc.file_name or "file.dat").lower()

    if not fname.endswith(".txt"):
        await message.reply_text("❌ Unsupported file type. Please reply to a `.txt` file.")
        return
    
    if doc.file_size > 80 * 1024: # 80 KB limit
        await message.reply_text("❌ **File Too Large:** The input file must be under 80 KB.")
        return

    status_msg = await message.reply_text("⏳ Downloading and reading file...")

    # --- 3. Read File Content ---
    try:
        path = await target_msg.download()
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw_text_content = f.read()
        
        try:
            os.remove(path)
        except Exception:
            pass # Continue even if deletion fails

        if not raw_text_content.strip():
            await status_msg.edit("❌ The file appears to be empty.")
            return

    except Exception as e:
        await status_msg.edit(f"❌ An error occurred while reading the file: {e}")
        return

    await status_msg.edit("🤖 **Contacting AI...**\nAsking AI to arrange the content. This may take a moment.")

    # --- 4. Build AI Prompt ---
    # This prompt instructs the AI to use the provided text as source material
    # and reformat it according to the user's exact specifications.
    prompt_text = f"""Please analyze the following unstructured text content and meticulously reformat it into a structured MCQ (Multiple Choice Question) format.

Your task is to convert the raw data provided below into a clean, numbered list of questions.

REQUIRED OUTPUT FORMAT:
- Each question must be numbered (1., 2., etc.).
- Each question must have all its options listed below it, prefixed with (a), (b), (c), (d), etc. (Include all relevant options, e.g., (e) if present).
- You MUST identify the single correct option for each question and place a ✅ emoji right after it.
- Ensure the position of the correct answer (✅) is varied (randomized) across different questions.
- After the options, you MUST include a brief explanation prefixed with "Ex:".
- Every explanation line MUST end with the signature: {STYLISH_SIGNATURE}
- The entire output MUST be enclosed in a single markdown code block (```).

Example of the REQUIRED format:
1. Who founded the Tughlaq Dynasty? / तुग़लक वंश की स्थापना किसने की?
(a) Ghiyasuddin Tughlaq / घियासुद्दीन तुग़लक ✅
(b) Alauddin Khilji / अलाउद्दीन खिलजी
(c) Bahlol Lodhi / बहलोल लोधी
(d) Khizr Khan / खिज़र खान
Ex: Ghiyasuddin Tughlaq founded the dynasty in 1320. {STYLISH_SIGNATURE}

---
Here is the RAW TEXT CONTENT you must reformat:

{raw_text_content}
---

Now, arrange the text above according to the specified format. Ensure every rule is followed.
"""

    # --- 5. Call Gemini API (Copied from /ai handler) ---
    headers = {
        'Content-Type': 'application/json',
        'X-goog-api-key': GEMINI_API_KEY
    }
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
         "generationConfig": {
            "temperature": 0.3, # Lower temperature for formatting tasks
            "topK": 1,
            "topP": 1,
            "maxOutputTokens": 8192,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload, headers=headers, timeout=1800) as resp:
                response_bytes = await resp.read()

                if resp.status != 200:
                    error_text = response_bytes.decode('utf-8', errors='ignore')
                    await status_msg.edit(f"❌ **API Error: {resp.status}**\nFailed to get data from AI.\n`{error_text}`")
                    return
                
                response_text = response_bytes.decode('utf-8')
                response_json = json.loads(response_text)

    except asyncio.TimeoutError:
         await status_msg.edit("❌ **Request Timed Out:** The AI took too long to respond.")
         return
    except Exception as e:
        await status_msg.edit(f"❌ **HTTP Request Failed:**\n`{str(e)}`")
        return

    # --- 6. Parse Response and Create File ---
    try:
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        # Clean the markdown block wrapper (```) from the AI response
        clean_text = re.sub(r'^```(markdown|text|)?\s*|\s*```$', '', raw_text, flags=re.MULTILINE | re.DOTALL).strip()

        if not clean_text or len(clean_text) < 20:
             await status_msg.edit(f"❌ **Empty Response:** The AI returned an empty or invalid formatted response.\n`{response_json}`")
             return

        # Create the output file
        base_name = os.path.splitext(fname)[0]
        filename = f"arranged_{base_name}.txt"

        file_data = io.BytesIO(clean_text.encode('utf-8-sig')) # Use utf-8-sig to include BOM
        file_data.name = filename

        await message.reply_document(
            document=file_data,
            caption=f"✅ AI has successfully arranged your file!"
        )
        await status_msg.delete()

    except (KeyError, IndexError, TypeError):
        await status_msg.edit(f"❌ **Failed to Parse AI Response.**\nCould not find text in the response.\nFull Response: `{response_json}`")
    except Exception as e:
        await status_msg.edit(f"❌ **An error occurred processing the output file:**\n`{str(e)}`")


@app.on_message(filters.command("split"))
async def split_handler(client, message: Message):
    """
    Splits a quiz file into multiple files with specified number of questions each.
    Usage: Reply to a .txt file with /split [number]
    """
    # Check if user replied to a message with a file
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.reply_text(
            "⚠️ **Usage:** Please reply to a `.txt` or `.csv` file with the command `/split [number]`\n\n"
            "**Example:** `/split 50` (will split into files with 50 questions each)"
        )
        return
    
    # Parse the split number
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply_text("❌ Please specify the number of questions per file. Example: `/split 50`")
            return
        
        questions_per_file = int(command_parts[1])
        if questions_per_file <= 0:
            await message.reply_text("❌ Number of questions per file must be greater than 0.")
            return
    except ValueError:
        await message.reply_text("❌ Please provide a valid number. Example: `/split 50`")
        return
    
    # Check file type
    doc = message.reply_to_message.document
    fname = (doc.file_name or "file").lower()
    if not (fname.endswith(".txt") or fname.endswith(".csv")):
        await message.reply_text("❌ Unsupported file type. Please use a `.txt` or `.csv` file.")
        return
    
    status_msg = await message.reply_text(f"📥 Downloading and parsing file...")
    
    try:
        # Download and parse the file
        path = await message.reply_to_message.download()
        
        if fname.endswith(".csv"):
            questions = parse_csv(path)
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            questions = detect_and_parse(txt)
        
        # Clean up downloaded file
        try:
            os.remove(path)
        except Exception:
            pass
        
        if not questions:
            await status_msg.edit("❌ Could not parse any questions from the file. Make sure the format is supported.")
            return
        
        total_questions = len(questions)
        if questions_per_file > total_questions:
            await status_msg.edit(f"❌ The file only has {total_questions} questions, but you requested {questions_per_file} per file.")
            return
        
        # Calculate number of files needed
        num_files = (total_questions + questions_per_file - 1) // questions_per_file
        
        await status_msg.edit(f"✅ Parsed {total_questions} questions.\n\nSplitting into {num_files} files with {questions_per_file} questions each...")
        
        # Split questions into chunks
        chunks = [questions[i:i + questions_per_file] for i in range(0, total_questions, questions_per_file)]
        
        # Process each chunk
        for i, chunk in enumerate(chunks, start=1):
            await status_msg.edit(f"📝 Processing file {i}/{num_files}...")
            
            # Format questions for output
            out_lines = []
            for j, q in enumerate(chunk, start=1):
                qtext = q.get("text", "").replace("\r", "")
                out_lines.append(f"{j}. {qtext}")
                
                for idx, opt in enumerate(q.get("options", [])):
                    prefix = f"({chr(97 + idx)})"
                    mark = " ✅" if idx == q.get("correctIndex", -1) else ""
                    out_lines.append(f"{prefix} {opt}{mark}")
                
                if q.get("explanation"):
                    out_lines.append(f"Ex: {q.get('explanation')}")
                out_lines.append("")
            
            # Create file
            final_txt = "\n".join(out_lines).strip()
            file_obj = io.BytesIO(final_txt.encode("utf-8"))
            
            # Create filename
            base_name = os.path.splitext(os.path.basename(fname))[0]
            file_obj.name = f"{base_name}_part{i}_{len(chunk)}q.txt"
            
            # Send file with caption
            caption = (
                f"📁 Part {i} of {num_files}\n"
                f"📊 Contains {len(chunk)} questions\n"
                f"🔢 Total questions in file: {total_questions}\n"
                f"👤 Requested by: {message.from_user.mention}\n"
                f"#SplitQuiz"
            )
            
            await message.reply_document(
                file_obj,
                caption=caption,
                reply_to_message_id=message.reply_to_message_id
            )
            
            # Small delay to avoid rate limits
            await asyncio.sleep(1)
        
        await status_msg.edit(f"✅ Successfully split {total_questions} questions into {num_files} files!")
        
    except Exception as e:
        await status_msg.edit(f"❌ An error occurred while processing the file: {e}")

# ── Custom Delay Text-to-Poll Sender (/tx) ──

@app.on_message(filters.command("tx"))
async def tx_handler(client, message: Message):
    """
    Sends quiz polls from text or a file with a user-defined delay.
    Usage: /tx [delay_in_seconds] [quiz_text]
    Example: /tx 10 ... (sends polls every 10 seconds)
    Default delay is 3 seconds if not specified.
    """
    DEFAULT_DELAY = 3
    delay = DEFAULT_DELAY
    content = None

    # --- 1. Get Content & Parse Delay ---
    if message.reply_to_message and message.reply_to_message.document:
        try:
            # Download content from the replied-to file
            file_path = await message.reply_to_message.download()
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            os.remove(file_path)
            
            # Check for a delay number in the command/caption (e.g., /tx 10)
            if len(message.command) > 1 and message.command[1].isdigit():
                parsed_delay = int(message.command[1])
                if parsed_delay > 0:
                    delay = parsed_delay

        except Exception as e:
            await message.reply_text(f"❌ Error downloading document: {str(e)}")
            return
    elif len(message.command) > 1:
        args_text = message.text.split(None, 1)[1]
        parts = args_text.split(None, 1)

        # Check if the first argument is a positive number for the delay
        if parts and parts[0].isdigit() and int(parts[0]) > 0:
            delay = int(parts[0])
            if len(parts) > 1:
                content = parts[1] # The rest of the message is content
            else:
                await message.reply_text("⚠️ You provided a delay, but no quiz text after it.")
                return
        else:
            # If no valid delay is found, the whole argument is content
            content = args_text
    else:
        await message.reply_text("⚠️ Please provide quiz text after /tx or reply to a text document.")
        return

    if not content:
        await message.reply_text("⚠️ No content found.")
        return

    # --- 2. Parse the Content (Identical logic to /txqz) ---
    questions = []
    try:
        if 'const quizData' in content:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            json_str = content[json_start:json_end]
            data = json.loads(json_str)
            for item in data['questions']:
                q = {
                    'question': item['text'].strip(),
                    'options': [opt.strip() for opt in item['options']],
                    'correct': item['correctIndex'],
                    'explanation': (item.get('explanation', '').strip() + ' ' + item.get('reference', '').strip()).strip()
                }
                if q['options'] and q['correct'] < len(q['options']):
                    questions.append(q)
    except json.JSONDecodeError:
        pass

    if not questions:
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r'^[Qq]?\d+\.', line):
                q = {'question': re.sub(r'^[Qq]?\d+\.', '', line).strip(), 'options': [], 'correct': -1, 'explanation': ''}
                i += 1
                while i < len(lines):
                    l = lines[i].strip()
                    if re.match(r'^\([a-z]\)', l):
                        match = re.match(r'^\(([a-z])\)\s*(.*?)(?:\s*✅)?$', l)
                        if match:
                            is_correct = '✅' in lines[i]
                            q['options'].append(match.group(2).strip())
                            if is_correct: q['correct'] = len(q['options']) - 1
                        i += 1
                    elif l.startswith('Ex:'):
                        q['explanation'] = re.sub(r'^Ex:', '', l).strip()
                        i += 1
                        break
                    elif re.match(r'^[Qq]?\d+\.', l): break
                    else: i += 1
                if q['correct'] != -1 and q['options']: questions.append(q)
            else: i += 1

    if not questions:
        await message.reply_text("❌ Unable to parse any quizzes from the provided content.")
        return

    # --- 3. Send the Polls with the Custom Delay ---
    total = len(questions)
    await message.reply_text(f"✅ Parsed {total} quizzes. Sending them with a **{delay} second** delay between each...")

    for i, q in enumerate(questions):
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
            await message.reply_text(f"❌ Error sending quiz #{i+1}: {str(e)}")
        
        if i < total - 1: # Don't sleep after the last poll
            await asyncio.sleep(delay)

    await message.reply_text("🎉 All quizzes sent!")


# ── Poll Collector (/poll & /done) ──

@app.on_message(filters.command("poll"))
async def poll_command_handler(client, message: Message):
    """Initiates a poll collection session for the user."""
    uid = message.from_user.id
    # Initialize the state for this user
    user_state[uid] = {
        "flow": "poll_collection", 
        "polls": []
    }
    await message.reply_text(
        "✅ OK! I'm ready to collect your quiz polls.\n\n"
        "Please send me the polls one by one. When you're finished, send the /done command."
    )

@app.on_message(filters.command("done"))
async def done_command_handler(client, message: Message):
    """Finalizes the poll collection, formats, and sends the .txt file."""
    uid = message.from_user.id

    # Check if the user is in the correct flow
    if user_state.get(uid, {}).get("flow") != "poll_collection":
        # User might have typed /done by accident without starting /poll
        return

    collected_polls = user_state[uid].get("polls", [])

    if not collected_polls:
        await message.reply_text("You haven't sent any polls to collect. Use /poll to start.")
        del user_state[uid] # Clean up state
        return

    await message.reply_text(f"👍 Got it! Formatting {len(collected_polls)} polls into a text file...")

    # --- Format the collected polls into the specified text format ---
    out_lines = []
    for i, poll_data in enumerate(collected_polls, start=1):
        # Add the question line
        out_lines.append(f"{i}. {poll_data['question']}")
        
        # Add the option lines with (a), (b), etc.
        for idx, opt_text in enumerate(poll_data['options']):
            prefix = f"({chr(97 + idx)})" # chr(97) is 'a'
            out_lines.append(f"{prefix} {opt_text}")
        
        # Add a blank line for spacing between questions
        out_lines.append("") 

    # --- Create and send the document ---
    final_txt = "\n".join(out_lines).strip()
    file_obj = io.BytesIO(final_txt.encode("utf-8-sig"))
    file_obj.name = f"collected_polls_from_{uid}.txt"

    await message.reply_document(
        file_obj,
        caption=f"✅ Here are your {len(collected_polls)} collected polls."
    )
    
    # --- Crucial: Clean up the user's state after finishing ---
    del user_state[uid]

# This handler specifically listens for incoming polls
@app.on_message(filters.poll, group=2) # Using a group to ensure it's checked
async def poll_message_handler(client, message: Message):
    """Catches polls sent by a user who is in a poll_collection session."""
    uid = message.from_user.id
    
    # Only process this poll if the user has started the /poll flow
    if user_state.get(uid, {}).get("flow") == "poll_collection":
        poll = message.poll
        
        # Store the necessary information
        user_state[uid]["polls"].append({
            "question": poll.question,
            "options": [opt.text for opt in poll.options]
        })
        
        count = len(user_state[uid]["polls"])
        await message.reply_text(f"👍 Parsed poll #{count}. Send more or use /done to finish.")
# ... (all your existing bot code above) ...

def sanitize_filename(filename):
    """
    Sanitize a string to be safe for use as a filename.
    Removes or replaces characters that are not allowed in filenames.
    """
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    
    # Replace spaces with underscores (optional)
    filename = filename.replace(' ', '_')
    
    # Limit length to avoid issues with long filenames
    if len(filename) > 100:
        filename = filename[:100]
    
    return filename


# ── /scr Command Handler ──
@app.on_message(filters.command("scr"))
async def scr_command_handler(client, message: Message):
    """
    Scrapes quiz IDs and quizzes from TestNook, then sends a zip file.
    Usage: /scr [creator_id] [page_num] [workers (optional)]
    Example: /scr 12345 3
    Example: /scr 12345 3 10
    """
    # Parse command arguments
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply_text(
                "❌ **Usage:** `/scr [creator_id] [page_num] [workers (optional)]`\n\n"
                "**Example:** `/scr 12345 3`\n"
                "**Example:** `/scr 12345 3 10`"
            )
            return
        
        creator_id = args[1]
        page_num = int(args[2])
        workers = int(args[3]) if len(args) > 3 else 5
        
        if not creator_id.isdigit():
            await message.reply_text("❌ Creator ID must be a number.")
            return
        
        if page_num < 1:
            await message.reply_text("❌ Page number must be at least 1.")
            return
        
        if workers < 1 or workers > 20:
            await message.reply_text("❌ Workers must be between 1 and 20.")
            return
            
    except ValueError:
        await message.reply_text("❌ Invalid arguments. Please check your input.")
        return
    
    # Store scraping state
    user_id = message.from_user.id
    user_state[user_id] = {
        "flow": "scraping",
        "creator_id": creator_id,
        "page_num": page_num,
        "workers": workers,
        "cancelled": False,
        "status_message": None,
        "quiz_ids": [],
        "scraped_quizzes": []
    }
    
    # Send initial status message
    status_msg = await message.reply_text(
        f"🚀 **Starting Scraping Process**\n\n"
        f"• Creator ID: `{creator_id}`\n"
        f"• Pages: `{page_num}`\n"
        f"• Workers: `{workers}`\n\n"
        f"⏳ Step 1/3: Scraping quiz IDs..."
    )
    
    user_state[user_id]["status_message"] = status_msg
    
    # Start the scraping process
    asyncio.create_task(run_scraping_process(client, user_id))

async def run_scraping_process(client, user_id):
    """Runs the complete scraping process for a user."""
    if user_id not in user_state or user_state[user_id].get("flow") != "scraping":
        return
    
    state = user_state[user_id]
    creator_id = state["creator_id"]
    page_num = state["page_num"]
    workers = state["workers"]
    
    try:
        # Step 1: Scrape quiz IDs
        await update_status(client, user_id, "⏳ Step 1/3: Scraping quiz IDs...")
        quiz_ids = await scrape_quiz_ids(creator_id, page_num, workers)
        
        if state.get("cancelled"):
            await finalize_scraping(client, user_id, "❌ Process cancelled by user.")
            return
            
        if not quiz_ids:
            await finalize_scraping(client, user_id, "❌ No quiz IDs found. Process stopped.")
            return
            
        state["quiz_ids"] = quiz_ids
        
        # Send quiz IDs file to user
        quiz_ids_file = f"creator_{creator_id}_quiz_ids.txt"
        with open(quiz_ids_file, "w", encoding="utf-8") as f:
            for quiz in quiz_ids:
                f.write(f"{quiz['quiz_name']} : {quiz['quiz_id']}\n")
        
        await client.send_document(
            user_id,
            document=quiz_ids_file,
            caption=f"✅ Found {len(quiz_ids)} quiz IDs for creator {creator_id}"
        )
        
        # Step 2: Scrape quizzes
        await update_status(client, user_id, f"⏳ Step 2/3: Scraping {len(quiz_ids)} quizzes...")
        scraped_quizzes = await scrape_quizzes(quiz_ids, workers, user_id)
        
        if state.get("cancelled"):
            await finalize_scraping(client, user_id, "❌ Process cancelled by user.")
            return
            
        state["scraped_quizzes"] = scraped_quizzes
        
        # Step 3: Create zip file
        await update_status(client, user_id, "⏳ Step 3/3: Creating zip file...")
        zip_filename = await create_zip_file(creator_id, scraped_quizzes)
        
        # Send zip file
        await client.send_document(
            user_id,
            document=zip_filename,
            caption=f"✅ Scraping complete! {len(scraped_quizzes)} quizzes scraped for creator {creator_id}"
        )
        
        await finalize_scraping(client, user_id, "✅ Scraping process completed successfully!")
        
    except Exception as e:
        await finalize_scraping(client, user_id, f"❌ An error occurred: {str(e)}")

async def scrape_quiz_ids(creator_id, page_num, workers):
    """Scrapes quiz IDs using logic from scrapequizid.py."""
    quiz_ids = []
    BASE_URL = "https://testnookapp-f602da876a9b.herokuapp.com"
    
    HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-GB',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
        'sec-ch-ua': '"Chromium";v="127", "Not)A;Brand";v="99", "Microsoft Edge Simulate";v="127", "Lemur";v="127"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
    }
    
    urls = []
    for page in range(1, page_num + 1):
        if page == 1:
            urls.append(f"{BASE_URL}/creator/{creator_id}")
        else:
            urls.append(f"{BASE_URL}/creator/{creator_id}?page={page}")
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = []
        for url in urls:
            task = asyncio.create_task(scrape_single_page(session, url))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if isinstance(result, list):
                quiz_ids.extend(result)
    
    return quiz_ids

async def scrape_single_page(session, url):
    """Scrapes a single page for quiz data."""
    try:
        async with session.get(url, timeout=200) as response:
            response.raise_for_status()
            html = await response.text()
        
        soup = BeautifulSoup(html, 'html.parser')
        quiz_cards = soup.find_all('div', class_='quiz-card')
        
        if not quiz_cards:
            return []
        
        quizzes = []
        for card in quiz_cards:
            name_tag = card.find('h3')
            quiz_name = name_tag.get_text(strip=True) if name_tag else "Unknown Quiz Name"

            onclick_attr = card.get('onclick', '')
            match = re.search(r"/quiz/([a-zA-Z0-9]+)", onclick_attr)
            quiz_id = match.group(1) if match else None

            if quiz_id:
                quizzes.append({
                    'quiz_name': quiz_name,
                    'quiz_id': quiz_id
                })
        
        return quizzes
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []

async def scrape_quizzes(quiz_ids, workers, user_id):
    """Scrapes quizzes using logic from scrapequiz.py."""
    scraped_quizzes = []
    BASE_URL = "https://testnookapp-f602da876a9b.herokuapp.com"
    
    HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-GB',
        'Connection': 'keep-alive',
        'Cookie': 'session=.eJxNjkEKwjAQRe8y61biTBJjztF9iGYKAU0xmSJYeneDiLh9vP_4G1zXWrlIeKzcJC8FvBr-YH6FnMCDdZpnp8jGlIye-aISsYkWBvhIsbQn1wZ-27-kSawSJN-5z1GhGdV5RJwUeSRPdEB31CfqAVkk3n4HesPR_gaS-jGq.aNDBNQ.oB9tZ3n0UXy8dBQcbr38SWYEEtk',
        'Referer': f'{BASE_URL}/',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
        'sec-ch-ua': '"Chromium";v="127", "Not)A;Brand";v="99", "Microsoft Edge Simulate";v="127", "Lemur";v="127"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
    }
    
    POST_HEADERS = {
        **HEADERS,
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'Origin': BASE_URL,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
    }
    
    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(workers)
    
    async def scrape_single_quiz(quiz_info):
        """Scrapes a single quiz."""
        async with semaphore:
            if user_id in user_state and user_state[user_id].get("cancelled"):
                return None
                
            quiz_name = quiz_info['quiz_name']
            quiz_id = quiz_info['quiz_id']
            output_filename = sanitize_filename(quiz_name) + ".txt"
            
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    q_num = 0
                    quiz_content = []
                    
                    while True:
                        # Fetch the question page
                        q_url = f"{BASE_URL}/quiz/{quiz_id}/question/{q_num}"
                        async with session.get(q_url, timeout=200) as response:
                            response.raise_for_status()
                            html = await response.text()
                        
                        if "Quiz Complete" in html:
                            break
                        
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Parse question and options
                        question_text = soup.find('div', class_='question-text')
                        if question_text:
                            question_text = question_text.get_text(strip=True)
                        else:
                            question_text = "Unknown Question"
                        
                        options = []
                        option_elements = soup.find_all('div', class_='option')
                        for opt in option_elements:
                            options.append(opt.get_text(strip=True))
                        
                        # Submit a temporary answer to find the correct one
                        answer_url = f"{BASE_URL}/quiz/{quiz_id}/answer"
                        post_headers = {**POST_HEADERS, 'Referer': q_url}
                        payload = {"question_num": q_num, "selected_option": 0}
                        
                        async with session.post(answer_url, headers=post_headers, json=payload, timeout=20) as resp:
                            answer_data = await resp.json()
                        
                        if not answer_data.get('success'):
                            raise Exception(f"Failed to get answer for Q{q_num}")
                        
                        correct_option_index = answer_data['correct_option']
                        
                        # Format the question and answers
                        quiz_content.append(f"{q_num + 1}. {question_text}")
                        for i, option_text in enumerate(options):
                            cleaned_option = re.sub(r'^[A-Z]\s*', '', option_text)
                            marker = "✅" if i == correct_option_index else ""
                            quiz_content.append(f"({chr(97 + i)}) {cleaned_option} {marker}")
                        quiz_content.append("")  # Add a blank line
                        
                        q_num += 1
                        await asyncio.sleep(0.2)  # Be polite to the server
                    
                    # Save the quiz content to a file
                    with open(output_filename, 'w', encoding='utf-8') as f:
                        f.write("\n".join(quiz_content))
                    
                    return output_filename
                    
            except Exception as e:
                print(f"Error scraping quiz {quiz_id}: {e}")
                # Write error to a log file
                with open("error_log.txt", "a", encoding="utf-8") as log_file:
                    log_file.write(f"Error processing '{quiz_name}' (ID: {quiz_id}): {e}\n")
                return None
    
    # Scrape all quizzes concurrently
    tasks = []
    for quiz in quiz_ids:
        tasks.append(asyncio.create_task(scrape_single_quiz(quiz)))
    
    results = await asyncio.gather(*tasks)
    
    # Filter out None results (failed scrapes)
    return [result for result in results if result is not None]

async def create_zip_file(creator_id, scraped_files):
    """Creates a zip file with all scraped quizzes."""
    zip_filename = f"{creator_id}by@andr0idpie9.zip"
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in scraped_files:
            zipf.write(file, os.path.basename(file))
    
    # Clean up individual files
    for file in scraped_files:
        try:
            os.remove(file)
        except:
            pass
    
    return zip_filename

async def update_status(client, user_id, message):
    """Updates the status message for the user."""
    if user_id in user_state and user_state[user_id].get("status_message"):
        try:
            await user_state[user_id]["status_message"].edit_text(message)
        except:
            pass  # Ignore errors if message can't be edited

async def finalize_scraping(client, user_id, message):
    """Finalizes the scraping process and cleans up."""
    if user_id in user_state and user_state[user_id].get("status_message"):
        try:
            await user_state[user_id]["status_message"].edit_text(message)
        except:
            pass
    
    # Clean up state
    if user_id in user_state:
        del user_state[user_id]

# Add the /cancel command handler
@app.on_message(filters.command("cancel"))
async def cancel_command_handler(client, message: Message):
    """Cancels any ongoing scraping process for the user."""
    user_id = message.from_user.id
    
    if user_id in user_state and user_state[user_id].get("flow") == "scraping":
        user_state[user_id]["cancelled"] = True
        await message.reply_text("⏹️ Cancellation requested. Finishing current operations...")
        
        # If we have some data, create and send a zip file
        if user_state[user_id].get("scraped_quizzes"):
            creator_id = user_state[user_id]["creator_id"]
            scraped_quizzes = user_state[user_id]["scraped_quizzes"]
            
            zip_filename = await create_zip_file(creator_id, scraped_quizzes)
            
            await client.send_document(
                user_id,
                document=zip_filename,
                caption=f"✅ Partial results: {len(scraped_quizzes)} quizzes scraped before cancellation"
            )
    else:
        await message.reply_text("❌ No active scraping process to cancel.")

@app.on_message(filters.text & ~filters.command([
    "start", "help", "create", "ping", "poll", "done", "scr", "tx", "txqz", "htmk", "poll2txt", "shufftxt", "split", 
    "ph", "ai", "ocr", "arrange"
]))

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
