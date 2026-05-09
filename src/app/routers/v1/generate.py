from fastapi import APIRouter, Depends

from app.core.deps import QuestionServiceDep
from app.core.rate_limit import make_rate_limiter
from app.schemas.generate import GenerateRequest, GenerateResponse, QuestionSchema
from app.schemas.response import ApiResponse

router = APIRouter()

_rate_limit = make_rate_limiter(route="/api/v1/generate")


@router.post(
    "/generate",
    response_model=ApiResponse[GenerateResponse],
    dependencies=[Depends(_rate_limit)],
)
async def generate(
    payload: GenerateRequest,
    service: QuestionServiceDep,
) -> ApiResponse[GenerateResponse]:
    questions = await service.generate(payload.role)
    return ApiResponse[GenerateResponse](
        data=GenerateResponse(
            questions=[
                QuestionSchema(
                    category=q.category,
                    question=q.question,
                    rationale=q.rationale,
                )
                for q in questions
            ]
        )
    )
