from abc import ABC, abstractmethod
from typing import List

from app.schemas import Document


class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        raise NotImplementedError
