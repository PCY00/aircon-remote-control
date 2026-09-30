# Zigbee/MQTT Step 1 — Raspberry Pi 게이트웨이

## 범위

ZBDongle-P가 연결된 Raspberry Pi에 로컬 Mosquitto와 Zigbee2MQTT를 구성한다. 기존
FastAPI 포트 8001 서비스는 유지하며 동글 펌웨어 플래시와 기기 페어링은 포함하지 않는다.

## 사전 확인

- 운영체제: Debian 13 Trixie, arm64
- Docker, Compose, Mosquitto: 미설치
- Debian 저장소 후보: Docker 26.1.5, Compose 2.26.1, Mosquitto 2.0.21
- 디스크: 29 GB 중 약 24 GB 사용 가능
- 메모리: 약 1.8 GiB 중 약 1.6 GiB 사용 가능
- 기존 포트 8001: 정상 사용 중
- 새 포트 1883과 8080: 충돌 없음
- 2.4 GHz Wi-Fi: 채널 4 사용 확인, SSID와 주소는 기록에서 제외
- Zigbee 채널: 공식 권장 ZLL 채널 중 Wi-Fi 채널과 거리를 둔 20으로 최초 고정

## Windows PowerShell에서 SSH 점검 명령 전달 실패

### 증상 1

원격 셸에서 실행하려던 `$()`가 Windows PowerShell에서 먼저 평가되어 로컬에 없는
`dpkg` 명령 오류가 발생했고, SSH로 전달된 문자열의 따옴표도 닫히지 않았다.

### 증상 2

원격 명령을 PowerShell 작은따옴표로 감싼 시도에서는 `ssh.exe` 네이티브 인수 전달
과정에서 내부 따옴표가 제거되어 Bash가 괄호 앞에서 문법 오류를 냈다.

### 증상 3

PowerShell here-string을 표준입력으로 보낸 시도에서는 줄 끝이 CRLF로 다시 기록되어
마지막 `free -h` 옵션 뒤에 `\r`이 붙었다. 나머지 점검은 수행됐지만 해당 명령은
`invalid option`으로 실패했다.

### 원인과 해결 원칙

PowerShell, `ssh.exe`, 원격 Bash의 세 인용·개행 규칙을 긴 한 줄에 중첩한 것이 원인이다.
짧은 조회는 SSH에 단순한 프로그램과 인수만 전달하고, 여러 줄 변경 작업은 저장소에서
LF로 관리한 `.sh` 파일을 체크섬 검증 후 배포해 실행한다. 비밀번호나 원격 셸용 코드가
PowerShell에서 보간되지 않도록 한다.

실패는 Pi 파일이나 설정을 변경하지 않았으며 최종 메모리 확인은 단일 SSH 명령으로
분리해 성공했다.

## 로컬 설계

- 기존 FastAPI는 사용자 systemd 단위로 유지
- Mosquitto와 Zigbee2MQTT만 Compose로 격리
- 공식 Zigbee2MQTT 2.14.1과 Mosquitto 2.1.2 이미지 고정
- 모든 비밀과 동적 네트워크 상태는 `runtime/zigbee/`에 보존
- MQTT와 관리 화면은 Pi 루프백에서만 접근
- 로그는 컨테이너별 10 MB, 3개로 제한
- 배포는 Zigbee 파일 9개만 전송하는 별도 preview-first 스크립트 사용

## 로컬 검증과 첫 배포

- Docker Compose가 서비스 2개와 설정 파일을 정상 해석했다.
- MQTT 1883과 Zigbee2MQTT 관리 화면 8080이 모두 `127.0.0.1`에만 게시됨을
  Compose의 JSON 출력으로 재검증했다.
- 시스템 Python으로 테스트했을 때 FastAPI가 없어 수집 단계에서 실패했다. 코드 결함이
  아니라 잘못된 Python 환경을 사용한 것이 원인이었고, 프로젝트 `.venv`로 다시 실행해
  31개 테스트가 모두 통과했다.
