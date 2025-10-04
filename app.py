import os
import sqlite3
import json
from functools import wraps
from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    url_for, 
    session, 
    flash, 
    g
)

# --- CONFIGURATION ---
app = Flask(__name__)
# IMPORTANT: Set a strong, random secret key for session security
app.secret_key = os.urandom(24) 
# The password for accessing the web panel. 
# SET THIS IN YOUR ENVIRONMENT VARIABLES.
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
DATABASE = "quizzes.db"

if ADMIN_PASSWORD == 'admin123':
    print("WARNING: Using default admin password. Set the ADMIN_PASSWORD environment variable for security.")

# --- DATABASE HELPERS ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- AUTHENTICATION ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Incorrect password. Please try again.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Dashboard with summary stats."""
    db = get_db()
    creator_count = db.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    quiz_count = db.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0]
    attempt_count = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    return render_template('index.html', 
                           creator_count=creator_count, 
                           quiz_count=quiz_count, 
                           attempt_count=attempt_count)

@app.route('/creators')
@login_required
def creators_list():
    """Show a list of all quiz creators."""
    db = get_db()
    # Query to count quizzes per creator
    creators = db.execute("""
        SELECT c.id, c.tg_user_id, c.username, c.display_name, COUNT(q.id) as quiz_count
        FROM creators c
        LEFT JOIN quizzes q ON c.id = q.creator_id
        GROUP BY c.id
        ORDER BY quiz_count DESC
    """).fetchall()
    return render_template('creators.html', creators=creators)

@app.route('/quizzes')
@app.route('/quizzes/creator/<int:creator_id>')
@login_required
def quizzes_list(creator_id=None):
    """
    Show a list of all quizzes.
    If creator_id is provided, filter quizzes by that creator.
    """
    db = get_db()
    creator = None
    query = """
        SELECT q.id, q.title, q.time_per_question_sec, q.negative_mark, q.created_at, c.display_name, c.username
        FROM quizzes q
        JOIN creators c ON q.creator_id = c.id
    """
    params = ()
    
    if creator_id:
        query += " WHERE q.creator_id = ?"
        params = (creator_id,)
        creator = db.execute("SELECT * FROM creators WHERE id = ?", (creator_id,)).fetchone()

    query += " ORDER BY q.created_at DESC"
    quizzes = db.execute(query, params).fetchall()
    
    return render_template('quizzes.html', quizzes=quizzes, creator=creator)

@app.route('/quiz/<quiz_id>')
@login_required
def quiz_details(quiz_id):
    """Shows details and questions for a specific quiz."""
    db = get_db()
    quiz = db.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if not quiz:
        flash('Quiz not found.', 'error')
        return redirect(url_for('quizzes_list'))
        
    question_rows = db.execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx", (quiz_id,)).fetchall()
    questions = []
    for row in question_rows:
        try:
            # The 'q_json' field contains the question data as a JSON string
            q_data = json.loads(row['q_json'])
            q_data['db_id'] = row['id'] # Add database ID for potential future edits/deletes
            questions.append(q_data)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse JSON for question ID {row['id']}")
            continue # Skip malformed questions

    return render_template('quizzes.html', quizzes=[quiz], specific_quiz=quiz, questions=questions)

@app.route('/quiz/delete/<quiz_id>', methods=['POST'])
@login_required
def delete_quiz(quiz_id):
    """Deletes a quiz, its questions, and its attempts."""
    db = get_db()
    db.execute("DELETE FROM questions WHERE quiz_id = ?", (quiz_id,))
    db.execute("DELETE FROM attempts WHERE quiz_id = ?", (quiz_id,))
    db.execute("DELETE FROM schedule WHERE quiz_id = ?", (quiz_id,))
    db.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
    db.commit()
    flash(f"Quiz '{quiz_id}' and all its data have been deleted.", 'success')
    return redirect(request.referrer or url_for('quizzes_list'))


@app.route('/attempts')
@login_required
def attempts_list():
    """Shows a list of all quiz attempts."""
    db = get_db()
    attempts = db.execute("""
        SELECT a.id, a.user_id, a.username, a.started_at, a.score, a.max_score, q.title as quiz_title
        FROM attempts a
        LEFT JOIN quizzes q ON a.quiz_id = q.id
        ORDER BY a.started_at DESC
        LIMIT 100 
    """).fetchall() # Limit to recent 100 for performance
    return render_template('attempts.html', attempts=attempts)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8080)
