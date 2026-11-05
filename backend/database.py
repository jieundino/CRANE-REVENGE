"""CRANE REVENGE SQLite 데이터베이스 연결, 초기화 및 쿼리 모듈."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator

DEFAULT_DATABASE_PATH = "./data/crane_revenge.db"


def get_database_path(db_path: str | None = None) -> Path:
    """환경 변수 DATABASE_PATH 또는 인자로 전달된 SQLite DB 파일 경로를 반환한다."""
    raw_path = db_path or os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
    return Path(raw_path).resolve()


def ensure_db_directory(db_path: Path) -> None:
    """DB 파일이 위치할 부모 디렉터리가 없으면 생성한다."""
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db_connection(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """외래 키 제약과 트랜잭션이 적용된 SQLite 연결 컨텍스트 매니저."""
    resolved_path = get_database_path(db_path)
    ensure_db_directory(resolved_path)

    conn = sqlite3.connect(str(resolved_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """데이터베이스 파일 및 players, game_records 테이블과 인덱스를 초기화한다."""
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL,
                created_at DATETIME NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                clear_time REAL NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (player_id) REFERENCES players(player_id)
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_game_records_player_time
            ON game_records (player_id, clear_time);
            """
        )


def _utc_now_iso() -> str:
    """현재 UTC 시각을 ISO-8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


def upsert_player(
    player_id: str,
    nickname: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """플레이어를 등록하거나 기존 플레이어가 있으면 닉네임을 갱신하고 정보를 반환한다."""
    init_db(db_path)
    now_iso = _utc_now_iso()

    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT player_id, nickname, created_at FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO players (player_id, nickname, created_at) VALUES (?, ?, ?)",
                (player_id, nickname, now_iso),
            )
            return {
                "player_id": player_id,
                "nickname": nickname,
                "created_at": now_iso,
                "is_new": True,
            }

        if row["nickname"] != nickname:
            conn.execute(
                "UPDATE players SET nickname = ? WHERE player_id = ?",
                (nickname, player_id),
            )

        return {
            "player_id": row["player_id"],
            "nickname": nickname,
            "created_at": row["created_at"],
            "is_new": False,
        }


def get_player(player_id: str, db_path: str | None = None) -> dict[str, Any] | None:
    """player_id로 플레이어 정보를 조회한다."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT player_id, nickname, created_at FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def create_game_record(
    player_id: str,
    clear_time: float,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """게임 클리어 기록을 저장하고 개인 최고 기록 갱신 여부와 최고 기록을 반환한다.

    플레이어가 존재하지 않으면 None을 반환한다.
    모든 플레이 기록은 삭제/덮어쓰기 없이 game_records에 누적 저장된다.
    """
    init_db(db_path)
    rounded_time = round(float(clear_time), 2)
    now_iso = _utc_now_iso()

    with get_db_connection(db_path) as conn:
        player_row = conn.execute(
            "SELECT player_id FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        if player_row is None:
            return None

        prev_row = conn.execute(
            "SELECT MIN(clear_time) AS best_time FROM game_records WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        previous_best = (
            round(float(prev_row["best_time"]), 2)
            if prev_row and prev_row["best_time"] is not None
            else None
        )

        conn.execute(
            """
            INSERT INTO game_records (player_id, clear_time, created_at)
            VALUES (?, ?, ?)
            """,
            (player_id, rounded_time, now_iso),
        )

        if previous_best is None or rounded_time < previous_best:
            is_new_best = True
            best_time = rounded_time
            message = "새로운 개인 최고 기록입니다."
        else:
            is_new_best = False
            best_time = previous_best
            message = "기록이 저장되었습니다. (기존 개인 최고 기록 유지)"

        return {
            "success": True,
            "clear_time": rounded_time,
            "is_new_best": is_new_best,
            "best_time": best_time,
            "message": message,
        }


def get_player_best_record(
    player_id: str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """특정 플레이어의 개인 최고 기록을 조회한다.

    플레이어가 존재하지 않으면 None을 반환하고,
    플레이어는 존재하나 기록이 없으면 best_time=None, has_record=False를 반환한다.
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        player_row = conn.execute(
            "SELECT player_id, nickname FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        if player_row is None:
            return None

        best_row = conn.execute(
            """
            SELECT MIN(clear_time) AS best_time, COUNT(*) AS record_count
            FROM game_records
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        has_record = bool(best_row and best_row["best_time"] is not None)
        best_time = (
            round(float(best_row["best_time"]), 2) if has_record else None
        )
        record_count = int(best_row["record_count"]) if best_row else 0

        return {
            "player_id": player_row["player_id"],
            "nickname": player_row["nickname"],
            "has_record": has_record,
            "best_time": best_time,
            "record_count": record_count,
        }


def get_top_rankings(
    limit: int = 10,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """플레이어별 최고 기록(MIN(clear_time))을 오름차순으로 정렬하여 상위 랭킹을 반환한다.

    동일 기록일 경우 해당 최고 기록을 먼저 달성한 순서(MIN(record_id))로 정렬한다.
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            """
            WITH player_best AS (
                SELECT
                    player_id,
                    MIN(clear_time) AS best_time
                FROM game_records
                GROUP BY player_id
            ),
            best_achieved AS (
                SELECT
                    gr.player_id,
                    pb.best_time,
                    MIN(gr.record_id) AS first_best_record_id
                FROM game_records gr
                JOIN player_best pb
                  ON gr.player_id = pb.player_id
                 AND gr.clear_time = pb.best_time
                GROUP BY gr.player_id, pb.best_time
            )
            SELECT
                p.player_id,
                p.nickname,
                ba.best_time
            FROM best_achieved ba
            JOIN players p ON p.player_id = ba.player_id
            ORDER BY ba.best_time ASC, ba.first_best_record_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        rankings: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=1):
            rankings.append(
                {
                    "rank": idx,
                    "player_id": row["player_id"],
                    "nickname": row["nickname"],
                    "best_time": round(float(row["best_time"]), 2),
                }
            )
        return rankings
