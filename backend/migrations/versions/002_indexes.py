"""Indexes for chronological queries and forecast revisions."""
from alembic import op
revision='002'
down_revision='001'
def upgrade():
    op.create_index('ix_matches_kickoff','matches',['kickoff'])
    op.create_index('ix_predictions_match_id','model_predictions',['match_id','id'])
    op.create_index('ix_results_available_at','results',['available_at'])
    op.create_index('ix_odds_match_available','odds_snapshots',['match_id','available_at'])
def downgrade():
    for name,table in [('ix_matches_kickoff','matches'),('ix_predictions_match_id','model_predictions'),('ix_results_available_at','results'),('ix_odds_match_available','odds_snapshots')]:op.drop_index(name,table_name=table)
