import uuid
import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.services.conversation import (
    create_conversation,
    get_conversation,
    save_message,
    get_context,
)
from app.services.router import route_question
from app.services.sql import generate_and_execute
from app.services.rag import retrieve
from app.services.synthesis import synthesize

router = APIRouter(prefix="/conversations", tags=["conversations"])
limiter = Limiter(key_func=get_remote_address)


class AskRequest(BaseModel):
    question: str


@router.post("")
def new_conversation():
    """Create a new conversation and return the session_id."""
    session_id = str(uuid.uuid4())
    conversation = create_conversation(session_id)
    return {"session_id": session_id, "conversation_id": conversation.id}


@router.post("/{session_id}/ask")
@limiter.limit("20/hour")
async def ask(request: Request, session_id: str, body: AskRequest):
    """
    Main endpoint — takes a question, routes it, retrieves data,
    synthesizes an answer, saves messages, returns everything.
    """
    conversation = get_conversation(session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    context = get_context(conversation.id)
    history = context["recent"]
    summary = context["summary"]
    question = body.question

    route = route_question(question, history)
    print(f"Route: {route} for question: {question}")

    sql_result = None
    rag_result = None
    try:
        if route == "SQL":
            sql_result = generate_and_execute(question, history)
        elif route == "RAG":
            rag_result = retrieve(question, history)
        elif route == "BOTH":
            loop = asyncio.get_event_loop()
            sql_task = loop.run_in_executor(None, generate_and_execute, question, history)
            rag_task = loop.run_in_executor(None, retrieve, question, history)
            sql_result, rag_result = await asyncio.gather(sql_task, rag_task)
    except Exception as e:
        print(f"Retrieval error: {e}")

    answer = synthesize(
        question=question,
        history=history,
        sql_result=sql_result,
        rag_result=rag_result,
        summary=summary,
    )

    save_message(conversation_id=conversation.id, role="user", content=question)
    save_message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        route=route,
        generated_sql=sql_result.get("sql") if sql_result else None,
    )

    return {
        "answer": answer,
        "route": route,
        "sql": sql_result.get("sql") if sql_result else None,
        "data": sql_result.get("results") if sql_result else None,
        "rag_type": rag_result.get("rag_type") if rag_result else None,
        "sources": [c.get("source") for c in rag_result.get("chunks", [])] if rag_result else None,
    }


@router.get("/{session_id}/messages")
def get_messages(session_id: str):
    """Get all messages for a conversation."""
    conversation = get_conversation(session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    context = get_context(conversation.id)
    return {
        "session_id": session_id,
        "messages": context["recent"],
        "summary": context["summary"],
    }
