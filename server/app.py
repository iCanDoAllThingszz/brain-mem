import os
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.storage.graph import GraphStore
from server.storage.tag_dict import TagDict
from server.storage.buffer import EncoderBuffer
from server.engine.perceiver import Perceiver
from server.engine.evaluator import Evaluator
from server.engine.encoder import Encoder
from server.engine.retriever import Retriever
from server.engine.consolidator import Consolidator
from server.engine.working_memory import WorkingMemory, _goal_label
from server.engine.prospective_checker import ProspectiveChecker
from server.engine.profile_updater import ProfileUpdater
from server.engine.llm_client import configure as configure_llm
from server.storage.user_profile import UserProfileStore
from server.activity_log import log_event, read_recent

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("brain_memory")

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
SEED_TAGS = [
    "人物", "组织", "地点", "物品", "作品", "概念", "技能",
    "观点", "情感", "事件", "决策", "里程碑", "计划", "方法论", "教训", "洞察",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Brain Memory Service...")

    # Load config
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

    # Configure LLM
    llm_config = config.get("llm", {})
    configure_llm(
        base_url=llm_config.get("base_url"),
        model=llm_config.get("model"),
        api_key=llm_config.get("api_key") or None,
        temperature=llm_config.get("temperature"),
    )

    # Storage config
    storage_config = config.get("storage", {})
    neo4j_config = storage_config.get("neo4j", {})

    graph = GraphStore(
        uri=neo4j_config.get("uri", "bolt://localhost:7687"),
        user=neo4j_config.get("user", "neo4j"),
        password=neo4j_config.get("password", "laolao2026"),
    )
    await graph.connect()

    os.makedirs("./data", exist_ok=True)
    tag_dict = TagDict(path=storage_config.get("tag_dict", {}).get("path", "./data/tag_dict.json"))
    buffer = EncoderBuffer(db_path=storage_config.get("buffer", {}).get("path", "./data/buffer.db"))
    profile_store = UserProfileStore(db_path=storage_config.get("user_profiles", {}).get("path", "./data/user_profiles.db"))

    for tag in SEED_TAGS:
        if not tag_dict.get_tag(tag):
            tag_dict.add_tag(tag)

    app.state.graph = graph
    app.state.tag_dict = tag_dict
    app.state.buffer = buffer
    app.state.perceiver = Perceiver()
    app.state.evaluator = Evaluator()
    app.state.encoder = Encoder(graph, tag_dict, buffer)
    app.state.retriever = Retriever(graph, buffer)
    app.state.consolidator = Consolidator(graph, tag_dict, buffer)
    app.state.working_memory = WorkingMemory(graph, buffer, profile_store)
    app.state.prospective_checker = ProspectiveChecker(graph)
    app.state.profile_updater = ProfileUpdater(profile_store)

    # Ensure vector index exists
    try:
        await graph.ensure_vector_index()
        logger.info("Vector index ready")
    except Exception as e:
        logger.warning("Failed to create vector index: %s", e)

    logger.info("All components initialized.")
    yield

    logger.info("Shutting down Brain Memory Service...")
    await graph.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Brain Memory Service", version="0.1.0", lifespan=lifespan)

# Session message counters for intermediate summaries
_session_msg_counts: Dict[str, int] = {}
_SESSION_SUMMARY_INTERVAL = 5  # Generate summary every N encoded QA rounds


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class BaseRequest(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str


class SessionStartRequest(BaseRequest):
    user_profile: Optional[dict] = None
    agent_context: Optional[dict] = None


class BeforeQueryRequest(BaseRequest):
    query: str
    recent_messages: Optional[list] = None


class AfterResponseRequest(BaseRequest):
    user_message: str
    assistant_response: str


class SessionEndRequest(BaseRequest):
    conversation_history: list = []


class ConsolidateRequest(BaseModel):
    tenant_id: str
    user_id: str


class CheckProspectiveRequest(BaseModel):
    tenant_id: str
    user_id: str


def ok(data: Any) -> dict:
    return {"code": 0, "message": "success", "data": data}


def err(code: int, message: str) -> dict:
    return {"code": code, "message": message, "data": None}


# ---------------------------------------------------------------------------
# Exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500, content=err(500, str(exc)))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/logs")
async def get_logs(n: int = 30):
    """View recent activity logs."""
    return {"logs": read_recent(n)}


@app.post("/hooks/session-start")
async def session_start(req: SessionStartRequest, request: Request):
    logger.info("session-start | tenant=%s user=%s session=%s", req.tenant_id, req.user_id, req.session_id)
    try:
        wm = request.app.state.working_memory
        prospective_checker = request.app.state.prospective_checker

        # Check for time-based prospective memory triggers
        triggered_reminders = await prospective_checker.check_time_triggers(
            req.tenant_id, req.user_id
        )

        result = await wm.load(
            req.tenant_id, req.user_id, req.session_id,
            req.user_profile, req.agent_context,
        )

        # Add triggered reminders to pending_reminders
        pending_reminders = result.get("pending_reminders", [])
        for reminder in triggered_reminders:
            pending_reminders.append(reminder['action'])

        ctx = result.get("context", "")
        log_event("hook_session_start", f"Loaded WM for session {req.session_id[:8]}", {
            "goals": result.get("user_goals", []),
            "reminders": pending_reminders,
            "emotional_baseline": result.get("emotional_baseline", "neutral"),
            "context": ctx[:200] if ctx else "",
            "triggered_time_reminders": len(triggered_reminders),
        })
        return ok({"context": ctx, "pending_reminders": pending_reminders})
    except Exception as exc:
        logger.exception("session-start failed: %s", exc)
        return JSONResponse(status_code=500, content=err(500, str(exc)))


@app.post("/hooks/before-query")
async def before_query(req: BeforeQueryRequest, request: Request):
    logger.info("before-query | session=%s query=%.80s", req.session_id, req.query)
    try:
        wm_store = request.app.state.working_memory
        retriever = request.app.state.retriever
        prospective_checker = request.app.state.prospective_checker

        # Check for event-based prospective memory triggers
        triggered_reminders = await prospective_checker.check_event_triggers(
            req.tenant_id, req.user_id, req.query
        )

        wm = wm_store.get(req.session_id)
        result = await retriever.retrieve(
            req.query, req.tenant_id, req.user_id, wm, max_results=10, session_id=req.session_id
        )
        memories = result.get("memories", [])

        # Inject triggered reminders into context
        context = result.get("context", "")
        if triggered_reminders:
            reminder_text = "\n\n【提醒事项】\n" + "\n".join(
                f"- {r['action']}" for r in triggered_reminders
            )
            context = context + reminder_text
            log_event("prospective_trigger", f"Event triggers activated: {len(triggered_reminders)}", {
                "triggers": [r['action'] for r in triggered_reminders],
            })

        log_event("hook_before_query", f"Query: {req.query[:80]}", {
            "memories_found": len(memories),
            "top_memories": [f"{m.get('content', '')[:60]} (score={m.get('relevance', 0):.2f})" for m in memories[:3]],
            "triggered_reminders": len(triggered_reminders),
        })
        return ok({"context": context})
    except Exception as exc:
        logger.exception("before-query failed: %s", exc)
        return JSONResponse(status_code=500, content=err(500, str(exc)))


# --- background task helpers ---

_POSITIVE_EMOTIONS = {"joy", "surprise"}
_NEGATIVE_EMOTIONS = {"sadness", "anger", "fear"}


def _update_emotional_baseline(
    wm_store: WorkingMemory, session_id: str, evaluation: dict
) -> None:
    """Update the in-memory WM emotional baseline from the current message's emotion.

    Only updates when emotional_intensity >= 3 to avoid noise from low-signal messages.
    Intensity < 3 leaves the baseline unchanged (emotions persist until a new signal arrives).
    """
    emotion_type = evaluation.get("emotion_type", "neutral")
    intensity = float(evaluation.get("emotional_intensity", 0))
    if intensity < 3 or emotion_type == "neutral":
        return
    if emotion_type in _POSITIVE_EMOTIONS:
        new_baseline = "positive"
    elif emotion_type in _NEGATIVE_EMOTIONS:
        new_baseline = "negative"
    else:
        return
    wm_store.update(session_id, {"emotional_baseline": new_baseline})


async def _process_after_response(
    user_message: str,
    assistant_response: str,
    tenant_id: str, user_id: str, session_id: str,
    perceiver: Perceiver, evaluator: Evaluator, encoder: Encoder,
    wm_store: WorkingMemory,
    profile_updater: ProfileUpdater,
):
    try:
        wm = wm_store.get(session_id)

        # 1.丘脑分类
        perception = await perceiver.classify(user_message, wm, assistant_response=assistant_response)
        msg_type = perception.get("type")
        rewrite = perception.get("rewrite")
        logger.info("after-response perceiver type=%s rewrite=%s session=%s",
                     msg_type, bool(rewrite), session_id)

        log_event("perceiver", f"[{msg_type}] {user_message[:60]}", {
            "type": msg_type,
            "category": perception.get("category", "cognition"),
            "target_entities": perception.get("target_entities"),
            "reason": perception.get("reason", ""),
            "rewrite": rewrite[:100] if rewrite else None,
        })

        if msg_type == "informative":
            # Use rewrite for evaluation and encoding if available
            memory_input = rewrite or user_message
            category = perception.get("category", "cognition")

            # log / reconsolidation / prospective / forget bypass the evaluator:
            # logs are always worth recording as-is, the others have explicit user intent
            if category in ("log", "reconsolidation", "prospective", "forget"):
                evaluation = {
                    "task_relevance": 5,
                    "emotional_intensity": 0,
                    "emotion_type": "neutral",
                    "novelty": 5,
                    "encode_decision": True,
                    "encode_priority": "high" if category in ("prospective", "forget") else "low",
                    "reason": f"{category} message, auto-encode",
                    "category": category,
                    "target_entities": perception.get("target_entities"),
                    "correction_type": perception.get("correction_type"),
                    "trigger_type": perception.get("trigger_type"),
                    "trigger_value": perception.get("trigger_value"),
                    "action": perception.get("action"),
                }
                log_event("evaluator", f"[auto-pass] category={category}", {
                    "encode_decision": True,
                    "reason": f"{category} auto-encode",
                })
            else:
                # 2.前额叶皮层+杏仁核打分
                evaluation = await evaluator.evaluate(memory_input, wm)
                log_event("evaluator", f"relevance={evaluation.get('task_relevance')} emotion={evaluation.get('emotional_intensity')} novelty={evaluation.get('novelty')}", {
                    "encode_decision": evaluation.get("encode_decision"),
                    "encode_priority": evaluation.get("encode_priority"),
                    "reason": evaluation.get("reason", ""),
                })

            # Update emotional baseline in WM based on this message's emotion.
            # Runs for all informative messages (not just encoded ones) so the
            # perceiver always sees the user's current emotional state.
            if wm is not None:
                _update_emotional_baseline(wm_store, session_id, evaluation)

            if evaluation.get("encode_decision"):
                # Pass category, target_entities, correction_type, and prospective fields to encoder
                evaluation["category"] = perception.get("category", "cognition")
                evaluation["target_entities"] = perception.get("target_entities")
                evaluation["correction_type"] = perception.get("correction_type")
                evaluation["trigger_type"] = perception.get("trigger_type")
                evaluation["trigger_value"] = perception.get("trigger_value")
                evaluation["action"] = perception.get("action")

                # Encode the rewrite (higher density) but store original message too
                result = await encoder.encode_message(
                    memory_input, evaluation, tenant_id, user_id, session_id, wm
                )
                if result.get("skipped"):
                    log_event("encoder", f"Skipped: {result.get('reason')} | {user_message[:40]}", {
                        "reason": result.get("reason"),
                    })
                else:
                    result_type = result.get("type", "memory")
                    if result_type == "memory":
                        entities = result.get("entities", [])
                        entity_details = [
                            f"{e.get('name')}({e.get('action','?')})"
                            for e in entities[:5]
                        ]
                        log_event("encoder", f"Encoded: {user_message[:60]}", {
                            "importance": result.get("importance"),
                            "entities": entity_details,
                            "relations": len(result.get("relations", [])),
                        })
                    elif result_type == "log":
                        log_event("encoder", f"Log: {user_message[:60]}", {
                            "category": result.get("category"),
                            "target_entities": result.get("target_entities"),
                            "file_path": result.get("file_path"),
                        })
                    elif result_type == "reconsolidation":
                        log_event("encoder", f"Reconsolidation: {user_message[:60]}", {
                            "correction_type": result.get("correction_type"),
                            "nodes_updated": result.get("nodes_updated"),
                        })
                    elif result_type == "prospective":
                        log_event("encoder", f"Prospective: {user_message[:60]}", {
                            "trigger_type": result.get("trigger_type"),
                            "trigger_value": result.get("trigger_value"),
                            "action": result.get("action"),
                        })
                    elif result_type == "forget":
                        log_event("encoder", f"Forget: {user_message[:60]}", {
                            "target_entities": result.get("target_entities"),
                            "nodes_suppressed": result.get("nodes_suppressed"),
                        })
                    else:
                        log_event("encoder", f"Encoded ({result_type}): {user_message[:60]}", {})

                    # Append encoded message to working memory so later messages in this
                    # session can reference what was already discussed and encoded
                    if wm is not None:
                        session_msgs = list(wm.get("session_messages", []))
                        session_msgs.append(memory_input)
                        wm_store.update(session_id, {"session_messages": session_msgs[-10:]})

                    # Incrementally update persistent user profile and goals,
                    # then refresh the in-memory WM cache so this session sees
                    # the latest user_profile and user_goals immediately
                    updated = await profile_updater.update(tenant_id, user_id, memory_input)
                    if updated and wm is not None:
                        wm_store.update(session_id, {
                            "user_goals": [_goal_label(g) for g in updated["goals"]],
                            "raw": {
                                "user_profile": updated["profile"],
                                "active_goals": updated["goals"],
                            },
                        })

                    # Count encoded QA rounds and trigger intermediate summary every N rounds
                    global _session_msg_counts
                    _session_msg_counts[session_id] = _session_msg_counts.get(session_id, 0) + 1
                    encoded_count = _session_msg_counts[session_id]
                    if encoded_count % _SESSION_SUMMARY_INTERVAL == 0:
                        logger.info("Triggering intermediate summary for session %s (encoded_count=%d)", session_id, encoded_count)
                        try:
                            await encoder.generate_session_summary(tenant_id, user_id, session_id)
                            log_event("intermediate_summary", f"Generated intermediate summary for session {session_id[:8]}", {
                                "session_id": session_id,
                                "encoded_count": encoded_count,
                            })
                        except Exception as e:
                            logger.warning("Intermediate summary generation failed: %s", e)
                logger.info("after-response encoded | session=%s", session_id)
    except Exception as exc:
        logger.exception("after-response background task failed: %s", exc)


async def _process_session_end(
    tenant_id: str, user_id: str, session_id: str,
    encoder: Encoder, wm_store: WorkingMemory,
):
    try:
        # Summary is now generated from buffer's encoded memory units,
        # no need for conversation_history parameter.
        await encoder.generate_session_summary(tenant_id, user_id, session_id)
        wm_store.destroy(session_id)

        # Clean up session message counter
        global _session_msg_counts
        if session_id in _session_msg_counts:
            del _session_msg_counts[session_id]

        logger.info("session-end completed | session=%s", session_id)
    except Exception as exc:
        logger.exception("session-end background task failed: %s", exc)


async def _process_consolidate(
    tenant_id: str, user_id: str,
    consolidator: Consolidator,
):
    try:
        result = await consolidator.consolidate(tenant_id, user_id)
        log_event("consolidation", f"nodes_created={result.get('nodes_created', 0)} relations={result.get('relations_created', 0)}", {
            "nodes_created": result.get("nodes_created", 0),
            "nodes_updated": result.get("nodes_updated", 0),
            "nodes_merged": result.get("nodes_merged", 0),
            "relations_created": result.get("relations_created", 0),
            "patterns": result.get("patterns_discovered", [])[:3],
            "conflicts": result.get("conflicts_found", [])[:3],
        })
        logger.info("consolidate completed | tenant=%s user=%s result=%s", tenant_id, user_id, result)
    except Exception as exc:
        logger.exception("consolidate background task failed: %s", exc)


@app.post("/hooks/after-response")
async def after_response(req: AfterResponseRequest, request: Request, background_tasks: BackgroundTasks):
    logger.info("after-response | session=%s", req.session_id)
    background_tasks.add_task(
        _process_after_response,
        req.user_message, req.assistant_response,
        req.tenant_id, req.user_id, req.session_id,
        request.app.state.perceiver,
        request.app.state.evaluator,
        request.app.state.encoder,
        request.app.state.working_memory,
        request.app.state.profile_updater,
    )
    return ok({"status": "accepted"})


@app.post("/hooks/session-end")
async def session_end(req: SessionEndRequest, request: Request, background_tasks: BackgroundTasks):
    logger.info("session-end | session=%s", req.session_id)
    background_tasks.add_task(
        _process_session_end,
        req.tenant_id, req.user_id, req.session_id,
        request.app.state.encoder,
        request.app.state.working_memory,
    )
    return ok({"status": "accepted"})


@app.post("/hooks/consolidate")
async def consolidate(req: ConsolidateRequest, request: Request, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    logger.info("consolidate | tenant=%s user=%s task_id=%s", req.tenant_id, req.user_id, task_id)
    background_tasks.add_task(
        _process_consolidate,
        req.tenant_id, req.user_id,
        request.app.state.consolidator,
    )
    return ok({"status": "accepted", "task_id": task_id})


@app.post("/hooks/check-prospective")
async def check_prospective(req: CheckProspectiveRequest, request: Request):
    """
    Check for time-based prospective memory triggers.
    This endpoint can be called by external cron jobs or on session-start.
    """
    logger.info("check-prospective | tenant=%s user=%s", req.tenant_id, req.user_id)
    try:
        prospective_checker = request.app.state.prospective_checker

        # Check for time-based triggers
        triggered_reminders = await prospective_checker.check_time_triggers(
            req.tenant_id, req.user_id
        )

        if triggered_reminders:
            log_event("prospective_trigger", f"Time triggers activated: {len(triggered_reminders)}", {
                "triggers": [r['action'] for r in triggered_reminders],
            })

        return ok({
            "triggered_count": len(triggered_reminders),
            "reminders": triggered_reminders,
        })
    except Exception as exc:
        logger.exception("check-prospective failed: %s", exc)
        return JSONResponse(status_code=500, content=err(500, str(exc)))


@app.post("/hooks/backfill-embeddings")
async def backfill_embeddings(request: Request):
    """One-time backfill: generate embeddings for all nodes that don't have one."""
    try:
        body = await request.json()
        tenant_id = body.get("tenant_id", "default")
        user_id = body.get("user_id", "yugo")

        graph = request.app.state.graph
        from server.engine.embedding_client import get_embeddings

        nodes = await graph.find_nodes_without_embedding(tenant_id, user_id)
        if not nodes:
            return {"code": 0, "message": "success", "data": {"backfilled": 0, "message": "All nodes already have embeddings"}}

        # Batch generate embeddings
        texts = [f"{n['name']}: {n['summary'] or n['name']}" for n in nodes]
        embeddings = await get_embeddings(texts, type_="db")

        updated = 0
        for node, emb in zip(nodes, embeddings):
            if any(v != 0.0 for v in emb[:10]):
                await graph.update_node_embedding(node["id"], emb)
                updated += 1

        log_event("backfill", f"Backfilled {updated}/{len(nodes)} node embeddings", {})
        return {"code": 0, "message": "success", "data": {"backfilled": updated, "total": len(nodes)}}
    except Exception as e:
        logger.error("Backfill failed: %s", e)
        return {"code": 1, "message": str(e)}
