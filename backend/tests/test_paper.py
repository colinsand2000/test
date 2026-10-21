from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Competition,Team,DataSource,Match,Prediction,ModelVersion,OddsSnapshot,Result
from app import paper
from app.main import portfolio
import app.main as api

class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime.now(timezone.utc)-timedelta(days=2)

def test_virtual_losses_retained_and_late_entries_rejected(monkeypatch):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(paper,'Session',factory);monkeypatch.setattr(api,'Session',factory)
    now=datetime.now(timezone.utc).replace(tzinfo=None);kickoff=now-timedelta(days=1)
    with factory.begin() as db:
        db.add_all([Competition(id='PL',name='PL'),Team(id='a',name='a'),Team(id='b',name='b'),DataSource(id='s',name='s')]);db.flush()
        db.add(Match(id='m',competition_id='PL',season='2024',home_id='a',away_id='b',kickoff=kickoff,available_at=now-timedelta(days=4),fetched_at=now-timedelta(days=4),source_id='s'))
        db.add(ModelVersion(id='v',created_at=now-timedelta(days=3),config={}));db.flush()
        p=Prediction(match_id='m',model_version='v',generated_at=now-timedelta(days=3),data_cutoff_time=now-timedelta(days=3),features_version='v',probabilities=[.6,.2,.2],snapshot={})
        o=OddsSnapshot(match_id='m',source_id='s',available_at=now-timedelta(days=4),fetched_at=now-timedelta(days=4),odds=[2.,3.,4.])
        db.add_all([p,o]);db.flush();pid,oid=p.id,o.id
    with pytest.raises(ValueError,match='before kickoff'):paper.record(pid,oid,0)
    monkeypatch.setattr(paper,'datetime',Clock)
    paper.record(pid,oid,0)
    with factory.begin() as db:db.add(Result(match_id='m',home_goals=0,away_goals=2,available_at=now-timedelta(hours=1),fetched_at=now-timedelta(hours=1),source_id='s'))
    summary=portfolio(False)
    assert summary['paper_bets']==1 and summary['losses']==1 and summary['wins']==0
    assert summary['pnl']==-1 and summary['roi']==-1
    assert portfolio(True)['paper_bets']==0
