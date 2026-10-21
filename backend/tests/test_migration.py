import os,subprocess
from pathlib import Path
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.exc import IntegrityError,DBAPIError

def test_migration_database_trigger_blocks_direct_sql(tmp_path):
    url='sqlite:///'+str(tmp_path/'migration.db')
    subprocess.run([str(Path('../.venv/bin/alembic').resolve()),'upgrade','head'],env={**os.environ,'DATABASE_URL':url},check=True)
    engine=create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO model_versions (id,created_at,config) VALUES ('test','2024-01-01','{}')"))
    with pytest.raises(DBAPIError):
        with engine.begin() as db:db.execute(text("UPDATE model_versions SET config='{}' WHERE id='test'"))
    with pytest.raises(DBAPIError):
        with engine.begin() as db:db.execute(text("DELETE FROM model_versions WHERE id='test'"))
    with engine.connect() as db:assert db.execute(text("SELECT count(*) FROM model_versions")).scalar()==1
