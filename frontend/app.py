"""CRANE REVENGE Streamlit 프론트엔드 애플리케이션 (5단계 스테이지, WASD/Space 키보드 조작, 장애물, API 연동)."""

from collections.abc import MutableMapping
import html
from pathlib import Path
import random
import sys
from typing import Any
import textwrap

# 프로젝트 루트를 sys.path에 추가하여 실행 위치와 무관하게 backend/frontend 패키지 import 보장
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from backend.models import validate_nickname_string
from frontend.api_client import (
    APIClientError,
    check_server_health,
    fetch_player_best,
    fetch_rankings,
    register_player,
    submit_game_record,
)
from frontend import game_logic
from frontend.game_logic import (
    GRID_SIZE,
    INITIAL_PLAYER_POS,
    KEY_INPUT_COOLDOWN_SECONDS,
    STAGE_CONFIG,
    TARGET_ATTACK_COUNT,
    TOTAL_STAGES,
    advance_to_next_stage,
    can_attack,
    format_elapsed_time,
    generate_obstacles,
    get_elapsed_time,
    get_initial_player_pos,
    get_or_create_player_id,
    get_stage_settings,
    has_valid_path,
    init_game_state,
    move_player,
    setup_stage,
    spawn_claw_position,
    start_new_game,
)

# =====================================================================
# Streamlit Custom Components V2 — WASD 및 Space 키보드 입력 컴포넌트
# =====================================================================
_KEYBOARD_HTML = """
<div class="kb-status-bar" tabindex="-1">
    <span class="kb-dot"></span>
    <span><strong>[ KEYBOARD CONTROL ]</strong> W: UP | A: LEFT | S: DOWN | D: RIGHT | SPACE: ATTACK</span>
</div>
"""

_KEYBOARD_CSS = """
.kb-status-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 8px;
    background: #0f172a;
    border: 1px solid #334155;
    color: #e2e8f0;
    font-family: monospace;
    font-size: 0.85rem;
    user-select: none;
}
.kb-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;
    display: inline-block;
}
"""

_KEYBOARD_JS = """
export default function(component) {
    const { setTriggerValue } = component;

    if (window.__craneKeydownHandler) {
        window.removeEventListener("keydown", window.__craneKeydownHandler, true);
    }

    let lastSentAt = window.__craneLastKeyAt || 0;
    let seq = window.__craneKeySeq || 0;
    const COOLDOWN_MS = 120;

    const isEditableElement = (el) => {
        if (!el) return false;
        const tag = (el.tagName || "").toUpperCase();
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
            return true;
        }
        return Boolean(el.isContentEditable);
    };

    const handleKeyDown = (event) => {
        if (!document.hasFocus()) {
            return;
        }
        if (event.ctrlKey || event.altKey || event.metaKey) {
            return;
        }

        const active = document.activeElement;
        const target = event.target || active;
        if (isEditableElement(target) || isEditableElement(active)) {
            return;
        }

        const rawKey = event.key || "";
        const code = event.code || "";
        let normalized = null;

        if (code === "Space" || rawKey === " ") {
            normalized = "SPACE";
        } else {
            const upper = rawKey.toUpperCase();
            if (upper === "W" || upper === "A" || upper === "S" || upper === "D") {
                normalized = upper;
            } else if (code === "KeyW" || rawKey === "ㅈ") {
                normalized = "W";
            } else if (code === "KeyA" || rawKey === "ㅁ") {
                normalized = "A";
            } else if (code === "KeyS" || rawKey === "ㄴ") {
                normalized = "S";
            } else if (code === "KeyD" || rawKey === "ㅇ") {
                normalized = "D";
            }
        }

        if (!normalized) {
            return;
        }

        // Space 입력 시 브라우저 화면 스크롤 및 버튼 기본 클릭 동작 방지
        if (normalized === "SPACE") {
            event.preventDefault();
            event.stopPropagation();
        }

        // 키를 누르고 있는 동안 발생하는 자동 반복(event.repeat) 차단
        if (event.repeat) {
            return;
        }

        const now = Date.now();
        if (now - lastSentAt < COOLDOWN_MS) {
            return;
        }
        lastSentAt = now;
        window.__craneLastKeyAt = now;
        seq += 1;
        window.__craneKeySeq = seq;

        setTriggerValue("action", {
            key: normalized,
            event_id: `${now}-${seq}`,
            timestamp: now / 1000.0,
            repeat: Boolean(event.repeat),
            is_input_focused: false,
        });
    };

    window.__craneKeydownHandler = handleKeyDown;
    window.addEventListener("keydown", handleKeyDown, true);

    return () => {
        window.removeEventListener("keydown", handleKeyDown, true);
        if (window.__craneKeydownHandler === handleKeyDown) {
            window.__craneKeydownHandler = null;
        }
    };
}
"""

