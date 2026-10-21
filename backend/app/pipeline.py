import argparse
import csv
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
from .db import Session
from .models import Match, Team, DataSource, Prediction, ModelVersion, Result
from .ingest import import_csv, history
from .research import features,predict,fit_boosting,fit_reconstructed_boosting,walk_forward,metrics,digest,eligible,FEATURE_VERSION,MODEL_VERSION

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)

def demo():
    """Fictional teams, fictional matches, fixed RNG. Never real forecasts."""
    with Session.begin() as db:
        if db.get(DataSource,'synthetic-v1'):
            if not db.query(Match).filter(Match.source_id=='synthetic-v1',Match.kickoff>now()).first():
                k=now().replace(hour=23,minute=30,second=0,microsecond=0)+timedelta(days=1)
                for j in range(0,12,2):
                    db.add(Match(id=f'demo-upcoming-{k.date()}-{j}',competition_id='PL',season='synthetic',home_id=f'Demolag {j+1:02}',away_id=f'Demolag {j+2:02}',kickoff=k,available_at=now(),fetched_at=now(),source_id='synthetic-v1'))
            return
    path=Path('artifacts/synthetic.csv');path.parent.mkdir(exist_ok=True)
    rng=np.random.default_rng(42)
    start=now().replace(hour=15,minute=0,second=0,microsecond=0)-timedelta(days=180)
    rows=[]
    teams=[f'Demolag {i+1:02}' for i in range(12)]
    for day in range(0,160,3):
        order=rng.permutation(12)
        for j in range(0,12,2):
            h,a=teams[order[j]],teams[order[j+1]]; k=start+timedelta(days=day)
            rows.append(dict(id=f'demo-{day}-{j}',competition_id='PL',season='synthetic',home_id=h,away_id=a,kickoff=k.isoformat()+'Z',available_at=(k-timedelta(days=7)).isoformat()+'Z',result_available_at=(k+timedelta(hours=3)).isoformat()+'Z',home_goals=int(rng.poisson(1.5)),away_goals=int(rng.poisson(1.2))))
    with path.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    import_csv(path,'synthetic-v1',True)
    with Session.begin() as db:
        for j in range(0,12,2):
            k=now().replace(hour=23,minute=30,second=0,microsecond=0)+timedelta(days=1)
            db.add(Match(id=f'demo-upcoming-{j}',competition_id='PL',season='synthetic',home_id=teams[j],away_id=teams[j+1],kickoff=k,available_at=now(),fetched_at=now(),source_id='synthetic-v1'))

def generate(synthetic=False):
    from .live_models import FixtureObservation
    from .tips import build_tip,POLICY_VERSION
    from .live_models import AnalysisTip
    with Session.begin() as db:
        cutoff=now()
        all_history=eligible(history(db,synthetic),cutoff)
        code=Path(__file__).with_name('research.py').read_text()
        code_sha=digest(code)
        archive=Path('artifacts/code')/code_sha;archive.mkdir(parents=True,exist_ok=True)
        (archive/'research.py').write_text(code)
        (archive/'requirements.lock').write_text(Path('requirements.lock').read_text())
        upcoming=db.query(Match).join(DataSource).filter(DataSource.synthetic==synthetic,Match.kickoff>cutoff,Match.kickoff<=cutoff+timedelta(days=7),Match.available_at<=cutoff).all()
        for competition in sorted({m.competition_id for m in upcoming}):
            h=[r for r in all_history if r['competition_id']==competition]
            version='v1-'+digest({'history':h,'code':code_sha,'competition':competition})[:16]
            if not db.get(ModelVersion,version):
                db.add(ModelVersion(id=version,created_at=cutoff,config={'code_sha256':code_sha,'code_version':MODEL_VERSION,'features':FEATURE_VERSION,'training_data_sha256':digest(h),'parameters':{'home_advantage':1.12,'elo_home_points':65,'elo_k':20,'random_seed':7},'synthetic':synthetic,'production_model':'poisson','calibration_status':'not_validated','competition':competition,'boosting_training_protocol':'recorded-availability' if synthetic else 'retrospective-assumed-48h'}));db.flush()
            boosting=fit_boosting(h,cutoff) if synthetic else fit_reconstructed_boosting(h,cutoff)
            for m in [m for m in upcoming if m.competition_id==competition]:
                observation=db.query(FixtureObservation).filter_by(match_id=m.id).order_by(FixtureObservation.id.desc()).first()
                if observation and (observation.payload['kickoff_precision']=='date-only' or observation.payload.get('status')=='WITHDRAWN'):continue
                # Features describe the scheduled match time; history is frozen at the generation cutoff.
                f=features(h,m.home_id,m.away_id,m.kickoff);p=predict(f,boosting)
                previous=db.query(Prediction).filter_by(match_id=m.id).order_by(Prediction.id.desc()).first()
                missing_results=[]
                recent=db.query(Match).outerjoin(Result,Result.match_id==Match.id).filter(Match.source_id==m.source_id,Match.season==m.season,Match.kickoff>cutoff-timedelta(days=35),Match.kickoff<cutoff-timedelta(hours=6),Result.match_id==None).all()
                for prior in recent:
                    if not {m.home_id,m.away_id}.intersection({prior.home_id,prior.away_id}):continue
                    event=db.query(FixtureObservation).filter_by(match_id=prior.id).order_by(FixtureObservation.id.desc()).first()
                    if event and event.payload.get('status')=='WITHDRAWN':continue
                    missing_results.append({'match_id':prior.id,'home':prior.home_id,'away':prior.away_id,'kickoff':prior.kickoff.isoformat()+'Z'})
                snapshot={'incomplete_recent_results':missing_results,'boosting_training_protocol':'recorded-availability' if synthetic else 'retrospective-assumed-48h','code_sha256':code_sha,'feature_reference_time':m.kickoff.isoformat(),'features':f,'models':p,'history':[{**r,'kickoff':r['kickoff'].isoformat(),'available_at':r['available_at'].isoformat()} for r in h], 'missing':['xG','xGA','skador','avstängningar','startelvor','skott'], 'synthetic':synthetic,'confidence':'LOW','data_quality':'LOW','calibration_status':'not_validated','fixture_observation_id':observation.id if observation else None,'scheduled_kickoff':m.kickoff.isoformat()+'Z','competition':competition}
                # Preserve prior forecasts; avoid identical hourly clones if nothing has changed.
                if previous and previous.model_version==version and previous.snapshot['features']==f and previous.snapshot.get('fixture_observation_id')==snapshot['fixture_observation_id'] and previous.snapshot.get('incomplete_recent_results',[])==missing_results and cutoff-previous.generated_at<timedelta(hours=12):
                    prediction=previous
                else:
                    prediction=Prediction(match_id=m.id,model_version=version,generated_at=cutoff,data_cutoff_time=cutoff,features_version=FEATURE_VERSION,probabilities=p['poisson'],snapshot=snapshot,supersedes_id=previous.id if previous else None)
                    db.add(prediction);db.flush()
                if not db.query(AnalysisTip).filter_by(prediction_id=prediction.id,policy_version=POLICY_VERSION).first():
                    tip=build_tip(prediction,m,cutoff)
                    db.add(AnalysisTip(prediction_id=prediction.id,created_at=cutoff,policy_version=POLICY_VERSION,decision=tip['decision'],snapshot=tip))

