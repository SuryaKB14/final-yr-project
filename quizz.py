import streamlit as st
import os
import json
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pypdf import PdfReader

# Load environment variables
load_dotenv()

# Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    google_api_key=os.getenv("GEMINI_API_KEY")
)

st.title("MCQ Quiz Generator")

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])
quiz_level = st.selectbox("Difficulty", ["easy", "medium", "hard"])
num_questions = st.slider("Number of Questions", 3, 10, 5)

# Generate quiz
if st.button("Generate Quiz"):

    if not uploaded_file:
        st.warning("Please upload a PDF first.")
        st.stop()

    # Extract text
    reader = PdfReader(uploaded_file)
    text = ""

    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted

    if not text.strip():
        st.error("Could not extract text from this PDF.")
        st.stop()

    with st.spinner("Generating quiz..."):

        prompt = f"""
You are a quiz creator.

Based on the text below, create {num_questions} multiple choice questions at {quiz_level} difficulty.

TEXT:
{text[:4000]}

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

        try:
            response = llm.invoke(prompt)
            raw = response.content.strip()

            # Clean markdown if Gemini returns ```json
            raw = re.sub(r"```json|```", "", raw).strip()

            mcqs = json.loads(raw)

            st.session_state.mcqs = mcqs

            st.success("Quiz generated! Scroll down.")

        except Exception:
            st.error("AI returned invalid JSON. Please try again.")
            st.stop()

# Show quiz
if "mcqs" in st.session_state:

    mcqs = st.session_state.mcqs
    answers = {}

    st.header("Quiz")

    for i, q in enumerate(mcqs):

        st.markdown(f"**Q{i+1}. {q['question']}**")

        options = [f"{k}. {v}" for k, v in q["options"].items()]

        answers[i] = st.radio(
            f"Select answer for Q{i+1}",
            options,
            key=f"q{i}"
        )

        st.write("")

    if st.button("Submit Answers"):

        score = 0

        st.subheader("Results")

        for i, q in enumerate(mcqs):

            if answers[i]:

                user = answers[i][0]
                correct = q["correct_answer"]

                if user == correct:
                    st.success(f"Q{i+1}: Correct! {q['explanation']}")
                    score += 1
                else:
                    st.error(f"Q{i+1}: Wrong. Correct answer: {correct}. {q['explanation']}")

            else:
                st.warning(f"Q{i+1}: Not answered.")

        st.markdown(f"### Score: {score} / {len(mcqs)}")