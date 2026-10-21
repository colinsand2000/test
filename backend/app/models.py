from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)

class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)

class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    synthetic: Mapped[bool] = mapped_column(default=False)

class Match(Base):
    __tablename__ = "matches"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"))
    season: Mapped[str] = mapped_column(String)
    home_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    away_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    kickoff: Mapped[datetime] = mapped_column(DateTime)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    available_at: Mapped[datetime] = mapped_column(DateTime)

class Result(Base):
    __tablename__ = "results"
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    available_at: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))

class TeamMatchStat(Base):
    __tablename__ = "team_match_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    available_at: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    values: Mapped[dict] = mapped_column(JSON)

class Player(Base):
    __tablename__ = "players"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String)

class Injury(Base):
    __tablename__ = "injuries"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    available_at: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    details: Mapped[dict] = mapped_column(JSON)

class Lineup(Base):
    __tablename__ = "lineups"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    available_at: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    details: Mapped[dict] = mapped_column(JSON)

class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    available_at: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    odds: Mapped[list] = mapped_column(JSON)

class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    config: Mapped[dict] = mapped_column(JSON)

class Prediction(Base):
    __tablename__ = "model_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    model_version: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime)
    data_cutoff_time: Mapped[datetime] = mapped_column(DateTime)
    features_version: Mapped[str] = mapped_column(String)
    probabilities: Mapped[list] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("model_predictions.id"), nullable=True)

class PaperBet(Base):
    __tablename__ = "paper_bets"
    __table_args__ = (UniqueConstraint("prediction_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("model_predictions.id"))
    odds_snapshot_id: Mapped[int] = mapped_column(ForeignKey("odds_snapshots.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    outcome: Mapped[int] = mapped_column(Integer)
    probability: Mapped[float] = mapped_column(Float)
    market_probability: Mapped[float] = mapped_column(Float)
    odds: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float, default=1.0)

# API exposes no mutation endpoint; protect ordinary ORM updates as well.
def immutable(*_):
    raise ValueError("Append-only record: create a new version instead")
for table in (Prediction, ModelVersion, PaperBet, Result, OddsSnapshot):
    event.listen(table, "before_update", immutable)
    event.listen(table, "before_delete", immutable)
