import time
import wikipedia
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.unstructured import Document
from app.models.structured import Player, Game, PlayerGameStats, Team
import os
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
    print("Generating game narratives using Groq...")

    games = db.query(Game).all()
    count = 0
    start_time = time.time()
    print(f"Found {len(games)} games in database")

    for i, game in enumerate(games, start=1):
        # skip preseason games
        if str(game.id).zfill(10).startswith('001'):
            print(f"[{i}/{len(games)}] Skipping preseason game {game.id}")
            continue

        existing = db.query(Document).filter(
            Document.source == f"game:{game.id}",
            Document.doc_type == "narrative"
        ).first()
        if existing:
            print(f"[{i}/{len(games)}] Skipping already ingested game {game.id}")
            continue

        if game.home_team_score is None or game.away_team_score is None:
            print(f"[{i}/{len(games)}] Skipping unfinished game {game.id} ({game.date}) — missing final score")
            continue

        game_start = time.time()
        print(f"[{i}/{len(games)}] Starting game {game.id} on {game.date} ({'playoff' if game.postseason else 'regular season'})")

        try:
            pbp = playbyplayv3.PlayByPlayV3(game_id=str(game.id).zfill(10))
            df = pbp.get_data_frames()[0]
            print(f"[{i}/{len(games)}] Retrieved play-by-play with {len(df)} rows")
            time.sleep(0.6)

            if df.empty:
                print(f"[{i}/{len(games)}] No play-by-play data for game {game.id}; skipping")
                continue

            # get team names from database using game's team IDs
            home_team = db.query(Team).filter(Team.id == game.home_team_id).first() if game.home_team_id else None
            away_team = db.query(Team).filter(Team.id == game.away_team_id).first() if game.away_team_id else None

            # fallback to play-by-play team names if not in db
            if not home_team or not away_team:
                team_ids = df[df['teamId'] != 0]['teamId'].unique()
                team_names = {}
                for tid in team_ids:
                    team = db.query(Team).filter(Team.id == int(tid)).first()
                    if team:
                        team_names[int(tid)] = team.full_name
                team_name_list = list(team_names.values())
                matchup = f"{team_name_list[0]} vs {team_name_list[1]}" if len(team_name_list) >= 2 else "NBA game"
                home_name = team_name_list[0] if team_name_list else "Home Team"
                away_name = team_name_list[1] if len(team_name_list) > 1 else "Away Team"
            else:
                home_name = home_team.full_name
                away_name = away_team.full_name
                matchup = f"{away_name} @ {home_name}"

            # build score line
            if game.home_team_score and game.away_team_score:
                if game.home_team_wins:
                    score_line = f"Final score: {home_name} {game.home_team_score}, {away_name} {game.away_team_score}. {home_name} won."
                else:
                    score_line = f"Final score: {away_name} {game.away_team_score}, {home_name} {game.home_team_score}. {away_name} won."
                score_diff = abs(game.home_team_score - game.away_team_score)
                closeness = "close game" if score_diff <= 5 else "competitive game" if score_diff <= 10 else "blowout" if score_diff >= 20 else "moderate margin"
            else:
                score_line = ""
                closeness = "unknown margin"

            # build team stats context
            team_stats = ""
            if game.home_team_fg_pct and game.away_team_fg_pct:
                team_stats = (
                    f"{home_name} shot {game.home_team_fg_pct:.1%} from the field, "
                    f"{game.home_team_fg3_pct:.1%} from three, "
                    f"{game.home_team_reb} rebounds, {game.home_team_ast} assists, {game.home_team_tov} turnovers. "
                    f"{away_name} shot {game.away_team_fg_pct:.1%} from the field, "
                    f"{game.away_team_fg3_pct:.1%} from three, "
                    f"{game.away_team_reb} rebounds, {game.away_team_ast} assists, {game.away_team_tov} turnovers."
                )

            # filter to significant plays
            significant = df[
                (df['actionType'].isin(['Made Shot', 'Turnover'])) |
                (df['description'].str.contains('3PT', na=False)) |
                (df['description'].str.contains('Dunk', na=False))
            ].copy()

            max_period = int(df['period'].max())
            went_to_ot = max_period > 4

            # build play summary capped at 80 plays
            play_lines = []
            for _, play in significant.iterrows():
                if play['description'] and str(play['description']).strip():
                    period = play['period']
                    period_label = f"Q{period}" if period <= 4 else f"OT{period - 4 if period > 5 else ''}"
                    team_id = int(play['teamId']) if play['teamId'] else 0
                    team_name = home_name if team_id == game.home_team_id else away_name
                    play_lines.append(f"{period_label} | {team_name}: {play['description']}")

            plays_text = "\n".join(play_lines[:80])

            season_type = "playoff" if game.postseason else "regular season"

            prompt = f"""You are a sports journalist writing a game recap for an NBA {season_type} game.

Game: {matchup}
Date: {game.date}
Season: {game.season}
{score_line}
Game character: {closeness}
{"This game went to overtime." if went_to_ot else ""}

Team stats:
{team_stats}

Key plays:
{plays_text}

Write a 4-5 sentence narrative recap of this game. Cover:
- Who won and by how much
- Who dominated and who struggled
- Whether the game was close or a blowout and when it was decided
- Any turning points or momentum swings
- Standout individual performances with specific details from the plays

Write like a real sports journalist. Be specific and vivid. Use player and team names.
Write only the narrative, no headline, no preamble."""

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )
            narrative = response.choices[0].message.content.strip()

            doc = Document(
                content=narrative,
                doc_type="narrative",
                source=f"game:{game.id}",
                player_id=None,
                game_id=game.id,
                embedding=embed(narrative)
            )
            db.add(doc)

            count += 1
            elapsed = time.time() - game_start
            print(f"[{i}/{len(games)}] Completed game {game.id} in {elapsed:.1f}s — {matchup} on {game.date}")

            if count % 50 == 0:
                db.commit()
                print(f"[{count}/{len(games)}] Committed after 50 narratives")

            time.sleep(0.3)

        except Exception as e:
            elapsed = time.time() - game_start
            print(f"[{i}/{len(games)}] Failed on game {game.id} after {elapsed:.1f}s: {e}")
            time.sleep(2)
            continue

    total_elapsed = time.time() - start_time
    db.commit()
    db.close()
    print(f"Narrative generation complete — {count} games processed in {total_elapsed:.1f}s")

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