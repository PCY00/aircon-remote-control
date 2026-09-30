# Step 1 — Raspberry Pi 원격 제어 개발 환경 구성

> Raspberry Pi OS Lite에 FastAPI 서비스를 올리고, 공유기 포트포워딩 없이
> Tailscale을 통해 포트 8001에 접근할 수 있는 개발·배포 환경을 만든 과정이다.

## 1. 프로젝트의 출발점

목표는 오래된 벽걸이 에어컨을 기존 리모컨 없이도 제어하는 것이었다. Raspberry Pi 4B를
집 안의 중앙 제어기로 두고, 기존 리모컨의 적외선 신호를 학습해 웹에서 다시 보내기로 했다.

처음부터 외부 인터넷에 포트를 공개하고 싶지는 않았다. 따라서 공유기 포트포워딩 대신
Tailscale 사설망을 사용하고, 웹과 API는 하나의 FastAPI 서비스가 포트 `8001`에서 제공하게
했다.

```text
외부 휴대폰·PC
      │ Tailscale
      ▼
Raspberry Pi 4B : 8001
      │
 FastAPI / Uvicorn
```

개발 PC는 Windows, 실행 장비는 Raspberry Pi OS 64-bit Lite였다. Pi는 화면 없이 운영하기
때문에 모든 설치·배포·복구가 SSH로 재현돼야 했다.

## 2. 로컬 폴더를 기준본으로 정한 이유

Pi에 SSH로 접속해 그 자리에서 코드를 수정하면 PC와 Pi의 버전이 쉽게 달라진다. 이 프로젝트는
Windows의 현재 작업 폴더를 유일한 기준본으로 정하고, 다음 흐름만 허용했다.

```text
로컬 구현 → 테스트 → 배포 미리보기 → 사용자 승인 → Pi 전송 → SHA-256 검증
```

배포 스크립트는 기본 실행 시 파일 목록과 해시만 출력한다. `-Apply`를 명시하고 사용자가
승인한 경우에만 전송하며, 원격 삭제 기능은 넣지 않았다. `.venv`, 비밀 값, 캐시, 사진과
Pi 런타임 데이터도 동기화 대상에서 제외했다.

이 결정 덕분에 이후 UI와 IR 코드를 여러 번 수정하면서도 Pi의 운영 데이터와 로컬 기준본을
분리할 수 있었다.

## 3. SSH 키 인증에서 처음 만난 문제

처음 만든 프로젝트 개인키로 접속하자 Pi 계정 비밀번호가 아니라 개인키 passphrase를
요구했다. Pi의 `authorized_keys`와 권한을 다시 확인했지만 다음 값은 모두 정상이었다.

- `~/.ssh`: `700`
- `authorized_keys`: `600`
- 소유자: Pi 사용자
- PC와 Pi에 기록된 공개키 지문: 일치

원인은 공개키 복사 실패가 아니라 Windows 개인키 자체에 예상하지 못한 passphrase가 설정된
것이었다. 기존 키를 지우지 않고 배포 전용 ED25519 키를 별도로 만들고 공개키만 Pi에 추가했다.
마지막에는 대화형 암호 입력을 금지한 `BatchMode=yes` 접속으로 검증했다.

여기서 얻은 교훈은 간단하다. SSH 키를 만들었으면 곧바로 공개키 추출과 지문을 확인하고,
Pi에 등록한 뒤에는 반드시 비대화형 접속까지 시험해야 한다.

## 4. 프로젝트 경로와 Python 가상환경

Pi의 프로젝트 경로는 다음 하나로 고정했다.

```text
/home/<user>/aircon-controller
```

시스템 Python을 오염시키지 않도록 프로젝트 안에 `.venv`를 만들고 편집 가능 모드로 설치했다.

```bash
cd /home/<user>/aircon-controller
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip check
```

실제 환경은 Python 3.13 계열이었고 FastAPI, Uvicorn과 Starlette 설치 후 `pip check`를
통과했다. 로컬에서는 먼저 `127.0.0.1:8001`에 개발 서버를 띄워 `/health`가 HTTP 200을
반환하는지 확인했다.

테스트 과정에서 Starlette가 기존 `httpx` 테스트 경로의 사용 중단 예정 경고를 냈다.
경고를 숨기는 대신 당시 새 기본 경로인 `httpx2`로 개발 의존성을 옮기고, 경고를 오류로
취급한 테스트까지 다시 통과시켰다.

## 5. Tailscale 설치

Pi의 `/etc/os-release`는 Debian 13 Trixie였다. 자동 설치 스크립트 대신 배포판과 코드명이
보이는 저장소 설정 방식을 사용했다. 패키지 목록을 갱신하는 과정에서 Debian 저장소 버전이
13.5에서 13.6으로 바뀌었다는 알림이 표시됐지만 오류가 아니었고, 전체 운영체제 업그레이드는
수행하지 않았다.

