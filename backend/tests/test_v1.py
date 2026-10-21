from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Match,Competition,Team,DataSource,ModelVersion,Prediction,OddsSnapshot
from app.live_models import FixtureObservation
from app.sync import SeasonData,apply_dataset
from app.tips import build_tip,odds_comparison
from app.main import app
import app.sync as sync
import app.v1_api as v1

@pytest.fixture
def factory(monkeypatch,tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'v1.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(sync,'Session',factory);monkeypatch.setattr(v1,'Session',factory)
    return factory

def inputs():
    at=datetime(2026,10,21)
    f={s:{'matches':20,'elo':1500,'form_5':2.,'goals_for':2.,'goals_against':1.,'rest_days':6} for s in ['home','away']}
    p=SimpleNamespace(probabilities=[.7,.2,.1],generated_at=at,snapshot={'features':f,'models':{'poisson':[.7,.2,.1],'elo':[.6,.25,.15],'ensemble_candidate':[.65,.225,.125]},'history':[{'home_id':'A','away_id':'B','kickoff':(at-timedelta(days=5)).isoformat()}],'missing':['xG']})
    m=SimpleNamespace(home_id='A',away_id='B',competition_id='PL',kickoff=at+timedelta(days=2))
    return p,m,at

def test_candidate_explicitly_not_guaranteed():
    p,m,at=inputs();t=build_tip(p,m,at)
    assert t['decision']=='CANDIDATE' and t['outcome']=='HOME' and t['confidence']=='LOW'
    assert t['model_votes']==2 and t['blocks']==[] and 'inte belägg för lönsamhet' in t['note']

@pytest.mark.parametrize('change',['stale_prediction','small_sample','disagreement','weak_probability','old_results'])
def test_abstention(change):
    p,m,at=inputs()
    if change=='stale_prediction':p.generated_at-=timedelta(days=2)
    if change=='small_sample':p.snapshot['features']['home']['matches']=2
    if change=='disagreement':p.snapshot['models']['elo']=[.1,.2,.7]
    if change=='weak_probability':p.probabilities=[.4,.35,.25]
    if change=='old_results':p.snapshot['history'][0]['kickoff']=(at-timedelta(days=50)).isoformat()
    t=build_tip(p,m,at);assert t['decision']=='ABSTAIN' and t['blocks']

def test_high_hit_rate_can_lose():
    c=odds_comparison([.8,.1,.1],[1.1,10,12])
    assert c['model_expected_return'][0]==pytest.approx(-.12) and c['break_even_probabilities'][0]>.9
    assert sum(c['market_probabilities'])==pytest.approx(1)

def dataset(hour='15:00',score=None):
    row={'date':'2026-11-20','time':hour,'round':'R1','team1':'A','team2':'B'}
    if score is not None:row['score']=score
    return SeasonData.model_validate({'name':'Test','matches':[row]})

def test_sync_idempotency_and_schedule_audit(factory):
    meta={'fetched_at':'2026-10-21T12:00:00Z','revision':'a'*40,'url':'https://example.invalid','sha256':'hash'}
    first=apply_dataset(dataset(),meta,'2026-27','PL',datetime(2026,10,21,12))
    second=apply_dataset(dataset(),meta,'2026-27','PL',datetime(2026,10,21,13))
    assert first['inserted']==1 and second['inserted']==0 and second['observations']==0
    third=apply_dataset(dataset('17:30'),{**meta,'revision':'b'*40,'fetched_at':'2026-10-22T12:00:00Z'},'2026-27','PL',datetime(2026,10,22,12))
    assert third['inserted']==0 and third['observations']==1
    with factory() as db:
        before,after=db.query(FixtureObservation).order_by(FixtureObservation.id).all()
        assert before.payload['kickoff_utc']!=after.payload['kickoff_utc'] and db.query(Match).count()==1
        assert db.query(Match).first().kickoff.hour==17

def test_future_result_atomic_rejection(factory):
    with pytest.raises(ValueError,match='before kickoff'):apply_dataset(dataset(score=[0,0]),{'fetched_at':'2026-10-21T12:00:00Z','revision':'a'*40,'url':'url','sha256':'hash'},'2026-27','PL',datetime(2026,10,21))
    with factory() as db:assert db.query(Match).count()==0

@pytest.mark.parametrize('score',[[0,0],{'ft':[2,1]}])
def test_provider_score_formats(score):assert dataset(score=score).matches[0].score.ft is not None

def test_manual_odds_unverified_and_validated(factory):
    at=datetime.now(timezone.utc).replace(tzinfo=None)
    with factory.begin() as db:
        db.add_all([Competition(id='PL',name='PL'),Team(id='a',name='A'),Team(id='b',name='B'),DataSource(id='s',name='s',synthetic=True)]);db.flush()
        db.add(Match(id='m',competition_id='PL',season='demo',home_id='a',away_id='b',kickoff=at+timedelta(days=1),source_id='s',available_at=at-timedelta(days=1),fetched_at=at-timedelta(days=1)))
        db.add(ModelVersion(id='v',created_at=at,config={}));db.flush()
        db.add(Prediction(match_id='m',model_version='v',generated_at=at,data_cutoff_time=at,features_version='f',probabilities=[.8,.1,.1],snapshot={}))
    client=TestClient(app)
    assert client.post('/api/matches/m/compare-odds',json={'home':1,'draw':3,'away':4}).status_code==422
    r=client.post('/api/matches/m/compare-odds',json={'home':1.1,'draw':10,'away':12})
    assert r.status_code==200 and not r.json()['verified'] and r.json()['model_expected_return'][0]<0
    with factory() as db:
        assert db.query(OddsSnapshot).count()==1 and db.get(DataSource,'manual-odds-demo').synthetic is True

def test_reconstructed_training_never_includes_unknown_labels(monkeypatch):
    import app.research as research
    at=datetime(2026,10,21)
    rows=[{'id':'known','kickoff':at-timedelta(days=10),'available_at':at-timedelta(days=1)}, {'id':'future-label','kickoff':at-timedelta(days=5),'available_at':at+timedelta(days=1)}]
    captured=[]
    def fake_fit(data,cutoff):captured.extend(data);return 'model'
    monkeypatch.setattr(research,'fit_boosting',fake_fit)
    assert research.fit_reconstructed_boosting(rows,at)=='model'
    assert [r['id'] for r in captured]==['known']
    assert captured[0]['available_at']==rows[0]['kickoff']+timedelta(days=2)

def test_elo_input_order_is_event_time_not_download_order():
    from app.research import eligible
    at=datetime(2026,10,21)
    rows=[{'id':'b','kickoff':at-timedelta(days=10),'available_at':at-timedelta(days=1)}, {'id':'a','kickoff':at-timedelta(days=5),'available_at':at-timedelta(days=2)}]
    assert [r['id'] for r in eligible(rows,at)]==['b','a']

def test_manual_sync_rate_limit_and_unknown_job(factory):
    from app.live_models import SourceRun
    from app.sync import PROVIDER
    at=datetime.now(timezone.utc).replace(tzinfo=None)
    with factory.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=at,finished_at=at,status='ok',revision='a'*40,details={}))
    client=TestClient(app)
    assert client.post('/api/sync').status_code==429
    assert client.get('/api/sync/'+'0'*32).status_code==404

