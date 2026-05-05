from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    full_name = Column(String)
    abbreviation = Column(String)
    city = Column(String)
    conference = Column(String)
    division = Column(String)

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    position = Column(String)
    height_feet = Column(Integer, nullable=True)
    height_inches = Column(Integer, nullable=True)
    weight_pounds = Column(Integer, nullable=True)
    draft_year = Column(Integer, nullable=True)
    draft_round = Column(Integer, nullable=True)
    draft_number = Column(Integer, nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team = relationship("Team")

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_team_score = Column(Integer)
    away_team_score = Column(Integer)
    season = Column(Integer)
    postseason = Column(Boolean, default=False)

class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    game_id = Column(Integer, ForeignKey("games.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    min = Column(String, nullable=True)
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