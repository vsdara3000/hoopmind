import time
import wikipedia
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Document, Player

model = SentenceTransformer('all-MiniLM-L6-v2')


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if len(chunk.split()) > 50:
            chunks.append(chunk)
    return chunks


def embed(text: str) -> list[float]:
    return model.encode(text).tolist()


def ingest_player_bios():
    db: Session = SessionLocal()
    print("Fetching active players from database...")

    active_players = db.query(Player).filter(Player.is_active == True).all()
    print(f"Found {len(active_players)} active players")

    for i, player in enumerate(active_players):
        name = f"{player.first_name} {player.last_name}"

        existing = db.query(Document).filter(
            Document.source == f"wikipedia:{name}",
            Document.doc_type == "bio"
        ).first()
        if existing:
            print(f"[{i+1}/{len(active_players)}] Skipping {name} — already ingested")
            continue

        try:
            page = wikipedia.page(name, auto_suggest=False)
            chunks = chunk_text(page.content)

            for chunk in chunks:
                doc = Document(
                    content=chunk,
                    doc_type="bio",
                    source=f"wikipedia:{name}",
                    player_id=player.id,
                    game_id=None,
                    embedding=embed(chunk)
                )
                db.add(doc)

            db.commit()
            print(f"[{i+1}/{len(active_players)}] ✓ {name} — {len(chunks)} chunks")

            if i % 50 == 0 and i > 0:
                print("Pausing 30 seconds to avoid rate limiting...")
                time.sleep(30)
            else:
                time.sleep(1.5)

        except wikipedia.exceptions.DisambiguationError as e:
            try:
                page = wikipedia.page(e.options[0], auto_suggest=False)
                chunks = chunk_text(page.content)
                for chunk in chunks:
                    doc = Document(
                        content=chunk,
                        doc_type="bio",
                        source=f"wikipedia:{name}",
                        player_id=player.id,
                        game_id=None,
                        embedding=embed(chunk)
                    )
                    db.add(doc)
                db.commit()
                print(f"[{i+1}/{len(active_players)}] ✓ {name} (disambiguation) — {len(chunks)} chunks")
            except Exception as e2:
                print(f"[{i+1}/{len(active_players)}] ✗ {name} failed: {e2}")

        except wikipedia.exceptions.PageError:
            print(f"[{i+1}/{len(active_players)}] ✗ {name} — no Wikipedia page, skipping")

        except Exception as e:
            if "expecting value" in str(e) or "429" in str(e):
                print(f"Rate limited on {name}, waiting 60 seconds...")
                time.sleep(60)
                try:
                    page = wikipedia.page(name, auto_suggest=False)
                    chunks = chunk_text(page.content)
                    for chunk in chunks:
                        doc = Document(
                            content=chunk,
                            doc_type="bio",
                            source=f"wikipedia:{name}",
                            player_id=player.id,
                            game_id=None,
                            embedding=embed(chunk)
                        )
                        db.add(doc)
                    db.commit()
                    print(f"[{i+1}/{len(active_players)}] ✓ {name} — retry successful")
                except Exception as e2:
                    print(f"[{i+1}/{len(active_players)}] ✗ {name} failed after retry: {e2}")
            else:
                print(f"[{i+1}/{len(active_players)}] ✗ {name} failed: {e}")
            continue

    db.close()
    print("Player bio ingestion complete")


def test_similarity_search(query: str, top_k: int = 5):
    from sqlalchemy import text
    db: Session = SessionLocal()

    query_embedding = embed(query)

    results = db.execute(text("""
        SELECT content, doc_type, source,
               1 - (embedding <=> CAST(:embedding AS vector)) as similarity
        FROM documents
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :k
    """), {"embedding": str(query_embedding), "k": top_k})

    print(f"\nTop {top_k} results for: '{query}'\n")
    for row in results:
        print(f"[{row.doc_type}] similarity: {row.similarity:.3f}")
        print(f"source: {row.source}")
        print(f"content: {row.content[:200]}...")
        print("---")

    db.close()


if __name__ == "__main__":
    ingest_player_bios()
    test_similarity_search("LeBron James career achievements")
    test_similarity_search("clutch fourth quarter performance")