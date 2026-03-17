import streamlit as st
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
print(os.getenv("GEMINI_API_KEY"))
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    google_api_key=os.getenv("GEMINI_API_KEY")
)

st.title("AI FLASHCARD GENERATOR")

topic = st.text_input("WHAT TOPIC ARE YOU STUDYING?")
difficulty = st.selectbox("Difficulty level", ["Beginner","Intermediate","Advanced"])
num_cards = st.slider("Number Of Cards",2,20,5)
language = st.text_input("Language")

def generate_flashcards(topic,difficulty,num_cards,language="English"):

    translation_instruction = ""
    if language.lower() != "english":
        translation_instruction = f"Translate both sides to {language}"

    prompt = f"""
    Create {num_cards} study flashcards about {topic} at {difficulty} level.
    {translation_instruction}

    Format each card as:
    Q: [Clear question]
    A: [Concise answer]

    Include:
    - Key terms and definitions
    - Important dates/events (if historical)
    - Examples where applicable
    - Mnemonics for memorization
    """

    response = llm.invoke(prompt)
    return response.content

if st.button("Generate Flashcards"):
    if topic:
        flashcards = generate_flashcards(topic,difficulty,num_cards,language)
        st.markdown(flashcards)
    else:
        st.warning("Please enter a topic.")