- Windows의 `bash.exe`는 WSL 실행기였지만 설치된 배포판이 없어 문법 검사가 실패했다.
  같은 파일을 Git Bash의 Bash로 검사해 네 개 셸 스크립트가 모두 통과했다.
- 승인 후 Zigbee 전용 파일 9개, 12,910바이트만 Pi에 전송했다. 원격 체크섬과 Pi에서의
  `bash -n` 검사가 모두 통과했으며 파일 삭제는 없었다.
- 시스템 범위에서 추정한 서비스명을 조회했을 때 `inactive`가 나왔지만 실제 에어컨 앱은
  사용자 systemd 단위였다. 올바른 범위에서는 `active`였고, Tailscale 주소의 8001
  `/health`도 성공했다. 앱이 Tailscale 주소에만 바인딩되어 있으므로 Pi의
  `127.0.0.1:8001` 요청이 실패하는 것은 정상이다.
- Docker 설치 전 상태이므로 1883과 8080은 아직 열리지 않았다.

관련 캡처:

- `docs/assets/terminal/24-zigbee-step1-validation-issues.txt/.png`
- `docs/assets/terminal/25-zigbee-step1-local-deploy.txt/.png`

## Docker 호스트 설치 확인

사용자가 Pi 터미널에서 `sudo ./scripts/install_zigbee_host.sh`를 실행했다. 이후 새 SSH
세션에서 다음을 검증했다.

- Docker `26.1.5+dfsg1`, Compose `2.26.1-4` 설치 완료
- `docker.service`가 `enabled`, `active`
- `air` 사용자가 `docker`와 `dialout` 그룹에 속함
- 비밀번호 없는 일반 사용자 명령으로 Docker 데몬 접근 성공
- 기존 사용자 systemd 에어컨 서비스와 Tailscale 포트 8001 상태 정상
- 스택 기동 전 1883과 8080 포트는 비어 있음

관련 캡처: `docs/assets/terminal/26-zigbee-docker-host-install.txt/.png`

## 첫 기동과 점검 타임아웃

초기화 스크립트가 런타임 디렉터리와 비밀정보를 만들고 Mosquitto 및 Zigbee2MQTT
컨테이너를 정상 기동했다. 첫 점검에서는 컨테이너가 실행 중이었지만 MQTT bridge 상태를
15초 안에 받지 못해 `Timed out`으로 종료됐다.

읽기 전용 로그를 확인한 결과 두 컨테이너의 재시작 횟수는 0이었고 직렬 포트도 호스트와
컨테이너 양쪽에서 정상적으로 열렸다. ZBDongle-P의 첫 초기화는 시작 후 약 29초에
완료됐으며, 곧바로 다음 항목이 모두 확인됐다.

- Coordinator 백업 생성
- 펌웨어 형식 `ZStack3x0`, revision `20240710` 인식
- Mosquitto 인증 연결
- `zigbee2mqtt/bridge/state`에 `{"state":"online"}` 발행
- Zigbee2MQTT 관리 화면 시작

즉, 원인은 설정이나 권한 문제가 아니라 첫 기동 시간보다 짧았던 점검 대기시간이었다.
두 번째 점검은 즉시 통과했다. 재현성을 위해 로컬 점검 스크립트의 MQTT 대기시간을
15초에서 60초로 늘렸고, 별도 승인 후 Pi에 반영했다.

관련 캡처: `docs/assets/terminal/27-zigbee-first-start-timeout-recovery.txt/.png`

## 백업 직후 retained `offline` 오판

일관된 스냅샷을 만들기 위해 Zigbee2MQTT와 Mosquitto를 함께 정지한 뒤 39,102바이트의
백업을 생성했다. 파일 소유자는 `air:air`, 권한은 `600`이며 서비스 두 개도 자동으로
재시작했다.

재시작 직후 점검에서는 MQTT bridge 상태가 `offline`으로 나왔다. Zigbee2MQTT는 종료할
때 retained `offline`을 저장하며 기존 점검 코드는 구독 직후 받은 첫 메시지 한 개만
판단했다. 약 2초 뒤 새 프로세스가 `online`을 발행했으며 재점검은 모두 통과했다.

