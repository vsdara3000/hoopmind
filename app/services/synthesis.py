from decimal import Decimal
from app.services.llm import chat

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
- State facts confidently. Never use hedging language like "I believe", "it looks like", "it's likely", "I'd say", "probably", or "I'm not sure". If the data is in the context, state it as fact.
- Never make up stats or facts not present in the provided context"""


def format_sql_results(results: list[dict]) -> str:
    """Convert SQL results (max 20 rows) to readable text for the LLM."""
    if not results:
        return "No data found."
    lines = []
    for row in results[:20]:
        cleaned = {
            k: round(float(v), 3) if isinstance(v, Decimal) else v
            for k, v in row.items()
        }
        lines.append(", ".join(f"{k}: {v}" for k, v in cleaned.items()))
    return "\n".join(lines)


def format_rag_chunks(chunks: list[dict]) -> str:
    """Format RAG chunks (max 5, 1000 chars each) into readable context."""
    if not chunks:
        return "No relevant information found."
    return "\n\n".join(
        f"[Source {i+1}: {c.get('source', 'unknown')}]\n{c.get('content', '')[:1000]}"
        for i, c in enumerate(chunks[:5])
    )


def synthesize(
    question: str,
    history: list,
    sql_result: dict = None,
    rag_result: dict = None,
    summary: str = None,
) -> str:
    """
    Generate a final plain English answer from retrieved data.

    Takes the question, conversation history, SQL results and/or RAG chunks,
    and produces a conversational answer the user actually sees.
    """
    context_parts = []
    if sql_result:
        formatted = format_sql_results(sql_result.get("results", []))
        context_parts.append(f"STATS DATA (from database query: {sql_result.get('sql', '')[:100]}):\n{formatted}")
    if rag_result:
        rag_type = rag_result.get("rag_type", "")
        label = "PLAYER BIOGRAPHY CONTEXT" if rag_type == "BIO" else "GAME NARRATIVE CONTEXT"
        context_parts.append(f"{label}:\n{format_rag_chunks(rag_result.get('chunks', []))}")

    context = "\n\n".join(context_parts) if context_parts else "No additional context available."

    messages = [{"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT}]
    if summary:
        messages.append({"role": "system", "content": f"Earlier in this conversation: {summary}"})
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": f"""Context:
{context}

Question: {question}

Answer conversationally using the context above. Be specific with names and numbers."""})

    return chat(messages, max_tokens=500, temperature=0.3)
