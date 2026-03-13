"""
Retriever engine component for the brain-memory service.
Corresponds to the memory retrieval mechanism in the human brain.
Implements multi-path retrieval and LLM-based context reconstruction.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from server.engine.llm_client import call_llm, call_llm_json
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore

logger = logging.getLogger(__name__)

_EXTRACT_CLUES_SYSTEM = """\
You are a query analyzer for a memory retrieval system.
Extract search clues from the user's query to help find relevant memories.

Return ONLY valid JSON:
{
  "entities": ["entity name 1", "entity name 2"],
  "keywords": ["keyword1", "keyword2"],
  "time_hint": "today|recent|specific_date|none",
  "query_intent": "one-sentence description of what the user wants to know"
}
"""

_RECONSTRUCT_SYSTEM = """\
You are a memory context synthesizer for an AI agent. \
Given a set of raw memory fragments, synthesize them into a coherent, \
natural-language context paragraph that the agent can use to answer the user's query.

Rules:
- Be concise but complete — include all relevant facts.
- Use natural language, not bullet points.
- If memories are contradictory, note the contradiction.
- If memories are sparse, say so honestly.
- Write in the same language as the query.
"""


class Retriever:
    """
    Multi-path memory retriever — the recall mechanism of the memory system.

    Searches the graph via three parallel paths (exact name, alias, fuzzy),
    traverses relations, merges with buffer contents, scores results, and
    reconstructs a coherent context string via LLM.
    """

    def __init__(self, graph: GraphStore, buffer: EncoderBuffer) -> None:
        """
        Initialize the retriever.

        Args:
            graph: GraphStore instance for graph-based retrieval.
            buffer: EncoderBuffer instance for buffer-based retrieval.
        """
        self.graph = graph
        self.buffer = buffer

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        working_memory: Optional[Dict[str, Any]] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Retrieve memories relevant to the query using multi-path search.

        Multi-path retrieval flow:
        1. Extract entity clues and keywords from the query via LLM.
        2. Path A: Exact name match → find_nodes_by_name
        3. Path B: Alias match → find_nodes_by_alias
        4. Path C: Fuzzy keyword match → find_nodes_fuzzy
        5. Relation traversal from matched nodes (1-2 hops).
        6. Buffer retrieval: recent unarchived memory units.
        7. Deduplicate and score all candidates.
        8. LLM reconstructs top-K fragments into a coherent context.
        9. Update access records for retrieved nodes.

        Composite score = relevance×0.4 + importance×0.2 + recency×0.2
                        + access_frequency×0.1 + emotional_resonance×0.1

        Args:
            query: Natural language query string.
            tenant_id: Tenant identifier.
            user_id: User identifier.
            working_memory: Optional session context for scoring.
            max_results: Maximum number of memory fragments to include.

        Returns:
            Dict with keys:
                - "context": str — natural language context ready for LLM injection
                - "memories": list of {"id", "content", "relevance", "confidence"}
        """
        # Step 1: Extract search clues
        clues = await self._extract_clues(query)
        entities = clues.get("entities", [])
        keywords = clues.get("keywords", [])

        # Steps 2-5: Multi-path graph retrieval (run in parallel where possible)
        node_candidates: Dict[str, Any] = {}  # node_id → scored candidate

        graph_tasks = []
        for entity in entities:
            graph_tasks.append(self._search_by_name(entity, tenant_id, user_id))
            graph_tasks.append(self._search_by_alias(entity, tenant_id, user_id))
        for kw in keywords:
            graph_tasks.append(self._search_fuzzy(kw, tenant_id, user_id))

        if graph_tasks:
            results = await asyncio.gather(*graph_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Graph search path failed: %s", result)
                    continue
                for node in result:
                    if node.id not in node_candidates:
                        node_candidates[node.id] = node

        # Search dormant nodes too (for revival)
        all_search_terms = entities + keywords
        if all_search_terms:
            try:
                dormant_matches = await self.graph.find_dormant_nodes(
                    all_search_terms, tenant_id, user_id, limit=5)
                for node in dormant_matches:
                    if node.id not in node_candidates:
                        node_candidates[node.id] = node
            except Exception as e:
                logger.warning("Dormant search failed: %s", e)

        # Step 5: Relation traversal from matched nodes
        traversal_tasks = [
            self._traverse(node_id) for node_id in list(node_candidates.keys())[:5]
        ]
        if traversal_tasks:
            traversal_results = await asyncio.gather(*traversal_tasks, return_exceptions=True)
            for tresult in traversal_results:
                if isinstance(tresult, Exception):
                    continue
                for row in tresult:
                    node_id = row.get("to_id")
                    if node_id and node_id not in node_candidates:
                        # Create a lightweight placeholder from traversal data
                        node_candidates[node_id] = self._node_from_traversal(row)

        # Step 6: Buffer retrieval
        buffer_units = []
        try:
            buffer_units = self.buffer.read_recent(tenant_id, user_id, limit=20)
        except Exception as e:
            logger.warning("Buffer retrieval failed: %s", e)

        # Step 7: Score and rank
        scored = self._score_candidates(
            list(node_candidates.values()), buffer_units, query, entities, keywords
        )
        top_k = scored[:max_results]

        # Step 8: LLM reconstruction
        context = await self._reconstruct_context(query, top_k)

        # Step 9: Update access records for graph nodes
        node_ids_to_update = [
            c["id"] for c in top_k if c.get("source") == "graph"
        ]
        await self._update_access_batch(node_ids_to_update)

        memories = [
            {
                "id": c["id"],
                "content": c["content"],
                "relevance": round(c["score"], 3),
                "confidence": c.get("confidence", 1.0),
            }
            for c in top_k
        ]

        return {"context": context, "memories": memories}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _extract_clues(self, query: str) -> Dict[str, Any]:
        """Use LLM to extract entity names and keywords from the query."""
        try:
            return await call_llm_json(
                _EXTRACT_CLUES_SYSTEM,
                f'Query:\n"""\n{query}\n"""',
            )
        except Exception as e:
            logger.warning("Clue extraction failed: %s", e)
            # Fallback: use the whole query as a keyword
            return {"entities": [], "keywords": [query], "time_hint": "none", "query_intent": query}

    async def _search_by_name(self, name: str, tenant_id: str, user_id: str) -> list:
        try:
            return await self.graph.find_nodes_by_name(name, tenant_id, user_id)
        except Exception as e:
            logger.warning("find_nodes_by_name('%s') failed: %s", name, e)
            return []

    async def _search_by_alias(self, alias: str, tenant_id: str, user_id: str) -> list:
        try:
            return await self.graph.find_nodes_by_alias(alias, tenant_id, user_id)
        except Exception as e:
            logger.warning("find_nodes_by_alias('%s') failed: %s", alias, e)
            return []

    async def _search_fuzzy(self, keyword: str, tenant_id: str, user_id: str) -> list:
        try:
            return await self.graph.find_nodes_fuzzy(keyword, tenant_id, user_id)
        except Exception as e:
            logger.warning("find_nodes_fuzzy('%s') failed: %s", keyword, e)
            return []

    async def _traverse(self, node_id: str) -> list:
        try:
            return await self.graph.traverse_relations(node_id, max_depth=2)
        except Exception as e:
            logger.warning("traverse_relations('%s') failed: %s", node_id, e)
            return []

    @staticmethod
    def _node_from_traversal(row: Dict[str, Any]) -> Any:
        """Create a lightweight dict-like object from a traversal row."""
        props = row.get("node_props", {})

        class _NodeProxy:
            def __init__(self, p: dict) -> None:
                self.id = p.get("id", "")
                self.name = p.get("name", "")
                self.summary = p.get("summary", "")
                self.importance = float(p.get("importance", 5.0))
                self.retrieval_strength = float(p.get("retrieval_strength", 5.0))
                self.access_count = int(p.get("access_count", 0))
                self.last_accessed = p.get("last_accessed", "")
                self.emotional_tag = p.get("emotional_tag", {"type": "neutral", "intensity": 0})
                self.confidence = float(p.get("confidence", 1.0))
                self.content = p.get("content", "")

        return _NodeProxy(props)

    def _score_candidates(
        self,
        nodes: list,
        buffer_units: List[Dict[str, Any]],
        query: str,
        entities: List[str],
        keywords: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Score and merge graph nodes + buffer units into a unified ranked list.

        Composite score = relevance×0.4 + importance×0.2 + recency×0.2
                        + access_frequency×0.1 + emotional_resonance×0.1
        """
        candidates = []
        seen_ids: Set[str] = set()

        # Score graph nodes
        for node in nodes:
            if not node.id or node.id in seen_ids:
                continue
            seen_ids.add(node.id)

            relevance = self._text_relevance(
                f"{node.name} {node.summary} {node.content}", entities, keywords
            )
            importance = min(float(getattr(node, "importance", 5.0)) / 10.0, 1.0)
            recency = self._recency_score(getattr(node, "last_accessed", ""))
            access_freq = min(float(getattr(node, "access_count", 0)) / 100.0, 1.0)
            emotional = self._emotional_score(getattr(node, "emotional_tag", {}))

            score = (
                relevance * 0.4
                + importance * 0.2
                + recency * 0.2
                + access_freq * 0.1
                + emotional * 0.1
            )
            content = f"{node.name}: {getattr(node, 'summary', '') or getattr(node, 'content', '')}"
            candidates.append({
                "id": node.id,
                "content": content,
                "score": score,
                "confidence": float(getattr(node, "confidence", 1.0)),
                "source": "graph",
            })

        # Score buffer units
        for unit in buffer_units:
            unit_id = unit.get("id", "")
            if not unit_id or unit_id in seen_ids:
                continue
            seen_ids.add(unit_id)

            message = unit.get("message", "")
            relevance = self._text_relevance(message, entities, keywords)
            importance = min(float(unit.get("importance", 5.0)) / 10.0, 1.0)
            recency = self._recency_score(unit.get("timestamp", ""))
            emotional = float(unit.get("emotional_intensity", 0)) / 10.0

            score = relevance * 0.4 + importance * 0.2 + recency * 0.2 + 0.0 * 0.1 + emotional * 0.1
            candidates.append({
                "id": unit_id,
                "content": message,
                "score": score,
                "confidence": 0.9,
                "source": "buffer",
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    @staticmethod
    def _text_relevance(text: str, entities: List[str], keywords: List[str]) -> float:
        """Simple keyword overlap relevance score (0-1)."""
        if not text:
            return 0.0
        text_lower = text.lower()
        all_terms = entities + keywords
        if not all_terms:
            return 0.5
        hits = sum(1 for t in all_terms if t.lower() in text_lower)
        return min(hits / len(all_terms), 1.0)

    @staticmethod
    def _recency_score(timestamp_str: str) -> float:
        """Convert a timestamp to a 0-1 recency score (1 = just now, decays over 30 days)."""
        if not timestamp_str:
            return 0.0
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            ts = ts.replace(tzinfo=None)
            days_ago = (datetime.utcnow() - ts).total_seconds() / 86400.0
            return max(0.0, 1.0 - days_ago / 30.0)
        except Exception:
            return 0.0

    @staticmethod
    def _emotional_score(emotional_tag: Any) -> float:
        """Convert emotional_tag to a 0-1 resonance score."""
        if isinstance(emotional_tag, dict):
            intensity = float(emotional_tag.get("intensity", 0))
            return min(intensity / 10.0, 1.0)
        return 0.0

    async def _reconstruct_context(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> str:
        """Use LLM to synthesize top-K memory fragments into a coherent context."""
        if not candidates:
            return "No relevant memories found."

        fragments = "\n".join(
            f"[{i+1}] {c['content']}" for i, c in enumerate(candidates)
        )
        user_prompt = (
            f'User query: "{query}"\n\n'
            f"Memory fragments:\n{fragments}\n\n"
            "Synthesize these memories into a coherent context paragraph."
        )
        try:
            return await call_llm(_RECONSTRUCT_SYSTEM, user_prompt, temperature=0.3)
        except Exception as e:
            logger.error("Context reconstruction failed: %s", e)
            # Fallback: join fragments as plain text
            return "\n".join(c["content"] for c in candidates)

    async def _update_access_batch(self, node_ids: List[str]) -> None:
        """Update access records and revive dormant nodes if retrieved."""
        tasks = []
        for nid in node_ids:
            if nid:
                tasks.append(self._update_and_revive(nid))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_and_revive(self, node_id: str) -> None:
        """Update access for a node and revive it if dormant."""
        try:
            await self.graph.update_access(node_id)
            revived = await self.graph.revive_if_dormant(node_id)
            if revived:
                logger.info("Revived dormant node %s via retrieval", node_id)
        except Exception as e:
            logger.warning("update_access/revive('%s') failed: %s", node_id, e)
