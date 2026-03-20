from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi
import fitz
from dotenv import load_dotenv
import os
import json
import re

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

    flashcards = generate_flashcards(
        pdf_text,
        difficulty,
        num_cards,
        language
    )

    return jsonify({"flashcards": flashcards})


# ---------------- QUIZ GENERATOR ----------------

@app.route("/generate-quiz", methods=["POST"])
def generate_quiz():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No PDF uploaded"}), 400

        file = request.files['file']
        difficulty = request.form.get("difficulty", "easy")
        num_questions = int(request.form.get("num_questions", 5))

        reader = PdfReader(file)
        text = ""

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted

        if not text.strip():
            return jsonify({"error": "No text found in PDF"}), 400

        text = text[:4000]

        prompt = f"""
You are a quiz creator.

Based on the text below, create {num_questions} multiple choice questions at {difficulty} difficulty.

TEXT:
{text}

Return ONLY a JSON array in this format:

[
  {{
    "question": "Question here?",
    "options": {{
      "A": "option",
      "B": "option",
      "C": "option",
      "D": "option"
    }},
    "correct_answer": "A",
    "explanation": "Why this is correct."
  }}
]
"""

        response = llm.invoke(prompt)
        raw = response.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()

        mcqs = json.loads(raw)

        return jsonify({"mcqs": mcqs})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- AI TUTOR (NEW FEATURE) ----------------

def generate_ai_tutor_response(question, subject):

    prompt = f"""
You are an AI tutor helping a student.

Subject: {subject}

Student Question:
{question}

Provide:
1. Step-by-step solution
2. Final answer
2. Simple explanation
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
        print("ERROR:", str(e))  # ✅ debug
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


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)