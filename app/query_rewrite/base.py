from abc import ABC, abstractmethod


class BaseQueryRewriter(ABC):
    @abstractmethod
    def rewrite(self, question: str) -> str:
        raise NotImplementedError
