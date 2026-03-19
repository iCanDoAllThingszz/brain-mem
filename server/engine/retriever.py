"""
Retriever engine component for the brain-memory service.
Corresponds to the memory retrieval mechanism in the human brain.
Implements multi-path retrieval and LLM-based context reconstruction.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from server.engine.llm_client import call_llm, call_llm_json
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore

logger = logging.getLogger(__name__)

_EXTRACT_CLUES_SYSTEM = """\
你是一个记忆检索系统的查询分析器。从用户的查询中提取搜索线索，帮助找到相关记忆。

重要规则：
- 只提取真正有意义的实体和关键词，不要提取停用词或过于通用的词
- 实体应该是人名、地名、项目名、具体事物等专有名词
- 关键词应该是有区分度的动词、名词、形容词
- 如果查询是纯社交性质（如"嗯嗯"、"好的"、"咋不回我"），返回空列表
- 如果查询是当前会话的延续（如"一起修复"、"继续"），返回空列表
- 识别查询中的情感信息（如"开心"、"沮丧"、"生气"、"害怕"、"惊讶"）

只返回有效的JSON：
{
  "entities": ["实体名1", "实体名2"],
  "keywords": ["关键词1", "关键词2"],
  "time_hint": "today|recent|specific_date|none",
  "query_intent": "用一句话描述用户想知道什么",
  "query_emotion": "joy|sadness|anger|fear|surprise|neutral"
}
"""

_RECONSTRUCT_SYSTEM = """\
你是AI助手长期记忆系统的记忆上下文合成器。给定一组原始记忆片段，将它们合成为简洁的事实性摘要。

