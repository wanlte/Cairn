from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DriftClaim(BaseModel):
    key: str
    value: str
    group: str


class DriftPoint(BaseModel):
    snapshot_id: int
    period: str
    created_at: datetime
    claims: list[DriftClaim] = Field(default_factory=list)
    triggers: dict[str, int] = Field(default_factory=dict)


class DriftCurveResponse(BaseModel):
    points: list[DriftPoint] = Field(default_factory=list)
    total_snapshots: int = 0


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    weight: float


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str
    weight: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
