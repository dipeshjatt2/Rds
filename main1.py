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
import glob
import uuid
import shutil
import tempfile
import pytz
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
from telegram.helpers import escape_markdown

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Poll,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    PollAnswerHandler,
    PollHandler,
    filters,
    JobQueue,
    InlineQueryHandler,
)
from telegram.constants import ParseMode

# --- BOT CONFIGURATION ---
BOT_TOKEN = os.environ.get("book")
OWNER_ID = 5203820046
DB_PATH = "quizzes.db"
SESSION_DIR = "sessions"
os.makedirs(SESSION_DIR, exist_ok=True)
 
# +++ ADD THESE LINES +++

POLL_QUESTION_MAX_LENGTH = 250
PLACEHOLDER_QUESTION = "⬆️ LOOK AT THE MESSAGE ABOVE FOR THE QUESTION ⬆️"


if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN env var required. Please set it in your environment.")

# --- DATABASE INITIALIZATION ---
def init_db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS creators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_user_id INTEGER UNIQUE,
        username TEXT,
        display_name TEXT,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quizzes (
        id TEXT PRIMARY KEY,
        title TEXT,
        creator_id INTEGER,
        total_time_min INTEGER,
        time_per_question_sec INTEGER,
        negative_mark REAL DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(creator_id) REFERENCES creators(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id TEXT,
        idx INTEGER,
        q_json TEXT,
        FOREIGN KEY(quiz_id) REFERENCES quizzes(id)
    )""")
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
    # New table for scheduled quizzes
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        quiz_id TEXT,
        creator_id INTEGER,
        scheduled_time_utc TEXT,
        status TEXT DEFAULT 'pending' -- pending, triggered, error
    )""")
    con.commit()
    try:
        cur.execute("PRAGMA table_info(quizzes)")
        cols = [r[1] for r in cur.fetchall()]
        if "time_per_question_sec" not in cols:
            cur.execute("ALTER TABLE quizzes ADD COLUMN time_per_question_sec INTEGER")
            con.commit()
    except Exception:
        pass
    con.row_factory = sqlite3.Row
    return con

db = init_db()

# --- UTILITY FUNCTIONS & STATE MANAGEMENT ---
def db_execute(query, params=(), commit=True):
    cur = db.cursor()
    cur.execute(query, params)
    if commit:
        db.commit()
    return cur

running_private_tasks: Dict[Tuple[int,int], asyncio.Task] = {} 
running_group_tasks: Dict[Tuple[int,str], asyncio.Task] = {}
private_session_locks: Dict[Tuple[int,int], asyncio.Lock] = {}
group_session_locks: Dict[Tuple[int,str], asyncio.Lock] = {}
ongoing_sessions = {}
POLL_ID_TO_SESSION_MAP: Dict[str, Dict[str, Any]] = {}

# --- REPLACE your old generate_quiz_html function with this one ---

async def generate_quiz_html(quiz_settings: dict, questions: list) -> str | None:
    """
    Generates a standalone, interactive HTML file from quiz data for the new template.

    Args:
        quiz_settings: A dictionary with quiz settings like total time and negative marks.
        questions: A list of question objects from the session.

    Returns:
        The file path to the generated temporary HTML file, or None on failure.
    """
    try:
        # 1. Read the HTML template
        with open("format.html", "r", encoding="utf-8") as f:
            html_template = f.read()

        # 2. Build the full quiz object required by the new HTML template.
        #    The `questions` list from the session already has the correct format
        #    ('text', 'options', 'correctIndex', etc.), so we don't need to convert it.
        full_quiz_object = {
            "settings": {
                "totalTimeSec": quiz_settings.get("totalTimeSec", 600),
                "negativeMarkPerWrong": quiz_settings.get("negativeMark", 0.0)
            },
            "questions": questions
        }
        
        # 3. Convert the entire object to a JSON string
        quiz_data_json = json.dumps(full_quiz_object, ensure_ascii=False, indent=2)

        # 4. Replace the new placeholder in the template
        final_html = html_template.replace(
            "/* QUIZ_DATA_PLACEHOLDER */",
            quiz_data_json
        )

        # 5. Save to a temporary file and return the path
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html", encoding="utf-8") as temp_f:
            temp_f.write(final_html)
            return temp_f.name

    except FileNotFoundError:
        print("CRITICAL ERROR: The 'format.html' template file was not found.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred in generate_quiz_html: {e}")
        traceback.print_exc()
        return None


def get_private_lock(key: Tuple[int,int]):
    if key not in private_session_locks:
        private_session_locks[key] = asyncio.Lock()
    return private_session_locks[key]

def get_group_lock(key: Tuple[int,str]):
    if key not in group_session_locks:
        group_session_locks[key] = asyncio.Lock()
    return group_session_locks[key]

def get_private_session_path(user_id, attempt_id):
    return os.path.join(SESSION_DIR, f"private_{user_id}_{attempt_id}.json")

def get_group_session_path(chat_id, quiz_id):
    safe_quiz_id = re.sub(r'[^a-zA-Z0-9_]', '', str(quiz_id))
    return os.path.join(SESSION_DIR, f"group_{chat_id}_{safe_quiz_id}.json")

async def read_session_file(path, lock: asyncio.Lock):
    async with lock:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if 'started_at' in data and isinstance(data['started_at'], str):
                    try:
                        data['started_at'] = datetime.fromisoformat(data['started_at'])
                    except Exception:
                        data['started_at'] = datetime.utcnow()
                return data
        except Exception:
            traceback.print_exc()
            return None

async def write_session_file(path, session_data, lock: asyncio.Lock):
    async with lock:
        data_to_write = session_data.copy()
        if 'started_at' in data_to_write and isinstance(data_to_write['started_at'], datetime):
            data_to_write['started_at'] = data_to_write['started_at'].isoformat()
        data_to_write.pop('auto_task', None)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data_to_write, f, ensure_ascii=False, indent=2)
        except Exception:
            traceback.print_exc()

async def delete_session_file(path, key, lock_dict, task_dict=None):
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
            os.remove(path)
        except Exception as e:
            print(f"Error removing orphaned session file {path}: {e}")

    if task_dict is not None:
        task = task_dict.pop(key, None)
        if task:
            try:
                task.cancel()
            except Exception:
                pass
    lock_dict.pop(key, None)

# --- PARSING FUNCTIONS ---
def parse_format2_enhanced(txt: str):
    questions = []
    blocks = re.split(r'\n\s*\n+', txt.strip())
    option_regex = re.compile(r'^\s*\([a-zA-Z]\)\s*')
    ex_regex = re.compile(r'(?i)^ex:\s*')
    for block in blocks:
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        if not re.match(r'^\s*(\d+)\.\s*(.*)', lines[0]):
             return []
        first_opt_ex_index = -1
        for i, line in enumerate(lines):
            if option_regex.match(line) or ex_regex.match(line):
                first_opt_ex_index = i
                break
        if first_opt_ex_index == -1:
            return []
        q_lines = lines[:first_opt_ex_index]
        opt_ex_lines = lines[first_opt_ex_index:]
        if not q_lines:
            return []
        q_text_first_line = re.sub(r'^\s*\d+\.\s*', '', q_lines[0]).strip()
        q_text_other_lines = [l.strip() for l in q_lines[1:]]
        all_q_text_parts = [q_text_first_line] + q_text_other_lines
        qtext = "\n".join(all_q_text_parts).strip()
        opts = []
        correct = -1
        explanation_buffer = []
        parsing_explanation = False
        for l in opt_ex_lines:
            l_stripped = l.strip()
            if parsing_explanation:
                explanation_buffer.append(l_stripped)
                continue
            if ex_regex.match(l_stripped):
                parsing_explanation = True
                first_ex_line = ex_regex.sub('', l_stripped).strip()
                if first_ex_line:
                    explanation_buffer.append(first_ex_line)
            elif option_regex.match(l_stripped):
                opt_text = option_regex.sub('', l_stripped).strip()
                if "✅" in opt_text or "✅️" in opt_text:
                    opt_text = opt_text.replace("✅", "").replace("✅️", "").strip()
                    opts.append(opt_text)
                    correct = len(opts) - 1
                else:
                    opts.append(opt_text)
            elif l_stripped and opts:
                opts[-1] = opts[-1] + "\n" + l_stripped
        explanation = "\n".join(explanation_buffer).strip()
        if not opts or len(opts) < 2 or correct == -1:
            return []
        questions.append({
            "text": qtext,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })
    return questions

