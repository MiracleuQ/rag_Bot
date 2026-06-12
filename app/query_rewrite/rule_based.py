import re

from app.query_rewrite.base import BaseQueryRewriter

# 中文企业场景常见的敬语/请求前缀，对检索无贡献，需移除。
PREFIX_PATTERNS = (
    r"^\s*请问",
    r"^\s*麻烦你",
    r"^\s*麻烦",
    r"^\s*帮我",
    r"^\s*请帮我",
    r"^\s*我想知道",
    r"^\s*我想了解",
    r"^\s*能否",
    r"^\s*可以帮我",
    r"^\s*看下",
    r"^\s*看一下",
    r"^\s*查下",
    r"^\s*查一下",
    r"^\s*了解下",
    r"^\s*了解一下",
)

# 常见句末语气词，去除后保留核心查询实体。
SUFFIX_PATTERNS = (
    r"\s*是什么\??$",
    r"\s*是啥\??$",
    r"\s*吗\??$",
)


class RuleBasedQueryRewriter(BaseQueryRewriter):
    """基于规则的查询改写：移除敬语、语气词等检索噪声，保留核心关键词。

    适用于检索精度要求不高、不想消耗 LLM token 的场景。
    """

    def __init__(self, max_chars: int = 256):
        self._max_chars = max_chars

    def rewrite(self, question: str) -> str:
        text = question.strip()
        if not text:
            return ""

        # 标点规范化：中文句号/逗号转空格，问号统一为英文，减少标点差异对检索的影响。
        text = text.replace("？", "?").replace("。", " ").replace("，", " ")
        text = re.sub(r"\s+", " ", text).strip()

        for pattern in PREFIX_PATTERNS:
            text = re.sub(pattern, "", text).strip()

        text = text.strip(" ?")
        for pattern in SUFFIX_PATTERNS:
            text = re.sub(pattern, "", text).strip()

        text = text.strip(" ?")
        if not text:
            return question.strip()

        if len(text) > self._max_chars:
            text = text[: self._max_chars]
        return text
