import os
import sys
import time

# allow running directly (python scripts/latency.py) from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.router import route_question
from app.services.sql import generate_and_execute
from app.services.rag import retrieve
from app.services.synthesis import synthesize

def time_it(label, fn, *args):
    start = time.time()
    result = fn(*args)
    elapsed = time.time() - start
    print(f"{label}: {elapsed:.2f}s")
    return result, elapsed

questions = [
    ("SQL", "Who led the NBA in scoring in 2024?"),
    ("SQL", "What were LeBron James stats in the 2024 season?"),
    ("RAG-Game", "What happened in Game 7 of the 2016 NBA Finals?"),
    ("RAG-Bio", "Tell me about Steph Curry's career legacy"),
    ("BOTH", "Was Shai's playoff performance consistent with his regular season?"),
]

for expected_type, question in questions:
    print(f"\n{'='*60}")
    print(f"Q ({expected_type}): {question}")

    total_start = time.time()

    route, route_time = time_it("  Router", route_question, question, [])
    print(f"  Route: {route}")

    sql_result = None
    rag_result = None

    if route == "SQL":
        sql_result, _ = time_it("  SQL service", generate_and_execute, question, [])
    elif route == "RAG":
        rag_result, _ = time_it("  RAG service", retrieve, question, [])
    elif route == "BOTH":
        sql_result, _ = time_it("  SQL service", generate_and_execute, question, [])
        rag_result, _ = time_it("  RAG service", retrieve, question, [])

    answer, synth_time = time_it("  Synthesis", synthesize, question, [], sql_result, rag_result)

    total = time.time() - total_start
    print(f"  TOTAL: {total:.2f}s")
    print(f"  Answer preview: {answer[:100]}...")