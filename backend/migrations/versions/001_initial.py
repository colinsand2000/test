"""Initial schema."""
from alembic import op
from app.db import Base
from app import models
revision = "001"
down_revision = None

def upgrade():
    original=("competitions","teams","data_sources","matches","results","team_match_stats","players","injuries","lineups","odds_snapshots","model_versions","model_predictions","paper_bets")
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in original])
    # Enforce immutable research records even for direct SQL writes.
    bind = op.get_bind()
    tables = ("model_predictions", "model_versions", "paper_bets", "results", "odds_snapshots")
    if bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_research_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Append-only research record'; END $$")
        for table in tables:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_research_mutation()")
    elif bind.dialect.name == "sqlite":
        for table in tables:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only research record'); END")

def downgrade():
    raise RuntimeError("Destructive downgrade disabled for research records; archive the database first")
