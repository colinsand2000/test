import argparse,csv
from datetime import datetime,timezone
from pydantic import BaseModel,model_validator
from .ingest import utc
from .models import Match,DataSource,OddsSnapshot
from .research import normalize_odds
from .db import Session

class OddsRow(BaseModel):
    match_id:str
    available_at:datetime
    home:float
    draw:float
    away:float
    @model_validator(mode='after')
    def validate_odds(self):
        self.available_at=utc(self.available_at)
        normalize_odds([self.home,self.draw,self.away]);return self

def import_odds(path,source):
    with open(path) as f:rows=[OddsRow.model_validate(r) for r in csv.DictReader(f)]
    with Session.begin() as db:
        if not db.get(DataSource,source):db.add(DataSource(id=source,name=source,synthetic=False));db.flush()
        for r in rows:
            m=db.get(Match,r.match_id)
            if not m:raise ValueError('Unknown match')
            if r.available_at>=m.kickoff:raise ValueError('Pre-match odds required')
            if db.query(OddsSnapshot).filter_by(match_id=r.match_id,source_id=source,available_at=r.available_at).first():raise ValueError('Duplicate odds snapshot')
            db.add(OddsSnapshot(match_id=r.match_id,source_id=source,available_at=r.available_at,fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),odds=[r.home,r.draw,r.away]))
    return len(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True);p.add_argument('--source',required=True);a=p.parse_args();print(import_odds(a.csv,a.source))
