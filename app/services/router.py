from app.services.llm import classify, format_history

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
    user_content = f"{format_history(history)}Question to classify: {question}"
    return classify(
        ROUTER_SYSTEM_PROMPT,
        user_content,
        allowed={"SQL", "RAG", "BOTH"},
        default="BOTH",
        model="llama-3.1-8b-instant",
    )
