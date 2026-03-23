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
- 利用上下文信息解析指代关系（如"他"、"那个"、"这件事"）

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
        使用多路径检索查询相关记忆。

        检索流程：
        1. 检查查询缓存（10秒内相同查询直接返回）
        2. 使用LLM从查询中提取实体线索和关键词（利用working_memory解析指代）
        3. 多路径并行图检索：
           - 路径A: 精确名称匹配 → find_nodes_by_name
           - 路径B: 别名匹配 → find_nodes_by_alias
           - 路径C: 模糊关键词匹配 → find_nodes_fuzzy
           - 路径D: 休眠节点搜索（用于唤醒）
           - 路径E: 向量语义搜索（针对每个实体+query整体）
        4. 关系遍历：从匹配节点出发遍历1-2跳关系
        5. Buffer检索：获取最近未归档的记忆单元
        6. 去重并综合打分所有候选
        7. 按最小分数阈值过滤
        8. LLM重构top-K片段为连贯上下文
        9. 更新被检索节点的访问记录

        综合评分公式：
        - 中性情绪: relevance×0.5 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.1
        - 非中性情绪: relevance×0.4 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.2

        Args:
            query: 自然语言查询字符串
            tenant_id: 租户标识
            user_id: 用户标识
            working_memory: 可选的会话上下文，用于评分和指代解析
            max_results: 最多返回的记忆片段数
            session_id: 可选的会话标识，用于缓存

        Returns:
            包含以下键的字典：
                - "context": str — 可直接注入LLM的自然语言上下文
                - "memories": list of {"id", "content", "relevance", "confidence"}
        """
        # 步骤1: 检查查询缓存
        cache_key = None
        if session_id:
            query_hash = hashlib.md5(query.encode()).hexdigest()
            cache_key = (session_id, query_hash)
            if cache_key in self._query_cache:
                cached_result, cached_time = self._query_cache[cache_key]
                age = (datetime.utcnow() - cached_time).total_seconds()
                if age < self._CACHE_TTL_SECONDS:
                    logger.info("Returning cached result for session=%s query_hash=%s", session_id, query_hash[:8])
                    return cached_result

        # 步骤2: 提取搜索线索（传入working_memory用于指代解析）
        clues = await self._extract_clues(query, working_memory)
        if not isinstance(clues, dict):
            logger.warning('_extract_clues returned %s instead of dict, using fallback', type(clues).__name__)
            clues = {"entities": [], "keywords": [query], "time_hint": "none", "query_intent": query, "query_emotion": "neutral"}

        entities = clues.get("entities", [])
        keywords = clues.get("keywords", [])
        query_emotion = clues.get("query_emotion", "neutral")

        # 确定当前情绪（用于情感共鸣评分）
        current_emotion = query_emotion
        if current_emotion == "neutral" and working_memory:
            baseline = working_memory.get("emotional_baseline", "neutral")
            if baseline == "positive":
                current_emotion = "joy"
            elif baseline == "negative":
                current_emotion = "sadness"

        # 如果没有提取到有意义的线索，返回空结果
        if not entities and not keywords:
            logger.info("No meaningful clues extracted from query: %s", query)
            result = {"context": "No relevant memories found.", "memories": []}
            if session_id and cache_key:
                self._query_cache[cache_key] = (result, datetime.utcnow())
            return result

        # 步骤3-5: 多路径图检索（并行执行）
        node_candidates: Dict[str, Any] = {}
        fuzzy_matches: Dict[str, str] = {}

        graph_tasks = []
        task_metadata = []

        # 为每个实体执行精确名称和别名搜索
        for entity in entities:
            graph_tasks.append(self._search_by_name(entity, tenant_id, user_id))
            task_metadata.append(("name", entity))
            graph_tasks.append(self._search_by_alias(entity, tenant_id, user_id))
            task_metadata.append(("alias", entity))

        # 为每个关键词执行模糊搜索
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
                        if search_method == "fuzzy":
                            fuzzy_matches[node.id] = search_term

        # 路径E: 向量语义搜索（针对实体+query，与图搜索并行）
        vector_candidates = {}  # 向量召回的节点
        similarity_scores = {}  # 保存相似度得分
        try:
            from server.engine.embedding_client import get_embedding
            import numpy as np

            # E1: 为每个实体做向量搜索（更精准）
            vector_tasks = []
            for entity in entities[:3]:  # 限制前3个实体避免过多查询
                vector_tasks.append(self._search_by_vector(entity, tenant_id, user_id))

            # E2: 对整个query也做向量搜索（捕获语义相似）
            vector_tasks.append(self._search_by_vector(query, tenant_id, user_id))

            if vector_tasks:
                vector_results = await asyncio.gather(*vector_tasks, return_exceptions=True)
                for vresult in vector_results:
                    if isinstance(vresult, Exception):
                        continue
                    for node, score in vresult:
                        if node.id not in vector_candidates:
                            vector_candidates[node.id] = node
                            similarity_scores[node.id] = score
                        else:
                            # 保留最高相似度得分
                            similarity_scores[node.id] = max(similarity_scores.get(node.id, 0), score)
        except ImportError:
            logger.debug("Embedding client not available, skipping vector search")

        # 步骤4: 关系遍历（从匹配节点出发，优先遍历重要节点）
        # 图搜索召回：全部保留，按importance排序
        graph_sorted = sorted(
            node_candidates.items(),
            key=lambda x: getattr(x[1], 'importance', 5.0),
            reverse=True
        )

        # 向量召回：按相似度优先，importance次之
        vector_sorted = sorted(
            vector_candidates.items(),
            key=lambda x: (similarity_scores.get(x[0], 0.0), getattr(x[1], 'importance', 5.0)),
            reverse=True
        )

        # 合并：图搜索全部 + 向量top5（去重）
        sorted_candidates = graph_sorted[:]
        seen_ids = {nid for nid, _ in graph_sorted}
        for nid, node in vector_sorted[:5]:
            if nid not in seen_ids:
                sorted_candidates.append((nid, node))
                seen_ids.add(nid)
        traversal_tasks = [
            self._traverse(node_id) for node_id, _ in sorted_candidates[:]
        ]

        # 收集关系信息用于上下文重构
        relations = []
        if traversal_tasks:
            traversal_results = await asyncio.gather(*traversal_tasks, return_exceptions=True)
            for tresult in traversal_results:
                if isinstance(tresult, Exception):
                    continue
                for row in tresult:
                    node_id = row.get("to_id")
                    if node_id and node_id not in node_candidates:
                        node_candidates[node_id] = self._node_from_traversal(row)

                    # 收集关系信息（包含description和properties）
                    from_id = row.get("from_id")
                    rel_type = row.get("rel_type", "")
                    rel_props = row.get("rel_props", {})
                    if from_id and node_id and rel_type:
                        relations.append({
                            "from_id": from_id,
                            "to_id": node_id,
                            "type": rel_type,
                            "description": rel_props.get("description", ""),  # 独立字段
                            "properties": rel_props  # 完整属性
                        })

        # 步骤5: Buffer检索（短期记忆）
        buffer_units = []
        try:
            buffer_units = self.buffer.read_recent(tenant_id, user_id, limit=20)

            # Buffer向量搜索（numpy暴力匹配）
            try:
                from server.engine.embedding_client import get_embedding
                import numpy as np

                query_embedding = await get_embedding(query, type_="query")
                if any(v != 0.0 for v in query_embedding[:10]):
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
                                        for bu in buffer_units:
                                            if bu.get("id") == buf_id:
                                                bu["_vector_score"] = score
                                                break
            except Exception as e:
                logger.warning("Buffer vector search failed: %s", e)
        except Exception as e:
            logger.warning("Buffer retrieval failed: %s", e)

        # 步骤6: 综合评分和排序
        scored = self._score_candidates(
            list(node_candidates.values()), buffer_units, query, entities, keywords, current_emotion
        )

        # 步骤7: 按最小分数阈值过滤
        MIN_SCORE_THRESHOLD = 0.25
        scored = [c for c in scored if c["score"] >= MIN_SCORE_THRESHOLD]

        # 如果没有候选通过阈值，尝试降低阈值或搜索休眠节点
        if not scored:
            logger.info("No candidates passed threshold, trying fallback strategies")

            # 策略1: 降低阈值重试
            MIN_SCORE_THRESHOLD = 0.15
            scored = self._score_candidates(
                list(node_candidates.values()), buffer_units, query, entities, keywords, current_emotion
            )
            scored = [c for c in scored if c["score"] >= MIN_SCORE_THRESHOLD]
            for c in scored:
                c["confidence"] = 0.5

            # 策略2: 如果仍然没有结果，尝试唤醒休眠节点
            if not scored:
                all_search_terms = entities + keywords
                if all_search_terms:
                    try:
                        dormant_matches = await self.graph.find_dormant_nodes(
                            all_search_terms, tenant_id, user_id, limit=5)
                        if dormant_matches:
                            logger.info("Found %d dormant nodes, attempting revival", len(dormant_matches))
                            # 对休眠节点评分
                            dormant_scored = self._score_candidates(
                                dormant_matches, [], query, entities, keywords, current_emotion
                            )
                            scored = [c for c in dormant_scored if c["score"] >= 0.15]
                            for c in scored:
                                c["confidence"] = 0.6  # 休眠节点置信度稍高
                    except Exception as e:
                        logger.warning("Dormant node search failed: %s", e)

        if not scored:
            result = {"context": "No relevant memories found.", "memories": []}
            if session_id and cache_key:
                self._query_cache[cache_key] = (result, datetime.utcnow())
            return result

        top_k = scored[:max_results]

        # 步骤8: LLM重构为连贯上下文（传入关系信息）
        context = await self._reconstruct_context(query, top_k, relations)

        # 步骤9: 批量更新访问记录
        node_ids_to_update = [c["id"] for c in top_k if c.get("source") == "graph"]
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

        # 缓存结果
        if session_id and cache_key:
            self._query_cache[cache_key] = (result, datetime.utcnow())
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

    async def _extract_clues(
        self, query: str, working_memory: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        使用LLM从查询中提取实体名称和关键词。

        Args:
            query: 用户查询
            working_memory: 工作记忆，包含会话上下文用于解析指代关系

        Returns:
            包含 entities, keywords, time_hint, query_intent, query_emotion 的字典
        """
        try:
            # 构建上下文信息，帮助LLM理解指代关系
            context_parts = []
            if working_memory:
                # 本session最近的消息，用于解析"他"、"那个"等指代
                session_msgs = working_memory.get("session_messages", [])
                if session_msgs:
                    recent = " | ".join(session_msgs[-3:])
                    context_parts.append(f"最近对话: {recent}")

                # 用户画像和目标，帮助理解查询意图
                raw = working_memory.get("raw", {})
                if raw.get("user_profile"):
                    context_parts.append(f"用户画像: {raw['user_profile']}")
                if working_memory.get("user_goals"):
                    goals = "; ".join(working_memory["user_goals"][:3])
                    context_parts.append(f"当前目标: {goals}")

            context_block = ""
            if context_parts:
                context_block = "\n\n上下文（用于解析指代）:\n" + "\n".join(context_parts)

            user_prompt = f'Query:\n"""\n{query}\n"""{context_block}'
            return await call_llm_json(_EXTRACT_CLUES_SYSTEM, user_prompt)
        except Exception as e:
            logger.warning("Clue extraction failed: %s", e)
            return {"entities": [], "keywords": [query], "time_hint": "none", "query_intent": query}

    async def _search_by_name(self, name: str, tenant_id: str, user_id: str) -> list:
        """通过精确名称搜索节点"""
        try:
            return await self.graph.find_nodes_by_name(name, tenant_id, user_id)
        except Exception as e:
            logger.warning("find_nodes_by_name('%s') failed: %s", name, e)
            return []

    async def _search_by_alias(self, alias: str, tenant_id: str, user_id: str) -> list:
        """通过别名搜索节点"""
        try:
            return await self.graph.find_nodes_by_alias(alias, tenant_id, user_id)
        except Exception as e:
            logger.warning("find_nodes_by_alias('%s') failed: %s", alias, e)
            return []

    async def _search_fuzzy(self, keyword: str, tenant_id: str, user_id: str) -> list:
        """通过模糊关键词搜索节点"""
        try:
            return await self.graph.find_nodes_fuzzy(keyword, tenant_id, user_id)
        except Exception as e:
            logger.warning("find_nodes_fuzzy('%s') failed: %s", keyword, e)
            return []

    async def _search_by_vector(self, text: str, tenant_id: str, user_id: str) -> list:
        """
        通过向量语义搜索节点。

        Args:
            text: 要搜索的文本（实体名或query）
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            匹配的(节点, 相似度得分)元组列表
        """
        try:
            from server.engine.embedding_client import get_embedding
            import numpy as np

            embedding = await get_embedding(text, type_="query")
            # 检查是否为零向量（使用范数判断）
            if np.linalg.norm(embedding) > 0:
                vector_hits = await self.graph.vector_search(embedding, top_k=5, min_score=0.5)
                results = []
                for hit in vector_hits:
                    node_data = hit["node"]
                    if node_data.get("id"):
                        node = self._node_from_dict(node_data)
                        results.append((node, hit["score"]))
                        logger.debug("Vector search '%s' found: %s (score=%.2f)",
                                   text[:20], node_data.get("name"), hit["score"])
                return results
            return []
        except Exception as e:
            logger.warning("Vector search for '%s' failed: %s", text, e)
            return []

    async def _traverse(self, node_id: str) -> list:
        """
        从节点出发遍历关系图。

        Args:
            node_id: 起始节点ID

        Returns:
            遍历到的关系列表
        """
        try:
            return await self.graph.traverse_relations(node_id, max_depth=2)
        except Exception as e:
            logger.warning("traverse_relations('%s') failed: %s", node_id, e)
            return []

    @staticmethod
    def _node_from_traversal(row: Dict[str, Any]) -> Any:
        """从遍历结果行创建轻量级节点代理对象"""
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
        """从Neo4j节点字典创建轻量级节点代理对象（用于向量搜索结果）"""
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
        对图节点和buffer单元进行综合评分并合并为统一排序列表。

        综合评分公式：
        - 中性情绪时：relevance×0.5 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.1
        - 非中性情绪时：relevance×0.4 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.2

        Args:
            nodes: 图节点列表
            buffer_units: buffer记忆单元列表
            query: 查询字符串
            entities: 提取的实体列表
            keywords: 提取的关键词列表
            current_emotion: 当前情绪状态

        Returns:
            按分数降序排列的候选列表
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
        计算文本相关性评分（0-1）。

        使用多种匹配策略：
        1. 精确实体/关键词匹配（高权重）
        2. 部分子串匹配（中权重）
        3. 查询词重叠（低权重）

        Args:
            text: 待评分文本
            query: 原始查询
            entities: 提取的实体列表
            keywords: 提取的关键词列表

        Returns:
            相关性评分 0-1
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
        """
        将时间戳转换为0-1的新近度评分（1=刚刚，30天内线性衰减）。

        Args:
            timestamp_str: ISO格式时间戳字符串

        Returns:
            新近度评分 0-1
        """
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
        计算节点情感与当前情感的共鸣度（0-1）。

        规则：
        1. 情感类型匹配：相同情感类型 → 高共鸣
        2. 情感强度：节点情感越强 → 共鸣越明显
        3. 特殊规则：当前情感为负面时，正面"鼓励性"记忆也会获得加成
           （例如用户悲伤时，过去的成功记忆）

        Args:
            emotional_tag: 节点的emotional_tag字典，包含"type"和"intensity"
            current_emotion: 当前情感（从查询或工作记忆获取）

        Returns:
            共鸣度评分 0-1
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
        self, query: str, candidates: List[Dict[str, Any]], relations: List[Dict[str, str]] = None
    ) -> str:
        """
        使用LLM将top-K记忆片段合成为事实性上下文摘要。

        Args:
            query: 用户查询
            candidates: 候选记忆列表
            relations: 节点间的关系列表

        Returns:
            合成的上下文字符串
        """
        if not candidates:
            return "No relevant memories found."

        # 构建节点ID到内容的映射
        id_to_content = {c["id"]: c["content"] for c in candidates}

        fragments = "\n".join(
            f"[{i+1}] {c['content']}" for i, c in enumerate(candidates)
        )

        # 构建关系描述
        relation_text = ""
        if relations:
            rel_lines = []
            for rel in relations[:10]:  # 限制关系数量
                from_id = rel.get("from_id")
                to_id = rel.get("to_id")
                rel_type = rel.get("type", "关联")
                rel_desc = rel.get("description", "")
                rel_props = rel.get("properties", {})

                # 只包含在候选中的关系
                if from_id in id_to_content and to_id in id_to_content:
                    from_name = id_to_content[from_id].split(":")[0]
                    to_name = id_to_content[to_id].split(":")[0]

                    # 构建关系描述
                    if rel_desc:
                        # 优先使用 description 字段
                        rel_line = f"{from_name} --{rel_type}--> {to_name}: {rel_desc}"
                    else:
                        rel_line = f"{from_name} --{rel_type}--> {to_name}"

                    # 补充时间等关键属性
                    extra_info = []
                    if rel_props.get("valid_from"):
                        extra_info.append(f"始于 {rel_props['valid_from'][:10]}")
                    if rel_props.get("confidence") and rel_props["confidence"] < 0.8:
                        extra_info.append(f"置信度 {rel_props['confidence']:.1f}")

                    if extra_info:
                        rel_line += f" ({', '.join(extra_info)})"

                    rel_lines.append(rel_line)

            if rel_lines:
                relation_text = "\n\n关系网络：\n" + "\n".join(rel_lines)

        user_prompt = (
            f"用户当前查询：{query}\n\n"
            f"记忆片段：\n{fragments}{relation_text}\n\n"
            "请将这些记忆片段合成为简洁的事实性上下文段落（50-100字）。\n"
            "利用关系网络理解节点间的联系。\n"
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
        """
        批量更新访问记录并唤醒休眠节点。

        Args:
            node_ids: 要更新的节点ID列表
            fuzzy_matches: 模糊匹配映射（用于别名学习）
        """
        tasks = []
        for nid in node_ids:
            if nid:
                fuzzy_term = fuzzy_matches.get(nid)
                tasks.append(self._update_and_revive(nid, fuzzy_term))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_and_revive(self, node_id: str, fuzzy_term: Optional[str] = None) -> None:
        """
        更新节点访问记录并唤醒休眠节点。同时处理间隔重复复习和别名学习。

        Args:
            node_id: 节点ID
            fuzzy_term: 可选的模糊匹配词（用于别名学习）
        """
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
