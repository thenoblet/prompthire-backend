from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Question:
    category: str
    question: str
    rationale: str
