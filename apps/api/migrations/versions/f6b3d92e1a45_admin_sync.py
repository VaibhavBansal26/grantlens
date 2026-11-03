"""admin sync

Revision ID: f6b3d92e1a45
Revises: e5a2c81f7d34
Create Date: 2026-11-03 13:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f6b3d92e1a45'
down_revision = 'e5a2c81f7d34'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_account', sa.Column('is_admin', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table('sync_schedule',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('interval_hours', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sync_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('trigger', sa.String(length=10), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('schedule_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('fetched', sa.Integer(), server_default='0', nullable=False),
    sa.Column('inserted', sa.Integer(), server_default='0', nullable=False),
    sa.Column('updated', sa.Integer(), server_default='0', nullable=False),
    sa.Column('unchanged', sa.Integer(), server_default='0', nullable=False),
    sa.Column('embedded', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['schedule_id'], ['sync_schedule.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['user_account.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sync_run_status'), 'sync_run', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_sync_run_status'), table_name='sync_run')
    op.drop_table('sync_run')
    op.drop_table('sync_schedule')
    op.drop_column('user_account', 'is_admin')
