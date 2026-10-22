import streamlit as st
import requests
import json
import os
import uuid
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==================== CONFIGURATION ====================
st.set_page_config(
    page_title="AI Buddy | Smart Study Assistant",
    page_icon="🤖",
    layout="wide"
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(APP_DIR, "chat_history.json")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2:1b"

SYSTEM_PROMPT = """
You are AI Buddy, a helpful AI study assistant for MCA students.
Explain concepts in simple English.
Give accurate, beginner-friendly explanations.
For programming questions, provide properly formatted code
and explain the expected output.
Use headings and examples when helpful.
If you are unsure, say so instead of inventing facts.
"""

# ==================== HELPER FOR PDF GENERATION ====================
def generate_pdf(text_content):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    
    custom_style = ParagraphStyle(
        'PDFStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        spaceAfter=8
    )
    
    story = []
    paragraphs = text_content.split('\n')
    for p in paragraphs:
        if p.strip():
            clean_text = p.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Paragraph(clean_text, custom_style))
        else:
            story.append(Spacer(1, 6))
            
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==================== DATA MANAGEMENT ====================
def load_data():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, dict):
                conversations = data.get("conversations", [])
                if isinstance(conversations, list):
                    return {"conversations": conversations}

            if isinstance(data, list) and data:
                return {
                    "conversations": [{
                        "id": str(uuid.uuid4()),
                        "title": "Previous Chat",
                        "created": datetime.now().strftime("%d %b %Y, %I:%M %p"),
                        "messages": data
                    }]
                }
        except (json.JSONDecodeError, OSError):
            pass

    return {"conversations": []}

def save_data():
    temp_file = HISTORY_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(st.session_state.chat_data, file, ensure_ascii=False, indent=2)
    os.replace(temp_file, HISTORY_FILE)

def create_chat():
    chat = {
        "id": str(uuid.uuid4()),
        "title": "New Chat",
        "created": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "messages": []
    }
    st.session_state.chat_data["conversations"].insert(0, chat)
    st.session_state.active_chat_id = chat["id"]
    save_data()

def get_active_chat():
    for chat in st.session_state.chat_data["conversations"]:
        if chat["id"] == st.session_state.active_chat_id:
            return chat
    create_chat()
    return st.session_state.chat_data["conversations"][0]

# ==================== OLLAMA AI ====================
def ask_ollama(messages, json_mode=False):
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "stream": False,
        "options": {"temperature": 0.3}
    }
    if json_mode:
        payload["format"] = "json"

    response = requests.post(OLLAMA_URL, json=payload, timeout=240)
    response.raise_for_status()
    return response.json()["message"]["content"]

def ask_ollama_stream(messages):
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "stream": True,
        "options": {"temperature": 0.3}
    }
    response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=240)
    response.raise_for_status()

    for line in response.iter_lines():
        if line:
            chunk = json.loads(line.decode("utf-8"))
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content

def show_ai_error(error):
    if isinstance(error, requests.exceptions.ConnectionError):
        st.error("Ollama connect hot nahiye. Ollama application start kara ani terminal madhye 'ollama list' check kara.")
    elif isinstance(error, requests.exceptions.Timeout):
        st.error("AI response la jast vel lagat aahe. Punha try kara.")
    elif isinstance(error, requests.exceptions.HTTPError):
        st.error("Ollama API error. Model installed aahe ka check kara: ollama list")
    else:
        st.error(f"Something went wrong: {error}")

def generate_quiz(topic, count, difficulty):
    prompt = f"""
Create {count} multiple-choice questions for an MCA student.
Topic: {topic}
Difficulty: {difficulty}
Return ONLY valid JSON in this exact structure:
{{
  "questions": [
    {{
      "question": "Question text",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Exact correct option text",
      "explanation": "Short explanation"
    }}
  ]
}}
Rules:
- Exactly {count} questions.
- Four options per question.
- Only one correct answer per question.
- The answer must exactly match one of the options.
"""
    raw = ask_ollama([{"role": "user", "content": prompt}], json_mode=True)
    data = json.loads(raw)
    questions = data.get("questions", [])

    if not questions:
        raise ValueError("AI did not generate any questions.")

    for q in questions:
        if (
            not isinstance(q.get("question"), str)
            or not isinstance(q.get("options"), list)
            or len(q["options"]) != 4
            or q.get("answer") not in q["options"]
        ):
            raise ValueError("Quiz format is invalid. Please generate it again.")

    return questions[:count]

# ==================== SESSION STATE ====================
if "chat_data" not in st.session_state:
    st.session_state.chat_data = load_data()

