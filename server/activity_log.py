"""
Brain Memory Activity Logger
Structured logging for hook activity, working memory, and consolidation events.
Keeps a rolling log file for human inspection.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_LOG_FILE = os.path.join(_LOG_DIR, "activity.log")
_MAX_LINES = 500  # Keep last 500 entries

# Beijing timezone
_BJT = timezone(timedelta(hours=8))


def _now_bjt() -> str:
    return datetime.now(_BJT).strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)


def log_event(
    event_type: str,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a structured log entry.

    event_type: hook_session_start | hook_before_query | hook_after_response |
                hook_session_end | hook_consolidate | perceiver | evaluator |
                encoder | retriever | working_memory | error
    """
    _ensure_dir()
    entry = {
        "time": _now_bjt(),
        "type": event_type,
        "summary": summary[:200],
    }
    if details:
        # Truncate large values
        clean = {}
        for k, v in details.items():
            if isinstance(v, str) and len(v) > 300:
                clean[k] = v[:300] + "..."
            elif isinstance(v, list) and len(v) > 10:
                clean[k] = v[:10]
            else:
                clean[k] = v
        entry["details"] = clean

    line = json.dumps(entry, ensure_ascii=False)

    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # Trim if too long
        _trim_log()
    except Exception:
        pass


def _trim_log():
    """Keep only the last _MAX_LINES entries."""
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _MAX_LINES:
            with open(_LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-_MAX_LINES:])
    except Exception:
        pass


def read_recent(n: int = 30) -> str:
    """Read the last N log entries as formatted text."""
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = lines[-n:]
        output = []
        for line in entries:
            try:
                e = json.loads(line.strip())
                t = e.get("time", "")
                etype = e.get("type", "")
                summary = e.get("summary", "")
                details = e.get("details", {})
                detail_str = ""
                if details:
                    detail_parts = [f"{k}={v}" for k, v in details.items() if k != "context"]
                    if detail_parts:
                        detail_str = " | " + ", ".join(detail_parts[:5])
                output.append(f"[{t}] {etype}: {summary}{detail_str}")
            except Exception:
                output.append(line.strip())
        return "\n".join(output)
    except FileNotFoundError:
        return "No activity log yet."
