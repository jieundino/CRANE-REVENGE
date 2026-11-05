"""STEP 3: 플레이어 등록, 조회 및 입력 검증 테스트."""

import os
from pathlib import Path
import tempfile
import unittest
import uuid

from backend.main import app
from tests import ASGIClient


class TestPlayersAPI(unittest.TestCase):
    """POST /players 및 GET /players/{player_id}/best 검증."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_players.db")
        os.environ["DATABASE_PATH"] = self.db_path
        self.client = ASGIClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_register_new_player_and_update_existing(self) -> None:
        player_id = str(uuid.uuid4())
        res1 = self.client.post(
            "/players",
            json={"player_id": player_id, "nickname": "ANGRY_BEAR"},
        )
        self.assertEqual(res1.status_code, 200)
        body1 = res1.json()
        self.assertEqual(body1["player_id"], player_id)
        self.assertEqual(body1["nickname"], "ANGRY_BEAR")
        self.assertTrue(body1["is_new"])

        # 동일 UUID로 재요청 시 신규 생성이 아닌 기존 플레이어 닉네임 갱신
        res2 = self.client.post(
            "/players",
            json={"player_id": player_id, "nickname": "SUPER_BEAR"},
        )
        self.assertEqual(res2.status_code, 200)
        body2 = res2.json()
        self.assertEqual(body2["player_id"], player_id)
        self.assertEqual(body2["nickname"], "SUPER_BEAR")
        self.assertFalse(body2["is_new"])
        self.assertEqual(body1["created_at"], body2["created_at"])

    def test_duplicate_nickname_allowed_for_different_uuid(self) -> None:
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        r1 = self.client.post("/players", json={"player_id": id1, "nickname": "집게파괴자"})
        r2 = self.client.post("/players", json={"player_id": id2, "nickname": "집게파괴자"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertNotEqual(r1.json()["player_id"], r2.json()["player_id"])

    def test_invalid_uuid_rejected(self) -> None:
        res = self.client.post(
            "/players",
            json={"player_id": "not-a-valid-uuid", "nickname": "TESTER"},
        )
        self.assertEqual(res.status_code, 422)

    def test_invalid_nickname_rejected(self) -> None:
        player_id = str(uuid.uuid4())
        # 빈 문자열
        r_empty = self.client.post(
            "/players",
            json={"player_id": player_id, "nickname": "   "},
        )
        self.assertEqual(r_empty.status_code, 422)

        # 스크립트/HTML 태그 삽입 시도
        r_xss = self.client.post(
            "/players",
            json={"player_id": player_id, "nickname": "<script>alert(1)</script>"},
        )
        self.assertEqual(r_xss.status_code, 422)

        # 20자 초과
        r_long = self.client.post(
            "/players",
            json={"player_id": player_id, "nickname": "A" * 25},
        )
        self.assertEqual(r_long.status_code, 422)

    def test_get_player_best_without_records(self) -> None:
        player_id = str(uuid.uuid4())
        self.client.post("/players", json={"player_id": player_id, "nickname": "NO_RECORD"})
        res = self.client.get(f"/players/{player_id}/best")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["has_record"])
        self.assertIsNone(body["best_time"])
        self.assertEqual(body["record_count"], 0)

    def test_get_player_best_unregistered_returns_404(self) -> None:
        unknown_id = str(uuid.uuid4())
        res = self.client.get(f"/players/{unknown_id}/best")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
