#!/usr/bin/env python3
"""One-time script to clean duplicate entries from the encoder buffer."""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import yaml
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    data_cfg = config.get("storage", {})
    db_path = os.path.join(base_dir, data_cfg.get("buffer", {}).get("path", "data/buffer.db").lstrip("./"))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, tenant_id, user_id, data, importance FROM memory_buffer ORDER BY importance DESC"
    ).fetchall()

    seen = {}
    to_delete = []
    for row in rows:
        try:
            data = json.loads(row["data"])
        except Exception:
            continue
        msg = data.get("message", "").strip()
        if not msg:
            continue
        key = (row["tenant_id"], row["user_id"], msg)
        if key in seen:
            to_delete.append(row["id"])
        else:
            seen[key] = row["id"]

    if to_delete:
        placeholders = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM memory_buffer WHERE id IN ({placeholders})", to_delete)
        conn.commit()
        print(f"Deleted {len(to_delete)} duplicate buffer entries")
    else:
        print("No duplicates found")
    conn.close()


if __name__ == "__main__":
    main()
