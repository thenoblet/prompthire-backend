"""Pydantic schemas instructor binds against when calling the LLM.

These are NOT wire DTOs — they are the shape we force the model to produce.
Field-length caps defend against the model returning paragraphs the frontend
cannot render; `min_length=3, max_length=3` enforces "exactly three questions"
on the model output.

Imported by `infrastructure/llm.py`. Translated to domain `Question` objects
before crossing the infrastructure boundary.
"""

from pydantic import BaseModel, Field


class LLMQuestion(BaseModel):
    """Structured representation of a single question as produced by the LLM.

    Field-length caps prevent the model from returning values that are too long
    for the frontend to render. This schema is never exposed in the API; it is
    translated to a domain ``Question`` object inside ``LLMClient.generate``.

    Attributes:
        category: Short topic label; capped at 80 characters.
        question: The interview question text; capped at 500 characters.
        rationale: Explanation of relevance; capped at 500 characters.
    """

    category: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=500)


class LLMQuestions(BaseModel):
    """Container holding exactly three ``LLMQuestion`` objects.

    Instructor uses this class as the ``response_model`` when calling the LLM,
    enforcing the three-question constraint at the schema level.

    Attributes:
        questions: A list of exactly three questions; ``min_length=3,
            max_length=3`` is enforced by Pydantic.
    """

    questions: list[LLMQuestion] = Field(min_length=3, max_length=3)
