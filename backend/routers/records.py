"""게임 클리어 기록 제출 라우터."""

from fastapi import APIRouter, HTTPException, status

from backend.database import create_game_record
from backend.models import RecordCreateRequest, RecordCreateResponse

router = APIRouter(prefix="/records", tags=["Records"])


@router.post(
    "",
    response_model=RecordCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="게임 클리어 기록 제출",
)
async def submit_record(payload: RecordCreateRequest) -> RecordCreateResponse:
    """플레이어의 클리어 기록을 저장하고 개인 최고 기록 갱신 여부를 반환한다."""
    result = create_game_record(
        player_id=payload.player_id,
        clear_time=payload.clear_time,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="등록되지 않은 플레이어입니다. 먼저 플레이어를 등록해주세요.",
        )
    return RecordCreateResponse(**result)
