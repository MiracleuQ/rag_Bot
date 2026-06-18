import re
import math
from typing import List, Set

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize_for_coverage(text: str) -> Set[str]:
    normalized = text.lower().strip()
    if not normalized:
        return set()
    tokens = set(_TOKEN_RE.findall(normalized))
    chinese_chars = [ch for ch in normalized if "\u4e00" <= ch <= "\u9fff"]
    if len(chinese_chars) == 1:
        tokens.add(chinese_chars[0])
    for idx in range(0, max(len(chinese_chars) - 1, 0)):
        tokens.add("".join(chinese_chars[idx: idx + 2]))
    return {token for token in tokens if token}


def coverage_score(query: str, merged_text: str) -> float:
    query_tokens = tokenize_for_coverage(query)
    if not query_tokens:
        return 0.0
    if not merged_text.strip():
        return 0.0
    hit_count = len(query_tokens.intersection(tokenize_for_coverage(merged_text)))
    return hit_count / max(1, len(query_tokens))


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