def parse_format_dash(txt: str):
    questions = []
    blocks = re.split(r'(?m)^Q\d+:\s*', txt)
    for block in blocks:
        if not block.strip():
            continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        qtext = lines[0]
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
            continue
        questions.append({
            "text": qtext,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })
    return questions

def parse_format1(txt: str):
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
            continue
        questions.append({
            "text": definition,
            "options": opts,
            "correctIndex": correct,
            "explanation": explanation,
            "reference": ""
        })
    return questions

def parse_format2_simple(txt: str):
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
            continue
        questions.append({"text":qtext,"options":opts,"correctIndex":correct,"explanation":explanation.strip(),"reference":""})
    return questions

def parse_format3(txt: str):
    try:
        m = re.search(r'const\s+quizData\s*=\s*(\[.*\]);', txt, flags=re.S)
        if not m:
             m = re.search(r'const\s+quizData\s*=\s*({.*});', txt, flags=re.S)
             if not m:
                 return []
             obj = json.loads(m.group(1))
             return obj.get("questions",[])
        return json.loads(m.group(1))
    except Exception:
        return []

def parse_format4(txt: str):
    questions=[]
    blocks = re.split(r'\n\s*\n', txt.strip())
    for block in blocks:
        lines=[l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 3: continue
        qtext=lines[0]
        opts=[];correct=-1
        explanation = ""
        opt_lines = lines[1:]
        ex_line_index = -1
        for i, l in enumerate(opt_lines):
             if l.lower().startswith("ex:"):
                 explanation = re.sub(r'(?i)^ex:\s*', '', l).strip()
                 ex_line_index = i
                 if i + 1 < len(opt_lines):
                     explanation += "\n" + "\n".join(opt_lines[i+1:])
                 break
        if ex_line_index != -1:
            opt_lines = opt_lines[:ex_line_index]
        for i,l in enumerate(opt_lines):
            has_tick='✅' in l
            l=l.replace('✅','').strip()
            opts.append(l)
            if has_tick: correct=i
        if not opts or correct == -1:
            continue
        questions.append({"text":qtext,"options":opts,"correctIndex":correct,"explanation":explanation,"reference":""})
    return questions

def parse_csv(path: str):
    questions = []
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                opts = []
                for i in range(1, 11):
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
                    continue
                questions.append({
                    "text": q_text.strip(),
                    "options": opts,
                    "correctIndex": correct_idx,
                    "explanation": row.get("Explanation", "").strip(),
                    "reference": ""
                })
    except Exception as e:
        print(f"Failed to parse CSV: {e}")
        return []
    return questions

def detect_and_parse_strict(txt: str):
    res_f2_enhanced = parse_format2_enhanced(txt)
    if res_f2_enhanced:
        return res_f2_enhanced
    res_f4 = parse_format4(txt)
    if res_f4:
        return res_f4
    res_f_dash = parse_format_dash(txt)
    if res_f_dash:
        return res_f_dash
    res_f1 = parse_format1(txt)
    if res_f1:
        return res_f1
    res_f2_simple = parse_format2_simple(txt)
    if res_f2_simple:
        return res_f2_simple
    res_f3 = parse_format3(txt)
    if res_f3:
        return res_f3
    return []

# --- JSON & DB HELPER FUNCTIONS ---
def questions_to_json(qs):
    return json.dumps(qs, ensure_ascii=False)

def questions_from_json(s):
    return json.loads(s)

def get_creator_by_tg(tg_user_id):
    cur = db_execute("SELECT * FROM creators WHERE tg_user_id = ?", (tg_user_id,), commit=False)
    return cur.fetchone()

def get_or_create_creator_by_tg(user):
    c = db_execute("SELECT * FROM creators WHERE tg_user_id = ?", (user.id,), commit=False).fetchone()
    if c:
        return c
    username = user.username or ""
    display_name = ((user.first_name or "") + " " + (user.last_name or "")).strip()
    cur = db_execute("INSERT INTO creators (tg_user_id, username, display_name, is_admin) VALUES (?, ?, ?, 0)",
                     (user.id, username, display_name), commit=True)
    return db_execute("SELECT * FROM creators WHERE id = ?", (cur.lastrowid,), commit=False).fetchone()

def generate_quiz_id(length=8):
    chars = string.ascii_letters + string.digits
    while True:
        quiz_id = ''.join(random.choices(chars, k=length))
        if not db_execute("SELECT 1 FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone():
            return quiz_id

def ensure_owner_exists(tg_user_id, username=None, display_name=None):
    global OWNER_ID
    if OWNER_ID == 0:
        OWNER_ID = tg_user_id
    c = get_creator_by_tg(OWNER_ID)
    if not c:
        db_execute("INSERT INTO creators (tg_user_id, username, display_name, is_admin) VALUES (?, ?, ?, 1)",
                   (OWNER_ID, username or "", display_name or ""), True)

# --- COMMAND HANDLERS ---
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    uname = user.username or ""
    fullname = ((user.first_name or "") + " " + (user.last_name or "")).strip()
    if OWNER_ID == 0:
        ensure_owner_exists(uid, uname, fullname)
    
    is_owner = uid == OWNER_ID
    owner_commands = (
        "\n\n👑 **Owner Commands:**\n"
        "• /backup - Create a backup of the DB and images\n"
        "• /restore - Restore from a backup file (reply to file)"
    ) if is_owner else ""

    text = (
        "👋 **Welcome to QuizMaster Bot!**\n\n"
        "Available commands:\n"
        "• /create - Create a quiz interactively\n"
        "• /myquizzes - List quizzes you created\n"
        "• /take <quiz_id> - Start a timed quiz (private)\n"
        "• /post <quiz_id> - Post/share a quiz card into the chat\n"
        "• /schedule <quiz_id> - Schedule a quiz to run in a group\n"
        "• /finish - Finish your active private quiz early\n"
        "• /finish <quiz_id> - (In groups) Finish a specific quiz (admins only)\n\n"
        "Create and play quizzes using Telegram’s built-in quiz polls."
        f"{owner_commands}"
    )
    await update.effective_message.reply_text(text)

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = {"flow": "create_quiz", "step": "title"}
    ongoing_sessions[(uid, "create")] = state
    await update.effective_message.reply_text("✍️ Creating a new quiz. Send the *Quiz Title*:")

async def done_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /done command during the questions step of quiz creation."""
    if update.effective_chat.type != 'private':
        return

    uid = update.effective_user.id
    key = (uid, "create")
    
    if key not in ongoing_sessions:
        return

    state = ongoing_sessions[key]

    if state.get("step") == "questions":
        if not state.get("questions"):
            await update.effective_message.reply_text("❌ No questions found. Send at least one question in the required format or upload a .txt file.")
            return
        
        state["step"] = "images"
        await update.effective_message.reply_text(
            "✅ Questions saved.\n\n"
            "Do you want to add images to the questions?\n"
            "If yes, send an image with the **question number** as the caption (e.g., caption `1` for the first question).\n\n"
            "Send /no_images when you are finished adding images or to skip this step."
        )

async def no_images_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /no_images command during the images step of quiz creation."""
    if update.effective_chat.type != 'private':
        return

    uid = update.effective_user.id
    key = (uid, "create")
    
    if key not in ongoing_sessions:
        return

    state = ongoing_sessions[key]

    if state.get("step") == "images":
        creator = get_or_create_creator_by_tg(update.effective_user)
        quiz_id = generate_quiz_id()
        db_execute("INSERT INTO quizzes (id, title, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?)",
                         (quiz_id, state["title"], creator["id"], 0, state.get("time_per_question_sec", 30), state.get("negative", 0.0), datetime.utcnow().isoformat()))
        for idx, q in enumerate(state["questions"]):
            db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
        
        del ongoing_sessions[key]
        await update.effective_message.reply_text(f"✅ Quiz created with id `{quiz_id}` (time per question: {state.get('time_per_question_sec')}s, negative: {state.get('negative')})", parse_mode=ParseMode.MARKDOWN)

async def create_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    uid = update.effective_user.id
    key = (uid, "create")
    if key not in ongoing_sessions:
        return
    state = ongoing_sessions[key]
    if update.message and (update.message.document or update.message.photo) and state.get("step") == "questions":
        return
    text = (update.message.text or "").strip() if update.message and update.message.text else ""
    if not text:
        return
    
    # State: Title
    if state["step"] == "title":
        state["title"] = text
        state["step"] = "time_per_q"
        await update.effective_message.reply_text("Saved title. Now send **time per question in seconds** (integer):")
        return
    
    # State: Time per Question
    if state["step"] == "time_per_q":
        try:
            secs = int(text)
            if secs <= 0:
                raise ValueError
            state["time_per_question_sec"] = secs
        except:
            await update.effective_message.reply_text("❌ Please send a valid positive integer for seconds.")
            return
        state["step"] = "negative"
        await update.effective_message.reply_text("Saved time. Now send **negative marks per wrong answer** (e.g., `0.25` or `0` for none):")
        return

    # State: Negative Marking
    if state["step"] == "negative":
        try:
            neg = float(text)
            if neg < 0:
                raise ValueError
            state["negative"] = neg
        except:
            await update.effective_message.reply_text("❌ Please send a valid non-negative number for negative marks (e.g., 0.25).")
            return
        state["step"] = "questions"
        state["questions"] = []
        await update.effective_message.reply_text(
            "Now send questions one by one in this exact format OR upload a `.txt` file with many questions in the same format:\n\n"
            "1. [4/50] Question text (can be multiple lines)\n"
            "(a) option1 (can be multiple lines)\n"
            "(b) option2 ✅\n"
            "(c) option3\n"
            "Ex: Optional explanation text (can be multiple lines)\n\n"
            "Send /done when finished."
        )
        return

    # State: Questions
    if state["step"] == "questions":
        parsed = parse_format2_enhanced(text)
        if not parsed:
            await update.effective_message.reply_text("❌ Could not parse the question. Make sure it exactly matches the required format (numbered, (a) options, and one ✅).")
            return
        state["questions"].extend(parsed)
        await update.effective_message.reply_text(f"✅ Saved {len(parsed)} question(s). Total so far: {len(state['questions'])}. Send next or /done.")
        return

    # State: Images
    if state["step"] == "images":
        # This part now only handles unexpected text. /no_images is a command.
        await update.effective_message.reply_text("Please send an image with a question number as the caption, or send /no_images to finish creating the quiz.")
        return

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.photo:
        return
    uid = update.effective_user.id
    key = (uid, "create")

    if key in ongoing_sessions and ongoing_sessions[key].get("step") == "images":
        state = ongoing_sessions[key]
        caption = (msg.caption or "").strip()
        if not caption.isdigit():
            await msg.reply_text("❌ Invalid caption. Please send a valid question number (e.g., '1', '2', etc.).")
            return
        
        q_num = int(caption)
        if not (1 <= q_num <= len(state.get("questions", []))):
            await msg.reply_text(f"❌ Question number out of range. You have {len(state.get('questions',[]))} questions. Please provide a number between 1 and {len(state.get('questions',[]))}.")
            return
        
        file_id = msg.photo[-1].file_id
        state["questions"][q_num - 1]["image_file_id"] = file_id
        await msg.reply_text(f"✅ Image saved for question {q_num}. Send more images or /no_images to finish.")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.document:
        return
    uid = update.effective_user.id
    create_key = (uid, "create")
    
    # Handle .txt or .csv file upload during the /create flow
    if create_key in ongoing_sessions and ongoing_sessions[create_key].get("step") == "questions":
        file_obj = await msg.document.get_file()
        path = await file_obj.download_to_drive()
        
        fname = (msg.document.file_name or "").lower()
        try:
            if fname.endswith(".txt"):
                with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    data = f.read()
                parsed = detect_and_parse_strict(data)
                if not parsed:
                    await msg.reply_text("❌ The .txt file did not match any of the required formats or was invalid. Please fix and resend.")
                    return
                ongoing_sessions[create_key].setdefault("questions", []).extend(parsed)
                await msg.reply_text(f"✅ Imported {len(parsed)} questions from the file. Total so far: {len(ongoing_sessions[create_key]['questions'])}. Send more or /done.")
                return
            elif fname.endswith(".csv"):
                parsed = parse_csv(path)
                if not parsed:
                    await msg.reply_text("❌ CSV parsing failed.")
                    return
                ongoing_sessions[create_key].setdefault("questions", []).extend(parsed)
                await msg.reply_text(f"✅ Imported {len(parsed)} questions from CSV. Total so far: {len(ongoing_sessions[create_key]['questions'])}. Send more or /done.")
                return
        finally:
            try:
                os.remove(path)
            except:
                pass
        return

    # Handle standalone .csv file upload to create a quiz directly
    file_obj = await msg.document.get_file()
    path = await file_obj.download_to_drive()
    
    fname = (msg.document.file_name or "").lower()
    creator = get_or_create_creator_by_tg(update.effective_user)
    try:
        if fname.endswith(".csv"):
            parsed = parse_csv(path)
            if not parsed:
                await msg.reply_text(f"❌ Failed to parse {fname}: CSV format error or empty.")
                return
            title = os.path.splitext(os.path.basename(fname))[0]
            quiz_id = generate_quiz_id()
            db_execute("INSERT INTO quizzes (id, title, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?)",
                                (quiz_id, title, creator["id"], 0, 30, 0.0, datetime.utcnow().isoformat()))
            for idx, q in enumerate(parsed):
                db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
            await msg.reply_text(f"✅ CSV Upload: Created 1 quiz ({title}) with {len(parsed)} questions. ID: `{quiz_id}`")
            return
    except Exception as e:
        await msg.reply_text(f"❌ Error processing document: {e}")
    finally:
        try:
            os.remove(path)
        except:
            pass

async def myquizzes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    c = get_creator_by_tg(uid)
    if not c:
        await update.effective_message.reply_text("You haven't created any quizzes yet. Use /create to start.")
        return
    cur = db_execute("SELECT * FROM quizzes WHERE creator_id = ? ORDER BY created_at DESC", (c["id"],), commit=False)
    rows = cur.fetchall()
    if not rows:
        await update.effective_message.reply_text("You have no quizzes yet.")
        return
    text_lines = []
    kb = []
    for r in rows:
        tp = r['time_per_question_sec'] or '-'
        text_lines.append(f"ID: {r['id']} | {r['title']} | Time/q: {tp}s | Neg: {r['negative_mark']}")
        kb.append([InlineKeyboardButton(f"{r['id']}: {r['title']}", callback_data=f"viewquiz:{r['id']}")])
    await update.effective_message.reply_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(kb))

# --- CALLBACK QUERY HANDLERS ---
async def view_quiz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
    txt = (f"Quiz ID: {quiz_id}\nTitle: {qrow['title']}\n"
           f"Creator: {creator['username'] or creator['display_name']}\nQuestions: {len(qrows)}\n\nPreview:\n" + "\n".join(preview))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Delete 🚮", callback_data=f"deletequiz:{quiz_id}"), InlineKeyboardButton("Export♻️✅️", callback_data=f"exportquiz:{quiz_id}")],
        [InlineKeyboardButton("Share (post card)↗️➡️↘️", callback_data=f"postcard:{quiz_id}")]
    ])
    await query.message.reply_text(txt, reply_markup=kb)

