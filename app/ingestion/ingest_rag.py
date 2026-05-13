import time
import wikipedia
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.unstructured import Document
from app.models.structured import Player, Game, PlayerGameStats, Team

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


def ingest_game_summaries():
    from nba_api.stats.endpoints import playbyplayv3
    db: Session = SessionLocal()
    print("Generating game summaries from play-by-play...")

    games = db.query(Game).all()
    count = 0

    for i, game in enumerate(games):
        existing = db.query(Document).filter(
            Document.source == f"game:{game.id}",
            Document.doc_type == "recap"
        ).first()
        if existing:
            continue

        try:
            pbp = playbyplayv3.PlayByPlayV3(game_id=str(game.id).zfill(10))
            df = pbp.get_data_frames()[0]
            time.sleep(0.6)

            if df.empty:
                continue

            # get team names for this game
            team_ids = df[df['teamId'] != 0]['teamId'].unique()
            team_names = {}
            for tid in team_ids:
                team = db.query(Team).filter(Team.id == int(tid)).first()
                if team:
                    team_names[int(tid)] = team.full_name

            # filter to significant plays only
            significant = df[
                (df['actionType'].isin(['Made Shot', 'Turnover', 'Foul', 'Rebound'])) |
                (df['description'].str.contains('3PT', na=False)) |
                (df['description'].str.contains('Dunk', na=False))
            ].copy()

            if significant.empty:
                continue

            season_type = "playoff" if game.postseason else "regular season"

            # handle all periods including overtime
            max_period = int(df['period'].max())
            for period in range(1, max_period + 1):
                period_plays = significant[significant['period'] == period]
                if period_plays.empty:
                    continue

                if period <= 4:
                    period_name = f"Q{period}"
                else:
                    ot_num = period - 4
                    period_name = f"OT{ot_num}" if ot_num > 1 else "OT"

                lines = [
                    f"NBA {season_type} game on {game.date} (season {game.season}), {period_name}."
                ]

                for _, play in period_plays.iterrows():
                    if play['description'] and str(play['description']).strip():
                        team_name = team_names.get(int(play['teamId']), play['teamTricode'])
                        lines.append(f"{team_name}: {play['description']}")

                content = " | ".join(lines)

                if len(lines) > 3:
                    doc = Document(
                        content=content,
                        doc_type="recap",
                        source=f"game:{game.id}",
                        player_id=None,
                        game_id=game.id,
                        embedding=embed(content)
                    )
                    db.add(doc)

            count += 1
            if count % 50 == 0:
                db.commit()
                print(f"{count} games processed...")

        except Exception as e:
            print(f"Failed on game {game.id}: {e}")
            time.sleep(2)
            continue

    db.commit()
    db.close()
    print(f"Game summaries complete — {count} games processed")


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
    ingest_game_summaries()
    test_similarity_search("LeBron James career achievements")
    test_similarity_search("clutch fourth quarter performance")
    test_similarity_search("three point shooting performance")