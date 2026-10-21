"""Account-free, versioned OpenFootball synchronization. CC0, local source clocks."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import httpx
from pydantic import BaseModel,Field,model_validator,field_validator
from .db import Session,engine
from .models import Match,Result,Team,Competition,DataSource
from .live_models import FixtureObservation,SourceRun
from .ingest import COMPETITIONS
from .providers import LEAGUES

TIMEZONES={'PL':'Europe/London','LL':'Europe/Madrid','BL':'Europe/Berlin','SA':'Europe/Rome','L1':'Europe/Paris'}
PROVIDER='openfootball-current'
def now():return datetime.now(timezone.utc).replace(tzinfo=None)

class Score(BaseModel):
    ft:list[int]|None=None
    @model_validator(mode='after')
    def check(self):
        if self.ft is not None and (len(self.ft)!=2 or any(type(g)!=int or g<0 or g>50 for g in self.ft)):raise ValueError('Invalid result')
        return self
class FixtureData(BaseModel):
    date:str
    time:str|None=None
    round:str=''
    team1:str=Field(min_length=1)
    team2:str=Field(min_length=1)
    score:Score|None=None
    @field_validator('score',mode='before')
    @classmethod
    def normalize_score(cls,value):
        return {'ft':value} if isinstance(value,list) else value
    @model_validator(mode='after')
    def check(self):
        datetime.strptime(self.date,'%Y-%m-%d')
        if self.time:datetime.strptime(self.time,'%H:%M')
        if self.team1==self.team2:raise ValueError('Same team twice')
        return self
class SeasonData(BaseModel):
    name:str
    matches:list[FixtureData]

def revision():
    response=subprocess.run(['git','ls-remote','https://github.com/openfootball/football.json.git','HEAD'],capture_output=True,text=True,timeout=30,check=True)
    sha=response.stdout.split()[0]
    if not re.fullmatch(r'[a-f0-9]{40}',sha):raise ValueError('Invalid provider revision')
    return sha

def season_for(value):
    year=value.year if value.month>=7 else value.year-1
    return f'{year}-{str(year+1)[-2:]}'

def source_payload(sha,season,league,client):
    if not re.fullmatch(r'[a-f0-9]{40}',sha):raise ValueError('Full Git revision required')
    if not re.fullmatch(r'20\d\d-\d\d',season):raise ValueError('Invalid season')
    url=f'https://raw.githubusercontent.com/openfootball/football.json/{sha}/{season}/{LEAGUES[league]}.json'
    folder=Path('artifacts/provider');folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{sha}-{season}-{league}.json';meta=path.with_suffix('.metadata.json')
    if path.exists() and meta.exists():
        raw=path.read_bytes();metadata=json.loads(meta.read_text())
        if hashlib.sha256(raw).hexdigest()!=metadata['sha256']:raise ValueError('Source checksum mismatch')
    else:
        response=client.get(url);response.raise_for_status();raw=response.content
        SeasonData.model_validate_json(raw)
        metadata={'url':url,'revision':sha,'sha256':hashlib.sha256(raw).hexdigest(),'fetched_at':now().isoformat()+'Z','license':'CC0-1.0','timezone_policy':TIMEZONES[league], 'timezone_note':'Source wall-clock interpreted in competition timezone; no independent kickoff verification'}
        path.write_bytes(raw);meta.write_text(json.dumps(metadata,indent=2))
    validated=SeasonData.model_validate_json(raw)
    expected=306 if league in ('BL','L1') else 380
    if len(validated.matches)<expected-20:raise ValueError('Incomplete season feed; existing schedule preserved')
    return validated,metadata

def apply_dataset(data,metadata,season,league,checked_at):
    observed=datetime.fromisoformat(metadata['fetched_at'].replace('Z','+00:00')).replace(tzinfo=None)
    source='openfootball-feed-'+league
    inserted=updated=finished=withdrawn=0
    with Session.begin() as db:
        if not db.get(DataSource,source):db.add(DataSource(id=source,name=f'OpenFootball CC0 · {league}',synthetic=False));db.flush()
        if not db.get(Competition,league):db.add(Competition(id=league,name=COMPETITIONS[league]));db.flush()
        seen=set()
        for item in data.matches:
            key=f'{league}|{season}|{item.round}|{item.team1}|{item.team2}'
            ident='live-'+hashlib.sha256(key.encode()).hexdigest()[:24]
            if ident in seen:raise ValueError('Duplicate provider fixture identity')
            seen.add(ident)
            stamp=datetime.strptime(item.date+' '+(item.time or '00:00'),'%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(TIMEZONES[league]))
            kickoff=stamp.astimezone(timezone.utc).replace(tzinfo=None)
            score=item.score.ft if item.score else None
            # An upstream future score is invalid, not a training observation.
            if score is not None and kickoff>=checked_at:raise ValueError('Provider supplied a result before kickoff')
            payload={**item.model_dump(),'kickoff_utc':kickoff.isoformat()+'Z','kickoff_precision':'source-local-time' if item.time else 'date-only','timezone':TIMEZONES[league],'revision':metadata['revision'],'url':metadata['url'],'sha256':metadata['sha256'],'score':score,'status':'FINAL' if score is not None else 'SCHEDULED'}
            # Dataset revision changes alone do not create a match revision if content is unchanged.
            content={k:v for k,v in payload.items() if k not in ('revision','url','sha256')}
            checksum=hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()
            m=db.get(Match,ident)
            if not m:
                for team in (item.team1,item.team2):
                    if not db.get(Team,team):db.add(Team(id=team,name=team));db.flush()
                m=Match(id=ident,competition_id=league,season=season,home_id=item.team1,away_id=item.team2,kickoff=kickoff,available_at=observed,fetched_at=observed,source_id=source)
                db.add(m);db.flush();inserted+=1
            previous=db.query(FixtureObservation).filter_by(match_id=ident).order_by(FixtureObservation.id.desc()).first()
            if not previous or previous.payload.get('content_sha256')!=checksum or previous.payload.get('status')=='WITHDRAWN':
                # A revised payload can return to a previously observed state; retain the new event.
                event_payload={**payload,'content_sha256':checksum,'observed_at':checked_at.isoformat()+'Z'}
                event_hash=hashlib.sha256(json.dumps(event_payload,sort_keys=True).encode()).hexdigest()
                exists=db.query(FixtureObservation).filter_by(match_id=ident,payload_sha256=event_hash).first()
                if not exists:db.add(FixtureObservation(match_id=ident,observed_at=checked_at,source_id=source,payload_sha256=event_hash,payload=event_payload));updated+=1
                if m.kickoff!=kickoff:m.kickoff=kickoff
            r=db.get(Result,ident)
            if score is not None and not r:
                db.add(Result(match_id=ident,home_goals=score[0],away_goals=score[1],available_at=observed,fetched_at=observed,source_id=source));finished+=1
            elif score is not None and r and [r.home_goals,r.away_goals]!=score:
                raise ValueError('Result correction needs explicit review; old result preserved')
        missing=db.query(Match).filter_by(source_id=source,competition_id=league,season=season).all()
        for m in missing:
            if m.id in seen:continue
            old=db.query(FixtureObservation).filter_by(match_id=m.id).order_by(FixtureObservation.id.desc()).first()
            if not old or old.payload.get('status')=='WITHDRAWN':continue
            payload={**old.payload,'status':'WITHDRAWN','withdrawn_reason':'Not present in latest complete season dataset','revision':metadata['revision'],'observed_at':checked_at.isoformat()+'Z'}
            checksum=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            db.add(FixtureObservation(match_id=m.id,observed_at=checked_at,source_id=source,payload_sha256=checksum,payload=payload));withdrawn+=1
    return {'competition':league,'season':season,'matches':len(data.matches),'inserted':inserted,'observations':updated,'results':finished,'withdrawn':withdrawn}

def synchronize(include_previous=False,only=None,fixed_revision=None,job_id=None):
    start=now();sha=None;details=[];errors=[]
    try:
        sha=fixed_revision or revision()
        current=season_for(start);year=int(current[:4]);seasons=[current]
        if include_previous:seasons=[f'{year-1}-{str(year)[-2:]}',current]
        with httpx.Client(timeout=30,follow_redirects=True) as client:
            for league in ([only] if only else LEAGUES):
                for season in seasons:
                    try:
                        data,meta=source_payload(sha,season,league,client)
                        details.append(apply_dataset(data,meta,season,league,start))
                    except (httpx.HTTPError,ValueError) as exc:
                        errors.append({'competition':league,'season':season,'error':type(exc).__name__})
    except (subprocess.SubprocessError,ValueError,OSError) as exc:errors.append({'error':type(exc).__name__})
    status='ok' if not errors else 'partial' if details else 'error'
    with Session.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=start,finished_at=now(),status=status,revision=sha,details={'job_id':job_id,'datasets':details,'errors':errors,'requested_competitions':[only] if only else list(LEAGUES),'license':'CC0-1.0'}))
    return {'status':status,'revision':sha,'datasets':details,'errors':errors}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',action='store_true');p.add_argument('--league',choices=list(LEAGUES));p.add_argument('--revision');a=p.parse_args()
    result=synchronize(a.bootstrap,a.league,a.revision);print(json.dumps(result,indent=2))
    if result['status']=='error':raise SystemExit(1)
