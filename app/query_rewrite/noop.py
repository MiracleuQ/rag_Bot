from app.query_rewrite.base import BaseQueryRewriter


class NoopQueryRewriter(BaseQueryRewriter):
    def rewrite(self, question: str) -> str:
        return question.strip()
