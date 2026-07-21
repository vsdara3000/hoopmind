from app.services.router import route_question

def test_sql_questions():
    sql_questions = [
        "Who led the NBA in scoring in 2024?",
        "What were LeBron James stats in the 2024 season?",
        "Which team had the most assists per game in 2023?",
        "How many points did Shai average in the playoffs?",
        "Who shot the best from three in 2024?",
    ]
    for q in sql_questions:
        result = route_question(q, [])
        assert result in ["SQL", "BOTH"], f"Expected SQL or BOTH for: {q}, got {result}"

def test_rag_questions():
    rag_questions = [
        "Tell me about LeBron James career legacy",
        "What happened in the 2024 NBA Finals?",
        "Tell me about Steph Curry's journey to becoming the greatest shooter",
        "What made the 2016 Finals so historic?",
    ]
    for q in rag_questions:
        result = route_question(q, [])
        assert result in ["RAG", "BOTH"], f"Expected RAG or BOTH for: {q}, got {result}"

def test_both_questions():
    both_questions = [
        "Was Shai's playoff performance consistent with his regular season?",
        "How did Jayson Tatum's Finals performance compare to his regular season stats?",
    ]
    for q in both_questions:
        result = route_question(q, [])
        assert result == "BOTH", f"Expected BOTH for: {q}, got {result}"

def test_followup_with_history():
    history = [
        {"role": "user", "content": "Who led the NBA in scoring in 2024?"},
        {"role": "assistant", "content": "Shai Gilgeous-Alexander led with 31.2 ppg"}
    ]
    result = route_question("What about his playoff stats?", history)
    assert result in ["SQL", "BOTH"]

def test_returns_valid_route():
    result = route_question("random question about basketball", [])
    assert result in ["SQL", "RAG", "BOTH"]