async def delete_quiz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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

async def export_quiz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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

async def postcard_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    quiz_id = query.data.split(":")[1]
    await post_quiz_card(context.bot, query.message.chat.id, quiz_id)

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.effective_message.text.split()
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /post <quiz_id>")
        return
    quiz_id = args[1]
    await post_quiz_card(context.bot, update.effective_chat.id, quiz_id)
    
async def _generate_quiz_card_content(quiz_id: str) -> Tuple[str, InlineKeyboardMarkup, int, int] | Tuple[None, None, None, None]:
    """
    Fetches quiz data and generates the text and keyboard for a quiz card.
    Returns (text, keyboard, question_count, time_per_question) or (None, None, None, None) if not found.
    """
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        return None, None, None, None
        
    qs_cur = db_execute("SELECT COUNT(*) as cnt FROM questions WHERE quiz_id = ?", (quiz_id,), commit=False)
    total_q = qs_cur.fetchone()["cnt"]
    
    title = escape_markdown(qrow["title"] or f"Quiz {quiz_id}", version=2)
    time_per_q = qrow['time_per_question_sec'] or 30
    negative_marking = qrow['negative_mark']
    negative_marking_str = escape_markdown(str(negative_marking), version=2)

    # All changes are in this section to escape the hardcoded '#' and '-' characters
    base_lines = [
        f'💳 *Quiz Name:* {title}',
        f'\\#️⃣ *Questions:* {total_q}',  # FIXED: Escaped the '#' character
        f'⏰ *Timer:* {time_per_q} seconds',
        f'🆔 *Quiz ID:* `{quiz_id}`',
        f'🏴‍☠️ *\\-ve Marking:* {negative_marking_str}',  # FIXED: Escaped the '-' character
        '💰 *Type:* free'
    ]
    
    creator_mention_line = ""
    if qrow['creator_id']:
        creator_row = db_execute("SELECT * FROM creators WHERE id = ?", (qrow['creator_id'],), commit=False).fetchone()
        if creator_row:
            if creator_row['username']:
                creator_mention_line = f"*Created by:* @{creator_row['username']}"
            elif creator_row['display_name']:
                 escaped_name = escape_markdown(creator_row['display_name'], version=2)
                 creator_mention_line = f"*Created by:* {escaped_name}"
    
    if creator_mention_line:
        base_lines.append(creator_mention_line)

    base_lines.append("\nTap start to play\\!")

    text = "\n".join(base_lines)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Start this quiz (in this chat) 🧑‍🧑‍🧒‍🧒", callback_data=f"startgroup:{quiz_id}")],
        [InlineKeyboardButton("Start in private👤", callback_data=f"startprivate:{quiz_id}")]
    ])
    
    return text, kb, total_q, time_per_q


    
