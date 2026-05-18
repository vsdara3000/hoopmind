# test_sql.py
from app.services.sql_service import generate_and_execute

questions = [
    "Who had the highest free throw percentage in the 2024 playoffs?",
]
for question in questions:
    print(f"\nQ: {question}")
    result = generate_and_execute(question, [])
    print(f"SQL: {result['sql']}")
    print(f"Results: {result['results'][:3]}")
    print("---")
