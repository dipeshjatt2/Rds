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
import shutil
import logging
import threading  # Required to run both services
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any

# --- Flask Import ---
from flask import Flask

# --- Aiogram Imports ---
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    PollAnswer,
    Poll,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Document,
    FSInputFile,
    BufferedInputFile
)
from aiogram.enums import ParseMode

# --- Flask App Definition (Script 1) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def hello_world():
    return 'Tech VJ'

def run_flask():
    """Runs the Flask app in a separate thread."""
    print("Starting Flask server on http://0.0.0.0:5000...")
    # Using 0.0.0.0 to make it accessible on the network
    flask_app.run(host='0.0.0.0', port=5000)


# --- Aiogram Bot Script (Script 2) ---

# --- Original Bot Config ---
BOT_TOKEN = os.environ.get("BOOK")
OWNER_ID = 5203820046  # Original script set this, but also had logic to auto-set if 0
DB_PATH = "quizzes.db"
SESSION_DIR = "sessions"
os.makedirs(SESSION_DIR, exist_ok=True)

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN env var required. Please set it in your environment.")

# --- Database & Parsing Logic (UNCHANGED) ---
# All your database functions (init_db, db_execute, get_creator...) and
# all your parsing functions (parse_format2_enhanced, parse_csv, detect_and_parse_strict...)
# remain identical. They are pure Python and not framework-dependent.

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
        subject TEXT,
        section TEXT,
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

def db_execute(query, params=(), commit=True):
    cur = db.cursor()
    cur.execute(query, params)
    if commit:
        db.commit()
    return cur

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

def questions_to_json(qs):
    return json.dumps(qs, ensure_ascii=False)

def questions_from_json(s):
    return json.loads(s)

def get_creator_by_tg(tg_user_id):
    cur = db_execute("SELECT * FROM creators WHERE tg_user_id = ?", (tg_user_id,), commit=False)
    return cur.fetchone()

def get_or_create_creator_by_tg(user: types.User):
    c = db_execute("SELECT * FROM creators WHERE tg_user_id = ?", (user.id,), commit=False).fetchone()
    if c:
        return c
    username = user.username or ""
    display_name = (user.full_name or "").strip()
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


# --- Global Session Management (UNCHANGED) ---
# This complex logic is framework-agnostic and is ported directly.
# Helper functions that need the Bot object will now accept it as a parameter.
running_group_tasks: Dict[Tuple[int,str], asyncio.Task] = {}
private_session_locks: Dict[Tuple[int,int], asyncio.Lock] = {}
group_session_locks: Dict[Tuple[int,str], asyncio.Lock] = {}
POLL_ID_TO_SESSION_MAP: Dict[str, Dict[str, Any]] = {}

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


# --- Aiogram Dispatcher and FSM States ---
dp = Dispatcher()

class CreateQuizState(StatesGroup):
    title = State()
    subject = State()
    section = State()
    time_per_q = State()
    negative = State()
    questions = State()


# --- Aiogram Handlers ---

@dp.message(Command("start", "help"))
async def start_handler(message: Message):
    user = message.from_user
    uid = user.id
    uname = user.username or ""
    fullname = user.full_name or ""
    if OWNER_ID == 0:
        ensure_owner_exists(uid, uname, fullname)
    text = (
        "👋 **Welcome to QuizMaster Bot!**\n\n"
        "Available commands:\n"
        "• /create - Create a quiz interactively\n"
        "• /bulkupload - Upload a .zip of .txt quizzes\n"
        "• /myquizzes - List quizzes you created\n"
        "• /take <quiz_id> - Start a timed quiz (private)\n"
        "• /post <quiz_id> - Post/share a quiz card into the chat\n"
        "• /finish - Finish your active private quiz early\n"
        "• /finish <quiz_id> - (In groups) Finish a specific quiz (admins only)\n\n"
        "Create and play quizzes using Telegram’s built-in quiz polls."
    )
    await message.reply(text)

