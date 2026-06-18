from abc import ABC, abstractmethod
import re
from typing import Iterable, List

from openai import BadRequestError, OpenAI

from app.config import Settings


class BaseEmbedder(ABC):
    @abstractmethod
    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAIEmbedder(BaseEmbedder):
    _BATCH_LIMIT_RE = re.compile(r"larger than\s*(\d+)", re.IGNORECASE)

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenAI(
            # OpenAI SDK 要求 api_key 非空，传 "EMPTY_KEY" 绕过构造校验，
            # 实际调用时由 embed_texts() 的 guard 拦截空配置。
            api_key=settings.embedding_api_key or "EMPTY_KEY",
            base_url=settings.embedding_base_url,
            timeout=settings.embedding_timeout_sec,
        )

    @classmethod
    def _extract_batch_limit(cls, exc: BadRequestError) -> int | None:
        candidates: List[str] = [str(exc)]
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    candidates.append(message)

        for text in candidates:
            match = cls._BATCH_LIMIT_RE.search(text)
            if match:
                try:
                    limit = int(match.group(1))
                except ValueError:
                    return None
                return limit if limit > 0 else None
        return None

    def _embed_with_auto_batch(self, text_list: List[str], _depth: int = 0) -> List[List[float]]:
        if _depth > 5:
            raise RuntimeError("Embedding auto-batch recursion depth exceeded. Check API batch limit config.")
        try:
            resp = self._client.embeddings.create(
                model=self._settings.embedding_model,
                input=text_list,
            )
            return [item.embedding for item in resp.data]
        except BadRequestError as exc:
            # 兼容 OpenAI-compatible 服务对单次 embedding 批大小的额外限制（如 <=10）。
            # 若检测到该类错误，自动按限制拆分批次，避免整次入库失败。
            limit = self._extract_batch_limit(exc)
            if not limit or limit >= len(text_list):
                raise

            vectors: List[List[float]] = []
            for i in range(0, len(text_list), limit):
                sub_batch = text_list[i : i + limit]
                sub_vectors = self._embed_with_auto_batch(sub_batch, _depth=_depth + 1)
                vectors.extend(sub_vectors)
            return vectors

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        text_list = list(texts)
        if not text_list:
            return []
        if not self._settings.embedding_api_key:
            raise ValueError("EMBEDDING_API_KEY is empty. Please configure it in .env.")

        return self._embed_with_auto_batch(text_list)


def create_embedder(settings: Settings) -> BaseEmbedder:
    if settings.embedding_provider == "openai":
        return OpenAIEmbedder(settings=settings)
    raise ValueError(
        "Unsupported EMBEDDING_PROVIDER. "
        f"expected='openai' actual='{settings.embedding_provider}'"
    )
