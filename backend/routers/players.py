"""플레이어 등록 및 개인 최고 기록 조회 라우터."""

from fastapi import APIRouter, HTTPException, status

from backend.database import get_player_best_record, upsert_player
from backend.models import (
    PlayerBestResponse,
    PlayerCreateRequest,
    PlayerResponse,
    validate_uuid_string,
)

router = APIRouter(prefix="/players", tags=["Players"])


@router.post(
    "",
    response_model=PlayerResponse,
    status_code=status.HTTP_200_OK,
    summary="플레이어 등록 또는 닉네임 갱신",
)
async def register_or_update_player(payload: PlayerCreateRequest) -> PlayerResponse:
    """UUID 기반으로 신규 플레이어를 등록하거나 기존 플레이어의 닉네임을 갱신한다."""
    result = upsert_player(
        player_id=payload.player_id,
        nickname=payload.nickname,
    )
    return PlayerResponse(**result)


@router.get(
    "/{player_id}/best",
    response_model=PlayerBestResponse,
    status_code=status.HTTP_200_OK,
    summary="특정 플레이어의 개인 최고 기록 조회",
)
async def get_player_best(player_id: str) -> PlayerBestResponse:
    """플레이어 UUID로 개인 최고 기록 및 기록 보유 여부를 조회한다."""
    try:
        normalized_id = validate_uuid_string(player_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    record_info = get_player_best_record(player_id=normalized_id)
    if record_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="등록되지 않은 플레이어입니다.",
        )

    return PlayerBestResponse(**record_info)
