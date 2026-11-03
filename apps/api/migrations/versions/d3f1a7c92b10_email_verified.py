"""email verified

Revision ID: d3f1a7c92b10
Revises: 8aba673dd7ec
Create Date: 2026-11-03 09:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd3f1a7c92b10'
down_revision = '8aba673dd7ec'
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts never verified their address, so they start unverified and can verify from the app.
    with op.batch_alter_table('user_account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('user_account', schema=None) as batch_op:
        batch_op.drop_column('email_verified')
