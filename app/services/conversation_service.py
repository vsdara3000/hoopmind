import os
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from app.models.conversation import Conversation, Message
from app.database import SessionLocal

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def create_conversation(session_id: str) -> Conversation:
    """Create a new conversation and save it to the database."""
    db: Session = SessionLocal()
    conversation = Conversation(session_id=session_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.close()
    return conversation


def get_conversation(session_id: str) -> Conversation | None:
    """Get a conversation by session_id."""
    db: Session = SessionLocal()
    conversation = db.query(Conversation).filter(
        Conversation.session_id == session_id
    ).first()
    db.close()
    return conversation


def save_message(
    conversation_id: int,
    role: str,
    content: str,
    route: str = None,
    generated_sql: str = None
) -> Message:
    """Save a single message to the database."""
    db: Session = SessionLocal()
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        route=route,
        generated_sql=generated_sql
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    db.close()
    return message


def get_context(conversation_id: int) -> dict:
    """
    Get conversation context for passing to the LLM.
    
    For short conversations (6 or fewer messages): return all messages.
    For long conversations: return last 6 messages + a summary of older ones.
    
    This prevents the context window from getting too large while
    keeping the conversation coherent.
    """
    db: Session = SessionLocal()
    all_messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()
    db.close()

    if len(all_messages) <= 6:
        return {
            "recent": [{"role": m.role, "content": m.content} for m in all_messages],
            "summary": None
        }

    # summarize older messages
    older = all_messages[:-6]
    recent = all_messages[-6:]

    older_text = "\n".join([f"{m.role}: {m.content}" for m in older])

    summary_response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""Summarize this NBA conversation history in 2-3 sentences.
Focus on which players, teams, and topics were discussed.
Be specific with names.

Conversation:
{older_text}

Write only the summary, no preamble."""
        }],
        max_tokens=150
    )

    summary = summary_response.choices[0].message.content.strip()

    return {
        "recent": [{"role": m.role, "content": m.content} for m in recent],
        "summary": summary
    }