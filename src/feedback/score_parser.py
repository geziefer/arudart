"""
Score parser for human feedback system.

Parses user score input in various natural language formats into
structured ParsedScore data.
"""

import re
from dataclasses import dataclass


@dataclass
class ParsedScore:
    """Structured representation of a dart score.

    Attributes:
        ring: Score ring type - "single", "double", "triple",
              "bull", "single_bull", or "miss".
        sector: Board sector 1-20 for regular scores, None for bulls/miss.
        total: Final calculated score value.
    """

    ring: str  # "single", "double", "triple", "bull", "single_bull", "miss"
    sector: int | None  # 1-20 for regular, None for bulls/miss
    total: int  # final score


VALID_SECTORS = set(range(1, 21))

# Ring prefix mapping for single-letter formats (T20, D16, S5)
_PREFIX_MAP = {"t": "triple", "d": "double", "s": "single"}

# Word-based ring names
_WORD_RINGS = {"triple": "triple", "double": "double", "single": "single"}

# Ring multipliers for total calculation
_MULTIPLIERS = {"single": 1, "double": 2, "triple": 3}

# Patterns for miss variants
_MISS_VARIANTS = {"0", "miss", "bounce"}

# Patterns for double bull variants
_BULL_VARIANTS = {"50", "db", "bull", "double bull"}

# Patterns for single bull variants
_SINGLE_BULL_VARIANTS = {"25", "sb", "single bull"}

# Regex for prefix + number format (T20, D16, S5)
_PREFIX_RE = re.compile(r"^([tds])(\d+)$")

# Regex for word + number format ("triple 20", "double 16", "single 5")
_WORD_RE = re.compile(r"^(triple|double|single)\s+(\d+)$")

# Regex for plain number
_PLAIN_NUMBER_RE = re.compile(r"^(\d+)$")


class ScoreParser:
    """Parse user score input into structured ParsedScore objects.

    Supports multiple input formats including prefix notation (T20, D16),
    word notation (triple 20), plain numbers, bull variants, and miss.
    """

    def parse_score(self, input_string: str) -> ParsedScore | None:
        """Parse a score input string into a ParsedScore.

        Args:
            input_string: User input string (e.g., "T20", "D16", "25", "miss").

        Returns:
            ParsedScore if input is valid, None otherwise.
        """
        if not input_string or not isinstance(input_string, str):
            return None

        normalized = input_string.strip().lower()

        if not normalized:
            return None

        # 1. Miss variants: "0", "miss", "bounce"
        if normalized in _MISS_VARIANTS:
            return ParsedScore(ring="miss", sector=None, total=0)

        # 2. Double bull variants: "50", "db", "bull", "double bull"
        if normalized in _BULL_VARIANTS:
            return ParsedScore(ring="bull", sector=None, total=50)

        # 3. Single bull variants: "25", "sb", "single bull"
        if normalized in _SINGLE_BULL_VARIANTS:
            return ParsedScore(ring="single_bull", sector=None, total=25)

        # 4. Prefix + number format: T20, D16, S5
        match = _PREFIX_RE.match(normalized)
        if match:
            prefix, num_str = match.group(1), match.group(2)
            sector = int(num_str)
            if sector not in VALID_SECTORS:
                return None
            ring = _PREFIX_MAP[prefix]
            total = sector * _MULTIPLIERS[ring]
            return ParsedScore(ring=ring, sector=sector, total=total)

        # 5. Word + number format: "triple 20", "double 16", "single 5"
        match = _WORD_RE.match(normalized)
        if match:
            word, num_str = match.group(1), match.group(2)
            sector = int(num_str)
            if sector not in VALID_SECTORS:
                return None
            ring = _WORD_RINGS[word]
            total = sector * _MULTIPLIERS[ring]
            return ParsedScore(ring=ring, sector=sector, total=total)

        # 6. Plain number 1-20 → assume single
        match = _PLAIN_NUMBER_RE.match(normalized)
        if match:
            sector = int(match.group(1))
            if sector in VALID_SECTORS:
                return ParsedScore(ring="single", sector=sector, total=sector)
            return None

        return None
