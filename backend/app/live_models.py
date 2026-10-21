"""Append-only provider observations and informational model tips."""
from datetime import datetime
from sqlalchemy import String,DateTime,ForeignKey,JSON,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import immutable

class SourceRun(Base):
    __tablename__='source_runs'
    id:Mapped[int]=mapped_column(primary_key=True)
    provider:Mapped[str]=mapped_column(String)
    started_at:Mapped[datetime]=mapped_column(DateTime)
    finished_at:Mapped[datetime]=mapped_column(DateTime)
    status:Mapped[str]=mapped_column(String)
    revision:Mapped[str|None]=mapped_column(String,nullable=True)
    details:Mapped[dict]=mapped_column(JSON)

class FixtureObservation(Base):
    __tablename__='fixture_observations'
    __table_args__=(UniqueConstraint('match_id','payload_sha256'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    match_id:Mapped[str]=mapped_column(ForeignKey('matches.id'))
    observed_at:Mapped[datetime]=mapped_column(DateTime)
    source_id:Mapped[str]=mapped_column(ForeignKey('data_sources.id'))
    payload_sha256:Mapped[str]=mapped_column(String)
    payload:Mapped[dict]=mapped_column(JSON)

class AnalysisTip(Base):
    __tablename__='analysis_tips'
    __table_args__=(UniqueConstraint('prediction_id','policy_version'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    prediction_id:Mapped[int]=mapped_column(ForeignKey('model_predictions.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime)
    policy_version:Mapped[str]=mapped_column(String)
    decision:Mapped[str]=mapped_column(String)
    snapshot:Mapped[dict]=mapped_column(JSON)

for cls in (SourceRun,FixtureObservation,AnalysisTip):
    event.listen(cls,'before_update',immutable)
    event.listen(cls,'before_delete',immutable)
