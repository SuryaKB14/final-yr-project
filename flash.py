import streamlit as st
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from pypdf import PdfReader

# Load environment variables
load_dotenv()

# Initialize Gemini model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    google_api_key=os.getenv("GEMINI_API_KEY")
)

st.title("📚 AI Flashcard Generator")

# PDF Upload Section
st.subheader("📄 Upload Your Study Materials")
uploaded_files = st.file_uploader(
    "Upload one or more PDF files",
    type=["pdf"],
    accept_multiple_files=True
)

# Function to extract text from PDFs
def extract_text_from_pdfs(files):
    combined_text = ""
    for file in files:
        reader = PdfReader(file)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                combined_text += text + "\n"
    return combined_text.strip()


# Flashcard generator function
def generate_flashcards_from_pdf(pdf_text, difficulty, num_cards, language="English"):

    translation_instruction = ""
    if language.lower() != "english":
        translation_instruction = f"Translate both sides to {language}."

    # Prevent context overflow
    max_chars = 40000
    if len(pdf_text) > max_chars:
        pdf_text = pdf_text[:max_chars] + "\n...[content truncated]"

    prompt = f"""
    Based ONLY on the following study material, create {num_cards} flashcards at {difficulty} level.
    {translation_instruction}

    Study Material:
    \"\"\"
    {pdf_text}
    \"\"\"

    Format each card as:

    Q: [Clear question]
    A: [Concise answer]

    Include:
    - Key terms and definitions
    - Important concepts
    - Examples if useful
    - Mnemonics where helpful
    """

    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


# Only show settings if PDFs uploaded
if uploaded_files:

    st.success(f"✅ {len(uploaded_files)} PDF(s) uploaded successfully!")

    st.subheader("⚙️ Flashcard Settings")

    difficulty = st.selectbox(
        "Difficulty Level",
        ["Beginner", "Intermediate", "Advanced"]
    )

    num_cards = st.slider(
        "Number Of Cards",
        min_value=2,
        max_value=20,
        value=5
    )

    language = st.text_input(
        "Language",
        value="English"
    )

    if st.button("Generate Flashcards"):

        with st.spinner("📖 Extracting text from PDFs..."):
            pdf_text = extract_text_from_pdfs(uploaded_files)

        if not pdf_text:
            st.error("❌ Could not extract text from PDFs.")
        else:

            st.write(f"📄 Extracted {len(pdf_text)} characters")

            with st.spinner("🧠 Generating flashcards..."):
                flashcards = generate_flashcards_from_pdf(
                    pdf_text,
                    difficulty,
                    num_cards,
                    language
                )

            st.session_state.flashcards = flashcards

# Display flashcards if available
if "flashcards" in st.session_state:

    st.subheader("🧠 Your Flashcards")

    st.markdown(st.session_state.flashcards)

else:
    st.info("👆 Please upload at least one PDF to get started.")