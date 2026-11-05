"""CRANE REVENGE 순수 Python 게임 규칙, 5단계 스테이지, 장애물 생성(BFS 검증) 및 키보드 입력 처리 모듈.

이 모듈은 Streamlit에 의존하지 않으므로 단위 테스트에서 독립적으로 검증할 수 있다.
"""

from collections import deque
from collections.abc import Callable, MutableMapping
import random
import time
from typing import Any
import uuid

from backend.models import validate_uuid_string

# =====================================================================
# 스테이지 및 게임 설정 상수 (Section 4.1, 4.2)
# =====================================================================
STAGE_CONFIG: dict[int, dict[str, int]] = {
    1: {"grid_size": 5, "obstacle_count": 2},
    2: {"grid_size": 6, "obstacle_count": 5},
    3: {"grid_size": 7, "obstacle_count": 9},
    4: {"grid_size": 8, "obstacle_count": 14},
    5: {"grid_size": 10, "obstacle_count": 22},
}

TOTAL_STAGES: int = len(STAGE_CONFIG)
GRID_SIZE: int = STAGE_CONFIG[1]["grid_size"]  # 기본(STAGE 1) 격자 크기: 5
TARGET_ATTACK_COUNT: int = 3
INITIAL_PLAYER_POS: tuple[int, int] = (GRID_SIZE - 1, GRID_SIZE // 2)  # (4, 2)

# 키보드 연속 입력 최소 간격(초) — 과도한 반복 이동 방지
KEY_INPUT_COOLDOWN_SECONDS: float = 0.08

# 방향키 매핑 (WASD, 키 코드, 한글 두벌식 대응)
DIRECTION_KEY_MAP: dict[str, tuple[int, int]] = {
    "W": (-1, 0),
    "KEYW": (-1, 0),
    "ㅈ": (-1, 0),
    "A": (0, -1),
    "KEYA": (0, -1),
    "ㅁ": (0, -1),
    "S": (1, 0),
    "KEYS": (1, 0),
    "ㄴ": (1, 0),
    "D": (0, 1),
    "KEYD": (0, 1),
    "ㅇ": (0, 1),
}

ATTACK_KEYS: set[str] = {"SPACE", " ", "SPACEBAR"}


def get_stage_settings(stage: int) -> dict[str, int]:
    """스테이지 번호에 해당하는 격자 크기(grid_size)와 장애물 수(obstacle_count)를 반환한다."""
    if stage in STAGE_CONFIG:
        return dict(STAGE_CONFIG[stage])
    max_stage = max(STAGE_CONFIG.keys())
    return dict(STAGE_CONFIG[max_stage])


def get_initial_player_pos(grid_size: int = GRID_SIZE) -> tuple[int, int]:
    """주어진 격자 크기에서 플레이어 시작 위치(하단 중앙)를 반환한다."""
    return (grid_size - 1, grid_size // 2)


# =====================================================================
# 경로 탐색(BFS) 및 랜덤 쓰레기 장애물 생성 (Section 3.3, 3.4)
# =====================================================================
def has_valid_path(
    grid_size: int,
    start_position: tuple[int, int],
    target_position: tuple[int, int],
    obstacles: set[tuple[int, int]],
) -> bool:
    """BFS(너비 우선 탐색)를 사용해 시작 위치에서 목표 위치까지 도달 가능한지 검증한다."""
    start = tuple(start_position)
    target = tuple(target_position)
    obstacle_set = {tuple(pos) for pos in obstacles}

    if not (0 <= start[0] < grid_size and 0 <= start[1] < grid_size):
        return False
    if not (0 <= target[0] < grid_size and 0 <= target[1] < grid_size):
        return False
    if start in obstacle_set or target in obstacle_set:
        return False
    if start == target:
        return True

    visited: set[tuple[int, int]] = {start}
    queue: deque[tuple[int, int]] = deque([start])

    while queue:
        cur_r, cur_c = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = cur_r + dr, cur_c + dc
            nxt = (nr, nc)
            if not (0 <= nr < grid_size and 0 <= nc < grid_size):
                continue
            if nxt in obstacle_set or nxt in visited:
                continue
            if nxt == target:
                return True
            visited.add(nxt)
            queue.append(nxt)

    return False


def _build_guaranteed_path(
    grid_size: int,
    start: tuple[int, int],
    target: tuple[int, int],
    chooser: Any,
) -> set[tuple[int, int]]:
    """재시도 초과 시 시작점에서 목표점까지의 보장된 이동 경로 좌표 집합을 생성한다."""
    cur_r, cur_c = start
    tgt_r, tgt_c = target
    path_cells: set[tuple[int, int]] = {(cur_r, cur_c), (tgt_r, tgt_c)}

    steps: list[tuple[int, int]] = []
    dr = 1 if tgt_r > cur_r else -1
    dc = 1 if tgt_c > cur_c else -1
    for _ in range(abs(tgt_r - cur_r)):
        steps.append((dr, 0))
    for _ in range(abs(tgt_c - cur_c)):
        steps.append((0, dc))

    chooser.shuffle(steps)
    for step_r, step_c in steps:
        cur_r += step_r
        cur_c += step_c
        if 0 <= cur_r < grid_size and 0 <= cur_c < grid_size:
            path_cells.add((cur_r, cur_c))

    return path_cells


def generate_obstacles(
    grid_size: int,
    obstacle_count: int,
    start_position: tuple[int, int],
    target_position: tuple[int, int],
    rng: random.Random | None = None,
    max_retries: int = 100,
) -> set[tuple[int, int]]:
    """시작 위치와 집게 위치를 제외하고 도달 가능한 경로가 보장된 랜덤 쓰레기 장애물을 생성한다."""
    chooser = rng or random
    start = tuple(start_position)
    target = tuple(target_position)

    all_candidates = [
        (r, c)
        for r in range(grid_size)
        for c in range(grid_size)
        if (r, c) != start and (r, c) != target
    ]
    target_count = min(max(0, int(obstacle_count)), len(all_candidates))
    if target_count == 0:
        return set()

    for _ in range(max(1, max_retries)):
        sampled = set(chooser.sample(all_candidates, target_count))
        if has_valid_path(grid_size, start, target, sampled):
            return sampled

    # 재시도 횟수 초과 시 안전한 대체 방식: 보장된 경로를 먼저 확보한 뒤 나머지 빈 공간에 장애물 배치
    reserved_path = _build_guaranteed_path(grid_size, start, target, chooser)
    safe_candidates = [pos for pos in all_candidates if pos not in reserved_path]
    safe_count = min(target_count, len(safe_candidates))
    return set(chooser.sample(safe_candidates, safe_count))


def spawn_claw_position(
    exclude_pos: tuple[int, int],
    grid_size: int = GRID_SIZE,
    rng: random.Random | None = None,
    obstacles: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """플레이어 위치 및 장애물과 겹치지 않으며 도달 가능한 무작위 집게 좌표를 생성한다."""
    chooser = rng or random
    player_pos = tuple(exclude_pos)
    obstacle_set = {tuple(p) for p in obstacles} if obstacles else set()

    candidates = [
        (r, c)
        for r in range(grid_size)
        for c in range(grid_size)
        if (r, c) != player_pos and (r, c) not in obstacle_set
    ]
    if not candidates:
        return (0, 0) if player_pos != (0, 0) else (0, min(1, grid_size - 1))

    if obstacle_set:
        reachable = [
            pos
            for pos in candidates
            if has_valid_path(grid_size, player_pos, pos, obstacle_set)
        ]
        if reachable:
            return chooser.choice(reachable)

    return chooser.choice(candidates)


# =====================================================================
# 플레이어 UUID 및 세션 상태 초기화 (Section 4.3, 5.1)
# =====================================================================
def get_or_create_player_id(query_params: MutableMapping[str, Any] | None = None) -> str:
    """URL 쿼리 파라미터에서 UUID를 재사용하거나 유효하지 않으면 새로 생성한다."""
    if query_params is not None:
        raw_id = query_params.get("player_id")
        if isinstance(raw_id, list):
            raw_id = raw_id[0] if raw_id else None
        if isinstance(raw_id, str):
            try:
                return validate_uuid_string(raw_id)
            except ValueError:
                pass

    new_id = str(uuid.uuid4())
    if query_params is not None:
        try:
            query_params["player_id"] = new_id
        except Exception:
            pass
    return new_id


def init_game_state(
    state: MutableMapping[str, Any],
    query_params: MutableMapping[str, Any] | None = None,
) -> None:
    """Streamlit rerun 이후에도 상태가 초기화되지 않도록 기본 세션 키를 보장한다."""
    if "player_id" not in state or not state["player_id"]:
        state["player_id"] = get_or_create_player_id(query_params)
    elif query_params is not None and query_params.get("player_id") != state["player_id"]:
        try:
            query_params["player_id"] = state["player_id"]
        except Exception:
            pass

    stage1 = get_stage_settings(1)
    defaults: dict[str, Any] = {
        "nickname": "",
        "screen": "main",  # main | prologue | game | result | ranking
        "current_stage": 1,
        "total_stages": TOTAL_STAGES,
        "grid_size": stage1["grid_size"],
        "obstacle_count": stage1["obstacle_count"],
        "obstacles": set(),
        "game_started": False,
        "game_cleared": False,
        "all_stages_cleared": False,
        "player_position": get_initial_player_pos(stage1["grid_size"]),
        "claw_position": (0, stage1["grid_size"] // 2),
        "attack_count": 0,
        "start_time": None,
        "clear_time": None,
        "record_submitted": False,
        "current_best_time": None,
        "is_new_best": False,
        "submission_message": "",
        "submission_error": None,
        "last_key_event_id": None,
        "last_key_timestamp": None,
        "action_feedback": "WASD 키 또는 방향 버튼으로 쓰레기(🗑️)를 피해 집게(🕹️)까지 이동하세요!",
    }
    for key, default_val in defaults.items():
        if key not in state:
            state[key] = default_val


# =====================================================================
# 스테이지 초기화, 이동, 공격 및 타이머 로직 (Section 4, 5)
# =====================================================================
def setup_stage(
    state: MutableMapping[str, Any],
    stage: int,
    rng: random.Random | None = None,
) -> None:
    """지정한 스테이지 번호에 맞춰 격자 크기, 플레이어/집게 좌표, 쓰레기 장애물을 새로 생성한다.

    전체 게임 경과 시간(start_time)은 초기화하지 않는다.
    """
    settings = get_stage_settings(stage)
    grid_size = settings["grid_size"]
    obstacle_count = settings["obstacle_count"]

    player_pos = get_initial_player_pos(grid_size)
    claw_pos = spawn_claw_position(player_pos, grid_size, rng=rng, obstacles=None)
    obstacles = generate_obstacles(
        grid_size=grid_size,
        obstacle_count=obstacle_count,
        start_position=player_pos,
        target_position=claw_pos,
        rng=rng,
    )

    state["current_stage"] = stage
    state["total_stages"] = int(state.get("total_stages") or TOTAL_STAGES)
    state["grid_size"] = grid_size
    state["obstacle_count"] = obstacle_count
    state["player_position"] = player_pos
    state["claw_position"] = claw_pos
    state["obstacles"] = obstacles
    state["attack_count"] = 0
    state["game_started"] = True
    state["game_cleared"] = False


def start_new_game(
    state: MutableMapping[str, Any],
    rng: random.Random | None = None,
    total_stages: int = TOTAL_STAGES,
) -> None:
    """STAGE 1부터 새 게임을 시작하며 전체 타이머(time.monotonic())와 상태를 초기화한다."""
    state["total_stages"] = total_stages
    setup_stage(state, stage=1, rng=rng)
    state["all_stages_cleared"] = False
    state["start_time"] = time.monotonic()
    state["clear_time"] = None
    state["record_submitted"] = False
    state["is_new_best"] = False
    state["submission_message"] = ""
    state["submission_error"] = None
    state["last_key_event_id"] = None
    state["last_key_timestamp"] = None
    state["action_feedback"] = (
        f"STAGE 1 / {total_stages} 시작! 쓰레기 장애물(🗑️)을 피해 집게(🕹️)를 추격하세요!"
    )
    state["screen"] = "game"


def advance_to_next_stage(
    state: MutableMapping[str, Any],
    rng: random.Random | None = None,
) -> int:
    """현재 스테이지 클리어 후 다음 스테이지로 이동하며 새로운 맵을 생성한다."""
    next_stage = int(state.get("current_stage", 1)) + 1
    total_stages = int(state.get("total_stages", TOTAL_STAGES))
    setup_stage(state, stage=next_stage, rng=rng)
    state["action_feedback"] = (
        f"🎉 STAGE {next_stage - 1} 클리어! "
        f"STAGE {next_stage} / {total_stages} ({state['grid_size']}×{state['grid_size']}, "
        f"장애물 {state['obstacle_count']}개) 시작!"
    )
    return next_stage


def get_elapsed_time(state: MutableMapping[str, Any]) -> float:
    """현재 진행 중인 전체 게임의 경과 시간(초)을 계산한다."""
    if state.get("game_cleared") and state.get("clear_time") is not None:
        return float(state["clear_time"])
    if not state.get("game_started") or state.get("start_time") is None:
        return 0.0
    elapsed = time.monotonic() - float(state["start_time"])
    return round(max(0.0, elapsed), 2)


def format_elapsed_time(seconds: float) -> str:
    """경과 시간(초)을 MM:SS.xx 형식(예: 00:42.51)으로 반환한다."""
    safe_sec = max(0.0, float(seconds))
    minutes = int(safe_sec // 60)
    rem_sec = safe_sec - (minutes * 60)
    return f"{minutes:02d}:{rem_sec:05.2f}"


def move_player(state: MutableMapping[str, Any], dr: int, dc: int) -> bool:
    """상하좌우로 한 칸 이동한다. 대각선 이동, 격자판 외부 이동, 쓰레기 장애물 진입은 차단한다."""
    if not state.get("game_started") or state.get("game_cleared"):
        return False

    # 한 번에 상하좌우 정확히 1칸만 허용 (대각선 및 순간이동 방지)
    if abs(dr) + abs(dc) != 1:
        return False

    grid_size = int(state.get("grid_size", GRID_SIZE))
    cur_r, cur_c = state["player_position"]
    new_r = cur_r + dr
    new_c = cur_c + dc

    if not (0 <= new_r < grid_size and 0 <= new_c < grid_size):
        state["action_feedback"] = "⚠️ 기계 유리벽에 막혀 더 이상 이동할 수 없습니다!"
        return False

    obstacles: set[tuple[int, int]] = set(state.get("obstacles") or set())
    if (new_r, new_c) in obstacles:
        state["action_feedback"] = "🗑️ 쓰레기 장애물에 막혀 이동할 수 없습니다! 다른 경로를 찾으세요."
        return False

    state["player_position"] = (new_r, new_c)
    if state["player_position"] == state["claw_position"]:
        state["action_feedback"] = "🎯 집게 포착! 지금 [SPACE] 키 또는 공격 버튼을 누르세요!"
    else:
        state["action_feedback"] = f"인형이 ({new_r + 1}행, {new_c + 1}열)로 이동했습니다."
    return True


def can_attack(state: MutableMapping[str, Any]) -> bool:
    """플레이어가 집게 위치에 도달했는지 확인한다."""
    return (
        bool(state.get("game_started"))
        and not bool(state.get("game_cleared"))
        and tuple(state.get("player_position", (-1, -1)))
        == tuple(state.get("claw_position", (-2, -2)))
    )


def attack_claw(
    state: MutableMapping[str, Any],
    rng: random.Random | None = None,
    auto_submit: bool = True,
    submit_callback: Callable[[MutableMapping[str, Any]], bool] | None = None,
) -> bool:
    """집게와 같은 칸에 있을 때 공격을 수행한다.

    - 스테이지당 3회 공격 성공 시 해당 스테이지 클리어
    - 중간 스테이지(STAGE 1~4) 클리어 시 다음 스테이지 맵 생성 (타이머 유지, 기록 미제출)
    - 최종 스테이지(STAGE 5) 클리어 시 전체 타이머 종료 및 결과 화면 전환 후 기록 1회 제출
    """
    if not can_attack(state):
        state["action_feedback"] = "⚠️ 집게와 같은 위치에 있어야 공격할 수 있습니다!"
        return False

    state["attack_count"] = int(state.get("attack_count", 0)) + 1
    current_stage = int(state.get("current_stage", 1))
    total_stages = int(state.get("total_stages", TOTAL_STAGES))
    grid_size = int(state.get("grid_size", GRID_SIZE))
    obstacles: set[tuple[int, int]] = set(state.get("obstacles") or set())

    if state["attack_count"] >= TARGET_ATTACK_COUNT:
        if current_stage < total_stages:
            advance_to_next_stage(state, rng=rng)
            return True

        # 최종 스테이지(STAGE 5) 클리어 -> 전체 게임 완료
        raw_elapsed = time.monotonic() - float(state["start_time"])
        state["clear_time"] = round(max(0.50, raw_elapsed), 2)
        state["game_started"] = False
        state["game_cleared"] = True
        state["all_stages_cleared"] = True
        state["action_feedback"] = (
            f"🎉 FINAL CLEAR! 모든 {total_stages}개 스테이지를 돌파하고 집게에게 복수했습니다!"
        )
        state["screen"] = "result"
        if auto_submit and submit_callback is not None:
            submit_callback(state)
        return True

    # 아직 해당 스테이지의 공격 횟수가 남아 있으면 집게가 장애물을 피해 도달 가능한 다른 칸으로 이동
    remaining = TARGET_ATTACK_COUNT - state["attack_count"]
    state["claw_position"] = spawn_claw_position(
        tuple(state["player_position"]),
        grid_size=grid_size,
        rng=rng,
        obstacles=obstacles,
    )
    state["action_feedback"] = (
        f"💥 타격 성공! (ATTACK: {state['attack_count']} / {TARGET_ATTACK_COUNT}) "
        f"집게가 다른 위치로 도망쳤습니다! (남은 공격: {remaining}회)"
    )
    return True


def handle_keyboard_event(
    state: MutableMapping[str, Any],
    event_payload: dict[str, Any] | str | None,
    *,
    rng: random.Random | None = None,
    auto_submit: bool = True,
    submit_callback: Callable[[MutableMapping[str, Any]], bool] | None = None,
) -> bool:
    """브라우저에서 전달된 WASD / Space 키보드 이벤트를 검증하고 게임 상태에 반영한다.

    예외 처리:
    - 게임 진행 중(game_started=True, game_cleared=False, screen=='game')이 아닐 때는 무시
    - 텍스트 입력창 포커스 중(is_input_focused=True)일 때는 무시
    - 키 누름 유지에 의한 자동 반복 이벤트(repeat=True) 무시
    - 동일 event_id 중복 처리 방지 (Streamlit rerun 시 중복 이동/공격 차단)
    - 너무 빠른 연속 입력(KEY_INPUT_COOLDOWN_SECONDS 미만) 제어
    """
    if not event_payload:
        return False

    if not state.get("game_started") or state.get("game_cleared"):
        return False

    if state.get("screen", "game") != "game":
        return False

    if isinstance(event_payload, str):
        raw_key = event_payload
        event_id = None
        timestamp = None
        is_repeat = False
        is_input_focused = False
    elif isinstance(event_payload, dict):
        raw_key = str(event_payload.get("key", ""))
        event_id = event_payload.get("event_id")
        timestamp = event_payload.get("timestamp")
        is_repeat = bool(event_payload.get("repeat", False))
        is_input_focused = bool(event_payload.get("is_input_focused", False))
    else:
        return False

    if is_input_focused or is_repeat:
        return False

    if event_id is not None and state.get("last_key_event_id") == event_id:
        return False

    normalized_key = "SPACE" if raw_key == " " else raw_key.strip().upper()
    if normalized_key not in DIRECTION_KEY_MAP and normalized_key not in ATTACK_KEYS:
        return False

    if timestamp is not None:
        try:
            ts_val = float(timestamp)
        except (TypeError, ValueError):
            ts_val = None
        if ts_val is not None:
            last_ts = state.get("last_key_timestamp")
            if (
                last_ts is not None
                and (ts_val - float(last_ts)) < KEY_INPUT_COOLDOWN_SECONDS
            ):
                return False
            state["last_key_timestamp"] = ts_val

    if event_id is not None:
        state["last_key_event_id"] = event_id

    if normalized_key in DIRECTION_KEY_MAP:
        dr, dc = DIRECTION_KEY_MAP[normalized_key]
        return move_player(state, dr, dc)

    return attack_claw(
        state,
        rng=rng,
        auto_submit=auto_submit,
        submit_callback=submit_callback,
    )
