"""
User interaction prompts for the feedback collection system.

Handles displaying detected scores and collecting user confirmation
or correction input via standard input with timeout support.

Requirements: AC-7.5.1.2, AC-7.5.1.3, AC-7.5.1.4, AC-7.5.1.6
"""

import sys
import threading


# Valid confirmation responses
_VALID_RESPONSES = {"y", "n", "c", "s"}

# Default timeout in seconds for confirmation prompt
DEFAULT_TIMEOUT = 30


class FeedbackPrompt:
    """Handle user interaction for feedback collection.

    Provides prompts for confirming detected scores and entering
    corrected scores, with timeout support for non-blocking gameplay.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize FeedbackPrompt.

        Args:
            timeout: Seconds to wait for user input before defaulting to skip.
        """
        self.timeout = timeout

    def prompt_confirmation(
        self, detected_score_str: str, confidence: float
    ) -> str:
        """Prompt user to confirm or correct a detected score.

        Displays the detected score with confidence and asks the user
        to confirm, reject, correct, or skip. Re-prompts on invalid input.
        Times out after self.timeout seconds, defaulting to 's' (skip).

        Args:
            detected_score_str: Human-readable score string, e.g. "T20 (60 points)".
            confidence: Detection confidence value in [0, 1].

        Returns:
            User response: 'y', 'n', 'c', or 's'.
        """
        print(f"Detected: {detected_score_str}, Confidence: {confidence:.2f}")

        while True:
            response = self._input_with_timeout(
                "Is this correct? (y)es / (n)o / (c)orrect score / (s)kip: "
            )

            if response is None:
                # Timeout reached
                print("\nTimeout — skipping.")
                return "s"

            response = response.strip().lower()
            if response in _VALID_RESPONSES:
                return response

            print(f"Invalid input '{response}'. Please enter y, n, c, or s.")

    def prompt_score_input(self) -> str:
        """Prompt user to enter the actual score.

        Re-prompts if the user enters an empty string.

        Returns:
            Non-empty score string entered by the user.
        """
        while True:
            score = input("Enter actual score (e.g., T20, D16, 25, miss): ")
            score = score.strip()
            if score:
                return score
            print("Score cannot be empty. Please try again.")

    def _input_with_timeout(self, prompt: str) -> str | None:
        """Read a line of input with a timeout.

        Uses a background thread to call input(). If the user does not
        respond within self.timeout seconds, returns None.

        Args:
            prompt: The prompt string to display.

        Returns:
            The user's input string, or None on timeout.
        """
        result: list[str] = []

        def _read() -> None:
            try:
                result.append(input(prompt))
            except EOFError:
                result.append("s")

        thread = threading.Thread(target=_read, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout)

        if result:
            return result[0]
        return None
