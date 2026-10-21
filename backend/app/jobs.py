"""One sync at a time per database, with persisted append-only job events."""
import fcntl,hashlib
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from .db import engine,Session
from .live_models import SourceRun
from .sync import synchronize,PROVIDER

@contextmanager
def job_lock():
    # Only a hash is written; the database URL and password never enter logs/files.
    key=hashlib.sha256(str(engine.url).encode()).hexdigest()[:16]
    path=Path('/tmp')/f'fotbolls-ai-sync-{key}.lock'
    with path.open('a') as file:
        try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            yield False;return
        try:yield True
        finally:fcntl.flock(file,fcntl.LOCK_UN)

def sync_and_predict(job_id=None):
    from .pipeline import generate
    with job_lock() as acquired:
        if not acquired:
            if job_id:
                stamp=datetime.now(timezone.utc).replace(tzinfo=None)
                with Session.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=stamp,finished_at=stamp,status='busy',revision=None,details={'job_id':job_id}))
            return {'status':'busy'}
        if job_id:
            stamp=datetime.now(timezone.utc).replace(tzinfo=None)
            with Session.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=stamp,finished_at=stamp,status='running',revision=None,details={'job_id':job_id}))
        try:
            value=synchronize()
            from .football_data import supplement
            market=supplement()
            value['supplement_status']=market['status']
            if market['status']!='ok' and value['status']=='ok':
                value['status']='partial'
                value['errors'].append({'provider':'football-data','error':'SupplementUnavailable'})
            generate(False)
            if job_id:
                stamp=datetime.now(timezone.utc).replace(tzinfo=None)
                with Session.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=stamp,finished_at=stamp,status=value['status'],revision=value.get('revision'),details={'job_id':job_id,'datasets':value.get('datasets',[]),'errors':value.get('errors',[])}))
            try:
                from .backup import save
                value['backup_status']=save()['status']
            except Exception:value['backup_status']='error'
            return value
        except Exception:
            stamp=datetime.now(timezone.utc).replace(tzinfo=None)
            with Session.begin() as db:db.add(SourceRun(provider=PROVIDER,started_at=stamp,finished_at=stamp,status='error',revision=None,details={'job_id':job_id,'errors':[{'error':'ProcessingError'}]}))
            return {'status':'error'}
