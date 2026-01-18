import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="DECA Quiz", layout="wide")

# Initialize session state
if "questions" not in st.session_state:
    st.session_state.questions = []
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "current_page" not in st.session_state:
    st.session_state.current_page = 0
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "pdf_loaded" not in st.session_state:
    st.session_state.pdf_loaded = False

def extract_questions_and_answers(pdf_file):
    """Extract questions and answers from PDF"""
    questions = []
    answer_key = {}
    explanations = {}
    
    with pdfplumber.open(pdf_file) as pdf:
        text = "\n".join([page.extract_text() for page in pdf.pages])
    
    # Split by "KEY" to separate questions from answer key
    parts = text.split("KEY")
    questions_text = parts[0] if len(parts) > 0 else text
    answer_text = parts[1] if len(parts) > 1 else ""
    
    # Extract questions
    question_pattern = r'(\d+)\.\s+(.*?)(?=\n[A-D]\.|$)'
    choice_pattern = r'([A-D])\.\s+(.*?)(?=\n[A-D]\.|$|\n\d+\.)'
    
    current_q = None
    lines = questions_text.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Check if this is a question start
        match = re.match(r'^(\d+)\.\s+(.+)', line)
        if match:
            q_num = int(match.group(1))
            q_text = match.group(2)
            
            # Collect full question text (may span multiple lines)
            j = i + 1
            while j < len(lines) and not re.match(r'^[A-D]\.\s', lines[j].strip()):
                if lines[j].strip():
                    q_text += " " + lines[j].strip()
                j += 1
            
            current_q = {
                "number": q_num,
                "text": q_text.strip(),
                "choices": {},
                "correct": None,
                "explanation": ""
            }
            
            # Extract choices for this question
            for k in range(j, min(j + 5, len(lines))):
                choice_match = re.match(r'^([A-D])\.\s+(.+)', lines[k].strip())
                if choice_match:
                    choice_letter = choice_match.group(1)
                    choice_text = choice_match.group(2)
                    
                    # Collect multi-line choices
                    m = k + 1
                    while m < len(lines) and not re.match(r'^[A-D]\.\s', lines[m].strip()) and not re.match(r'^\d+\.', lines[m].strip()):
                        if lines[m].strip():
                            choice_text += " " + lines[m].strip()
                        m += 1
                    
                    current_q["choices"][choice_letter] = choice_text.strip()
                elif not choice_match and lines[k].strip() and not re.match(r'^\d+\.', lines[k].strip()):
                    break
            
            if current_q["choices"]:
                questions.append(current_q)
    
    # Extract answer key and explanations
    if answer_text:
        # Find answer key section (usually starts with question numbers)
        answer_lines = answer_text.split('\n')
        current_explanation = ""
        
        for line in answer_lines:
            line = line.strip()
            if not line:
                continue
            
            # Match answer line like "1. A"
            answer_match = re.match(r'^(\d+)\.\s+([A-D])', line)
            if answer_match:
                q_num = int(answer_match.group(1))
                answer = answer_match.group(2)
                answer_key[q_num] = answer
                current_explanation = ""
            elif q_num in answer_key and line and not re.match(r'^\d+\.', line):
                # This is part of the explanation
                current_explanation += " " + line
                explanations[q_num] = current_explanation.strip()
    
    # Assign answers and explanations to questions
    for q in questions:
        q["correct"] = answer_key.get(q["number"], None)
        q["explanation"] = explanations.get(q["number"], "No explanation available")
    
    return questions

def calculate_score(questions, answers):
    """Calculate score and get wrong answers"""
    correct = 0
    wrong = []
    
    for q in questions:
        user_ans = answers.get(q["number"])
        if user_ans == q["correct"]:
            correct += 1
        else:
            wrong.append({
                "number": q["number"],
                "question": q["text"],
                "your_answer": user_ans or "Not answered",
                "correct_answer": q["correct"],
                "explanation": q["explanation"]
            })
    
    score = (correct / len(questions)) * 100 if questions else 0
    return score, wrong

