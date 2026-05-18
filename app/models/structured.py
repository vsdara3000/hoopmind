from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    full_name = Column(String)
    abbreviation = Column(String)
    nickname = Column(String, nullable=True)
    city = Column(String)
    state = Column(String, nullable=True)
    year_founded = Column(Integer, nullable=True)

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team = relationship("Team")

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    home_team_score = Column(Integer, nullable=True)
    away_team_score = Column(Integer, nullable=True)
    home_team_wins = Column(Boolean, nullable=True)
    season = Column(Integer)
    postseason = Column(Boolean, default=False)
    # new columns
    home_team_fg_pct = Column(Float, nullable=True)
    away_team_fg_pct = Column(Float, nullable=True)
    home_team_fg3_pct = Column(Float, nullable=True)
    away_team_fg3_pct = Column(Float, nullable=True)
    home_team_reb = Column(Integer, nullable=True)
    away_team_reb = Column(Integer, nullable=True)
    home_team_ast = Column(Integer, nullable=True)
    away_team_ast = Column(Integer, nullable=True)
    home_team_tov = Column(Integer, nullable=True)
    away_team_tov = Column(Integer, nullable=True)
    home_team_stl = Column(Integer, nullable=True)
    away_team_stl = Column(Integer, nullable=True)
    home_team_blk = Column(Integer, nullable=True)
    away_team_blk = Column(Integer, nullable=True)

class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    game_id = Column(Integer, ForeignKey("games.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    min = Column(Float, nullable=True)  # Changed from String to Float
    pts = Column(Integer, nullable=True)
    reb = Column(Integer, nullable=True)
    ast = Column(Integer, nullable=True)
    stl = Column(Integer, nullable=True)
    blk = Column(Integer, nullable=True)
    fgm = Column(Integer, nullable=True)
    fga = Column(Integer, nullable=True)
    fg_pct = Column(Float, nullable=True)
    fg3m = Column(Integer, nullable=True)
    fg3a = Column(Integer, nullable=True)
    fg3_pct = Column(Float, nullable=True)
    ftm = Column(Integer, nullable=True)
    fta = Column(Integer, nullable=True)
    ft_pct = Column(Float, nullable=True)
    oreb = Column(Integer, nullable=True)
    dreb = Column(Integer, nullable=True)
    turnover = Column(Integer, nullable=True)
    pf = Column(Integer, nullable=True)

class SeasonAverage(Base):
    __tablename__ = "season_averages"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    season = Column(Integer)
    games_played = Column(Integer, nullable=True)
    min = Column(Float, nullable=True)
    pts = Column(Float, nullable=True)
    reb = Column(Float, nullable=True)
    ast = Column(Float, nullable=True)
    stl = Column(Float, nullable=True)
    blk = Column(Float, nullable=True)
    fg_pct = Column(Float, nullable=True)
    fg3_pct = Column(Float, nullable=True)
    ft_pct = Column(Float, nullable=True)