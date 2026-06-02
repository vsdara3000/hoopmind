import os
from groq import Groq
from dotenv import load_dotenv
from decimal import Decimal

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYNTHESIS_SYSTEM_PROMPT = """You are HoopsMind, an expert NBA analyst and historian.
You answer questions about NBA stats, players, games, and history in a conversational, 
knowledgeable way — like a brilliant friend who knows everything about basketball.

Guidelines:
- Be conversational and engaging, not robotic
- Trust the provided context completely — if stats are in the context, state them confidently as facts
- Never express doubt about data that is explicitly provided in the context
- Reference specific stats and names when available
- If narrative context is provided, weave it into your answer naturally
- Be concise — 3-5 sentences for most answers, longer only if the question demands it
- If the context is empty or missing, only then say you don't have enough information
- Never make up stats or facts not present in the provided context"""


def format_sql_results(results: list[dict]) -> str:
    """Convert SQL results to readable text for the LLM."""
    if not results:
        return "No data found."

    # convert Decimal to float for readability
    cleaned = []
    for row in results[:20]:  # cap at 20 rows
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, Decimal):
                clean_row[k] = round(float(v), 3)
            else:
                clean_row[k] = v
        cleaned.append(clean_row)

    lines = []
    for row in cleaned:
        line = ", ".join([f"{k}: {v}" for k, v in row.items()])
        lines.append(line)

    return "\n".join(lines)


def format_rag_chunks(chunks: list[dict], rag_type: str) -> str:
    """Format RAG chunks into readable context for the LLM."""
    if not chunks:
        return "No relevant information found."

    lines = []
    for i, chunk in enumerate(chunks[:5]):
        source = chunk.get("source", "unknown")
        content = chunk.get("content", "")[:1000]  # cap each chunk at 1000 chars
        lines.append(f"[Source {i+1}: {source}]\n{content}")

    return "\n\n".join(lines)


def synthesize(
    question: str,
    history: list,
    sql_result: dict = None,
    rag_result: dict = None,
    summary: str = None
) -> str:
    """
    Generate a final plain English answer from retrieved data.

    Takes the question, conversation history, SQL results and/or RAG chunks,
    and produces a conversational answer the user actually sees.
    """
    # build context section
    context_parts = []

    if sql_result:
        formatted = format_sql_results(sql_result.get("results", []))
        context_parts.append(f"STATS DATA (from database query: {sql_result.get('sql', '')[:100]}):\n{formatted}")

    if rag_result:
        rag_type = rag_result.get("rag_type", "")
        chunks = rag_result.get("chunks", [])
        formatted = format_rag_chunks(chunks, rag_type)
        label = "PLAYER BIOGRAPHY CONTEXT" if rag_type == "BIO" else "GAME NARRATIVE CONTEXT"
        context_parts.append(f"{label}:\n{formatted}")

    context = "\n\n".join(context_parts) if context_parts else "No additional context available."

    # build messages
    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT}
    ]

    # add conversation summary if exists
    if summary:
        messages.append({
            "role": "system",
            "content": f"Earlier in this conversation: {summary}"
        })

    # add recent history
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})

    # add the actual question with context
    messages.append({
        "role": "user",
        "content": f"""Context:
{context}

Question: {question}

Answer conversationally using the context above. Be specific with names and numbers."""
    })

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=500,
        temperature=0.3  # slight creativity for conversational tone
    )

    return response.choices[0].message.content.strip()