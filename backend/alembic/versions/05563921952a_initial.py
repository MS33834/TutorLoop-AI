"""initial (squashed)

Revision ID: 05563921952a
Revises:
Create Date: 2026-06-22 08:15:59.974306

Squashed on 2026-07-02: the 10 incremental migrations that followed this
one (add_video_status, add_user_is_active, add_rooms_table, ...) were all
redundant because this migration uses Base.metadata.create_all(), which
creates the *current* full schema in one shot. The incremental migrations
then tried to ADD COLUMN / CREATE TABLE for objects that already existed,
failing with "column already exists" / "relation already exists".

Since the project has not shipped to production (no data to preserve), the
clean fix is to keep this single create_all migration as the only revision.
This also resolves the immediate CI migrations-job failure.

Tech debt TD-03 (rewrite as explicit op.create_table DDL) remains open and
is tracked for Phase 5.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '05563921952a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and vector indexes."""
    from app.models.db import Base

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Use the current connection to run metadata.create_all synchronously.
    # op.run_sync does not exist in alembic <= 1.18; use the bind directly.
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    # Approximate nearest-neighbor indexes for pgvector
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_embedding
        ON knowledge_nodes
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_frames_embedding
        ON video_frames
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    """Drop all tables."""
    from app.models.db import Base

    op.execute("DROP INDEX IF EXISTS idx_video_frames_embedding")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_nodes_embedding")

    bind = op.get_bind()
    Base.metadata.drop_all(bind)
