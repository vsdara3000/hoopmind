import time
from nba_api.stats.static import teams, players
from nba_api.stats.endpoints import leaguegamefinder, boxscoretraditionalv3
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.structured import Team, Player, Game, PlayerGameStats, SeasonAverage


def ingest_teams():
    db: Session = SessionLocal()
    nba_teams = teams.get_teams()
    print("Ingesting teams...")
    for t in nba_teams:
        existing = db.query(Team).filter(Team.id == t["id"]).first()
        if existing:
            existing.full_name = t["full_name"]
            existing.abbreviation = t["abbreviation"]
            existing.nickname = t.get("nickname")
            existing.city = t["city"]
            existing.state = t.get("state")
            existing.year_founded = t.get("year_founded")
        else:
            team = Team(
                id=t["id"],
                full_name=t["full_name"],
                abbreviation=t["abbreviation"],
                nickname=t.get("nickname"),
                city=t["city"],
                state=t.get("state"),
                year_founded=t.get("year_founded")
            )
            db.add(team)
    db.commit()
    db.close()
    print(f"Done — {len(nba_teams)} teams ingested")


def ingest_players():
    db: Session = SessionLocal()
    print("Ingesting players...")
    nba_players = players.get_players()
    for p in nba_players:
        existing = db.query(Player).filter(Player.id == p["id"]).first()
        if existing:
            existing.full_name = p.get("full_name")
            existing.is_active = p.get("is_active")
        else:
            player = Player(
                id=p["id"],
                first_name=p["first_name"],
                last_name=p["last_name"],
                full_name=p.get("full_name"),
                is_active=p.get("is_active"),
                team_id=None
            )
            db.add(player)
    db.commit()
    db.close()
    print(f"Done — {len(nba_players)} players ingested")


def ingest_games(season="2024-25"):
    db: Session = SessionLocal()
    print(f"Ingesting games for {season}...")
    gamefinder = leaguegamefinder.LeagueGameFinder(season_nullable=season)
    games_df = gamefinder.get_data_frames()[0]

    game_ids_seen = set()
    for _, row in games_df.iterrows():
        game_id_str = str(row["GAME_ID"])
        game_id = int(game_id_str)
        if game_id in game_ids_seen:
            continue
        game_ids_seen.add(game_id)

        existing = db.query(Game).filter(Game.id == game_id).first()
        if not existing:
            is_postseason = game_id_str.startswith("004")
            game = Game(
                id=game_id,
                date=row["GAME_DATE"],
                home_team_id=None,
                away_team_id=None,
                home_team_score=None,
                away_team_score=None,
                season=int(season[:4]),
                postseason=is_postseason
            )
            db.add(game)
    db.commit()
    db.close()
    print(f"Done — {len(game_ids_seen)} games ingested")