def backtest(synthetic=False, reconstructed=False, competition=None):
    with Session() as db: h=history(db,synthetic)
    if competition: h=[r for r in h if r["competition_id"]==competition]
    if reconstructed:
        if synthetic: raise ValueError("Reconstruction is for retrospective real data only")
        h=[{**r,"available_at":r["kickoff"]+timedelta(days=2)} for r in h]
    runs=walk_forward(h)
    scores={}
    for model in ('poisson','elo','boosting','ensemble_candidate','poisson_calibrated','elo_calibrated','boosting_calibrated'):
        selected=[r for r in runs if model in r['probabilities']]
        scores[model]=metrics([r['probabilities'][model] for r in selected],[r['actual'] for r in selected])
    # Persist dated immutable artifacts, including all evaluated rows and complete input history.
    code=Path(__file__).with_name('research.py').read_text();code_sha=digest(code)
    archive=Path('artifacts/code')/code_sha;archive.mkdir(parents=True,exist_ok=True)
    (archive/'research.py').write_text(code);(archive/'requirements.lock').write_text(Path('requirements.lock').read_text())
    stamp=now().strftime('%Y%m%dT%H%M%S%f')
    artifact={'code_sha256':code_sha,'run_id':stamp,'generated_at':now().isoformat()+'Z','synthetic':synthetic,'protocol':'retrospective-assumed-48h' if reconstructed else 'recorded-availability','data_sha256':digest(h),'model_version':MODEL_VERSION,'features_version':FEATURE_VERSION,'rows':runs,'metrics':scores,'history':h,'notes':['No historical odds imported: paper ROI unavailable', 'Historical availability is assumed at match date + 48h; NOT verified point-in-time evidence' if reconstructed else 'Uses recorded availability times','Probabilities are uncalibrated candidates; confidence remains LOW','Ensemble has not been promoted; evaluation requires separate temporal holdout']}
    out=Path('artifacts');out.mkdir(exist_ok=True)
    (out/f'backtest-{stamp}.json').write_text(json.dumps(artifact,default=str))
    print(json.dumps({k:{a:b for a,b in v.items() if a!='reliability'} for k,v in scores.items()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['demo','import','predict','backtest']);p.add_argument('--csv');p.add_argument('--source');p.add_argument('--synthetic',action='store_true');p.add_argument('--reconstructed',action='store_true');p.add_argument('--competition');a=p.parse_args()
    if a.command=='demo': demo();generate(True)
    elif a.command=='import':
        if not a.csv or not a.source: p.error('--csv and --source required')
        print(import_csv(a.csv,a.source,a.synthetic))
    elif a.command=='predict': generate(a.synthetic)
    else: backtest(a.synthetic,a.reconstructed,a.competition)
