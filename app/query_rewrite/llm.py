import re

from app.llm_client import LLMClient
from app.query_rewrite.base import BaseQueryRewriter

REWRITE_SYSTEM_PROMPT = """你是企业知识库检索查询改写器。

任务：
1. 如果原问题已是适合检索的完整查询，原样输出；
2. 否则将用户问题改写为更利于知识库检索的查询语句；
3. 保留原始意图、关键实体、时间范围、约束条件；
4. 不增加原问题没有的新事实，不回答问题本身；
5. 输出仅一行改写后的查询，不要解释。
"""


class LLMQueryRewriter(BaseQueryRewriter):
    def __init__(self, llm_client: LLMClient, max_chars: int = 256):
        self._llm_client = llm_client
        self._max_chars = max_chars

    @staticmethod
    def _sanitize(text: str) -> str:
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        first_line = re.sub(r"^(改写后[：:]\s*|查询[：:]\s*)", "", first_line).strip()
        return first_line.strip("\"' ")

    def rewrite(self, question: str) -> str:
        original = question.strip()
        if not original:
            return ""

        messages = [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": f"原问题：{original}"},
        ]
        try:
            # 温度设为 0，尽量减少改写漂移，保持检索稳定性。
            rewritten = self._llm_client.chat(messages=messages, temperature=0.0)
        except Exception:
            # 改写失败直接回退原问题，保证主流程可用。
            return original

        rewritten = self._sanitize(rewritten)
        if not rewritten:
            return original
        if len(rewritten) > self._max_chars:
            rewritten = rewritten[: self._max_chars]
        return rewritten