if "active_chat_id" not in st.session_state:
    conversations = st.session_state.chat_data["conversations"]
    if conversations:
        st.session_state.active_chat_id = conversations[0]["id"]
    else:
        create_chat()

if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None

if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False

# ==================== DESIGN ====================
st.markdown("""
<style>
.stApp { background-color: #f4f7fc; }
h1 { color: #1d4ed8; }
.stButton > button { border-radius: 10px; min-height: 40px; }
[data-testid="stChatMessage"] { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

# ==================== SIDEBAR ====================
with st.sidebar:
    st.title("🤖 AI Buddy")
    st.caption("Your Smart Study Assistant")
    st.divider()

    page = st.radio(
        "Navigation",
        ["💬 AI Chat", "📚 Study Notes", "💻 Code Helper", "📝 Quiz Generator"],
        key="navigation"
    )

    st.divider()
    st.subheader("🕘 Chat History")

    if st.button("➕ New Chat", use_container_width=True):
        create_chat()
        st.rerun()

    conversations = st.session_state.chat_data["conversations"]

    if conversations:
        chat_options = {
            chat["id"]: (chat.get("title", "Chat") + " — " + chat.get("created", ""))
            for chat in conversations
        }
        ids = list(chat_options.keys())

        if st.session_state.active_chat_id not in ids:
            st.session_state.active_chat_id = ids[0]

        selected_id = st.selectbox(
            "Open previous chat",
            options=ids,
            format_func=lambda x: chat_options[x],
            index=ids.index(st.session_state.active_chat_id),
            key="history_selector"
        )

        if selected_id != st.session_state.active_chat_id:
            st.session_state.active_chat_id = selected_id
            st.rerun()

        if st.button("🗑️ Delete Current Chat", use_container_width=True):
            st.session_state.chat_data["conversations"] = [
                c for c in st.session_state.chat_data["conversations"]
                if c["id"] != st.session_state.active_chat_id
            ]
            remaining = st.session_state.chat_data["conversations"]
            if remaining:
                st.session_state.active_chat_id = remaining[0]["id"]
                save_data()
            else:
                st.session_state.active_chat_id = None
                create_chat()
            st.rerun()

        if st.button("⚠️ Clear All History", use_container_width=True):
            st.session_state.chat_data["conversations"] = []
            create_chat()
            st.rerun()
    else:
        st.info("No previous chats.")

    st.divider()
    st.caption("Model: llama3.2:1b")
    st.caption("Runs locally using Ollama")

# ==================== HEADER ====================
st.title("🤖 AI Buddy")
st.subheader("Your Smart AI Study Assistant")
st.caption("AI Chat • Study Notes • Code Helper • Quiz Generator")
st.divider()

# ==================== AI CHAT ====================
if page == "💬 AI Chat":
    chat = get_active_chat()
    st.header("💬 " + chat.get("title", "New Chat"))
    st.write("Ask questions, learn concepts and explore programming.")

    for message in chat.get("messages", []):
        if message.get("role") in ("user", "assistant"):
            with st.chat_message(message["role"]):
                st.markdown(message.get("content", ""))

    prompt = st.chat_input("Ask AI Buddy anything...")

    if prompt:
        chat["messages"].append({"role": "user", "content": prompt})
        if chat.get("title") == "New Chat":
            chat["title"] = prompt[:35]
        save_data()

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            try:
                full_response = st.write_stream(ask_ollama_stream(chat["messages"]))
                chat["messages"].append({"role": "assistant", "content": full_response})
                save_data()
            except Exception as error:
                show_ai_error(error)

        st.rerun()

# ==================== STUDY NOTES ====================
elif page == "📚 Study Notes":
    st.header("📚 AI Study Notes Generator")
    topic = st.text_input("Enter your topic", placeholder="Example: Python Loops")
    level = st.selectbox("Difficulty Level", ["Beginner", "Intermediate", "Advanced"])
    language = st.selectbox("Notes Language", ["Simple English", "Marathi", "Hindi"])

    if st.button("📝 Generate Study Notes", use_container_width=True):
        if topic.strip():
            prompt = f"""
Create complete study notes for an MCA student.
Topic: {topic}
Difficulty: {level}
Language: {language}
Include Introduction, important concepts, simple explanations, practical examples, Python example and expected output, advantages/applications, and short conclusion.
"""
            try:
                with st.spinner("Preparing your notes..."):
                    notes = ask_ollama([{"role": "user", "content": prompt}])
                st.session_state["last_notes"] = notes
                st.session_state["last_notes_topic"] = topic
            except Exception as error:
                show_ai_error(error)
        else:
            st.warning("Please enter a topic.")

    if st.session_state.get("last_notes"):
        st.divider()
        st.subheader("📖 Notes: " + st.session_state.get("last_notes_topic", "Study Topic"))
        st.markdown(st.session_state["last_notes"])

        col1, col2, col3 = st.columns(3)
        pdf_data = generate_pdf(st.session_state["last_notes"])
        col1.download_button("⬇️ Download PDF (.pdf)", data=pdf_data, file_name="AI_Buddy_Study_Notes.pdf", mime="application/pdf", use_container_width=True)
        col2.download_button("⬇️ Download Markdown (.md)", data=st.session_state["last_notes"], file_name="AI_Buddy_Study_Notes.md", mime="text/markdown", use_container_width=True)
        col3.download_button("⬇️ Download Text (.txt)", data=st.session_state["last_notes"], file_name="AI_Buddy_Study_Notes.txt", mime="text/plain", use_container_width=True)

# ==================== CODE HELPER ====================
elif page == "💻 Code Helper":
    st.header("💻 AI Code Helper")
    language = st.selectbox("Programming Language", ["Python", "Java", "C", "C++", "JavaScript", "C#", "SQL"])
    task = st.selectbox("What do you need?", ["Write a program", "Explain code", "Find and fix an error", "Show an example"])
    code_input = st.text_area("Describe your task or paste your code", placeholder="Example: Write a program to add two numbers", height=150)

    if st.button("🚀 Generate Code", use_container_width=True):
        if code_input.strip():
            prompt = f"""
You are a programming tutor.
Language: {language}
Task: {task}
User request or code: {code_input}
Provide correct code block, simple explanation, expected output, and common mistakes.
"""
            try:
                with st.spinner("Preparing your solution..."):
                    result = ask_ollama([{"role": "user", "content": prompt}])
                st.markdown(result)
                pdf_data = generate_pdf(result)
                st.download_button("⬇️ Download PDF Response", data=pdf_data, file_name="AI_Buddy_Code_Solution.pdf", mime="application/pdf")
            except Exception as error:
                show_ai_error(error)
        else:
            st.warning("Describe your programming task first.")

# ==================== QUIZ GENERATOR ====================
elif page == "📝 Quiz Generator":
    st.header("📝 AI Quiz Generator")
    st.write("Generate MCQs and test your knowledge.")

    topic = st.text_input("Quiz topic", placeholder="Example: Python Variables")
    count = st.selectbox("Number of questions", [3, 5, 10], index=1)
    difficulty = st.selectbox("Quiz difficulty", ["Easy", "Medium", "Hard"])

    if st.button("🎯 Generate Quiz", use_container_width=True):
        if topic.strip():
            try:
                with st.spinner("Creating your quiz..."):
                    questions = generate_quiz(topic, count, difficulty)
                st.session_state.quiz_data = {"topic": topic, "questions": questions}
                st.session_state.quiz_submitted = False
                st.rerun()
            except Exception as error:
                show_ai_error(error)
        else:
            st.warning("Enter a quiz topic first.")

    quiz = st.session_state.quiz_data

    if quiz:
        st.divider()
        st.subheader("Quiz: " + quiz["topic"])

        with st.form("quiz_form"):
            answers = []
            for i, question in enumerate(quiz["questions"]):
                st.markdown(f"**Q{i + 1}. {question['question']}**")
                selected = st.radio("Choose an answer", question["options"], index=None, key=f"quiz_{i}", label_visibility="collapsed")
                answers.append(selected)
                st.divider()

            submitted = st.form_submit_button("✅ Submit Quiz", use_container_width=True)

        if submitted:
            st.session_state.quiz_answers = answers
            st.session_state.quiz_submitted = True

        if st.session_state.quiz_submitted:
            answers = st.session_state.quiz_answers
            questions = quiz["questions"]
            score = sum(1 for i, question in enumerate(questions) if answers[i] == question["answer"])

            st.subheader(f"🏆 Your Score: {score}/{len(questions)}")
            st.progress(score / len(questions))

            for i, question in enumerate(questions):
                correct = answers[i] == question["answer"]
                if correct:
                    st.success(f"Q{i + 1}: Correct!")
                else:
                    st.error(f"Q{i + 1}: Incorrect. Correct answer: {question['answer']}")
                
                explanation = question.get("explanation", "")
                if explanation:
                    st.write(explanation)

            if st.button("🔄 Try Another Quiz"):
                st.session_state.quiz_data = None
                st.session_state.quiz_submitted = False
                st.rerun()

# ==================== FOOTER ====================
st.divider()
st.caption("🤖 AI Buddy | MCA Python Project | Built with Streamlit and Ollama")