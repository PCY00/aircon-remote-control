# Git migration manifest — 에어컨 원격 제어

작성일: 2026-09-30

## 저장소 상태

- 로컬 Git: 존재, 빈 `main`, 커밋 없음, 원격 없음.
- 제안 원격 이름: `PCY00/aircon-remote-control` — 아직 생성하지 않았고 계정 재인증 후 존재 여부를 먼저 확인한다.

## 추적 후보

- 루트 문서와 설정: `README.md`, `AGENTS.md`, `.gitattributes`, `.gitignore`, `.env.example`, `pyproject.toml`
- 애플리케이션과 테스트: `app/`, `tests/`
- 배포 정의와 장치 프로필: `deploy/`, `device_profiles/`
- 작성 문서와 검증된 이미지: `docs/`
- 펌웨어 소스: `firmware/` 중 빌드·managed component를 제외한 소스
- 운영·개발 도구: `scripts/`, `signals/`

## Git에서 제외 유지

- `.venv/`, Python 캐시, 테스트·lint 캐시, `*.egg-info/`
- `.env`, 키·인증서, `.deploy/`, 로컬 host 정보
- `runtime/`, `runtime_preview/`, 로그와 로컬 DB
- `tmp/`, `.codex-remote-attachments/`
- 펌웨어 build, `managed_components`, `sdkconfig*`, 생성 ZIP

## 조건부 검토

- `outputs/`: 현재 두 파일, 약 0.25 MiB. 소스 증거인지 재생성 가능한 산출물인지 확인한 뒤 포함 여부를 정한다.
- `docs/assets/`: 2026-09-30 메타데이터 검사는 통과했지만 첫 commit 직전에 다시 검사한다.

## 과거 자료 보존

- 기존 문서·저널·결정 기록은 날짜 기록으로 유지한다.
- 런타임 DB와 장비 상태는 Git에서 제외하되 로컬에서는 삭제하지 않는다.

## 차단 요인과 안전 조건

- `PCY00` 로컬 GitHub CLI 재인증 대기.
- 첫 commit 전 staging 목록, 비밀 패턴, 파일 크기 검증 필요.
- 실제 장비나 Raspberry Pi에는 이번 전환 과정에서 접속하지 않는다.
