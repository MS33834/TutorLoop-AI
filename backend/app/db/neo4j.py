"""Neo4j graph database access."""

import asyncio
import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None
_driver_lock = asyncio.Lock()


async def get_driver() -> AsyncDriver:
    """Return a singleton Neo4j async driver."""
    global _driver
    if _driver is None:
        # Guard creation with a lock so concurrent first callers do not each
        # spin up a separate driver / connection pool.
        async with _driver_lock:
            if _driver is None:  # double-checked locking
                _driver = AsyncGraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                    # Explicit pool/timeout tuning so production traffic does not
                    # exhaust the default pool or hang indefinitely.
                    connection_pool_size=50,
                    connection_timeout=30,
                    max_connection_lifetime=3600,
                )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def create_nodes_and_edges(
    course_id: str, nodes: list[dict], edges: list[dict]
) -> tuple[list[str], list[str]]:
    """Create KnowledgeNode nodes and dependency edges in Neo4j.

    Edge relations are stored as Neo4j relationship type (uppercased) so that
    different relation types (prerequisite, related, next, etc.) are preserved
    as distinct relationship types in the graph database.

    Returns the created Neo4j node IDs for nodes and relationship IDs for edges.
    """
    driver = await get_driver()
    node_ids = []
    rel_ids = []

    node_batch = [
        {
            "id": node.get("id"),
            "name": node.get("name", ""),
            "description": node.get("description", ""),
            "threshold": node.get("threshold", 0.8),
        }
        for node in nodes
    ]
    # Group edges by relation type so each type gets its own relationship label.
    edges_by_type: dict[str, list[dict]] = {}
    for edge in edges:
        if not edge.get("from") or not edge.get("to"):
            continue
        relation = (edge.get("relation") or "prerequisite").strip().upper()
        # Sanitize: Neo4j relationship types must be alphanumeric + underscore.
        relation = "".join(c if c.isalnum() or c == "_" else "_" for c in relation)
        if not relation:
            relation = "PREREQUISITE"
        edges_by_type.setdefault(relation, []).append(
            {"from": edge["from"], "to": edge["to"], "relation": edge.get("relation", "prerequisite")}
        )

    async with driver.session() as session:
        # Create nodes in bulk via UNWIND.
        if node_batch:
            node_result = await session.run(
                """
                UNWIND $nodes AS node
                MERGE (n:KnowledgeNode {course_id: $course_id, node_id: node.id})
                SET n.name = node.name,
                    n.description = node.description,
                    n.threshold = node.threshold
                RETURN elementId(n) AS eid
                """,
                course_id=course_id,
                nodes=node_batch,
            )
            async for record in node_result:
                node_ids.append(record["eid"])
            await node_result.consume()

        # Create edges per relation type so each type is a distinct relationship.
        for rel_type, batch in edges_by_type.items():
            edge_result = await session.run(
                f"""
                UNWIND $edges AS edge
                MATCH (a:KnowledgeNode {{course_id: $course_id, node_id: edge.from}})
                MATCH (b:KnowledgeNode {{course_id: $course_id, node_id: edge.to}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r.relation = edge.relation
                RETURN elementId(r) AS eid
                """,
                course_id=course_id,
                edges=batch,
            )
            async for record in edge_result:
                rel_ids.append(record["eid"])
            await edge_result.consume()

    return node_ids, rel_ids


async def get_graph(course_id: str) -> dict:
    """Return all nodes and edges for a course."""
    driver = await get_driver()
    nodes = []
    edges = []

    async with driver.session() as session:
        node_result = await session.run(
            """
            MATCH (n:KnowledgeNode {course_id: $course_id})
            RETURN n.node_id AS id, n.name AS name,
                   n.description AS description, n.threshold AS threshold
            """,
            course_id=course_id,
        )
        async for record in node_result:
            nodes.append(
                {
                    "id": record["id"],
                    "name": record["name"],
                    "description": record["description"],
                    "threshold": record["threshold"],
                }
            )

        # Match any relationship type between course nodes, not just PREREQUISITE.
        edge_result = await session.run(
            """
            MATCH (a:KnowledgeNode {course_id: $course_id})-[r]->(b:KnowledgeNode {course_id: $course_id})
            RETURN a.node_id AS from_id, b.node_id AS to_id,
                   r.relation AS relation, type(r) AS rel_type
            """,
            course_id=course_id,
        )
        async for record in edge_result:
            relation = record["relation"] or record["rel_type"] or "prerequisite"
            edges.append(
                {
                    "from": record["from_id"],
                    "to": record["to_id"],
                    "relation": relation,
                }
            )

    return {"nodes": nodes, "edges": edges}


async def get_prerequisites(node_id: str, course_id: str | None = None) -> list[dict]:
    """Return all prerequisite nodes for a given node_id."""
    driver = await get_driver()
    prereqs = []

    async with driver.session() as session:
        if course_id:
            result = await session.run(
                """
                MATCH (p:KnowledgeNode)-[:PREREQUISITE]->(n:KnowledgeNode {course_id: $course_id, node_id: $node_id})
                RETURN p.node_id AS id, p.name AS name, p.description AS description
                """,
                course_id=course_id,
                node_id=node_id,
            )
        else:
            result = await session.run(
                """
                MATCH (p:KnowledgeNode)-[:PREREQUISITE]->(n:KnowledgeNode {node_id: $node_id})
                RETURN p.node_id AS id, p.name AS name, p.description AS description
                """,
                node_id=node_id,
            )
        async for record in result:
            prereqs.append(
                {
                    "id": record["id"],
                    "name": record["name"],
                    "description": record["description"],
                }
            )

    return prereqs


async def delete_node(course_id: str, node_id: str) -> None:
    """Delete a KnowledgeNode and its relationships from Neo4j.

    Postgres cascades handle edges/mastery on the SQL side, but Neo4j has no
    cross-store cascade, so callers must invoke this to keep the graph DB
    consistent when a knowledge node is deleted.
    """
    driver = await get_driver()
    async with driver.session() as session:
        # DETACH DELETE removes the node together with all its relationships.
        await session.run(
            """
            MATCH (n:KnowledgeNode {course_id: $course_id, node_id: $node_id})
            DETACH DELETE n
            """,
            course_id=course_id,
            node_id=node_id,
        )
