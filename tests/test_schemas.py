import pytest

from app.schemas import ChatRequest, ChatResponse, Document, SessionRecord, MessageRecord


class TestDocument:
    def test_create_with_required_fields(self):
        doc = Document(doc_id="doc-1", content="hello")
        assert doc.doc_id == "doc-1"
        assert doc.content == "hello"
        assert doc.source is None
        assert doc.score is None

    def test_create_with_all_fields(self):
        doc = Document(doc_id="doc-1", content="hello", source="test.pdf", score=0.95)
        assert doc.source == "test.pdf"
        assert doc.score == 0.95


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(question="你好")
        assert req.question == "你好"
        assert req.session_id is None
        assert req.user_id is None
        assert req.channel == "api"

    def test_empty_question_fails(self):
        with pytest.raises(Exception):
            ChatRequest(question="")

    def test_with_optional_fields(self):
        req = ChatRequest(
            question="测试",
            session_id="s-1",
            user_id="u-1",
            channel="wechat",
        )
        assert req.session_id == "s-1"
        assert req.channel == "wechat"


class TestChatResponse:
    def test_default_values(self):
        resp = ChatResponse(answer="test")
        assert resp.answer == "test"
        assert resp.used_docs == []
        assert resp.session_id is None

    def test_with_docs(self):
        doc = Document(doc_id="d1", content="c")
        resp = ChatResponse(answer="a", used_docs=[doc])
        assert len(resp.used_docs) == 1


class TestSessionRecord:
    def test_create(self):
        record = SessionRecord(
            session_id="s-1",
            channel="api",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
        assert record.session_id == "s-1"
        assert record.user_id is None


class TestMessageRecord:
    def test_create(self):
        record = MessageRecord(
            message_id=1,
            session_id="s-1",
            role="user",
            content="hello",
            created_at="2024-01-01",
        )
        assert record.message_id == 1
        assert record.used_docs == []
