import os
from dotenv import load_dotenv
from tavily import TavilyClient
from sqlalchemy import text
from app.services.embeddings import embed
from app.services.llm import classify, format_history
from app.database import SessionLocal

load_dotenv()
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

GAME_DOMAINS = [
    "bleacherreport.com",
    "cbssports.com",
    "si.com",
    "usatoday.com",
    "basketballreference.com",
    "theringer.com",
    "yahoo.com/sports",
]

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
    user_content = f"{format_history(history)}Question: {question}"
    return classify(RAG_ROUTER_PROMPT, user_content, allowed={"BIO", "GAME"}, default="GAME")


def search_bios(query: str, top_k: int = 5) -> list[dict]:
    """Search pgvector for relevant player bio chunks (career/background/legacy)."""
    embedding = str(embed(query))
    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT content, source,
                   1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM documents
            WHERE doc_type = 'bio'
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
        """), {"embedding": embedding, "k": top_k})
        return [
            {"content": r.content, "source": r.source, "similarity": float(r.similarity)}
            for r in rows
        ]


def search_games(query: str, top_k: int = 5) -> list[dict]:
    """Search the web via Tavily for game recaps and narratives."""
    results = tavily_client.search(
        query=f"NBA {query} game recap",
        search_depth="advanced",
        max_results=top_k,
        include_domains=GAME_DOMAINS,
    )
    return [
        {"content": r.get("content", "")[:2000], "source": r["url"], "similarity": r.get("score", 0)}
        for r in results.get("results", [])
        if r.get("score", 0) > 0.3
    ]


def retrieve(question: str, history: list) -> dict:
    """
    Main entry point for RAG retrieval.
    Classifies the question then routes to pgvector (BIO) or Tavily (GAME).
    Returns chunks and which backend was used.
    """
    rag_type = classify_rag_question(question, history)
    chunks = search_bios(question) if rag_type == "BIO" else search_games(question)
    return {"chunks": chunks, "rag_type": rag_type}
