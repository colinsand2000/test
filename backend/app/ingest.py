"""Strict, atomic CSV ingestion. Only licensed sources should be imported."""
import csv
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from .db import Session
from .models import Competition, Team, Match, Result, DataSource, OddsSnapshot

COMPETITIONS={'PL':'Premier League','LL':'La Liga','BL':'Bundesliga','SA':'Serie A','L1':'Ligue 1','CL':'Champions League','EL':'Europa League'}

def utc(value):
    if value.tzinfo is None: raise ValueError('Timezone required: use ISO 8601 with Z or +00:00')
    return value.astimezone(timezone.utc).replace(tzinfo=None)

class MatchRow(BaseModel):
    id: str = Field(min_length=1)
    competition_id: str
    season: str
    home_id: str
    away_id: str
    kickoff: datetime
    available_at: datetime
    result_available_at: datetime
    home_goals: int = Field(ge=0,le=50)
    away_goals: int = Field(ge=0,le=50)
    @model_validator(mode='after')
    def validate_row(self):
        self.kickoff=utc(self.kickoff);self.available_at=utc(self.available_at);self.result_available_at=utc(self.result_available_at)
        if self.home_id==self.away_id: raise ValueError('Teams must differ')
        if self.competition_id not in COMPETITIONS: raise ValueError('Unknown competition')
        if self.result_available_at <= self.kickoff: raise ValueError('Result must be available after kickoff')
        return self

def import_csv(path, source, synthetic=False):
    rows=[MatchRow.model_validate(r) for r in csv.DictReader(Path(path).open())]
    if len({r.id for r in rows})!=len(rows): raise ValueError('Duplicate match ids in CSV')
    now=datetime.now(timezone.utc).replace(tzinfo=None)
    with Session.begin() as db:
        existing=db.get(DataSource,source)
        if existing and existing.synthetic!=synthetic: raise ValueError('Cannot mix real and synthetic source identity')
        if not existing: db.add(DataSource(id=source,name=source,synthetic=synthetic));db.flush()
        for key,name in COMPETITIONS.items():
            if not db.get(Competition,key): db.add(Competition(id=key,name=name))
        db.flush()
        for r in rows:
            if db.get(Match,r.id): raise ValueError(f'Match already exists: {r.id}; import rolled back')
            for t in (r.home_id,r.away_id):
                if not db.get(Team,t): db.add(Team(id=t,name=t));db.flush()
            db.add(Match(id=r.id,competition_id=r.competition_id,season=r.season,home_id=r.home_id,away_id=r.away_id,kickoff=r.kickoff,available_at=r.available_at,source_id=source,fetched_at=now))
            db.flush()
            db.add(Result(match_id=r.id,home_goals=r.home_goals,away_goals=r.away_goals,available_at=r.result_available_at,source_id=source,fetched_at=now))
    return len(rows)

def history(db, synthetic=False):
    rows=db.query(Match,Result).join(Result,Result.match_id==Match.id).join(DataSource,DataSource.id==Match.source_id).filter(DataSource.synthetic==synthetic).all()
    return [dict(id=m.id,competition_id=m.competition_id,season=m.season,home_id=m.home_id,away_id=m.away_id,kickoff=m.kickoff,available_at=max(m.available_at,r.available_at),home_goals=r.home_goals,away_goals=r.away_goals,source_id=m.source_id,fetched_at=r.fetched_at.isoformat()) for m,r in rows]
