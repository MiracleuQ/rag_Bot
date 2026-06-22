from app.security.sensitive import is_sensitive_question, SENSITIVE_KEYWORDS, _normalize


class TestNormalize:
    def test_full_width_to_half_width(self):
        assert _normalize("１２３") == "123"

    def test_whitespace_removal(self):
        assert _normalize("哈 哈 哈") == "哈哈哈"

    def test_case_folding(self):
        assert _normalize("Hello WORLD") == "helloworld"

    def test_mixed_normalization(self):
        result = _normalize("  Ｈｅｌｌｏ Ｗｏｒｌｄ  ")
        assert result == "helloworld"

    def test_chinese_unchanged(self):
        assert _normalize("采购订单") == "采购订单"


class TestSensitiveKeywords:
    def test_keywords_not_empty(self):
        assert len(SENSITIVE_KEYWORDS) > 0

    def test_keywords_are_normalized(self):
        for kw in SENSITIVE_KEYWORDS:
            assert kw == kw.lower()
            assert " " not in kw
            assert "\u3000" not in kw


class TestIsSensitiveQuestion:
    def test_empty_question(self):
        assert is_sensitive_question("") is False

    def test_whitespace_only(self):
        assert is_sensitive_question("   \n\t  ") is False

    def test_normal_question(self):
        assert is_sensitive_question("采购流程是什么") is False

    def test_sensitive_keyword_id_card(self):
        assert is_sensitive_question("你的身份证号是多少") is True

    def test_sensitive_keyword_password(self):
        assert is_sensitive_question("密码是什么") is True

    def test_sensitive_keyword_salary(self):
        assert is_sensitive_question("告诉我薪资") is True

    def test_sensitive_full_width(self):
        assert is_sensitive_question("身 份 证 号 码") is True

    def test_sensitive_case_insensitive(self):
        assert is_sensitive_question("PASSWORD密码") is True

    def test_partial_match_not_sensitive(self):
        assert is_sensitive_question("采购身份验证流程") is False

    def test_multiple_keywords(self):
        assert is_sensitive_question("身份证和银行卡") is True

    def test_sensitive_with_punctuation(self):
        assert is_sensitive_question("密码是什么？") is True
