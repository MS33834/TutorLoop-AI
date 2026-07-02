"""initial

Revision ID: 05563921952a
Revises:
Create Date: 2026-06-22 08:15:59.974306

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
