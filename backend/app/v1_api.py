import json
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,HTTPException,Query
from pydantic import BaseModel,Field,model_validator
from .db import Session
from .models import Match,Prediction,DataSource,OddsSnapshot,Result
from .live_models import AnalysisTip,SourceRun,FixtureObservation
from .sync import PROVIDER,season_for
from .tips import odds_comparison,build_tip,POLICY_VERSION

router=APIRouter(prefix='/api')
def now():return datetime.now(timezone.utc).replace(tzinfo=None)

def provider_status(db):
    current=season_for(now());output={}
    recent=db.query(SourceRun).filter_by(provider=PROVIDER).order_by(SourceRun.id.desc()).limit(30).all()
    for league in ['PL','LL','BL','SA','L1','CL','EL']:
        last=None
        for run in recent:
            if any(d['competition']==league and d['season']==current for d in run.details.get('datasets',[])):
                last=run;break
        output[league]={'state':'CONNECTED' if last and now()-last.finished_at<timedelta(hours=36) else 'STALE' if last else 'UNAVAILABLE','checked_at':last.finished_at.isoformat()+'Z' if last else None,'revision':last.revision if last else None,'source':'OpenFootball · CC0' if last else None,'realtime':False,'note':'Offentligt källrepo, inte realtidsfeed. Källans lokala matchtid tolkas i ligans tidszon.' if last else 'Ingen ansluten verifierad källa.'}
    return output

@router.get('/status')
def status():
    with Session() as db:
        providers=provider_status(db)
        latest=db.query(SourceRun).filter_by(provider=PROVIDER).order_by(SourceRun.id.desc()).first()
        from .football_data import PROVIDER as SUPPLEMENT_PROVIDER
        supplement=db.query(SourceRun).filter_by(provider=SUPPLEMENT_PROVIDER).order_by(SourceRun.id.desc()).first()
        return {'version':'1.0.0','mode':'personal-analysis','payments':False,'automatic_betting':False,'sources':providers,'latest_sync':{'status':latest.status,'finished_at':latest.finished_at.isoformat()+'Z','details':latest.details} if latest else None,'supplement':{'status':supplement.status,'checked_at':supplement.finished_at.isoformat()+'Z','details':supplement.details} if supplement else None,'odds':'CSV_OBSERVATIONS_AND_MANUAL' if supplement and supplement.status=='ok' else 'MANUAL_COMPARISON_ONLY','calibration':'NOT_INDEPENDENTLY_VALIDATED','missing':['Verifierat oddsflöde','Skador och startelvor','xG','CL/EL-källa'],'cadence_minutes':60}

@router.get('/tips')
def tips(synthetic:bool=False,competition:str|None=None,days:int=Query(7,ge=1,le=7),decision:str|None=None):
    with Session() as db:
        sources=provider_status(db);at=now()
        query=db.query(Match,DataSource).join(DataSource).filter(DataSource.synthetic==synthetic,Match.kickoff>at,Match.kickoff<=at+timedelta(days=days))
        if competition:query=query.filter(Match.competition_id==competition)
        rows=[]
        for match,source in query.order_by(Match.kickoff).all():
            p=db.query(Prediction).filter_by(match_id=match.id).order_by(Prediction.id.desc()).first()
            record=db.query(AnalysisTip).filter_by(prediction_id=p.id,policy_version=POLICY_VERSION).first() if p else None
            value=build_tip(p,match,at) if p else {'decision':'ABSTAIN','blocks':['Ingen verifierbar modellprognos finns ännu.'],'probability':None,'outcome':None,'reasons':[],'confidence':'LOW','missing':[]}
            if not synthetic and sources.get(match.competition_id,{}).get('state')!='CONNECTED':
                value['decision']='ABSTAIN';value['blocks'].append('Källans synk är saknad eller äldre än 36 timmar.')
            # A fixture revision invalidates forecasts made for a superseded schedule.
            obs=db.query(FixtureObservation).filter_by(match_id=match.id).order_by(FixtureObservation.id.desc()).first()
            if obs and obs.payload.get('status')=='WITHDRAWN':
                value['decision']='ABSTAIN';value['blocks'].append('Matchen saknas i senaste fullständiga källschemat; inget tips lämnas.')
            if p and obs and p.snapshot.get('fixture_observation_id')!=obs.id:
                value['decision']='ABSTAIN';value['blocks'].append('Spelschemat har ändrats efter prognosen; invänta omberäkning.')
            row={**value,'match_id':match.id,'home':match.home_id,'away':match.away_id,'competition':match.competition_id,'kickoff':match.kickoff.isoformat()+'Z','synthetic':source.synthetic,'probabilities':p.probabilities if p else None,'prediction_id':p.id if p else None,'tip_id':record.id if record else None,'model_version':p.model_version if p else None,'generated_at':p.generated_at.isoformat()+'Z' if p else None,'data_cutoff_time':p.data_cutoff_time.isoformat()+'Z' if p else None,'source':source.name,'kickoff_precision':obs.payload.get('kickoff_precision') if obs else 'provided','timezone':obs.payload.get('timezone') if obs else 'UTC','source_checked_at':sources.get(match.competition_id,{}).get('checked_at')}
            rows.append(row)
        candidates=sum(r['decision']=='CANDIDATE' for r in rows)
        if decision:rows=[r for r in rows if r['decision']==decision]
        rows.sort(key=lambda r:(r['decision']!='CANDIDATE',-(r.get('probability') or 0),r['kickoff']))
        return {'rows':rows,'total':len(rows),'candidates':candidates,'abstain':sum(r['decision']=='ABSTAIN' for r in rows),'policy_version':POLICY_VERSION,'notice':'Kandidater är modellens förstaval, inte säkra spel eller bevis på lönsamhet.'}

