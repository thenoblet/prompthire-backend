from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

RoleStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200, strip_whitespace=True),
]


class GenerateRequest(BaseModel):
    """Wire payload for ``POST /api/v1/generate``.

    Attributes:
        role: The job title or role description the user wants interview
            questions for. Stripped of leading/trailing whitespace; must be
            between 1 and 200 characters after stripping.
    """

    role: RoleStr


class QuestionSchema(BaseModel):
    """Wire representation of a single interview question in the API response.

    Mirrors the ``Question`` domain object field-for-field; used to decouple
    the wire format from the internal domain model.

    Attributes:
        category: Short topic label (e.g. ``"Behavioural"`` or ``"Technical"``).
        question: The interview question text shown to the user.
        rationale: Explanation of why the question is relevant for the role.
    """

    category: str
    question: str
    rationale: str


class GenerateResponse(BaseModel):
    """Wire payload returned by ``POST /api/v1/generate`` on success.

    Wrapped by the generic ``ApiResponse[T]`` envelope before serialisation.

    Attributes:
        questions: Exactly three role-specific interview questions. Length is
            enforced at the schema level so a malformed list never reaches the
            client.
    """

    questions: list[QuestionSchema] = Field(min_length=3, max_length=3)
