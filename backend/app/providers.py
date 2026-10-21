"""Public CC0 historical results. No odds or point-in-time publication claims."""
import argparse
import csv
import hashlib
import json
import time
from datetime import datetime,timezone
from pathlib import Path
import httpx
from pydantic import BaseModel,Field
from .ingest import import_csv

REVISION='e6744429ee395bc86f247348c6184bb08d4eb361'
LEAGUES={'PL':'en.1','LL':'es.1','BL':'de.1','SA':'it.1','L1':'fr.1'}
class Score(BaseModel):
    ft:list[int]|None=None
class PublicMatch(BaseModel):
    date:str
    team1:str=Field(min_length=1)
    team2:str=Field(min_length=1)
    score:Score|None=None
class PublicSeason(BaseModel):
    name:str
    matches:list[PublicMatch]

def fetch(league='PL',season='2023-24'):
    if league not in LEAGUES:raise ValueError('No verified adapter for this competition')
    url=f'https://raw.githubusercontent.com/openfootball/football.json/{REVISION}/{season}/{LEAGUES[league]}.json'
    folder=Path('artifacts/sources');folder.mkdir(parents=True,exist_ok=True)
    file=folder/f'openfootball-{REVISION}-{season}-{league}.json'
    metadata=file.with_suffix('.metadata.json')
    if file.exists() and metadata.exists():
        raw=file.read_bytes(); meta=json.loads(metadata.read_text())
        if hashlib.sha256(raw).hexdigest()!=meta['sha256']: raise ValueError('Cached data checksum mismatch')
    else:
        with httpx.Client(timeout=30,follow_redirects=True) as client:
            for attempt in range(4):
                response=client.get(url)
                if response.status_code not in (429,502,503,504):break
                time.sleep(min(2**attempt,8))
            response.raise_for_status(); raw=response.content
        PublicSeason.model_validate_json(raw)
        meta={'url':url,'revision':REVISION,'sha256':hashlib.sha256(raw).hexdigest(),'fetched_at':datetime.now(timezone.utc).isoformat(),'license':'CC0-1.0','license_url':f'https://github.com/openfootball/football.json/blob/{REVISION}/LICENSE.md','availability':'First locally verified at fetched_at; historical publication times unknown','kickoff_precision':'date only: represented at 00:00 UTC, not a verified kickoff time'}
        file.write_bytes(raw);metadata.write_text(json.dumps(meta,indent=2))
    dataset=PublicSeason.model_validate_json(raw)
    rows=[]
    for item in dataset.matches:
        if not item.score or item.score.ft is None:continue
        if len(item.score.ft)!=2 or any(g<0 or g>50 for g in item.score.ft):raise ValueError('Invalid score')
        date=datetime.strptime(item.date,'%Y-%m-%d').replace(tzinfo=timezone.utc)
        ident='of-'+hashlib.sha256(f'{league}|{season}|{item.date}|{item.team1}|{item.team2}'.encode()).hexdigest()[:24]
        rows.append(dict(id=ident,competition_id=league,season=season,home_id=item.team1,away_id=item.team2,kickoff=date.isoformat(),available_at=meta['fetched_at'],result_available_at=meta['fetched_at'],home_goals=item.score.ft[0],away_goals=item.score.ft[1]))
    csvpath=file.with_suffix('.csv')
    with csvpath.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    from .db import Session
    from .models import DataSource
    source=f'openfootball-{league}-{season}-{REVISION[:8]}'
    with Session() as db:
        if db.get(DataSource,source):return {'source':source,'status':'already_imported','n':len(rows)}
    return {'source':source,'status':'imported','n':import_csv(csvpath,source),'metadata':meta}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--league',choices=LEAGUES,default='PL');parser.add_argument('--season',default='2023-24');args=parser.parse_args()
    print(json.dumps(fetch(args.league,args.season),indent=2))