@router.get('/prediction-log')
def prediction_log(synthetic:bool=False,limit:int=Query(100,ge=1,le=500)):
    with Session() as db:
        query=db.query(Prediction,Match,DataSource).join(Match,Prediction.match_id==Match.id).join(DataSource,Match.source_id==DataSource.id).filter(DataSource.synthetic==synthetic).order_by(Prediction.id.desc()).limit(limit)
        rows=[]
        for p,m,s in query:
            result=db.get(Result,m.id)
            if result and result.available_at>now():result=None
            outcome=0 if result and result.home_goals>result.away_goals else 1 if result and result.home_goals==result.away_goals else 2 if result else None
            pick=max(range(3),key=lambda i:p.probabilities[i])
            rows.append({'id':p.id,'match_id':m.id,'home':m.home_id,'away':m.away_id,'competition':m.competition_id,'synthetic':s.synthetic,'generated_at':p.generated_at.isoformat()+'Z','cutoff':p.data_cutoff_time.isoformat()+'Z','model_version':p.model_version,'features_version':p.features_version,'probabilities':p.probabilities,'outcome':outcome,'correct':pick==outcome if outcome is not None else None,'supersedes_id':p.supersedes_id,'scheduled_kickoff':p.snapshot.get('scheduled_kickoff',m.kickoff.isoformat()+'Z')})
        return {'rows':rows,'returned':len(rows),'limit':limit,'note':'Alla prognosversioner i urvalet redovisas. Väntande utfall räknas inte som vinster.'}

class ManualOdds(BaseModel):
    home:float=Field(gt=1,le=10000)
    draw:float=Field(gt=1,le=10000)
    away:float=Field(gt=1,le=10000)
    @model_validator(mode='after')
    def validate_all(self):
        from .research import normalize_odds
        normalize_odds([self.home,self.draw,self.away]);return self

@router.post('/matches/{match_id}/compare-odds')
def compare_odds(match_id:str,value:ManualOdds):
    with Session.begin() as db:
        m=db.get(Match,match_id)
        if not m:raise HTTPException(404,'Match saknas')
        if m.kickoff<=now():raise HTTPException(409,'Matchen har redan startat')
        p=db.query(Prediction).filter_by(match_id=m.id).order_by(Prediction.id.desc()).first()
        if not p:raise HTTPException(409,'Ingen prognos att jämföra med')
        source=db.get(DataSource,m.source_id)
        if now()-p.generated_at>timedelta(hours=36):raise HTTPException(409,'Prognosen är för gammal; invänta omberäkning.')
        observation=db.query(FixtureObservation).filter_by(match_id=m.id).order_by(FixtureObservation.id.desc()).first()
        if observation and (observation.payload.get('status')=='WITHDRAWN' or p.snapshot.get('fixture_observation_id')!=observation.id):raise HTTPException(409,'Spelschemat har ändrats; invänta en aktuell prognos.')
        if not source.synthetic and provider_status(db).get(m.competition_id,{}).get('state')!='CONNECTED':raise HTTPException(409,'Källan är inte tillräckligt aktuell för jämförelse.')
        source_id='manual-odds-demo' if source.synthetic else 'manual-odds-real'
        if not db.get(DataSource,source_id):db.add(DataSource(id=source_id,name='Manuellt angivna odds · ej leverantörsverifierade',synthetic=source.synthetic));db.flush()
        odds=[value.home,value.draw,value.away];stamp=now()
        quote=OddsSnapshot(match_id=m.id,source_id=source_id,available_at=stamp,fetched_at=stamp,odds=odds);db.add(quote);db.flush()
        return {**odds_comparison(p.probabilities,odds),'odds_snapshot_id':quote.id,'prediction_id':p.id,'model_probabilities':p.probabilities,'odds':odds,'recorded_at':stamp.isoformat()+'Z','verified':False,'source':'Manuell inmatning','warning':'Oddsen är inmatade av dig och inte verifierade mot marknaden. Modellen är inte oberoende kalibrerad. Positivt beräknat modellövertag är inte en vinstgaranti.'}

