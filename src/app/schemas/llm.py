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
    category: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=500)


class LLMQuestions(BaseModel):
    questions: list[LLMQuestion] = Field(min_length=3, max_length=3)