def test_missing_recent_results_force_abstention():
    p,m,at=inputs();p.snapshot['incomplete_recent_results']=[{'match_id':'missing'}]
    value=build_tip(p,m,at)
    assert value['decision']=='ABSTAIN' and any('Resultat saknas' in b for b in value['blocks'])

def test_withdrawn_fixture_can_return_without_erasing_history(factory):
    meta={'fetched_at':'2026-10-21T12:00:00Z','revision':'a'*40,'url':'url','sha256':'hash'}
    apply_dataset(dataset(),meta,'2026-27','PL',datetime(2026,10,21))
    empty=SeasonData(name='Complete test season after withdrawal',matches=[])
    apply_dataset(empty,{**meta,'revision':'b'*40},'2026-27','PL',datetime(2026,10,22))
    with factory() as db:assert db.query(FixtureObservation).order_by(FixtureObservation.id.desc()).first().payload['status']=='WITHDRAWN'
    apply_dataset(dataset(),{**meta,'revision':'c'*40},'2026-27','PL',datetime(2026,10,23))
    with factory() as db:
        assert db.query(FixtureObservation).count()==3
        assert db.query(FixtureObservation).order_by(FixtureObservation.id.desc()).first().payload['status']=='SCHEDULED'

def test_successful_sync_job_is_persisted_and_pollable(factory,monkeypatch):
    import app.jobs as jobs
    from app.live_models import SourceRun
    from app.sync import PROVIDER
    def complete(job_id):
        at=datetime.now(timezone.utc).replace(tzinfo=None)
        with factory.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=at,finished_at=at,status='ok',revision='a'*40,details={'job_id':job_id,'datasets':[]}))
    monkeypatch.setattr(jobs,'sync_and_predict',complete)
    client=TestClient(app);response=client.post('/api/sync')
    assert response.status_code==202
    job=response.json()['job_id'];status=client.get('/api/sync/'+job).json()
    assert status['status']=='ok' and status['job_id']==job


def test_live_evaluation_does_not_report_pending_as_wins(factory):
    client=TestClient(app);value=client.get('/api/live-performance').json()
    assert value['n']==0 and value['accuracy'] is None and value['roi'] is None
    assert value['protocol']=='prospective-log'

def test_official_csv_supplement_fills_only_identified_results(factory,monkeypatch):
    import app.football_data as fd
    monkeypatch.setattr(fd,'Session',factory)
    stamp=datetime.now(timezone.utc).replace(tzinfo=None)
    kickoff=stamp-timedelta(days=2)
    with factory.begin() as db:
        db.add_all([Competition(id='PL',name='PL'),Team(id='Manchester City FC',name='City'),Team(id='Everton FC',name='Everton'),DataSource(id='s',name='s')]);db.flush()
        db.add(Match(id='known',competition_id='PL',season='2026-27',home_id='Manchester City FC',away_id='Everton FC',kickoff=kickoff,source_id='s',available_at=kickoff-timedelta(days=10),fetched_at=kickoff-timedelta(days=10)))
    row={'Date':kickoff.strftime('%d/%m/%Y'),'Time':kickoff.strftime('%H:%M'),'HomeTeam':'Man City','AwayTeam':'Everton','FTHG':'2','FTAG':'0','FTR':'H','HS':'12','AS':'3'}
    meta={'fetched_at':stamp.isoformat()+'Z','url':'https://www.football-data.co.uk/test.csv','sha256':'digest'}
    first=fd.apply_rows([row],meta,'PL','2026-27');second=fd.apply_rows([row],meta,'PL','2026-27')
    assert first['results_added']==1 and first['stats_added']==2 and second['results_added']==0
    with factory() as db:
        from app.models import Result
        r=db.get(Result,'known');assert r.home_goals==2 and r.available_at==stamp
    unknown={**row,'HomeTeam':'Unknown Club'}
    assert len(fd.apply_rows([unknown],meta,'PL','2026-27')['unmatched'])==1

def test_csv_team_matching_does_not_use_fuzzy_similarity():
    from app.football_data import canonical
    assert canonical('Man City')==canonical('Manchester City FC')
    assert canonical('Man United')!=canonical('Man City')
    assert canonical('Ath Madrid')==canonical('Club Atlético de Madrid')
