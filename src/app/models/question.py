from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Question:
    """Immutable domain object representing a single interview question.

    Produced by ``LLMClient.generate`` and returned by ``QuestionService``.
    Immutability is enforced by the ``frozen=True`` flag; ``slots=True``
    reduces memory overhead when large lists are cached.

    Attributes:
        category: Short label grouping the question by topic
            (e.g. ``"Behavioural"`` or ``"Technical"``).
        question: The interview question text shown to the user.
        rationale: Explanation of why the question is relevant for the role,
            shown to the user alongside the question.
    """

    category: str
    question: str
    rationale: str
