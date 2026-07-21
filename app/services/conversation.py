from app.models import Conversation, Message
from app.database import SessionLocal
from app.services.llm import chat


def create_conversation(session_id: str) -> Conversation:
    """Create a new conversation and save it to the database."""
    with SessionLocal() as db:
        conversation = Conversation(session_id=session_id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation


def get_conversation(session_id: str) -> Conversation | None:
    """Get a conversation by session_id."""
    with SessionLocal() as db:
        return db.query(Conversation).filter(Conversation.session_id == session_id).first()


def save_message(
    conversation_id: int,
    role: str,
    content: str,
    route: str = None,
    generated_sql: str = None,
) -> Message:
    """Save a single message to the database."""
    with SessionLocal() as db:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            route=route,
            generated_sql=generated_sql,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message


def get_context(conversation_id: int) -> dict:
    """
    Get conversation context for passing to the LLM.

    For short conversations (6 or fewer messages): return all messages.
    For long conversations: return last 6 messages + a summary of older ones.

    This prevents the context window from getting too large while
    keeping the conversation coherent.
    """
    with SessionLocal() as db:
        all_messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()

    def as_dicts(messages):
        return [{"role": m.role, "content": m.content} for m in messages]

    if len(all_messages) <= 6:
        return {"recent": as_dicts(all_messages), "summary": None}

    older, recent = all_messages[:-6], all_messages[-6:]
    older_text = "\n".join(f"{m.role}: {m.content}" for m in older)
    summary = chat(
        [{"role": "user", "content": f"""Summarize this NBA conversation history in 2-3 sentences.
Focus on which players, teams, and topics were discussed.
Be specific with names.

Conversation:
{older_text}

Write only the summary, no preamble."""}],
        max_tokens=150,
        temperature=1.0,
    )
    return {"recent": as_dicts(recent), "summary": summary}