KEYBOARD_LISTENER_COMPONENT = st.components.v2.component(
    "crane_revenge_keyboard_listener",
    html=_KEYBOARD_HTML,
    css=_KEYBOARD_CSS,
    js=_KEYBOARD_JS,
)


# =====================================================================
# 백엔드 기록 제출 및 공격/키보드 래퍼 함수
# =====================================================================
def submit_cleared_record(state: MutableMapping[str, Any]) -> bool:
    """최종 스테이지 클리어 기록을 FastAPI 서버에 1회 제출한다. 중복 제출(record_submitted=True)을 방지한다."""
    if state.get("record_submitted"):
        return True
    if not state.get("game_cleared") or state.get("clear_time") is None:
        return False

    try:
        register_player(
            player_id=str(state["player_id"]),
            nickname=str(state["nickname"]),
        )
        response = submit_game_record(
            player_id=str(state["player_id"]),
            clear_time=float(state["clear_time"]),
        )
        state["record_submitted"] = True
        state["is_new_best"] = bool(response.get("is_new_best", False))
        state["current_best_time"] = response.get("best_time")
        state["submission_message"] = str(
            response.get("message", "기록이 서버에 저장되었습니다.")
        )
        state["submission_error"] = None
        return True
    except APIClientError as exc:
        state["record_submitted"] = False
        state["submission_error"] = exc.message
        return False


def attack_claw(
    state: MutableMapping[str, Any],
    rng: random.Random | None = None,
    auto_submit: bool = True,
) -> bool:
    """집게 공격을 처리하고 최종 스테이지 클리어 시 기록 제출 콜백을 연동한다."""
    return game_logic.attack_claw(
        state,
        rng=rng,
        auto_submit=auto_submit,
        submit_callback=submit_cleared_record,
    )


def handle_keyboard_event(
    state: MutableMapping[str, Any],
    event_payload: dict[str, Any] | str | None,
    *,
    rng: random.Random | None = None,
    auto_submit: bool = True,
) -> bool:
    """WASD 및 Space 키보드 입력 이벤트를 처리하고 최종 클리어 시 기록 제출 콜백을 연동한다."""
    return game_logic.handle_keyboard_event(
        state,
        event_payload,
        rng=rng,
        auto_submit=auto_submit,
        submit_callback=submit_cleared_record,
    )


