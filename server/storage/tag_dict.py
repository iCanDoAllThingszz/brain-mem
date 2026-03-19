"""
Tag dictionary management for the brain-memory service.
Persists tag metadata to a JSON file with append-only semantics.
Supports hierarchical (parent/child) tag relationships.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Hierarchical core tags: {parent: [children]}
# Top-level tags have parent=None
_CORE_TAG_HIERARCHY: Dict[Optional[str], List[str]] = {
    None: ["人物", "组织", "地点", "项目", "概念",
           "事件", "决策", "计划", "技能", "情感",
           "健康", "财务", "技术", "教训", "作品"],
    "人物": ["家人", "同事", "朋友", "同学", "客户"],
    "技术": ["前端", "后端", "AI/ML", "基础设施", "数据"],
    "计划": ["短期", "长期", "提醒"],
    "健康": ["运动", "饮食", "睡眠", "心理"],
    "财务": ["收入", "支出", "投资"],
}

_FIND_SIMILAR_SYSTEM = """\
You are a hierarchical tag taxonomy manager. Given a new tag and the existing \
tag tree, decide whether the new tag should be merged into an existing tag, \
placed under an existing parent, or kept as a new top-level tag.

Rules:
- If the new tag is semantically equivalent or a near-synonym of an existing tag, \
  return {"match": "<existing_tag_name>", "parent": null}.
- If the new tag is a sub-concept that should be a child of an existing tag, \
  return {"match": null, "parent": "<parent_tag_name>"}.
- If the new tag is genuinely distinct and adds value as a top-level tag, \
  return {"match": null, "parent": null}.

