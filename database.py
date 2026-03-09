import sqlite3
import json
from datetime import datetime

DB_PATH = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            total_answers INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            last_daily DATE,
            daily_count INTEGER DEFAULT 0,
            daily_goal INTEGER DEFAULT 5,
            exam_date TEXT,
            user_level TEXT DEFAULT 'beginner'
        )
    """)
    
    # Добавляем новые колонки, если их нет
    try:
        cur.execute("SELECT exam_date FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE users ADD COLUMN exam_date TEXT")
    
    try:
        cur.execute("SELECT user_level FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE users ADD COLUMN user_level TEXT DEFAULT 'beginner'")
    
    # Таблица заданий
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            subject TEXT,
            theme_id TEXT,
            text TEXT,
            options TEXT,
            correct TEXT,
            letters TEXT
        )
    """)
    
    # Таблица обратной связи
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            date TEXT
        )
    """)
    
    # Таблица статистики по темам
    cur.execute("""
        CREATE TABLE IF NOT EXISTS theme_stats (
            user_id INTEGER,
            subject TEXT,
            theme_id TEXT,
            total INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, subject, theme_id)
        )
    """)
    
    # Таблица избранных конспектов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            subject TEXT,
            theme_id TEXT,
            added DATE DEFAULT CURRENT_DATE,
            PRIMARY KEY (user_id, subject, theme_id)
        )
    """)
    
    # Таблица напоминаний
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            user_id INTEGER PRIMARY KEY,
            reminder_time TEXT,
            active INTEGER DEFAULT 1
        )
    """)
    
    # Таблица подписок (премиум)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            subscription_type TEXT DEFAULT 'free',
            expires_at DATE,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    conn.commit()
    conn.close()

# ---------- Работа с пользователями ----------
def get_user(user_id, username=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute("""
            INSERT INTO users (user_id, username, level, exp, total_answers, correct_answers, last_daily, daily_count, daily_goal, exam_date, user_level)
            VALUES (?, ?, 1, 0, 0, 0, date('now'), 0, 5, NULL, 'beginner')
        """, (user_id, username))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    conn.close()
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))

def update_user_stats(user_id, correct=False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT total_answers, correct_answers, exp FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        get_user(user_id)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT total_answers, correct_answers, exp FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    
    total, correct_ans, exp = row
    total += 1
    if correct:
        correct_ans += 1
        exp += 10
    else:
        exp += 1
    level = exp // 100 + 1
    cur.execute("""
        UPDATE users SET total_answers=?, correct_answers=?, exp=?, level=?
        WHERE user_id=?
    """, (total, correct_ans, exp, level, user_id))
    conn.commit()
    conn.close()

def update_daily(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_daily, daily_count FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        get_user(user_id)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT last_daily, daily_count FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    last, count = row
    today = datetime.now().date().isoformat()
    if last == today:
        count += 1
    else:
        count = 1
    cur.execute("UPDATE users SET last_daily=?, daily_count=? WHERE user_id=?", (today, count, user_id))
    conn.commit()
    conn.close()
    return count

def get_daily_goal(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_daily, daily_count, daily_goal FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        get_user(user_id)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT last_daily, daily_count, daily_goal FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    last, count, goal = row
    today = datetime.now().date().isoformat()
    if last != today:
        count = 0
    conn.close()
    return count, goal

def set_daily_goal(user_id, goal):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET daily_goal=? WHERE user_id=?", (goal, user_id))
    conn.commit()
    conn.close()

def set_exam_date(user_id, exam_date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET exam_date=? WHERE user_id=?", (exam_date, user_id))
    conn.commit()
    conn.close()

def set_user_level(user_id, user_level):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET user_level=? WHERE user_id=?", (user_level, user_id))
    conn.commit()
    conn.close()

def get_all_users_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(total_answers), SUM(correct_answers) FROM users")
    total_users, total_answers, total_correct = cur.fetchone()
    conn.close()
    return total_users or 0, total_answers or 0, total_correct or 0

# ---------- Статистика по темам ----------
def update_theme_stats(user_id, subject, theme_id, correct):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO theme_stats (user_id, subject, theme_id, total, correct)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(user_id, subject, theme_id) DO UPDATE SET
            total = total + 1,
            correct = correct + excluded.correct
    """, (user_id, subject, theme_id, 1 if correct else 0))
    conn.commit()
    conn.close()