@router.get('/live-performance')
def live_performance(synthetic:bool=False):
    """Prospective log evaluation: one fixed selection rule, never historical reconstruction."""
    from .research import metrics,label
    with Session() as db:
        records=db.query(Prediction,Match).join(Match,Prediction.match_id==Match.id).join(DataSource,Match.source_id==DataSource.id).filter(DataSource.synthetic==synthetic).order_by(Prediction.id).all()
        selected={}
        for p,m in records:
            if p.generated_at<m.kickoff:selected[m.id]=(p,m)
        settled=[];pending=0;invalid=0
        for p,m in selected.values():
            r=db.get(Result,m.id)
            if not r or r.available_at>now():pending+=1;continue
            settled.append((p,m,label(r.home_goals,r.away_goals)))
        result=metrics([p.probabilities for p,m,y in settled],[y for p,m,y in settled])
        return {**result,'pending':pending,'matches_logged':len(selected),'selection_rule':'Latest recorded prediction strictly before actual scheduled kickoff; one per match','synthetic':synthetic,'protocol':'prospective-log','correct':sum(max(range(3),key=lambda i:p.probabilities[i])==y for p,m,y in settled),'incorrect':sum(max(range(3),key=lambda i:p.probabilities[i])!=y for p,m,y in settled),'roi':None,'note':'Träffsäkerhet för verkliga förhandsprognoser. Ingen ROI beräknas utan en separat, verifierbar odds- och urvalslogg.'}

from fastapi import BackgroundTasks
import uuid

@router.post('/sync',status_code=202)
def request_sync(background_tasks:BackgroundTasks):
    job=uuid.uuid4().hex
    with Session.begin() as db:
        latest=db.query(SourceRun).filter_by(provider=PROVIDER).order_by(SourceRun.id.desc()).first()
        if latest and now()-latest.finished_at<timedelta(minutes=5):raise HTTPException(429,'Källan kontrollerades nyligen. Vänta fem minuter mellan manuella synkar.',headers={'Retry-After':'300'})
        stamp=now()
        db.add(SourceRun(provider=PROVIDER,started_at=stamp,finished_at=stamp,status='queued',revision=None,details={'job_id':job}))
    from .jobs import sync_and_predict
    background_tasks.add_task(sync_and_predict,job)
    return {'job_id':job,'status':'queued'}

@router.get('/sync/{job_id}')
def sync_status(job_id:str):
    if not all(c in '0123456789abcdef' for c in job_id) or len(job_id)!=32:raise HTTPException(404,'Jobbet saknas')
    with Session() as db:
        records=db.query(SourceRun).order_by(SourceRun.id.desc()).limit(100).all()
        match=next((r for r in records if r.details.get('job_id')==job_id),None)
        if not match:raise HTTPException(404,'Jobbet saknas')
        status=match.status
        if status in ('running','queued') and now()-match.started_at>timedelta(minutes=10):status='interrupted'
        return {'job_id':job_id,'status':status,'finished_at':match.finished_at.isoformat()+'Z','details':match.details}

@router.get('/matches/{match_id}/market-odds')
def observed_market_odds(match_id:str):
    with Session() as db:
        match=db.get(Match,match_id)
        if not match:raise HTTPException(404,'Match saknas')
        quote=db.query(OddsSnapshot).filter(OddsSnapshot.match_id==match_id,OddsSnapshot.source_id.like('football-data-%')).order_by(OddsSnapshot.id.desc()).first()
        if match.kickoff<=now():return {'status':'CLOSED','odds':None,'message':'Matchen har startat.'}
        if not quote:return {'status':'UNAVAILABLE','odds':None,'message':'Ingen aktuell källobservation finns. Du kan ange odds själv för en manuell jämförelse.'}
        stale=now()-quote.fetched_at>timedelta(hours=2)
        return {'status':'STALE' if stale else 'OBSERVED','odds':quote.odds,'observed_at':quote.fetched_at.isoformat()+'Z','source':'football-data.co.uk CSV · B365-kolumner','publication_time_known':False,'verified_current_bookmaker_price':False,'message':'Indirekt källobservation; den ursprungliga publiceringstiden är okänd. Kontrollera priset själv. Inga riktiga spel utförs.'}
