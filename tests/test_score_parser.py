"""
Unit tests for ScoreParser.

Tests specific examples, invalid inputs, case insensitivity,
and whitespace handling for the score parser.

Requirements: Score Input Format, AC-7.5.1.4
"""

import pytest

from src.feedback.score_parser import ParsedScore, ScoreParser


@pytest.fixture
def parser():
    return ScoreParser()


# --- Specific score examples ---


class TestSpecificScores:
    """Test known score inputs produce correct ParsedScore values."""

    def test_triple_20(self, parser):
        result = parser.parse_score("T20")
        assert result == ParsedScore(ring="triple", sector=20, total=60)

    def test_double_16(self, parser):
        result = parser.parse_score("D16")
        assert result == ParsedScore(ring="double", sector=16, total=32)

    def test_single_bull_25(self, parser):
        result = parser.parse_score("25")
        assert result == ParsedScore(ring="single_bull", sector=None, total=25)

    def test_bull_keyword(self, parser):
        result = parser.parse_score("bull")
        assert result == ParsedScore(ring="bull", sector=None, total=50)

    def test_bull_50(self, parser):
        result = parser.parse_score("50")
        assert result == ParsedScore(ring="bull", sector=None, total=50)

    def test_double_bull_db(self, parser):
        result = parser.parse_score("DB")
        assert result == ParsedScore(ring="bull", sector=None, total=50)

    def test_single_bull_sb(self, parser):
        result = parser.parse_score("SB")
        assert result == ParsedScore(ring="single_bull", sector=None, total=25)

    def test_miss_keyword(self, parser):
        result = parser.parse_score("miss")
        assert result == ParsedScore(ring="miss", sector=None, total=0)

    def test_miss_zero(self, parser):
        result = parser.parse_score("0")
        assert result == ParsedScore(ring="miss", sector=None, total=0)

    def test_bounce(self, parser):
        result = parser.parse_score("bounce")
        assert result == ParsedScore(ring="miss", sector=None, total=0)

    def test_single_prefix(self, parser):
        result = parser.parse_score("S5")
        assert result == ParsedScore(ring="single", sector=5, total=5)

    def test_plain_number_1(self, parser):
        result = parser.parse_score("1")
        assert result == ParsedScore(ring="single", sector=1, total=1)

    def test_plain_number_20(self, parser):
        result = parser.parse_score("20")
        assert result == ParsedScore(ring="single", sector=20, total=20)

    def test_word_triple_20(self, parser):
        result = parser.parse_score("triple 20")
        assert result == ParsedScore(ring="triple", sector=20, total=60)

    def test_word_double_16(self, parser):
        result = parser.parse_score("double 16")
        assert result == ParsedScore(ring="double", sector=16, total=32)

    def test_word_single_5(self, parser):
        result = parser.parse_score("single 5")
        assert result == ParsedScore(ring="single", sector=5, total=5)

    def test_double_bull_words(self, parser):
        result = parser.parse_score("double bull")
        assert result == ParsedScore(ring="bull", sector=None, total=50)

    def test_single_bull_words(self, parser):
        result = parser.parse_score("single bull")
        assert result == ParsedScore(ring="single_bull", sector=None, total=25)


# --- Invalid inputs ---


class TestInvalidInputs:
    """Test that invalid inputs return None."""

    def test_invalid_sector_t25(self, parser):
        assert parser.parse_score("T25") is None

    def test_invalid_sector_d0(self, parser):
        assert parser.parse_score("D0") is None

    def test_random_string(self, parser):
        assert parser.parse_score("xyz") is None

    def test_empty_string(self, parser):
        assert parser.parse_score("") is None

    def test_whitespace_only(self, parser):
        assert parser.parse_score("   ") is None

    def test_negative_number(self, parser):
        assert parser.parse_score("-5") is None

    def test_large_number(self, parser):
        assert parser.parse_score("100") is None

    def test_invalid_sector_s21(self, parser):
        assert parser.parse_score("S21") is None


# --- Case insensitivity ---


class TestCaseInsensitivity:
    """Test that parsing is case-insensitive."""

    def test_lowercase_t20(self, parser):
        assert parser.parse_score("t20") == parser.parse_score("T20")

    def test_lowercase_d16(self, parser):
        assert parser.parse_score("d16") == parser.parse_score("D16")

    def test_lowercase_s5(self, parser):
        assert parser.parse_score("s5") == parser.parse_score("S5")

    def test_uppercase_miss(self, parser):
        assert parser.parse_score("MISS") == parser.parse_score("miss")

    def test_mixed_case_bull(self, parser):
        assert parser.parse_score("Bull") == parser.parse_score("bull")

    def test_uppercase_db(self, parser):
        assert parser.parse_score("DB") == parser.parse_score("db")

    def test_uppercase_sb(self, parser):
        assert parser.parse_score("SB") == parser.parse_score("sb")


# --- Whitespace handling ---


class TestWhitespaceHandling:
    """Test that leading/trailing whitespace is stripped."""

    def test_leading_space(self, parser):
        assert parser.parse_score(" T20") == ParsedScore(ring="triple", sector=20, total=60)

    def test_trailing_space(self, parser):
        assert parser.parse_score("T20 ") == ParsedScore(ring="triple", sector=20, total=60)

    def test_both_spaces(self, parser):
        assert parser.parse_score("  T20  ") == ParsedScore(ring="triple", sector=20, total=60)

    def test_tab_padding(self, parser):
        assert parser.parse_score("\tD16\t") == ParsedScore(ring="double", sector=16, total=32)
