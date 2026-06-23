"""add interaction indexes

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-23 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Indexes speed up class-report and analytics queries. IF NOT EXISTS makes
    # the migration safe for databases that already have them.
    op.create_index(
        "ix_interactions_course_id", "interactions", ["course_id"], if_not_exists=True
    )
    op.create_index(
        "ix_interactions_user_id", "interactions", ["user_id"], if_not_exists=True
    )
    op.create_index(
        "ix_interactions_created_at", "interactions", ["created_at"], if_not_exists=True
    )
    op.create_index(
        "ix_interactions_course_created",
        "interactions",
        ["course_id", "created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_interactions_course_created", table_name="interactions", if_exists=True)
    op.drop_index("ix_interactions_created_at", table_name="interactions", if_exists=True)
    op.drop_index("ix_interactions_user_id", table_name="interactions", if_exists=True)
    op.drop_index("ix_interactions_course_id", table_name="interactions", if_exists=True)
