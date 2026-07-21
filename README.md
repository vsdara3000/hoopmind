# HoopMind

NBA Q&A backend that answers stats and narrative questions by routing each query to SQL, RAG, or both, then synthesizing a response with an LLM.

## How it works

1. Create a conversation session
2. Ask a question — the router classifies it as `SQL`, `RAG`, or `BOTH`
3. Retrieve data (structured stats and/or embeddings + web search)
4. Synthesize a natural-language answer and save the turn

Built with **FastAPI**, **Postgres + pgvector**, **Groq**, **Tavily**, and **sentence-transformers** (`all-MiniLM-L6-v2`).

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/conversations` | Create a session → `{ session_id, conversation_id }` |
| `POST` | `/conversations/{session_id}/ask` | Ask a question (`{ "question": "..." }`) |
| `GET` | `/conversations/{session_id}/messages` | Conversation history + summary |

Ask is rate-limited to **20 requests/hour** per IP.

Interactive docs: `http://localhost:8000/docs`

## Prerequisites

- Python 3.11+
- Docker (for Postgres + pgvector)
- API keys: [Groq](https://console.groq.com/) and [Tavily](https://tavily.com/)

## Setup

```bash
# Clone
git clone https://github.com/vsdara3000/hoopmind.git
cd hoopmind

# Virtualenv + deps
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

# Env
cp .env.example .env   # or create .env manually — see below

# Database
docker compose up -d
alembic upgrade head

# Optional: load NBA stats / RAG corpus
# python -m app.ingestion.ingest
# python -m app.ingestion.ingest_rag

# Run API
uvicorn app.main:app --reload --port 8000
```

## Environment variables

Create a `.env` in the project root:

```env
DATABASE_URL=postgresql://hoopmind:hoopmind@localhost:5432/hoopmind
POSTGRES_USER=hoopmind
POSTGRES_PASSWORD=hoopmind
POSTGRES_DB=hoopmind
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
```

`.env` is gitignored — never commit secrets.

## Project layout

```
app/
  main.py              # FastAPI app
  routes.py            # Conversation endpoints
  models.py            # SQLAlchemy models
  database.py
  services/            # Router, SQL, RAG, synthesis, LLM, embeddings
  ingestion/           # NBA API + RAG ingest scripts
alembic/               # Migrations
docker-compose.yml     # Postgres + pgvector
tests/
scripts/
```

## Frontend

This repo is the **API only**. Point your separate frontend at:

```
http://localhost:8000
```

CORS is open for local development (`allow_origins=["*"]`). Tighten this for production.

## Deploy notes

- Frontend: Vercel (or similar)
- Backend: Railway / Render with enough RAM for embeddings (`torch` + sentence-transformers often need **≥2 GB**)
- Database: Postgres with the **pgvector** extension