# --- Create Quiz FSM Flow ---

@dp.message(Command("create"), StateFilter(None))
async def create_command(message: Message, state: FSMContext):
    if message.chat.type != 'private':
        await message.reply("Quiz creation is only available in private chat.")
        return
    await state.set_state(CreateQuizState.title)
    await message.reply("✍️ Creating a new quiz. Send the *Quiz Title*:")

@dp.message(CreateQuizState.title, F.text)
async def handle_create_title(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.reply("Please send valid text for the title.")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateQuizState.subject)
    await message.reply("Saved title. Now send the *subject* (e.g., Math, Physics):")

@dp.message(CreateQuizState.subject, F.text)
async def handle_create_subject(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.reply("Please send valid text for the subject.")
        return
    await state.update_data(subject=message.text.strip())
    await state.set_state(CreateQuizState.section)
    await message.reply("Saved subject. Now send the *section* or category (optional; send '-' for none):")

@dp.message(CreateQuizState.section, F.text)
async def handle_create_section(message: Message, state: FSMContext):
    if not message.text:
        return
    text = message.text.strip()
    await state.update_data(section="" if text == "-" else text)
    await state.set_state(CreateQuizState.time_per_q)
    await message.reply("Saved section. Now send **time per question in seconds** (integer):")

@dp.message(CreateQuizState.time_per_q, F.text)
async def handle_create_time(message: Message, state: FSMContext):
    try:
        secs = int(message.text.strip())
        if secs <= 0:
            raise ValueError
        await state.update_data(time_per_question_sec=secs)
    except Exception:
        await message.reply("❌ Please send a valid positive integer for seconds.")
        return
    await state.set_state(CreateQuizState.negative)
    await message.reply("Saved time. Now send **negative marks per wrong answer** (e.g., `0.25` or `0` for none):")

@dp.message(CreateQuizState.negative, F.text)
async def handle_create_negative(message: Message, state: FSMContext):
    try:
        neg = float(message.text.strip())
        if neg < 0:
            raise ValueError
        await state.update_data(negative=neg)
    except Exception:
        await message.reply("❌ Please send a valid non-negative number for negative marks (e.g., 0.25).")
        return
    await state.set_state(CreateQuizState.questions)
    await state.update_data(questions=[]) # Initialize empty list
    await message.reply(
        "Now send questions one by one in this exact format OR upload a `.txt` file with many questions in the same format:\n\n"
        "1. [4/50] Question text (can be multiple lines)\n"
        "(a) option1 (can be multiple lines)\n"
        "(b) option2 ✅\n"
        "(c) option3\n"
        "Ex: Optional explanation text (can be multiple lines)\n\n"
        "Send /done when finished."
    )

@dp.message(CreateQuizState.questions, F.text)
async def handle_questions_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "/done":
        state_data = await state.get_data()
        questions = state_data.get("questions", [])
        if not questions:
            await message.reply("❌ No questions found. Send at least one question in the required format or upload a .txt file.")
            return
        
        creator = get_or_create_creator_by_tg(message.from_user)
        quiz_id = generate_quiz_id()
        time_per_q = state_data.get('time_per_question_sec', 30)
        negative = state_data.get('negative', 0.0)
        
        db_execute("INSERT INTO quizzes (id, title, subject, section, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (quiz_id, state_data["title"], state_data["subject"], state_data["section"], creator["id"], 0, time_per_q, negative, datetime.utcnow().isoformat()))
        
        for idx, q in enumerate(questions):
            db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
        
        await state.clear()
        await message.reply(f"✅ Quiz created with id `{quiz_id}` (time per question: {time_per_q}s, negative: {negative})")
        return

    # If not /done, parse as a question
    parsed = parse_format2_enhanced(text)
    if not parsed:
        await message.reply("❌ Could not parse the question. Make sure it exactly matches the required format (numbered, (a) options, and one ✅).")
        return

    state_data = await state.get_data()
    all_questions = state_data.get("questions", []) + parsed
    await state.update_data(questions=all_questions)
    await message.reply(f"✅ Saved {len(parsed)} question(s). Total so far: {len(all_questions)}. Send next or /done.")

# This handler specifically catches documents ONLY during the 'questions' state
@dp.message(CreateQuizState.questions, F.document)
async def handle_questions_document(message: Message, state: FSMContext, bot: Bot):
    file_id = message.document.file_id
    file_name = (message.document.file_name or "").lower()
    temp_path = f"temp_{file_id}"

    try:
        await bot.download(message.document, destination=temp_path)

        parsed = []
        if file_name.endswith(".txt"):
            with open(temp_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                data = f.read()
            parsed = detect_and_parse_strict(data)
            if not parsed:
                await message.reply("❌ The .txt file did not match any of the required formats or was invalid. Please fix and resend.")
                return
        
        elif file_name.endswith(".csv"):
            parsed = parse_csv(temp_path)
            if not parsed:
                await message.reply("❌ CSV parsing failed.")
                return
        
        else:
            await message.reply("❌ Invalid file type. Please send a `.txt` or `.csv` file.")
            return

        state_data = await state.get_data()
        all_questions = state_data.get("questions", []) + parsed
        await state.update_data(questions=all_questions)
        await message.reply(f"✅ Imported {len(parsed)} questions from the file. Total so far: {len(all_questions)}. Send more or /done.")
    
    except Exception as e:
        await message.reply(f"❌ Error processing file: {e}")
        traceback.print_exc()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# --- Bulk Upload Handlers ---

@dp.message(Command("bulkupload"))
async def bulkupload_command(message: Message):
    await message.reply("✅ Send a `.zip` file containing `.txt` or `.csv` files (each file must be in one of the supported formats).")

# This handler catches documents ONLY when NO state is active
@dp.message(F.document, StateFilter(None))
async def handle_bulk_document(message: Message, bot: Bot):
    file_id = message.document.file_id
    file_name = (message.document.file_name or "").lower()
    temp_path = f"temp_bulk_{file_id}"
    user_id = message.from_user.id
    creator = get_or_create_creator_by_tg(message.from_user)

    try:
        await bot.download(message.document, destination=temp_path)
        
        if file_name.endswith(".csv"):
            parsed = parse_csv(temp_path)
            if not parsed:
                await message.reply(f"❌ Failed to parse {file_name}: CSV format error or empty.")
                return
            title = os.path.splitext(os.path.basename(file_name))[0]
            quiz_id = generate_quiz_id()
            db_execute("INSERT INTO quizzes (id, title, subject, section, creator_id, total_time_min, time_per_question_sec, negative_mark, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                (quiz_id, title, "", "", creator["id"], 0, 30, 0.0, datetime.utcnow().isoformat()))
            for idx, q in enumerate(parsed):
                db_execute("INSERT INTO questions (quiz_id, idx, q_json) VALUES (?,?,?)", (quiz_id, idx, questions_to_json(q)))
            await message.reply(f"✅ CSV Upload: Created 1 quiz ({title}) with {len(parsed)} questions. ID: `{quiz_id}`")
            return
        
        if file_name.endswith(".zip"):
            created = 0
            errors = []
            with zipfile.ZipFile(temp_path, "r") as z:
                temp_zip_dir = f"temp_zip_{user_id}"
                os.makedirs(temp_zip_dir, exist_ok=True)
                for fname_in_zip in z.namelist():
                    if fname_in_zip.startswith("__MACOSX"):
                        continue
                    fname_lower = fname_in_zip.lower()
                    parsed = []
                    title = os.path.splitext(os.path.basename(fname_in_zip))[0]
                    try:
                        if fname_lower.endswith(".txt"):
                            data = z.read(fname_in_zip).decode("utf-8-sig", errors="ignore")
                            parsed = detect_and_parse_strict(data)
                        elif fname_lower.endswith(".csv"):
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
                try:
                    shutil.rmtree(temp_zip_dir)
                except:
                    pass
            await message.reply(f"✅ Bulk upload finished. Created {created} quizzes.\nErrors: {errors[:10]}")
            return
    
    except Exception as e:
        await message.reply(f"❌ Error processing document: {e}")
        traceback.print_exc()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --- General Command Handlers ---

@dp.message(Command("myquizzes"))
async def myquizzes_handler(message: Message):
    uid = message.from_user.id
    c = get_creator_by_tg(uid)
    if not c:
        await message.reply("You haven't created any quizzes yet. Use /create to start.")
        return
    cur = db_execute("SELECT * FROM quizzes WHERE creator_id = ? ORDER BY created_at DESC", (c["id"],), commit=False)
    rows = cur.fetchall()
    if not rows:
        await message.reply("You have no quizzes yet.")
        return
    text_lines = []
    kb_buttons = []
    for r in rows:
        p = r['subject'] or '-'
        tp = r['time_per_question_sec'] or '-'
        text_lines.append(f"ID: {r['id']} | {r['title']} | Subject: {p} | Time/q: {tp}s | Neg: {r['negative_mark']}")
        kb_buttons.append([InlineKeyboardButton(text=f"{r['id']}: {r['title']}", callback_data=f"viewquiz:{r['id']}")])
    
    await message.reply("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))

@dp.message(Command("post"))
async def post_command(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: /post <quiz_id>")
        return
    quiz_id = args[1].strip()
    await post_quiz_card(bot, message.chat.id, quiz_id)

@dp.message(Command("take"))
async def take_handler(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: /take <quiz_id>")
        return
    quiz_id = args[1].strip()
    await take_quiz_private(bot, message.from_user.id, quiz_id)

@dp.message(Command("finish"))
async def finish_command_handler(message: Message, bot: Bot):
    chat = message.chat
    user_id = message.from_user.id
    
    if chat.type == 'private':
        active_sessions = glob.glob(os.path.join(SESSION_DIR, f"private_{user_id}_*.json"))
        if not active_sessions:
            await message.reply("You have no active quiz to finish.")
            return
        session_path = active_sessions[0]
        filename = os.path.basename(session_path)
        try:
            parts = filename.replace("private_", "").replace(".json", "").split("_")
            uid = int(parts[0])
            attempt_id = int(parts[1])
            session_key = (uid, attempt_id)
        except Exception:
            await message.reply("Error identifying your session file. Could not finish.")
            if os.path.exists(session_path): os.remove(session_path)
            return
        
        lock = get_private_lock(session_key)
        session_data = await read_session_file(session_path, lock)
        if not session_data:
            await message.reply("Could not read your session data. Cleaning up.")
            await delete_session_file(session_path, session_key, private_session_locks)
            return
        
        await message.reply("Finishing your quiz now and calculating results...")
        await finalize_attempt(bot, session_key, session_data)
        
    else: # Group chat
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply(
                "In a group, you must specify which quiz to finish.\n"
                "Usage: `/finish <quiz_id>`\n"
                "(Only admins or the quiz starter can do this.)"
            )
            return
            
        quiz_id = args[1].strip()
        chat_id = chat.id
        session_key = (chat_id, quiz_id)
        session_path = get_group_session_path(chat_id, quiz_id)

        if not os.path.exists(session_path):
            await message.reply(f"No active quiz found in this chat with ID: `{quiz_id}`")
            return

        try:
            admins = await bot.get_chat_administrators(chat_id)
            admin_ids = {admin.user.id for admin in admins}
        except Exception:
            admin_ids = set()

        lock = get_group_lock(session_key)
        session_data = await read_session_file(session_path, lock)
        starter_id = session_data.get("starter_id") if session_data else None
        
        if user_id == starter_id or user_id in admin_ids or user_id == OWNER_ID:
            await message.reply(f"Force-finishing quiz `{quiz_id}` and calculating results...")
            await group_finalize_and_export(bot, session_key)
        else:
            await message.reply("You do not have permission. Only chat admins or the person who started the quiz can finish it.")


# --- Callback Query Handlers ---

@dp.callback_query(F.data.startswith("viewquiz:"))
async def view_quiz_cb(query: CallbackQuery):
    quiz_id = query.data.split(":", 1)[1]
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        await query.answer("Quiz not found", show_alert=True)
        return
    creator = db_execute("SELECT * FROM creators WHERE id = ?", (qrow["creator_id"],), commit=False).fetchone()
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    preview = []
    for i, qr in enumerate(qrows[:10], start=1):
        qobj = questions_from_json(qr["q_json"])
        preview.append(f"{i}. {qobj.get('text','')}\n  a) {qobj.get('options',[None])[0] if qobj.get('options') else ''}")
    txt = (f"Quiz ID: {quiz_id}\nTitle: {qrow['title']}\nSubject: {qrow['subject']}\nSection: {qrow['section']}\n"
           f"Creator: {creator['username'] or creator['display_name']}\nQuestions: {len(qrows)}\n\nPreview:\n" + "\n".join(preview))
    kb_buttons = [
        [InlineKeyboardButton(text="Delete", callback_data=f"deletequiz:{quiz_id}"), 
         InlineKeyboardButton(text="Export", callback_data=f"exportquiz:{quiz_id}")],
        [InlineKeyboardButton(text="Share (post card)", callback_data=f"postcard:{quiz_id}")]
    ]
    await query.message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await query.answer()

@dp.callback_query(F.data.startswith("deletequiz:"))
async def delete_quiz_cb(query: CallbackQuery):
    uid = query.from_user.id
    quiz_id = query.data.split(":", 1)[1]
    q = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not q:
        await query.answer("Not found", show_alert=True)
        return
    creator = get_creator_by_tg(uid)
    if not creator or (creator["is_admin"] != 1 and creator["id"] != q["creator_id"]):
        await query.answer("No permission", show_alert=True)
        return
    db_execute("DELETE FROM questions WHERE quiz_id = ?", (quiz_id,))
    db_execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
    await query.answer("Deleted", show_alert=True)
    await query.message.reply(f"✅ Quiz {quiz_id} deleted.")
    try:
        await query.message.delete() # Clean up the message with the buttons
    except:
        pass

@dp.callback_query(F.data.startswith("exportquiz:"))
async def export_quiz_cb(query: CallbackQuery):
    quiz_id = query.data.split(":", 1)[1]
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        await query.answer("No questions", show_alert=True)
        return
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
    
    # Use BufferedInputFile for aiogram
    bio = io.BytesIO(content.encode("utf-8"))
    file_to_send = BufferedInputFile(bio.read(), filename=f"quiz_{quiz_id}.txt")
    
    await query.message.reply_document(file_to_send, caption=f"Exported quiz {quiz_id}")
    await query.answer()

@dp.callback_query(F.data.startswith("postcard:"))
async def postcard_cb(query: CallbackQuery, bot: Bot):
    quiz_id = query.data.split(":", 1)[1]
    await post_quiz_card(bot, query.message.chat.id, quiz_id)
    await query.answer()

@dp.callback_query(F.data.startswith("startprivate:"))
async def start_private_cb(query: CallbackQuery, bot: Bot):
    quiz_id = query.data.split(":", 1)[1]
    uid = query.from_user.id
    try:
        await bot.send_message(uid, "Starting quiz in private for you...")
        await take_quiz_private(bot, uid, quiz_id)
        await query.answer("Starting quiz in private...")
    except Exception as e:
        logging.error(f"Failed to start private quiz: {e}")
        await query.answer("❌ Failed to start in private. Have you started/unblocked me?", show_alert=True)

@dp.callback_query(F.data.startswith("startgroup:"))
async def start_group_cb(query: CallbackQuery, bot: Bot):
    quiz_id = query.data.split(":", 1)[1]
    chat_id = query.message.chat.id
    await start_quiz_in_group(bot, chat_id, quiz_id, starter_id=query.from_user.id)
    await query.answer("Starting quiz in this chat...")

# --- Poll Handlers ---

@dp.poll_answer()
async def poll_answer_handler(answer: PollAnswer, bot: Bot):
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
            
            # This logic was slightly different in PTB. We'll stick to the original's
            # intent which seemed to be "advance when the poll closes", not on answer.
            # But the PTB script *DID* call reveal_correct... here. Let's keep it.
            await reveal_correct_and_advance_private(bot, session_key, qidx, chosen_idx=chosen)
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
                user_full_name = user.full_name or str(user_id)
                p_data = {
                    "answers": [-1] * len(session["questions"]),
                    "start_time": time.time(),
                    "username": user_full_name
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

@dp.poll()
async def poll_update_handler(poll: Poll, bot: Bot):
    if not poll.is_closed:
        return
    
    mapping = POLL_ID_TO_SESSION_MAP.get(poll.id)
    if not mapping:
        return

    session_type = mapping.get("type")
    session_key = mapping.get("key")

    if session_type == "private":
        path = get_private_session_path(*session_key)
        lock = get_private_lock(session_key)
        session = await read_session_file(path, lock)

        if not session:
            return

        if session.get("poll_id") == poll.id:
            # Check if an answer was already recorded by PollAnswerHandler
            if session["answers"][session["current_q"]] == -1:
                # If not, it means timeout, advance without an answer
                await reveal_correct_and_advance_private(bot, session_key, session["current_q"], timed_out=True)
            # If an answer was recorded, reveal_and_advance was already called by poll_answer_handler
            # In the original script, it seems both could run. Let's stick to the original logic.
            # The original PollHandler *also* called reveal_and_advance.
            # To prevent double-advancing, we must check if we are still on the *same* question.
            
            fresh_session = await read_session_file(path, lock) # re-read
            if fresh_session and fresh_session["current_q"] == session["current_q"]:
                 await reveal_correct_and_advance_private(bot, session_key, session["current_q"], timed_out=True)
    
    elif session_type == "group":
        # Group logic is handled by the asyncio.sleep timer task (per_question_timeout)
        # This handler isn't strictly needed for group flow as defined in original script.
        pass


# --- Core Quiz Logic Helpers (Updated to accept Bot object) ---

async def post_quiz_card(bot: Bot, chat_id: int, quiz_id: str):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await bot.send_message(chat_id, "Quiz not found.")
        except:
            pass
        return
    qs_cur = db_execute("SELECT COUNT(*) as cnt FROM questions WHERE quiz_id = ?", (quiz_id,), commit=False)
    total_q = qs_cur.fetchone()["cnt"]
    title = qrow["title"] or f"Quiz {quiz_id}"
    time_per_q = qrow['time_per_question_sec'] or 30
    negative_marking = qrow['negative_mark']
    base_lines = [
        f"💳 Quiz Name: `{title}`",
        f"#️⃣ Questions: {total_q}",
        f"⏰ Timer: {time_per_q} seconds",
        f"🆔 Quiz ID: `{quiz_id}`",
        f"🏴‍☠️ -ve Marking: {negative_marking}",
        "💰 Type: free"
    ]
    creator_mention_line = ""
    if qrow['creator_id']:
        creator_row = db_execute("SELECT * FROM creators WHERE id = ?", (qrow['creator_id'],), commit=False).fetchone()
        if creator_row:
            if creator_row['username']:
                creator_mention_line = f"Created by: @{creator_row['username']}"
            elif creator_row['display_name']:
                 creator_mention_line = f"Created by: {creator_row['display_name']}"
    if creator_mention_line:
        base_lines.append(creator_mention_line)
    base_lines.append("\nTap start to play!")
    text = "\n".join(base_lines)
    
    kb_buttons = [
        [InlineKeyboardButton(text="Start this quiz (in this chat)", callback_data=f"startgroup:{quiz_id}")],
        [InlineKeyboardButton(text="Start in private", callback_data=f"startprivate:{quiz_id}")]
    ]
    await bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))


async def take_quiz_private(bot: Bot, user_id: int, quiz_id: str):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await bot.send_message(user_id, "Quiz not found.")
        except: pass
        return
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        try:
            await bot.send_message(user_id, "No questions in quiz.")
        except: pass
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

async def send_question_for_session_private(bot: Bot, session_key: Tuple[int, int]):
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

    explanation = q.get("explanation") or None

    try:
        sent_poll = await bot.send_poll(
            chat_id=session["chat_id"],
            question=q.get("text"),
            options=q.get("options"),
            type='quiz', # Using string literal as per aiogram
            correct_option_id=q.get("correctIndex", 0),
            open_period=session["time_per_question_sec"],
            is_anonymous=False,
            explanation=explanation
        )
        
        session['poll_id'] = sent_poll.poll.id
        session['message_id'] = sent_poll.message_id
        
        POLL_ID_TO_SESSION_MAP[sent_poll.poll.id] = {"type": "private", "key": session_key}

        await write_session_file(path, session, lock)
    except Exception as e:
        print(f"Failed to send private poll: {e}")
        await finalize_attempt(bot, session_key, session)
        return

async def reveal_correct_and_advance_private(bot: Bot, session_key: Tuple[int, int], qidx: int, chosen_idx=None, timed_out=False):
    path = get_private_session_path(*session_key)
    lock = get_private_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return
    
    # Ensure we are only advancing ONCE for this question index
    if session["current_q"] != qidx:
        # Already advanced, possibly by a race condition between poll_answer and poll_update
        return

    if session.get("poll_id"):
        POLL_ID_TO_SESSION_MAP.pop(session["poll_id"], None)
        # Attempt to stop the poll (Telegram doesn't always reflect this instantly)
        try:
            await bot.stop_poll(session["chat_id"], session["message_id"])
        except:
            pass

    session["current_q"] += 1
    await write_session_file(path, session, lock)
    
    if session["current_q"] >= len(session["questions"]):
        await finalize_attempt(bot, session_key, session)
        return
        
    await send_question_for_session_private(bot, session_key)

async def finalize_attempt(bot: Bot, session_key: Tuple[int, int], session_data: dict):
    total = 0.0
    maxscore = len(session_data["questions"])
    quiz_row = db_execute("SELECT * FROM quizzes WHERE id = ?", (session_data["quiz_id"],), commit=False).fetchone()
    negative = quiz_row["negative_mark"] if quiz_row else 0.0
    for idx, q in enumerate(session_data["questions"]):
        correct = q.get("correctIndex", -1)
        ans = session_data["answers"][idx]
        if ans == correct and correct != -1:
            total += 1.0
        elif ans != -1 and correct != -1:
            total -= negative
    if total < 0: total = 0.0
    finished_at = datetime.utcnow().isoformat()
    db_execute("UPDATE attempts SET finished_at=?, answers_json=?, score=?, max_score=? WHERE id=?",
               (finished_at, json.dumps(session_data["answers"]), total, maxscore, session_data["attempt_id"]))
    try:
        await bot.send_message(session_data["user_id"], f" ✅ Quiz finished! Your score: {total}/{maxscore}")
    except:
        pass
    path = get_private_session_path(*session_key)
    await delete_session_file(path, session_key, private_session_locks)

async def start_quiz_in_group(bot: Bot, chat_id: int, quiz_id: str, starter_id: int = None):
    qrow = db_execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,), commit=False).fetchone()
    if not qrow:
        try:
            await bot.send_message(chat_id, "Quiz not found.")
        except: pass
        return
    qs_cur = db_execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,), commit=False)
    qrows = qs_cur.fetchall()
    if not qrows:
        try:
            await bot.send_message(chat_id, "No questions in quiz.")
        except: pass
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
    await bot.send_message(chat_id, f"🎯 Quiz starting now: *{qrow['title']}*\nTime per question: {session['time_per_question_sec']}s\nEveryone can answer using the quiz options. Results will be shown at the end.")
    await group_send_question(bot, session_key)

async def group_send_question(bot: Bot, session_key: Tuple[int, str]):
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
    
    explanation = q.get("explanation") or None

    try:
        sent_poll = await bot.send_poll(
            chat_id=session["chat_id"],
            question=q.get("text"),
            options=q.get("options"),
            type='quiz',
            correct_option_id=q.get("correctIndex", 0),
            open_period=session["time_per_question_sec"],
            is_anonymous=False,
            explanation=explanation
        )
        session["poll_id"] = sent_poll.poll.id
        session["message_id"] = sent_poll.message_id

        POLL_ID_TO_SESSION_MAP[sent_poll.poll.id] = {"type": "group", "key": session_key}

        await write_session_file(path, session, lock)
    except Exception as e:
        print(f"Failed to send group poll: {e}. Finalizing quiz.")
        await group_finalize_and_export(bot, session_key)
        return
    
    old_task = running_group_tasks.pop(session_key, None)
    if old_task:
        old_task.cancel()
    
    async def per_question_timeout():
        try:
            await asyncio.sleep(session["time_per_question_sec"] + 2)
            # Re-read session to ensure we are still on the same question
            fresh_session = await read_session_file(path, lock)
            if fresh_session and fresh_session["current_q"] == qidx:
                await group_reveal_and_advance(bot, session_key, qidx, timed_out=True)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in group timeout task: {e}")
            
    running_group_tasks[session_key] = asyncio.create_task(per_question_timeout())


async def group_reveal_and_advance(bot: Bot, session_key: Tuple[int, str], qidx: int, timed_out=False):
    path = get_group_session_path(*session_key)
    lock = get_group_lock(session_key)
    session = await read_session_file(path, lock)
    if not session:
        return
    
    # Ensure we only advance once per question
    if session["current_q"] != qidx:
        return

    if session.get("poll_id"):
        POLL_ID_TO_SESSION_MAP.pop(session["poll_id"], None)
        try:
            await bot.stop_poll(session["chat_id"], session["message_id"])
        except Exception:
            pass

    session["current_q"] += 1
    await write_session_file(path, session, lock)
    
    if session["current_q"] >= len(session["questions"]):
        await group_finalize_and_export(bot, session_key)
        return
        
    await group_send_question(bot, session_key)


async def group_finalize_and_export(bot: Bot, session_key: Tuple[int, str]):
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
        await bot.send_message(chat_id, final_message)
    except Exception as e:
        print(f"Error sending final group results: {e}")
    
    await delete_session_file(path, session_key, group_session_locks, running_group_tasks)


# --- Aiogram Main Execution ---

async def main_async():
    # Set default parse mode to MARKDOWN (legacy) to match PTB script's behavior
    bot = Bot(token=BOT_TOKEN, default_parse_mode=ParseMode.MARKDOWN)
    
    # Register all handlers with the dispatcher
    # Handlers are already decorated, so they are attached to `dp`
    
    print("Starting Aiogram Quiz Bot polling...")
    # Start polling
    await dp.start_polling(bot)


# --- COMBINED MAIN LAUNCHER ---

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 1. Start the Flask server in a daemon thread.
    # A daemon thread will automatically shut down when the main program (the bot) exits.
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 2. Run the asyncio bot main function (which blocks) on the main thread.
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down bot and web server...")
