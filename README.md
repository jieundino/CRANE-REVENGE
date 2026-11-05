# 🕹️ CRANE REVENGE — 집게에게 복수하라!

인형뽑기 기계 안에 갇힌 봉제인형이 매번 힘없이 인형을 놓치는 약골 집게에 분노하여, 기계 바닥에 버려진 **쓰레기 장애물(`🗑️`)**을 피해 **집게(`🕹️`)**를 추격하고 **총 5개 스테이지**를 돌파해 기계 밖으로 끌어내는 역발상 경로 탐색 & 시간 기록형 웹 미니게임입니다.

---

## 1. 주요 기능

- **WASD + Space 키보드 조작 및 마우스 보조 조작**:
  - Streamlit Custom Components V2(`st.components.v2.component`)를 활용해 브라우저의 `W`(위), `A`(왼쪽), `S`(아래), `D`(오른쪽) 이동 및 `Space` 공격 이벤트를 Python 게임 상태에 실시간 반영합니다 (한/영 키 상태와 무관하게 `KeyW/A/S/D` 코드 인식 지원).
  - 접근성을 위해 화면 내 마우스 이동/공격 보조 버튼도 함께 제공합니다.
- **랜덤 쓰레기 장애물 및 BFS 경로 보장**:
  - 스테이지가 시작될 때마다 쓰레기 장애물(`🗑️`)이 무작위로 배치되며, **BFS(너비 우선 탐색)** 알고리즘을 통해 플레이어 시작 위치에서 집게 위치까지 이동 가능한 유효 경로가 100% 존재하도록 검증합니다.
- **5개 스테이지 진행 시스템**:
  - 각 스테이지에서 집게를 **3회 공격(`ATTACK: 3 / 3`)**하면 다음 스테이지로 이동하며 격자 크기와 쓰레기 장애물 수가 점진적으로 증가합니다.
  - `STAGE 1 (5×5, 장애물 2개)` → `STAGE 2 (6×6, 5개)` → `STAGE 3 (7×7, 9개)` → `STAGE 4 (8×8, 14개)` → `STAGE 5 (10×10, 22개)`
- **누적 타이머 및 명예의 전당(TOP 10 랭킹)**:
  - `STAGE 1` 시작 시 `time.monotonic()` 타이머가 시작되어 `STAGE 5` 최종 클리어 시점까지의 총 소요 시간을 기록합니다.
  - 플레이어별 모든 기록을 SQLite에 보존하되, 전체 랭킹(TOP 10)에는 플레이어별 **가장 빠른 최고 기록(`MIN(clear_time)`)**만 반영합니다.

---

## 2. 기술 스택

| 구분 | 기술 | 역할 |
|---|---|---|
| 언어 | Python (`>=3.11`) | 게임 규칙, 경로 탐색(BFS) 및 백엔드 API 로직 |
| 패키지 관리 | `uv` | 가상환경(`.venv`), `pyproject.toml`, `uv.lock` 관리 |
| 프론트엔드 | Streamlit (`>=1.66.1`) | 웹 UI, Custom Components V2 키보드 입력, 세션 상태 관리 |
| 백엔드 API | FastAPI | 플레이어 등록, 클리어 기록 저장, 개인 최고 기록 및 랭킹 API |
| 데이터 검증 | Pydantic | UUID, 닉네임, 클리어 시간 유효 범위 검증 |
| 데이터베이스 | SQLite (`sqlite3`) | `players`, `game_records` 영속 저장 |
| 서버 / 통신 | Uvicorn / HTTPX | FastAPI ASGI 서버 실행 및 Streamlit ↔ FastAPI HTTP 통신 |

---

## 3. 프로젝트 디렉터리 구조

