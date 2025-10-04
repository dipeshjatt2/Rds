from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3
import os
import json
from datetime import datetime
import tempfile
import csv
import io

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# Database configuration
DB_PATH = "quizzes.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    
    # Get basic statistics
    total_quizzes = conn.execute('SELECT COUNT(*) as count FROM quizzes').fetchone()['count']
    total_creators = conn.execute('SELECT COUNT(*) as count FROM creators').fetchone()['count']
    total_attempts = conn.execute('SELECT COUNT(*) as count FROM attempts').fetchone()['count']
    total_questions = conn.execute('SELECT COUNT(*) as count FROM questions').fetchone()['count']
    
    # Get recent activity
    recent_quizzes = conn.execute('''
        SELECT q.*, c.username, c.display_name 
        FROM quizzes q 
        LEFT JOIN creators c ON q.creator_id = c.id 
        ORDER BY q.created_at DESC 
        LIMIT 5
    ''').fetchall()
    
    recent_attempts = conn.execute('''
        SELECT a.*, q.title as quiz_title 
        FROM attempts a 
        LEFT JOIN quizzes q ON a.quiz_id = q.id 
        ORDER BY a.started_at DESC 
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    return render_template('dashboard.html',
                         total_quizzes=total_quizzes,
                         total_creators=total_creators,
                         total_attempts=total_attempts,
                         total_questions=total_questions,
                         recent_quizzes=recent_quizzes,
                         recent_attempts=recent_attempts)

@app.route('/creators')
@login_required
def creators():
    conn = get_db_connection()
    creators_list = conn.execute('''
        SELECT c.*, COUNT(q.id) as quiz_count 
        FROM creators c 
        LEFT JOIN quizzes q ON c.id = q.creator_id 
        GROUP BY c.id 
        ORDER BY c.id DESC
    ''').fetchall()
    conn.close()
    return render_template('creators.html', creators=creators_list)

@app.route('/creator/<int:creator_id>')
@login_required
def creator_detail(creator_id):
    conn = get_db_connection()
    
    # Get creator info
    creator = conn.execute('SELECT * FROM creators WHERE id = ?', (creator_id,)).fetchone()
    if not creator:
        conn.close()
        return "Creator not found", 404
    
    # Get creator's quizzes
    quizzes = conn.execute('''
        SELECT q.*, COUNT(quest.id) as question_count 
        FROM quizzes q 
        LEFT JOIN questions quest ON q.id = quest.quiz_id 
        WHERE q.creator_id = ? 
        GROUP BY q.id 
        ORDER BY q.created_at DESC
    ''', (creator_id,)).fetchall()
    
    # Get creator's attempts
    attempts = conn.execute('''
        SELECT a.*, q.title as quiz_title 
        FROM attempts a 
        LEFT JOIN quizzes q ON a.quiz_id = q.id 
        WHERE q.creator_id = ? 
        ORDER BY a.started_at DESC 
        LIMIT 10
    ''', (creator_id,)).fetchall()
    
    conn.close()
    
    return render_template('creator_detail.html', 
                         creator=creator, 
                         quizzes=quizzes, 
                         attempts=attempts)

@app.route('/quizzes')
@login_required
def quizzes():
    conn = get_db_connection()
    quizzes_list = conn.execute('''
        SELECT q.*, c.username, c.display_name, COUNT(quest.id) as question_count 
        FROM quizzes q 
        LEFT JOIN creators c ON q.creator_id = c.id 
        LEFT JOIN questions quest ON q.id = quest.quiz_id 
        GROUP BY q.id 
        ORDER BY q.created_at DESC
    ''').fetchall()
    conn.close()
    return render_template('quizzes.html', quizzes=quizzes_list)

@app.route('/quiz/<quiz_id>')
@login_required
def quiz_detail(quiz_id):
    conn = get_db_connection()
    
    # Get quiz info
    quiz = conn.execute('''
        SELECT q.*, c.username, c.display_name 
        FROM quizzes q 
        LEFT JOIN creators c ON q.creator_id = c.id 
        WHERE q.id = ?
    ''', (quiz_id,)).fetchone()
    
    if not quiz:
        conn.close()
        return "Quiz not found", 404
    
    # Get questions
    questions = conn.execute('''
        SELECT * FROM questions 
        WHERE quiz_id = ? 
        ORDER BY idx
    ''', (quiz_id,)).fetchall()
    
    # Parse question JSON
    parsed_questions = []
    for q in questions:
        q_data = json.loads(q['q_json'])
        q_data['db_id'] = q['id']
        parsed_questions.append(q_data)
    
    # Get attempts for this quiz
    attempts = conn.execute('''
        SELECT * FROM attempts 
        WHERE quiz_id = ? 
        ORDER BY started_at DESC
    ''', (quiz_id,)).fetchall()
    
    conn.close()
    
    return render_template('quiz_detail.html', 
                         quiz=quiz, 
                         questions=parsed_questions, 
                         attempts=attempts)

@app.route('/delete_quiz/<quiz_id>', methods=['POST'])
@login_required
def delete_quiz(quiz_id):
    conn = get_db_connection()
    
    try:
        # Delete related records first
        conn.execute('DELETE FROM questions WHERE quiz_id = ?', (quiz_id,))
        conn.execute('DELETE FROM attempts WHERE quiz_id = ?', (quiz_id,))
        conn.execute('DELETE FROM quizzes WHERE id = ?', (quiz_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Quiz deleted successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Error deleting quiz: {str(e)}'})

@app.route('/edit_question/<int:question_id>', methods=['POST'])
@login_required
def edit_question(question_id):
    conn = get_db_connection()
    
    try:
        question_data = request.json
        updated_q_json = json.dumps({
            'text': question_data['text'],
            'options': question_data['options'],
            'correctIndex': int(question_data['correctIndex']),
            'explanation': question_data.get('explanation', ''),
            'reference': question_data.get('reference', '')
        })
        
        conn.execute('UPDATE questions SET q_json = ? WHERE id = ?', (updated_q_json, question_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Question updated successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Error updating question: {str(e)}'})

@app.route('/delete_question/<int:question_id>', methods=['POST'])
@login_required
def delete_question(question_id):
    conn = get_db_connection()
    
    try:
        conn.execute('DELETE FROM questions WHERE id = ?', (question_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Question deleted successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Error deleting question: {str(e)}'})

@app.route('/attempts')
@login_required
def attempts():
    conn = get_db_connection()
    attempts_list = conn.execute('''
        SELECT a.*, q.title as quiz_title, c.username, c.display_name 
        FROM attempts a 
        LEFT JOIN quizzes q ON a.quiz_id = q.id 
        LEFT JOIN creators c ON q.creator_id = c.id 
        ORDER BY a.started_at DESC
    ''').fetchall()
    conn.close()
    return render_template('attempts.html', attempts=attempts_list)

@app.route('/attempt/<int:attempt_id>')
@login_required
def attempt_detail(attempt_id):
    conn = get_db_connection()
    
    attempt = conn.execute('''
        SELECT a.*, q.title as quiz_title, c.username, c.display_name 
        FROM attempts a 
        LEFT JOIN quizzes q ON a.quiz_id = q.id 
        LEFT JOIN creators c ON q.creator_id = c.id 
        WHERE a.id = ?
    ''', (attempt_id,)).fetchone()
    
    if not attempt:
        conn.close()
        return "Attempt not found", 404
    
    # Get quiz questions to compare answers
    questions = conn.execute('''
        SELECT q.* FROM questions q 
        WHERE q.quiz_id = ? 
        ORDER BY q.idx
    ''', (attempt['quiz_id'],)).fetchall()
    
    # Parse answers
    answers = json.loads(attempt['answers_json']) if attempt['answers_json'] else []
    
    # Prepare question-answer pairs
    qa_pairs = []
    for i, q in enumerate(questions):
        q_data = json.loads(q['q_json'])
        user_answer = answers[i] if i < len(answers) else -1
        is_correct = user_answer == q_data['correctIndex']
        
        qa_pairs.append({
            'question': q_data,
            'user_answer': user_answer,
            'is_correct': is_correct,
            'question_number': i + 1
        })
    
    conn.close()
    
    return render_template('attempt_detail.html', 
                         attempt=attempt, 
                         qa_pairs=qa_pairs)

@app.route('/delete_attempt/<int:attempt_id>', methods=['POST'])
@login_required
def delete_attempt(attempt_id):
    conn = get_db_connection()
    
    try:
        conn.execute('DELETE FROM attempts WHERE id = ?', (attempt_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Attempt deleted successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Error deleting attempt: {str(e)}'})

@app.route('/export_quiz/<quiz_id>')
@login_required
def export_quiz(quiz_id):
    conn = get_db_connection()
    
    quiz = conn.execute('SELECT * FROM quizzes WHERE id = ?', (quiz_id,)).fetchone()
    if not quiz:
        conn.close()
        return "Quiz not found", 404
    
    questions = conn.execute('SELECT * FROM questions WHERE quiz_id = ? ORDER BY idx', (quiz_id,)).fetchall()
    conn.close()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Question', 'Option 1', 'Option 2', 'Option 3', 'Option 4', 'Correct Index', 'Explanation'])
    
    # Write questions
    for q in questions:
        q_data = json.loads(q['q_json'])
        row = [q_data['text']]
        
        # Add options
        for opt in q_data['options']:
            row.append(opt)
        
        # Fill remaining options if less than 4
        while len(row) < 5:
            row.append('')
        
        # Add correct index (1-based for CSV)
        row.append(q_data['correctIndex'] + 1)
        row.append(q_data.get('explanation', ''))
        
        writer.writerow(row)
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'quiz_{quiz_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

# API endpoints for statistics
@app.route('/api/stats')
@login_required
def api_stats():
    conn = get_db_connection()
    
    # Basic counts
    stats = {
        'total_quizzes': conn.execute('SELECT COUNT(*) as count FROM quizzes').fetchone()['count'],
        'total_creators': conn.execute('SELECT COUNT(*) as count FROM creators').fetchone()['count'],
        'total_attempts': conn.execute('SELECT COUNT(*) as count FROM attempts').fetchone()['count'],
        'total_questions': conn.execute('SELECT COUNT(*) as count FROM questions').fetchone()['count'],
    }
    
    # Quizzes per creator
    quizzes_per_creator = conn.execute('''
        SELECT c.username, c.display_name, COUNT(q.id) as quiz_count 
        FROM creators c 
        LEFT JOIN quizzes q ON c.id = q.creator_id 
        GROUP BY c.id 
        ORDER BY quiz_count DESC 
        LIMIT 10
    ''').fetchall()
    
    stats['quizzes_per_creator'] = [
        {'creator': row['username'] or row['display_name'], 'count': row['quiz_count']}
        for row in quizzes_per_creator
    ]
    
    # Recent activity
    recent_activity = conn.execute('''
        SELECT 'quiz' as type, title as name, created_at as date FROM quizzes 
        UNION ALL 
        SELECT 'attempt' as type, quiz_id as name, started_at as date FROM attempts 
        ORDER BY date DESC 
        LIMIT 10
    ''').fetchall()
    
    stats['recent_activity'] = [
        {'type': row['type'], 'name': row['name'], 'date': row['date']}
        for row in recent_activity
    ]
    
    conn.close()
    return jsonify(stats)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
