from __future__ import annotations

from abc import ABC, abstractmethod

from apps.api.ingestion.schemas import RawItem, SourceType


class BaseCollector(ABC):
    source_type: SourceType

    @abstractmethod
    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        raise NotImplementedError
