"""
Neo4j graph storage layer for the brain-memory service.
Provides async CRUD and traversal operations on memory nodes and relations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, exceptions as neo4j_exc

from server.models.node import Node
from server.models.relation import Relation

logger = logging.getLogger(__name__)


class GraphStore:
    """
    Async Neo4j graph store for memory nodes and relations.

    All nodes carry tenant_id and user_id properties for multi-tenant data isolation.
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        """
        Initialize the graph store with Neo4j connection parameters.

        Args:
            uri: Neo4j bolt URI, e.g. bolt://localhost:7687
            user: Neo4j username
            password: Neo4j password
        """
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        """Establish connection to Neo4j and verify connectivity."""
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            await self._driver.verify_connectivity()
            logger.info("Connected to Neo4j at %s", self._uri)
        except neo4j_exc.ServiceUnavailable as e:
            logger.error("Failed to connect to Neo4j: %s", e)
            raise

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    def _ensure_connected(self) -> AsyncDriver:
        """Return driver or raise if not connected."""
        if self._driver is None:
            raise RuntimeError("GraphStore is not connected. Call connect() first.")
        return self._driver

    # -------------------------------------------------------------------------
    # Node operations
    # -------------------------------------------------------------------------

    async def create_node(self, node: Node, tenant_id: str, user_id: str) -> Node:
        """
        Create a new memory node in the graph.

        Args:
            node: Node instance to persist
            tenant_id: Tenant identifier for data isolation
            user_id: User identifier for data isolation

        Returns:
            The created Node (with server-assigned timestamps preserved)
        """
        driver = self._ensure_connected()
        props = node.to_neo4j_props(tenant_id, user_id)
        query = """
        CREATE (n:MemoryNode $props)
        RETURN n
        """
        async with driver.session() as session:
            result = await session.run(query, props=props)
            record = await result.single()
            if record is None:
                raise RuntimeError(f"Failed to create node: {node.id}")
            return Node.from_neo4j_props(dict(record["n"]))

    async def update_node(self, node_id: str, updates: Dict[str, Any]) -> Node:
        """
        Update properties of an existing node.

        Args:
            node_id: Target node ID
            updates: Dict of property updates (partial update)

        Returns:
            Updated Node

        Raises:
            ValueError: If node not found
        """
        driver = self._ensure_connected()
        import json
        # Serialize complex fields if present
        if "emotional_tag" in updates and isinstance(updates["emotional_tag"], dict):
            updates["emotional_tag"] = json.dumps(updates["emotional_tag"])
        if "properties" in updates and isinstance(updates["properties"], dict):
            updates["properties"] = json.dumps(updates["properties"])
        for field in ("created_at", "updated_at", "last_accessed", "valid_from", "valid_until"):
            if field in updates and isinstance(updates[field], datetime):
                updates[field] = updates[field].isoformat()
        updates["updated_at"] = datetime.utcnow().isoformat()

        query = """
        MATCH (n:MemoryNode {id: $node_id})
        SET n += $updates
        RETURN n
        """
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id, updates=updates)
            record = await result.single()
            if record is None:
                raise ValueError(f"Node not found: {node_id}")
            return Node.from_neo4j_props(dict(record["n"]))

    async def get_node(self, node_id: str) -> Optional[Node]:
        """
        Retrieve a node by its ID.

        Args:
            node_id: Node ID to look up

        Returns:
            Node if found, None otherwise
        """
        driver = self._ensure_connected()
        query = "MATCH (n:MemoryNode {id: $node_id}) RETURN n"
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id)
            record = await result.single()
            if record is None:
                return None
            return Node.from_neo4j_props(dict(record["n"]))

    async def find_nodes_by_name(self, name: str, tenant_id: str, user_id: str) -> List[Node]:
        """
        Find nodes by exact name match within a tenant/user scope.

        Args:
            name: Exact node name to match
            tenant_id: Tenant scope
            user_id: User scope

        Returns:
            List of matching nodes
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {name: $name, tenant_id: $tenant_id, user_id: $user_id})
        RETURN n
        """
        async with driver.session() as session:
            result = await session.run(query, name=name, tenant_id=tenant_id, user_id=user_id)
            return [Node.from_neo4j_props(dict(r["n"])) async for r in result]

    async def find_nodes_by_alias(self, alias: str, tenant_id: str, user_id: str) -> List[Node]:
        """
        Find nodes where the given alias appears in the aliases list.

        Args:
            alias: Alias string to search for
            tenant_id: Tenant scope
            user_id: User scope

        Returns:
            List of matching nodes
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
        WHERE $alias IN n.aliases
        RETURN n
        """
        async with driver.session() as session:
            result = await session.run(query, alias=alias, tenant_id=tenant_id, user_id=user_id)
            return [Node.from_neo4j_props(dict(r["n"])) async for r in result]

    async def find_nodes_by_tags(self, tags: List[str], tenant_id: str, user_id: str) -> List[Node]:
        """
        Find nodes that contain ALL of the specified tags.

        Args:
            tags: List of tags that must all be present
            tenant_id: Tenant scope
            user_id: User scope

        Returns:
            List of matching nodes
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
        WHERE ALL(tag IN $tags WHERE tag IN n.tags)
        RETURN n
        """
        async with driver.session() as session:
            result = await session.run(query, tags=tags, tenant_id=tenant_id, user_id=user_id)
            return [Node.from_neo4j_props(dict(r["n"])) async for r in result]

    async def find_nodes_fuzzy(self, keyword: str, tenant_id: str, user_id: str) -> List[Node]:
        """
        Fuzzy search nodes by keyword (name CONTAINS match).

        Args:
            keyword: Substring to search in node names
            tenant_id: Tenant scope
            user_id: User scope

        Returns:
            List of matching nodes
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
        WHERE toLower(n.name) CONTAINS toLower($keyword)
        RETURN n
        """
        async with driver.session() as session:
            result = await session.run(query, keyword=keyword, tenant_id=tenant_id, user_id=user_id)
            return [Node.from_neo4j_props(dict(r["n"])) async for r in result]

    async def traverse_relations(self, node_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Traverse all outgoing relationships from a node up to max_depth hops.

        Args:
            node_id: Starting node ID
            max_depth: Maximum traversal depth (default 2)

        Returns:
            List of dicts with keys: from_id, to_id, rel_type, rel_props, node_props
        """
        driver = self._ensure_connected()
        query = f"""
        MATCH path = (start:MemoryNode {{id: $node_id}})-[r*1..{max_depth}]->(end:MemoryNode)
        UNWIND relationships(path) AS rel
        RETURN startNode(rel).id AS from_id,
               endNode(rel).id AS to_id,
               type(rel) AS rel_type,
               properties(rel) AS rel_props,
               properties(endNode(rel)) AS node_props
        """
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id)
            rows = []
            async for r in result:
                rows.append({
                    "from_id": r["from_id"],
                    "to_id": r["to_id"],
                    "rel_type": r["rel_type"],
                    "rel_props": dict(r["rel_props"]),
                    "node_props": dict(r["node_props"]),
                })
            return rows

    # -------------------------------------------------------------------------
    # Relation operations
    # -------------------------------------------------------------------------

    async def create_relation(self, relation: Relation) -> Relation:
        """
        Create a directed relationship between two existing nodes.

        Args:
            relation: Relation instance to persist

        Returns:
            The created Relation

        Raises:
            ValueError: If either node does not exist
        """
        driver = self._ensure_connected()
        props = relation.to_neo4j_props()
        rel_type = relation.type.upper().replace(" ", "_")
        query = f"""
        MATCH (a:MemoryNode {{id: $from_id}})
        MATCH (b:MemoryNode {{id: $to_id}})
        CREATE (a)-[r:{rel_type} $props]->(b)
        RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
        """
        async with driver.session() as session:
            result = await session.run(
                query, from_id=relation.from_id, to_id=relation.to_id, props=props
            )
            record = await result.single()
            if record is None:
                raise ValueError(
                    f"Failed to create relation: nodes {relation.from_id} or {relation.to_id} not found"
                )
            return Relation.from_neo4j_record(
                record["from_id"], record["to_id"], record["rel_type"], dict(record["r"])
            )

    async def update_relation(
        self, from_id: str, to_id: str, rel_type: str, updates: Dict[str, Any]
    ) -> None:
        """
        Update properties of an existing relationship.

        Args:
            from_id: Source node ID
            to_id: Target node ID
            rel_type: Relationship type string
            updates: Property updates to apply
        """
        driver = self._ensure_connected()
        import json
        if "properties" in updates and isinstance(updates["properties"], dict):
            updates["properties"] = json.dumps(updates["properties"])
        for field in ("valid_from", "valid_until"):
            if field in updates and isinstance(updates[field], datetime):
                updates[field] = updates[field].isoformat()
        cypher_type = rel_type.upper().replace(" ", "_")
        query = f"""
        MATCH (a:MemoryNode {{id: $from_id}})-[r:{cypher_type}]->(b:MemoryNode {{id: $to_id}})
        SET r += $updates
        """
        async with driver.session() as session:
            await session.run(query, from_id=from_id, to_id=to_id, updates=updates)

    async def get_relations(self, node_id: str) -> List[Relation]:
        """
        Get all relationships (incoming and outgoing) for a node.

        Args:
            node_id: Node ID to query

        Returns:
            List of Relation objects
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {id: $node_id})-[r]-(m:MemoryNode)
        RETURN startNode(r).id AS from_id, endNode(r).id AS to_id,
               type(r) AS rel_type, properties(r) AS rel_props
        """
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id)
            relations = []
            async for r in result:
                relations.append(
                    Relation.from_neo4j_record(
                        r["from_id"], r["to_id"], r["rel_type"], dict(r["rel_props"])
                    )
                )
            return relations

    # -------------------------------------------------------------------------
    # Advanced queries
    # -------------------------------------------------------------------------

    async def find_active_nodes(
        self,
        tenant_id: str,
        user_id: str,
        zone: Optional[str] = None,
        min_strength: float = 0.0,
    ) -> List[Node]:
        """
        Find all active nodes for a tenant/user, optionally filtered by zone and strength.

        Args:
            tenant_id: Tenant scope
            user_id: User scope
            zone: Optional memory zone filter
            min_strength: Minimum retrieval_strength threshold

        Returns:
            List of active nodes
        """
        driver = self._ensure_connected()
        zone_filter = "AND n.zone = $zone" if zone else ""
        query = f"""
        MATCH (n:MemoryNode {{tenant_id: $tenant_id, user_id: $user_id, status: 'active'}})
        WHERE n.retrieval_strength >= $min_strength {zone_filter}
        RETURN n
        ORDER BY n.retrieval_strength DESC
        """
        params: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "min_strength": min_strength,
        }
        if zone:
            params["zone"] = zone
        async with driver.session() as session:
            result = await session.run(query, **params)
            return [Node.from_neo4j_props(dict(r["n"])) async for r in result]

    async def update_access(self, node_id: str) -> None:
        """
        Increment access_count, update last_accessed, and strengthen retrieval.
        Retrieval practice effect: each recall strengthens the memory (+0.5, cap 10).
        """
        driver = self._ensure_connected()
        now = datetime.utcnow().isoformat()
        query = """
        MATCH (n:MemoryNode {id: $node_id})
        SET n.access_count = n.access_count + 1,
            n.last_accessed = $now,
            n.retrieval_strength = CASE
                WHEN n.retrieval_strength + 0.5 > 10.0 THEN 10.0
                ELSE n.retrieval_strength + 0.5
            END
        """
        async with driver.session() as session:
            await session.run(query, node_id=node_id, now=now)

    async def apply_decay(
        self, tenant_id: str, user_id: str, base_half_life_days: int = 30
    ) -> None:
        """
        Apply memory decay with importance-weighted and zone-differentiated half-lives.

        Effective half-life = base × (1 + importance/10) × zone_factor
        Zone factors: episodic=0.5, semantic=2.0, procedural=3.0, emotional=1.0
        Nodes with retrieval_strength < 0.1 transition to 'dormant'.
        """
        driver = self._ensure_connected()
        now = datetime.utcnow().isoformat()
        query = """
        MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id, status: 'active'})
        WITH n,
             CASE n.zone
                 WHEN 'episodic' THEN 0.5
                 WHEN 'semantic' THEN 2.0
                 WHEN 'procedural' THEN 3.0
                 ELSE 1.0
             END AS zone_factor,
             duration.between(datetime(n.last_accessed), datetime($now)).days AS days_elapsed
        WITH n, days_elapsed,
             $base_half_life * (1.0 + n.importance / 10.0) * zone_factor AS effective_half_life
        WITH n, days_elapsed, effective_half_life,
             n.retrieval_strength * n.decay_factor * exp(-0.693147 / effective_half_life * toFloat(days_elapsed)) AS new_strength
        SET n.retrieval_strength = new_strength,
            n.status = CASE WHEN new_strength < 0.1 THEN 'dormant' ELSE n.status END
        """
        async with driver.session() as session:
            await session.run(
                query,
                tenant_id=tenant_id,
                user_id=user_id,
                now=now,
                base_half_life=float(base_half_life_days),
            )
        logger.info(
            "Applied decay (base_half_life=%d days) for tenant=%s user=%s",
            base_half_life_days, tenant_id, user_id,
        )

    async def merge_nodes(self, keep_id: str, remove_id: str) -> None:
        """
        Merge two nodes: transfer relations from remove to keep, merge aliases/tags,
        then delete the remove node. Uses native Cypher (no APOC dependency).
        """
        driver = self._ensure_connected()
        async with driver.session() as session:
            # Verify both nodes exist
            check = await session.run(
                "MATCH (n:MemoryNode) WHERE n.id IN [$keep_id, $remove_id] RETURN count(n) AS cnt",
                keep_id=keep_id, remove_id=remove_id,
            )
            record = await check.single()
            if record is None or record["cnt"] < 2:
                raise ValueError(f"One or both nodes not found: keep={keep_id}, remove={remove_id}")

            # Transfer outgoing relations (create new, delete old)
            await session.run(
                """
                MATCH (remove:MemoryNode {id: $remove_id})-[r]->(target:MemoryNode)
                WHERE target.id <> $keep_id
                WITH remove, r, target, type(r) AS rtype, properties(r) AS rprops
                MATCH (keep:MemoryNode {id: $keep_id})
                CREATE (keep)-[nr:RELATED_TO]->(target)
                SET nr = rprops
                DELETE r
                """,
                keep_id=keep_id, remove_id=remove_id,
            )

            # Transfer incoming relations
            await session.run(
                """
                MATCH (source:MemoryNode)-[r]->(remove:MemoryNode {id: $remove_id})
                WHERE source.id <> $keep_id
                WITH source, r, remove, type(r) AS rtype, properties(r) AS rprops
                MATCH (keep:MemoryNode {id: $keep_id})
                CREATE (source)-[nr:RELATED_TO]->(keep)
                SET nr = rprops
                DELETE r
                """,
                keep_id=keep_id, remove_id=remove_id,
            )

            # Merge aliases and tags from remove into keep
            await session.run(
                """
                MATCH (keep:MemoryNode {id: $keep_id})
                MATCH (remove:MemoryNode {id: $remove_id})
                SET keep.aliases = keep.aliases + [x IN remove.aliases WHERE NOT x IN keep.aliases],
                    keep.tags = keep.tags + [x IN remove.tags WHERE NOT x IN keep.tags],
                    keep.source_sessions = keep.source_sessions + [x IN remove.source_sessions WHERE NOT x IN keep.source_sessions]
                """,
                keep_id=keep_id, remove_id=remove_id,
            )

            # Delete the remove node and its remaining relationships
            await session.run(
                "MATCH (n:MemoryNode {id: $remove_id}) DETACH DELETE n",
                remove_id=remove_id,
            )
        logger.info("Merged node %s into %s", remove_id, keep_id)

    async def find_dormant_nodes(
        self, keywords: List[str], tenant_id: str, user_id: str, limit: int = 5
    ) -> List[Node]:
        """Search dormant nodes by name/alias keyword match."""
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id, status: 'dormant'})
        WHERE any(kw IN $keywords WHERE n.name CONTAINS kw OR any(a IN n.aliases WHERE a CONTAINS kw))
        RETURN n ORDER BY n.importance DESC LIMIT $limit
        """
        async with driver.session() as session:
            result = await session.run(
                query, tenant_id=tenant_id, user_id=user_id,
                keywords=keywords, limit=limit,
            )
            records = await result.data()
        return [self._record_to_node(r["n"]) for r in records if r.get("n")]

    async def revive_if_dormant(self, node_id: str) -> bool:
        """Revive a dormant node back to active with reset strength=5.0."""
        driver = self._ensure_connected()
        now = datetime.utcnow().isoformat()
        query = """
        MATCH (n:MemoryNode {id: $node_id, status: 'dormant'})
        SET n.status = 'active', n.retrieval_strength = 5.0, n.last_accessed = $now
        RETURN n.id AS revived
        """
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id, now=now)
            record = await result.single()
        if record and record.get("revived"):
            logger.info("Revived dormant node %s", node_id)
            return True
        return False

    async def add_aliases(self, node_id: str, aliases: List[str]) -> None:
        """Add aliases to an existing node (merge, no duplicates)."""
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {id: $node_id})
        SET n.aliases = n.aliases + [x IN $aliases WHERE NOT x IN n.aliases]
        """
        async with driver.session() as session:
            await session.run(query, node_id=node_id, aliases=aliases)

    async def merge_tags(self, node_id: str, new_tags: List[str]) -> None:
        """Merge new tags into an existing node (no duplicates)."""
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {id: $node_id})
        SET n.tags = n.tags + [x IN $new_tags WHERE NOT x IN n.tags]
        """
        async with driver.session() as session:
            await session.run(query, node_id=node_id, new_tags=new_tags)

    # ------------------------------------------------------------------
    # Vector search methods
    # ------------------------------------------------------------------

    async def ensure_vector_index(self):
        """Create vector index for MemoryNode embeddings if not exists."""
        async with self._driver.session() as session:
            result = await session.run(
                "SHOW INDEXES YIELD name WHERE name = 'memory_embedding' RETURN count(*) as count"
            )
            record = await result.single()
            if record and record["count"] > 0:
                return
            await session.run("""
                CREATE VECTOR INDEX memory_embedding IF NOT EXISTS
                FOR (n:MemoryNode) ON (n.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 1536,
                    `vector.similarity_function`: 'cosine'
                }}
            """)
            logger.info("Created vector index 'memory_embedding'")

    async def update_node_embedding(self, node_id: str, embedding: list):
        """Update the embedding property of a MemoryNode."""
        async with self._driver.session() as session:
            await session.run(
                "MATCH (n:MemoryNode {id: $id}) SET n.embedding = $embedding",
                id=node_id, embedding=embedding
            )

    async def vector_search(self, query_embedding: list, top_k: int = 10, min_score: float = 0.5) -> list:
        """Vector similarity search on MemoryNodes."""
        async with self._driver.session() as session:
            result = await session.run("""
                CALL db.index.vector.queryNodes('memory_embedding', $top_k, $embedding)
                YIELD node, score
                WHERE score >= $min_score AND node.status <> 'suppressed'
                RETURN node, score
                ORDER BY score DESC
            """, top_k=top_k, embedding=query_embedding, min_score=min_score)
            records = [r async for r in result]
            return [{"node": dict(r["node"]), "score": r["score"]} for r in records]

    async def get_all_graph_data(self, tenant_id: str, user_id: str, limit: int = 300) -> Dict[str, Any]:
        """
        Fetch nodes and relationships for graph visualization up to a limit.
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
        WITH n ORDER BY n.updated_at DESC LIMIT $limit
        OPTIONAL MATCH (n)-[r]->(m:MemoryNode)
        WHERE m.tenant_id = $tenant_id AND m.user_id = $user_id
        RETURN n AS node, r AS relation, m AS target
        """
        async with driver.session() as session:
            result = await session.run(query, tenant_id=tenant_id, user_id=user_id, limit=limit)
            
            nodes_dict = {}
            relations = []
            
            async for r in result:
                # Add node
                node_data = r["node"]
                if node_data:
                    node_props = dict(node_data)
                    node_id = node_props.get("id")
                    if node_id and node_id not in nodes_dict:
                        nodes_dict[node_id] = node_props
                
                # Add relation and target if they exist
                rel_data = r.get("relation")
                target_data = r.get("target")
                
                if rel_data and target_data:
                    rel_type = rel_data.type
                    rel_props = dict(rel_data)
                    target_props = dict(target_data)
                    target_id = target_props.get("id")
                    
                    if target_id and target_id not in nodes_dict:
                        nodes_dict[target_id] = target_props
                        
                    relations.append({
                        "from_id": node_id,
                        "to_id": target_id,
                        "rel_type": rel_type,
                        "rel_props": rel_props
                    })
            
            # De-duplicate relations just in case
            unique_relations = []
            seen_rels = set()
            for rel in relations:
                # Basic signature for unique relations
                sig = f"{rel['from_id']}-{rel['to_id']}-{rel['rel_type']}"
                if sig not in seen_rels:
                    seen_rels.add(sig)
                    unique_relations.append(rel)
                    
            return {
                "nodes": list(nodes_dict.values()),
                "relations": unique_relations
            }

    async def delete_node_and_relations(self, node_id: str, tenant_id: str, user_id: str) -> bool:
        """
        Delete a node and all its relationships (DETACH DELETE).
        """
        driver = self._ensure_connected()
        query = """
        MATCH (n:MemoryNode {id: $node_id, tenant_id: $tenant_id, user_id: $user_id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id, tenant_id=tenant_id, user_id=user_id)
            record = await result.single()
            return record and record["deleted"] > 0

    async def delete_relation(self, from_id: str, to_id: str, rel_type: str, tenant_id: str, user_id: str) -> bool:
        """
        Delete a specific relationship between two nodes.
        """
        driver = self._ensure_connected()
        cypher_type = rel_type.upper().replace(" ", "_")
        query = f"""
        MATCH (a:MemoryNode {{id: $from_id, tenant_id: $tenant_id, user_id: $user_id}})-[r:{cypher_type}]->(b:MemoryNode {{id: $to_id, tenant_id: $tenant_id, user_id: $user_id}})
        DELETE r
        RETURN count(r) AS deleted
        """
        async with driver.session() as session:
            result = await session.run(query, from_id=from_id, to_id=to_id, tenant_id=tenant_id, user_id=user_id)
            record = await result.single()
            return record and record["deleted"] > 0
