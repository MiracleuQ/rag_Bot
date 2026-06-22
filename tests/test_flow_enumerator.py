from app.services.flow_enumerator import is_flow_enumeration_question, build_flow_enumeration_answer, _flow_code_key
from app.schemas import Document


class TestIsFlowEnumerationQuestion:
    def test_empty_question(self):
        assert is_flow_enumeration_question("") is False

    def test_normal_question(self):
        assert is_flow_enumeration_question("采购流程是什么") is False

    def test_flow_keywords(self):
        assert is_flow_enumeration_question("有哪些流程") is True
        assert is_flow_enumeration_question("相关流程包括") is True
        assert is_flow_enumeration_question("流程有哪些步骤") is True

    def test_list_keywords(self):
        assert is_flow_enumeration_question("相关流程列表") is True

    def test_partial_match(self):
        assert is_flow_enumeration_question("流程图") is False


class TestFlowCodeKey:
    def test_simple_code(self):
        assert _flow_code_key("4.1") == (4, 1)

    def test_nested_code(self):
        assert _flow_code_key("4.1.2") == (4, 1, 2)

    def test_invalid_segment(self):
        result = _flow_code_key("4.abc")
        assert result[0] == 4
        assert result[1] == 9999

    def test_comparison(self):
        assert _flow_code_key("4.1") < _flow_code_key("4.2")
        assert _flow_code_key("4.1") < _flow_code_key("4.1.1")


class TestBuildFlowEnumerationAnswer:
    def test_empty_docs(self):
        result = build_flow_enumeration_question("有哪些流程", [])
        assert result == ""

    def test_non_flow_question(self):
        docs = [Document(doc_id="d1", content="some content", source="test.pdf")]
        result = build_flow_enumeration_answer("你好", docs)
        assert result == ""

    def test_no_source_docs(self):
        docs = [Document(doc_id="d1", content="some content", source="")]
        result = build_flow_enumeration_answer("有哪些流程", docs)
        assert result == ""


def build_flow_enumeration_question(question: str, docs):
    return build_flow_enumeration_answer(question, docs)
