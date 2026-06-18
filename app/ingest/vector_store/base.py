from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.ingest.models import VectorPoint


class BaseVectorStore(ABC):
    @abstractmethod
    def upsert(self, points: List[VectorPoint]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_points(self, point_ids: List[str]) -> None:
        raise NotImplementedError

    def query(self, vector: List[float], top_k: int = 1) -> List[Tuple[str, float]]:
        return []
