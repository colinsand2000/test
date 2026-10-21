"""V1 provider logs, fixture revisions and informational tips."""
from alembic import op
import sqlalchemy as sa
revision='003'
down_revision='002'
def upgrade():
    op.create_table('source_runs',sa.Column('id',sa.Integer,primary_key=True),sa.Column('provider',sa.String,nullable=False),sa.Column('started_at',sa.DateTime,nullable=False),sa.Column('finished_at',sa.DateTime,nullable=False),sa.Column('status',sa.String,nullable=False),sa.Column('revision',sa.String,nullable=True),sa.Column('details',sa.JSON,nullable=False))
    op.create_table('fixture_observations',sa.Column('id',sa.Integer,primary_key=True),sa.Column('match_id',sa.String,sa.ForeignKey('matches.id'),nullable=False),sa.Column('observed_at',sa.DateTime,nullable=False),sa.Column('source_id',sa.String,sa.ForeignKey('data_sources.id'),nullable=False),sa.Column('payload_sha256',sa.String,nullable=False),sa.Column('payload',sa.JSON,nullable=False),sa.UniqueConstraint('match_id','payload_sha256'))
    op.create_table('analysis_tips',sa.Column('id',sa.Integer,primary_key=True),sa.Column('prediction_id',sa.Integer,sa.ForeignKey('model_predictions.id'),nullable=False),sa.Column('created_at',sa.DateTime,nullable=False),sa.Column('policy_version',sa.String,nullable=False),sa.Column('decision',sa.String,nullable=False),sa.Column('snapshot',sa.JSON,nullable=False),sa.UniqueConstraint('prediction_id','policy_version'))
    op.create_index('ix_tip_prediction','analysis_tips',['prediction_id'])
    op.create_index('ix_source_provider_time','source_runs',['provider','finished_at'])
    op.create_index('ix_fixture_match_time','fixture_observations',['match_id','id'])
    dialect=op.get_bind().dialect.name
    for table in ['source_runs','fixture_observations','analysis_tips']:
        if dialect=='postgresql':op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_research_mutation()')
        elif dialect=='sqlite':
            for action in ['UPDATE','DELETE']:op.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only research record'); END")
def downgrade():raise RuntimeError('Archive research records before destructive changes')
