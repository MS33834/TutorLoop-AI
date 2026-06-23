"""add room stats and config columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-23 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Using ADD COLUMN IF NOT EXISTS makes the migration safe for databases
    # that already have these columns (e.g. created by SQLAlchemy metadata
    # create_all during local development).
    op.execute(
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS entry_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS welcome_message TEXT"
    )
    op.execute(
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS max_participants INTEGER"
    )
    op.execute(
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS config_json JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS config_json")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS max_participants")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS welcome_message")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS last_activity_at")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS entry_count")
