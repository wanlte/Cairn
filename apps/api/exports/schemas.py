from __future__ import annotations

from pydantic import BaseModel


class ExportResponse(BaseModel):
    kind: str
    format: str
    filename: str
    content: str