# Sidebar for file upload
st.sidebar.title("📚 DECA Quiz")

uploaded_file = st.sidebar.file_uploader("Upload PDF Exam", type=["pdf"])

if uploaded_file and not st.session_state.pdf_loaded:
    with st.spinner("Parsing PDF..."):
        st.session_state.questions = extract_questions_and_answers(uploaded_file)
        st.session_state.pdf_loaded = True
        st.session_state.user_answers = {}
        st.session_state.quiz_submitted = False
        st.session_state.current_page = 0
    st.sidebar.success(f"✅ Loaded {len(st.session_state.questions)} questions")

if st.session_state.pdf_loaded and not st.session_state.quiz_submitted:
    st.title("🎯 DECA Finance Cluster Exam")
    
    questions = st.session_state.questions
    questions_per_page = 10
    total_pages = (len(questions) + questions_per_page - 1) // questions_per_page
    page = st.session_state.current_page
    
    start_idx = page * questions_per_page
    end_idx = min(start_idx + questions_per_page, len(questions))
    page_questions = questions[start_idx:end_idx]
    
    # Progress indicator
    st.markdown(f"### Question {start_idx + 1} - {end_idx} of {len(questions)}")
    st.progress((end_idx) / len(questions))
    
    # Display questions
    for q in page_questions:
        st.markdown(f"### {q['number']}. {q['text']}")
        
        selected = st.radio(
            "Select your answer:",
            options=list(q['choices'].keys()),
            format_func=lambda x: f"{x} - {q['choices'][x]}",
            key=f"q_{q['number']}",
            index=None
        )
        
        if selected:
            st.session_state.user_answers[q['number']] = selected
        
        st.divider()
    
    # Navigation buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if page > 0:
            if st.button("⬅️ Previous"):
                st.session_state.current_page -= 1
                st.rerun()
    
    with col2:
        st.write(f"Page {page + 1} of {total_pages}")
    
    with col3:
        if page < total_pages - 1:
            if st.button("Next ➡️"):
                st.session_state.current_page += 1
                st.rerun()
    
    st.divider()
    
    # Submit button
    if st.button("✅ Submit Quiz", type="primary", use_container_width=True):
        if len(st.session_state.user_answers) == len(questions):
            st.session_state.quiz_submitted = True
            st.rerun()
        else:
            st.warning(f"⚠️ Please answer all {len(questions)} questions before submitting.")

elif st.session_state.quiz_submitted:
    st.title("📊 Quiz Results")
    
    questions = st.session_state.questions
    score, wrong_answers = calculate_score(questions, st.session_state.user_answers)
    
    # Score display
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Your Score", f"{score:.1f}%")
    with col2:
        st.metric("Correct", len(questions) - len(wrong_answers))
    with col3:
        st.metric("Incorrect", len(wrong_answers))
    
    st.divider()
    
    # Wrong answers with explanations
    if wrong_answers:
        st.subheader("❌ Wrong Answers")
        
        for wrong in wrong_answers:
            with st.expander(f"Question {wrong['number']}: {wrong['question'][:60]}..."):
                st.markdown(f"**Your Answer:** {wrong['your_answer']}")
                st.markdown(f"**Correct Answer:** {wrong['correct_answer']}")
                st.markdown(f"**Explanation:** {wrong['explanation']}")
    else:
        st.success("🎉 Perfect Score! You got all questions correct!")
    
    # Reset button
    if st.button("🔄 Retake Quiz", type="secondary", use_container_width=True):
        st.session_state.quiz_submitted = False
        st.session_state.user_answers = {}
        st.session_state.current_page = 0
        st.rerun()

else:
    st.title("📚 DECA Quiz Platform")
    st.info("👈 Upload a PDF exam from the sidebar to get started!")