# CRANE REVENGE 진행 상황

## 현재 진행 단계
- [x] STEP 1. uv 프로젝트 구성
- [x] STEP 2. FastAPI 기본 서버
- [x] STEP 3. SQLite 및 API
- [x] STEP 4. Streamlit 화면 (5스테이지·장애물·WASD/Space 키보드 조작 확장 완료)
- [x] STEP 5. 타이머 및 게임 로직 (BFS 경로 탐색·5스테이지 누적 타이머 확장 완료)
- [x] STEP 6. 프론트엔드-백엔드 연동
- [x] STEP 7. 통합 테스트 및 GitHub 정리
- [x] STEP 8. Azure VM 배포
- [x] STEP 9. App Service 배포 적합성 확인
- [ ] STEP 10. Azure App Service 배포
- [ ] STEP 11. 배포 비교 및 문서화

## 구현 완료 사항
- **STEP 1 ~ STEP 8**: 로컬 개발·테스트(23개 통과), GitHub 저장소(`https://github.com/jieundino/CRANE-REVENGE.git`) Push, Azure Linux VM(`http://20.41.121.123:8501`) 배포 및 외부 접속 검증 완료
- **STEP 9. Azure App Service 배포 적합성 사전 확인 및 배포 준비 파일 구성 완료**:
  - **OS 및 Python 런타임 지원 확인**: Azure App Service (Linux)의 Python `3.11` / `3.12` 런타임과 호환되도록 `requires-python = ">=3.11"` 구성 확인
  - **Oryx 빌드 호환용 `requirements.txt` 추가**: GitHub Actions 또는 VS Code 확장으로 App Service에 배포할 때 Azure Oryx 빌더가 자동으로 가상환경(`antenv`)에 패키지를 설치할 수 있도록 `requirements.txt` 생성
  - **단일 외부 포트 제약 및 다중 프로세스 관리 스크립트 (`scripts/start_app_service.sh`) 작성**:
    - App Service는 외부로 단일 HTTP 포트(`$PORT`, 기본 `8000`)만 노출하므로, 외부 진입 포트(`0.0.0.0:$PORT`)에는 **Streamlit**을 바인딩하고, **FastAPI**는 컨테이너 내부 루프백의 별도 포트(`127.0.0.1:8001`, `BACKEND_PORT=8001`)로 분리해 포트 충돌을 원천 방지함 (`API_BASE_URL=http://127.0.0.1:8001` 자동 설정)
    - `wait -n`과 `trap cleanup`을 통해 두 프로세스 중 하나라도 비정상 종료되면 나머지 프로세스도 즉시 정리하고 컨테이너 종료 코드를 반환하여 App Service가 자동 재시작할 수 있도록 구성
  - **SQLite 영속 저장 경로 설정**: App Service(Linux)에서 재시작·재배포 시에도 파일이 유지되는 마운트 경로인 `/home`(`/home/data/crane_revenge.db`)을 `DATABASE_PATH` 기본값으로 사용하도록 설정
  - **`.gitattributes` 추가**: Windows에서 Git 커밋 시에도 `*.sh` 파일이 항상 Linux 호환 `LF` 줄바꿈을 유지하도록 설정 (`CRLF count: 0` 검증 완료)

## 실행한 테스트와 결과
- `[로컬 Windows PowerShell] [프로젝트 루트]` `.venv\Scripts\python.exe -c "b = open('scripts/start_app_service.sh', 'rb').read(); print('CRLF count:', b.count(b'\r\n'), 'LF count:', b.count(b'\n'))"`
  - **결과**: `CRLF count: 0 LF count: 100` (Linux 컨테이너 실행 호환성 확인)
- `[로컬 Windows PowerShell] [프로젝트 루트]` `.venv\Scripts\python.exe -m unittest discover -s tests -v`
  - **결과**: 23개 테스트 전체 통과 유지

## 현재 발생한 오류
- 없음

## 결정한 설계 및 변경 사항
- **기존 Streamlit + FastAPI 분리 구조 유지 + 단일 시작 스크립트(`scripts/start_app_service.sh`) 채택**:
  - App Service 배포를 위해 기존 코드를 단일 프로세스로 대규모 변경하지 않고, 하나의 시작 스크립트에서 내부 FastAPI(`127.0.0.1:8001`)와 외부 Streamlit(`0.0.0.0:$PORT`)을 함께 실행·감시하는 방식을 채택함.

## 다음 작업
- **STEP 10. Azure App Service 배포**
  - 새로 추가한 `scripts/start_app_service.sh`, `requirements.txt`, `.gitattributes`를 GitHub에 Push
  - Azure Portal에서 Linux App Service 생성 및 GitHub(또는 VS Code) 연동 배포
  - 시작 명령(`bash scripts/start_app_service.sh`) 및 환경 변수 설정 후 `*.azurewebsites.net` 접속 및 데이터 영속성 검증

## 실행 방법
```bash
# [Azure App Service 시작 명령 (Startup Command)]
bash scripts/start_app_service.sh
```
