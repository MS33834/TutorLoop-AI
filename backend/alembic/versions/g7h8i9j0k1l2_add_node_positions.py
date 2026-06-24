"""add node positions

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-24 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS position_x DOUBLE PRECISION")
    op.execute("ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS position_y DOUBLE PRECISION")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_nodes DROP COLUMN IF EXISTS position_x")
    op.execute("ALTER TABLE knowledge_nodes DROP COLUMN IF EXISTS position_y")