로컬 점검 코드를 다시 개선해 최대 60초 동안 retained 상태를 반복 조회하고 `online`만
성공으로 인정하도록 했다. 같은 유형의 Windows SSH 인용 오류도 한 번 재발했지만 이미
기록한 원인과 동일했고 Pi에는 아무 변경도 일어나지 않았다.

관련 캡처: `docs/assets/terminal/28-zigbee-backup-retained-offline.txt/.png`

## retained 상태 점검 수정 배포

별도 승인을 받은 뒤 `scripts/check_zigbee_stack.sh` 한 파일만 Pi에 다시 전송했다. 로컬과
원격 SHA-256이 일치했고 Pi에서 `bash -n`도 통과했다. 서비스 재시작 없이 실행한 최종
점검에서 다음을 다시 확인했다.

- Mosquitto와 Zigbee2MQTT 컨테이너 실행 중
- Coordinator firmware revision `20240710`, 형식 `ZStack3x0`
- MQTT bridge `online`
- 1883과 8080은 루프백에만 게시
- 기존 에어컨 앱 8001 health 정상

관련 캡처: `docs/assets/terminal/29-zigbee-check-fix-deploy.txt/.png`

## Raspberry Pi 재부팅 자동 복구

사용자가 `sudo reboot`를 실행했고 약 15초 뒤 SSH가 다시 열렸다. `uptime`은 0분으로
실제 재부팅을 확인했다. Docker는 `enabled`, `active`였으며 두 컨테이너, 루프백 포트,
MQTT bridge와 기존 8001 앱도 자동 복구됐다.

첫 점검은 성공했지만 Mosquitto가 재부팅 전 retained `online`을 디스크에 보존했을 수
있으므로 그 결과만으로 Coordinator 복구를 단정하지 않았다. 현재 Zigbee2MQTT 컨테이너의
`StartedAt` 이후 로그만 별도로 조회했고 다음 부팅 과정이 실제로 새로 완료됐음을 확인했다.

- 컨테이너 시작 후 직렬 포트 재개방
- 약 31초 뒤 Coordinator firmware revision `20240710` 재인식
- Mosquitto 재연결 및 새 `online` 발행
- 현재 부팅의 `Zigbee2MQTT started!` 기록
- 컨테이너 비정상 재시작 0회

재발 방지를 위해 로컬 점검 스크립트도 현재 컨테이너 시작 시각 이후의
`Zigbee2MQTT started!`를 최대 60초 기다린 다음 MQTT 상태를 검사하도록 보강했다. 이
수정은 별도 승인 후 Pi에 반영한다.

관련 캡처: `docs/assets/terminal/30-zigbee-reboot-autorecovery.txt/.png`

## Step 1 최종 동기화와 완료 판정

현재 컨테이너 시작 이후 로그를 확인하는 최종 점검 스크립트를 별도 승인 후 Pi에
반영했다. 로컬과 원격 SHA-256이 일치했고, 최종 점검에서 현재 부팅의 Coordinator
초기화와 MQTT `online`을 다시 확인했다.

배포 기준 파일 9개 전체도 로컬과 Pi의 SHA-256을 비교해 모두 일치했다. 프로젝트
가상환경에서 기존 테스트 31개가 통과했다. 이로써 Step 1 완료 기준인 Coordinator 인식,
MQTT online, 루프백 제한, 영구 백업, 재부팅 자동 복구와 기존 8001 서비스 보존을 모두
충족했다.

관련 캡처: `docs/assets/terminal/31-zigbee-step1-final-verification.txt/.png`

## 진행 상태

- [x] USB/직렬 인식과 권한 확인
- [x] Pi 패키지·자원·포트 사전 확인
- [x] Compose와 설정 템플릿 작성
- [x] 설치·초기화·점검·백업·배포 스크립트 작성
- [x] 로컬 정적 검증
- [x] Pi 파일 배포
- [x] Docker 설치
- [x] Coordinator 연결과 MQTT online 검증
- [x] 재부팅 자동 복구
- [x] 민감 백업 생성
