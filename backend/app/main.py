import json
from datetime import datetime,timezone
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from .db import Session
from .models import Match,Team,Prediction,DataSource,Competition,PaperBet,Result
from .research import metrics,label,settle

app=FastAPI(title='Fotbolls-AI',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_methods=['GET','POST'],allow_headers=['*'])

@app.get('/api/health')
def health():
    with Session() as db: db.query(Competition).count()
    return {'status':'ok','mode':'research','real_money':False}

@app.get('/api/competitions')
def competitions():
    with Session() as db: return [{'id':r.id,'name':r.name} for r in db.query(Competition).all()]

def serialize(m,p,source):
    return {'id':m.id,'home':m.home_id,'away':m.away_id,'competition':m.competition_id,'season':m.season,'kickoff':m.kickoff.isoformat()+'Z','synthetic':source.synthetic,'source':source.name,'fetched_at':m.fetched_at.isoformat()+'Z','probabilities':p.probabilities if p else None,'confidence':'LOW' if p else None,'data_quality':'LOW','prediction_id':p.id if p else None,'generated_at':p.generated_at.isoformat()+'Z' if p else None,'cutoff':p.data_cutoff_time.isoformat()+'Z' if p else None,'model_version':p.model_version if p else None}

@app.get('/api/matches')
def matches(synthetic:bool=False,competition:str|None=None):
    with Session() as db:
        q=db.query(Match,DataSource).join(DataSource).filter(DataSource.synthetic==synthetic,Match.kickoff>=datetime.now(timezone.utc).replace(tzinfo=None))
        if competition: q=q.filter(Match.competition_id==competition)
        output=[]
        for m,s in q.order_by(Match.kickoff).limit(100):
            p=db.query(Prediction).filter_by(match_id=m.id).order_by(Prediction.id.desc()).first()
            output.append(serialize(m,p,s))
        return output

@app.get('/api/matches/{match_id}')
def match_detail(match_id:str):
    with Session() as db:
        m=db.get(Match,match_id)
        if not m: raise HTTPException(404,'Match not found')
        s=db.get(DataSource,m.source_id)
        ps=db.query(Prediction).filter_by(match_id=m.id).order_by(Prediction.id.desc()).all()
        return {**serialize(m,ps[0] if ps else None,s),'snapshot':ps[0].snapshot if ps else None,'versions':[{'id':p.id,'generated_at':p.generated_at.isoformat()+'Z','supersedes_id':p.supersedes_id,'model_version':p.model_version} for p in ps]}


def portfolio(synthetic=False,competition=None,season=None):
    with Session() as db:
        query=db.query(PaperBet,Prediction,Match).join(Prediction,PaperBet.prediction_id==Prediction.id).join(Match,Prediction.match_id==Match.id).join(DataSource,Match.source_id==DataSource.id).filter(DataSource.synthetic==synthetic)
        if competition:query=query.filter(Match.competition_id==competition)
        if season:query=query.filter(Match.season==season)
        pnls=[];stakes=[];count=0
        for b,p,m in query.all():
            count+=1;r=db.get(Result,m.id)
            if r and r.available_at<=datetime.now(timezone.utc).replace(tzinfo=None):pnls.append(settle(b.outcome,label(r.home_goals,r.away_goals),b.odds,b.stake));stakes.append(b.stake)
        return {'paper_bets':count,'roi':sum(pnls)/sum(stakes) if stakes else None,'wins':sum(x>0 for x in pnls),'losses':sum(x<0 for x in pnls),'pnl':sum(pnls) if pnls else None}

@app.get('/api/performance')
def performance(synthetic:bool=False,competition:str|None=None,season:str|None=None,model:str='poisson',confidence:str|None=None):
    virtual=portfolio(synthetic,competition,season) if confidence in (None,'','LOW') else {'paper_bets':0,'roi':None,'wins':0,'losses':0,'pnl':None}
    artifacts=[]
    for path in Path('artifacts').glob('backtest-*.json'):
        value=json.loads(path.read_text())
        if value['synthetic']==synthetic: artifacts.append(value)
    if not artifacts: return {**virtual,'status':'no_evaluation','n':0,'message':'Kör ett walk-forward-backtest på importerad historik.'}
    run=max(artifacts,key=lambda x:x['run_id'])
    rows=[r for r in run['rows'] if model in r['probabilities'] and (not competition or r['competition']==competition) and (not season or r['season']==season) and (not confidence or r['confidence']==confidence)]
    score=metrics([r['probabilities'][model] for r in rows],[r['actual'] for r in rows])
    def grouped(key):
        return {v:metrics([r['probabilities'][model] for r in rows if r[key]==v],[r['actual'] for r in rows if r[key]==v]) for v in sorted({r[key] for r in rows})}
    correct=sum(max(range(3),key=lambda j:r['probabilities'][model][j])==r['actual'] for r in rows)
    return {**score,'status':'evaluated','synthetic':synthetic,'model':model,'protocol':run.get('protocol','recorded-availability'),'run_id':run['run_id'],'model_version':run['model_version'],**virtual,'correct':correct,'incorrect':len(rows)-correct,'by_league':grouped('competition'),'by_season':grouped('season'),'by_confidence':grouped('confidence'),'models':{name:metrics([r['probabilities'][name] for r in rows if name in r['probabilities']],[r['actual'] for r in rows if name in r['probabilities']]) for name in run['metrics']},'notes':run['notes'],'timeline':[{'kickoff':r['kickoff'],'correct':int(max(range(3),key=lambda j:r['probabilities'][model][j])==r['actual'])} for r in rows]}

@app.get('/api/paper-bets')
def paper_bets(synthetic:bool=False):
    with Session() as db:
        rows=[]
        for b,p,m,s in db.query(PaperBet,Prediction,Match,DataSource).join(Prediction,PaperBet.prediction_id==Prediction.id).join(Match,Prediction.match_id==Match.id).join(DataSource,Match.source_id==DataSource.id).filter(DataSource.synthetic==synthetic).all():
            r=db.get(Result,m.id)
            if r and r.available_at>datetime.now(timezone.utc).replace(tzinfo=None):r=None
            actual=label(r.home_goals,r.away_goals) if r else None
            rows.append({'id':b.id,'match_id':m.id,'model_version':p.model_version,'created_at':b.created_at.isoformat()+'Z','outcome':b.outcome,'probability':b.probability,'market_probability':b.market_probability,'odds':b.odds,'stake':b.stake,'synthetic':s.synthetic,'actual':actual,'pnl':settle(b.outcome,actual,b.odds,b.stake) if r else None})
        settled=[r for r in rows if r['pnl'] is not None]
        profit=sum(r['pnl'] for r in settled);stake=sum(r['stake'] for r in settled)
        return {'rows':rows,'n':len(rows),'settled':len(settled),'roi':profit/stake if stake else None,'pnl':profit if settled else None,'wins':sum(r['pnl']>0 for r in settled),'losses':sum(r['pnl']<0 for r in settled)}

from .v1_api import router as v1_router
app.include_router(v1_router)
