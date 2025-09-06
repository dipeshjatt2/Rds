import os
import io
import re
import json
import csv
import time
import zipfile
import sqlite3
import asyncio
import random
import traceback
import string
import glob  # Added for session file searching
from threading import Thread
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, send_file, abort
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, User
from pyrogram.enums import ParseMode, ChatMemberStatus  # Added ChatMemberStatus
# from dotenv import load_dotenv # REMOVED as requested

# load_dotenv() # REMOVED as requested

# --- CONFIG ---
# Variables are now read directly from OS environment
API_ID = int(os.environ.get("API_ID", "22118129"))
API_HASH = os.environ.get("API_HASH", "43c66e3314921552d9330a4b05b18800")
BOT_TOKEN = os.environ.get("BOT_TOK2")
OWNER_ID = int(os.environ.get("OWNER_ID", "5203820046"))
TEMPLATE_HTML = "format2.html" # Note: This variable exists but is unused by the HTML quiz generator
DB_PATH = "quizzes.db"
WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN env var required. Please set it in your environment.")

# --- Session file directory ---
SESSION_DIR = "sessions"
os.makedirs(SESSION_DIR, exist_ok=True)


# --- Pyrogram app ---
app = Client("combined_quiz_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- DB init & migration ---
def init_db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = con.cursor()
    # creators
    cur.execute("""
    CREATE TABLE IF NOT EXISTS creators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_user_id INTEGER UNIQUE,
        username TEXT,
        display_name TEXT,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )""")
    # quizzes (note time_per_question_sec and negative_mark)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quizzes (
        id TEXT PRIMARY KEY,
        title TEXT,
        subject TEXT,
        section TEXT,
        creator_id INTEGER,
        total_time_min INTEGER,
        time_per_question_sec INTEGER,
        negative_mark REAL DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(creator_id) REFERENCES creators(id)
    )""")
    # questions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id TEXT,
        idx INTEGER,
        q_json TEXT,
        FOREIGN KEY(quiz_id) REFERENCES quizzes(id)
    )""")
    # attempts (per-user attempts)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id TEXT,
        user_id INTEGER,
        username TEXT,
        started_at TEXT,
        finished_at TEXT,
        answers_json TEXT,
        score REAL,
        max_score REAL,
        FOREIGN KEY(quiz_id) REFERENCES quizzes(id)
    )""")
    con.commit()
    # attempt to add time_per_question_sec if missing (safe)
    try:
        cur.execute("PRAGMA table_info(quizzes)")
        cols = [r[1] for r in cur.fetchall()]
        if "time_per_question_sec" not in cols:
            cur.execute("ALTER TABLE quizzes ADD COLUMN time_per_question_sec INTEGER")
            con.commit()
    except Exception:
        pass
    return con

db = init_db()
db.row_factory = sqlite3.Row

def db_execute(query, params=(), commit=True):
    cur = db.cursor()
    cur.execute(query, params)
    if commit:
        db.commit()
    return cur

def get_creator_by_tg(tg_user_id):
    cur = db_execute("SELECT * FROM creators WHERE tg_user_id = ?", (tg_user_id,), commit=False)
    return cur.fetchone()

def get_or_create_creator_by_tg(user: User):
    """Checks for a creator by TG ID. If not found, creates one and returns it."""
    c = db_execute("SELECT * FROM creators WHERE tg_user_id = ?", (user.id,), commit=False).fetchone()
    if c:
        return c
    # Not found, create one
    username = user.username or ""
    # FIX: Construct full name from first_name and last_name
    display_name = ((user.first_name or "") + " " + (user.last_name or "")).strip()
    cur = db_execute("INSERT INTO creators (tg_user_id, username, display_name, is_admin) VALUES (?, ?, ?, 0)",
                     (user.id, username, display_name), commit=True)
    # Fetch and return the newly created row
    return db_execute("SELECT * FROM creators WHERE id = ?", (cur.lastrowid,), commit=False).fetchone()


def ensure_owner_exists(tg_user_id, username=None, display_name=None):
    global OWNER_ID
    if OWNER_ID == 0:
        OWNER_ID = tg_user_id
    c = get_creator_by_tg(OWNER_ID)
    if not c:
        db_execute("INSERT INTO creators (tg_user_id, username, display_name, is_admin) VALUES (?, ?, ?, 1)",
                   (OWNER_ID, username or "", display_name or ""), True)

def generate_quiz_id(length=8):
    chars = string.ascii_letters + string.digits
    while True:
        quiz_id = ''.join(random.choices(chars, k=length))
        if not db_execute("SELECT 1 FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone():
            return quiz_id

# --- Parsing (Start) ---

# --- MODIFICATION 1 (Renamed to 'parse_format2_enhanced'): Updated parser to support multi-line Qs, Options, and Explanations ---
def parse_format2_enhanced(txt: str):
    """
    Enhanced format parser (Original MOD 1): Handles numbered blocks where each block can have:
    1. [..] Question text (can span multiple lines)
    (a) option1 (can span multiple lines)
    (b) option2 ✅
    ...
    Ex: explanation (can span multiple lines until next block)

    Returns list of question dicts OR [] if any block invalid (strict).
    """
    questions = []
    # normalize newlines, then split into blocks by double newline
    blocks = re.split(r'\n\s*\n+', txt.strip())

    # Regex for options and explanation (compiled once)
    option_regex = re.compile(r'^\s*\([a-zA-Z]\)\s*')
    ex_regex = re.compile(r'(?i)^ex:\s*')

    for block in blocks:
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue  # Skip empty blocks

        # Check if block starts with a number (like "1." or "1. [..]")
        if not re.match(r'^\s*(\d+)\.\s*(.*)', lines[0]):
             # This block doesn't start with a question number. Strict failure.
             return []

        # Find where options/explanation start
        first_opt_ex_index = -1
        for i, line in enumerate(lines):
            if option_regex.match(line) or ex_regex.match(line):
                first_opt_ex_index = i
                break

        if first_opt_ex_index == -1:
            # Block has a question number but no options or 'Ex:'. Invalid.
            return []  # Strict failure

        # Question is everything BEFORE that index
        q_lines = lines[:first_opt_ex_index]
        opt_ex_lines = lines[first_opt_ex_index:] # These are the option and explanation lines

        if not q_lines:
            return []  # Strict failure

        # Re-join multi-line question text, strip the "1. " from the FIRST line only
        q_text_first_line = re.sub(r'^\s*\d+\.\s*', '', q_lines[0]).strip()
        q_text_other_lines = [l.strip() for l in q_lines[1:]]
        all_q_text_parts = [q_text_first_line] + q_text_other_lines
        qtext = "\n".join(all_q_text_parts).strip()

        # --- NEW PARSING LOGIC: Handles multi-line options AND multi-line explanation ---
        opts = []
        correct = -1
        explanation_buffer = []
        parsing_explanation = False # Flag to switch modes

        for l in opt_ex_lines:
            l_stripped = l.strip()

            if parsing_explanation:
                # We are already in explanation mode, just append the line
                explanation_buffer.append(l_stripped)
                continue

            if ex_regex.match(l_stripped):
                # We hit the explanation. Start buffering.
                parsing_explanation = True
                first_ex_line = ex_regex.sub('', l_stripped).strip()
                if first_ex_line: # Only add if it's not just "Ex:"
                    explanation_buffer.append(first_ex_line)

            elif option_regex.match(l_stripped):
                # We are parsing a NEW option
                opt_text = option_regex.sub('', l_stripped).strip()
                if "✅" in opt_text or "✅️" in opt_text: # Handle both emoji variants
                    opt_text = opt_text.replace("✅", "").replace("✅️", "").strip()
                    opts.append(opt_text)
                    correct = len(opts) - 1
                else:
                    opts.append(opt_text)

            elif l_stripped and opts:
                # This is NOT an explanation, NOT a new option, IS text, and we HAVE a previous option.
                # Therefore, it must be a continuation of the previous option.
                opts[-1] = opts[-1] + "\n" + l_stripped

            # Any other lines (blank lines before any options, etc) are ignored.

        # After the loop, join the explanation buffer
        explanation = "\n".join(explanation_buffer).strip()
        # --- END NEW PARSING LOGIC ---

        if not opts or len(opts) < 2 or correct == -1:
            # Block is invalid (no options, or no correct answer marked)
            return []  # strict enforcement

        questions.append({
            "text": qtext,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })

    return questions
# --- END MODIFICATION 1 (Renamed) ---


# --- NEW PARSERS (Added as requested) ---

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
        
        if not opts or correct == -1:
            continue # Skip invalid blocks in this format

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
        # Use re.S (DOTALL) to ensure matches across newlines
        for match in re.finditer(r'\(([a-zA-Z])\)\s*(.*?)(?=(\([a-zA-Z]\)|Ex:|$))', chunk, flags=re.IGNORECASE | re.DOTALL):
            raw = match.group(2).strip()
            has_tick = '✅' in raw
            raw = raw.replace('✅','').strip()
            opts.append(raw)
            if has_tick:
                correct = len(opts)-1
        m_ex = re.search(r'Ex\s*:\s*[“"]?(.*?)[”"]?\s*$', chunk, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
        explanation = m_ex.group(1).strip() if m_ex else ""
        
        if not opts or correct == -1:
            continue # Skip invalid

        questions.append({
            "text": definition,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })
    return questions

def parse_format2_simple(txt: str):
    """Numbered + a) b) style (Simple version provided by user)"""
    questions = []
    blocks = re.split(r'(?m)^\d+\.\s*', txt)
    for block in blocks:
        if not block.strip(): continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines: continue
        qtext = lines[0]
        opts = []; correct = -1
        explanation = ""
        parsing_explanation = False
        
        for i, l in enumerate(lines[1:]):
            if l.lower().startswith("ex:"):
                parsing_explanation = True
                explanation = re.sub(r'(?i)^ex:\s*', '', l).strip()
                continue
            
            if parsing_explanation:
                explanation += "\n" + l
                continue

            has_tick = '✅' in l
            l = l.replace('✅','').strip()
            if re.match(r'^[a-zA-Z]\)\s*', l.lower()):
                l = re.sub(r'^[a-zA-Z]\)\s*', '', l).strip()
            elif re.match(r'^\([a-zA-Z]\)\s*', l.lower()):
                 l = re.sub(r'^\([a-zA-Z]\)\s*', '', l).strip()

            opts.append(l)
            if has_tick: 
                correct = len(opts)-1

        if not opts or correct == -1:
            continue # Skip invalid
            
        questions.append({"text":qtext,"options":opts,"correctIndex":correct,"explanation":explanation.strip(),"reference":""})
    return questions


def parse_format3(txt: str):
    """Direct JSON quizData"""
    try:
        m = re.search(r'const\s+quizData\s*=\s*(\[.*\]);', txt, flags=re.S)
        if not m:
             m = re.search(r'const\s+quizData\s*=\s*({.*});', txt, flags=re.S)
             if not m:
                 return []
             # This is object format { questions: [...] }
             obj = json.loads(m.group(1))
             return obj.get("questions",[])
        
        # This is direct array format [...]
        return json.loads(m.group(1))
    except Exception:
        return []

def parse_format4(txt: str):
    """Q + options line by line, blank line separates questions"""
    questions=[]
    blocks = re.split(r'\n\s*\n', txt.strip()) # Split on blank lines
    for block in blocks:
        lines=[l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 3: continue # Must have Q + at least 2 opts
        qtext=lines[0]
        opts=[];correct=-1
        explanation = ""
        
        opt_lines = lines[1:]
        ex_line_index = -1
        
        # Find explanation
        for i, l in enumerate(opt_lines):
             if l.lower().startswith("ex:"):
                 explanation = re.sub(r'(?i)^ex:\s*', '', l).strip()
                 ex_line_index = i
                 # Check for multi-line explanation
                 if i + 1 < len(opt_lines):
                     explanation += "\n" + "\n".join(opt_lines[i+1:])
                 break # Found explanation, stop parsing options

        if ex_line_index != -1:
            opt_lines = opt_lines[:ex_line_index] # Only lines before Ex: are options

        for i,l in enumerate(opt_lines):
            has_tick='✅' in l
            l=l.replace('✅','').strip()
            opts.append(l)
            if has_tick: correct=i
            
        if not opts or correct == -1:
            continue # Skip invalid

        questions.append({"text":qtext,"options":opts,"correctIndex":correct,"explanation":explanation,"reference":""})
    return questions

def parse_csv(path: str):
    """CSV format parser (Requires a file path)"""
    questions = []
    try:
        # Use utf-8-sig to handle potential BOM (Byte Order Mark)
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
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
                
                q_text = row.get("Question (Exam Info)", "") or row.get("Question", "")
                if not q_text.strip() or not opts:
                    continue # Skip empty rows

                questions.append({
                    "text": q_text.strip(),
                    "options": opts,
                    "correctIndex": correct_idx,
                    "explanation": row.get("Explanation", "").strip(),
                    "reference": ""
                })
    except Exception as e:
        print(f"Failed to parse CSV: {e}")
        return [] # Return empty on failure
    return questions

# --- END NEW PARSERS ---

# --- UPDATED: Universal Parser Detection ---
def detect_and_parse_strict(txt: str):
    """
    Tries all available text-based parsers and returns the first valid result.
    The enhanced multi-line parser (f2_enhanced) is prioritized as it's the strictest.
    """
    
    # 1. Try enhanced format 2 (multi-line, strict numbered (a), supports multi-line everything)
    # This is the format used by /create, so it should be checked first.
    res_f2_enhanced = parse_format2_enhanced(txt)
    if res_f2_enhanced:
        # print("Detected format: f2_enhanced")
        return res_f2_enhanced

    # 2. Try format 4 (blank line separated)
    res_f4 = parse_format4(txt)
    if res_f4:
        # print("Detected format: f4")
        return res_f4

    # 3. Try format dash (Q#: ... - opt1 ... - opt2 ✅)
    res_f_dash = parse_format_dash(txt)
    if res_f_dash:
        # print("Detected format: dash")
        return res_f_dash

    # 4. Try format 1 (definition style 1. ... (a)... (b)... Ex:)
    res_f1 = parse_format1(txt)
    if res_f1:
        # print("Detected format: f1")
        return res_f1

    # 5. Try format 2 simple (user provided 1. ... a) ... b) ...)
    res_f2_simple = parse_format2_simple(txt)
    if res_f2_simple:
        # print("Detected format: f2_simple")
        return res_f2_simple

    # 6. Try format 3 (JSON const quizData)
    res_f3 = parse_format3(txt)
    if res_f3:
        # print("Detected format: f3_json")
        return res_f3

    # If none matched
    return []
# --- END Universal Parser Detection ---


# --- JSON helpers ---
def questions_to_json(qs):
    return json.dumps(qs, ensure_ascii=False)

def questions_from_json(s):
    return json.loads(s)


# --- Session Management (File-based) ---

# In-memory stores for running tasks and file locks, NOT for session data.
running_private_tasks = {}  # (user_id, attempt_id) -> asyncio.Task
running_group_tasks = {}    # (chat_id, quiz_id) -> asyncio.Task

private_session_locks = {}  # (user_id, attempt_id) -> asyncio.Lock
group_session_locks = {}    # (chat_id, quiz_id) -> asyncio.Lock

# ongoing_sessions is *only* for the /create flow state
ongoing_sessions = {}  # (user_id, "create") => state


def get_private_lock(key):
    if key not in private_session_locks:
        private_session_locks[key] = asyncio.Lock()
    return private_session_locks[key]

def get_group_lock(key):
    if key not in group_session_locks:
        group_session_locks[key] = asyncio.Lock()
    return group_session_locks[key]

# --- Session File Helpers ---

def get_private_session_path(user_id, attempt_id):
    return os.path.join(SESSION_DIR, f"private_{user_id}_{attempt_id}.json")

def get_group_session_path(chat_id, quiz_id):
    safe_quiz_id = re.sub(r'[^a-zA-Z0-9_]', '', str(quiz_id))
    return os.path.join(SESSION_DIR, f"group_{chat_id}_{safe_quiz_id}.json")

async def read_session_file(path, lock):
    async with lock:
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert ISO string back to datetime object
                if 'started_at' in data and isinstance(data['started_at'], str):
                    try:
                        data['started_at'] = datetime.fromisoformat(data['started_at'])
                    except ValueError:
                        data['started_at'] = datetime.utcnow() # Fallback
                return data
        except Exception:
            traceback.print_exc()
            return None

async def write_session_file(path, session_data, lock):
    async with lock:
        # Prep data for JSON (convert datetime to string)
        data_to_write = session_data.copy()
        if 'started_at' in data_to_write and isinstance(data_to_write['started_at'], datetime):
            data_to_write['started_at'] = data_to_write['started_at'].isoformat()

        # We absolutely cannot save the asyncio.Task
        data_to_write.pop('auto_task', None)

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data_to_write, f, ensure_ascii=False, indent=2)
        except Exception:
            traceback.print_exc()


async def delete_session_file(path, key, lock_dict, task_dict):
    lock = lock_dict.get(key)
    if lock:
        async with lock:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Error removing session file {path}: {e}")
    elif os.path.exists(path):
        try:
            os.remove(path) # remove orphaned file
        except Exception as e:
            print(f"Error removing orphaned session file {path}: {e}")

    # Clean up task and lock from memory
    task = task_dict.pop(key, None)
    if task:
        try:
            task.cancel()
        except Exception:
            pass

    lock_dict.pop(key, None)


# --- /start handler ---
@app.on_message(filters.command(["start", "help"]))
async def start_handler(_, message: Message):
    uid = message.from_user.id
    uname = message.from_user.username or ""
    # FIX: Construct full name from first_name and last_name
    fullname = ((message.from_user.first_name or "") + " " + (message.from_user.last_name or "")).strip()
    if OWNER_ID == 0:
        ensure_owner_exists(uid, uname, fullname)
    text = (
        "👋 **Welcome to QuizMaster Bot!**\n\n"
        "Available commands:\n"
        "• /create - Create a quiz interactively\n"
        "• /bulkupload - Upload a .zip of .txt quizzes\n"
        "• /myquizzes - List quizzes you created\n"
        "• /take <quiz_id> - Start a timed quiz (private)\n"
        "• /post <quiz_id> - Post/share a quiz card into the chat (start in group or private)\n"
        "• /finish - Finish your active private quiz early\n\n"
        "Web panel available at / (runs on the server)."
    )
    await message.reply_text(text)

# --- /create interactive with negative marking step ---
@app.on_message(filters.command("create") & filters.private)
async def create_command(client, message: Message):
    uid = message.from_user.id
    # Anyone can create a quiz
    state = {"flow": "create_quiz", "step": "title"}
    ongoing_sessions[(uid, "create")] = state # This is for the *creator* flow, not a quiz session
    await message.reply_text("✍️ Creating a new quiz. Send the *Quiz Title*:")

# create flow handler (includes accepting .txt during questions)
@app.on_message(filters.private & ~filters.command(["start", "help", "create", "bulkupload", "myquizzes", "take", "make_creator", "post", "htmk", "finish"]))
async def create_flow_handler(client, message: Message):
    uid = message.from_user.id
    key = (uid, "create")
    if key not in ongoing_sessions:
        return # Not in create flow
    state = ongoing_sessions[key]

    # If .txt document is uploaded during questions step -> import strictly
    if message.document and state.get("step") == "questions":
        fname = (message.document.file_name or "").lower()
        if not fname.endswith(".txt"):
            await message.reply_text("❌ Only `.txt` files are accepted here (must be in one of the supported formats).")
            return
        path = await message.download()
        try:
            # --- FIX: Changed encoding to "utf-8-sig" to handle BOM ---
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                data = f.read()
            # Use the new universal detector
            parsed = detect_and_parse_strict(data) 
            if not parsed:
                await message.reply_text("❌ The .txt file did not match any of the required formats or was invalid. Please fix and resend.")
                return
            state.setdefault("questions", []).extend(parsed)
            await message.reply_text(f"✅ Imported {len(parsed)} questions from the file. Total so far: {len(state['questions'])}. Send more or /done.")
        except Exception as e:
            await message.reply_text(f"❌ Error reading file: {e}")
        finally:
            try:
                os.remove(path)
            except:
                pass
        return

    text = (message.text or "").strip()
    if not text:
        return

    # Steps flow (title -> subject -> section -> time_per_q -> negative -> questions)
    if state["step"] == "title":
        state["title"] = text
        state["step"] = "subject"
        await message.reply_text("Saved title. Now send the *subject* (e.g., Math, Physics):")
        return

    if state["step"] == "subject":
        state["subject"] = text
        state["step"] = "section"
        await message.reply_text("Saved subject. Now send the *section* or category (optional; send '-' for none):")
        return

    if state["step"] == "section":
        state["section"] = "" if text == "-" else text
        state["step"] = "time_per_q"
        await message.reply_text("Saved section. Now send **time per question in seconds** (integer):")
        return

    if state["step"] == "time_per_q":
        try:
            secs = int(text)
            if secs <= 0:
                raise ValueError
            state["time_per_question_sec"] = secs
        except:
            await message.reply_text("❌ Please send a valid positive integer for seconds.")
            return
        state["step"] = "negative"
        await message.reply_text("Saved time. Now send **negative marks per wrong answer** (e.g., `0.25` or `0` for none):")
        return

    if state["step"] == "negative":
        try:
            neg = float(text)
            if neg < 0:
                raise ValueError
            state["negative"] = neg
        except:
            await message.reply_text("❌ Please send a valid non-negative number for negative marks (e.g., 0.25).")
            return
        state["step"] = "questions"
        state["questions"] = []
        await message.reply_text(
            "Now send questions one by one in this exact format OR upload a `.txt` file with many questions in the same format:\n\n"
            "1. [4/50] Question text (can be multiple lines)\n"
            "Optional second line of question\n"
            "(a) option1 (can be multiple lines)\n"
            "(b) option2 ✅\n"
            "(c) option3\n"
            "Ex: Optional explanation text (can be multiple lines)\n\n"
            "Send /done when finished."
        )
        return

    if state["step"] == "questions":
        if text == "/done":
            if not state.get("questions"):
                await message.reply_text("❌ No questions found. Send at least one question in the required format or upload a .txt file.")
                return
            creator = get_or_create_creator_by_tg(message.from_user)
            quiz_id = generate_quiz_id()
            db_execute("INSERT INTO quizzes (id, title, subject, section, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (quiz_id, state["title"], state["subject"], state["section"], creator["id"], 0, state.get("time_per_question_sec", 30), state.get("negative", 0.0), datetime.utcnow().isoformat()))
            for idx, q in enumerate(state["questions"]):
                db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
            del ongoing_sessions[key] # Remove creator flow state
            await message.reply_text(f"✅ Quiz created with id `{quiz_id}` (time per question: {state.get('time_per_question_sec')}s, negative: {state.get('negative')})!")
            return

        # try parse single or multi-blocks from message text using the strict multi-line parser
        # (This must use the enhanced parser, as it's the required format for /create)
        parsed = parse_format2_enhanced(text) 
        if not parsed:
            await message.reply_text("❌ Could not parse the question. Make sure it exactly matches the required format (numbered, (a) options, and one ✅).")
            return
        state["questions"].extend(parsed)
        await message.reply_text(f"✅ Saved {len(parsed)} question(s). Total so far: {len(state['questions'])}. Send next or /done.")
        return

# --- /bulkupload .zip of .txt (creators only) ---
@app.on_message(filters.command("bulkupload") & filters.private)
async def bulkupload_handler(client, message: Message):
    await message.reply_text("✅ Send a `.zip` file containing `.txt` or `.csv` files (each file must be in one of the supported formats).")

@app.on_message(filters.document & filters.private)
async def doc_handler_private(client, message: Message):
    uid = message.from_user.id
    # Check if this doc is for a create flow
    create_key = (uid, "create")
    if create_key in ongoing_sessions and ongoing_sessions[create_key].get("step") == "questions":
        # This is handled by create_flow_handler, don't process as zip or csv
        return

    fname = (message.document.file_name or "").lower()
    creator = get_or_create_creator_by_tg(message.from_user)
    path = await message.download()

    # Handle single CSV upload (if not zip)
    if fname.endswith(".csv"):
        try:
            parsed = parse_csv(path) # Use the CSV path parser
            if not parsed:
                 await message.reply_text(f"❌ Failed to parse {fname}: CSV format error or empty.")
                 return
            
            title = os.path.splitext(os.path.basename(fname))[0]
            quiz_id = generate_quiz_id()
            db_execute("INSERT INTO quizzes (id, title, subject, section, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                (quiz_id, title, "", "", creator["id"], 0, 30, 0.0, datetime.utcnow().isoformat()))
            for idx, q in enumerate(parsed):
                db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
            await message.reply_text(f"✅ CSV Upload: Created 1 quiz ({title}) with {len(parsed)} questions. ID: `{quiz_id}`")
        except Exception as e:
             await message.reply_text(f"❌ Error processing CSV: {e}")
        finally:
            try:
                os.remove(path)
            except:
                pass
        return

    # Handle Zip upload
    if fname.endswith(".zip"):
        try:
            created = 0
            errors = []
            with zipfile.ZipFile(path, "r") as z:
                # Need a temporary dir for CSVs
                temp_zip_dir = f"temp_zip_{uid}"
                os.makedirs(temp_zip_dir, exist_ok=True)
                
                for fname_in_zip in z.namelist():
                    if fname_in_zip.startswith("__MACOSX"):
                        continue
                        
                    fname_lower = fname_in_zip.lower()
                    parsed = []
                    title = os.path.splitext(os.path.basename(fname_in_zip))[0]
                    
                    try:
                        if fname_lower.endswith(".txt"):
                            # --- FIX: Changed encoding to "utf-8-sig" to handle BOM ---
                            data = z.read(fname_in_zip).decode("utf-8-sig", errors="ignore")
                            # Use the universal detector
                            parsed = detect_and_parse_strict(data) 
                        
                        elif fname_lower.endswith(".csv"):
                            # Extract CSV to temp path to use parse_csv
                            csv_temp_path = z.extract(fname_in_zip, path=temp_zip_dir)
                            parsed = parse_csv(csv_temp_path)

                        else:
                            errors.append(f"{fname_in_zip}: not a .txt or .csv file, skipped")
                            continue

                        if not parsed:
                            errors.append(f"{fname_in_zip}: format mismatch or parsing failed")
                            continue
                        
                        quiz_id = generate_quiz_id()
                        db_execute("INSERT INTO quizzes (id, title, subject, section, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                         (quiz_id, title, "", "", creator["id"], 0, 30, 0.0, datetime.utcnow().isoformat()))
                        for idx, q in enumerate(parsed):
                            db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
                        created += 1
                    except Exception as e:
                        errors.append(f"{fname_in_zip}: {e}")
                
                # Clean up temp zip dir
                try:
                    import shutil
                    shutil.rmtree(temp_zip_dir)
                except:
                    pass

            await message.reply_text(f"✅ Bulk upload finished. Created {created} quizzes.\nErrors: {errors[:10]}")
        except Exception as e:
            await message.reply_text(f"❌ Error processing zip: {e}")
        finally:
            try:
                os.remove(path)
            except:
                pass
    else:
        # txt handling for create flow is already covered by create_flow_handler
        pass

# --- myquizzes (creators) ---
@app.on_message(filters.command("myquizzes") & filters.private)
async def myquizzes_handler(client, message: Message):
    uid = message.from_user.id
    c = get_creator_by_tg(uid)
    if not c:
        await message.reply_text("You haven't created any quizzes yet. Use /create to start.")
        return
    cur = db_execute("SELECT * FROM quizzes WHERE creator_id = ? ORDER BY created_at DESC", (c["id"],), commit=False)
    rows = cur.fetchall()
    if not rows:
        await message.reply_text("You have no quizzes yet.")
        return
    text_lines = []
    kb = []
    for r in rows:
        p = r['subject'] or '-'
        tp = r['time_per_question_sec'] or '-'
        text_lines.append(f"ID: {r['id']} | {r['title']} | Subject: {p} | Time/q: {tp}s | Neg: {r['negative_mark']}")
        kb.append([InlineKeyboardButton(f"{r['id']}: {r['title']}", callback_data=f"viewquiz:{r['id']}")])
    await message.reply_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(kb))

# --- view/export/delete/share quiz via callbacks (unchanged) ---
@app.on_callback_query(filters.regex(r"^viewquiz:"))
async def view_quiz_cb(c: Client, query: CallbackQuery):
    quiz_id = query.data.split(":")[1]
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        await query.answer("Quiz not found", show_alert=True); return
    creator = db_execute("SELECT * FROM creators WHERE id = ?", (qrow["creator_id"],), commit=False).fetchone()
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    preview = []
    for i, qr in enumerate(qrows[:10], start=1):
        qobj = questions_from_json(qr["q_json"])
        preview.append(f"{i}. {qobj.get('text','')}\n  a) {qobj.get('options',[None])[0] if qobj.get('options') else ''}")
    txt = (f"Quiz ID: {quiz_id}\nTitle: {qrow['title']}\nSubject: {qrow['subject']}\nSection: {qrow['section']}\n"
           f"Creator: {creator['username'] or creator['display_name']}\nQuestions: {len(qrows)}\n\nPreview:\n" + "\n".join(preview))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Delete", callback_data=f"deletequiz:{quiz_id}"), InlineKeyboardButton("Export", callback_data=f"exportquiz:{quiz_id}")],
        [InlineKeyboardButton("Share (post card)", callback_data=f"postcard:{quiz_id}")]
    ])
    await query.message.reply_text(txt, reply_markup=kb)
    await query.answer()

@app.on_callback_query(filters.regex(r"^deletequiz:"))
async def delete_quiz_cb(c: Client, query: CallbackQuery):
    uid = query.from_user.id
    quiz_id = query.data.split(":")[1]
    q = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not q:
        await query.answer("Not found", show_alert=True); return
    creator = get_creator_by_tg(uid)
    if not creator or (creator["is_admin"] != 1 and creator["id"] != q["creator_id"]):
        await query.answer("No permission", show_alert=True); return
    db_execute("DELETE FROM questions WHERE quiz_id = ?", (quiz_id,))
    db_execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
    await query.answer("Deleted", show_alert=True)
    await query.message.reply_text(f"✅ Quiz {quiz_id} deleted.")

@app.on_callback_query(filters.regex(r"^exportquiz:"))
async def export_quiz_cb(c: Client, query: CallbackQuery):
    quiz_id = query.data.split(":")[1]
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        await query.answer("No questions", show_alert=True); return
    lines = []
    for i, qr in enumerate(qrows, start=1):
        qobj = questions_from_json(qr["q_json"])
        lines.append(f"{i}. {qobj.get('text','')}")
        for opt_idx, opt in enumerate(qobj.get("options", [])):
            mark = " ✅" if opt_idx == qobj.get("correctIndex", -1) else ""
            lines.append(f"({chr(97+opt_idx)}) {opt}{mark}")
        if qobj.get("explanation"):
            lines.append(f"Ex: {qobj.get('explanation')}")
        lines.append("")
    content = "\n".join(lines)
    bio = io.BytesIO(content.encode("utf-8"))
    bio.name = f"quiz_{quiz_id}.txt"
    await query.message.reply_document(bio, caption=f"Exported quiz {quiz_id}")
    await query.answer()

@app.on_callback_query(filters.regex(r"^postcard:"))
async def postcard_cb(c: Client, query: CallbackQuery):
    # Post the quiz card into the same chat where callback occurred
    quiz_id = query.data.split(":")[1]
    await query.answer()
    await post_quiz_card(c, query.message.chat.id, quiz_id)

# --- /post <quiz_id> - send a "card" message with Start buttons ---
@app.on_message(filters.command("post") & (filters.private | filters.group))
async def post_command(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /post <quiz_id>")
        return
    quiz_id = args[1]
    await post_quiz_card(client, message.chat.id, quiz_id)


# --- MODIFICATION 3: Updated post_quiz_card to include creator mention ---
async def post_quiz_card(client, chat_id, quiz_id):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await client.send_message(chat_id, "Quiz not found.")
        except:
            pass
        return
    qs_cur = db_execute("SELECT COUNT(*) as cnt FROM questions WHERE quiz_id = ?", (quiz_id,), commit=False)
    total_q = qs_cur.fetchone()["cnt"]
    title = qrow["title"] or f"Quiz {quiz_id}"

    # --- Build text with creator mention ---
    base_lines = [
        f"🎯 *{title}*",
        f"Subject: {qrow['subject'] or '-'} | Qs: {total_q} | Time/q: {qrow['time_per_question_sec'] or 30}s",
        f"Negative: {qrow['negative_mark']}"
    ]

    # Fetch creator details
    creator_mention_line = ""
    if qrow['creator_id']:
        creator_row = db_execute("SELECT * FROM creators WHERE id = ?", (qrow['creator_id'],), commit=False).fetchone()
        if creator_row:
            if creator_row['username']:
                creator_mention_line = f"Created by: @{creator_row['username']}"
            elif creator_row['display_name']:
                 creator_mention_line = f"Created by: {creator_row['display_name']}" # Plain text fallback

    if creator_mention_line:
        base_lines.append(creator_mention_line)

    base_lines.append("\nTap start to play!")
    text = "\n".join(base_lines)
    # --- End of text building ---

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Start this quiz (in this chat)", callback_data=f"startgroup:{quiz_id}")],
        [InlineKeyboardButton("Start in private", callback_data=f"startprivate:{quiz_id}")]
    ])
    await client.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
# --- END MODIFICATION 3 ---


# --- Start in private (DM) via postcard/button ---
@app.on_callback_query(filters.regex(r"^startprivate:"))
async def start_private_cb(c: Client, query: CallbackQuery):
    quiz_id = query.data.split(":")[1]
    uid = query.from_user.id
    await query.answer("Starting quiz in private...")
    # send DM start prompt and then call /take-like behavior
    try:
        await c.send_message(uid, "Starting quiz in private for you...")
        # emulate /take in private
        await take_quiz_private(c, uid, quiz_id)
    except Exception as e:
        await query.message.reply_text(f"❌ Failed to start in private: {e}")

# --- Start in group via postcard/button ---
@app.on_callback_query(filters.regex(r"^startgroup:"))
async def start_group_cb(c: Client, query: CallbackQuery):
    quiz_id = query.data.split(":")[1]
    chat_id = query.message.chat.id
    # only allow starting in groups or channels or supergroups
    await query.answer("Starting quiz in this chat...")
    await start_quiz_in_group(c, chat_id, quiz_id, starter_id=query.from_user.id)

# --- Private quiz routine (reused by /take and startprivate) ---
@app.on_message(filters.command("take") & filters.private)
async def take_handler(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /take <quiz_id>"); return
    quiz_id = args[1]
    await take_quiz_private(client, message.from_user.id, quiz_id)

async def take_quiz_private(client, user_id, quiz_id):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await client.send_message(user_id, "Quiz not found.")
        except:
            pass
        return
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        try:
            await client.send_message(user_id, "No questions in quiz.")
        except:
            pass
        return
    questions = [questions_from_json(qr["q_json"]) for qr in qrows]
    username = ""  # in private path we will fetch username when saving attempt
    started_at = datetime.utcnow().isoformat()
    cur = db_execute("INSERT INTO attempts (quiz_id, user_id, username, started_at) VALUES (?,?,?,?)",
                    (quiz_id, user_id, username, started_at))
    attempt_id = cur.lastrowid

    session = {
        "quiz_id": quiz_id,
        "user_id": user_id,
        "attempt_id": attempt_id,
        "questions": questions,
        "answers": [-1]*len(questions),
        "current_q": 0,
        "started_at": datetime.utcnow(), # This is a datetime object
        "time_per_question_sec": int(qrow["time_per_question_sec"] or 30),
        "message_id": None,
        "chat_id": user_id,
    }

    # Write session to file instead of in-memory dict
    session_key = (user_id, attempt_id)
    session_path = get_private_session_path(user_id, attempt_id)
    lock = get_private_lock(session_key)
    await write_session_file(session_path, session, lock)

    try:
        await client.send_message(user_id, f"✅ Quiz started: {qrow['title']}\nTime per question: {session['time_per_question_sec']} seconds.\nAnswer by tapping an option.")
    except:
        pass

    # Pass the key to the handler
    await send_question_for_session_private(client, session_key)

async def send_question_for_session_private(client: Client, session_key):
    # Read session from file
    path = get_private_session_path(*session_key)
    lock = get_private_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return # Session was likely finished and deleted

    qidx = session["current_q"]
    if qidx < 0 or qidx >= len(session["questions"]):
        await finalize_attempt(client, session_key, session)
        return

    q = session["questions"][qidx]
    buttons = []
    for i, opt in enumerate(q.get("options", [])):
        buttons.append([InlineKeyboardButton(f"{chr(97+i)}. {opt}", callback_data=f"panswer:{session['attempt_id']}:{qidx}:{i}")])
    kb = InlineKeyboardMarkup(buttons)
    text = f"Q{qidx+1}/{len(session['questions'])} — {q.get('text')}\n\nYou have {session['time_per_question_sec']} seconds to answer."

    try:
        sent = await client.send_message(session["chat_id"], text, reply_markup=kb)
        session["message_id"] = sent.id
        # Save message_id back to session file
        await write_session_file(path, session, lock)
    except Exception as e:
        print(f"Failed to send private question: {e}")
        # Could not send message, user likely blocked bot. End attempt.
        await finalize_attempt(client, session_key, session)
        return


    # Cancel previous task if any
    old_task = running_private_tasks.pop(session_key, None)
    if old_task:
        old_task.cancel()

    async def per_question_timeout():
        try:
            await asyncio.sleep(session["time_per_question_sec"])
            # Re-read session data to check state
            fresh_path = get_private_session_path(*session_key)
            fresh_lock = get_private_lock(session_key)
            fresh_session = await read_session_file(fresh_path, fresh_lock)

            if not fresh_session:
                return # Quiz was deleted/finished

            if fresh_session["current_q"] == qidx and fresh_session["answers"][qidx] == -1:
                # Question is still active and unanswered
                await reveal_correct_and_advance_private(client, session_key, qidx, timed_out=True)
        except asyncio.CancelledError:
            pass # Task was cancelled, which is normal

    running_private_tasks[session_key] = asyncio.create_task(per_question_timeout())

@app.on_callback_query(filters.regex(r"^panswer:"))
async def panswer_cb(client: Client, query: CallbackQuery):
    parts = query.data.split(":")
    attempt_id = int(parts[1]); qidx = int(parts[2]); opt_idx = int(parts[3])
    uid = query.from_user.id
    key = (uid, attempt_id)

    # Read session from file
    path = get_private_session_path(*key)
    lock = get_private_lock(key)
    session = await read_session_file(path, lock)

    if not session:
        await query.answer("Session not found or expired", show_alert=True); return
    if session["current_q"] != qidx:
        await query.answer("This question is no longer active.", show_alert=True); return
    if session["answers"][qidx] != -1:
        await query.answer("Answer already recorded.", show_alert=True); return

    session["answers"][qidx] = opt_idx
    # Write updated answers back to file
    await write_session_file(path, session, lock)

    # Cancel the timeout task
    task = running_private_tasks.pop(key, None)
    if task:
        task.cancel()

    # reveal feedback privately
    await reveal_correct_and_advance_private(client, key, qidx, chosen_idx=opt_idx)
    await query.answer()

async def reveal_correct_and_advance_private(client: Client, session_key, qidx, chosen_idx=None, timed_out=False):
    # Read session
    path = get_private_session_path(*session_key)
    lock = get_private_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        return # Session file gone

    q = session["questions"][qidx]
    correct = q.get("correctIndex", -1)
    new_buttons = []
    for i, opt in enumerate(q.get("options", [])):
        label = f"{chr(97+i)}. {opt}"
        if i == correct:
            label = label + " ✅"
        if chosen_idx is not None and i == chosen_idx and chosen_idx != correct:
            label = label + " ❌"
        new_buttons.append([InlineKeyboardButton(label, callback_data="noop")])
    try:
        await client.edit_message_reply_markup(session["chat_id"], session["message_id"], reply_markup=InlineKeyboardMarkup(new_buttons))
    except:
        pass
    await asyncio.sleep(3)
    try:
        await client.delete_messages(session["chat_id"], session["message_id"])
    except:
        pass

    session["current_q"] += 1
    # Save the advanced question index
    await write_session_file(path, session, lock)

    if session["current_q"] >= len(session["questions"]):
        await finalize_attempt(client, session_key, session)
        return

    await send_question_for_session_private(client, session_key)

# --- NEW: /finish command for private chats ---
@app.on_message(filters.command("finish") & filters.private)
async def finish_private_quiz(client, message: Message):
    user_id = message.from_user.id
    # Find this user's active session file
    active_sessions = glob.glob(os.path.join(SESSION_DIR, f"private_{user_id}_*.json"))

    if not active_sessions:
        await message.reply_text("You have no active quiz to finish.")
        return

    # Finish the first one found
    session_path = active_sessions[0]
    filename = os.path.basename(session_path)
    try:
        parts = filename.replace("private_", "").replace(".json", "").split("_")
        uid = int(parts[0])
        attempt_id = int(parts[1])
        session_key = (uid, attempt_id)
    except Exception:
        await message.reply_text("Error identifying your session file. Could not finish.")
        if os.path.exists(session_path): # cleanup orphaned file
            os.remove(session_path)
        return

    lock = get_private_lock(session_key)
    session_data = await read_session_file(session_path, lock)

    if not session_data:
        await message.reply_text("Could not read your session data. Cleaning up.")
        await delete_session_file(session_path, session_key, private_session_locks, running_private_tasks)
        return

    await message.reply_text("Finishing your quiz now and calculating results...")
    # finalize_attempt will send the final score, update DB, and delete the file/tasks/locks
    await finalize_attempt(client, session_key, session_data)


# --- Group quiz logic ---
async def start_quiz_in_group(client: Client, chat_id: int, quiz_id: str, starter_id: int = None):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await client.send_message(chat_id, "Quiz not found.")
        except:
            pass
        return
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        try:
            await client.send_message(chat_id, "No questions in quiz.")
        except:
            pass
        return
    questions = [questions_from_json(qr["q_json"]) for qr in qrows]

    session_key = (chat_id, quiz_id)
    session_path = get_group_session_path(*session_key)

    # Check if session FILE already exists
    if os.path.exists(session_path):
        await client.send_message(chat_id, "A quiz is already running in this chat for this quiz_id.")
        return

    session = {
        "quiz_id": quiz_id,
        "chat_id": chat_id,
        "questions": questions,
        "current_q": 0,
        "time_per_question_sec": int(qrow["time_per_question_sec"] or 30),
        "participants": {},  # user_id -> {answers, start_time, end_time, username}
        "message_id": None,
        "starter_id": starter_id,
        "negative": float(qrow["negative_mark"] or 0.0),
        "title": qrow["title"]
    }

    # Write new session file
    lock = get_group_lock(session_key)
    await write_session_file(session_path, session, lock)

    await client.send_message(chat_id, f"🎯 Quiz starting now: *{qrow['title']}*\nTime per question: {session['time_per_question_sec']}s\nEveryone can answer — answers are recorded privately. Results will be shown at the end.", parse_mode=ParseMode.MARKDOWN)
    await group_send_question(client, session_key)

async def group_send_question(client: Client, session_key):
    # Read session from file
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        return # Session ended

    qidx = session["current_q"]
    if qidx < 0 or qidx >= len(session["questions"]):
        await group_finalize_and_export(client, session_key)
        return

    q = session["questions"][qidx]
    buttons = []
    for i, opt in enumerate(q.get("options", [])):
        buttons.append([InlineKeyboardButton(f"{chr(97+i)}. {opt}", callback_data=f"ganswer:{session['quiz_id']}:{qidx}:{i}")])

    controls = [InlineKeyboardButton("Reveal (advance)", callback_data=f"greveal:{session['quiz_id']}:{qidx}"),
                InlineKeyboardButton("Finish quiz", callback_data=f"gfinish:{session['quiz_id']}")]
    kb = InlineKeyboardMarkup(buttons + [controls])
    text = f"Q{qidx+1}/{len(session['questions'])} — {q.get('text')}\n\nYou have {session['time_per_question_sec']} seconds to answer. Tap your choice (answers are recorded)."

    try:
        sent = await client.send_message(session["chat_id"], text, reply_markup=kb)
        session["message_id"] = sent.id
        # Save message_id back to file
        await write_session_file(path, session, lock)
    except Exception as e:
        print(f"Failed to send group question: {e}. Finalizing quiz.")
        await group_finalize_and_export(client, session_key)
        return

    # cancel existing auto_task
    old_task = running_group_tasks.pop(session_key, None)
    if old_task:
        old_task.cancel()

    async def per_question_timeout():
        try:
            await asyncio.sleep(session["time_per_question_sec"])
            # Re-read session data to check state
            fresh_path = get_group_session_path(*session_key)
            fresh_lock = get_group_lock(session_key)
            fresh_session = await read_session_file(fresh_path, fresh_lock)

            if fresh_session and fresh_session["current_q"] == qidx:
                await group_reveal_and_advance(client, session_key, qidx, timed_out=True)
        except asyncio.CancelledError:
            pass

    running_group_tasks[session_key] = asyncio.create_task(per_question_timeout())

@app.on_callback_query(filters.regex(r"^ganswer:"))
async def ganswer_cb(client: Client, query: CallbackQuery):
    # callback set: ganswer:<quiz_id>:<qidx>:<opt_idx>
    parts = query.data.split(":")
    quiz_id = parts[1]; qidx = int(parts[2]); opt_idx = int(parts[3])
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    session_key = (chat_id, quiz_id)

    # Read session from file (with lock, since many users can answer)
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        await query.answer("No active group quiz here.", show_alert=True); return

    if session["current_q"] != qidx:
        await query.answer("This question is no longer active.", show_alert=True); return

    # register user's answer privately
    p_data = session["participants"].get(str(user_id)) # JSON keys are strings
    if p_data is None:
        # FIX: Construct full name from first_name and last_name
        user_full_name = ((query.from_user.first_name or "") + " " + (query.from_user.last_name or "")).strip()
        p_data = {
            "answers": [-1] * len(session["questions"]),
            "start_time": time.time(),
            "username": user_full_name or str(user_id)
        }
        session["participants"][str(user_id)] = p_data

    if p_data["answers"][qidx] != -1:
        # already answered this question
        await query.answer("You already answered this question.", show_alert=True); return

    # Record answer and time
    p_data["answers"][qidx] = opt_idx
    p_data["end_time"] = time.time()

    # Write updated participant data back to file
    await write_session_file(path, session, lock)

    # give immediate private feedback via an alert
    correct = session["questions"][qidx].get("correctIndex", -1)
    if opt_idx == correct:
        await query.answer("✅ Correct — your answer recorded (will be included in result).", show_alert=True)
    else:
        await query.answer("❌ Wrong — your answer recorded (will be included in result).", show_alert=True)


@app.on_callback_query(filters.regex(r"^greveal:"))
async def greveal_cb(client: Client, query: CallbackQuery):
    # greveal:<quiz_id>:<qidx>
    parts = query.data.split(":")
    quiz_id = parts[1]; qidx = int(parts[2])
    chat_id = query.message.chat.id
    session_key = (chat_id, quiz_id)

    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        await query.answer("Session not found.", show_alert=True); return

    # Permission check: starter, creator, or chat admin
    starter_ok = (query.from_user.id == session.get("starter_id"))
    creator_row = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    creator_obj = db_execute("SELECT * FROM creators WHERE id = ?", (creator_row['creator_id'],), commit=False).fetchone() if creator_row else None
    creator_tg_id = creator_obj['tg_user_id'] if creator_obj else None

    is_admin = False
    try:
        member = await client.get_chat_member(chat_id, query.from_user.id)
        is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        pass # Not admin or failed to check

    if not (starter_ok or query.from_user.id == creator_tg_id or is_admin):
        await query.answer("Only the starter, creator, or a chat admin can reveal early.", show_alert=True)
        return

    await query.answer("Revealing and advancing...")

    # Cancel timeout task
    task = running_group_tasks.pop(session_key, None)
    if task:
        task.cancel()

    await group_reveal_and_advance(client, session_key, qidx, timed_out=False)


@app.on_callback_query(filters.regex(r"^gfinish:"))
async def gfinish_cb(client: Client, query: CallbackQuery):
    quiz_id = query.data.split(":")[1]
    chat_id = query.message.chat.id
    session_key = (chat_id, quiz_id)

    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        await query.answer("No active quiz.", show_alert=True); return

    # Permission check: starter, creator, or chat admin
    creator_row = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    creator_obj = db_execute("SELECT * FROM creators WHERE id = ?", (creator_row['creator_id'],), commit=False).fetchone() if creator_row else None
    creator_tg_id = creator_obj['tg_user_id'] if creator_obj else None

    is_admin = False
    try:
        member = await client.get_chat_member(chat_id, query.from_user.id)
        is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        pass # Not admin or failed to check

    if not (query.from_user.id == session.get("starter_id") or query.from_user.id == creator_tg_id or is_admin):
        await query.answer("Only the starter, creator, or a chat admin can finish the quiz.", show_alert=True)
        return

    await query.answer("Finishing quiz and exporting results...")

    # cancel auto task
    task = running_group_tasks.pop(session_key, None)
    if task:
        task.cancel()

    await group_finalize_and_export(client, session_key)


# --- MODIFICATION 2: Updated group_reveal_and_advance to show explanation ---
async def group_reveal_and_advance(client: Client, session_key, qidx, timed_out=False):
    """
    Reveal correct answer, stats, AND explanation in the group, wait 3s, delete, advance.
    """
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        return
    chat_id, quiz_id = session_key
    q = session["questions"][qidx]
    correct = q.get("correctIndex", -1)

    # Calculate vote counts
    num_options = len(q.get("options", []))
    counts = [0] * num_options
    for p_data in session.get('participants', {}).values():
        ans = p_data['answers'][qidx]
        if 0 <= ans < num_options:
            counts[ans] += 1

    # build labeled buttons marking correct option with stats
    new_buttons = []
    for i, opt in enumerate(q.get("options", [])):
        label_text = f"{chr(97+i)}. {opt}"
        count = counts[i]
        emoji = "✅️" if i == correct else "❌️"
        label = f"{label_text} {emoji}({count})"
        new_buttons.append([InlineKeyboardButton(label, callback_data="noop")])

    # --- Build NEW text content including the question and explanation ---
    q_text = q.get('text')  # This is the original question text
    q_index_text = f"Q{qidx+1}/{len(session['questions'])}"

    lines_for_edit = [
        f"{q_index_text} — {q_text}",  # Keep original question
        "\n--- ANSWER STATS ---"  # This will appear above the buttons
    ]

    explanation = q.get("explanation", "").strip()
    if explanation:
        # Strip surrounding quotes if present (often in exports from other systems)
        if explanation.startswith('"') and explanation.endswith('"'):
            explanation = explanation[1:-1].strip()

        # Avoid adding an empty "Ex:" if that's all it was
        if explanation:
            lines_for_edit.append(f"\n**Explanation:** {explanation}")

    new_text_content = "\n".join(lines_for_edit)

    # Edit message text AND markup in one call
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=session["message_id"],
            text=new_text_content,
            reply_markup=InlineKeyboardMarkup(new_buttons),
            parse_mode=ParseMode.MARKDOWN  # Enable Markdown for **Explanation:**
        )
    except Exception:
        # Fallback: maybe markdown failed or text was too long/same. Try just editing markup.
        try:
            await client.edit_message_reply_markup(chat_id, session["message_id"], reply_markup=InlineKeyboardMarkup(new_buttons))
        except Exception:
            pass  # Give up
    # --- END NEW TEXT LOGIC ---

    # wait 3s
    await asyncio.sleep(3)
    # delete message
    try:
        await client.delete_messages(chat_id, session["message_id"])
    except:
        pass

    # advance
    session["current_q"] += 1
    # Save advanced state back to file
    await write_session_file(path, session, lock)

    # if done -> finalize and export
    if session["current_q"] >= len(session["questions"]):
        await group_finalize_and_export(client, session_key)
        return
    # else send next question
    await group_send_question(client, session_key)
# --- END MODIFICATION 2 ---


async def group_finalize_and_export(client: Client, session_key):
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        return
    chat_id, quiz_id = session_key

    def format_duration(seconds):
        if seconds < 0: seconds = 0
        minutes, seconds_rem = divmod(int(seconds), 60)
        return f"{minutes} min {seconds_rem} sec"

    participants = session["participants"]
    results = []
    negative = float(session.get("negative", 0.0))
    total_questions = len(session['questions'])

    for user_id_str, p_data in participants.items():
        score = 0.0
        for idx, ans in enumerate(p_data["answers"]):
            if idx >= len(session["questions"]): continue
            correct = session["questions"][idx].get("correctIndex", -1)
            if correct == -1: continue
            if ans == correct:
                score += 1.0
            elif ans != -1: # Correct: Only apply negative if attempted (not -1)
                score -= negative
        if score < 0: score = 0.0

        duration = p_data.get("end_time", p_data.get("start_time", 0)) - p_data.get("start_time", 0)
        results.append({
            "name": p_data.get("username", str(user_id_str)),
            "score": score,
            "duration": duration
        })

    # Sort by score (desc) and then duration (asc)
    results.sort(key=lambda x: (x["score"], -x["duration"]), reverse=True)

    quiz_title = session.get("title", f"Quiz {quiz_id}")
    msg_lines = [
        f"🏁 The quiz '{quiz_title}' has finished!",
        f"\n{total_questions} questions answered\n"
    ]
    medals = ["🥇", "🥈", "🥉"]

    if not results:
        msg_lines.append("No one participated in the quiz.")
    else:
        for i, res in enumerate(results):
            prefix = medals[i] if i < len(medals) else f"{i + 1}."
            score = res['score']
            score_text = str(int(score)) if score == int(score) else f"{score:.2f}"
            line = f"{prefix} {res['name']} – {score_text} ({format_duration(res['duration'])})"
            msg_lines.append(line)
        msg_lines.append("\n🏆 Congratulations to the winners!")

    final_message = "\n".join(msg_lines)

    try:
        await client.send_message(chat_id, final_message)
    except Exception as e:
        print(f"Error sending final group results: {e}")
        try:
            await client.send_message(chat_id, "Quiz finished, but there was an error displaying the results.")
        except: pass

    # cleanup: delete session file, task, and lock
    await delete_session_file(path, session_key, group_session_locks, running_group_tasks)


# --- finalize attempt for private quiz: compute score and update DB ---
async def finalize_attempt(client: Client, session_key, session_data):
    total = 0.0
    maxscore = len(session_data["questions"])
    # get quiz negative if present
    quiz_row = db_execute("SELECT * FROM quizzes WHERE id = ?", (session_data["quiz_id"],), commit=False).fetchone()
    negative = quiz_row["negative_mark"] if quiz_row else 0.0

    for idx, q in enumerate(session_data["questions"]):
        correct = q.get("correctIndex", -1)
        ans = session_data["answers"][idx]
        if ans == correct and correct != -1:
            total += 1.0
        elif ans != -1 and correct != -1: # Correct: Only apply negative if attempted (not -1)
            total -= negative
    if total < 0: total = 0.0

    finished_at = datetime.utcnow().isoformat()
    db_execute("UPDATE attempts SET finished_at=?, answers_json=?, score=?, max_score=? WHERE id=?",
               (finished_at, json.dumps(session_data["answers"]), total, maxscore, session_data["attempt_id"]))

    # notify user (private)
    try:
        await client.send_message(session_data["user_id"], f" ✅ Quiz finished! Your score: {total}/{maxscore}")
    except:
        pass

    # cleanup: delete session file, task, and lock
    path = get_private_session_path(*session_key)
    await delete_session_file(path, session_key, private_session_locks, running_private_tasks)


# --- htmk stub ---
@app.on_message(filters.command("htmk") & filters.private)
async def htmk_command_handler(client, message: Message):
    # This remains a stub as the logic for converting to HTML (format2.html) wasn't fully implemented in the original script,
    # but the command is acknowledged as requested by the landing page HTML.
    await message.reply_text("✅ Send a .txt file (in required format) to convert to HTML (feature stub).")

# --- Flask Web Panel (MODIFIED as requested) ---
web = Flask("quiz_webpanel")

# Store the requested HTML landing page
FLASK_INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DIPESH CHOUDHARY Bot</title>
    <style>
        /* General Styling & Cool Background */
        :root {
            --primary-color: #0088cc;
            --secondary-color: #24292e;
            --background-color: #121212;
            --text-color: #e0e0e0;
            --card-bg: #1e1e1e;
            --glow-color: rgba(0, 136, 204, 0.8);
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: var(--background-color);
            color: var(--text-color);
            overflow-x: hidden;
            background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
        }

        /* Header Section */
        header {
            text-align: center;
            padding: 100px 20px 50px 20px;
            position: relative;
        }

        .header-content {
            position: relative;
            z-index: 2;
            animation: fadeInDown 1s ease-out;
        }

        .bot-name {
            font-size: 3.5rem;
            font-weight: 700;
            margin: 0;
            color: #fff;
            text-shadow: 0 0 10px var(--glow-color), 0 0 20px var(--glow-color);
        }

        .bot-tagline {
            font-size: 1.2rem;
            margin-top: 10px;
            color: var(--text-color);
            opacity: 0.8;
        }

        /* Buttons */
        .cta-button {
            display: inline-block;
            background-color: var(--primary-color);
            color: #fff;
            padding: 15px 30px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: bold;
            margin-top: 30px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            box-shadow: 0 0 20px var(--glow-color);
        }

        .cta-button:hover {
            transform: translateY(-5px) scale(1.05);
            box-shadow: 0 0 35px var(--glow-color);
        }

        /* Features Section */
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px 20px;
        }

        h2 {
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 50px;
            position: relative;
            color: #fff;
        }

        h2::after {
            content: '';
            display: block;
            width: 80px;
            height: 4px;
            background: var(--primary-color);
            margin: 10px auto 0;
            border-radius: 2px;
        }
        
        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 30px;
        }

        .feature-card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 15px;
            border: 1px solid #333;
            text-align: center;
            transition: transform 0.3s, box-shadow 0.3s;
            opacity: 0; /* Initially hidden for animation */
            transform: translateY(30px);
        }

        .feature-card.visible {
            opacity: 1;
            transform: translateY(0);
        }
        
        .feature-card:hover {
            transform: translateY(-10px);
            box-shadow: 0 15px 30px rgba(0, 0, 0, 0.4);
        }

        .feature-icon {
            font-size: 3rem;
            color: var(--primary-color);
            margin-bottom: 20px;
        }

        .feature-card h3 {
            font-size: 1.5rem;
            margin-bottom: 10px;
        }

        /* Footer */
        footer {
            text-align: center;
            padding: 40px 20px;
            background-color: var(--secondary-color);
            margin-top: 50px;
        }

        /* Keyframe Animations */
        @keyframes fadeInDown {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    </style>
</head>
<body>

    <header>
        <div class="header-content">
            <h1 class="bot-name">@DIPESHCHOUDHARYBOT</h1>
            <p class="bot-tagline">Your Powerful & Versatile Quiz Management Assistant</p>
            <a href="https://t.me/DIPESHCHOUDHARYBOT" target="_blank" class="cta-button">Add to Telegram</a>
        </div>
    </header>

    <main class="container">
        <section id="features">
            <h2>Core Features</h2>
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feature-icon">📝</div>
                    <h3>Manual Quiz Creation</h3>
                    <p>Use the <code>/create</code> command to build quizzes step-by-step, right inside Telegram.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <h3>Bulk Poll Sender</h3>
                    <p>Instantly convert text or .txt files into multiple quiz polls with the <code>/txqz</code> command.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🌐</div>
                    <h3>Interactive HTML Quizzes</h3>
                    <p>Transform .txt or .csv files into shareable, timed HTML tests using the <code>/htmk</code> command.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🔄</div>
                    <h3>Shuffle & Randomize</h3>
                    <p>Easily shuffle question and answer orders for your quizzes to prevent cheating with <code>/shufftxt</code>.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">📄</div>
                    <h3>Multiple Format Support</h3>
                    <p>Intelligently parses various quiz formats, from simple text to complex CSV and JSON structures.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">⚙️</div>
                    <h3>Customizable Tests</h3>
                    <p>Set custom timers, negative marking, and filenames for your generated HTML quizzes.</p>
                </div>
            </div>
        </section>
    </main>

    <footer>
        <p>Developed by @dipesh_choudhary_rj</p>
    </footer>

    <script>
        // Simple Intersection Observer for scroll animations
        document.addEventListener("DOMContentLoaded", () => {
            const cards = document.querySelectorAll('.feature-card');

            const observer = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.1 // Trigger when 10% of the card is visible
            });

            cards.forEach(card => {
                observer.observe(card);
            });
        });
    </script>
</body>
</html>
"""

@web.route("/")
def index_web():
    # Return the static landing page HTML as requested, instead of the DB view
    return render_template_string(FLASK_INDEX_HTML)

# Note: The original /export/ and /delete/ routes were removed as they are not
# part of the new requested landing page and conflict with the requirement
# to "not show quiz db on web page".

def run_flask():
    web.run(host="0.0.0.0", port=WEB_PORT, debug=False, use_reloader=False)

def start_web_thread():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# --- startup ---
if __name__ == "__main__":
    # Clean any orphaned session files from previous runs
    print("Cleaning old session files...")
    files = glob.glob(os.path.join(SESSION_DIR, "*.json"))
    for f in files:
        try:
            os.remove(f)
        except:
            pass
    print(f"Removed {len(files)} old session files.")

    if OWNER_ID:
        ensure_owner_exists(OWNER_ID, None, None)
    start_web_thread()
    print("Starting bot + web panel...")
    app.run()
