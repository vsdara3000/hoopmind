"""
End-to-end smoke test: exercises every real dependency (Postgres, pgvector,
embeddings, Groq LLM calls, Tavily web search) and the full ask pipeline.

Run from the project root:  python scripts/smoke_test.py
"""
import os
import sys
import uuid
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal
from app.services.embeddings import embed
from app.services.router import route_question
from app.services.sql import generate_and_execute
from app.services.rag import retrieve, search_bios, search_games
from app.services.synthesis import synthesize
from app.services.conversation import (
    create_conversation,
    save_message,
    get_context,
)

results = []


def check(name, fn):
    try:
        detail = fn()
        results.append((name, True, detail))
        print(f"[PASS] {name} — {detail}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"[FAIL] {name} — {e}")
        traceback.print_exc()


def test_database():
    with SessionLocal() as db:
        assert db.execute(text("SELECT 1")).scalar() == 1
        games = db.execute(text("SELECT COUNT(*) FROM games")).scalar()
        docs = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    return f"connected (games={games}, documents={docs})"


def test_embeddings():
    vec = embed("LeBron James career achievements")
    assert isinstance(vec, list) and len(vec) == 384
    return f"384-dim vector ({vec[0]:.4f}, ...)"


def test_router():
    route = route_question("Who led the NBA in scoring in 2024?", [])
    assert route in {"SQL", "RAG", "BOTH"}
    return f"route={route}"


def test_sql_pipeline():
    out = generate_and_execute("Who led the NBA in scoring in 2024?", [])
    assert out["sql"].upper().startswith("SELECT")
    assert out["results"], "no rows returned"
    return f"{len(out['results'])} rows; top={list(out['results'][0].values())[:3]}"


def test_rag_bio_pgvector():
    chunks = search_bios("Tell me about Stephen Curry's career", top_k=3)
    assert chunks, "no bio chunks from pgvector"
    return f"{len(chunks)} chunks; top sim={chunks[0]['similarity']:.3f}"


def test_rag_game_tavily():
    chunks = search_games("2016 NBA Finals Game 7", top_k=3)
    assert chunks, "no web results from Tavily"
    return f"{len(chunks)} web results; top={chunks[0]['source']}"


def test_retrieve_router():
    out = retrieve("What is Nikola Jokic's legacy?", [])
    assert out["rag_type"] in {"BIO", "GAME"}
    assert out["chunks"], "retrieve returned no chunks"
    return f"rag_type={out['rag_type']}, {len(out['chunks'])} chunks"


def test_synthesis():
    fake_sql = {"sql": "SELECT ...", "results": [{"player": "Shai Gilgeous-Alexander", "avg_pts": 32.7}]}
    answer = synthesize("Who led the NBA in scoring in 2024?", [], sql_result=fake_sql)
    assert isinstance(answer, str) and len(answer) > 10
    return f'"{answer[:70]}..."'


def test_conversation_flow():
    conv = create_conversation(str(uuid.uuid4()))
    save_message(conv.id, "user", "Who led scoring in 2024?")
    save_message(conv.id, "assistant", "Shai Gilgeous-Alexander", route="SQL")
    ctx = get_context(conv.id)
    assert len(ctx["recent"]) == 2
    return f"conversation {conv.id}, {len(ctx['recent'])} messages persisted"


def test_full_pipeline():
    """Mimic the /ask endpoint end to end for a BOTH-style question."""
    question = "Was Shai's playoff performance consistent with his regular season?"
    route = route_question(question, [])
    sql_result = generate_and_execute(question, []) if route in {"SQL", "BOTH"} else None
    rag_result = retrieve(question, []) if route in {"RAG", "BOTH"} else None
    answer = synthesize(question, [], sql_result=sql_result, rag_result=rag_result)
    assert answer and len(answer) > 10
    return f'route={route}; answer="{answer[:60]}..."'


if __name__ == "__main__":
    print("=" * 70)
    print("HoopsMind end-to-end smoke test")
    print("=" * 70)
    check("Postgres connectivity", test_database)
    check("Embeddings (MiniLM)", test_embeddings)
    check("Router (Groq)", test_router)
    check("SQL pipeline (Groq + Postgres)", test_sql_pipeline)
    check("RAG BIO (pgvector)", test_rag_bio_pgvector)
    check("RAG GAME (Tavily)", test_rag_game_tavily)
    check("Retrieve sub-router", test_retrieve_router)
    check("Synthesis (Groq)", test_synthesis)
    check("Conversation persistence", test_conversation_flow)
    check("Full ask pipeline (BOTH)", test_full_pipeline)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("=" * 70)
    print(f"RESULT: {passed}/{total} passed")
    print("=" * 70)
    sys.exit(0 if passed == total else 1)
