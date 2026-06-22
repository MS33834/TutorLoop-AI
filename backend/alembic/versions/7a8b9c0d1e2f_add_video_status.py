"""add video status

Revision ID: 7a8b9c0d1e2f
Revises: 05563921952a
Create Date: 2026-06-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a8b9c0d1e2f'
down_revision: Union[str, Sequence[str], None] = '05563921952a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'videos',
        sa.Column('status', sa.String(length=32), nullable=True),
    )
    op.execute("UPDATE videos SET status = 'completed' WHERE status IS NULL")
    op.alter_column('videos', 'status', nullable=False)


def downgrade() -> None:
    op.drop_column('videos', 'status')
