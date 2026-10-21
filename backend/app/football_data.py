"""Optional official CSV supplement: results, match stats and observed market odds.

No credentials/payment details required. Needs cloud egress to the official host.
Historical quote publication times are unknown: availability is recorded on fetch.
Unmatched or ambiguous teams are rejected, never fuzzily merged.
"""
import csv,hashlib,io,json,math,re,unicodedata
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import httpx
from .db import Session
from .models import Match,Result,DataSource,OddsSnapshot,TeamMatchStat
from .live_models import SourceRun,FixtureObservation
from .research import normalize_odds
from .sync import TIMEZONES,season_for

PROVIDER='football-data-official-csv'
CODES={'PL':'E0','LL':'SP1','BL':'D1','SA':'I1','L1':'F1'}
ALIASES={
 'Man City':'Manchester City','Man United':'Manchester United','Newcastle':'Newcastle United','Tottenham':'Tottenham Hotspur',"Nott'm Forest":'Nottingham Forest','West Ham':'West Ham United','Wolves':'Wolverhampton Wanderers','Leeds':'Leeds United','Hull':'Hull City','Coventry':'Coventry City','Brighton':'Brighton Hove Albion','Bournemouth':'Bournemouth','Sunderland':'Sunderland','Ipswich':'Ipswich Town','Leicester':'Leicester City','Luton':'Luton Town',
 'Bayern Munich':'Bayern Munchen','Dortmund':'Borussia Dortmund','Leverkusen':'Bayer 04 Leverkusen',"M'gladbach":'Borussia Monchengladbach','Ein Frankfurt':'Eintracht Frankfurt','Hoffenheim':'1899 Hoffenheim','Werder Bremen':'Werder Bremen','Mainz':'1 Mainz 05','Union Berlin':'1 Union Berlin','FC Koln':'1 Koln','Hamburg':'Hamburger','Heidenheim':'1 Heidenheim 1846','St Pauli':'St Pauli','Stuttgart':'Stuttgart','Bochum':'Bochum 1848',
 'Ath Madrid':'Atletico Madrid','Ath Bilbao':'Athletic Bilbao','Sociedad':'Real Sociedad','Betis':'Real Betis','Celta':'Celta Vigo','Alaves':'Deportivo Alaves','Espanol':'Espanyol','La Coruna':'Deportivo La Coruna',
 'Inter':'Internazionale Milano','Verona':'Hellas Verona','Parma':'Parma','Bologna':'Bologna','Atalanta':'Atalanta','Fiorentina':'Fiorentina','Genoa':'Genoa','Sassuolo':'Sassuolo','Lecce':'Lecce',
 'Paris SG':'Paris Saint Germain','Marseille':'Olympique Marseille','Lyon':'Olympique Lyonnais','St Etienne':'Saint Etienne','Reims':'Stade Reims','Brest':'Stade Brestois 29','Rennes':'Stade Rennais','Strasbourg':'Strasbourg Alsace','Auxerre':'Auxerre','Nice':'Nice','Lille':'Lille','Angers':'Angers'
}
ALIASES.update({'Ath Bilbao':'Athletic Club','Espanol':'RCD Espanyol de Barcelona','Vallecano':'Rayo Vallecano de Madrid','Santander':'Real Racing Club de Santander','Osasuna':'CA Osasuna','Betis':'Real Betis Balompie','Sociedad':'Real Sociedad de Futbol','Mainz':'1 FSV Mainz 05','Paderborn':'SC Paderborn 07','Elversberg':'SV 07 Elversberg','Como':'Como 1907','Rennes':'Stade Rennais FC 1901','Lens':'Racing Club de Lens','Troyes':'ES Troyes AC'})
def now():return datetime.now(timezone.utc).replace(tzinfo=None)
def canonical(name):
    name=ALIASES.get(name,name)
    text=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower().replace('&',' ')
    words=re.sub(r'[^a-z0-9]+',' ',text).split()
    ignore={'fc','cf','afc','ac','ssc','rc','rsc','sv','tsg','vfl','vfb','sc','as','ss','club','calcio','de','rcd','ud','cfc','acf','aj','ogc','osc','sco','bc','us','1909','1913'}
    return ''.join(w for w in words if w not in ignore)

def parse_date(row,league):
    date=None
    for form in ('%d/%m/%Y','%d/%m/%y','%Y-%m-%d'):
        try:date=datetime.strptime(row['Date'],form);break
        except ValueError:pass
    if date is None:raise ValueError('Unknown CSV date')
    clock=row.get('Time','').strip()
    if clock:
        time=datetime.strptime(clock,'%H:%M');date=date.replace(hour=time.hour,minute=time.minute)
    return date.replace(tzinfo=ZoneInfo(TIMEZONES[league])).astimezone(timezone.utc).replace(tzinfo=None)

def download(client,url,stamp):
    response=client.get(url);response.raise_for_status();raw=response.content
    text=raw.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(text))
    if not {'Date','HomeTeam','AwayTeam'}.issubset(set(reader.fieldnames or [])):raise ValueError('Unexpected CSV schema')
    rows=list(reader)
    folder=Path('artifacts/football-data');folder.mkdir(parents=True,exist_ok=True)
    sha=hashlib.sha256(raw).hexdigest();path=folder/f'{sha}.csv'
    if not path.exists():path.write_bytes(raw)
    meta={'url':url,'sha256':sha,'fetched_at':stamp.isoformat()+'Z','historical_publication_time':'unknown','usage':'Personal research; source terms apply','provider':'football-data.co.uk'}
    metadata=folder/f'{stamp.strftime("%Y%m%dT%H%M%S%f")}-{sha[:8]}.metadata.json';metadata.write_text(json.dumps(meta,indent=2))
    return rows,meta

