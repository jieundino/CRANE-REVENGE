# CRANE REVENGE 진행 상황

## 현재 진행 단계
- [x] STEP 1. uv 프로젝트 구성
- [x] STEP 2. FastAPI 기본 서버
- [x] STEP 3. SQLite 및 API
- [x] STEP 4. Streamlit 화면 (5스테이지·장애물·WASD/Space 키보드 조작 확장 완료)
- [x] STEP 5. 타이머 및 게임 로직 (BFS 경로 탐색·5스테이지 누적 타이머 확장 완료)
- [x] STEP 6. 프론트엔드-백엔드 연동
- [x] STEP 7. 통합 테스트 및 GitHub 정리
- [ ] STEP 8. Azure VM 배포
- [ ] STEP 9. App Service 배포 적합성 확인
- [ ] STEP 10. Azure App Service 배포
- [ ] STEP 11. 배포 비교 및 문서화

## 구현 완료 사항
- **STEP 1 ~ STEP 3**: `uv` 프로젝트 초기화, FastAPI `/health` 및 플레이어(`POST /players`, `GET /players/{id}/best`)·기록(`POST /records`)·랭킹(`GET /rankings`) API와 SQLite 연동 완료
- **STEP 4 ~ STEP 6 및 게임 시스템 확장 완료**:
  - **순수 Python 게임 로직 모듈 분리 (`frontend/game_logic.py`)**:
    - Streamlit 의존성 없이 스테이지 설정(`STAGE_CONFIG`), 플레이어 이동 검증(`move_player`), 랜덤 쓰레기 장애물 생성(`generate_obstacles`), BFS 경로 유효성 검증(`has_valid_path`), 공격 및 스테이지 전환(`attack_claw`, `advance_to_next_stage`), 키보드 이벤트 처리(`handle_keyboard_event`)를 독립 모듈로 분리
  - **WASD 및 Space 키보드 조작 (`frontend/app.py` + `frontend/game_logic.py`)**:
    - Streamlit `1.66.1`의 Custom Components V2(`st.components.v2.component`)를 사용해 브라우저 `keydown` 이벤트를 캡처하여 Python 상태로 전달
    - `W`/`A`/`S`/`D`(한글 두벌식 `ㅈ`/`ㅁ`/`ㄴ`/`ㅇ` 및 `KeyW/A/S/D` 포함) 1칸 이동, `Space` 집게 공격 매핑
    - 예외 처리: 게임 진행 중이 아닐 때 무시, 입력창(`INPUT`/`TEXTAREA`) 포커스 시 무시, `Space` 스크롤 방지(`preventDefault`), `event.repeat` 자동 반복 무시, `event_id` 중복 적용 차단, 연속 입력 쿨다운 적용
    - 접근성을 위해 기존 마우스 방향/공격 보조 버튼도 함께 유지
  - **랜덤 쓰레기 장애물 및 BFS 경로 탐색**:
    - 플레이어 시작 위치와 집게 위치를 제외하고 지정된 개수의 쓰레기 장애물(`🗑️`)을 무작위 배치
    - BFS(`has_valid_path`)로 이동 가능 경로 존재 여부를 검증하며, 재시도 횟수 초과 시 보장된 경로를 먼저 확보한 뒤 나머지 칸에 장애물을 배치하는 안전 대체 로직 구현
  - **5개 스테이지 시스템 및 누적 타이머**:
    - `STAGE 1 (5×5, 장애물 2개)` → `STAGE 2 (6×6, 5개)` → `STAGE 3 (7×7, 9개)` → `STAGE 4 (8×8, 14개)` → `STAGE 5 (10×10, 22개)`
    - 각 스테이지에서 3회 공격 성공 시 다음 스테이지 맵을 새로 생성하며 전체 타이머(`start_time`)는 초기화하지 않고 유지
    - 중간 스테이지(1~4) 클리어 시에는 API 기록 제출을 하지 않으며, 최종 `STAGE 5` 클리어 시에만 전체 소요 시간을 1회 제출
- **STEP 7. 통합 테스트 및 GitHub 정리 완료**:
  - 전체 통합 테스트(23개) 및 `uv sync` 검증 완료
  - `.gitignore`를 통해 로컬 플레이 DB(`data/crane_revenge.db`), 가상환경(`.venv/`), `.env`, 비밀키 등이 Git 추적 대상에서 제외되고 `data/.gitkeep` 및 `uv.lock`이 포함되는지 확인
  - 한국어 `README.md` 작성 및 GitHub 원격 저장소(`https://github.com/jieundino/CRANE-REVENGE.git`) 연결·Push 진행

## 실행한 테스트와 결과
- `[로컬 Windows PowerShell] [프로젝트 루트]` `uv sync`
  - **결과**: 성공 (`Resolved 50 packages, Checked 47 packages`)
- `[로컬 Windows PowerShell] [프로젝트 루트]` `.venv\Scripts\python.exe -m unittest discover -s tests -v`
  - **결과**: 총 **23개 테스트 모두 성공 (`Ran 23 tests in 0.756s - OK`)**
- `[로컬 Windows PowerShell] [프로젝트 루트]` Git 추적 파일 점검 (`git status`)
  - **결과**: `data/crane_revenge.db`, `.venv/`, `__pycache__/` 등 제외 대상 파일이 커밋 목록에 포함되지 않고 `uv.lock`, `.env.example`, `data/.gitkeep` 및 소스/테스트/문서 파일만 추적됨을 확인

## 현재 발생한 오류
- 없음

## 결정한 설계 및 변경 사항
- **Custom Components V2 채택**: 외부 서드파티 패키지 추가 없이 현재 설치된 `streamlit 1.66.1`의 공식 `st.components.v2.component`(`setTriggerValue`)를 사용하여 iframe 포커스 문제 없이 메인 문서에서 직접 `keydown`을 감지하고 Python으로 전달하도록 구현함.
- **게임 규칙 모듈 분리**: `frontend/game_logic.py`로 순수 Python 게임 로직을 분리하고 `frontend/app.py`에서 재노출(re-export)하여 기존 코드 및 테스트 호환성을 유지함.

## 다음 작업
- **STEP 8. Azure VM 배포**
  - Azure Linux VM 생성 및 SSH 접속
  - Git 설치, Python/uv 환경 구성 및 GitHub 저장소(`https://github.com/jieundino/CRANE-REVENGE.git`) Clone
  - `uv sync` 후 FastAPI(내부 `127.0.0.1:8000`) 및 Streamlit(외부 `0.0.0.0:8501`) 실행, NSG 포트 설정 및 외부 접속 확인

## 실행 방법
```powershell
# [로컬 Windows PowerShell] [프로젝트 루트: C:\Users\UserK\Documents\CRANE_REVENGE]

# 1. 의존성 동기화
uv sync

# 2. 자동화 테스트 실행 (23개 테스트)
uv run python -m unittest discover -s tests -v

# 3. 터미널 1: FastAPI 백엔드 실행
$env:PYTHONPATH = (Get-Location).Path
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 4. 터미널 2: Streamlit 프론트엔드 실행
$env:PYTHONPATH = (Get-Location).Path
uv run streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```
