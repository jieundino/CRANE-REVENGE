"""CRANE REVENGE FastAPI 요청 및 응답 Pydantic 모델."""

import math
import re
import uuid
from pydantic import BaseModel, Field, field_validator

NICKNAME_MIN_LEN = 1
NICKNAME_MAX_LEN = 20
NICKNAME_PATTERN = re.compile(r"^[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9 _\-]+$")

MIN_CLEAR_TIME_SECONDS = 0.5
MAX_CLEAR_TIME_SECONDS = 3600.0


def validate_uuid_string(value: str) -> str:
    """UUID 문자열 형식을 검증하고 표준 소문자 UUID 문자열로 반환한다."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("유효한 플레이어 ID(UUID)가 필요합니다.")
    try:
        parsed = uuid.UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError("플레이어 ID가 올바른 UUID 형식이 아닙니다.") from exc
    return str(parsed)


def validate_nickname_string(value: str) -> str:
    """닉네임 길이 및 허용 문자(한글, 영문, 숫자, 공백, _, -)를 검증한다."""
    if not isinstance(value, str):
        raise ValueError("닉네임은 문자열이어야 합니다.")
    cleaned = value.strip()
    if len(cleaned) < NICKNAME_MIN_LEN or len(cleaned) > NICKNAME_MAX_LEN:
        raise ValueError(
            f"닉네임은 {NICKNAME_MIN_LEN}자 이상 {NICKNAME_MAX_LEN}자 이하여야 합니다."
        )
    if not NICKNAME_PATTERN.match(cleaned):
        raise ValueError(
            "닉네임에는 한글, 영문, 숫자, 공백, 밑줄(_), 하이픈(-)만 사용할 수 있습니다."
        )
    return cleaned


class PlayerCreateRequest(BaseModel):
    """POST /players 요청 모델."""

    player_id: str = Field(..., description="플레이어 고유 UUID")
    nickname: str = Field(..., description="플레이어 닉네임 (1~20자)")

    @field_validator("player_id")
    @classmethod
    def check_player_id(cls, value: str) -> str:
        return validate_uuid_string(value)

    @field_validator("nickname")
    @classmethod
    def check_nickname(cls, value: str) -> str:
        return validate_nickname_string(value)


class PlayerResponse(BaseModel):
    """POST /players 응답 모델."""

    player_id: str
    nickname: str
    created_at: str
    is_new: bool


class RecordCreateRequest(BaseModel):
    """POST /records 요청 모델."""

    player_id: str = Field(..., description="플레이어 고유 UUID")
    clear_time: float = Field(..., description="클리어 시간(초 단위 실수)")

    @field_validator("player_id")
    @classmethod
    def check_player_id(cls, value: str) -> str:
        return validate_uuid_string(value)

    @field_validator("clear_time")
    @classmethod
    def check_clear_time(cls, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("클리어 시간은 숫자여야 합니다.")
        float_val = float(value)
        if math.isnan(float_val) or math.isinf(float_val):
            raise ValueError("유효하지 않은 클리어 시간 값입니다.")
        if float_val <= 0:
            raise ValueError("클리어 시간은 0보다 큰 양수여야 합니다.")
        if float_val < MIN_CLEAR_TIME_SECONDS or float_val > MAX_CLEAR_TIME_SECONDS:
            raise ValueError(
                f"클리어 시간은 {MIN_CLEAR_TIME_SECONDS}초 이상 {MAX_CLEAR_TIME_SECONDS}초 이하의 합리적인 범위여야 합니다."
            )
        return round(float_val, 2)


class RecordCreateResponse(BaseModel):
    """POST /records 응답 모델."""

    success: bool
    clear_time: float
    is_new_best: bool
    best_time: float
    message: str


class PlayerBestResponse(BaseModel):
    """GET /players/{player_id}/best 응답 모델."""

    player_id: str
    nickname: str
    has_record: bool
    best_time: float | None = None
    record_count: int = 0


class RankingItem(BaseModel):
    """랭킹 단일 항목 모델."""

    rank: int
    player_id: str
    nickname: str
    best_time: float


class RankingsResponse(BaseModel):
    """GET /rankings 응답 모델."""

    rankings: list[RankingItem]