Return ONLY valid JSON.
"""


class Tag(BaseModel):
    """A canonical tag entry in the tag dictionary."""

    name: str = Field(..., description="Canonical tag name (immutable once created)")
    parent: Optional[str] = Field(default=None, description="Parent tag name for hierarchy (None = top-level)")
    aliases: List[str] = Field(default_factory=list, description="Alternative names for this tag")
    description: str = Field(default="", description="Human-readable description")
    usage_count: int = Field(default=0, description="Number of times this tag has been used")
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO timestamp of creation",
    )
    status: str = Field(default="active", description="Tag status: active/deprecated")
    preferred_replacement: Optional[str] = Field(
        default=None, description="Replacement tag name if deprecated"
    )


class TagDict:
    """
    Append-only tag dictionary backed by a JSON file.

    Core principle: tags are never deleted or renamed.
    Deprecated tags are marked with status='deprecated' and point to a replacement.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._tags: Dict[str, Tag] = {}
        self._load()
        self._ensure_core_tags()

    # -------------------------------------------------------------------------
    # Persistence helpers
    # -------------------------------------------------------------------------

    def _load(self) -> None:
        """Load tags from the JSON file, creating it if absent."""
        if not os.path.exists(self._path):
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            self._save()
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw: Dict[str, Any] = json.load(f)
            self._tags = {name: Tag(**data) for name, data in raw.items()}
            logger.debug("Loaded %d tags from %s", len(self._tags), self._path)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to load tag dict from %s: %s", self._path, e)
            self._tags = {}

    def _save(self) -> None:
        """Persist current tags to the JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {name: tag.model_dump() for name, tag in self._tags.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _ensure_core_tags(self) -> None:
        """Pre-seed the hierarchical core tags if they don't exist yet."""
        changed = False
        for parent, children in _CORE_TAG_HIERARCHY.items():
            for name in children:
                if name not in self._tags:
                    self._tags[name] = Tag(name=name, parent=parent, description="core tag")
                    changed = True
                elif self._tags[name].parent is None and parent is not None:
                    # Migrate existing flat tag to hierarchical
                    self._tags[name].parent = parent
                    changed = True
        if changed:
            self._save()
            logger.info("Pre-seeded/updated hierarchical core tags")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_tag(self, name: str) -> Optional[Tag]:
        """Exact lookup by tag name."""
        return self._tags.get(name)

    async def find_similar(self, name: str) -> Optional[Tag]:
        """
        Find a semantically similar tag (hierarchy-aware).

        Strategy:
        1. Exact match
        2. Case-insensitive match
        3. Alias match
        4. Substring containment
        5. LLM semantic similarity check with hierarchy context (fallback)

        Returns:
            Best matching Tag or None
        """
        # 1. Exact
        if name in self._tags:
            return self._tags[name]
        # 2. Case-insensitive
        lower = name.lower()
        for tag in self._tags.values():
            if tag.name.lower() == lower:
                return tag
        # 3. Alias match
        for tag in self._tags.values():
            if any(a.lower() == lower for a in tag.aliases):
                return tag
        # 4. Substring containment
        for tag in self._tags.values():
            if lower in tag.name.lower() or tag.name.lower() in lower:
                return tag

        # 5. LLM semantic similarity with hierarchy tree
        active_tags = [t for t in self._tags.values() if t.status == "active"]
        if not active_tags:
            return None
        try:
            from server.engine.llm_client import call_llm_json
            tree_text = self.get_hierarchy_tree_text()
            user_prompt = (
                f"New tag: \"{name}\"\n"
                f"Existing tag hierarchy:\n{tree_text}"
            )
            result = await call_llm_json(_FIND_SIMILAR_SYSTEM, user_prompt, temperature=0.1)
            match_name = result.get("match")
            if match_name and match_name in self._tags:
                logger.info("LLM matched tag '%s' -> '%s'", name, match_name)
                return self._tags[match_name]
            # LLM suggested a parent for a new child tag
            parent_name = result.get("parent")
            if parent_name and parent_name in self._tags:
                new_tag = self.add_tag(name, parent=parent_name)
                logger.info("LLM created child tag '%s' under '%s'", name, parent_name)
                return new_tag
        except Exception as e:
            logger.warning("LLM tag similarity check failed for '%s': %s", name, e)

        return None

    def add_tag(self, name: str, description: str = "", parent: Optional[str] = None) -> Tag:
        """Add a new tag. Returns existing entry if already present."""
        if name in self._tags:
            logger.debug("Tag '%s' already exists, returning existing entry", name)
            return self._tags[name]
        tag = Tag(name=name, description=description, parent=parent)
        self._tags[name] = tag
        self._save()
        logger.info("Added new tag: '%s' (parent=%s)", name, parent)
        return tag

    def deprecate_tag(self, name: str, replacement: str) -> None:
        """Mark a tag as deprecated and point it to a replacement."""
        if name not in self._tags:
            raise KeyError(f"Tag not found: '{name}'")
        if replacement not in self._tags:
            raise ValueError(f"Replacement tag not found: '{replacement}'. Add it first.")
        tag = self._tags[name]
        tag.status = "deprecated"
        tag.preferred_replacement = replacement
        self._save()
        logger.info("Deprecated tag '%s' -> replacement '%s'", name, replacement)

    async def standardize(self, candidate_tags: List[str]) -> List[str]:
        """
        Standardize a list of candidate tag strings (async — may call LLM).

        For each candidate:
        - If it matches an active tag exactly, keep it.
        - If it matches a deprecated tag, replace with its preferred_replacement.
        - If a similar active tag is found (including LLM check), use that instead.
        - Otherwise, add it as a new tag and return it.
        """
        result: List[str] = []
        for candidate in candidate_tags:
            existing = self.get_tag(candidate)
            if existing:
                if existing.status == "deprecated" and existing.preferred_replacement:
                    result.append(existing.preferred_replacement)
                else:
                    result.append(existing.name)
                self.increment_usage(result[-1])
                continue
            similar = await self.find_similar(candidate)
            if similar:
                canonical = (
                    similar.preferred_replacement
                    if similar.status == "deprecated" and similar.preferred_replacement
                    else similar.name
                )
                result.append(canonical)
                self.increment_usage(canonical)
            else:
                new_tag = self.add_tag(candidate)
                result.append(new_tag.name)
                self.increment_usage(new_tag.name)
        return result

    def get_all_active(self) -> List[Tag]:
        """Return all tags with status='active'."""
        return [tag for tag in self._tags.values() if tag.status == "active"]

    def increment_usage(self, tag_name: str) -> None:
        """Increment the usage counter for a tag. Silently ignores unknown names."""
        if tag_name in self._tags:
            self._tags[tag_name].usage_count += 1
            self._save()

    # -------------------------------------------------------------------------
    # Hierarchy API
    # -------------------------------------------------------------------------

    def get_children(self, parent_name: str) -> List[Tag]:
        """Return direct children of a tag."""
        return [t for t in self._tags.values() if t.parent == parent_name and t.status == "active"]

    def get_subtree(self, tag_name: str) -> Set[str]:
        """Return tag_name plus all descendant tag names (recursive)."""
        result: Set[str] = {tag_name}
        queue = [tag_name]
        while queue:
            current = queue.pop()
            for child in self.get_children(current):
                if child.name not in result:
                    result.add(child.name)
                    queue.append(child.name)
        return result

    def expand_tags_with_children(self, tags: List[str]) -> List[str]:
        """Expand a list of tags to include all descendant tags."""
        expanded: Set[str] = set()
        for tag in tags:
            expanded |= self.get_subtree(tag)
        return list(expanded)

    def get_full_path(self, tag_name: str) -> str:
        """Return the full hierarchical path, e.g. '人物/同事'."""
        parts = [tag_name]
        current = self._tags.get(tag_name)
        while current and current.parent and current.parent in self._tags:
            parts.insert(0, current.parent)
            current = self._tags.get(current.parent)
        return "/".join(parts)

    def get_hierarchy_tree_text(self) -> str:
        """Return a human-readable tree of all active tags for LLM prompts."""
        lines: List[str] = []
        # Top-level tags (no parent)
        top_level = [t for t in self._tags.values() if t.parent is None and t.status == "active"]
        for tag in sorted(top_level, key=lambda t: t.name):
            lines.append(f"- {tag.name}")
            children = self.get_children(tag.name)
            for child in sorted(children, key=lambda t: t.name):
                lines.append(f"  - {child.name}")
                grandchildren = self.get_children(child.name)
                for gc in sorted(grandchildren, key=lambda t: t.name):
                    lines.append(f"    - {gc.name}")
        return "\n".join(lines)
