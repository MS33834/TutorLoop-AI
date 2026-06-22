"""Neo4j graph database access."""

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    """Return a singleton Neo4j async driver."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
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
    """Create KnowledgeNode nodes and PREREQUISITE edges in Neo4j.

    Returns the created Neo4j node IDs for nodes and relationship IDs for edges.
    """
    driver = await get_driver()
    node_ids = []
    rel_ids = []

    async with driver.session() as session:
        # Create nodes
        for node in nodes:
            node_id = node.get("id")
            name = node.get("name", "")
            description = node.get("description", "")
            threshold = node.get("threshold", 0.8)

            result = await session.run(
                """
                MERGE (n:KnowledgeNode {course_id: $course_id, node_id: $node_id})
                SET n.name = $name,
                    n.description = $description,
                    n.threshold = $threshold
                RETURN elementId(n) AS eid
                """,
                course_id=course_id,
                node_id=node_id,
                name=name,
                description=description,
                threshold=threshold,
            )
            record = await result.single()
            if record:
                node_ids.append(record["eid"])
            await result.consume()

        # Create edges
        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            relation = edge.get("relation", "prerequisite")
            if not from_id or not to_id:
                continue

            result = await session.run(
                """
                MATCH (a:KnowledgeNode {course_id: $course_id, node_id: $from_id})
                MATCH (b:KnowledgeNode {course_id: $course_id, node_id: $to_id})
                MERGE (a)-[r:PREREQUISITE]->(b)
                SET r.relation = $relation
                RETURN elementId(r) AS eid
                """,
                course_id=course_id,
                from_id=from_id,
                to_id=to_id,
                relation=relation,
            )
            record = await result.single()
            if record:
                rel_ids.append(record["eid"])
            await result.consume()

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

        edge_result = await session.run(
            """
            MATCH (a:KnowledgeNode {course_id: $course_id})-[r:PREREQUISITE]->(b:KnowledgeNode {course_id: $course_id})
            RETURN a.node_id AS from_id, b.node_id AS to_id, r.relation AS relation
            """,
            course_id=course_id,
        )
        async for record in edge_result:
            edges.append(
                {
                    "from": record["from_id"],
                    "to": record["to_id"],
                    "relation": record["relation"],
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
