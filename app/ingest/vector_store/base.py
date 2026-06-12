from abc import ABC, abstractmethod
from typing import List

from app.ingest.models import VectorPoint


class BaseVectorStore(ABC):
    @abstractmethod
    def upsert(self, points: List[VectorPoint]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_points(self, point_ids: List[str]) -> None:
        raise NotImplementedError
