# Raspberry Pi 배포 설계

## 대상

- SSH 호스트명: `AC`
- 프로젝트 경로 제안: `/home/air/aircon-controller`
- 웹/API 포트: `8001`
- 외부 접근: Tailscale IPv4 주소의 `8001` 포트

사설 IP, 비밀번호와 인증 키는 이 문서에 기록하지 않는다.

## 초기 구성

초기 구성은 사용자 승인 후 다음 순서로 수행한다.

1. 프로젝트 전용 SSH 공개키를 기존 `authorized_keys`에 추가한다.
2. 새 키로 로그인이 되는지 별도 세션에서 검증한다.
3. Tailscale Debian Trixie 저장소와 패키지를 설치한다.
4. `tailscale up`이 출력한 주소를 사용자가 브라우저에서 승인한다.
5. 프로젝트 디렉터리와 Python 가상환경을 만든다.
6. 런타임 코드만 로컬에서 단방향 전송한다.
7. 사용자 단위 systemd 서비스를 설치하고 로그인 없이 실행되도록 lingering을 활성화한다.
8. 서비스가 Tailscale IPv4 주소의 `8001` 포트에만 바인딩됐는지 확인한다.

## 배포 원칙

- 실제 반영 전에 변경 파일 목록을 확인한다.
- `.git`, `.venv`, 문서용 대용량 사진, 비밀 정보와 로컬 캐시는 전송하지 않는다.
- 원격 파일은 기본적으로 삭제하지 않는다.
- 전송 후 SHA-256 비교와 `/health` 요청으로 검증한다.
- 서비스 재시작이 필요하면 배포 승인 범위에 명시한다.

## 코드 전송 스크립트

`scripts/deploy.ps1`은 기본적으로 전송 예정 파일과 SHA-256만 출력하며 Pi를 변경하지 않는다.

```powershell
.\scripts\deploy.ps1
```

출력된 대상과 파일 목록을 검토하고 사용자에게 Pi 업데이트 승인을 받은 뒤에만 실제 전송을 실행한다.

```powershell
.\scripts\deploy.ps1 -Apply
```

현재 전송 범위는 `app/`, `deploy/`, `device_profiles/`, `tests/`, `scripts/run_pi.sh`, `.env.example`, `pyproject.toml`, `README.md`다. `.git`, `.venv`, 캐시, 실제 `.env`, 블로그 문서·원본 사진과 로컬 전용 실행 스크립트는 포함하지 않는다. 원격 파일 삭제는 하지 않으며 전송 후 각 파일의 SHA-256을 비교한다.
