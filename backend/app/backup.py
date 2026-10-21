"""Workspace-local PostgreSQL backups for task snapshots; never overwrites a nonempty DB."""
import argparse,hashlib,json,subprocess,uuid
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import inspect,text
from .db import engine,Base
from . import models,live_models
ROOT=Path(__file__).resolve().parents[2]
FOLDER=ROOT/'backend/artifacts/backups'

def managed():
    return engine.dialect.name=='postgresql' and engine.url.host in ('127.0.0.1','localhost') and engine.url.database=='football' and engine.url.port in (None,5432)

def docker(*args,**kwargs):
    return subprocess.run(['docker','compose','exec','-T','db',*args],cwd=ROOT,check=True,**kwargs)

def save():
    if not managed():return {'status':'not-managed','note':'Use an external database backup policy for this connection'}
    FOLDER.mkdir(parents=True,exist_ok=True)
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-'+uuid.uuid4().hex[:8]+'.dump'
    path=FOLDER/name;partial=path.with_suffix('.partial')
    try:
        with partial.open('xb') as out:docker('pg_dump','-U','football','-d','football','--format=custom','--no-owner','--no-privileges',stdout=out,stderr=subprocess.PIPE,timeout=120)
        partial.replace(path)
        value={'file':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'created_at':datetime.now(timezone.utc).isoformat(),'bytes':path.stat().st_size}
        manifest=FOLDER/'latest.json';temp=FOLDER/'latest.partial.json';temp.write_text(json.dumps(value,indent=2));temp.replace(manifest)
        return {'status':'saved',**value}
    finally:
        if partial.exists():partial.unlink()

def restore_if_empty():
    if not managed():return {'status':'not-managed'}
    manifest=FOLDER/'latest.json'
    if not manifest.exists():return {'status':'no-backup'}
    # Inspect all application tables and unknown tables, not only prediction count.
    tables=inspect(engine).get_table_names()
    unknown=set(tables)-set(Base.metadata.tables)-{'alembic_version'}
    if unknown:return {'status':'preserved','reason':'Unknown database tables exist'}
    with engine.connect() as db:
        for name in set(tables)&set(Base.metadata.tables):
            if db.execute(text(f'SELECT 1 FROM "{name}" LIMIT 1')).first():return {'status':'preserved','reason':'Existing application data'}
    metadata=json.loads(manifest.read_text());name=metadata['file']
    if Path(name).name!=name or not name.endswith('.dump'):raise ValueError('Invalid backup filename')
    path=FOLDER/name
    if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:raise ValueError('Backup checksum mismatch; existing database untouched')
    with path.open('rb') as data:docker('pg_restore','-U','football','-d','football','--clean','--if-exists','--single-transaction','--no-owner','--no-privileges',stdin=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    return {'status':'restored','file':name}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--restore-if-empty',action='store_true');a=parser.parse_args()
    print(json.dumps(restore_if_empty() if a.restore_if_empty else save()))
