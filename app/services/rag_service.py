import os
from groq import Groq
from dotenv import load_dotenv
from tavily import TavilyClient
from sqlalchemy import text
from sentence_transformers import SentenceTransformer
from app.database import SessionLocal

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
model = SentenceTransformer('all-MiniLM-L6-v2')

RAG_ROUTER_PROMPT = """You are a sub-router for an NBA information assistant.

Classify this question into one of two categories:

BIO - the question is about a player's career, background, legacy, personality, achievements, or general information about who they are
Examples: "Tell me about LeBron's career", "What is Steph Curry's legacy?", "How did Kobe develop his work ethic?"

GAME - the question is about a specific game, series, season narrative, recent news, or what happened in a particular game or event
Examples: "What happened in the 2016 Finals?", "Tell me about Game 5 of the 2024 Finals", "How did the Celtics win the championship?"

Return only one word: BIO or GAME.
Never explain. Never return anything else."""


def classify_rag_question(question: str, history: list) -> str:
    """Decide whether to use pgvector (BIO) or Tavily (GAME)."""
    history_text = ""
    if history:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history[-4:]])
        history_text = f"\nRecent conversation:\n{history_text}\n"

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": RAG_ROUTER_PROMPT},
            {"role": "user", "content": f"{history_text}Question: {question}"}
        ],
        max_tokens=10,
        temperature=0
    )

    result = response.choices[0].message.content.strip().upper()

    if result not in ["BIO", "GAME"]:
        print(f"RAG router returned unexpected value: {result}, defaulting to GAME")
        return "GAME"

    return result


def search_bios(query: str, top_k: int = 5) -> list[dict]:
    """
    Search pgvector for relevant player bio chunks.
    Used for career/background/legacy questions.
    """
    db = SessionLocal()
    try:
        query_embedding = model.encode(query).tolist()

        results = db.execute(text("""
            SELECT content, source,
                   1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM documents
            WHERE doc_type = 'bio'
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
        """), {"embedding": str(query_embedding), "k": top_k})

        return [
            {
                "content": row.content,
                "source": row.source,
                "similarity": float(row.similarity)
            }
            for row in results
        ]
    finally:
        db.close()


def search_games(query: str, top_k: int = 5) -> list[dict]:
    results = tavily_client.search(
        query=f"NBA {query} game recap",
        search_depth="advanced",
        max_results=top_k,
        include_domains=[
            "bleacherreport.com",
            "cbssports.com",
            "si.com",
            "usatoday.com",
            "basketballreference.com",
            "theringer.com",
            "yahoo.com/sports"
        ]
    )

    return [
        {
            "content": r.get("content", "")[:2000],
            "source": r["url"],
            "similarity": r.get("score", 0)
        }
        for r in results.get("results", [])
        if r.get("score", 0) > 0.3
    ]


def retrieve(question: str, history: list) -> dict:
    """
    Main entry point for RAG retrieval.
    Classifies the question then routes to pgvector or Tavily.
    Returns chunks and which backend was used.
    """
    rag_type = classify_rag_question(question, history)

    if rag_type == "BIO":
        chunks = search_bios(question)
        return {"chunks": chunks, "rag_type": "BIO"}
    else:
        chunks = search_games(question)
        return {"chunks": chunks, "rag_type": "GAME"}