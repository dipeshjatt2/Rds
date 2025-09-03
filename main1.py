import os
import re
import json
import io
from pyrogram import Client, filters
from pyrogram.types import Message
import random
import time
import asyncio
import csv

# ── CONFIG ──
API_ID = 22118129
API_HASH = "43c66e3314921552d9330a4b05b18800"
BOT_TOKEN = "7621851195:AAGG1W5UTBmlbTHi2Hx7_vgUjaK7_ecnXOM"

TEMPLATE_HTML = "format2.html"  # must be in same dir

# State
PENDING = {}  # chat_id -> {"questions": [], "step": str, "time": int, "negative": float}

# ── Parsers ──
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
    """CSV format parser (no pandas)"""
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
    if "Definition:" in txt or re.search(r'\([a-zA-Z]\)', txt):
        return parse_format1(txt)
    if re.search(r'^\s*\d+\.\s+.*\na\)', txt, flags=re.M):
        return parse_format2(txt)
    if "const quizData" in txt:
        return parse_format3(txt)
    if re.search(r'✅', txt) and not ("(a)" in txt):
        return parse_format4(txt)
    return []

# ── HTML Injector ──
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

# ── Bot ──
app = Client("quiz_html_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command(["start","help"]))
async def start_handler(_, msg: Message):
    await msg.reply_text(
        "👋 Send me a .txt or .csv file.\n"
        "Supported formats: (1–4) text or CSV.\n"
        "I’ll parse the questions, then ask:\n"
        "1️⃣ Test time in minutes\n2️⃣ Negative mark per wrong\n3️⃣ Shuffle? (yes/no)\n4️⃣ Filename\n\n"
        "Then I’ll send you the final .html."
    )

@app.on_message(filters.document & (filters.private | filters.group))
async def file_handler(_, msg: Message):
    filename = msg.document.file_name.lower()
    path = await msg.download()

    if filename.endswith(".txt"):
        txt = open(path,"r",encoding="utf-8",errors="ignore").read()
        os.remove(path)
        questions = detect_and_parse(txt)

    elif filename.endswith(".csv"):
        questions = parse_csv(path)
        os.remove(path)

    else:
        return

    if not questions:
        await msg.reply_text("❌ Could not parse. Check file format.")
        return
    PENDING[msg.chat.id]={"questions":questions,"step":"time"}
    await msg.reply_text(f"✅ Parsed {len(questions)} questions.\nNow send test time in minutes:")

@app.on_message(filters.text & (filters.private | filters.group))
async def text_handler(_, msg: Message):
    if msg.chat.id not in PENDING: return
    state=PENDING[msg.chat.id]
    if state["step"]=="time":
        try:
            mins=int(msg.text.strip());
            state["time"]=mins; state["step"]="negative"
            await msg.reply_text("⏬ Now send negative marks per wrong (e.g. 0.25):")
        except: await msg.reply_text("❌ Send a valid integer (minutes).")
    elif state["step"]=="negative":
        try:
            neg=float(msg.text.strip())
            state["negative"]=neg; state["step"]="shuffle"
            await msg.reply_text("🔀 Do you want to shuffle questions and options? (yes/no):")
        except: await msg.reply_text("❌ Send a valid number (e.g. 0.25).")
    elif state["step"]=="shuffle":
        ans = msg.text.strip().lower()
        if ans not in ["yes", "no"]:
            await msg.reply_text("❌ Send yes or no.")
            return
        if ans == "no":
            state["step"]="filename"
            await msg.reply_text("📄 Finally send filename (without .html):")
            return
        progress_msg = await msg.reply_text("🔀 Starting shuffle... 0%")
        questions = state["questions"]
        random.shuffle(questions)
        num_q = len(questions)
        temp_file = f"temp_shuffled_{msg.chat.id}.txt"
        with open(temp_file, "w", encoding="utf-8") as f:
            pass
        last_update = time.time()
        for i, q in enumerate(questions):
            opts = q["options"]
            if len(opts) > 1:
                correct_opt = opts[q["correctIndex"]]
                random.shuffle(opts)
                q["correctIndex"] = opts.index(correct_opt)
            with open(temp_file, "a", encoding="utf-8") as f:
                f.write(f"{i+1}. {q['text']}\n")
                for j, opt in enumerate(opts):
                    mark = "✅" if j == q["correctIndex"] else ""
                    f.write(f"({chr(97+j)}) {opt}{mark} ")
                if q["explanation"]:
                    f.write(f"\nEx: {q['explanation']}")
                f.write("\n\n")
            progress = int((i + 1) / num_q * 100)
            current_time = time.time()
            if current_time - last_update >= 3:
                await progress_msg.edit_text(f"🔀 Shuffling... {progress}%")
                last_update = current_time
            await asyncio.sleep(0.5)
        await progress_msg.edit_text("🔀 Shuffle complete! 100%")
        with open(temp_file, "r", encoding="utf-8") as f:
            shuffled_txt = f.read()
        os.remove(temp_file)
        state["questions"] = detect_and_parse(shuffled_txt)
        state["step"]="filename"
        await msg.reply_text("📄 Finally send filename (without .html):")
    elif state["step"]=="filename":
        name=re.sub(r'[^A-Za-z0-9_\- ]+','',msg.text.strip())
        if not name:
            await msg.reply_text("❌ Invalid filename.")
            return
        out_name=f"{name}.html"
        with open(TEMPLATE_HTML,"r",encoding="utf-8",errors="ignore") as f: html=f.read()
        data=replace_questions_in_template(html,state["questions"],state["time"],state["negative"]).encode("utf-8")
        file_obj=io.BytesIO(data); file_obj.name=out_name
        await msg.reply_document(file_obj,caption=f"✅ Here is your quiz: {out_name}")
        PENDING.pop(msg.chat.id,None)

# ===============================
# /txt2quiz handler (unchanged)
# ===============================
@app.on_message(filters.command("txt2quiz", prefixes="/"))
async def txt2quiz_handler(client: Client, message: Message):
    try:
        text_block = ""
        if "\n" in message.text.strip():
            parts = message.text.split("\n", 1)
            text_block = parts[1].strip()
        elif message.reply_to_message and message.reply_to_message.document:
            file_path = await message.reply_to_message.download()
            with open(file_path, "r", encoding="utf-8") as f:
                text_block = f.read()
            os.remove(file_path)
        else:
            await message.reply_text(
                "📌 Usage:\n"
                "1. `/txt2quiz` + quiz text in message\n"
                "2. Reply `/txt2quiz` to a `.txt` file"
            )
            return
        if not text_block:
            await message.reply_text("❌ No quiz text found.")
            return
        questions = []
        current_q = None
        for line in text_block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit() and "." in line[:4]:
                if current_q:
                    questions.append(current_q)
                current_q = {
                    "text": line.split(".", 1)[1].strip(),
                    "options": [],
                    "correct": None,
                    "explanation": ""
                }
            elif line.startswith("(") and ")" in line[:4] and current_q:
                option_text = line[3:].strip()
                is_correct = "✅" in option_text
                option_text = option_text.replace("✅", "").strip()
                current_q["options"].append(option_text)
                if is_correct:
                    current_q["correct"] = len(current_q["options"]) - 1
            elif line.lower().startswith("ex:") and current_q:
                current_q["explanation"] = line[3:].strip()
        if current_q:
            questions.append(current_q)
        if not questions:
            await message.reply_text("❌ Could not parse any valid questions.")
            return
        sent_count = 0
        for q in questions:
            if len(q["options"]) < 2:
                continue
            correct_idx = q["correct"] if q["correct"] is not None else 0
            try:
                await client.send_poll(
                    chat_id=message.chat.id,
                    question=q["text"][:295],
                    options=q["options"][:10],
                    type="quiz",
                    correct_option_id=correct_idx,
                    explanation=q["explanation"] or None,
                    is_anonymous=False,
                )
                sent_count += 1
                await asyncio.sleep(2)
            except Exception as e:
                await message.reply_text(f"⚠️ Error: {e}")
        await message.reply_text(f"✅ Created {sent_count} quiz polls.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

if __name__=="__main__":
    print("Bot running. Press Ctrl+C to stop.")
    app.run()
