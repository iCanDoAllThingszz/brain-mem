"""
MiniMax Embedding Client (async).
Provides text embedding generation with LRU caching.
"""

import json
import os
import hashlib
from typing import List, Optional
from collections import OrderedDict

import httpx

import logging
logger = logging.getLogger(__name__)

_MAX_CACHE = 1000
_cache: OrderedDict = OrderedDict()

_api_key: Optional[str] = None
_API_URL = "https://api.minimaxi.com/v1/embeddings"
_MODEL = "embo-01"
DIMENSION = 1536


def _get_api_key() -> str:
    global _api_key
    if _api_key:
        return _api_key
    cred_path = os.path.expanduser("~/.openclaw/workspace/credentials/minimax_api.json")
    if os.path.exists(cred_path):
        with open(cred_path) as f:
            creds = json.load(f)
        _api_key = creds.get("minimax_api_key", "")
    if not _api_key:
        _api_key = os.getenv("MINIMAX_API_KEY", "")
    return _api_key


def _cache_key(text: str, type_: str) -> str:
    return hashlib.md5(f"{type_}:{text}".encode()).hexdigest()


async def get_embedding(text: str, type_: str = "query") -> List[float]:
    """
    Get embedding for a single text.
    type_: "query" for retrieval, "db" for storage.
    Returns 1536-dim float list.
    """
    key = _cache_key(text, type_)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    result = await get_embeddings([text], type_)
    if result:
        _cache[key] = result[0]
        if len(_cache) > _MAX_CACHE:
            _cache.popitem(last=False)
        return result[0]
    return [0.0] * DIMENSION  # fallback zero vector


async def get_embeddings(texts: List[str], type_: str = "db") -> List[List[float]]:
    """Batch embedding generation. One API call."""
    if not texts:
        return []

    api_key = _get_api_key()
    if not api_key:
        logger.warning("No MiniMax API key, returning zero vectors")
        return [[0.0] * DIMENSION] * len(texts)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": _MODEL, "texts": texts, "type": type_},
            )
            if resp.status_code == 200:
                data = resp.json()
                vectors = data.get("vectors", [])
                if vectors and len(vectors) == len(texts):
                    return vectors
                logger.warning("Embedding API returned unexpected format: %s", str(data)[:200])
            else:
                logger.error("Embedding API error %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("Embedding API call failed: %s", e)

    return [[0.0] * DIMENSION] * len(texts)