Tailscale 설치 후 기존 PC와 같은 Tailnet에 연결하고 다음을 확인했다.

- `tailscaled`: enabled·active
- Tailscale IPv4 할당
- 백엔드 상태: Running
- 실제 IP, 계정과 인증 URL: 문서에서 제거

## 6. systemd 사용자 서비스와 포트 8001

웹 서비스는 시스템 서비스가 아니라 Pi 사용자 단위의 systemd 서비스로 설치했다.

```text
~/.config/systemd/user/aircon-controller.service
```

서비스는 실행할 때 Tailscale IPv4를 조회하고 그 주소 하나에만 Uvicorn을 바인딩한다.
Tailscale이 아직 준비되지 않았다면 실패하고 systemd가 다시 시도한다. `0.0.0.0`, LAN 주소,
공용 인터페이스에는 자동으로 열리지 않는다.

SSH 로그아웃 후에도 서비스가 유지되고 부팅 때 자동 시작되도록 사용자 linger를 활성화했다.

```bash
systemctl --user enable --now aircon-controller.service
systemctl --user is-enabled aircon-controller.service
systemctl --user is-active aircon-controller.service
```

처음 `systemctl is-active`만 실행했을 때는 inactive로 표시됐다. 시스템 서비스가 아니라
사용자 서비스였기 때문에 `systemctl --user`가 필요했다. Pi 내부의
`http://127.0.0.1:8001`이 실패한 것도 장애가 아니라 Tailscale 주소 전용 바인딩의 결과였다.

## 7. Windows와 원격 셸 사이의 따옴표 문제

PowerShell에서 SSH를 거쳐 Bash와 Python을 한 줄로 실행하자 `$()`와 따옴표가 Windows에서
먼저 해석되는 문제가 반복됐다. 증상은 Windows에 없는 `head`를 실행하려 하거나 Python
문자열이 깨지는 식으로 나타났다.

해결 원칙은 세 가지였다.

1. 원격 셸 명령 전체를 PowerShell에서 안전한 한 문자열로 전달한다.
2. 복잡한 Python 한 줄 코드를 피하고 `pip show`, `grep`, `curl` 같은 단순 명령을 쓴다.
3. Tailscale 주소 조회와 HTTP 검증을 분리한다.

## 8. 최종 검증

Pi에서 Tailscale 주소의 `/health`가 HTTP 200을 반환했고, Windows PC에서도 LAN 주소나 SSH
터널이 아니라 Tailscale 주소를 직접 호출해 같은 응답을 확인했다.

```json
{
  "status": "ok",
  "service": "aircon-controller"
}
```

이로써 Step 1의 결과물은 다음과 같이 정리됐다.

- 재현 가능한 SSH 키 접속
- 로컬 기준본과 승인 기반 단방향 배포
- Python 가상환경과 FastAPI 골격
- 포트 8001 사용자 systemd 서비스
- Tailscale 전용 접근
- 서비스와 파일 체크섬 검증 절차

같은 물리 LAN에서 Tailscale 주소 경로까지는 확인했지만, 실제 셀룰러나 외부 Wi-Fi 시험은
후속 운영 검증으로 남겼다.

## 9. 게시 전 추가할 화면 캡처

Step 1 당시 터미널 원본 화면은 `docs/assets`에 별도로 보관되지 않았다. 게시 직전 같은
구성을 읽기 전용으로 다시 확인해 다음 세 장을 촬영하되 사용자명, 사설 주소와 Tailnet 정보는
가린다.

1. `systemctl --user`의 enabled·active 결과
2. Tailscale 주소에만 바인딩된 포트 8001
3. 외부 PC에서 `/health` HTTP 200을 확인한 화면

## 10. 다음 편

환경이 준비됐으니 다음 단계는 기존 리모컨의 적외선 신호를 실제로 수집하는 것이었다.
Step 2에서는 HW-477 수신기를 GPIO17에 연결하고 Carrier CS-A061GS 리모컨의 48비트
프레임을 분석한다.

## 원본 기록

- [프로젝트 초기 환경 구성](../journal/2026-08-29-environment-setup.md)
- [Raspberry Pi 실행 환경](../hardware/raspberry-pi.md)
- [웹 서비스 운영](../operations/web-service.md)
- [트러블슈팅](../troubleshooting.md)
- [로컬 기준본과 승인 기반 배포 결정](../decisions/0001-local-source-and-approved-deployment.md)
- [웹 스택과 포트 8001 결정](../decisions/0002-web-stack-and-port.md)
