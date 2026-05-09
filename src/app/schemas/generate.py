from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

RoleStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200, strip_whitespace=True),
]


class GenerateRequest(BaseModel):
    role: RoleStr


class QuestionSchema(BaseModel):
    category: str
    question: str
    rationale: str


class GenerateResponse(BaseModel):
    questions: list[QuestionSchema] = Field(min_length=3, max_length=3)
