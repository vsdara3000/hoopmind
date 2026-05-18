# test_router.py
from app.services.router_service import route_question

questions = [
    ("Who led the NBA in scoring in 2024?", []),
    ("Tell me about LeBron's career legacy", []),
    ("Was Jokic's 2024 performance consistent with his reputation?", []),
    ("How many points did Steph score last season?", []),
    ("What made the 2016 Finals so historic?", []),
    ("What about his assist numbers?", [{"role": "user", "content": "Tell me about Jokic"}, {"role": "assistant", "content": "Jokic is a great passer"}]),
]

for question, history in questions:
    route = route_question(question, history)
    print(f"{route:6} — {question}")