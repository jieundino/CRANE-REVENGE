"""CRANE REVENGE Streamlit 프론트엔드용 FastAPI HTTPX 클라이언트 모듈."""

import os
from typing import Any
from dotenv import load_dotenv
import httpx

load_dotenv()

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 5.0


class APIClientError(Exception):
    """FastAPI 서버 통신 실패 또는 비정상 응답 시 발생하는 사용자 친화적 예외."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_api_base_url() -> str:
    """환경 변수 API_BASE_URL을 읽어 마지막 슬래시를 제거한 기본 URL을 반환한다."""
    raw_url = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).strip()
    if not raw_url:
        raw_url = DEFAULT_API_BASE_URL
    return raw_url.rstrip("/")


def _extract_error_detail(response: httpx.Response, fallback: str) -> str:
    """FastAPI 에러 응답 JSON에서 사용자에게 표시할 메시지를 추출한다."""
    try:
        data = response.json()
        if isinstance(data, dict) and "detail" in data:
            detail = data["detail"]
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list) and detail:
                first = detail[0]
                if isinstance(first, dict) and "msg" in first:
                    return str(first["msg"])
    except Exception:
        pass
    return fallback


def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """HTTPX를 사용하여 FastAPI 엔드포인트를 호출하고 JSON 딕셔너리를 반환한다."""
    url = f"{get_api_base_url()}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method=method,
                url=url,
                json=json_body,
                params=params,
            )
    except httpx.ConnectError as exc:
        raise APIClientError(
            "백엔드 API 서버에 연결할 수 없습니다. FastAPI 서버가 실행 중인지 확인해주세요."
        ) from exc
    except httpx.TimeoutException as exc:
        raise APIClientError(
            "백엔드 API 서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
        ) from exc
    except httpx.RequestError as exc:
        raise APIClientError(
            "백엔드 API 서버와 통신하는 중 네트워크 오류가 발생했습니다."
        ) from exc

    if response.status_code >= 400:
        default_msg = (
            "입력값이 올바르지 않습니다."
            if response.status_code == 422
            else "서버 요청 처리 중 오류가 발생했습니다."
        )
        error_msg = _extract_error_detail(response, default_msg)
        raise APIClientError(error_msg, status_code=response.status_code)

    try:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("JSON object expected")
        return payload
    except Exception as exc:
        raise APIClientError("서버로부터 올바르지 않은 형식의 응답을 받았습니다.") from exc


def check_server_health() -> bool:
    """GET /health를 호출하여 백엔드 서버 정상 동작 여부를 반환한다."""
    try:
        data = _request("GET", "/health", timeout=2.5)
        return data.get("status") == "ok"
    except APIClientError:
        return False


def register_player(player_id: str, nickname: str) -> dict[str, Any]:
    """POST /players를 호출하여 플레이어를 등록하거나 닉네임을 갱신한다."""
    return _request(
        "POST",
        "/players",
        json_body={"player_id": player_id, "nickname": nickname},
    )


def submit_game_record(player_id: str, clear_time: float) -> dict[str, Any]:
    """POST /records를 호출하여 게임 클리어 기록을 제출한다."""
    return _request(
        "POST",
        "/records",
        json_body={"player_id": player_id, "clear_time": round(float(clear_time), 2)},
    )


def fetch_player_best(player_id: str) -> dict[str, Any] | None:
    """GET /players/{player_id}/best를 호출하여 플레이어 개인 최고 기록을 조회한다.

    미등록 플레이어(404)인 경우 None을 반환한다.
    """
    try:
        return _request("GET", f"/players/{player_id}/best")
    except APIClientError as exc:
        if exc.status_code == 404:
            return None
        raise


def fetch_rankings(limit: int = 10) -> list[dict[str, Any]]:
    """GET /rankings를 호출하여 상위 플레이어 랭킹 목록을 반환한다."""
    data = _request("GET", "/rankings", params={"limit": limit})
    rankings = data.get("rankings", [])
    if not isinstance(rankings, list):
        raise APIClientError("랭킹 데이터 형식이 올바르지 않습니다.")
    return rankings
