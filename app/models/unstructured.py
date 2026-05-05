from sqlalchemy import Column, Integer, String, ForeignKey
from pgvector.sqlalchemy import Vector
from app.database import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    content = Column(String)
    doc_type = Column(String)  # bio, recap, news
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True)
    source = Column(String, nullable=True)
    embedding = Column(Vector(384))