async def post_quiz_card(bot, chat_id, quiz_id):
    text, kb, _, __ = await _generate_quiz_card_content(quiz_id)
    if text and kb:
        # CHANGE: Switched to MARKDOWN_V2 to handle the escaped text correctly
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        try:
            await bot.send_message(chat_id, "Quiz not found.")
        except Exception:
            pass


# +++ ADD THIS ENTIRE NEW FUNCTION +++
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the inline query."""
    query = update.inline_query.query
    
    # Don't do anything if the query is empty
    if not query:
        return
        
    quiz_id = query.strip()
    results = []

    # Use our helper to get quiz details
    text, kb, total_q, time_per_q = await _generate_quiz_card_content(quiz_id)

    if text and kb:
        # If the quiz is found, create a result article
        results.append(
            InlineQueryResultArticle(
                id=quiz_id,
                title=db_execute("SELECT title FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()['title'],
                description=f"{total_q} Questions | {time_per_q}s Timer | ID: {quiz_id}",
                input_message_content=InputTextMessageContent(
                    message_text=text,
                    parse_mode=ParseMode.MARKDOWN,
                ),
                reply_markup=kb,
            )
        )
    else:
        # Optional: Show a "Not Found" message if the ID is invalid
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="Quiz Not Found",
                description=f"No quiz exists with the ID: {quiz_id}",
                input_message_content=InputTextMessageContent(
                    f"❌ Could not find a quiz with ID: `{quiz_id}`"
                ),
            )
        )

    await update.inline_query.answer(results, cache_time=5)



async def start_private_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Starting quiz in private...")
    quiz_id = query.data.split(":")[1]
    uid = query.from_user.id
    try:
        await context.bot.send_message(uid, "Starting quiz in private for you...")
        await take_quiz_private(context.bot, uid, quiz_id)
    except Exception as e:
        await query.message.reply_text(f"❌ Failed to start in private: {e}")

async def start_group_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Starting quiz in this chat...")
    quiz_id = query.data.split(":")[1]
    chat_id = query.message.chat.id
    await start_quiz_in_group(context.bot, chat_id, quiz_id, starter_id=query.from_user.id)

# --- PRIVATE QUIZ LOGIC ---
async def take_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.effective_message.text.split()
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /take <quiz_id>"); return
    quiz_id = args[1]
    await take_quiz_private(context.bot, update.effective_user.id, quiz_id)

async def take_quiz_private(bot, user_id, quiz_id):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await bot.send_message(user_id, "Quiz not found.")
        except:
            pass
        return
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        try:
            await bot.send_message(user_id, "No questions in quiz.")
        except:
            pass
        return
    questions = [questions_from_json(qr["q_json"]) for qr in qrows]
    username = ""  
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
        "started_at": datetime.utcnow(),
        "time_per_question_sec": int(qrow["time_per_question_sec"] or 30),
        "message_id": None,
        "chat_id": user_id,
    }
    session_key = (user_id, attempt_id)
    session_path = get_private_session_path(user_id, attempt_id)
    lock = get_private_lock(session_key)
    await write_session_file(session_path, session, lock)
    try:
        await bot.send_message(user_id, f"✅ Quiz started: {qrow['title']}\nTime per question: {session['time_per_question_sec']} seconds.\nAnswer by tapping an option.")
    except:
        pass
    await send_question_for_session_private(bot, session_key)

# +++ REPLACEMENT CODE +++
async def send_question_for_session_private(bot, session_key):
    path = get_private_session_path(*session_key)
    lock = get_private_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return
    qidx = session["current_q"]
    if qidx < 0 or qidx >= len(session["questions"]):
        await finalize_attempt(bot, session_key, session)
        return
    q = session["questions"][qidx]

    # Send image if it exists
    image_file_id = q.get("image_file_id")
    if image_file_id:
        try:
            await bot.send_photo(chat_id=session["chat_id"], photo=image_file_id)
        except Exception as e:
            print(f"Failed to send photo for private quiz (will continue): {e}")

    explanation = q.get("explanation") or None
    question_text = q.get("text")
    poll_question_text = question_text

    if len(question_text) > POLL_QUESTION_MAX_LENGTH:
        await bot.send_message(chat_id=session["chat_id"], text=question_text)
        poll_question_text = PLACEHOLDER_QUESTION

    sent = None
    for attempt in range(3):
        try:
            sent = await bot.send_poll(
                chat_id=session["chat_id"],
                question=poll_question_text,
                options=q.get("options"),
                type=Poll.QUIZ,
                correct_option_id=q.get("correctIndex", 0),
                open_period=session["time_per_question_sec"],
                is_anonymous=False,
                explanation=explanation
            )
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to send private poll: {e}")
            if attempt < 2:
                await asyncio.sleep(2)
            else:
                print("All retries failed for private poll. Finalizing quiz.")
                await finalize_attempt(bot, session_key, session)
                return

    if not sent:
        return

    session['poll_id'] = sent.poll.id
    session['message_id'] = sent.message_id if hasattr(sent, 'message_id') else None
    POLL_ID_TO_SESSION_MAP[sent.poll.id] = {"type": "private", "key": session_key}
    await write_session_file(path, session, lock)

    # +++ ADD THIS ENTIRE TIMER BLOCK +++
    # This creates a reliable internal timer to advance the question if the user doesn't answer.
    old_task = running_private_tasks.pop(session_key, None)
    if old_task:
        old_task.cancel()

    async def per_question_timeout_private():
        try:
            # Wait for the poll duration + a 2-second buffer
            await asyncio.sleep(session["time_per_question_sec"] + 2)
            # Re-read the session to ensure we are still on the same question
            fresh_session = await read_session_file(path, lock)
            if fresh_session and fresh_session["current_q"] == qidx:
                # If still on the same question, force advancement
                await reveal_correct_and_advance_private(bot, session_key, qidx, timed_out=True)
        except asyncio.CancelledError:
            pass # This is expected if the user answers normally

    running_private_tasks[session_key] = asyncio.create_task(per_question_timeout_private())


# --- POLL HANDLERS ---
async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user = answer.user
    user_id = user.id
    poll_id = answer.poll_id
    option_ids = answer.option_ids
    if not option_ids:
        return
    chosen = option_ids[0]

    mapping = POLL_ID_TO_SESSION_MAP.get(poll_id)
    if not mapping:
        return

    session_type = mapping.get("type")
    session_key = mapping.get("key")

    if session_type == "private":
        try:
            user_id_key, attempt_id = session_key
            if user_id_key != user_id:
                 return
            
            lock = get_private_lock(session_key)
            session_path = get_private_session_path(user_id, attempt_id)
            session = await read_session_file(session_path, lock)
            
            if not session:
                return
            qidx = session["current_q"]
            if qidx < 0 or qidx >= len(session["questions"]):
                return
            if session["answers"][qidx] != -1:
                return
            
            session["answers"][qidx] = chosen
            await write_session_file(session_path, session, lock)
            
            await reveal_correct_and_advance_private(context.bot, session_key, qidx, chosen_idx=chosen)
        except Exception as e:
            print(f"Error handling private poll answer: {e}")
            traceback.print_exc()
        return

    elif session_type == "group":
        try:
            chat_id, quiz_id = session_key
            lock = get_group_lock(session_key)
            session_path = get_group_session_path(chat_id, quiz_id)
            session = await read_session_file(session_path, lock)

            if not session:
                return
            qidx = session["current_q"]
            if qidx < 0 or qidx >= len(session["questions"]):
                return

            p_data = session["participants"].get(str(user_id))
            if p_data is None:
                user_full_name = ((user.first_name or "") + " " + (user.last_name or "")).strip()
                p_data = {
                    "answers": [-1] * len(session["questions"]),
                    "start_time": time.time(),
                    "username": user_full_name or str(user_id)
                }
                session["participants"][str(user_id)] = p_data
            
            if p_data["answers"][qidx] != -1:
                return
            
            p_data["answers"][qidx] = chosen
            p_data["end_time"] = time.time()
            await write_session_file(session_path, session, lock)
        except Exception as e:
            print(f"Error handling group poll answer: {e}")
            traceback.print_exc()
        return

async def poll_update_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll = update.poll
    if not poll.is_closed:
        return
    
    mapping = POLL_ID_TO_SESSION_MAP.get(poll.id)
    if not mapping or mapping.get("type") != "private":
        return

    session_key = mapping.get("key")
    if not session_key:
        return

    path = get_private_session_path(*session_key)
    lock = get_private_lock(session_key)
    session = await read_session_file(path, lock)

    if not session:
        return

    if session.get("poll_id") == poll.id:
        await reveal_correct_and_advance_private(context.bot, session_key, session["current_q"], timed_out=True)

# --- ADVANCEMENT & FINALIZATION LOGIC ---
# +++ REPLACEMENT CODE +++
async def reveal_correct_and_advance_private(bot, session_key, qidx, chosen_idx=None, timed_out=False):
    path = get_private_session_path(*session_key)
    lock = get_private_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return

    # +++ ADD THIS CRITICAL CHECK +++
    # This prevents a race condition. If the user answers AND the poll times out,
    # this function might be called twice. We check if the quiz has already
    # advanced past the question index (`qidx`) this call was for.
    if session.get("current_q") != qidx:
        return # Do nothing, we've already moved on.
    
    if session.get("poll_id"):
        POLL_ID_TO_SESSION_MAP.pop(session["poll_id"], None)

    session["current_q"] += 1
    await write_session_file(path, session, lock)
    
    if session["current_q"] >= len(session["questions"]):
        await finalize_attempt(bot, session_key, session)
        return
        
    await send_question_for_session_private(bot, session_key)


# +++ REPLACEMENT CODE +++
async def finalize_attempt(bot, session_key, session_data):
    # Cancel any running timer task for this quiz session
    task = running_private_tasks.pop(session_key, None)
    if task:
        task.cancel()

    # Calculate detailed statistics
    total_questions = len(session_data["questions"])
    correct = 0
    wrong = 0
    skipped = 0

    quiz_row = db_execute("SELECT * FROM quizzes WHERE id = ?", (session_data["quiz_id"],), commit=False).fetchone()
    negative = quiz_row["negative_mark"] if quiz_row else 0.0
    maxscore = len(session_data["questions"])

    for idx, q in enumerate(session_data["questions"]):
        correct_idx = q.get("correctIndex", -1)
        user_ans = session_data["answers"][idx]
        
        if user_ans == -1:
            skipped += 1
        elif user_ans == correct_idx:
            correct += 1
        else:
            wrong += 1

    # Calculate score with negative marking
    score = max(0, correct - (wrong * negative))

    # Create detailed results message
    results_text = f"""
