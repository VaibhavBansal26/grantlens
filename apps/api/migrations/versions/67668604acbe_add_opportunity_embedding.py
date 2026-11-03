"""add opportunity embedding

Revision ID: 67668604acbe
Revises: c15920d6e0e5
Create Date: 2026-11-02 15:27:58.255852

"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "67668604acbe"
down_revision = "c15920d6e0e5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "opportunity",
        sa.Column("embedding", Vector(384).with_variant(sa.JSON(), "sqlite"), nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_opportunity_embedding ON opportunity "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_opportunity_embedding")
    op.drop_column("opportunity", "embedding")
