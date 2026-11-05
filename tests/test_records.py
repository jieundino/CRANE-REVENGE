"""STEP 3~6 확장: 기록 API, 5단계 스테이지, 랜덤 쓰레기 장애물(BFS), WASD/Space 키보드 조작 및 타이머 테스트."""

import os
from pathlib import Path
import random
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from backend.main import app
from frontend.app import (
    GRID_SIZE,
    INITIAL_PLAYER_POS,
    STAGE_CONFIG,
    TARGET_ATTACK_COUNT,
    TOTAL_STAGES,
    attack_claw,
    can_attack,
    generate_obstacles,
    get_elapsed_time,
    handle_keyboard_event,
    has_valid_path,
    init_game_state,
    move_player,
    start_new_game,
    submit_cleared_record,
)
from tests import ASGIClient


class TestRecordsAPI(unittest.TestCase):
    """STEP 3: POST /records 검증."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "subdir" / "test_records.db")
        os.environ["DATABASE_PATH"] = self.db_path
        self.client = ASGIClient(app)
        self.player_id = str(uuid.uuid4())
        self.client.post(
            "/players",
            json={"player_id": self.player_id, "nickname": "CLAW_HUNTER"},
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_submit_record_and_best_time_update_policy(self) -> None:
        # 1. 첫 기록 제출 -> 개인 최고 기록 달성
        r1 = self.client.post(
            "/records",
            json={"player_id": self.player_id, "clear_time": 25.40},
        )
        self.assertEqual(r1.status_code, 201)
        b1 = r1.json()
        self.assertTrue(b1["success"])
        self.assertTrue(b1["is_new_best"])
        self.assertEqual(b1["best_time"], 25.40)

        # 2. 더 느린 기록 제출 -> 전체 기록에는 추가되지만 최고 기록은 25.40 유지
        r2 = self.client.post(
            "/records",
            json={"player_id": self.player_id, "clear_time": 31.85},
        )
        self.assertEqual(r2.status_code, 201)
        b2 = r2.json()
        self.assertFalse(b2["is_new_best"])
        self.assertEqual(b2["best_time"], 25.40)

        # 3. 더 빠른 기록 제출 -> 최고 기록 18.12로 갱신
        r3 = self.client.post(
            "/records",
            json={"player_id": self.player_id, "clear_time": 18.12},
        )
        self.assertEqual(r3.status_code, 201)
        b3 = r3.json()
        self.assertTrue(b3["is_new_best"])
        self.assertEqual(b3["best_time"], 18.12)

        # 4. 개인 최고 기록 조회 시 총 3개의 기록이 모두 보관되어 있고 최고 기록이 18.12인지 확인
        best_res = self.client.get(f"/players/{self.player_id}/best")
        self.assertEqual(best_res.status_code, 200)
        best_body = best_res.json()
        self.assertTrue(best_body["has_record"])
        self.assertEqual(best_body["best_time"], 18.12)
        self.assertEqual(best_body["record_count"], 3)

    def test_submit_record_for_unknown_player_returns_404(self) -> None:
        res = self.client.post(
            "/records",
            json={"player_id": str(uuid.uuid4()), "clear_time": 15.0},
        )
        self.assertEqual(res.status_code, 404)

    def test_invalid_clear_times_rejected(self) -> None:
        for invalid_time in [0, -5.2, 0.05, 99999.0]:
            res = self.client.post(
                "/records",
                json={"player_id": self.player_id, "clear_time": invalid_time},
            )
            self.assertEqual(
                res.status_code,
                422,
                msg=f"clear_time={invalid_time} should be rejected with 422",
            )


class TestGameStateAndTimerLogic(unittest.TestCase):
    """STEP 4 & STEP 5 기존 테스트: 격자판 이동/범위 제한, 공격 조건, 타이머, 재시작, 중복 제출 방지 검증."""

    def test_grid_movement_boundaries_and_rerun_persistence(self) -> None:
        state: dict = {}
        query_params: dict = {}
        init_game_state(state, query_params)
        saved_player_id = state["player_id"]
        self.assertEqual(query_params.get("player_id"), saved_player_id)

        # 게임 시작 전에는 타이머가 0.0이고 이동 불가
        self.assertEqual(get_elapsed_time(state), 0.0)
        self.assertFalse(move_player(state, -1, 0))

        # 게임 시작 후 기본 이동 경계 검증을 위해 장애물 비움
        rng = random.Random(42)
        start_new_game(state, rng=rng)
        state["obstacles"] = set()
        self.assertTrue(state["game_started"])
        self.assertEqual(state["player_position"], INITIAL_PLAYER_POS)  # (4, 2)

        # 하단 경계(row=4)에서 아래(+1, 0)로 이동 시 격자판 바깥이므로 거부됨
        self.assertFalse(move_player(state, 1, 0))
        self.assertEqual(state["player_position"], (4, 2))

        # 위(-1, 0)로 이동 성공 -> (3, 2)
        self.assertTrue(move_player(state, -1, 0))
        self.assertEqual(state["player_position"], (3, 2))

        # 왼쪽 끝(col=0)까지 이동 후 한 번 더 왼쪽 이동 시 경계 차단 확인
        self.assertTrue(move_player(state, 0, -1))
        self.assertTrue(move_player(state, 0, -1))
        self.assertEqual(state["player_position"], (3, 0))
        self.assertFalse(move_player(state, 0, -1))
        self.assertEqual(state["player_position"], (3, 0))

        # Streamlit rerun 시뮬레이션: init_game_state를 다시 호출해도 기존 상태 유지
        init_game_state(state, query_params)
        self.assertEqual(state["player_id"], saved_player_id)
        self.assertEqual(state["player_position"], (3, 0))
        self.assertTrue(state["game_started"])

    def test_attack_condition_timer_clear_and_restart(self) -> None:
        state: dict = {}
        init_game_state(state)
        state["nickname"] = "BEAR_HERO"
        rng = random.Random(7)
        start_new_game(state, rng=rng)

        # 시작 시각을 인위적으로 12.34초 전으로 설정하여 타이머 계산 검증
        state["start_time"] = time.monotonic() - 12.34
        self.assertGreaterEqual(get_elapsed_time(state), 12.0)

        # 집게와 다른 위치일 때는 공격 불가
        state["player_position"] = (4, 4)
        state["claw_position"] = (0, 0)
        self.assertFalse(can_attack(state))
        self.assertFalse(attack_claw(state, rng=rng, auto_submit=False))
        self.assertEqual(state["attack_count"], 0)

        # STAGE 1에서 STAGE 5까지 순차 클리어
        for expected_stage in range(1, TOTAL_STAGES + 1):
            self.assertEqual(state["current_stage"], expected_stage)
            for hit in range(1, TARGET_ATTACK_COUNT):
                state["player_position"] = state["claw_position"]
                self.assertTrue(can_attack(state))
                self.assertTrue(attack_claw(state, rng=rng, auto_submit=False))
                self.assertEqual(state["attack_count"], hit)
                self.assertFalse(state["game_cleared"])
                self.assertNotEqual(state["player_position"], state["claw_position"])

            # 해당 스테이지의 3번째 공격
            state["player_position"] = state["claw_position"]
            self.assertTrue(attack_claw(state, rng=rng, auto_submit=False))
            if expected_stage < TOTAL_STAGES:
                # 중간 스테이지 클리어 -> 다음 스테이지로 이동 및 공격 횟수 초기화
                self.assertEqual(state["current_stage"], expected_stage + 1)
                self.assertEqual(state["attack_count"], 0)
                self.assertFalse(state["game_cleared"])
                self.assertTrue(state["game_started"])
            else:
                # 최종 STAGE 5 클리어 -> 게임 종료 및 타이머 정지
                self.assertTrue(state["game_cleared"])
                self.assertTrue(state["all_stages_cleared"])
                self.assertFalse(state["game_started"])
                self.assertIsNotNone(state["clear_time"])
                self.assertGreaterEqual(state["clear_time"], 12.0)
                self.assertEqual(state["screen"], "result")

        # 재시작 시 STAGE 1 및 이전 게임 상태 초기화 확인
        start_new_game(state, rng=rng)
        self.assertEqual(state["current_stage"], 1)
        self.assertTrue(state["game_started"])
        self.assertFalse(state["game_cleared"])
        self.assertEqual(state["attack_count"], 0)
        self.assertIsNone(state["clear_time"])
        self.assertFalse(state["record_submitted"])

    def test_prevent_duplicate_record_submission(self) -> None:
        state: dict = {}
        init_game_state(state)
        state["nickname"] = "ONCE_ONLY"
        state["game_cleared"] = True
        state["clear_time"] = 19.85

        with (
            patch("frontend.app.register_player") as mock_reg,
            patch(
                "frontend.app.submit_game_record",
                return_value={
                    "success": True,
                    "clear_time": 19.85,
                    "is_new_best": True,
                    "best_time": 19.85,
                    "message": "새로운 개인 최고 기록입니다.",
                },
            ) as mock_sub,
        ):
            self.assertTrue(submit_cleared_record(state))
            self.assertTrue(state["record_submitted"])
            self.assertEqual(mock_sub.call_count, 1)

            # 두 번째 호출 시 이미 record_submitted=True이므로 API가 다시 호출되지 않음
            self.assertTrue(submit_cleared_record(state))
            self.assertEqual(mock_sub.call_count, 1)
            self.assertEqual(mock_reg.call_count, 1)


class TestKeyboardObstaclesAndStages(unittest.TestCase):
    """신규 확장 기능 테스트: WASD/Space 키보드 조작, 쓰레기 장애물/BFS 경로 탐색, 5개 스테이지 및 기록 제출 정책."""

    def test_wasd_mapping_and_diagonal_blocking(self) -> None:
        state: dict = {}
        init_game_state(state)
        start_new_game(state, rng=random.Random(10))
        state["obstacles"] = set()
        state["player_position"] = (2, 2)

        # W: 위로 이동 -> (1, 2)
        self.assertTrue(
            handle_keyboard_event(
                state,
                {"key": "W", "event_id": "ev-1", "timestamp": 100.0},
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], (1, 2))

        # A: 왼쪽 이동 -> (1, 1)
        self.assertTrue(
            handle_keyboard_event(
                state,
                {"key": "a", "event_id": "ev-2", "timestamp": 101.0},
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], (1, 1))

        # S: 아래로 이동 -> (2, 1)
        self.assertTrue(
            handle_keyboard_event(
                state,
                {"key": "S", "event_id": "ev-3", "timestamp": 102.0},
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], (2, 1))

        # D: 오른쪽 이동 -> (2, 2)
        self.assertTrue(
            handle_keyboard_event(
                state,
                {"key": "d", "event_id": "ev-4", "timestamp": 103.0},
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], (2, 2))

        # 대각선 이동(dr=-1, dc=-1)이나 2칸 순간이동은 move_player에서 차단
        self.assertFalse(move_player(state, -1, -1))
        self.assertFalse(move_player(state, 0, 2))
        self.assertEqual(state["player_position"], (2, 2))

    def test_space_attack_and_duplicate_or_repeat_or_focus_or_inactive_ignored(self) -> None:
        state: dict = {}
        init_game_state(state)

        # 1. 게임 시작 전에는 키 입력 무시
        self.assertFalse(
            handle_keyboard_event(state, {"key": "W", "event_id": "pre-1", "timestamp": 1.0})
        )

        rng = random.Random(99)
        start_new_game(state, rng=rng)
        state["obstacles"] = set()
        state["player_position"] = (2, 2)
        state["claw_position"] = (2, 2)

        # 2. 텍스트 입력창 포커스 중(is_input_focused=True)일 때는 무시
        self.assertFalse(
            handle_keyboard_event(
                state,
                {
                    "key": "W",
                    "event_id": "focus-1",
                    "timestamp": 10.0,
                    "is_input_focused": True,
                },
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], (2, 2))

        # 3. 키 누름 유지 자동 반복(repeat=True)일 때는 이동/공격 무시
        self.assertFalse(
            handle_keyboard_event(
                state,
                {"key": "W", "event_id": "rep-1", "timestamp": 11.0, "repeat": True},
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], (2, 2))

        # 4. Space 공격 이벤트가 정확히 1회만 적용되고 동일 event_id 재전달 시 무시
        self.assertTrue(
            handle_keyboard_event(
                state,
                {"key": "SPACE", "event_id": "atk-1", "timestamp": 12.0},
                rng=rng,
                auto_submit=False,
            )
        )
        self.assertEqual(state["attack_count"], 1)

        # 동일 event_id 중복 이벤트는 무시됨
        self.assertFalse(
            handle_keyboard_event(
                state,
                {"key": "SPACE", "event_id": "atk-1", "timestamp": 13.0},
                rng=rng,
                auto_submit=False,
            )
        )
        self.assertEqual(state["attack_count"], 1)

        # 5. 너무 빠른 연속 입력(쿨다운 미만 간격) 시 무시
        pos_before = state["player_position"]
        self.assertFalse(
            handle_keyboard_event(
                state,
                {"key": "W", "event_id": "fast-1", "timestamp": 12.02},
                auto_submit=False,
            )
        )
        self.assertEqual(state["player_position"], pos_before)

        # 6. 게임이 종료된 상태(game_cleared=True)에서는 키 입력 무시
        state["game_cleared"] = True
        state["game_started"] = False
        self.assertFalse(
            handle_keyboard_event(
                state,
                {"key": "W", "event_id": "post-1", "timestamp": 20.0},
                auto_submit=False,
            )
        )

    def test_obstacle_blocking_and_bfs_reachability_across_multiple_seeds(self) -> None:
        # 장애물이 있는 칸으로 이동할 수 없고 통과할 수 없는지 확인
        state: dict = {}
        init_game_state(state)
        start_new_game(state, rng=random.Random(1))
        state["player_position"] = (2, 2)
        state["obstacles"] = {(1, 2)}  # 바로 위 칸에 쓰레기 장애물 배치

        self.assertFalse(move_player(state, -1, 0))
        self.assertEqual(state["player_position"], (2, 2))
        self.assertIn("쓰레기 장애물", state["action_feedback"])

        # 우회 경로((2, 1) -> (1, 1) -> (0, 1))로는 정상 이동 가능
        self.assertTrue(move_player(state, 0, -1))
        self.assertEqual(state["player_position"], (2, 1))
        self.assertTrue(move_player(state, -1, 0))
        self.assertEqual(state["player_position"], (1, 1))

        # 5개 스테이지 설정에 대해 50개의 서로 다른 시드로 반복 생성해도
        # 항상 장애물 개수가 일치하고, 플레이어/집게와 겹치지 않으며, BFS 유효 경로가 존재하는지 검증
        for stage_num, cfg in STAGE_CONFIG.items():
            grid_size = cfg["grid_size"]
            obs_count = cfg["obstacle_count"]
            for seed in range(50):
                rng = random.Random(stage_num * 1000 + seed)
                p_pos = (grid_size - 1, grid_size // 2)
                c_pos = (0, seed % grid_size)
                obstacles = generate_obstacles(
                    grid_size=grid_size,
                    obstacle_count=obs_count,
                    start_position=p_pos,
                    target_position=c_pos,
                    rng=rng,
                )
                self.assertEqual(len(obstacles), obs_count)
                self.assertNotIn(p_pos, obstacles)
                self.assertNotIn(c_pos, obstacles)
                self.assertTrue(
                    has_valid_path(grid_size, p_pos, c_pos, obstacles),
                    msg=f"Stage {stage_num} seed {seed} failed BFS path check",
                )

        # 경로가 완전히 막힌 경우 has_valid_path가 False를 반환하는지 검증
        blocked_obstacles = {(3, 2), (4, 1), (4, 3)}
        self.assertFalse(has_valid_path(5, (4, 2), (0, 2), blocked_obstacles))

    def test_five_stage_config_progression_and_single_record_submission_at_stage_5(self) -> None:
        # 1. 총 5개 스테이지 및 설정값 확인
        self.assertEqual(TOTAL_STAGES, 5)
        expected_configs = {
            1: {"grid_size": 5, "obstacle_count": 2},
            2: {"grid_size": 6, "obstacle_count": 5},
            3: {"grid_size": 7, "obstacle_count": 9},
            4: {"grid_size": 8, "obstacle_count": 14},
            5: {"grid_size": 10, "obstacle_count": 22},
        }
        self.assertEqual(STAGE_CONFIG, expected_configs)

        state: dict = {}
        init_game_state(state)
        state["nickname"] = "STAGE_MASTER"
        rng = random.Random(2026)
        start_new_game(state, rng=rng)

        initial_start_time = state["start_time"]
        state["start_time"] = initial_start_time - 35.0  # 누적 타이머 검증용

        with (
            patch("frontend.app.register_player") as mock_reg,
            patch(
                "frontend.app.submit_game_record",
                return_value={
                    "success": True,
                    "clear_time": 35.0,
                    "is_new_best": True,
                    "best_time": 35.0,
                    "message": "새로운 개인 최고 기록입니다.",
                },
            ) as mock_submit,
        ):
            for stage_idx in range(1, TOTAL_STAGES + 1):
                self.assertEqual(state["current_stage"], stage_idx)
                self.assertEqual(state["grid_size"], expected_configs[stage_idx]["grid_size"])
                self.assertEqual(
                    len(state["obstacles"]),
                    expected_configs[stage_idx]["obstacle_count"],
                )
                self.assertTrue(
                    has_valid_path(
                        state["grid_size"],
                        state["player_position"],
                        state["claw_position"],
                        state["obstacles"],
                    )
                )

                # 각 스테이지에서 3회 공격 수행
                for hit in range(1, TARGET_ATTACK_COUNT + 1):
                    state["player_position"] = state["claw_position"]
                    self.assertTrue(
                        handle_keyboard_event(
                            state,
                            {
                                "key": "SPACE",
                                "event_id": f"stage-{stage_idx}-hit-{hit}",
                                "timestamp": float(stage_idx * 10 + hit),
                            },
                            rng=rng,
                            auto_submit=True,
                        )
                    )

                if stage_idx < TOTAL_STAGES:
                    # 중간 스테이지(STAGE 1~4) 클리어 시:
                    # - 기록이 API에 제출되지 않아야 함
                    # - 전체 타이머(start_time)가 초기화되지 않고 유지되어야 함
                    # - 다음 스테이지로 이동하고 공격 횟수가 0으로 초기화되어야 함
                    self.assertEqual(mock_submit.call_count, 0)
                    self.assertEqual(state["start_time"], initial_start_time - 35.0)
                    self.assertEqual(state["current_stage"], stage_idx + 1)
                    self.assertEqual(state["attack_count"], 0)
                    self.assertFalse(state["game_cleared"])
                else:
                    # 최종 스테이지(STAGE 5) 클리어 시:
                    # - 전체 클리어 시간이 정확히 1회 제출되어야 함
                    self.assertTrue(state["game_cleared"])
                    self.assertTrue(state["all_stages_cleared"])
                    self.assertTrue(state["record_submitted"])
                    self.assertEqual(mock_submit.call_count, 1)
                    self.assertEqual(mock_reg.call_count, 1)
                    submitted_time = mock_submit.call_args.kwargs["clear_time"]
                    self.assertGreaterEqual(submitted_time, 35.0)


if __name__ == "__main__":
    unittest.main()
