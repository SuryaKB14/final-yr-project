from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# 1. Users Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    course TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 2. Quiz Attempts Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS quiz_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    topic TEXT,
    difficulty_level TEXT,
    score INTEGER,
    total_questions INTEGER,
    accuracy REAL,
    attempt_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
""")

# 3. Question Responses Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS question_responses (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER,
    question_text TEXT,
    user_answer TEXT,
    correct_answer TEXT,
    is_correct INTEGER,
    topic TEXT,
    difficulty_level TEXT,
    FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(attempt_id)
)
""")

# 4. User Performance Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_performance (
    performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    topic TEXT,
    attempts_count INTEGER DEFAULT 0,
    average_score REAL DEFAULT 0,
    accuracy REAL DEFAULT 0,
    weakness_level TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
""")

cursor.execute("""
INSERT OR IGNORE INTO users (user_id, name, email, password, course)
VALUES (1, 'Demo User', 'demo@example.com', '1234', 'Python')
""")

conn.commit()
conn.close()

print("Database and tables created successfully!")