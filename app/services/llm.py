import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

DEFAULT_MODEL = "llama-3.3-70b-versatile"


def chat(messages: list[dict], model: str = DEFAULT_MODEL, max_tokens: int = 500, temperature: float = 0) -> str:
    """Call Groq chat completion and return the stripped text response."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def format_history(history: list, limit: int = 4) -> str:
    """Render the last few conversation turns as a labelled text block."""
    if not history:
        return ""
    turns = "\n".join(f"{m['role']}: {m['content']}" for m in history[-limit:])
    return f"\nRecent conversation:\n{turns}\n"


def classify(system_prompt: str, user_content: str, allowed: set[str], default: str, model: str = DEFAULT_MODEL) -> str:
    """Single-word LLM classifier that falls back to a default on unexpected output."""
    result = chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        model=model,
        max_tokens=10,
        temperature=0,
    ).upper()
    if result not in allowed:
        print(f"Classifier returned unexpected value: {result}, defaulting to {default}")
        return default
    return result
