"""jobs

Revision ID: e5a2c81f7d34
Revises: d3f1a7c92b10
Create Date: 2026-11-03 11:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e5a2c81f7d34'
down_revision = 'd3f1a7c92b10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('job',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('result_id', sa.Integer(), nullable=True),
    sa.Column('error', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user_account.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_job_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_job_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_user_id'))
        batch_op.drop_index(batch_op.f('ix_job_status'))
    op.drop_table('job')
