from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi
import fitz
from dotenv import load_dotenv
import os
import json
import re
from db import get_db_connection

# NEW IMPORTS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from pypdf import PdfReader

# Load env
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini client
client = genai.Client(api_key=API_KEY)

# LLM (Used for Flashcards + Quiz + Tutor)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    google_api_key=API_KEY
)

print("Starting EZStudy backend...")

app = Flask(__name__)
CORS(app, origins="*")


# ---------------- BASIC ROUTES ----------------

@app.route("/")
def home():
    return jsonify({"message": "EZStudy Backend Running Successfully 🚀"})


@app.route("/quiz")
def quiz_page():
    return render_template("quiz.html")


# ---------------- DATABASE HELPER FUNCTIONS ----------------

def get_weak_topics(user_id, selected_topic=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    if selected_topic:
        cursor.execute("""
            SELECT topic, accuracy, weakness_level
            FROM user_performance
            WHERE user_id = ? 
              AND topic = ?
              AND weakness_level IN ('High', 'Moderate')
        """, (user_id, selected_topic))
    else:
        cursor.execute("""
            SELECT topic, accuracy, weakness_level
            FROM user_performance
            WHERE user_id = ? AND weakness_level IN ('High', 'Moderate')
            ORDER BY accuracy ASC
        """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [row["topic"] for row in rows]


def get_user_adaptive_difficulty(user_id, selected_topic=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    if selected_topic:
        cursor.execute("""
            SELECT AVG(accuracy) as avg_accuracy
            FROM quiz_attempts
            WHERE user_id = ? AND topic = ?
        """, (user_id, selected_topic))
    else:
        cursor.execute("""
            SELECT AVG(accuracy) as avg_accuracy
            FROM quiz_attempts
            WHERE user_id = ?
        """, (user_id,))

    result = cursor.fetchone()
    conn.close()

    avg_accuracy = result["avg_accuracy"] if result["avg_accuracy"] is not None else None

    # First time user / no attempts in this topic
    if avg_accuracy is None:
        return "medium"

    if avg_accuracy < 50:
        return "easy"
    elif avg_accuracy < 80:
        return "medium"
    else:
        return "hard"


def update_user_performance(user_id, topic):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) as attempts_count, AVG(score) as average_score, AVG(accuracy) as accuracy
        FROM quiz_attempts
        WHERE user_id = ? AND topic = ?
    """, (user_id, topic))

    result = cursor.fetchone()

    attempts_count = result["attempts_count"] if result["attempts_count"] is not None else 0
    average_score = result["average_score"] if result["average_score"] is not None else 0
    accuracy = result["accuracy"] if result["accuracy"] is not None else 0

    if accuracy < 50:
        weakness_level = "High"
    elif accuracy < 75:
        weakness_level = "Moderate"
    else:
        weakness_level = "Low"

    cursor.execute("""
        SELECT * FROM user_performance
        WHERE user_id = ? AND topic = ?
    """, (user_id, topic))

    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE user_performance
            SET attempts_count = ?, average_score = ?, accuracy = ?, weakness_level = ?
            WHERE user_id = ? AND topic = ?
        """, (attempts_count, average_score, accuracy, weakness_level, user_id, topic))
    else:
        cursor.execute("""
            INSERT INTO user_performance
            (user_id, topic, attempts_count, average_score, accuracy, weakness_level)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, topic, attempts_count, average_score, accuracy, weakness_level))

    conn.commit()
    conn.close()


# ---------------- AUTH ROUTES ----------------

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json

    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    course = data.get('course', 'General')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (name, email, password, course)
            VALUES (?, ?, ?, ?)
        """, (name, email, password, course))

        conn.commit()
        return jsonify({"message": "User registered successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.json

    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM users WHERE email = ? AND password = ?
    """, (email, password))

    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({
            "message": "Login successful",
            "user_id": user["user_id"],
            "name": user["name"]
        }), 200
    else:
        return jsonify({"error": "Invalid email or password"}), 401


# ---------------- COMMON PDF TEXT EXTRACTOR ----------------

def extract_text_from_pdfs(files):
    combined_text = ""
    for file in files:
        reader = PdfReader(file)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                combined_text += text + "\n"
    return combined_text.strip()


# ---------------- FLASHCARDS ----------------

def generate_flashcards(pdf_text, difficulty, num_cards, language):
    translation_instruction = ""
    if language.lower() != "english":
        translation_instruction = f"Translate both sides to {language}."

    if len(pdf_text) > 40000:
        pdf_text = pdf_text[:40000]

    prompt = f"""
Based ONLY on the following study material, create {num_cards} flashcards at {difficulty} level.
{translation_instruction}

Study Material:
\"\"\"{pdf_text}\"\"\"

Format strictly as:
Q: ...
A: ...
"""

    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


@app.route('/generate-flashcards', methods=['POST'])
def generate_flashcards_api():
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    difficulty = request.form.get("difficulty", "Beginner")
    num_cards = request.form.get("num_cards", 5)
    language = request.form.get("language", "English")

    pdf_text = extract_text_from_pdfs(files)

    if not pdf_text:
        return jsonify({"error": "Could not extract text"}), 400

    flashcards = generate_flashcards(pdf_text, difficulty, num_cards, language)

    return jsonify({"flashcards": flashcards})


# ---------------- QUIZ GENERATOR ----------------

@app.route("/generate-quiz", methods=["POST"])
def generate_quiz():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No PDF uploaded"}), 400

        file = request.files['file']
        user_id = request.form.get("user_id", "1")
        num_questions = int(request.form.get("num_questions", 5))
        selected_topic = request.form.get("topic", "General")

        print("SELECTED TOPIC FROM FRONTEND:", selected_topic)

        # Adaptive logic based ONLY on selected topic
        weak_topics = get_weak_topics(user_id, selected_topic)
        difficulty = get_user_adaptive_difficulty(user_id, selected_topic)

        print("GENERATE QUIZ USER ID:", user_id)
        print("WEAK TOPICS:", weak_topics)
        print("SELECTED DIFFICULTY:", difficulty)

        reader = PdfReader(file)
        text = ""

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted

        if not text.strip():
            return jsonify({"error": "No text found in PDF"}), 400

        text = text[:5000]

        if weak_topics:
            focus = f"Focus more on these weak topics if relevant to the text: {', '.join(weak_topics)}."
        else:
            focus = f"Focus on the selected topic: {selected_topic}."

        prompt = f"""
You are a quiz creator.

Selected subject/topic: {selected_topic}
{focus}

Create {num_questions} multiple choice questions at {difficulty} difficulty level.

IMPORTANT:
- Return ONLY valid JSON array
- Questions should be relevant to the selected topic
- Each question MUST include:
  1. question
  2. topic
  3. options
  4. correct_answer
  5. explanation

TEXT:
{text}

Return format:
[
  {{
    "question": "Question here?",
    "topic": "{selected_topic}",
    "options": {{
      "A": "option A",
      "B": "option B",
      "C": "option C",
      "D": "option D"
    }},
    "correct_answer": "A",
    "explanation": "Why this is correct."
  }}
]
"""

        response = llm.invoke([HumanMessage(content=prompt)])

        raw = response.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()

        mcqs = json.loads(raw)

        return jsonify({
            "mcqs": mcqs,
            "difficulty": difficulty,
            "selected_topic": selected_topic
        })

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ---------------- SAVE QUIZ RESULT ----------------

@app.route('/save-quiz-result', methods=['POST'])
def save_quiz_result():
    data = request.json

    user_id = data.get('user_id')
    topic = data.get('topic')
    difficulty_level = data.get('difficulty_level')
    score = data.get('score')
    total_questions = data.get('total_questions')

    if not user_id or not topic:
        return jsonify({"error": "Missing user_id or topic"}), 400

    accuracy = (score / total_questions) * 100 if total_questions > 0 else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO quiz_attempts (user_id, topic, difficulty_level, score, total_questions, accuracy)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, topic, difficulty_level, score, total_questions, accuracy))

    conn.commit()
    attempt_id = cursor.lastrowid
    conn.close()

    # Update adaptive profile
    update_user_performance(user_id, topic)

    print("QUIZ RESULT SAVED")
    print("USER ID:", user_id)
    print("TOPIC:", topic)
    print("SCORE:", score)
    print("TOTAL:", total_questions)
    print("ACCURACY:", accuracy)

    return jsonify({
        "message": "Quiz result saved successfully",
        "attempt_id": attempt_id,
        "accuracy": accuracy
    }), 201


# ---------------- SAVE QUESTION RESPONSES ----------------

@app.route('/save-question-responses', methods=['POST'])
def save_question_responses():
    data = request.json
    attempt_id = data.get('attempt_id')
    responses = data.get('responses', [])

    conn = get_db_connection()
    cursor = conn.cursor()

    for response in responses:
        cursor.execute("""
            INSERT INTO question_responses
            (attempt_id, question_text, user_answer, correct_answer, is_correct, topic, difficulty_level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            attempt_id,
            response.get('question_text'),
            response.get('user_answer'),
            response.get('correct_answer'),
            1 if response.get('is_correct') else 0,
            response.get('topic'),
            response.get('difficulty_level')
        ))

    conn.commit()
    conn.close()

    return jsonify({"message": "Question responses saved successfully"}), 201


# ---------------- GET WEAK TOPICS ----------------

@app.route('/get-weak-topics/<int:user_id>', methods=['GET'])
def get_weak_topics_api(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT topic, accuracy, weakness_level
        FROM user_performance
        WHERE user_id = ? AND weakness_level IN ('High', 'Moderate')
        ORDER BY accuracy ASC
    """, (user_id,))

    weak_topics = cursor.fetchall()
    conn.close()

    weak_topic_list = [
        {
            "topic": row["topic"],
            "accuracy": row["accuracy"],
            "weakness_level": row["weakness_level"]
        }
        for row in weak_topics
    ]

    return jsonify({"weak_topics": weak_topic_list}), 200


# ---------------- USER PROGRESS DASHBOARD ----------------

@app.route('/get-user-progress/<int:user_id>', methods=['GET'])
def get_user_progress(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(*) as total_quizzes,
            AVG(score) as avg_score,
            AVG(accuracy) as avg_accuracy
        FROM quiz_attempts
        WHERE user_id = ?
    """, (user_id,))
    
    progress = cursor.fetchone()

    cursor.execute("""
        SELECT topic, accuracy
        FROM user_performance
        WHERE user_id = ?
        ORDER BY accuracy DESC
        LIMIT 1
    """, (user_id,))
    best_topic = cursor.fetchone()

    cursor.execute("""
        SELECT topic, accuracy
        FROM user_performance
        WHERE user_id = ?
        ORDER BY accuracy ASC
        LIMIT 1
    """, (user_id,))
    weak_topic = cursor.fetchone()

    conn.close()

    return jsonify({
        "total_quizzes": progress["total_quizzes"] or 0,
        "avg_score": progress["avg_score"] or 0,
        "avg_accuracy": progress["avg_accuracy"] or 0,
        "best_topic": best_topic["topic"] if best_topic else None,
        "weak_topic": weak_topic["topic"] if weak_topic else None
    }), 200


# ---------------- AI TUTOR ----------------

def generate_ai_tutor_response(question, subject):
    prompt = f"""
You are an AI tutor helping a student.

Subject: {subject}

Student Question:
{question}

Provide:
1. Step-by-step solution
2. Final answer
3. Simple explanation
"""

    response = llm.invoke([HumanMessage(content=prompt)])
    print("LLM RESPONSE:", response.content)
    return response.content


@app.route("/ai-tutor", methods=["POST"])
def ai_tutor():
    data = request.get_json()
    print("Incoming request:", data)

    if not data or "question" not in data:
        return jsonify({"error": "No question provided"}), 400

    question = data.get("question")
    subject = data.get("subject", "general")

    try:
        result = generate_ai_tutor_response(question, subject)

        return jsonify({
            "answer": result
        })

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ---------------- SUMMARIZER ----------------

def get_summary(prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text


@app.route('/summarize/text', methods=['POST'])
def summarize_text():
    data = request.get_json()

    if not data or "text" not in data:
        return jsonify({"error": "No text provided"}), 400

    text = data.get("text")
    prompt = f"Summarize the following text in bullet points:\n{text}"

    summary = get_summary(prompt)

    return jsonify({"summary": summary})


@app.route('/summarize/pdf', methods=['POST'])
def summarize_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    doc = fitz.open(stream=file.read(), filetype="pdf")

    text = ""
    for page in doc:
        text += page.get_text()

    summary = get_summary(f"Summarize this PDF:\n{text}")

    return jsonify({"summary": summary})


@app.route('/summarize/youtube', methods=['POST'])
def summarize_youtube():
    data = request.get_json()

    if not data or "url" not in data:
        return jsonify({"error": "No URL provided"}), 400

    url = data.get("url")
    video_id = url.split("v=")[-1]

    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    text = " ".join([t["text"] for t in transcript])

    summary = get_summary(f"Summarize this video:\n{text}")

    return jsonify({"summary": summary})


@app.route('/all-users', methods=['GET'])
def all_users():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()

    user_list = [
        {
            "user_id": row["user_id"],
            "name": row["name"],
            "email": row["email"],
            "course": row["course"]
        }
        for row in users
    ]

    return jsonify({"users": user_list})


@app.route('/test-performance', methods=['GET'])
def test_performance():
    user_id = 1
    topic = "Functions"
    difficulty_level = "easy"
    score = 2
    total_questions = 5

    accuracy = (score / total_questions) * 100 if total_questions > 0 else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO quiz_attempts (user_id, topic, difficulty_level, score, total_questions, accuracy)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, topic, difficulty_level, score, total_questions, accuracy))

    conn.commit()
    attempt_id = cursor.lastrowid
    conn.close()

    update_user_performance(user_id, topic)

    return jsonify({
        "message": "Test quiz result inserted successfully",
        "attempt_id": attempt_id,
        "accuracy": accuracy,
        "topic": topic
    })


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)