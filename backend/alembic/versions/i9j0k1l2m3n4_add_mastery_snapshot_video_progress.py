"""add mastery snapshot, video progress, and mastery bkt params

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-07-02 10:00:00.000000

Adds:
- ``mastery_snapshots`` table: append-only mastery history for time-series
  mastery curves.
- ``video_progress`` table: per-user video watch position and cumulative
  watched seconds.
- ``p_g``, ``p_s``, ``p_l0`` columns to the ``mastery`` table so each node
  can carry its own BKT guess/slip/initial-known probabilities instead of
  relying on the global settings defaults.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, Sequence[str], None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mastery_snapshots',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'user_id',
            sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'node_id',
            sa.String(length=36),
            sa.ForeignKey('knowledge_nodes.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'course_id',
            sa.String(length=36),
            sa.ForeignKey('courses.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('p_known', sa.Float(), nullable=False),
        sa.Column('p_t', sa.Float(), nullable=False, server_default='0.1'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_mastery_snapshots_user_node',
        'mastery_snapshots',
        ['user_id', 'node_id', 'created_at'],
    )

    op.create_table(
        'video_progress',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'user_id',
            sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'video_id',
            sa.String(length=36),
            sa.ForeignKey('videos.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'position_seconds', sa.Float(), nullable=False, server_default='0.0'
        ),
        sa.Column(
            'watched_seconds', sa.Float(), nullable=False, server_default='0.0'
        ),
        sa.Column(
            'last_watched_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            'user_id', 'video_id', name='uq_video_progress_user_video'
        ),
    )

    # Add per-node BKT parameters to mastery. IF NOT EXISTS keeps the migration
    # idempotent if a partial run already created some of the columns.
    op.execute(
        "ALTER TABLE mastery ADD COLUMN IF NOT EXISTS p_g FLOAT NOT NULL DEFAULT 0.2"
    )
    op.execute(
        "ALTER TABLE mastery ADD COLUMN IF NOT EXISTS p_s FLOAT NOT NULL DEFAULT 0.1"
    )
    op.execute(
        "ALTER TABLE mastery ADD COLUMN IF NOT EXISTS p_l0 FLOAT NOT NULL DEFAULT 0.1"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE mastery DROP COLUMN IF EXISTS p_l0")
    op.execute("ALTER TABLE mastery DROP COLUMN IF EXISTS p_s")
    op.execute("ALTER TABLE mastery DROP COLUMN IF EXISTS p_g")

    op.drop_table('video_progress')

    op.drop_index('ix_mastery_snapshots_user_node', table_name='mastery_snapshots')
    op.drop_table('mastery_snapshots')