# =====================================================================
# Streamlit 화면 렌더링 함수 (Section 3.3 A ~ E & Section 6)
# =====================================================================
def render_main_screen(state: MutableMapping[str, Any]) -> None:
    """A. 메인 화면: 게임 소개, 닉네임 입력, 게임 시작 및 랭킹 이동."""
    st.title("🕹️ CRANE REVENGE")
    st.subheader("집게에게 복수하라! — 5 스테이지 인형뽑기 기계 탈출 게임")

    st.markdown(
        textwrap.dedent(f"""
        인형뽑기 기계 안에 갇힌 봉제인형이 매번 힘없이 인형을 놓치는 약골 집게에 분노했습니다!<br>
        기계 바닥에 버려진 <strong>쓰레기 장애물(🗑️)</strong>을 피해 <strong>집게(🕹️)</strong>까지 이동한 뒤,<br>
        <strong>총 {TOTAL_STAGES}개 스테이지(5×5 → 10×10)</strong>를 연속 돌파하는 경로 탐색 & 시간 기록형 미니게임입니다.
        """),
        unsafe_allow_html=True
    )

    server_ok = check_server_health()
    if not server_ok:
        st.warning(
            "⚠️ 현재 백엔드 API 서버(`API_BASE_URL`)에 연결할 수 없습니다. "
            "게임을 시작하거나 랭킹을 보려면 FastAPI 서버를 먼저 실행해주세요."
        )

    nickname_input = st.text_input(
        "플레이어 닉네임 (1~20자, 한글/영문/숫자/_/- 허용)",
        value=state.get("nickname", ""),
        max_chars=20,
        placeholder="예: ANGRY_BEAR 또는 분노한곰돌이",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 게임 시작", use_container_width=True, type="primary"):
            try:
                validated_nick = validate_nickname_string(nickname_input)
            except ValueError as exc:
                st.error(str(exc))
            else:
                try:
                    register_player(str(state["player_id"]), validated_nick)
                    best_info = fetch_player_best(str(state["player_id"]))
                    if best_info and best_info.get("has_record"):
                        state["current_best_time"] = best_info.get("best_time")
                except APIClientError as exc:
                    st.error(exc.message)
                else:
                    state["nickname"] = validated_nick
                    state["screen"] = "prologue"
                    st.rerun()

    with col2:
        if st.button("🏆 랭킹 화면 보기", use_container_width=True):
            state["screen"] = "ranking"
            st.rerun()

    with st.expander("ℹ️ 플레이어 식별(UUID) 및 스테이지 구성 안내"):
        st.caption(
            f"현재 브라우저 플레이어 ID (UUID): `{state['player_id']}`\n\n"
            "- **스테이지 구성**: STAGE 1(5×5, 장애물 2개) → STAGE 2(6×6, 5개) → STAGE 3(7×7, 9개) → STAGE 4(8×8, 14개) → STAGE 5(10×10, 22개)\n"
            "- 별도 로그인 없이 UUID로 개인 최고 기록을 구분합니다 (닉네임 중복 허용).\n"
            "- 브라우저 URL의 `?player_id=...` 파라미터를 통해 새로고침 시에도 동일 ID를 유지합니다."
        )


def render_prologue_screen(state: MutableMapping[str, Any]) -> None:
    """B. 프롤로그 화면: 배경 스토리와 조작 안내 표시 후 본 게임 시작."""
    st.title("🎬 프롤로그 — 약골 집게의 최후")
    safe_nick = html.escape(str(state.get("nickname", "플레이어")))

    st.info(
        "위이잉— 철컥! 오늘도 인형뽑기 기계의 집게는 인형을 들어 올리다 말고 허공에서 맥없이 손을 놓아버렸습니다.\n\n"
        "수백 번째 쓰레기 더미 위로 추락한 봉제인형은 마침내 참을성의 한계를 넘었습니다!"
    )

    st.markdown(
        f"""
        > **🧸 {safe_nick}**: *"맨날 잡았다가 놓치기만 하는 고물 집게 녀석... 더 이상 못 참아!  
        > 쓰레기 더미를 뚫고 끝까지 추격해서 이 유리 상자 밖으로 끌어내 주겠다!!"*
        """
    )

    st.markdown(
        f"""
        ### 🎮 조작 및 스테이지 규칙
        - **키보드 조작**: `W`(위), `A`(왼쪽), `S`(아래), `D`(오른쪽)으로 1칸씩 이동 / `SPACE`로 집게 공격! (마우스 보조 버튼도 함께 지원)
        - **쓰레기 장애물(`🗑️`)**: 구겨진 종이, 빈 캔, 쓰레기 봉투가 놓인 칸으로는 이동할 수 없습니다.
        - **스테이지 진행**: 각 스테이지에서 집게(`🕹️`)를 **{TARGET_ATTACK_COUNT}번 공격**하면 다음 스테이지로 진격하며, **STAGE {TOTAL_STAGES}**까지 모두 클리어한 총 시간으로 랭킹을 겨룹니다!
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔥 STAGE 1 복수 시작! (타이머 작동)", use_container_width=True, type="primary"):
            start_new_game(state)
            st.rerun()
    with col2:
        if st.button("🏠 메인 화면으로", use_container_width=True):
            state["screen"] = "main"
            st.rerun()


def _get_grid_style(grid_size: int) -> tuple[str, str]:
    """격자 크기에 따라 화면이 지나치게 넓어지지 않도록 폰트 크기와 줄 간격을 조정한다."""
    if grid_size <= 6:
        return "1.95rem", "2.35rem"
    if grid_size <= 8:
        return "1.55rem", "1.95rem"
    return "1.25rem", "1.55rem"


def render_game_screen(state: MutableMapping[str, Any]) -> None:
    """C. 게임 화면: 스테이지 정보, 시간, 키보드 이벤트 수신, 격자판(장애물 포함), 보조 버튼."""
    # 1. 키보드 이벤트 컴포넌트 마운트 및 즉시 반영
    kb_result = KEYBOARD_LISTENER_COMPONENT(
        key="crane_revenge_kb",
        on_action_change=lambda: None,
    )
    if kb_result is not None and getattr(kb_result, "action", None):
        handled = handle_keyboard_event(state, kb_result.action)
        if handled and state.get("screen") != "game":
            st.rerun()

    current_stage = int(state.get("current_stage", 1))
    total_stages = int(state.get("total_stages", TOTAL_STAGES))
    grid_size = int(state.get("grid_size", GRID_SIZE))
    obstacles: set[tuple[int, int]] = set(state.get("obstacles") or set())
    obstacle_count = len(obstacles)
    attack_count = int(state.get("attack_count", 0))
    elapsed = get_elapsed_time(state)
    formatted_time = format_elapsed_time(elapsed)

    # 2. 상단 스테이지 및 게임 상태 헤더 (Section 6 형식 준수)
    st.markdown(
        f"""
        <div style="background:#0f172a; border:2px solid #334155; border-radius:12px; padding:14px 18px; margin-bottom:12px; font-family:monospace; color:#f8fafc;">
            <div style="font-size:1.35rem; font-weight:bold; color:#38bdf8; letter-spacing:1px;">🕹️ CRANE REVENGE</div>
            <div style="font-size:1.15rem; font-weight:bold; color:#facc15; margin-top:4px;">STAGE {current_stage} / {total_stages}</div>
            <div style="display:flex; flex-wrap:wrap; gap:18px; margin-top:8px; font-size:0.95rem; color:#e2e8f0;">
                <span><strong>GRID SIZE:</strong> {grid_size} x {grid_size}</span>
                <span><strong>OBSTACLES:</strong> {obstacle_count}</span>
                <span><strong>ATTACK:</strong> {attack_count} / {TARGET_ATTACK_COUNT}</span>
                <span style="color:#4ade80;"><strong>TIME:</strong> {formatted_time}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(state.get("action_feedback", ""))

    # 3. 격자판 렌더링 (🧸 플레이어, 🕹️ 집게, 💥 포착 완료, 🗑️ 쓰레기 장애물, ⬜ 빈 공간)
    p_row, p_col = state["player_position"]
    c_row, c_col = state["claw_position"]
    font_size, line_height = _get_grid_style(grid_size)

    grid_lines: list[str] = []
    for r in range(grid_size):
        row_cells: list[str] = []
        for c in range(grid_size):
            pos = (r, c)
            if pos == (p_row, p_col) and pos == (c_row, c_col):
                row_cells.append("💥")  # 인형과 집게가 같은 위치 (공격 가능!)
            elif pos == (p_row, p_col):
                row_cells.append("🧸")  # 플레이어 캐릭터
            elif pos == (c_row, c_col):
                row_cells.append("🕹️")  # 목표 집게
            elif pos in obstacles:
                row_cells.append("🗑️")  # 쓰레기 장애물
            else:
                row_cells.append("⬜")  # 이동 가능한 공간
        grid_lines.append(" ".join(row_cells))

    st.markdown(
        f"<div style='text-align:center; font-size:{font_size}; line-height:{line_height}; "
        "background:#1e293b; padding:14px; border-radius:12px; margin-bottom:10px; "
        "white-space:nowrap; overflow-x:auto; max-width:100%; border:1px solid #475569;'>"
        + "<br>".join(grid_lines)
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "범례: 🧸 플레이어 | 🕹️ 집게 | 🗑️ 쓰레기 장애물(이동 불가) | 💥 포착 완료(SPACE 공격!) | ⬜ 이동 가능 공간"
    )

    # 4. 키보드 조작 안내 박스 (Section 2-3 & Section 6)
    st.markdown(
        """
        ```text
        [ KEYBOARD CONTROL ]
        W : MOVE UP      A : MOVE LEFT      S : MOVE DOWN      D : MOVE RIGHT
        SPACE : ATTACK

        WASD : MOVE / SPACE : ATTACK — Find the claw and pull it down!
        ```
        """
    )

    # 5. 마우스 보조 조작 버튼 (접근성 및 보조 조작 유지)
    with st.expander("🖱️ 마우스 버튼 보조 조작 열기/닫기", expanded=True):
        _, up_col, _ = st.columns([1, 1, 1])
        with up_col:
            if st.button("⬆️ 위로 (W)", use_container_width=True):
                move_player(state, -1, 0)
                st.rerun()

        left_col, atk_col, right_col = st.columns([1, 1, 1])
        with left_col:
            if st.button("⬅️ 왼쪽 (A)", use_container_width=True):
                move_player(state, 0, -1)
                st.rerun()
        with atk_col:
            attack_ready = can_attack(state)
            if st.button(
                "⚡ 공격 (SPACE)",
                use_container_width=True,
                type="primary",
                disabled=not attack_ready,
            ):
                attack_claw(state)
                st.rerun()
        with right_col:
            if st.button("➡️ 오른쪽 (D)", use_container_width=True):
                move_player(state, 0, 1)
                st.rerun()

        _, down_col, _ = st.columns([1, 1, 1])
        with down_col:
            if st.button("⬇️ 아래로 (S)", use_container_width=True):
                move_player(state, 1, 0)
                st.rerun()

    st.divider()
    ctrl1, ctrl2 = st.columns(2)
    with ctrl1:
        if st.button("🔄 STAGE 1부터 다시 시작", use_container_width=True):
            start_new_game(state)
            st.rerun()
    with ctrl2:
        if st.button("🛑 게임 종료 (메인 화면)", use_container_width=True):
            state["game_started"] = False
            state["screen"] = "main"
            st.rerun()


def render_result_screen(state: MutableMapping[str, Any]) -> None:
    """D. 최종 결과 화면: FINAL CLEAR, 총 클리어 시간, 전체 스테이지 완료 여부, 최고 기록 갱신 여부 표시."""
    st.title("🎉 FINAL CLEAR — 복수 대성공!")
    st.subheader(f"플레이어: {state.get('nickname', '')}")

    clear_time = state.get("clear_time")
    best_time = state.get("current_best_time")
    total_stages = int(state.get("total_stages", TOTAL_STAGES))
    all_cleared = bool(state.get("all_stages_cleared", state.get("game_cleared", False)))

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "스테이지 완료",
        f"ALL {total_stages} STAGES" if all_cleared else f"STAGE {state.get('current_stage', 1)}",
    )
    col2.metric(
        "총 클리어 시간",
        f"{float(clear_time):.2f}초 ({format_elapsed_time(float(clear_time))})"
        if clear_time is not None
        else "-",
    )
    col3.metric(
        "개인 최고 기록",
        f"{float(best_time):.2f}초" if best_time is not None else "집계 중",
    )

    if state.get("record_submitted"):
        if state.get("is_new_best"):
            st.success(f"🌟 축하합니다! {state.get('submission_message', '새로운 개인 최고 기록입니다!')}")
        else:
            st.info(f"✅ {state.get('submission_message', '기록이 서버에 정상 저장되었습니다.')}")
    else:
        err_msg = state.get("submission_error") or "아직 기록이 서버에 제출되지 않았습니다."
        st.error(f"⚠️ 기록 저장 실패: {err_msg}")
        if st.button("📤 기록 다시 제출하기", use_container_width=True, type="primary"):
            submit_cleared_record(state)
            st.rerun()

    st.divider()
    b_col1, b_col2, b_col3 = st.columns(3)
    with b_col1:
        if st.button("🏆 전체 랭킹 확인", use_container_width=True, type="primary"):
            state["screen"] = "ranking"
            st.rerun()
    with b_col2:
        if st.button("🔄 다시 플레이", use_container_width=True):
            start_new_game(state)
            st.rerun()
    with b_col3:
        if st.button("🏠 메인 화면", use_container_width=True):
            state["screen"] = "main"
            st.rerun()


def render_ranking_screen(state: MutableMapping[str, Any]) -> None:
    """E. 랭킹 화면: 전체 플레이어 개인 최고 기록 TOP 10 및 내 최고 기록 표시."""
    st.title("🏆 CRANE REVENGE 명예의 전당 (TOP 10)")

    try:
        my_best_data = fetch_player_best(str(state["player_id"]))
        if my_best_data and my_best_data.get("has_record"):
            state["current_best_time"] = my_best_data.get("best_time")
    except APIClientError:
        my_best_data = None

    my_best = state.get("current_best_time")
    if my_best is not None:
        st.info(
            f"🙋 내 현재 최고 기록 (**{state.get('nickname') or '플레이어'}**): "
            f"**{float(my_best):.2f}초 ({format_elapsed_time(float(my_best))})**"
        )
    else:
        st.caption("아직 등록된 개인 클리어 기록이 없습니다. 5개 스테이지를 모두 클리어하고 첫 기록을 남겨보세요!")

    try:
        rankings = fetch_rankings(limit=10)
    except APIClientError as exc:
        st.error(f"⚠️ 랭킹을 불러올 수 없습니다: {exc.message}")
    else:
        if not rankings:
            st.warning("아직 등록된 랭킹 기록이 없습니다. 첫 번째 1위의 주인공이 되어보세요!")
        else:
            table_rows = []
            for item in rankings:
                rank_num = int(item.get("rank", 0))
                medal = {1: "🥇 1위", 2: "🥈 2위", 3: "🥉 3위"}.get(
                    rank_num, f"{rank_num}위"
                )
                is_me = item.get("player_id") == state.get("player_id")
                nick_display = f"{item.get('nickname', '')} {'(나)' if is_me else ''}".strip()
                best_sec = float(item.get("best_time", 0.0))
                table_rows.append(
                    {
                        "순위": medal,
                        "닉네임": nick_display,
                        "최고 기록(초)": f"{best_sec:.2f}초 ({format_elapsed_time(best_sec)})",
                    }
                )
            st.table(table_rows)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🏠 메인 화면으로 돌아가기", use_container_width=True, type="primary"):
            state["screen"] = "main"
            st.rerun()
    with col2:
        if state.get("nickname"):
            if st.button("🎮 바로 다시 플레이", use_container_width=True):
                start_new_game(state)
                st.rerun()


def main() -> None:
    """Streamlit 앱 메인 엔트리포인트."""
    st.set_page_config(
        page_title="CRANE REVENGE — 집게에게 복수하라!",
        page_icon="🕹️",
        layout="centered",
    )

    init_game_state(st.session_state, st.query_params)

    screen = st.session_state.get("screen", "main")
    if screen == "prologue":
        render_prologue_screen(st.session_state)
    elif screen == "game":
        render_game_screen(st.session_state)
    elif screen == "result":
        render_result_screen(st.session_state)
    elif screen == "ranking":
        render_ranking_screen(st.session_state)
    else:
        render_main_screen(st.session_state)


if __name__ == "__main__":
    main()
