from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True)
    created_at = Column(String, server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String)
    content = Column(Text)
    route = Column(String, nullable=True)
    generated_sql = Column(Text, nullable=True)
    created_at = Column(String, server_default=func.now())