def ingest_player_stats(season="2024-25"):
    db: Session = SessionLocal()
    print(f"Ingesting player stats for {season}...")

    gamefinder = leaguegamefinder.LeagueGameFinder(season_nullable=season)
    games_df = gamefinder.get_data_frames()[0]
    game_ids = games_df["GAME_ID"].unique().tolist()

    already_done = set(
        row[0] for row in db.query(PlayerGameStats.game_id).distinct().all()
    )

    for i, game_id in enumerate(game_ids):
        if int(game_id) in already_done:
            continue

        try:
            boxscore = boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=game_id,
                end_period=1, end_range=0,
                range_type=0, start_period=1, start_range=0
            )
            player_stats = boxscore.get_data_frames()[0]
            time.sleep(0.6)

            for _, row in player_stats.iterrows():
                if row["personId"] is None:
                    continue
                if row["minutes"] is None or row["minutes"] == "":
                    continue

                player_exists = db.query(Player).filter(Player.id == int(row["personId"])).first()
                if not player_exists:
                    unknown_player = Player(
                        id=int(row["personId"]),
                        first_name=row.get("firstName", "Unknown"),
                        last_name=row.get("familyName", "Unknown"),
                        full_name=f"{row.get('firstName', '')} {row.get('familyName', '')}".strip(),
                        is_active=True,
                        team_id=None
                    )
                    db.add(unknown_player)
                    db.flush()
                    print(f"Created missing player: {row.get('firstName')} {row.get('familyName')} ({row['personId']})")

                team_exists = db.query(Team).filter(Team.id == int(row["teamId"])).first()
                if not team_exists:
                    unknown_team = Team(
                        id=int(row["teamId"]),
                        full_name=row.get("teamName", "Unknown"),
                        abbreviation=row.get("teamTricode", "UNK"),
                        nickname=row.get("teamName", "Unknown"),
                        city=row.get("teamCity", "Unknown"),
                        state=None,
                        year_founded=None
                    )
                    db.add(unknown_team)
                    db.flush()
                    print(f"Created missing team: {row.get('teamName')} ({row['teamId']})")

                stat = PlayerGameStats(
                    player_id=int(row["personId"]),
                    game_id=int(game_id),
                    team_id=int(row["teamId"]),
                    min=str(row["minutes"]) if row["minutes"] else None,
                    pts=int(row["points"]) if row["points"] is not None else None,
                    reb=int(row["reboundsTotal"]) if row["reboundsTotal"] is not None else None,
                    ast=int(row["assists"]) if row["assists"] is not None else None,
                    stl=int(row["steals"]) if row["steals"] is not None else None,
                    blk=int(row["blocks"]) if row["blocks"] is not None else None,
                    fgm=int(row["fieldGoalsMade"]) if row["fieldGoalsMade"] is not None else None,
                    fga=int(row["fieldGoalsAttempted"]) if row["fieldGoalsAttempted"] is not None else None,
                    fg_pct=float(row["fieldGoalsPercentage"]) if row["fieldGoalsPercentage"] is not None else None,
                    fg3m=int(row["threePointersMade"]) if row["threePointersMade"] is not None else None,
                    fg3a=int(row["threePointersAttempted"]) if row["threePointersAttempted"] is not None else None,
                    fg3_pct=float(row["threePointersPercentage"]) if row["threePointersPercentage"] is not None else None,
                    ftm=int(row["freeThrowsMade"]) if row["freeThrowsMade"] is not None else None,
                    fta=int(row["freeThrowsAttempted"]) if row["freeThrowsAttempted"] is not None else None,
                    ft_pct=float(row["freeThrowsPercentage"]) if row["freeThrowsPercentage"] is not None else None,
                    oreb=int(row["reboundsOffensive"]) if row["reboundsOffensive"] is not None else None,
                    dreb=int(row["reboundsDefensive"]) if row["reboundsDefensive"] is not None else None,
                    turnover=int(row["turnovers"]) if row["turnovers"] is not None else None,
                    pf=int(row["foulsPersonal"]) if row["foulsPersonal"] is not None else None,
                )
                db.add(stat)

            db.commit()
            print(f"[{i+1}/{len(game_ids)}] Game {game_id} done")

        except Exception as e:
            db.rollback()
            time.sleep(2)
            continue

    db.close()
    print("Player stats ingestion complete")


def compute_season_averages():
    db: Session = SessionLocal()
    print("Computing season averages...")

    for season in [2023, 2024]:
        player_ids = db.query(PlayerGameStats.player_id).join(Game, PlayerGameStats.game_id == Game.id).filter(Game.season == season).distinct().all()

        for (player_id,) in player_ids:
            stats = db.query(PlayerGameStats).join(Game, PlayerGameStats.game_id == Game.id).filter(
                PlayerGameStats.player_id == player_id,
                Game.season == season,
                Game.postseason == False,
                PlayerGameStats.pts != None
            ).all()

            if not stats:
                continue

            games_played = len(stats)

            def avg(attr):
                vals = [getattr(s, attr) for s in stats if getattr(s, attr) is not None]
                return round(sum(vals) / len(vals), 3) if vals else None

            existing = db.query(SeasonAverage).filter(SeasonAverage.player_id == player_id, SeasonAverage.season == season).first()

            if existing:
                continue

            sa = SeasonAverage(
                player_id=player_id,
                season=season,
                games_played=games_played,
                pts=avg("pts"),
                reb=avg("reb"),
                ast=avg("ast"),
                stl=avg("stl"),
                blk=avg("blk"),
                fg_pct=avg("fg_pct"),
                fg3_pct=avg("fg3_pct"),
                ft_pct=avg("ft_pct"),
            )
            db.add(sa)

        db.commit()
        print(f"Season {season} averages done")
    db.close()
    print("Season averages complete")

if __name__ == "__main__":
    ingest_teams()
    ingest_players()
    ingest_games("2023-24")
    ingest_games("2024-25")
    ingest_player_stats("2023-24")
    ingest_player_stats("2024-25")
    compute_season_averages()