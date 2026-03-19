"""
LLM client for the brain-memory engine layer.
Provides shared async functions for calling LLM via OpenAI-compatible API.
All config (base_url, model, api_key) is injectable via configure().
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Module-level config, set via configure()
_config: Dict[str, Any] = {
    "base_url": "https://api.minimaxi.com/v1",
    "model": "MiniMax-M2.7-highspeed",
    "api_key": "",
    "temperature": 0.6,
}
_client: Optional[AsyncOpenAI] = None


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()


def configure(base_url: str = None, model: str = None, api_key: str = None, temperature: float = None) -> None:
    """
    Configure the LLM client. Call this at startup before any LLM calls.
    
    Args:
        base_url: OpenAI-compatible API base URL.
        model: Model name to use.
        api_key: API key. If empty, will try credentials file.
        temperature: Default sampling temperature.
    """
    global _client
    if base_url is not None:
        _config["base_url"] = base_url
    if model is not None:
        _config["model"] = model
    if api_key is not None:
        _config["api_key"] = api_key
    if temperature is not None:
        _config["temperature"] = temperature
    # Reset client so next call picks up new config
    _client = None
    logger.info("LLM client configured: base_url=%s model=%s", _config["base_url"], _config["model"])


def _get_client() -> AsyncOpenAI:
    """Lazily initialize and return the shared AsyncOpenAI client."""
    global _client
    if _client is None:
        api_key = _config["api_key"] or os.getenv("MINIMAX_API_KEY", "")
        if not api_key:
            # Try credentials file as fallback
            try:
                cred_path = os.path.expanduser("~/.openclaw/workspace/credentials/minimax_api.json")
                if os.path.exists(cred_path):
                    with open(cred_path) as f:
                        creds = json.load(f)
                    api_key = creds.get("minimax_api_key", "")
            except Exception:
                pass
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=_config["base_url"],
        )
    return _client


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = None,
    model: str = None,
) -> str:
    """
    Call the LLM and return the raw text response.

    Args:
        system_prompt: System-level instruction for the model.
        user_prompt: User message / query.
        temperature: Sampling temperature (defaults to configured value).
        model: Model name (defaults to configured value).

    Returns:
        Raw string content from the model response.

    Raises:
        RuntimeError: If the API call fails.
    """
    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=model or _config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature if temperature is not None else _config["temperature"],
        )
        text = response.choices[0].message.content or ""
        # Strip thinking tags from models that output them (e.g. MiniMax-M2.5)
        text = _strip_thinking(text)
        return text
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise RuntimeError(f"LLM call failed: {e}") from e


async def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = None,
) -> Dict[str, Any]:
    """
    Call the LLM and parse the response as JSON.

    Handles markdown code blocks (```json ... ```) that the model may wrap
    around the JSON output.

    Args:
        system_prompt: System-level instruction (should ask for JSON output).
        user_prompt: User message / query.
        temperature: Sampling temperature.

    Returns:
        Parsed dict from the model's JSON response.

    Raises:
        ValueError: If the response cannot be parsed as JSON.
        RuntimeError: If the API call fails.
    """
    raw = await call_llm(system_prompt, user_prompt, temperature=temperature)
    return _parse_json(raw)


def _parse_json(raw: str) -> Dict[str, Any]:
    """
    Robustly parse JSON from a string that may be wrapped in markdown code fences.
    """
    text = raw.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Last-ditch: find first {...} or [...] block
        brace_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except json.JSONDecodeError:
                pass
        logger.error("Failed to parse LLM JSON response: %s", raw[:500])
        raise ValueError(f"LLM returned non-JSON response: {raw[:200]}") from e
