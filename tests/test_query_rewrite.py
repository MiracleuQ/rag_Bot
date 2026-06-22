from app.query_rewrite.noop import NoopQueryRewriter
from app.query_rewrite.rule_based import RuleBasedQueryRewriter


class TestNoopQueryRewriter:
    def test_returns_same_text(self):
        rewriter = NoopQueryRewriter()
        assert rewriter.rewrite("采购流程") == "采购流程"

    def test_empty_input(self):
        rewriter = NoopQueryRewriter()
        assert rewriter.rewrite("") == ""

    def test_whitespace_stripped(self):
        rewriter = NoopQueryRewriter()
        result = rewriter.rewrite("  hello  ")
        assert result == "hello"


class TestRuleBasedQueryRewriter:
    def setup_method(self):
        self.rewriter = RuleBasedQueryRewriter(max_chars=256)

    def test_remove_prefix_ask(self):
        result = self.rewriter.rewrite("请问采购流程")
        assert result == "采购流程"

    def test_remove_prefix_help(self):
        result = self.rewriter.rewrite("帮我查一下库存")
        assert result == "库存"

    def test_remove_prefix_please(self):
        result = self.rewriter.rewrite("麻烦你告诉我价格")
        assert result == "告诉我价格"

    def test_remove_suffix_question(self):
        result = self.rewriter.rewrite("采购流程是什么?")
        assert "是什么" not in result

    def test_normalize_punctuation(self):
        result = self.rewriter.rewrite("价格。数量。")
        assert "。" not in result

    def test_max_chars_limit(self):
        rewriter = RuleBasedQueryRewriter(max_chars=10)
        result = rewriter.rewrite("这是一个很长很长很长很长的问题")
        assert len(result) <= 10

    def test_empty_after_rewrite_returns_original(self):
        result = self.rewriter.rewrite("请问")
        assert result == "请问"

    def test_empty_input(self):
        result = self.rewriter.rewrite("")
        assert result == ""

    def test_core_query_preserved(self):
        result = self.rewriter.rewrite("请问采购订单流程")
        assert "采购订单" in result
