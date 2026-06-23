"""add knowledge_edges table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-23 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_edges (
            id VARCHAR(36) PRIMARY KEY,
            course_id VARCHAR(36) NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            source_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
            target_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
            relation VARCHAR(64) NOT NULL DEFAULT 'prerequisite',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_knowledge_edge UNIQUE (course_id, source_id, target_id, relation)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_edges_course_id ON knowledge_edges (course_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_edges_source_id ON knowledge_edges (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_edges_target_id ON knowledge_edges (target_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_edges CASCADE")
