"""
Node data model for the brain-memory service.
Represents a memory node stored in the Neo4j knowledge graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Node(BaseModel):
    """
    A memory node in the knowledge graph.

    Supports multiple memory zones (semantic, episodic, procedural, emotional)
    with decay, access tracking, and emotional tagging.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Global unique ID (uuid)")
    name: str = Field(..., description="Primary name of the node")
    aliases: List[str] = Field(default_factory=list, description="Alternative names/aliases")
    tags: List[str] = Field(default_factory=list, description="Multi-dimensional, non-exclusive tags")
    summary: str = Field(default="", description="One-sentence summary")
    content: str = Field(default="", description="Detailed content (long text)")
    zone: str = Field(..., description="Memory zone: semantic/episodic/procedural/emotional")
    importance: float = Field(default=5.0, ge=0.0, le=10.0, description="Importance weight 0-10")
    emotional_tag: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "neutral", "intensity": 0},
        description='Emotional tag: {"type": "joy/sadness/anger/fear/surprise/neutral", "intensity": 0-10}',
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0-1")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
    valid_from: Optional[datetime] = Field(default=None, description="Validity start time")
    valid_until: Optional[datetime] = Field(default=None, description="Validity end time")
    access_count: int = Field(default=0, description="Number of times accessed")
    decay_factor: float = Field(default=1.0, description="Memory decay factor")
    retrieval_strength: float = Field(default=0.0, description="Retrieval strength (defaults to importance)")
    status: str = Field(default="active", description="Node status: active/dormant/suppressed")
    version: int = Field(default=1, description="Version number")
    source_sessions: List[str] = Field(default_factory=list, description="Source session IDs")
    context_snapshot: str = Field(default="", description="Context snapshot at creation time")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Free-form key-value extension properties")

    def model_post_init(self, __context: Any) -> None:
        """Set retrieval_strength to importance if not explicitly provided."""
        if self.retrieval_strength == 0.0 and self.importance > 0:
            self.retrieval_strength = self.importance

    @field_validator("zone")
    @classmethod
    def validate_zone(cls, v: str) -> str:
        """Validate memory zone value."""
        valid_zones = {"semantic", "episodic", "procedural", "emotional"}
        if v not in valid_zones:
            raise ValueError(f"zone must be one of {valid_zones}, got '{v}'")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate node status value."""
        valid_statuses = {"active", "dormant", "suppressed"}
        if v not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}, got '{v}'")
        return v

    @field_validator("emotional_tag")
    @classmethod
    def validate_emotional_tag(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate emotional tag structure."""
        valid_types = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
        if "type" not in v:
            v["type"] = "neutral"
        if v["type"] not in valid_types:
            raise ValueError(f"emotional_tag.type must be one of {valid_types}")
        if "intensity" not in v:
            v["intensity"] = 0
        intensity = float(v["intensity"])
        if not (0 <= intensity <= 10):
            raise ValueError("emotional_tag.intensity must be between 0 and 10")
        v["intensity"] = intensity
        return v

    def to_neo4j_props(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Convert node to Neo4j-compatible property dict.
        Includes tenant_id and user_id for data isolation.
        """
        data = self.model_dump()
        # Convert datetime fields to ISO strings for Neo4j
        for field in ("created_at", "updated_at", "last_accessed", "valid_from", "valid_until"):
            if data[field] is not None:
                data[field] = data[field].isoformat() if isinstance(data[field], datetime) else data[field]
        # Serialize complex fields as JSON strings
        import json
        data["emotional_tag"] = json.dumps(data["emotional_tag"])
        data["properties"] = json.dumps(data["properties"])
        data["aliases"] = data["aliases"]  # Neo4j supports list natively
        data["tags"] = data["tags"]
        data["source_sessions"] = data["source_sessions"]
        # Add isolation fields
        data["tenant_id"] = tenant_id
        data["user_id"] = user_id
        return data

    @classmethod
    def from_neo4j_props(cls, props: Dict[str, Any]) -> "Node":
        """
        Reconstruct a Node from Neo4j property dict.
        Handles deserialization of complex fields.
        """
        import json
        data = dict(props)
        # Remove isolation fields (not part of Node model)
        data.pop("tenant_id", None)
        data.pop("user_id", None)
        # Deserialize JSON strings
        for field in ("emotional_tag", "properties"):
            if isinstance(data.get(field), str):
                data[field] = json.loads(data[field])
        # Parse datetime strings
        for field in ("created_at", "updated_at", "last_accessed", "valid_from", "valid_until"):
            if data.get(field) and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
