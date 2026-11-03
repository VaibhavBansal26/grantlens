"""close date index

Revision ID: 8aba673dd7ec
Revises: b08a30094e5d
Create Date: 2026-11-02 21:09:04.427150

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '8aba673dd7ec'
down_revision = 'b08a30094e5d'
branch_labels = None
depends_on = None


def upgrade():
    # CONCURRENTLY: build the index without blocking writes to a table that other jobs are inserting into.
    # It cannot run inside a transaction, hence the autocommit block.
    with op.get_context().autocommit_block():
        op.create_index("ix_opportunity_close_date", "opportunity", ["close_date"], postgresql_concurrently=True,
                        if_not_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("ix_opportunity_close_date", table_name="opportunity", postgresql_concurrently=True,
                      if_exists=True)