def get_theme_stats(user_id, subject=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if subject:
        cur.execute("SELECT subject, theme_id, total, correct FROM theme_stats WHERE user_id=? AND subject=?", (user_id, subject))
    else:
        cur.execute("SELECT subject, theme_id, total, correct FROM theme_stats WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{"subject": r[0], "theme_id": r[1], "total": r[2], "correct": r[3]} for r in rows]

def get_worst_themes(user_id, subject=None, limit=3):
    stats = get_theme_stats(user_id, subject)
    stats = [s for s in stats if s['total'] >= 2]
    if not stats:
        return []
    stats.sort(key=lambda x: x['correct']/x['total'])
    return stats[:limit]

# ---------- Избранное ----------
def add_favorite(user_id, subject, theme_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO favorites (user_id, subject, theme_id) VALUES (?, ?, ?)", (user_id, subject, theme_id))
    conn.commit()
    conn.close()

def remove_favorite(user_id, subject, theme_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM favorites WHERE user_id=? AND subject=? AND theme_id=?", (user_id, subject, theme_id))
    conn.commit()
    conn.close()

def get_favorites(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT subject, theme_id FROM favorites WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{"subject": r[0], "theme_id": r[1]} for r in rows]

def is_favorite(user_id, subject, theme_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM favorites WHERE user_id=? AND subject=? AND theme_id=?", (user_id, subject, theme_id))
    row = cur.fetchone()
    conn.close()
    return row is not None

# ---------- Напоминания ----------
def set_reminder(user_id, time_str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO reminders (user_id, reminder_time, active) VALUES (?, ?, 1)", (user_id, time_str))
    conn.commit()
    conn.close()

def disable_reminder(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET active=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_active_reminders():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, reminder_time FROM reminders WHERE active=1")
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------- Работа с заданиями ----------
def add_task(task_id, subject, theme_id, text, options, correct, letters):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO tasks (task_id, subject, theme_id, text, options, correct, letters)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (task_id, subject, theme_id, text, json.dumps(options, ensure_ascii=False), correct, letters))
    conn.commit()
    conn.close()

def get_tasks_by_theme(subject, theme_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE subject=? AND theme_id=?", (subject, theme_id))
    rows = cur.fetchall()
    conn.close()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "subject": row[1],
            "theme_id": row[2],
            "text": row[3],
            "options": json.loads(row[4]),
            "correct": row[5],
            "letters": row[6]
        })
    return tasks

def get_task_by_id(task_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "subject": row[1],
            "theme_id": row[2],
            "text": row[3],
            "options": json.loads(row[4]),
            "correct": row[5],
            "letters": row[6]
        }
    return None

# ---------- Обратная связь ----------
def add_feedback(user_id, message):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO feedback (user_id, message, date) VALUES (?, ?, datetime('now'))", (user_id, message))
    conn.commit()
    conn.close()

# ---------- Подписки (премиум) ----------
def get_subscription(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT subscription_type, expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"type": row[0], "expires_at": row[1]}
    return {"type": "free", "expires_at": None}

def set_subscription(user_id, sub_type, expires_at):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO subscriptions (user_id, subscription_type, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, sub_type, expires_at))
    conn.commit()
    conn.close()

def has_premium(user_id):
    sub = get_subscription(user_id)
    if sub["type"] != "premium":
        return False
    if sub["expires_at"]:
        expires = datetime.strptime(sub["expires_at"], "%Y-%m-%d").date()
        if expires < datetime.now().date():
            return False
    return True