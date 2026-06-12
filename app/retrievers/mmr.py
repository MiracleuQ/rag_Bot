import math
from typing import List

from app.retrievers.base import BaseRetriever
from app.schemas import Document


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MMRRetriever(BaseRetriever):
    def __init__(
        self,
        base_retriever: BaseRetriever,
        embed_fn,
        lambda_mult: float = 0.5,
    ):
        self._base = base_retriever
        self._embed_fn = embed_fn
        self._lambda_mult = max(0.0, min(1.0, lambda_mult))

    def retrieve(self, query: str, top_k: int = 3) -> List[Document]:
        candidates = self._base.retrieve(query=query, top_k=max(top_k * 3, 12))
        if len(candidates) <= top_k:
            return candidates

        candidate_vectors = self._embed_fn([doc.content for doc in candidates])
        query_vector = self._embed_fn([query])[0]

        selected_indices: List[int] = []
        remaining = list(range(len(candidates)))

        for _ in range(min(top_k, len(candidates))):
            best_idx = -1
            best_score = float("-inf")

            for idx in remaining:
                relevance = _cosine_similarity(query_vector, candidate_vectors[idx])

                if selected_indices:
                    max_sim_to_selected = max(
                        _cosine_similarity(candidate_vectors[idx], candidate_vectors[s])
                        for s in selected_indices
                    )
                else:
                    max_sim_to_selected = 0.0

                mmr_score = (
                    self._lambda_mult * relevance
                    - (1 - self._lambda_mult) * max_sim_to_selected
                )

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            if best_idx >= 0:
                selected_indices.append(best_idx)
                remaining.remove(best_idx)

        return [candidates[i] for i in selected_indices]
