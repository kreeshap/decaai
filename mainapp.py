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
            padding: 1.5rem;
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

def is_likely_noise(line):
    """Check if a line is likely noise (headers, footers, page numbers, etc.)"""
    line = line.strip()
    if not line:
        return True
    if len(line) < 3:  # Very short lines are likely noise
        return True
    if line.startswith('Copyright'):
        return True
    if line.startswith('Posted online'):
        return True
    if line.startswith('Booklet'):
        return True
    if re.match(r'^Page\s+\d+', line, re.IGNORECASE):
        return True
    # Header patterns like "Test 1229 FINANCE EXAM 1"
    if re.match(r'^Test\s+\d+.*EXAM\s+\d+$', line) and 'KEY' not in line:
        return True
    return False

def parse_two_column_choices(line):
    """
    Parse choices that may be in two-column format like:
    'A. decision. C. privacy.'
    Returns dict of {letter: text} for all choices found on the line
    """
    choices = {}
    # Pattern to match "A. text" or "A) text"
    # We need to be careful to handle multiple choices on one line
    parts = re.findall(r'([A-D])[\.\)]\s+([^A-D]+?)(?=\s+[A-D][\.\)]|$)', line)
    for letter, text in parts:
        choices[letter] = text.strip().rstrip('.')
    return choices

def find_answer_key_split(text):
    """
    Find where the answer key section starts using multiple heuristics.
    Returns (questions_text, answer_text) tuple
    """
    print("\n" + "="*60)
    print("Attempting to locate answer key section...")
    print("="*60)
    
    # Strategy 1: Look for "KEY" in headers (most common)
    key_patterns = [
        r'EXAM[—\-\s]*KEY\s+\d+',  # EXAM—KEY 11, EXAM-KEY 11, EXAM KEY 11
        r'ANSWER\s+KEY',             # ANSWER KEY
        r'\bKEY\b.*\d+',            # KEY followed by page number
    ]
    
    for pattern in key_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            # Use the first match that appears after substantial content
            for match in matches:
                if match.start() > 5000:  # At least 5000 chars of questions
                    print(f"✓ Found answer key using pattern '{pattern}' at position {match.start()}")
                    print(f"  Context: ...{text[match.start()-20:match.start()+50]}...")
                    return text[:match.start()], text[match.start():]
    
    # Strategy 2: Look for sequential answer pattern "1. A\n2. B\n3. C" etc.
    answer_pattern = r'\n\s*1\.\s+[A-D]\s*\n\s*2\.\s+[A-D]\s*\n\s*3\.\s+[A-D]'
    matches = list(re.finditer(answer_pattern, text))
    if matches:
        for match in matches:
            if match.start() > 5000:
                print(f"✓ Found answer key using sequential pattern at position {match.start()}")
                split_pos = text.rfind('\n', match.start()-100, match.start()) + 1
                return text[:split_pos], text[split_pos:]
    
    # Strategy 3: Look for density increase
    chunk_size = 2000
    for i in range(5000, len(text) - chunk_size, 1000):
        chunk = text[i:i+chunk_size]
        answer_like = len(re.findall(r'\n\s*\d+\.\s+[A-D]\s*\n', chunk))
        if answer_like > 15:
            print(f"✓ Found answer key using density analysis at position {i}")
            return text[:i], text[i:]
    
    print("⚠ Could not locate answer key section - will parse entire document as questions")
    return text, ""

