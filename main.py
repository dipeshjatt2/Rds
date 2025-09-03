import asyncio
import json
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

# This HTML template file must be in the same directory as the bot script.
TEMPLATE_HTML = "format2.html"

app = Client("combined_quiz_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ── GLOBAL STATE & CONSTANTS ──
# Unified state management for all bot functions.
user_state = {}

# ─── HELPER FUNCTIONS (PARSING & HTML) ───
# These functions are from the second bot for the HTML generation feature.

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

@app.on_message(filters.text & ~filters.command(["start", "help", "create", "txqz", "htmk"]))
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


# ── RUN BOT ──
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
    else:
        print("Bot is running...")
        app.run()
