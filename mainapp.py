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
            color: #1f2937;
        }
        .correct-answer-box {
            background: #ecfdf5;
            border-left: 4px solid #10b981;
            padding: 1rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            color: #1f2937;
        }
        .explanation-box {
            background: #f0f9ff;
            border-left: 4px solid #333;
            padding: 1rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            font-size: 0.95rem;
            color: #1f2937;
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
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "start_question" not in st.session_state:
    st.session_state.start_question = 1
if "num_questions" not in st.session_state:
    st.session_state.num_questions = None
if "quiz_questions" not in st.session_state:
    st.session_state.quiz_questions = []

def extract_questions_and_answers(pdf_file):
    """Extract questions and answers from PDF"""
    questions = []
    answer_key = {}
    explanations = {}
    
    with pdfplumber.open(pdf_file) as pdf:
        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    
    # Split by looking for the answer key section
    # The answer key appears after pages with "EXAM—KEY" or "EXAM-KEY" in the header
    key_match = re.search(r'EXAM[—-]KEY\s+\d+', text)
    
    if key_match:
        # Split at the first occurrence of EXAM—KEY or EXAM-KEY
        questions_text = text[:key_match.start()]
        answer_text = text[key_match.start():]
    else:
        # Fallback: try splitting by "KEY" alone
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
    
    # Extract answer key and explanations - IMPROVED VERSION
    if answer_text:
        answer_lines = answer_text.split('\n')
        current_q_num = None
        current_explanation = ""
        
        for line in answer_lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Skip copyright/footer/source lines
            if (line_stripped.startswith('Copyright') or 
                (line_stripped.startswith('Test') and 'EXAM' in line_stripped) or
                line_stripped.startswith('SOURCE:')):
                continue
            
            # Match answer line - capture answer and any text after it
            # Format: "1. A" or "1. A Heat and lighting costs..."
            answer_match = re.match(r'^(\d+)\.\s+([A-D])(?:\s+(.*))?$', line_stripped)
            if answer_match:
                # Save previous explanation before starting new one
                if current_q_num is not None and current_explanation:
                    explanations[current_q_num] = current_explanation.strip()
                
                current_q_num = int(answer_match.group(1))
                answer_key[current_q_num] = answer_match.group(2)
                
                # Start explanation with any text on the same line as the answer
                explanation_start = answer_match.group(3)
                current_explanation = explanation_start if explanation_start else ""
            elif current_q_num is not None and line_stripped:
                # Check if this is a new answer line
                if not re.match(r'^\d+\.\s+[A-D]', line_stripped):
                    # This is part of the explanation
                    if current_explanation:
                        current_explanation += " " + line_stripped
                    else:
                        current_explanation = line_stripped
        
        # Don't forget the last explanation
        if current_q_num is not None and current_explanation:
            explanations[current_q_num] = current_explanation.strip()
    
    # Debug: Print what we found
    print(f"Found {len(questions)} questions")
    print(f"Found {len(answer_key)} answers in key")
    print(f"Found {len(explanations)} explanations")
    if len(answer_key) > 0:
        print(f"Sample answers: {list(answer_key.items())[:5]}")
    
    # Assign answers and explanations to questions
    for q in questions:
        q["correct"] = answer_key.get(q["number"], None)
        q["explanation"] = explanations.get(q["number"], "No explanation available.")
        
        # Debug first few questions
        if q["number"] <= 3:
            print(f"Q{q['number']}: correct={q['correct']}, has_explanation={len(q['explanation']) > 25}")
    
    return questions

def calculate_score(questions, answers):
    """Calculate score and get wrong answers - unanswered questions count as wrong"""
    correct = 0
    wrong = []
    unanswered = 0
    
    for q in questions:
        user_ans = answers.get(q["number"])
        # Check if question was answered AND if it's correct
        if user_ans is not None and user_ans == q["correct"]:
            correct += 1
        else:
            # Both unanswered and incorrect answers are marked as wrong
            if user_ans is None:
                unanswered += 1
                wrong.append({
                    "number": q["number"],
                    "question": q["text"],
                    "your_answer": "Not answered",
                    "correct_answer": q["correct"],
                    "explanation": q["explanation"],
                    "choice_text": q["choices"].get(q["correct"], "") if q["correct"] else "",
                    "is_unanswered": True
                })
            else:
                # Incorrect answer
                wrong.append({
                    "number": q["number"],
                    "question": q["text"],
                    "your_answer": user_ans,
                    "correct_answer": q["correct"],
                    "explanation": q["explanation"],
                    "choice_text": q["choices"].get(q["correct"], "") if q["correct"] else "",
                    "is_unanswered": False
                })
    
    # Calculate score based on total questions (correct / total * 100)
    total = len(questions)
    score = (correct / total * 100) if total > 0 else 0
    
    return score, wrong, unanswered

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
            st.session_state.quiz_started = False
        st.success(f"Loaded {len(st.session_state.questions)} questions")
        st.rerun()

elif not st.session_state.quiz_started:
    # Quiz configuration screen
    st.markdown('<div style="text-align: center; padding: 2rem;">', unsafe_allow_html=True)
    st.markdown("# Quiz Configuration")
    st.markdown("### Customize your quiz")
    st.markdown('</div>', unsafe_allow_html=True)
    
    total_questions = len(st.session_state.questions)
    
    col1, col2 = st.columns(2)
    
    with col1:
        start_q = st.number_input(
            "Start from question:",
            min_value=1,
            max_value=total_questions,
            value=1,
            step=1
        )
    
    with col2:
        num_q = st.number_input(
            "Number of questions:",
            min_value=1,
            max_value=total_questions - start_q + 1,
            value=min(10, total_questions - start_q + 1),
            step=1
        )
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Start Quiz", use_container_width=True, type="primary"):
            st.session_state.start_question = start_q
            st.session_state.num_questions = num_q
            # Filter questions for this quiz
            all_questions = st.session_state.questions
            st.session_state.quiz_questions = [q for q in all_questions if start_q <= q["number"] <= start_q + num_q - 1]
            st.session_state.quiz_submitted = False
            st.session_state.show_results = False
            st.session_state.current_question = 0
            st.session_state.quiz_started = True
            st.session_state.user_answers = {}
            st.rerun()
    
    with col2:
        if st.button("Upload Different PDF", use_container_width=True):
            st.session_state.pdf_loaded = False
            st.session_state.questions = []
            st.session_state.user_answers = {}
            st.session_state.current_question = 0
            st.session_state.quiz_submitted = False
            st.session_state.show_results = False
            st.session_state.quiz_started = False
            st.rerun()

elif st.session_state.quiz_submitted:
    questions = st.session_state.quiz_questions
    score, wrong_answers, unanswered_count = calculate_score(questions, st.session_state.user_answers)
    
    if st.session_state.show_results:
        # Score display
        st.markdown(f"""
            <div style="text-align: center;">
                <h1>Quiz Results</h1>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
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
            incorrect_count = len([w for w in wrong_answers if not w.get("is_unanswered", False)])
            st.markdown(f"""
                <div class="incorrect-card">
                    <div style="font-size: 2.5rem; font-weight: bold;">{incorrect_count}</div>
                    <div style="font-size: 0.9rem; margin-top: 0.5rem;">Incorrect</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
                <div style="background: #fef3c7; color: #92400e; padding: 1.5rem; border-radius: 12px; text-align: center;">
                    <div style="font-size: 2.5rem; font-weight: bold;">{unanswered_count}</div>
                    <div style="font-size: 0.9rem; margin-top: 0.5rem;">Unanswered</div>
                </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        # Wrong answers with explanations
        if wrong_answers:
            st.markdown('<h2>Review Your Mistakes</h2>', unsafe_allow_html=True)
            
            for idx, wrong in enumerate(wrong_answers, 1):
                with st.expander(f"Question {wrong['number']}: {wrong['question'][:70]}...", expanded=(idx==1 if len(wrong_answers)==1 else False)):
                    st.markdown(f"<p style='color: white;'><strong>Question {wrong['number']}:</strong> {wrong['question']}</p>", unsafe_allow_html=True)
                    st.divider()
                    
                    st.markdown(f'<div class="wrong-answer-box"><strong>Your Answer:</strong> {wrong["your_answer"]}</div>', unsafe_allow_html=True)
                    
                    if wrong["correct_answer"]:
                        st.markdown(f'<div class="correct-answer-box"><strong>Correct Answer:</strong> {wrong["correct_answer"]} - {wrong["choice_text"]}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="correct-answer-box"><strong>Correct Answer:</strong> Not available in answer key</div>', unsafe_allow_html=True)
                    
                    st.markdown(f'<div class="explanation-box"><strong>Explanation:</strong> {wrong["explanation"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="perfect-score">
                    <div style="font-size: 4rem;">🎉</div>
                    <h2 style="color: #065f46; margin: 1rem 0;">Perfect Score!</h2>
                    <p>You got all questions correct!</p>
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
            if st.button("New Quiz", use_container_width=True):
                st.session_state.quiz_started = False
                st.session_state.quiz_submitted = False
                st.session_state.user_answers = {}
                st.session_state.current_question = 0
                st.session_state.show_results = False
                st.rerun()
    
    else:
        # Show quiz with results banner
        questions = st.session_state.quiz_questions
        current_idx = st.session_state.current_question
        q = questions[current_idx]
        
        # Show current score banner
        answered = len(st.session_state.user_answers)
        current_score, _, _ = calculate_score(questions, st.session_state.user_answers)
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
    questions = st.session_state.quiz_questions
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
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if st.button("Previous", use_container_width=True, disabled=(current_idx == 0)):
            st.session_state.current_question -= 1
            st.rerun()
    
    with col2:
        st.markdown(f"<div style='text-align: center; padding: 0.5rem;'><strong>Question {current_idx + 1} out of {len(questions)}</strong></div>", unsafe_allow_html=True)
    
    with col3:
        if st.button("Submit", use_container_width=True, type="primary"):
            st.session_state.quiz_submitted = True
            st.session_state.show_results = True
            st.rerun()
    
    with col4:
        if st.button("Next", use_container_width=True, disabled=(current_idx == len(questions) - 1)):
            st.session_state.current_question += 1
            st.rerun()