关键规则：
- 只输出事实性记忆内容，不要回答用户的问题
- 不要提供分析、建议或评论
- 不要直接称呼用户（不要用"你"、"your"、"you"）
- 要简洁——只包含能提供新信息的事实（目标50-100字）
- 使用自然语言，不要用项目符号
- 如果记忆相互矛盾，注明矛盾之处
- 如果记忆稀疏或不相关，返回"No relevant memories found."
- 用中文书写（与存储的记忆语言一致）
- 这个上下文将作为背景知识前置到助手的prompt中
- 助手已经有当前对话历史——不要重复近期消息
- 如果记忆片段都是关于当前正在讨论的话题，说明这些记忆没有增量价值，返回"No relevant memories found."
"""


class Retriever:
    """
    Multi-path memory retriever — the recall mechanism of the memory system.

    Searches the graph via three parallel paths (exact name, alias, fuzzy),
    traverses relations, merges with buffer contents, scores results, and
    reconstructs a coherent context string via LLM.
    """

    # Class-level query cache: (session_id, query_hash) → (result, timestamp)
    _query_cache: Dict[tuple, tuple] = {}
    _CACHE_TTL_SECONDS = 10

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
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve memories relevant to the query using multi-path search.

        Multi-path retrieval flow:
        1. Check query cache to prevent duplicate calls within 10s.
        2. Extract entity clues and keywords from the query via LLM.
        3. Path A: Exact name match → find_nodes_by_name
        4. Path B: Alias match → find_nodes_by_alias
        5. Path C: Fuzzy keyword match → find_nodes_fuzzy
        6. Relation traversal from matched nodes (1-2 hops).
        7. Buffer retrieval: recent unarchived memory units.
        8. Deduplicate and score all candidates.
        9. Filter by minimum score threshold.
        10. LLM reconstructs top-K fragments into a coherent context.
        11. Update access records for retrieved nodes.

        Composite score = relevance×0.5 + importance×0.15 + recency×0.15
                        + access_frequency×0.1 + emotional_resonance×0.1

        Args:
            query: Natural language query string.
            tenant_id: Tenant identifier.
            user_id: User identifier.
            working_memory: Optional session context for scoring.
            max_results: Maximum number of memory fragments to include.
            session_id: Optional session identifier for caching.

        Returns:
            Dict with keys:
                - "context": str — natural language context ready for LLM injection
                - "memories": list of {"id", "content", "relevance", "confidence"}
        """
        # Step 1: Check query cache
        if session_id:
            query_hash = hashlib.md5(query.encode()).hexdigest()
            cache_key = (session_id, query_hash)
            if cache_key in self._query_cache:
                cached_result, cached_time = self._query_cache[cache_key]
                age = (datetime.utcnow() - cached_time).total_seconds()
                if age < self._CACHE_TTL_SECONDS:
                    logger.info("Returning cached result for session=%s query_hash=%s", session_id, query_hash[:8])
                    return cached_result

        # Step 2: Extract search clues
        clues = await self._extract_clues(query)
        # Guard against LLM returning non-dict (e.g., list)
        if not isinstance(clues, dict):
            logger.warning('_extract_clues returned %s instead of dict, using fallback', type(clues).__name__)
            clues = {"entities": [], "keywords": [query], "time_hint": "none", "query_intent": query, "query_emotion": "neutral"}
        entities = clues.get("entities", [])
        keywords = clues.get("keywords", [])
        query_emotion = clues.get("query_emotion", "neutral")

        # Determine current emotion from query or working memory
        current_emotion = query_emotion
        if current_emotion == "neutral" and working_memory:
            # Fallback to working memory emotional baseline
            baseline = working_memory.get("emotional_baseline", "neutral")
            # Map baseline to emotion type
            if baseline == "positive":
                current_emotion = "joy"
            elif baseline == "negative":
                current_emotion = "sadness"
            # else: keep neutral

        # If no meaningful clues extracted, return empty result
        if not entities and not keywords:
            logger.info("No meaningful clues extracted from query: %s", query)
            result = {"context": "No relevant memories found.", "memories": []}
            if session_id:
                self._query_cache[cache_key] = (result, datetime.utcnow())
            return result

        # Steps 3-6: Multi-path graph retrieval (run in parallel where possible)
        node_candidates: Dict[str, Any] = {}  # node_id → scored candidate
        fuzzy_matches: Dict[str, str] = {}  # node_id → fuzzy_query_term (for alias learning)

        graph_tasks = []
        task_metadata = []  # Track which search method and term for each task

        for entity in entities:
            graph_tasks.append(self._search_by_name(entity, tenant_id, user_id))
            task_metadata.append(("name", entity))
            graph_tasks.append(self._search_by_alias(entity, tenant_id, user_id))
            task_metadata.append(("alias", entity))
        for kw in keywords:
            graph_tasks.append(self._search_fuzzy(kw, tenant_id, user_id))
            task_metadata.append(("fuzzy", kw))

        if graph_tasks:
            results = await asyncio.gather(*graph_tasks, return_exceptions=True)
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning("Graph search path failed: %s", result)
                    continue
                search_method, search_term = task_metadata[idx]
                for node in result:
                    if node.id not in node_candidates:
                        node_candidates[node.id] = node
                        # Track fuzzy matches for alias learning
                        if search_method == "fuzzy":
                            fuzzy_matches[node.id] = search_term

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

        # Step 6: Relation traversal from matched nodes
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

        # Step 7: Buffer retrieval
        buffer_units = []
        try:
            buffer_units = self.buffer.read_recent(tenant_id, user_id, limit=20)
        except Exception as e:
            logger.warning("Buffer retrieval failed: %s", e)

        # Step 7.5: Vector semantic search (Path E)
        try:
            from server.engine.embedding_client import get_embedding
            import numpy as np

            query_embedding = await get_embedding(query, type_="query")
            if any(v != 0.0 for v in query_embedding[:10]):  # not a zero vector
                # E1: Neo4j vector search (long-term memory)
                try:
                    vector_hits = await self.graph.vector_search(query_embedding, top_k=5, min_score=0.5)
                    for hit in vector_hits:
                        node_data = hit["node"]
                        nid = node_data.get("id", "")
                        if nid and nid not in node_candidates:
                            node_candidates[nid] = self._node_from_dict(node_data)
                            logger.info("Vector search found node: %s (score=%.2f)", node_data.get("name"), hit["score"])
                except Exception as e:
                    logger.warning("Neo4j vector search failed: %s", e)

                # E2: Buffer vector search (short-term memory, numpy brute force)
                try:
                    buf_embeddings = self.buffer.get_embeddings(tenant_id, user_id)
                    if buf_embeddings:
                        q_emb = np.array(query_embedding, dtype=np.float32)
                        q_norm = np.linalg.norm(q_emb)
                        if q_norm > 0:
                            for buf_id, buf_emb_bytes in buf_embeddings:
                                b_emb = np.frombuffer(buf_emb_bytes, dtype=np.float32)
                                b_norm = np.linalg.norm(b_emb)
                                if b_norm > 0:
                                    score = float(np.dot(q_emb, b_emb) / (q_norm * b_norm))
                                    if score > 0.5:
                                        # Find the buffer unit and add if not already present
                                        for bu in buffer_units:
                                            if bu.get("id") == buf_id:
                                                bu["_vector_score"] = score
                                                break
                except Exception as e:
                    logger.warning("Buffer vector search failed: %s", e)
        except ImportError:
            pass  # embedding_client not available

        # Step 8: Score and rank
        scored = self._score_candidates(
            list(node_candidates.values()), buffer_units, query, entities, keywords, current_emotion
        )

        # Step 9: Filter by minimum score threshold
        MIN_SCORE_THRESHOLD = 0.25
        scored = [c for c in scored if c["score"] >= MIN_SCORE_THRESHOLD]

        if not scored:
            logger.info("No candidates passed minimum score threshold for query: %s", query)
            # Try fallback retrieval with relaxed constraints
            scored = await self._retrieve_with_fallback(
                query, entities, keywords, current_emotion, tenant_id, user_id, max_results,
                buffer_units=buffer_units,
            )

        if not scored:
            result = {"context": "No relevant memories found.", "memories": []}
            if session_id:
                self._query_cache[cache_key] = (result, datetime.utcnow())
            return result

        top_k = scored[:max_results]

        # Step 10: LLM reconstruction
        context = await self._reconstruct_context(query, top_k)

        # Step 11: Update access records for graph nodes
        node_ids_to_update = [
            c["id"] for c in top_k if c.get("source") == "graph"
        ]
        await self._update_access_batch(node_ids_to_update, fuzzy_matches)

        memories = [
            {
                "id": c["id"],
                "content": c["content"],
                "relevance": round(c["score"], 3),
                "confidence": c.get("confidence", 1.0),
            }
            for c in top_k
        ]

        result = {"context": context, "memories": memories}

        # Cache the result
        if session_id:
            self._query_cache[cache_key] = (result, datetime.utcnow())
            # Clean up old cache entries
            self._cleanup_cache()

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cleanup_cache(self) -> None:
        """Remove cache entries older than TTL."""
        now = datetime.utcnow()
        expired_keys = [
            k for k, (_, ts) in self._query_cache.items()
            if (now - ts).total_seconds() >= self._CACHE_TTL_SECONDS
        ]
        for k in expired_keys:
            del self._query_cache[k]

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

    @staticmethod
    def _node_from_dict(node_data: Dict[str, Any]) -> Any:
        """Create a lightweight dict-like object from a Neo4j node dict (e.g., from vector search)."""
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
        return _NodeProxy(node_data)

    def _score_candidates(
        self,
        nodes: list,
        buffer_units: List[Dict[str, Any]],
        query: str,
        entities: List[str],
        keywords: List[str],
        current_emotion: str = "neutral",
    ) -> List[Dict[str, Any]]:
        """
        Score and merge graph nodes + buffer units into a unified ranked list.

        Composite score:
        - When current_emotion is neutral:
          relevance×0.5 + importance×0.15 + recency×0.15 + access_frequency×0.1 + emotional_resonance×0.1
        - When current_emotion is non-neutral:
          relevance×0.4 + importance×0.15 + recency×0.15 + access_frequency×0.1 + emotional_resonance×0.2
        """
        # Determine if emotional resonance should be weighted higher
        emotional_weight = 0.2 if current_emotion != "neutral" else 0.1
        relevance_weight = 0.4 if current_emotion != "neutral" else 0.5

        candidates = []
        seen_ids: Set[str] = set()

        # Score graph nodes
        for node in nodes:
            if not node.id or node.id in seen_ids:
                continue

            # Filter out suppressed nodes
            if getattr(node, "status", "active") == "suppressed":
                continue

            seen_ids.add(node.id)

            relevance = self._text_relevance(
                f"{node.name} {node.summary} {node.content}", query, entities, keywords
            )
            importance = min(float(getattr(node, "importance", 5.0)) / 10.0, 1.0)
            recency = self._recency_score(getattr(node, "last_accessed", ""))
            access_freq = min(float(getattr(node, "access_count", 0)) / 100.0, 1.0)
            emotional = self._emotional_resonance(
                getattr(node, "emotional_tag", {}), current_emotion
            )

            score = (
                relevance * relevance_weight
                + importance * 0.15
                + recency * 0.15
                + access_freq * 0.1
                + emotional * emotional_weight
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
            relevance = self._text_relevance(message, query, entities, keywords)
            importance = min(float(unit.get("importance", 5.0)) / 10.0, 1.0)
            recency = self._recency_score(unit.get("timestamp", ""))
            # Buffer units don't have structured emotional_tag, use intensity directly
            emotional_intensity = float(unit.get("emotional_intensity", 0)) / 10.0

            score = (
                relevance * relevance_weight
                + importance * 0.15
                + recency * 0.15
                + 0.0 * 0.1
                + emotional_intensity * emotional_weight
            )
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
    def _text_relevance(text: str, query: str, entities: List[str], keywords: List[str]) -> float:
        """
        Enhanced keyword relevance score (0-1) with better matching.

        Uses multiple strategies:
        1. Exact entity/keyword match (high weight)
        2. Partial substring match (medium weight)
        3. Query term overlap (low weight)
        """
        if not text:
            return 0.0

        text_lower = text.lower()
        query_lower = query.lower()

        # Strategy 1: Exact entity/keyword match
        all_terms = entities + keywords
        if not all_terms:
            # Fallback: check if query appears in text
            if query_lower in text_lower:
                return 0.6
            return 0.1

        exact_hits = sum(1 for t in all_terms if t.lower() in text_lower)
        exact_score = min(exact_hits / len(all_terms), 1.0)

        # Strategy 2: Partial match (for multi-character terms)
        partial_hits = 0
        for term in all_terms:
            if len(term) >= 2:
                # Check if any 2+ character substring of term appears in text
                term_lower = term.lower()
                if any(term_lower[i:i+2] in text_lower for i in range(len(term_lower)-1)):
                    partial_hits += 0.5
        partial_score = min(partial_hits / len(all_terms), 1.0) if all_terms else 0.0

        # Strategy 3: Query term overlap (split query into words)
        query_words = [w for w in query_lower.split() if len(w) >= 2]
        if query_words:
            query_hits = sum(1 for w in query_words if w in text_lower)
            query_score = min(query_hits / len(query_words), 1.0)
        else:
            query_score = 0.0

        # Weighted combination: exact match is most important
        final_score = exact_score * 0.6 + partial_score * 0.2 + query_score * 0.2
        return final_score

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
    def _emotional_resonance(emotional_tag: Any, current_emotion: str) -> float:
        """
        Calculate emotional resonance between node emotion and current emotion (0-1).

        Rules:
        1. Emotion type matching: same emotion type → high resonance
        2. Emotion intensity: stronger node emotion → more noticeable resonance
        3. Special rule: when current emotion is negative, positive "encouraging" memories
           also get a boost (e.g., past successes when user is sad)

        Args:
            emotional_tag: Node's emotional_tag dict with "type" and "intensity"
            current_emotion: Current emotion from query or working memory

        Returns:
            Resonance score 0-1
        """
        if not isinstance(emotional_tag, dict):
            return 0.0

        node_emotion = emotional_tag.get("type", "neutral")
        intensity = float(emotional_tag.get("intensity", 0))

        # Normalize intensity to 0-1
        intensity_normalized = min(intensity / 10.0, 1.0)

        # If current emotion is neutral, just return intensity
        if current_emotion == "neutral":
            return intensity_normalized

        # Define emotion categories
        positive_emotions = {"joy", "surprise"}
        negative_emotions = {"sadness", "anger", "fear"}

        # Case 1: Exact emotion match → high resonance
        if node_emotion == current_emotion:
            return intensity_normalized * 1.0

        # Case 2: Same valence (both positive or both negative) → medium resonance
        current_is_positive = current_emotion in positive_emotions
        current_is_negative = current_emotion in negative_emotions
        node_is_positive = node_emotion in positive_emotions
        node_is_negative = node_emotion in negative_emotions

        if current_is_positive and node_is_positive:
            return intensity_normalized * 0.7
        if current_is_negative and node_is_negative:
            return intensity_normalized * 0.7

        # Case 3: Special rule - when user is negative, positive memories can be encouraging
        # Give a moderate boost to positive memories when user is sad/angry/fearful
        if current_is_negative and node_is_positive and intensity >= 5:
            return intensity_normalized * 0.5

        # Case 4: Opposite valence with no special rule → low resonance
        return intensity_normalized * 0.2

    async def _reconstruct_context(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> str:
        """Use LLM to synthesize top-K memory fragments into a factual context summary."""
        if not candidates:
            return "No relevant memories found."

        fragments = "\n".join(
            f"[{i+1}] {c['content']}" for i, c in enumerate(candidates)
        )
        # Pass query context to help LLM judge relevance, but instruct it NOT to answer
        user_prompt = (
            f"用户当前查询：{query}\n\n"
            f"记忆片段：\n{fragments}\n\n"
            "请将这些记忆片段合成为简洁的事实性上下文段落（50-100字）。\n"
            "只包含与查询相关且能提供新信息的事实。\n"
            "如果记忆片段都是关于当前正在讨论的话题（用户已经知道的内容），返回\"No relevant memories found.\"\n"
            "不要回答问题，不要提供建议。"
        )
        try:
            result = await call_llm(_RECONSTRUCT_SYSTEM, user_prompt, temperature=0.3)
            # If result is too long (>200 chars), it's probably not following instructions
            if len(result) > 200:
                logger.warning("LLM reconstruction output too long (%d chars), truncating", len(result))
                result = result[:200] + "..."
            return result
        except Exception as e:
            logger.error("Context reconstruction failed: %s", e)
            return "\n".join(c["content"] for c in candidates)

    async def _update_access_batch(self, node_ids: List[str], fuzzy_matches: Dict[str, str]) -> None:
        """Update access records and revive dormant nodes if retrieved."""
        tasks = []
        for nid in node_ids:
            if nid:
                fuzzy_term = fuzzy_matches.get(nid)
                tasks.append(self._update_and_revive(nid, fuzzy_term))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_and_revive(self, node_id: str, fuzzy_term: Optional[str] = None) -> None:
        """Update access for a node and revive it if dormant. Also handle spaced repetition review and alias learning."""
        try:
            # Get the node to check if it needs review
            node = await self.graph.get_node(node_id)
            if node:
                props = node.properties or {}
                needs_review = props.get("needs_review", False)

                # Update access (increments access_count, updates last_accessed, strengthens retrieval)
                await self.graph.update_access(node_id)

                # Alias learning: if found via fuzzy match, add the query term as an alias
                if fuzzy_term:
                    existing_aliases = props.get("aliases", [])
                    node_name_lower = node.name.lower()
                    fuzzy_term_lower = fuzzy_term.lower()

                    # Only add if:
                    # 1. Not already in aliases
                    # 2. Not the same as node name
                    # 3. Term is meaningful (length >= 2)
                    if (fuzzy_term not in existing_aliases and
                        fuzzy_term_lower != node_name_lower and
                        len(fuzzy_term) >= 2):
                        new_aliases = existing_aliases + [fuzzy_term]
                        await self.graph.update_node(node_id, {"properties": {**props, "aliases": new_aliases}})
                        logger.info(
                            "Alias learning: added '%s' to node %s (name=%s)",
                            fuzzy_term, node_id[:8], node.name
                        )

                # If this node was marked for review, clear the flag and update review history
                if needs_review:
                    review_count = props.get("review_count", 0) + 1
                    now = datetime.utcnow()

                    # Calculate next review date based on spaced repetition algorithm
                    INTERVALS = [1, 3, 7, 21]  # First 4 reviews
                    if review_count < len(INTERVALS):
                        interval_days = INTERVALS[review_count]
                    else:
                        # After 4th review, double the interval each time
                        interval_days = INTERVALS[-1] * (2 ** (review_count - len(INTERVALS) + 1))

                    next_review_date = now + timedelta(days=interval_days)

                    # Update node properties
                    updated_props = {
                        **props,
                        "needs_review": False,
                        "review_count": review_count,
                        "last_review_date": now.isoformat(),
                        "next_review_date": next_review_date.isoformat(),
                    }

                    await self.graph.update_node(node_id, {"properties": updated_props})
                    logger.info(
                        "Spaced repetition: reviewed node %s (review_count=%d, next_review in %d days)",
                        node_id[:8], review_count, interval_days
                    )

            # Revive if dormant
            revived = await self.graph.revive_if_dormant(node_id)
            if revived:
                logger.info("Revived dormant node %s via retrieval", node_id)
        except Exception as e:
            logger.warning("update_access/revive('%s') failed: %s", node_id, e)

    # ------------------------------------------------------------------
    # Retrieval fallback mechanism
    # ------------------------------------------------------------------

    async def _retrieve_with_fallback(
        self,
        query: str,
        entities: List[str],
        keywords: List[str],
        current_emotion: str,
        tenant_id: str,
        user_id: str,
        max_results: int,
        buffer_units: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        补偿检索策略：当正常检索失败时，尝试更宽松的检索条件。

        策略（按顺序尝试）：
        1. 降低score阈值（从0.25降到0.15）
        2. 扩大图遍历深度（从2跳到3跳）
        3. 放宽关键词匹配（使用更短的子串）

        Args:
            query: 查询字符串
            entities: 提取的实体列表
            keywords: 提取的关键词列表
            current_emotion: 当前情绪
            tenant_id: 租户ID
            user_id: 用户ID
            max_results: 最大结果数

        Returns:
            补偿检索的候选列表（confidence标记为0.5）
        """
        logger.info("Attempting fallback retrieval for query: %s", query)

        # Strategy 1: Lower score threshold
        node_candidates: Dict[str, Any] = {}

        # Re-run graph searches (same as before)
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
                    continue
                for node in result:
                    if node.id not in node_candidates:
                        node_candidates[node.id] = node

        # Strategy 2: Expand traversal depth to 3 hops
        if node_candidates:
            traversal_tasks = [
                self._traverse_deep(node_id) for node_id in list(node_candidates.keys())[:5]
            ]
            traversal_results = await asyncio.gather(*traversal_tasks, return_exceptions=True)
            for tresult in traversal_results:
                if isinstance(tresult, Exception):
                    continue
                for row in tresult:
                    node_id = row.get("to_id")
                    if node_id and node_id not in node_candidates:
                        node_candidates[node_id] = self._node_from_traversal(row)

        # Strategy 3: Relaxed keyword matching (shorter substrings)
        if not node_candidates:
            # Try matching with shorter substrings (2+ chars instead of full keywords)
            all_terms = entities + keywords
            short_terms = []
            for term in all_terms:
                if len(term) >= 4:
                    # Extract 2-3 char substrings
                    short_terms.append(term[:3])
                    short_terms.append(term[-3:])
                elif len(term) >= 2:
                    short_terms.append(term)

            for term in short_terms[:10]:  # Limit to avoid too many queries
                try:
                    fuzzy_results = await self.graph.find_nodes_fuzzy(term, tenant_id, user_id)
                    for node in fuzzy_results:
                        if node.id not in node_candidates:
                            node_candidates[node.id] = node
                except Exception as e:
                    logger.warning("Fallback fuzzy search failed for '%s': %s", term, e)

        if not node_candidates:
            logger.info("Fallback retrieval found no candidates")
            return []

        # Score candidates with LOWER threshold (0.15 instead of 0.25)
        # buffer_units already read by the caller (retrieve()); reuse to avoid duplicate DB read
        if buffer_units is None:
            buffer_units = []

        scored = self._score_candidates(
            list(node_candidates.values()), buffer_units, query, entities, keywords, current_emotion
        )

        # Apply lower threshold
        FALLBACK_THRESHOLD = 0.15
        scored = [c for c in scored if c["score"] >= FALLBACK_THRESHOLD]

        if not scored:
            logger.info("Fallback retrieval: no candidates passed lower threshold")
            return []

        # Mark all fallback results with lower confidence
        for candidate in scored[:max_results]:
            candidate["confidence"] = 0.5  # Lower confidence for fallback results

        logger.info("Fallback retrieval found %d candidates (confidence=0.5)", len(scored[:max_results]))
        return scored[:max_results]

    async def _traverse_deep(self, node_id: str) -> list:
        """Traverse relations with depth=3 for fallback retrieval."""
        try:
            return await self.graph.traverse_relations(node_id, max_depth=3)
        except Exception as e:
            logger.warning("Deep traversal failed for '%s': %s", node_id, e)
            return []
