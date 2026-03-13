"""
Relation data model for the brain-memory service.
Represents a directed relationship between two memory nodes in the Neo4j graph.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Relation(BaseModel):
    """
    A directed relationship between two memory nodes.

    Supports temporal validity, confidence scoring, and free-form properties.
    """

    from_id: str = Field(..., description="Source node ID")
    to_id: str = Field(..., description="Target node ID")
    type: str = Field(..., description="Relationship type (e.g., RELATED_TO, CAUSES, PART_OF)")
    description: str = Field(default="", description="Natural language description of the relationship")
    valid_from: Optional[datetime] = Field(default=None, description="Relationship validity start time")
    valid_until: Optional[datetime] = Field(default=None, description="Relationship validity end time")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0-1")
    source_session: str = Field(default="", description="Session ID that created this relationship")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Free-form extension properties")

    def to_neo4j_props(self) -> Dict[str, Any]:
        """
        Convert relation to Neo4j-compatible property dict.
        Excludes from_id and to_id (used for node matching, not stored on edge).
        """
        import json
        data = self.model_dump()
        data.pop("from_id")
        data.pop("to_id")
        data.pop("type")
        # Convert datetime fields to ISO strings
        for field in ("valid_from", "valid_until"):
            if data[field] is not None and isinstance(data[field], datetime):
                data[field] = data[field].isoformat()
        data["properties"] = json.dumps(data["properties"])
        return data

    @classmethod
    def from_neo4j_record(cls, from_id: str, to_id: str, rel_type: str, props: Dict[str, Any]) -> "Relation":
        """
        Reconstruct a Relation from Neo4j relationship data.
        """
        import json
        data = dict(props)
        data["from_id"] = from_id
        data["to_id"] = to_id
        data["type"] = rel_type
        # Deserialize JSON strings
        if isinstance(data.get("properties"), str):
            data["properties"] = json.loads(data["properties"])
        # Parse datetime strings
        for field in ("valid_from", "valid_until"):
            if data.get(field) and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
