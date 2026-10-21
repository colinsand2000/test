import os
from alembic import context
from sqlalchemy import create_engine
from app.db import Base
from app import models
config = context.config
engine = create_engine(os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url")))
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