def extract_questions_and_answers(pdf_file):
    """Universal PDF parser that works with any DECA exam format"""
    questions = []
    answer_key = {}
    explanations = {}
    
    # Extract text from PDF
    with pdfplumber.open(pdf_file) as pdf:
        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    
    print(f"\n{'='*60}")
    print(f"PARSING PDF")
    print(f"{'='*60}")
    print(f"Total text length: {len(text):,} characters")
    
    # Split into questions and answers sections
    questions_text, answer_text = find_answer_key_split(text)
    
    print(f"\nQuestions section: {len(questions_text):,} characters")
    print(f"Answer section: {len(answer_text):,} characters")
    print(f"\n{'='*60}")
    print("PARSING QUESTIONS")
    print(f"{'='*60}\n")
    
    # Parse questions section
    lines = questions_text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip noise
        if is_likely_noise(line):
            i += 1
            continue
        
        # Look for question start: "1. " or "1) " with text after
        question_match = re.match(r'^(\d+)[\.\)]\s+(.+)', line)
        
        if question_match:
            q_num = int(question_match.group(1))
            q_text = question_match.group(2)
            
            # Read continuation lines for the question
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                
                # Stop if we hit an answer choice
                if re.match(r'^[A-D][\.\)]\s+', next_line):
                    break
                
                # Stop if we hit another question number
                if re.match(r'^\d+[\.\)]\s+', next_line):
                    break
                
                # Add non-noise lines to question text
                if next_line and not is_likely_noise(next_line):
                    q_text += " " + next_line
                
                j += 1
            
            # Now extract the 4 answer choices (handling two-column format)
            choices = {}
            
            while j < len(lines) and len(choices) < 4:
                choice_line = lines[j].strip()
                
                # Check if we've moved to the next question
                if re.match(r'^\d+[\.\)]\s+', choice_line):
                    break
                
                # Skip noise
                if is_likely_noise(choice_line):
                    j += 1
                    continue
                
                # Try to parse choices from this line (handles two-column format)
                line_choices = parse_two_column_choices(choice_line)
                
                if line_choices:
                    # Add any new choices we found
                    for letter, text in line_choices.items():
                        if letter not in choices:
                            choices[letter] = text
                    j += 1
                else:
                    # This might be a continuation of the previous choice
                    if choices and not re.match(r'^[A-D][\.\)]\s+', choice_line):
                        # Add to the last choice
                        last_letter = list(choices.keys())[-1]
                        choices[last_letter] += " " + choice_line
                    j += 1
            
            # Only save question if we found all 4 choices
            if len(choices) == 4 and all(letter in choices for letter in ['A', 'B', 'C', 'D']):
                questions.append({
                    "number": q_num,
                    "text": q_text.strip(),
                    "choices": choices,
                    "correct": None,
                    "explanation": ""
                })
                
                # Progress logging
                if len(questions) <= 5 or len(questions) % 25 == 0:
                    print(f"  Q{q_num}: {q_text[:60]}...")
            else:
                print(f"  ⚠ Q{q_num}: Found only {len(choices)}/4 choices - skipping. Choices: {list(choices.keys())}")
            
            i = j
        else:
            i += 1
    
    print(f"\n✓ Extracted {len(questions)} complete questions")
    
    # Parse answer key section
    if answer_text:
        print(f"\n{'='*60}")
        print("PARSING ANSWER KEY")
        print(f"{'='*60}\n")
        
        answer_lines = answer_text.split('\n')
        current_q_num = None
        current_explanation = ""
        in_source_section = False
        
        for line in answer_lines:
            line_stripped = line.strip()
            
            if not line_stripped or is_likely_noise(line_stripped):
                continue
            
            # Skip SOURCE: sections (common in DECA exams)
            if line_stripped.startswith('SOURCE:'):
                in_source_section = True
                continue
            
            # Look for answer pattern: "1. A" or "1. B Some explanation"
            answer_match = re.match(r'^(\d+)[\.\)]\s+([A-D])(?:\s+(.*))?$', line_stripped)
            
            if answer_match:
                # Save previous explanation
                if current_q_num and current_explanation:
                    explanations[current_q_num] = current_explanation.strip()
                
                current_q_num = int(answer_match.group(1))
                answer_key[current_q_num] = answer_match.group(2)
                
                # Start new explanation
                explanation_start = answer_match.group(3)
                current_explanation = explanation_start if explanation_start else ""
                in_source_section = False
                
                # Progress logging
                if len(answer_key) <= 5 or len(answer_key) % 25 == 0:
                    print(f"  Q{current_q_num}: {answer_key[current_q_num]}")
            
            elif current_q_num and not in_source_section:
                # Continue building explanation
                if not re.match(r'^\d+[\.\)]\s+[A-D]', line_stripped):
                    if current_explanation:
                        current_explanation += " " + line_stripped
                    else:
                        current_explanation = line_stripped
        
        # Save last explanation
        if current_q_num and current_explanation:
            explanations[current_q_num] = current_explanation.strip()
        
        print(f"\n✓ Extracted {len(answer_key)} answers")
        print(f"✓ Extracted {len(explanations)} explanations")
    
    # Assign answers and explanations to questions
    for q in questions:
        q["correct"] = answer_key.get(q["number"])
        q["explanation"] = explanations.get(q["number"], "No explanation available.")
    
    # Final summary
    if questions:
        q_numbers = [q["number"] for q in questions]
        with_answers = sum(1 for q in questions if q["correct"])
        with_explanations = sum(1 for q in questions if q["explanation"] != "No explanation available.")
        
        print(f"\n{'='*60}")
        print("PARSING COMPLETE")
        print(f"{'='*60}")
        print(f"Total questions: {len(questions)}")
        print(f"Question range: Q{min(q_numbers)} to Q{max(q_numbers)}")
        print(f"With answer keys: {with_answers}/{len(questions)}")
        print(f"With explanations: {with_explanations}/{len(questions)}")
        print(f"{'='*60}\n")
    
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
    st.markdown("# DECA Quiz")
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
        
        # Show summary
        num_questions = len(st.session_state.questions)
        num_with_answers = sum(1 for q in st.session_state.questions if q["correct"] is not None)
        num_with_explanations = sum(1 for q in st.session_state.questions if q["explanation"] != "No explanation available.")
        
        st.success(f"✓ Loaded {num_questions} questions")
        
        # Show question number distribution
        if num_questions > 0:
            q_numbers = [q["number"] for q in st.session_state.questions]
            st.info(f"📊 Questions range from #{min(q_numbers)} to #{max(q_numbers)}")
        
        if num_with_answers < num_questions:
            st.warning(f"⚠ Only {num_with_answers}/{num_questions} questions have answer keys")
        else:
            st.success(f"✓ All {num_with_answers} questions have answer keys")
        
        if num_with_explanations < num_questions:
            st.info(f"ℹ️ {num_with_explanations}/{num_questions} questions have explanations")
        
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
            value=min(100, total_questions - start_q + 1),
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