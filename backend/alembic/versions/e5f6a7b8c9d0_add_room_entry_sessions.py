"""add room_entry_sessions table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-23 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The IF NOT EXISTS guard makes this safe for databases where SQLAlchemy
    # metadata create_all has already created the table.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS room_entry_sessions (
            id VARCHAR(36) PRIMARY KEY,
            room_id VARCHAR(36) NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            session_id VARCHAR(64) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_room_entry_session UNIQUE (room_id, session_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_room_entry_sessions_room_id ON room_entry_sessions (room_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_room_entry_sessions_session_id ON room_entry_sessions (session_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS room_entry_sessions CASCADE")