📊 *Quiz Results: {quiz_row['title'] if quiz_row else 'Quiz'}*

✅ *Correct:* {correct}
❌ *Wrong:* {wrong}
⏭️ *Skipped:* {skipped}
📝 *Total Questions:* {total_questions}

🏆 *Score:* {score:.2f}/{maxscore}
📉 *Accuracy:* {(correct/total_questions)*100:.1f}%
⚖️ *Negative Marking:* {negative} per wrong answer

{"🎉 Excellent!" if correct/total_questions >= 0.8 else "👍 Good job!" if correct/total_questions >= 0.6 else "💪 Keep practicing!"}
"""

    finished_at = datetime.utcnow().isoformat()
    db_execute("UPDATE attempts SET finished_at=?, answers_json=?, score=?, max_score=? WHERE id=?",
               (finished_at, json.dumps(session_data["answers"]), score, maxscore, session_data["attempt_id"]))
    
    try:
        await bot.send_message(session_data["user_id"], results_text, parse_mode=ParseMode.MARKDOWN)

        total_quiz_time_sec = len(session_data["questions"]) * session_data.get("time_per_question_sec", 30)
        
        quiz_settings = {
            "totalTimeSec": total_quiz_time_sec,
            "negativeMark": negative
        }

        html_path = await generate_quiz_html(
            quiz_settings,
            session_data["questions"]
        )
        if html_path:
            try:
                await bot.send_document(
                    session_data["user_id"],
                    document=open(html_path, "rb"),
                    caption="Here is an HTML file for you to practice this quiz again.",
                    filename=f"{session_data['quiz_id']}_practice.html"
                )
            finally:
                os.remove(html_path)

    except Exception as e:
        print(f"Error sending message or HTML file in finalize_attempt: {e}")
    
    path = get_private_session_path(*session_key)
    await delete_session_file(path, session_key, private_session_locks)

async def finish_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user_id = update.effective_user.id
    
    if chat.type == 'private':
        active_sessions = glob.glob(os.path.join(SESSION_DIR, f"private_{user_id}_*.json"))
        if not active_sessions:
            await update.effective_message.reply_text("You have no active quiz to finish.")
            return
        session_path = active_sessions[0]
        filename = os.path.basename(session_path)
        try:
            parts = filename.replace("private_", "").replace(".json", "").split("_")
            uid = int(parts[0])
            attempt_id = int(parts[1])
            session_key = (uid, attempt_id)
        except Exception:
            await update.effective_message.reply_text("Error identifying your session file. Could not finish.")
            if os.path.exists(session_path): os.remove(session_path)
            return
        
        lock = get_private_lock(session_key)
        session_data = await read_session_file(session_path, lock)
        if not session_data:
            await update.effective_message.reply_text("Could not read your session data. Cleaning up.")
            await delete_session_file(session_path, session_key, private_session_locks)
            return
        
        await update.effective_message.reply_text("Finishing your quiz now and calculating results...")
        await finalize_attempt(context.bot, session_key, session_data)
        
    else: # Group chat
        args = context.args
        if not args:
            await update.effective_message.reply_text(
                "In a group, you must specify which quiz to finish.\n"
                "Usage: `/finish <quiz_id>`\n"
                "(Only admins or the quiz starter can do this.)"
            )
            return
            
        quiz_id = args[0]
        chat_id = chat.id
        session_key = (chat_id, quiz_id)
        session_path = get_group_session_path(chat_id, quiz_id)

        if not os.path.exists(session_path):
            await update.effective_message.reply_text(f"No active quiz found in this chat with ID: `{quiz_id}`", parse_mode=ParseMode.MARKDOWN)
            return

        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_ids = {admin.user.id for admin in admins}
        except Exception:
            admin_ids = set()

        lock = get_group_lock(session_key)
        session_data = await read_session_file(session_path, lock)
        starter_id = session_data.get("starter_id") if session_data else None
        
        if user_id == starter_id or user_id in admin_ids or user_id == OWNER_ID:
            await update.effective_message.reply_text(f"Force-finishing quiz `{quiz_id}` and calculating results...", parse_mode=ParseMode.MARKDOWN)
            await group_finalize_and_export(context.bot, session_key)
        else:
            await update.effective_message.reply_text("You do not have permission. Only chat admins or the person who started the quiz can finish it.")

# --- GROUP QUIZ LOGIC ---
async def start_quiz_in_group(bot, chat_id: int, quiz_id: str, starter_id: int = None):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await bot.send_message(chat_id, "Quiz not found.")
        except:
            pass
        return
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        try:
            await bot.send_message(chat_id, "No questions in quiz.")
        except:
            pass
        return
    questions = [questions_from_json(qr["q_json"]) for qr in qrows]
    session_key = (chat_id, quiz_id)
    session_path = get_group_session_path(*session_key)
    if os.path.exists(session_path):
        await bot.send_message(chat_id, f"A quiz with this ID (`{quiz_id}`) is already running. Use `/finish {quiz_id}` to stop it before starting a new one.")
        return
    session = {
        "quiz_id": quiz_id,
        "chat_id": chat_id,
        "questions": questions,
        "current_q": 0,
        "time_per_question_sec": int(qrow["time_per_question_sec"] or 30),
        "participants": {},
        "message_id": None,
        "starter_id": starter_id,
        "negative": float(qrow["negative_mark"] or 0.0),
        "title": qrow["title"]
    }
    lock = get_group_lock(session_key)
    await write_session_file(session_path, session, lock)
    
    # CHANGE: Escape the title and special characters in the message string
    escaped_title = escape_markdown(qrow['title'], version=2)
    message_text = (
        f"🎯 Quiz starting now: *{escaped_title}*\n"
        f"Time per question: {session['time_per_question_sec']}s\n"
        f"Everyone can answer using the quiz options\\. Results will be shown at the end\\."
    )
    
    # CHANGE: Switched to MARKDOWN_V2 for sending
    await bot.send_message(chat_id, message_text, parse_mode=ParseMode.MARKDOWN_V2)
    await group_send_question(bot, session_key)


async def group_send_question(bot, session_key):
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return
    qidx = session["current_q"]
    if qidx < 0 or qidx >= len(session["questions"]):
        await group_finalize_and_export(bot, session_key)
        return
    q = session["questions"][qidx]
    
    # Send image if it exists
    image_file_id = q.get("image_file_id")
    if image_file_id:
        try:
            await bot.send_photo(chat_id=session["chat_id"], photo=image_file_id)
        except Exception as e:
            print(f"Failed to send photo for group quiz (will continue): {e}")

    # ... (inside the function)
    explanation = q.get("explanation") or None
    question_text = q.get("text")
    poll_question_text = question_text

    # Check if the question is too long for a poll
    if len(question_text) > POLL_QUESTION_MAX_LENGTH:
        # Send the long question as a separate message first
        await bot.send_message(chat_id=session["chat_id"], text=question_text)
        # Use a placeholder for the poll question
        poll_question_text = PLACEHOLDER_QUESTION
        
    sent = None
    for attempt in range(3): # Retry up to 3 times
        try:
            sent = await bot.send_poll(
                chat_id=session["chat_id"],
                question=poll_question_text, # <-- Use the new variable here
                options=q.get("options"),
                type=Poll.QUIZ,
                correct_option_id=q.get("correctIndex", 0),
                open_period=session["time_per_question_sec"],
                is_anonymous=False,
                explanation=explanation
            )
            break # Success
# ... (rest of the function)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to send group poll: {e}")
            if attempt < 2:
                await asyncio.sleep(2)
            else:
                print("All retries failed for group poll. Finalizing quiz.")
                await group_finalize_and_export(bot, session_key)
                return
    
    if not sent: # Should not be reached, but as a safeguard
        return

    session["poll_id"] = sent.poll.id
    session["message_id"] = sent.message_id if hasattr(sent, 'message_id') else None
    POLL_ID_TO_SESSION_MAP[sent.poll.id] = {"type": "group", "key": session_key}
    await write_session_file(path, session, lock)
    
    old_task = running_group_tasks.pop(session_key, None)
    if old_task:
        old_task.cancel()
    async def per_question_timeout():
        try:
            await asyncio.sleep(session["time_per_question_sec"] + 2)
            fresh_session = await read_session_file(path, lock)
            if fresh_session and fresh_session["current_q"] == qidx:
                await group_reveal_and_advance(bot, session_key, qidx, timed_out=True)
        except asyncio.CancelledError:
            pass
    running_group_tasks[session_key] = asyncio.create_task(per_question_timeout())

async def group_reveal_and_advance(bot, session_key, qidx, timed_out=False):
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return
    
    if session.get("poll_id"):
        POLL_ID_TO_SESSION_MAP.pop(session["poll_id"], None)

    session["current_q"] += 1
    await write_session_file(path, session, lock)
    if session["current_q"] >= len(session["questions"]):
        await group_finalize_and_export(bot, session_key)
        return
    await group_send_question(bot, session_key)

async def group_finalize_and_export(bot, session_key):
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
            elif ans != -1:
                score -= negative
        if score < 0: score = 0.0
        duration = p_data.get("end_time", p_data.get("start_time", 0)) - p_data.get("start_time", 0)
        results.append({
            "name": p_data.get("username", str(user_id_str)),
            "score": score,
            "duration": duration
        })
    results.sort(key=lambda x: (x["score"], -x["duration"]), reverse=True)
    quiz_title = session.get("title", f"Quiz {quiz_id}")
    msg_lines = [f"🏁 The quiz '{quiz_title}' has finished!", f"\n{total_questions} questions answered\n"]
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
        # Send the result message
        await bot.send_message(chat_id, final_message)

        # Generate and send the HTML file
        total_quiz_time_sec = len(session["questions"]) * session.get("time_per_question_sec", 30)
        
        quiz_settings = {
            "totalTimeSec": total_quiz_time_sec,
            "negativeMark": session.get("negative", 0.0)
        }

        html_path = await generate_quiz_html(
            quiz_settings,
            session["questions"]
        )
        if html_path:
            try:
                await bot.send_document(
                    chat_id,
                    document=open(html_path, "rb"),
                    caption="Practice this quiz again with the attached HTML file.",
                    filename=f"{quiz_id}_practice.html"
                )
            finally:
                os.remove(html_path) # Always clean up the temp file
    
    except Exception as e:
        print(f"Error sending final group results or HTML: {e}")
    
    await delete_session_file(path, session_key, group_session_locks, running_group_tasks)
# --- BACKUP & RESTORE ---
async def backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = await update.effective_message.reply_text("Starting backup process...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # 1. Copy database
            shutil.copy(DB_PATH, os.path.join(tmpdir, "quizzes.db"))

            # 2. Get all unique image file_ids
            q_rows = db_execute("SELECT q_json FROM questions WHERE q_json LIKE '%image_file_id%'", commit=False).fetchall()
            unique_file_ids = set()
            for row in q_rows:
                q_obj = json.loads(row["q_json"])
                if "image_file_id" in q_obj:
                    unique_file_ids.add(q_obj["image_file_id"])

            # 3. Download images and create map
            image_map = {}
            if unique_file_ids:
                images_dir = os.path.join(tmpdir, "images")
                os.makedirs(images_dir)
                await msg.edit_text(f"Backing up database and {len(unique_file_ids)} images...")
                for i, file_id in enumerate(unique_file_ids):
                    try:
                        file = await context.bot.get_file(file_id)
                        filename = f"{i}.jpg"
                        await file.download_to_drive(os.path.join(images_dir, filename))
                        image_map[file_id] = filename
                    except Exception as e:
                        print(f"Could not download file_id {file_id}: {e}")

            if image_map:
                with open(os.path.join(tmpdir, "image_map.json"), "w") as f:
                    json.dump(image_map, f)
            
            # 4. Create zip file
            zip_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = shutil.make_archive(zip_filename, 'zip', tmpdir)

            # 5. Send to owner
            await update.effective_message.reply_document(
                document=open(zip_path, "rb"),
                caption="Here is your backup file."
            )
            await msg.delete()

        except Exception as e:
            await msg.edit_text(f"❌ Backup failed: {e}")
            traceback.print_exc()
        finally:
            if 'zip_path' in locals() and os.path.exists(zip_path):
                os.remove(zip_path)

async def restore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global db
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("Please use this command when replying to a backup `.zip` file.")
        return
    doc = msg.reply_to_message.document
    if not doc.file_name.lower().endswith(".zip"):
        await msg.reply_text("The replied file is not a `.zip` file.")
        return
    
    status_msg = await msg.reply_text("Starting restore process... Do not interrupt.")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # 1. Download and extract zip
            zip_file = await doc.get_file()
            zip_path = os.path.join(tmpdir, "backup.zip")
            await zip_file.download_to_drive(zip_path)
            
            extract_dir = os.path.join(tmpdir, "extracted")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # 2. Validate extracted files
            restored_db_path = os.path.join(extract_dir, "quizzes.db")
            if not os.path.exists(restored_db_path):
                raise FileNotFoundError("`quizzes.db` not found in the backup.")

            # 3. Backup current DB and replace
            db.close() # Close current connection
            if os.path.exists(DB_PATH):
                shutil.move(DB_PATH, f"{DB_PATH}.{int(time.time())}.bak")
            shutil.move(restored_db_path, DB_PATH)
            
            # Re-initialize global DB connection
            db = init_db()

            await status_msg.edit_text("Database restored. Now re-uploading images...")
            
            # 4. Re-upload images and update DB
            image_map_path = os.path.join(extract_dir, "image_map.json")
            if os.path.exists(image_map_path):
                with open(image_map_path, 'r') as f:
                    image_map = json.load(f)
                
                new_id_map = {}
                total_images = len(image_map)
                for i, (old_id, filename) in enumerate(image_map.items()):
                    await status_msg.edit_text(f"Re-uploading image {i+1}/{total_images}...")
                    image_path = os.path.join(extract_dir, "images", filename)
                    if os.path.exists(image_path):
                        with open(image_path, "rb") as photo_file:
                            sent_photo = await context.bot.send_photo(OWNER_ID, photo_file)
                            new_id_map[old_id] = sent_photo.photo[-1].file_id

                # Update questions in the new DB
                if new_id_map:
                    await status_msg.edit_text("Updating image references in the database...")
                    q_rows = db_execute("SELECT id, q_json FROM questions WHERE q_json LIKE '%image_file_id%'", commit=False).fetchall()
                    for q_row in q_rows:
                        q_obj = json.loads(q_row['q_json'])
                        if 'image_file_id' in q_obj and q_obj['image_file_id'] in new_id_map:
                            q_obj['image_file_id'] = new_id_map[q_obj['image_file_id']]
                            new_json = json.dumps(q_obj)
                            db_execute("UPDATE questions SET q_json = ? WHERE id = ?", (new_json, q_row['id']))

            await status_msg.edit_text("✅ Restore complete!")

        except Exception as e:
            await status_msg.edit_text(f"❌ Restore failed: {e}")
            traceback.print_exc()

# --- SCHEDULING ---
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Scheduling only works in groups.")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/schedule <quiz_id>`")
        return
    
    quiz_id = context.args[0]
    q_row = db_execute("SELECT id FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not q_row:
        await update.message.reply_text(f"Quiz with ID `{quiz_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return
    
    chat_id = chat.id
    user_id = update.effective_user.id
    key = (chat_id, user_id, "schedule")
    ongoing_sessions[key] = {"quiz_id": quiz_id, "step": "time"}
    await update.message.reply_text("Please provide the start time in **24-hour HH:MM format** (Indian Standard Time).", parse_mode=ParseMode.MARKDOWN)

async def schedule_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type == 'private':
        return
    
    user_id = update.effective_user.id
    chat_id = chat.id
    key = (chat_id, user_id, "schedule")

    if key in ongoing_sessions:
        state = ongoing_sessions[key]
        if state.get("step") == "time":
            time_str = update.message.text.strip()
            try:
                hour, minute = map(int, time_str.split(':'))
                
                IST = pytz.timezone('Asia/Kolkata')
                now_ist = datetime.now(IST)
                
                scheduled_time_ist = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if scheduled_time_ist <= now_ist:
                    scheduled_time_ist += timedelta(days=1)
                
                scheduled_time_utc = scheduled_time_ist.astimezone(pytz.utc)
                quiz_id = state['quiz_id']
                
                # Save to DB
                cur = db_execute("INSERT INTO schedule (chat_id, quiz_id, creator_id, scheduled_time_utc, status) VALUES (?, ?, ?, ?, 'pending')",
                                 (chat_id, quiz_id, user_id, scheduled_time_utc.isoformat()))
                schedule_id = cur.lastrowid
                
                # Schedule jobs
                schedule_quiz_jobs(context.job_queue, schedule_id, chat_id, quiz_id, scheduled_time_utc)
                
                await update.message.reply_text(f"✅ Quiz `{quiz_id}` scheduled for {scheduled_time_ist.strftime('%Y-%m-%d %H:%M')} IST.")
                
            except ValueError:
                await update.message.reply_text("Invalid time format. Please use HH:MM (e.g., 14:30).")
            except Exception as e:
                await update.message.reply_text(f"An error occurred: {e}")
            finally:
                del ongoing_sessions[key]

def schedule_quiz_jobs(job_queue: JobQueue, schedule_id: int, chat_id: int, quiz_id: str, scheduled_time_utc: datetime):
    now_utc = datetime.now(pytz.utc)

    # Schedule Start Job
    start_delta = (scheduled_time_utc - now_utc).total_seconds()
    if start_delta > 0:
        job_queue.run_once(
            schedule_start_callback,
            start_delta,
            data={"chat_id": chat_id, "quiz_id": quiz_id, "schedule_id": schedule_id},
            name=f"start_{schedule_id}"
        )

    # Schedule Alert Job (5 mins before)
    alert_time_utc = scheduled_time_utc - timedelta(minutes=5)
    alert_delta = (alert_time_utc - now_utc).total_seconds()
    if alert_delta > 0:
        job_queue.run_once(
            schedule_alert_callback,
            alert_delta,
            data={"chat_id": chat_id, "quiz_id": quiz_id, "schedule_id": schedule_id},
            name=f"alert_{schedule_id}"
        )

async def schedule_alert_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, quiz_id = job.data['chat_id'], job.data['quiz_id']
    q_row = db_execute("SELECT title FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    title = q_row['title'] if q_row else quiz_id
    await context.bot.send_message(chat_id, f"⏰ Reminder: Quiz '{title}' will start in 5 minutes!")

async def schedule_start_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, quiz_id, schedule_id = job.data['chat_id'], job.data['quiz_id'], job.data['schedule_id']
    
    # Update status in DB
    db_execute("UPDATE schedule SET status = 'triggered' WHERE id = ?", (schedule_id,))
    
    await start_quiz_in_group(context.bot, chat_id, quiz_id, starter_id=None)

async def load_schedules_on_startup(application: Application):
    """Reschedule pending jobs from the database when the bot starts."""
    print("Loading pending schedules from database...")
    job_queue = application.job_queue
    cur = db_execute("SELECT * FROM schedule WHERE status = 'pending'", commit=False)
    now_utc = datetime.now(pytz.utc)
    count = 0
    for row in cur.fetchall():
        try:
            scheduled_utc = datetime.fromisoformat(row['scheduled_time_utc']).replace(tzinfo=pytz.utc)
            if scheduled_utc > now_utc:
                schedule_quiz_jobs(job_queue, row['id'], row['chat_id'], row['quiz_id'], scheduled_utc)
                count += 1
            else:
                # Mark past-due jobs as errored/missed
                db_execute("UPDATE schedule SET status = 'missed' WHERE id = ?", (row['id'],))
        except Exception as e:
            print(f"Failed to load schedule {row['id']}: {e}")
            db_execute("UPDATE schedule SET status = 'error' WHERE id = ?", (row['id'],))
    print(f"Successfully re-scheduled {count} pending jobs.")

# --- MAIN BOT SETUP ---
def main():
    # Explicitly create a JobQueue
    job_queue = JobQueue()
    # Pass the JobQueue instance to the application builder
    app = Application.builder().token(BOT_TOKEN).job_queue(job_queue).build()
    
    # Command Handlers
    app.add_handler(CommandHandler(["start", "help"], start_handler))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("done", done_command_handler))
    app.add_handler(CommandHandler("no_images", no_images_command_handler))
    app.add_handler(CommandHandler("myquizzes", myquizzes_handler))
    app.add_handler(CommandHandler("take", take_handler))
    app.add_handler(CommandHandler("post", post_command))
    app.add_handler(CommandHandler("finish", finish_command_handler))
    app.add_handler(CommandHandler("backup", backup_handler))
    app.add_handler(CommandHandler("restore", restore_handler))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    
    # Message Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, create_flow_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, schedule_flow_handler))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(view_quiz_cb, pattern=r"^viewquiz:"))
    app.add_handler(CallbackQueryHandler(delete_quiz_cb, pattern=r"^deletequiz:"))
    app.add_handler(CallbackQueryHandler(export_quiz_cb, pattern=r"^exportquiz:"))
    app.add_handler(CallbackQueryHandler(postcard_cb, pattern=r"^postcard:"))
    app.add_handler(CallbackQueryHandler(start_private_cb, pattern=r"^startprivate:"))
    app.add_handler(CallbackQueryHandler(start_group_cb, pattern=r"^startgroup:"))
    
    # Poll Handlers
    app.add_handler(PollAnswerHandler(poll_answer_handler))
    app.add_handler(PollHandler(poll_update_handler))
    
    # Load schedules on startup
    app.post_init = load_schedules_on_startup

    print("Starting PTB Quiz Bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
