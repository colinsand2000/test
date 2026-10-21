from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Competition,DataSource,Team,Match,ModelVersion,Prediction

def test_predictions_append_only_and_reproducible():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Competition(id='PL',name='PL'),DataSource(id='x',name='x'),Team(id='a',name='A'),Team(id='b',name='B')]);db.flush()
        db.add(Match(id='m',competition_id='PL',season='s',home_id='a',away_id='b',kickoff=datetime(2025,1,1),fetched_at=datetime(2024,1,1),available_at=datetime(2024,1,1),source_id='x'))
        db.add(ModelVersion(id='v',created_at=datetime(2024,1,1),config={}));db.flush()
        p=Prediction(match_id='m',model_version='v',generated_at=datetime(2024,1,1),data_cutoff_time=datetime(2024,1,1),features_version='v1',probabilities=[.5,.2,.3],snapshot={'features':{'elo':1500}})
        db.add(p);db.commit();ident=p.id
        assert db.get(Prediction,ident).snapshot['features']['elo']==1500
        p.probabilities=[.9,.05,.05]
        with pytest.raises(ValueError,match='Append-only'):db.commit()
        db.rollback();assert db.get(Prediction,ident).probabilities==[.5,.2,.3]
