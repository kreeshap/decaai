import streamlit as st
import pdfplumber
import re
import pandas as pd

st.set_page_config(page_title="DECA Quiz", layout="centered", initial_sidebar_state="collapsed")

# Custom CSS for card styling
st.markdown("""
    <style>
        .question-card {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin: 0 auto;
        }
        .choice-button {
            width: 100%;
            padding: 1rem;
            margin: 0.5rem 0;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            background: white;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
        }
        .choice-button:hover {
            border-color: #9ca3af;
            background: #f9fafb;
        }
        .choice-button.selected {
            border-color: #333;
            background: #f3f4f6;
        }
        .score-card {
            background: #f3f4f6;
            color: #333;
            padding: 2rem;
            border-radius: 12px;
            text-align: center;
            margin: 1rem 0;
        }
        .correct-card {
            background: #ecfdf5;
            color: #065f46;
            padding: 1.5rem;
            border-radius: 12px;
            text-align: center;
        }
        .incorrect-card {
            background: #fef2f2;
            color: #991b1b;
            padding: 1.5rem;
            border-radius: 12px;
            text-align: center;
        }
        .wrong-answer-box {
            background: #fef2f2;
            border-left: 4px solid #ef4444;
            padding: 1.5rem;
            border-radius: 8px;
            margin: 1rem 0;
        }
        .explanation-box {
            background: #f0f9ff;
            border-left: 4px solid #333;
            padding: 1rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            font-size: 0.95rem;
        }
        .perfect-score {
            text-align: center;
            padding: 3rem 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "questions" not in st.session_state:
    st.session_state.questions = []
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "current_question" not in st.session_state:
    st.session_state.current_question = 0
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "pdf_loaded" not in st.session_state:
    st.session_state.pdf_loaded = False
if "show_results" not in st.session_state:
    st.session_state.show_results = False

def extract_questions_and_answers(pdf_file):
    """Extract questions and answers from PDF"""
    questions = []
    answer_key = {}
    explanations = {}
    
    with pdfplumber.open(pdf_file) as pdf:
        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    
    # Split by "KEY" to separate questions from answer key
    parts = text.split("KEY")
    questions_text = parts[0] if len(parts) > 0 else text
    answer_text = parts[1] if len(parts) > 1 else ""
    
    lines = questions_text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip lines that are purely copyright/footer info
        if not line or line.startswith('Copyright') or (line.startswith('Test') and 'EXAM' in line) or line.startswith('Booklet'):
            i += 1
            continue
        
        # Check if this is a question start (format: "1. Question text?")
        match = re.match(r'^(\d+)\.\s+(.+)', line)
        if match:
            q_num = int(match.group(1))
            q_text = match.group(2)
            
            # Collect full question text (may span multiple lines)
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if re.match(r'^[A-D]\.\s', next_line):
                    break
                if next_line and not re.match(r'^\d+\.', next_line):
                    # Only skip if it's a pure copyright/footer line
                    if not (next_line.startswith('Copyright') or (next_line.startswith('Test') and 'EXAM' in next_line)):
                        q_text += " " + next_line
                j += 1
            
            current_q = {
                "number": q_num,
                "text": q_text.strip(),
                "choices": {},
                "correct": None,
                "explanation": ""
            }
            
            # Extract choices for this question
            choice_count = 0
            while j < len(lines) and choice_count < 4:
                choice_line = lines[j].strip()
                choice_match = re.match(r'^([A-D])\.\s+(.+)', choice_line)
                if choice_match:
                    choice_letter = choice_match.group(1)
                    choice_text = choice_match.group(2)
                    
                    # Collect multi-line choices
                    k = j + 1
                    while k < len(lines):
                        continuation = lines[k].strip()
                        if re.match(r'^[A-D]\.\s', continuation) or re.match(r'^\d+\.', continuation):
                            break
                        if continuation:
                            # Only skip if it's a pure copyright/footer line
                            if not (continuation.startswith('Copyright') or (continuation.startswith('Test') and 'EXAM' in continuation)):
                                choice_text += " " + continuation
                        k += 1
                    
                    current_q["choices"][choice_letter] = choice_text.strip()
                    choice_count += 1
                    j = k
                else:
                    break
            
            if current_q["choices"] and len(current_q["choices"]) == 4:
                questions.append(current_q)
        
        i += 1
    
    # Extract answer key and explanations
    if answer_text:
        answer_lines = answer_text.split('\n')
        current_q_num = None
        current_explanation = ""
        
        for line in answer_lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Skip copyright/footer lines
            if line_stripped.startswith('Copyright') or (line_stripped.startswith('Test') and 'EXAM' in line_stripped):
                continue
            
            # Match answer line like "1. A"
            answer_match = re.match(r'^(\d+)\.\s+([A-D])', line_stripped)
            if answer_match:
                if current_q_num and current_explanation:
                    explanations[current_q_num] = current_explanation.strip()
                
                current_q_num = int(answer_match.group(1))
                answer_key[current_q_num] = answer_match.group(2)
                current_explanation = ""
            elif current_q_num and line_stripped and not re.match(r'^\d+\.', line_stripped):
                # This is part of the explanation
                if current_explanation:
                    current_explanation += " " + line_stripped
                else:
                    current_explanation = line_stripped
        
        # Don't forget the last explanation
        if current_q_num and current_explanation:
            explanations[current_q_num] = current_explanation.strip()
    
    # Assign answers and explanations to questions
    for q in questions:
        q["correct"] = answer_key.get(q["number"], None)
        q["explanation"] = explanations.get(q["number"], "No explanation available.")
    
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
                "explanation": q["explanation"],
                "choice_text": q["choices"].get(q["correct"], "")
            })
    
    score = (correct / len(questions)) * 100 if questions else 0
    return score, wrong

# Main app
if not st.session_state.pdf_loaded:
    st.markdown('<div style="text-align: center; padding: 2rem;">', unsafe_allow_html=True)
    st.markdown("# DECA Quiz Platform")
    st.markdown("### Upload your DECA exam PDF to get started")
    st.markdown('</div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Upload PDF Exam", type=["pdf"])
    
    if uploaded_file:
        with st.spinner("Parsing PDF..."):
            st.session_state.questions = extract_questions_and_answers(uploaded_file)
            st.session_state.pdf_loaded = True
            st.session_state.user_answers = {}
            st.session_state.quiz_submitted = False
            st.session_state.current_question = 0
        st.success(f"Loaded {len(st.session_state.questions)} questions")
        st.rerun()

elif st.session_state.quiz_submitted:
    questions = st.session_state.questions
    score, wrong_answers = calculate_score(questions, st.session_state.user_answers)
    
    if st.session_state.show_results:
        # Score display
        st.markdown(f"""
            <div style="text-align: center;">
                <h1>Quiz Results</h1>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
                <div class="score-card">
                    <div style="font-size: 2.5rem; font-weight: bold;">{score:.1f}%</div>
                    <div style="font-size: 0.9rem; margin-top: 0.5rem;">Your Score</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
                <div class="correct-card">
                    <div style="font-size: 2.5rem; font-weight: bold;">{len(questions) - len(wrong_answers)}</div>
                    <div style="font-size: 0.9rem; margin-top: 0.5rem;">Correct</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
                <div class="incorrect-card">
                    <div style="font-size: 2.5rem; font-weight: bold;">{len(wrong_answers)}</div>
                    <div style="font-size: 0.9rem; margin-top: 0.5rem;">Incorrect</div>
                </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        # Wrong answers with explanations
        if wrong_answers:
            st.subheader("Review Your Mistakes")
            
            for idx, wrong in enumerate(wrong_answers, 1):
                with st.expander(f"Question {wrong['number']}: {wrong['question'][:70]}...", expanded=(idx==1 if len(wrong_answers)==1 else False)):
                    st.markdown(f"**Question {wrong['number']}:** {wrong['question']}")
                    st.divider()
                    
                    st.markdown(f'<div class="wrong-answer-box"><strong>Your Answer:</strong> {wrong["your_answer"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div style="background: #ecfdf5; border-left: 4px solid #10b981; padding: 1rem; border-radius: 8px; margin: 0.5rem 0;"><strong>Correct Answer:</strong> {wrong["correct_answer"]}</div>', unsafe_allow_html=True)
                    
                    st.markdown(f'<div class="explanation-box"><strong>Explanation:</strong> {wrong["explanation"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="perfect-score">
                    <div style="font-size: 4rem;">Perfect Score!</div>
                    <h2 style="color: #065f46; margin: 1rem 0;">You got all questions correct!</h2>
                </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Continue Quiz", use_container_width=True):
                st.session_state.show_results = False
                st.rerun()
        
        with col2:
            if st.button("Retake Quiz", use_container_width=True):
                st.session_state.quiz_submitted = False
                st.session_state.user_answers = {}
                st.session_state.current_question = 0
                st.session_state.show_results = False
                st.rerun()
        
        with col3:
            if st.button("Upload New PDF", use_container_width=True):
                st.session_state.pdf_loaded = False
                st.session_state.questions = []
                st.session_state.user_answers = {}
                st.session_state.current_question = 0
                st.session_state.quiz_submitted = False
                st.session_state.show_results = False
                st.rerun()
    
    else:
        # Show quiz with results banner
        questions = st.session_state.questions
        current_idx = st.session_state.current_question
        q = questions[current_idx]
        
        # Show current score banner
        answered = len(st.session_state.user_answers)
        current_score, _ = calculate_score(questions, st.session_state.user_answers)
        st.info(f"Progress: {answered}/{len(questions)} answered | Current Score: {current_score:.1f}%")
        
        # Progress bar only
        st.markdown(f"""
            <div style="width: 100%; background: #e5e7eb; border-radius: 10px; height: 8px; overflow: hidden; margin-bottom: 2rem;">
                <div style="width: {((current_idx + 1) / len(questions)) * 100}%; background: #333; height: 100%; border-radius: 10px;"></div>
            </div>
        """, unsafe_allow_html=True)
        
        # Question card
        st.markdown(f"""
            <div class="question-card">
                <h3 style="color: #1f2937; margin-bottom: 1.5rem; font-size: 1.2rem; line-height: 1.5;">
                    {q['text']}
                </h3>
        """, unsafe_allow_html=True)
        
        # Answer options
        selected = st.session_state.user_answers.get(q["number"])
        
        # Get index of currently selected answer
        current_index = None
        if selected:
            try:
                current_index = ['A', 'B', 'C', 'D'].index(selected)
            except:
                current_index = None
        
        choice_option = st.radio(
            "Select your answer:",
            options=['A', 'B', 'C', 'D'],
            format_func=lambda x: f"{x} - {q['choices'].get(x, '')}",
            index=current_index,
            key=f"choice_{q['number']}",
            label_visibility="collapsed"
        )
        
        if choice_option:
            st.session_state.user_answers[q["number"]] = choice_option
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.divider()
        
        # Navigation buttons
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            if st.button("Previous", use_container_width=True, disabled=(current_idx == 0)):
                st.session_state.current_question -= 1
                st.rerun()
        
        with col2:
            st.markdown(f"<div style='text-align: center; padding: 0.5rem;'><strong>Question {current_idx + 1} out of {len(questions)}</strong></div>", unsafe_allow_html=True)
        
        with col3:
            if st.button("View Results", use_container_width=True):
                st.session_state.show_results = True
                st.rerun()
        
        with col4:
            if st.button("Next", use_container_width=True, disabled=(current_idx == len(questions) - 1)):
                st.session_state.current_question += 1
                st.rerun()

else:
    # Quiz interface
    questions = st.session_state.questions
    current_idx = st.session_state.current_question
    q = questions[current_idx]
    
    # Progress bar only
    st.markdown(f"""
        <div style="width: 100%; background: #e5e7eb; border-radius: 10px; height: 8px; overflow: hidden; margin-bottom: 2rem;">
            <div style="width: {((current_idx + 1) / len(questions)) * 100}%; background: #333; height: 100%; border-radius: 10px;"></div>
        </div>
    """, unsafe_allow_html=True)
    
    # Question card
    st.markdown(f"""
        <div class="question-card">
            <h3 style="color: #1f2937; margin-bottom: 1.5rem; font-size: 1.2rem; line-height: 1.5;">
                {q['text']}
            </h3>
    """, unsafe_allow_html=True)
    
    # Answer options
    selected = st.session_state.user_answers.get(q["number"])
    
    # Get index of currently selected answer
    current_index = None
    if selected:
        try:
            current_index = ['A', 'B', 'C', 'D'].index(selected)
        except:
            current_index = None
    
    choice_option = st.radio(
        "Select your answer:",
        options=['A', 'B', 'C', 'D'],
        format_func=lambda x: f"{x} - {q['choices'].get(x, '')}",
        index=current_index,
        key=f"choice_{q['number']}",
        label_visibility="collapsed"
    )
    
    if choice_option:
        st.session_state.user_answers[q["number"]] = choice_option
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.divider()
    
    # Navigation buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("Previous", use_container_width=True, disabled=(current_idx == 0)):
            st.session_state.current_question -= 1
            st.rerun()
    
    with col2:
        st.markdown(f"<div style='text-align: center; padding: 0.5rem;'><strong>Question {current_idx + 1} out of {len(questions)}</strong></div>", unsafe_allow_html=True)
    
    with col3:
        if current_idx == len(questions) - 1:
            if st.button("Submit", use_container_width=True, type="primary"):
                if len(st.session_state.user_answers) == len(questions):
                    st.session_state.quiz_submitted = True
                    st.session_state.show_results = True
                    st.rerun()
                else:
                    st.error(f"Please answer all {len(questions)} questions before submitting.")
        else:
            if st.button("Next", use_container_width=True):
                st.session_state.current_question += 1
                st.rerun()