```text
CRANE_REVENGE/
├── frontend/
│   ├── __init__.py
│   ├── app.py                  # Streamlit UI, Custom Component V2 키보드 리스너, 화면 전환
│   ├── game_logic.py           # 순수 Python 게임 규칙 (5스테이지, 장애물 생성, BFS 경로 검증, 키 입력 처리)
│   └── api_client.py           # HTTPX 기반 FastAPI 호출 클라이언트
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 앱 엔트리포인트 및 /health
│   ├── database.py             # SQLite 연결, 테이블 자동 초기화 및 쿼리
│   ├── models.py               # Pydantic 요청/응답 검증 모델
│   └── routers/
│       ├── __init__.py
│       ├── players.py          # POST /players, GET /players/{player_id}/best
│       ├── records.py          # POST /records
│       └── rankings.py         # GET /rankings?limit=10
├── data/
│   └── .gitkeep                # SQLite DB 저장 디렉터리 (실제 .db 파일은 Git 제외)
├── tests/
│   ├── __init__.py             # 인메모리 ASGI 3.0 테스트 클라이언트
│   ├── test_health.py          # 서버 상태 및 라우팅 테스트
│   ├── test_players.py         # 플레이어 등록/조회 및 입력 검증 테스트
│   ├── test_records.py         # 기록 API, 5스테이지, 장애물/BFS, 키보드 입력, 타이머 테스트
│   └── test_rankings.py        # 랭킹 정렬 및 프론트엔드-백엔드 통합 테스트
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── CRANE_REVENGE_SPEC.md
├── PROGRESS.md
└── README.md
```

---

## 4. 로컬 개발 환경 준비 및 실행 방법

### 4-1. 의존성 설치 (`[로컬 Windows PowerShell] [프로젝트 루트]`)

```powershell
uv sync
```

### 4-2. 환경 변수 설정

`.env.example`을 참고하여 필요 시 `.env` 파일을 생성합니다 (설정하지 않으면 아래 기본값이 사용됩니다).

```env
API_BASE_URL=http://127.0.0.1:8000
DATABASE_PATH=./data/crane_revenge.db
APP_ENV=development
```

### 4-3. FastAPI 백엔드 실행 (터미널 1)

```powershell
$env:PYTHONPATH = (Get-Location).Path
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

- 상태 확인: `http://127.0.0.1:8000/health`
- Swagger UI 문서: `http://127.0.0.1:8000/docs`

### 4-4. Streamlit 프론트엔드 실행 (터미널 2)

> `frontend/app.py` 상단에 프로젝트 루트를 `sys.path`에 자동 등록하는 코드가 포함되어 있어 `PYTHONPATH` 설정 여부와 무관하게 `backend` 모듈을 안전하게 불러옵니다.

```powershell
$env:PYTHONPATH = (Get-Location).Path
uv run streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

- 브라우저 접속: `http://127.0.0.1:8501`

### 4-5. 자동화 테스트 실행

```powershell
uv run python -m unittest discover -s tests -v
```

---

## 5. GitHub Repository 및 배포 절차 (STEP 8 ~ STEP 11 진행 예정)

- **GitHub Repository**: `https://github.com/jieundino/CRANE-REVENGE.git`
- **Azure Linux VM 배포 (STEP 8)**: 진행 예정 (미검증)
- **Azure App Service 배포 적합성 확인 및 배포 (STEP 9 ~ 10)**: 진행 예정 (미검증)
- **두 배포 방식 비교표 (STEP 11)**: 실제 배포 실습 완료 후 작성 예정

---

## 6. 알려진 제한사항 및 참고 사항

- 별도 로그인 없이 브라우저별 UUID(`?player_id=...`)로 플레이어를 식별합니다. URL을 타인과 공유하면 동일 플레이어 ID를 공유하게 될 수 있으며, 브라우저 데이터 삭제·시크릿 모드·다른 기기 접속 시 새 플레이어로 취급됩니다.
- 클라이언트에서 측정해 제출한 클리어 시간은 변조 가능성이 있으므로 본 프로젝트의 랭킹은 클라우드 배포 실습 및 학습용 기록으로 취급합니다.
