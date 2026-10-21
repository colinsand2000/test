"""Import verified future fixtures; no fictional dates or teams."""
import argparse,csv
from datetime import datetime,timezone
from pydantic import BaseModel,model_validator
from .db import Session
from .models import Match,Team,Competition,DataSource
from .ingest import COMPETITIONS,utc
class Fixture(BaseModel):
    id:str
    competition_id:str
    season:str
    home_id:str
    away_id:str
    kickoff:datetime
    available_at:datetime
    @model_validator(mode='after')
    def validate_fixture(self):
        self.kickoff=utc(self.kickoff);self.available_at=utc(self.available_at)
        if self.competition_id not in COMPETITIONS or self.home_id==self.away_id:raise ValueError('Invalid competition or teams')
        if self.available_at>=self.kickoff:raise ValueError('Fixture must be known before kickoff')
        if self.available_at>datetime.now(timezone.utc).replace(tzinfo=None):raise ValueError('Future publication time is not verifiable yet')
        return self

def import_fixtures(path,source):
    with open(path) as f:rows=[Fixture.model_validate(r) for r in csv.DictReader(f)]
    now=datetime.now(timezone.utc).replace(tzinfo=None)
    with Session.begin() as db:
        if not db.get(DataSource,source):db.add(DataSource(id=source,name=source,synthetic=False));db.flush()
        for key,name in COMPETITIONS.items():
            if not db.get(Competition,key):db.add(Competition(id=key,name=name))
        db.flush()
        for r in rows:
            if db.get(Match,r.id):raise ValueError('Existing match; updates require a recorded revision')
            for t in [r.home_id,r.away_id]:
                if not db.get(Team,t):db.add(Team(id=t,name=t));db.flush()
            db.add(Match(**r.model_dump(),source_id=source,fetched_at=now))
    return len(rows)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True);p.add_argument('--source',required=True);a=p.parse_args();print(import_fixtures(a.csv,a.source))
