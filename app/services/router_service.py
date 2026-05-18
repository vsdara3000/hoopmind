import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

ROUTER_SYSTEM_PROMPT = """You are a query router for an NBA stats and information assistant.

Your job is to classify a user question into exactly one of three categories:

SQL - the question asks for specific stats, numbers, rankings, records, or comparisons that can be answered from a database
Examples: "Who led the league in assists?", "How many points did LeBron average?", "Which team had the best record?"

RAG - the question asks for narratives, stories, context, career history, or opinions that require text-based knowledge
Examples: "Tell me about Steph Curry's career", "What made the 2016 Finals historic?", "What is LeBron's legacy?"

BOTH - the question needs both stats AND narrative context to answer properly
Examples: "Was LeBron's 2024 performance consistent with his career?", "How does Jokic's stats compare to his reputation as a passer?"

Return only one word: SQL, RAG, or BOTH.
Never explain your choice. Never return anything else."""


def route_question(question: str, history: list) -> str:
    """
    Classify a user question as SQL, RAG, or BOTH.
    
    Takes the question and recent conversation history so it can
    understand follow-up questions in context.
    Returns exactly one string: 'SQL', 'RAG', or 'BOTH'
    """
    # format history for context
    history_text = ""
    if history:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history[-4:]])
        history_text = f"\nRecent conversation:\n{history_text}\n"

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": f"{history_text}Question to classify: {question}"}
        ],
        max_tokens=10,
        temperature=0  # deterministic — we want consistent routing
    )

    result = response.choices[0].message.content.strip().upper()

    # safety check — if model returns something unexpected default to BOTH
    if result not in ["SQL", "RAG", "BOTH"]:
        print(f"Router returned unexpected value: {result}, defaulting to BOTH")
        return "BOTH"

    return result