"""add interaction foreign keys and knowledge node unique constraint

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-06-24 09:00:00.000000

Adds:
- Foreign-key constraints (ON DELETE SET NULL) to interactions.user_id,
  room_id, course_id, video_id, node_id so deletions no longer leave
  dangling rows that silently skew class reports.
- A unique constraint on (course_id, name) for knowledge_nodes so re-running
  build-graph cannot create duplicate nodes.

Existing dangling rows are nullified before the constraints are added so the
migration succeeds even if the data currently contains broken references.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullify any existing dangling references before adding FK constraints,
    # otherwise ALTER TABLE ... ADD CONSTRAINT would fail on inconsistent data.
    op.execute(
        "UPDATE interactions SET user_id = NULL "
        "WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users)"
    )
    op.execute(
        "UPDATE interactions SET room_id = NULL "
        "WHERE room_id IS NOT NULL AND room_id NOT IN (SELECT id FROM rooms)"
    )
    op.execute(
        "UPDATE interactions SET course_id = NULL "
        "WHERE course_id IS NOT NULL AND course_id NOT IN (SELECT id FROM courses)"
    )
    op.execute(
        "UPDATE interactions SET video_id = NULL "
        "WHERE video_id IS NOT NULL AND video_id NOT IN (SELECT id FROM videos)"
    )
    op.execute(
        "UPDATE interactions SET node_id = NULL "
        "WHERE node_id IS NOT NULL AND node_id NOT IN (SELECT id FROM knowledge_nodes)"
    )

    op.create_foreign_key(
        "fk_interactions_user_id_users",
        "interactions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_interactions_room_id_rooms",
        "interactions",
        "rooms",
        ["room_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_interactions_course_id_courses",
        "interactions",
        "courses",
        ["course_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_interactions_video_id_videos",
        "interactions",
        "videos",
        ["video_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_interactions_node_id_knowledge_nodes",
        "interactions",
        "knowledge_nodes",
        ["node_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Deduplicate knowledge_nodes by (course_id, name) before adding the unique
    # constraint: keep the oldest row per pair and remote the rest. Edges and
    # mastery referencing removed nodes are repointed to the kept node first.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, course_id, name,
                   ROW_NUMBER() OVER (PARTITION BY course_id, name ORDER BY created_at) AS rn
            FROM knowledge_nodes
        ),
        dupes AS (
            SELECT r.id AS dup_id, k.id AS keep_id
            FROM ranked r
            JOIN knowledge_nodes k
              ON k.course_id = r.course_id AND k.name = r.name
            WHERE r.rn > 1 AND k.id <> r.id
        )
        UPDATE knowledge_edges
        SET source_id = d.keep_id
        FROM dupes d
        WHERE knowledge_edges.source_id = d.dup_id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, course_id, name,
                   ROW_NUMBER() OVER (PARTITION BY course_id, name ORDER BY created_at) AS rn
            FROM knowledge_nodes
        ),
        dupes AS (
            SELECT r.id AS dup_id, k.id AS keep_id
            FROM ranked r
            JOIN knowledge_nodes k
              ON k.course_id = r.course_id AND k.name = r.name
            WHERE r.rn > 1 AND k.id <> r.id
        )
        UPDATE knowledge_edges
        SET target_id = d.keep_id
        FROM dupes d
        WHERE knowledge_edges.target_id = d.dup_id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, course_id, name,
                   ROW_NUMBER() OVER (PARTITION BY course_id, name ORDER BY created_at) AS rn
            FROM knowledge_nodes
        ),
        dupes AS (
            SELECT r.id AS dup_id, k.id AS keep_id
            FROM ranked r
            JOIN knowledge_nodes k
              ON k.course_id = r.course_id AND k.name = r.name
            WHERE r.rn > 1 AND k.id <> r.id
        )
        UPDATE mastery
        SET node_id = d.keep_id
        FROM dupes d
        WHERE mastery.node_id = d.dup_id
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_nodes
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY course_id, name ORDER BY created_at) AS rn
                FROM knowledge_nodes
            ) t
            WHERE t.rn > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_knowledge_node_course_name",
        "knowledge_nodes",
        ["course_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_knowledge_node_course_name", "knowledge_nodes", type_="unique")
    op.drop_constraint("fk_interactions_node_id_knowledge_nodes", "interactions", type_="foreignkey")
    op.drop_constraint("fk_interactions_video_id_videos", "interactions", type_="foreignkey")
    op.drop_constraint("fk_interactions_course_id_courses", "interactions", type_="foreignkey")
    op.drop_constraint("fk_interactions_room_id_rooms", "interactions", type_="foreignkey")
    op.drop_constraint("fk_interactions_user_id_users", "interactions", type_="foreignkey")
