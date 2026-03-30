"""
Feedback collector for the human feedback system.

Orchestrates the feedback collection workflow: displays the detected score,
prompts the user for confirmation or correction, parses corrected input,
and returns structured feedback data.

Requirements: AC-7.5.1.1, AC-7.5.1.2, AC-7.5.1.5
"""

from src.feedback.feedback_prompt import FeedbackPrompt
from src.feedback.score_parser import ParsedScore, ScoreParser
from src.fusion.dart_hit_event import DartHitEvent, Score


def score_to_display_string(score: Score) -> str:
    """Convert a Score dataclass to a human-readable display string.

    Examples:
        ring="triple", sector=20  → "T20 (60 points)"
        ring="bull"               → "DB (50 points)"
        ring="single_bull"        → "SB (25 points)"
        ring="miss"               → "Miss (0 points)"
        ring="single", sector=5   → "S5 (5 points)"
        ring="double", sector=16  → "D16 (32 points)"

    Args:
        score: Score dataclass with ring, sector, and total attributes.

    Returns:
        Formatted display string.
    """
    ring = score.ring
    sector = score.sector
    total = score.total

    if ring == "miss":
        label = "Miss"
    elif ring == "bull":
        label = "DB"
    elif ring == "single_bull":
        label = "SB"
    elif ring == "triple":
        label = f"T{sector}"
    elif ring == "double":
        label = f"D{sector}"
    elif ring == "single":
        label = f"S{sector}"
    else:
        label = f"{ring}{sector}"

    return f"{label} ({total} points)"


def score_to_parsed_score(score: Score) -> ParsedScore:
    """Convert a DartHitEvent Score to a ParsedScore.

    Args:
        score: Score dataclass from DartHitEvent.

    Returns:
        Equivalent ParsedScore instance.
    """
    return ParsedScore(ring=score.ring, sector=score.sector, total=score.total)


class FeedbackCollector:
    """Orchestrate feedback collection during gameplay.

    Integrates FeedbackPrompt for user interaction and ScoreParser
    for parsing corrected score input.
    """

    def __init__(
        self,
        prompt: FeedbackPrompt | None = None,
        parser: ScoreParser | None = None,
    ) -> None:
        """Initialize FeedbackCollector.

        Args:
            prompt: FeedbackPrompt instance (created if not provided).
            parser: ScoreParser instance (created if not provided).
        """
        self.prompt = prompt or FeedbackPrompt()
        self.parser = parser or ScoreParser()

    def collect_feedback(
        self,
        dart_hit_event: DartHitEvent,
        image_paths: dict,
    ) -> dict | None:
        """Collect user feedback for a detected dart throw.

        Displays the detected score, prompts the user for confirmation,
        and if the user corrects the score, parses the new input.

        Args:
            dart_hit_event: The detected dart hit event from fusion.
            image_paths: Dictionary of image paths per camera.

        Returns:
            Feedback data dict with detected_score, actual_score,
            is_correct, user_response, dart_hit_event, and image_paths.
            Returns None if the user skips and no feedback is recorded.
        """
        detected_score = dart_hit_event.score
        detected_display = score_to_display_string(detected_score)
        confidence = dart_hit_event.fusion_confidence

        user_response = self.prompt.prompt_confirmation(
            detected_display, confidence
        )

        detected_parsed = score_to_parsed_score(detected_score)

        if user_response in ("y", "s"):
            actual_parsed = detected_parsed
        else:
            # 'n' or 'c': ask for the actual score
            actual_parsed = self._prompt_for_actual_score()

        is_correct = (
            detected_parsed.ring == actual_parsed.ring
            and detected_parsed.sector == actual_parsed.sector
            and detected_parsed.total == actual_parsed.total
        )

        return {
            "detected_score": detected_parsed,
            "actual_score": actual_parsed,
            "is_correct": is_correct,
            "user_response": user_response,
            "dart_hit_event": dart_hit_event,
            "image_paths": image_paths,
        }

    def _prompt_for_actual_score(self) -> ParsedScore:
        """Prompt the user for the actual score and parse it.

        Re-prompts if parsing fails.

        Returns:
            ParsedScore from user input.
        """
        while True:
            score_str = self.prompt.prompt_score_input()
            parsed = self.parser.parse_score(score_str)
            if parsed is not None:
                return parsed
            print(
                f"Could not parse '{score_str}'. "
                "Try formats like T20, D16, 25, SB, DB, miss."
            )
