"""플레이어별 개인 최고 기록 랭킹 조회 라우터."""

from fastapi import APIRouter, Query, status

from backend.database import get_top_rankings
from backend.models import RankingItem, RankingsResponse

router = APIRouter(prefix="/rankings", tags=["Rankings"])


@router.get(
    "",
    response_model=RankingsResponse,
    status_code=status.HTTP_200_OK,
    summary="전체 플레이어 개인 최고 기록 TOP 랭킹 조회",
)
async def read_rankings(
    limit: int = Query(default=10, ge=1, le=50, description="조회할 최대 랭킹 수 (기본 10, 최대 50)"),
) -> RankingsResponse:
    """플레이어별 가장 빠른 기록(MIN(clear_time)) 기준 오름차순 랭킹을 반환한다."""
    rows = get_top_rankings(limit=limit)
    items = [RankingItem(**row) for row in rows]
    return RankingsResponse(rankings=items)
