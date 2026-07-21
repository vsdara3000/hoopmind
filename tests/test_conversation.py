import uuid
from app.services.conversation import (
    create_conversation,
    get_conversation,
    save_message,
    get_context
)

def test_create_conversation():
    session_id = str(uuid.uuid4())
    conv = create_conversation(session_id)
    assert conv.id is not None
    assert conv.session_id == session_id

def test_get_conversation():
    session_id = str(uuid.uuid4())
    created = create_conversation(session_id)
    fetched = get_conversation(session_id)
    assert fetched is not None
    assert fetched.id == created.id

def test_get_nonexistent_conversation():
    result = get_conversation("nonexistent-session-id")
    assert result is None

def test_save_and_retrieve_messages():
    session_id = str(uuid.uuid4())
    conv = create_conversation(session_id)
    save_message(conv.id, "user", "Who led scoring in 2024?")
    save_message(conv.id, "assistant", "Shai Gilgeous-Alexander", route="SQL")
    context = get_context(conv.id)
    assert len(context["recent"]) == 2
    assert context["recent"][0]["role"] == "user"
    assert context["recent"][1]["role"] == "assistant"

def test_context_returns_recent_only():
    session_id = str(uuid.uuid4())
    conv = create_conversation(session_id)
    for i in range(10):
        save_message(conv.id, "user", f"Question {i}")
        save_message(conv.id, "assistant", f"Answer {i}")
    context = get_context(conv.id)
    assert len(context["recent"]) <= 6

def test_long_conversation_has_summary():
    session_id = str(uuid.uuid4())
    conv = create_conversation(session_id)
    for i in range(8):
        save_message(conv.id, "user", f"Tell me about player {i}")
        save_message(conv.id, "assistant", f"Player {i} is great")
    context = get_context(conv.id)
    assert context["summary"] is not None