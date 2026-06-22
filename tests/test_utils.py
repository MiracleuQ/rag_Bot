import math

from app.utils import tokenize_for_coverage, coverage_score, cosine_similarity


class TestTokenizeForCoverage:
    def test_empty_string(self):
        assert tokenize_for_coverage("") == set()

    def test_whitespace_only(self):
        assert tokenize_for_coverage("   \n\t  ") == set()

    def test_english_tokens(self):
        tokens = tokenize_for_coverage("hello world 123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "123" in tokens

    def test_chinese_unigram(self):
        tokens = tokenize_for_coverage("好")
        assert "好" in tokens

    def test_chinese_bigram(self):
        tokens = tokenize_for_coverage("密码")
        assert "密码" in tokens

    def test_mixed_language(self):
        tokens = tokenize_for_coverage("Python 是最好的语言")
        assert "python" in tokens
        assert "最好" in tokens

    def test_single_chinese_char(self):
        tokens = tokenize_for_coverage("好")
        assert "好" in tokens

    def test_case_insensitive(self):
        tokens = tokenize_for_coverage("Hello WORLD")
        assert "hello" in tokens
        assert "world" in tokens


class TestCoverageScore:
    def test_empty_query(self):
        assert coverage_score("", "some text") == 0.0

    def test_empty_merged_text(self):
        assert coverage_score("query", "") == 0.0

    def test_both_empty(self):
        assert coverage_score("", "") == 0.0

    def test_full_coverage(self):
        score = coverage_score("hello world", "hello world foo bar")
        assert score == 1.0

    def test_partial_coverage(self):
        score = coverage_score("hello world", "hello foo bar")
        assert 0.0 < score < 1.0

    def test_no_coverage(self):
        score = coverage_score("hello world", "foo bar baz")
        assert score == 0.0


class TestCosineSimilarity:
    def test_identical_vectors(self):
        sim = cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        sim = cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 1e-6

    def test_opposite_vectors(self):
        sim = cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(sim - (-1.0)) < 1e-6

    def test_zero_vector(self):
        sim = cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert sim == 0.0

    def test_both_zero_vectors(self):
        sim = cosine_similarity([0.0, 0.0], [0.0, 0.0])
        assert sim == 0.0

    def test_similar_vectors(self):
        sim = cosine_similarity([1.0, 1.0], [1.0, 0.8])
        assert 0.9 < sim <= 1.0