def match_identity(db,row,league,season):
    home,away=canonical(row['HomeTeam']),canonical(row['AwayTeam'])
    choices=[m for m in db.query(Match).filter_by(competition_id=league,season=season).all() if canonical(m.home_id)==home and canonical(m.away_id)==away]
    if len(choices)!=1:raise ValueError('No unambiguous canonical fixture identity')
    return choices[0]

def apply_rows(rows,meta,league,season):
    stamp=datetime.fromisoformat(meta['fetched_at'].replace('Z','+00:00')).replace(tzinfo=None)
    source='football-data-'+league;added=stats=quotes=0;unmatched=[]
    with Session.begin() as db:
        if not db.get(DataSource,source):db.add(DataSource(id=source,name=f'football-data.co.uk · {league} · observed CSV',synthetic=False));db.flush()
        # Validate all observations before writing; one bad score rolls back the batch.
        for row in rows:
            if not row.get('HomeTeam') or not row.get('AwayTeam'):continue
            try:m=match_identity(db,row,league,season)
            except ValueError:unmatched.append({'home':row['HomeTeam'],'away':row['AwayTeam']});continue
            kickoff=parse_date(row,league)
            hg,ag=row.get('FTHG','').strip(),row.get('FTAG','').strip()
            if bool(hg)!=bool(ag):raise ValueError('Partial score')
            if hg and ag:
                if not hg.isdigit() or not ag.isdigit() or max(int(hg),int(ag))>50:raise ValueError('Invalid score')
                if kickoff>=stamp:raise ValueError('Result before kickoff')
                expected='H' if int(hg)>int(ag) else 'D' if int(hg)==int(ag) else 'A'
                if row.get('FTR') and row['FTR']!=expected:raise ValueError('Outcome and score disagree')
                old=db.get(Result,m.id)
                if old and (old.home_goals!=int(hg) or old.away_goals!=int(ag)):raise ValueError('Conflicting result; manual review required')
                if not old:
                    db.add(Result(match_id=m.id,home_goals=int(hg),away_goals=int(ag),source_id=source,available_at=stamp,fetched_at=stamp));added+=1
                if row.get('Time') and m.kickoff!=kickoff:
                    payload={'kickoff_utc':kickoff.isoformat()+'Z','kickoff_precision':'source-local-time','timezone':TIMEZONES[league],'status':'FINAL','url':meta['url'],'sha256':meta['sha256'],'observed_at':stamp.isoformat()+'Z','note':'Supplementary final-result time'}
                    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                    db.add(FixtureObservation(match_id=m.id,observed_at=stamp,source_id=source,payload_sha256=digest,payload=payload));m.kickoff=kickoff
                if not db.query(TeamMatchStat).filter_by(match_id=m.id,source_id=source).first():
                    for team,keys in [(m.home_id,{'shots':'HS','shots_on_target':'HST','corners':'HC','yellow_cards':'HY','red_cards':'HR'}),(m.away_id,{'shots':'AS','shots_on_target':'AST','corners':'AC','yellow_cards':'AY','red_cards':'AR'})]:
                        values={}
                        for name,key in keys.items():
                            if row.get(key,'').strip():
                                value=float(row[key])
                                if not math.isfinite(value) or value<0:raise ValueError('Invalid team statistic')
                                values[name]=value
                        if values:db.add(TeamMatchStat(match_id=m.id,team_id=team,source_id=source,available_at=stamp,fetched_at=stamp,values=values));stats+=1
            if m.kickoff>stamp and kickoff>stamp:
                odds=[row.get(k,'').strip() for k in ('B365H','B365D','B365A')]
                if all(odds):
                    values=[float(x) for x in odds];normalize_odds(values)
                    db.add(OddsSnapshot(match_id=m.id,source_id=source,available_at=stamp,fetched_at=stamp,odds=values));quotes+=1
    return {'competition':league,'results_added':added,'stats_added':stats,'quotes_observed':quotes,'unmatched':unmatched,'rows':len(rows)}

def supplement():
    stamp=now();details=[];errors=[];season=season_for(stamp);code=season[2:4]+season[-2:]
    with httpx.Client(timeout=20,follow_redirects=True) as client:
        for league,div in CODES.items():
            try:
                rows,meta=download(client,f'https://www.football-data.co.uk/mmz4281/{code}/{div}.csv',stamp)
                details.append(apply_rows(rows,meta,league,season))
            except (httpx.HTTPError,ValueError) as exc:errors.append({'competition':league,'error':type(exc).__name__})
        try:
            rows,meta=download(client,'https://www.football-data.co.uk/fixtures.csv',stamp)
            for league,div in CODES.items():
                relevant=[r for r in rows if r.get('Div')==div]
                if relevant:details.append(apply_rows(relevant,meta,league,season))
        except (httpx.HTTPError,ValueError) as exc:errors.append({'scope':'upcoming-odds','error':type(exc).__name__})
    state='ok' if not errors and not any(d['unmatched'] for d in details) else 'partial' if details else 'error'
    with Session.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=stamp,finished_at=now(),status=state,revision=None,details={'datasets':details,'errors':errors,'network_host':'www.football-data.co.uk'}))
    return {'status':state,'datasets':details,'errors':errors}

if __name__=='__main__':
    result=supplement();print(json.dumps(result,indent=2))
    if result['status']=='error':raise SystemExit(1)
