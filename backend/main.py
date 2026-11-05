"""CRANE REVENGE FastAPI 백엔드 애플리케이션 엔트리포인트."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.database import init_db
from backend.routers import players, rankings, records

load_dotenv()

logger = logging.getLogger("crane_revenge.backend")

APP_ENV = os.getenv("APP_ENV", "development").lower()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 시작 시 SQLite 데이터베이스와 테이블을 초기화한다."""
    init_db()
    yield


app = FastAPI(
    title="CRANE REVENGE API",
    description="인형뽑기 기계 탈출 미니게임 CRANE REVENGE의 플레이어·기록·랭킹 백엔드 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if APP_ENV != "production_no_docs" else None,
    redoc_url="/redoc" if APP_ENV != "production_no_docs" else None,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """내부 서버 오류 발생 시 상세 traceback이나 파일 경로를 노출하지 않고 안전한 응답을 반환한다."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
    )


@app.get("/health", tags=["System"], summary="서버 상태 확인")
async def health_check() -> dict[str, str]:
    """서버 정상 동작 여부를 반환한다."""
    return {"status": "ok"}


app.include_router(players.router)
app.include_router(records.router)
app.include_router(rankings.router)
