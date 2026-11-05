"""STEP 3 & STEP 6: TOP 10 랭킹 조회, 프론트엔드-백엔드 연동 및 예외 처리 테스트."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import httpx

from backend.main import app
from frontend import api_client
from frontend.api_client import APIClientError
from frontend.app import init_game_state, submit_cleared_record
from tests import ASGIClient, ASGIResponse


class TestRankingsAPI(unittest.TestCase):
    """STEP 3: GET /rankings 정렬, 동점자 처리, limit 및 DB 파일 유지 검증."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_rankings.db")
        os.environ["DATABASE_PATH"] = self.db_path
        self.client = ASGIClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rankings_order_and_tie_breaking_and_persistence(self) -> None:
        p1 = str(uuid.uuid4())
        p2 = str(uuid.uuid4())
        p3 = str(uuid.uuid4())

        self.client.post("/players", json={"player_id": p1, "nickname": "PLAYER_1"})
        self.client.post("/players", json={"player_id": p2, "nickname": "PLAYER_2"})
        self.client.post("/players", json={"player_id": p3, "nickname": "PLAYER_3"})

        # P1: 20.0초 후 15.0초 달성
        self.client.post("/records", json={"player_id": p1, "clear_time": 20.0})
        self.client.post("/records", json={"player_id": p1, "clear_time": 15.0})

        # P2: 12.5초 달성 후 18.0초(더 느린 기록)
        self.client.post("/records", json={"player_id": p2, "clear_time": 12.5})
        self.client.post("/records", json={"player_id": p2, "clear_time": 18.0})

        # P3: P1과 동일한 15.0초를 나중에 달성 -> 동점 시 먼저 달성한 P1이 앞순위여야 함
        self.client.post("/records", json={"player_id": p3, "clear_time": 15.0})

        # 새 ASGIClient 인스턴스로 DB 파일 재연결 후에도 데이터가 유지되는지 확인
        new_client = ASGIClient(app)
        res = new_client.get("/rankings?limit=10")
        self.assertEqual(res.status_code, 200)
        rankings = res.json()["rankings"]

        self.assertEqual(len(rankings), 3)
        self.assertEqual(rankings[0]["rank"], 1)
        self.assertEqual(rankings[0]["player_id"], p2)
        self.assertEqual(rankings[0]["best_time"], 12.5)

        self.assertEqual(rankings[1]["rank"], 2)
        self.assertEqual(rankings[1]["player_id"], p1)
        self.assertEqual(rankings[1]["best_time"], 15.0)

        self.assertEqual(rankings[2]["rank"], 3)
        self.assertEqual(rankings[2]["player_id"], p3)
        self.assertEqual(rankings[2]["best_time"], 15.0)


class TestFrontendBackendIntegration(unittest.TestCase):
    """STEP 6: Streamlit(api_client/app) <-> FastAPI 연동 및 서버 장애/오류 응답 예외 처리 검증."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_integration.db")
        os.environ["DATABASE_PATH"] = self.db_path
        self.asgi_client = ASGIClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _bridge_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        timeout: float = 5.0,
    ) -> dict:
        """api_client._request가 ASGIClient를 통해 실제 FastAPI 라우터와 SQLite를 호출하도록 연결."""
        full_path = path
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            full_path = f"{path}?{query}"
        resp: ASGIResponse = self.asgi_client.request(method, full_path, json_body=json_body)
        if resp.status_code >= 400:
            detail = resp.json().get("detail", "오류")
            raise APIClientError(str(detail), status_code=resp.status_code)
        return resp.json()

    def test_end_to_end_two_browsers_share_same_rankings(self) -> None:
        with patch.object(api_client, "_request", side_effect=self._bridge_request):
            # 브라우저 A 플레이어 세션
            browser_a: dict = {}
            init_game_state(browser_a)
            browser_a["nickname"] = "BROWSER_A"
            browser_a["game_cleared"] = True
            browser_a["clear_time"] = 22.45
            self.assertTrue(submit_cleared_record(browser_a))
            self.assertTrue(browser_a["record_submitted"])
            self.assertEqual(browser_a["current_best_time"], 22.45)

            # 브라우저 B 플레이어 세션 (더 빠른 기록 달성)
            browser_b: dict = {}
            init_game_state(browser_b)
            browser_b["nickname"] = "BROWSER_B"
            browser_b["game_cleared"] = True
            browser_b["clear_time"] = 14.10
            self.assertTrue(submit_cleared_record(browser_b))
            self.assertTrue(browser_b["record_submitted"])
            self.assertEqual(browser_b["current_best_time"], 14.10)

            # 두 브라우저에서 각각 랭킹 조회 시 동일한 서버 랭킹 확인
            rankings_from_a = api_client.fetch_rankings(limit=10)
            rankings_from_b = api_client.fetch_rankings(limit=10)
            self.assertEqual(rankings_from_a, rankings_from_b)
            self.assertEqual(len(rankings_from_a), 2)
            self.assertEqual(rankings_from_a[0]["nickname"], "BROWSER_B")
            self.assertEqual(rankings_from_a[0]["best_time"], 14.10)
            self.assertEqual(rankings_from_a[1]["nickname"], "BROWSER_A")
            self.assertEqual(rankings_from_a[1]["best_time"], 22.45)

    def test_api_server_down_shows_friendly_error_and_does_not_mark_submitted(self) -> None:
        state: dict = {}
        init_game_state(state)
        state["nickname"] = "OFFLINE_USER"
        state["game_cleared"] = True
        state["clear_time"] = 16.50

        with patch("httpx.Client.request", side_effect=httpx.ConnectError("Connection refused")):
            ok = submit_cleared_record(state)
            self.assertFalse(ok)
            # 요청 실패 시 기록이 저장된 것처럼 표시하지 않음
            self.assertFalse(state["record_submitted"])
            self.assertIsNotNone(state["submission_error"])
            self.assertIn("연결할 수 없습니다", state["submission_error"])

    def test_malformed_api_response_raises_api_client_error(self) -> None:
        mock_response = httpx.Response(status_code=200, content=b"not-valid-json")
        with patch("httpx.Client.request", return_value=mock_response):
            with self.assertRaises(APIClientError) as ctx:
                api_client.fetch_rankings()
            self.assertIn("올바르지 않은 형식", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
