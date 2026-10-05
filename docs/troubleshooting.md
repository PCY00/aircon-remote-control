# 문제 해결 기록

문제가 발생할 때 다음 형식으로 누적한다.

## 기록 형식

- 증상:
- 환경:
- 재현 방법:
- 관찰된 오류:
- 가설:
- 시도한 방법:
- 원인:
- 최종 해결:
- 검증:
- 재발 방지:

## 스마트홈 아이콘이 글자 기호처럼 보임

- 증상: `집에서`, `외출`, 스탠드 조명과 TV 아이콘이 서로 어울리지 않는 문자 기호로
  표시됐고, 하단 메뉴 아이콘도 실제 아이콘 대신 단순 기호에 가까웠다.
- 환경: FastAPI가 제공하는 단일 HTML UI, 외부 CDN 아이콘 스크립트 없음.
- 원인: HTML에는 `data-lucide` 이름이 있었지만 Lucide 렌더러를 불러오지 않았고,
  CSS `::before`의 유니코드 문자가 임시 대체물로 표시되고 있었다.
- 최종 해결: Lucide 1.37.0 UMD 번들과 ISC 라이선스를 `app/static/vendor/`에 고정하고
  FastAPI `/static` 경로로 제공했다. 임시 문자 CSS를 제거하고 SVG 렌더링으로 교체했다.
- 검증: 홈 화면에서 임시 `i[data-lucide]` 0개, `svg[data-lucide]` 52개를 확인했다.
  장면·기기·하단 메뉴의 지정 아이콘 이름이 모두 일치했고 브라우저 warning/error는 0건이었다.
- 재발 방지: 아이콘 라이브러리는 CDN의 `latest`를 사용하지 않고 버전·라이선스와 함께
  프로젝트 안에 보존한다. 새로운 아이콘 이름은 로컬 번들에 실제 존재하는지 검사한다.

## 접근성 알림 문장이 화면 아래에 노출됨

- 증상: 테마를 전환하면 `다크 테마 적용` 같은 접근성 알림 문장이 앱 바깥에 보였다.
- 원인: 알림 영역에 `sr-only` 클래스는 있었지만 시각적으로 숨기는 CSS가 없었다.
- 최종 해결: 화면 판독기는 읽을 수 있고 시각 화면에서는 1px 영역으로 숨기는 표준
  `sr-only` 스타일을 추가했다.
- 검증: 계산된 `position`이 `absolute`이며 최종 라이트·다크 화면에서 문장이 노출되지 않았다.

## 사용자 journalctl에는 파일이 없지만 systemctl에는 서비스 로그가 보임

- 증상: `journalctl --user -u aircon-controller.service`는 `No journal files were found`를
  반환했지만 서비스는 active였고 Tailscale health 요청도 성공했다.
- 추가 확인: `systemctl --user status aircon-controller.service`에는 Uvicorn 시작 완료와
  `/health`, UI, 정적 아이콘, 기기 프로필 API의 HTTP 200 기록이 표시됐다.
- 영향: 이번 배포와 서비스 동작 검증에는 영향이 없지만 장기간 로그 조회 가능 여부는 아직
  확인하지 못했다.
- 현재 판단: 서비스 장애가 아니라 Raspberry Pi OS Lite의 사용자 저널 저장·조회 구성 차이로
  추정한다. 원인은 아직 확정하지 않았다.
- 후속 작업: 실제 송신 서비스 운영 전에 저널 저장 정책과 로그 크기 제한을 함께 확인한다.

## 첨부 사진 원본을 찾을 수 없음

- 증상: 대화에 첨부된 이미지는 보이지만 지정된 로컬 경로를 이미지 검사 도구가 열지 못했다.
- 원인: 해당 시점에 원본 파일이 지정 경로에 없었다.
- 해결: 사용자가 원본 파일을 복구한 후 파일 목록과 크기를 확인하고 원본 해상도로 다시 검사했다.
- 검증: 다섯 장 모두 열렸으며 MCU와 PCB 표기를 이전보다 정확히 판독했다.
- 재발 방지: 블로그에 사용할 원본 사진은 프로젝트의 `docs/assets/`에도 보존한다.

## FastAPI 테스트에서 httpx 사용 중단 예정 경고

- 증상: 테스트 2개는 통과했지만 `Using httpx with starlette.testclient is deprecated; install httpx2 instead` 경고가 출력됐다.
- 환경: FastAPI 0.141.1, Starlette 1.6.0, httpx 0.28.1.
- 원인: Starlette 1.x의 `TestClient`가 `httpx2`를 우선 사용하도록 전환됐고 기존 `httpx` 경로는 호환용으로만 남아 있다.
- 해결: 개발 의존성을 `httpx2>=2.12,<3.0`으로 변경했다.
- 검증: 의존성 재설치 후 경고를 오류로 취급한 테스트와 정적 검사를 다시 수행한다.

## Windows에서 ssh-keyscan 결과가 나오지 않음

- 증상: Raspberry Pi 주소로 `ssh-keyscan`을 실행했지만 제한 시간 내에 호스트 키가 반환되지 않았다.
- 확인: ICMP Ping은 성공했고 TCP 22 포트도 열려 있었다.
- 판단: Raspberry Pi의 SSH 서비스 장애가 아니라 Windows 측 `ssh-keyscan` 동작 문제로 보인다. 정확한 원인은 아직 확정하지 않았다.
- 해결: 대화형 OpenSSH 연결을 사용해 표시된 ED25519 지문을 확인하고 호스트 키를 로컬 `known_hosts`에 등록했다.
- 검증: 비밀번호 인증으로 호스트명 `AC`에 정상 접속해 읽기 전용 명령을 수행했다.

## 프로젝트 SSH 공개키가 등록되지 않음

- 증상: `BatchMode=yes` SSH 연결이 `Permission denied (publickey,password)`로 실패했다.
- 원인: Raspberry Pi의 `authorized_keys` 파일 크기가 0바이트였다. Windows에도 기존 공개키가 없었다.
- 처리: Windows 사용자 SSH 저장소에 프로젝트 전용 ED25519 키를 생성하고 사용자가 공개키를 Pi의 `authorized_keys`에 추가했다.
- 검증: 비밀번호로 Pi에 읽기 전용 접속해 `.ssh`가 `700`, `authorized_keys`가 `600`, 소유자가 `air:air`임을 확인했다. 등록된 키는 한 줄의 `ssh-ed25519`이며 지문이 PC 공개키와 일치했다.

## 프로젝트 개인키가 예상과 달리 passphrase를 요구함

- 증상: `ssh -i <프로젝트 개인키> -o IdentitiesOnly=yes air@<Pi>` 실행 시 Pi 계정 비밀번호 대신 개인키 passphrase 입력창이 나타났다.
- 혼동 지점: 이 입력창은 Pi 로그인 비밀번호 입력창이 아니다. 개인키를 복호화하는 별도의 암호를 요구한다.
- Pi 측 확인: `~/.ssh` 권한 `700`, `authorized_keys` 권한 `600`, 소유자 `air:air`, 키 형식과 공개키 지문이 모두 정상이었다.
- PC 측 확인: 빈 passphrase로 개인키의 공개키를 추출하는 검사가 실패해 개인키 자체가 암호화된 것으로 판정했다.
- 원인: 프로젝트 개인키 생성 과정에서 예상하지 못한 passphrase가 설정됐다.
- 최종 해결: 기존 키를 덮어쓰거나 삭제하지 않고 `airconpi`라는 Pi 전용 ED25519 키를 새로 만들었다. 자동 배포를 위해 새 키의 passphrase는 비워 두고, 공개키만 기존 `authorized_keys`에 중복 검사 후 추가했다.
- 검증: Pi에는 기존 키와 새 키가 각각 한 줄씩 남아 있으며 디렉터리·파일 권한과 소유자가 유지됐다. 암호나 대화형 입력을 허용하지 않는 SSH `BatchMode`로 사설 IP와 호스트명 `AC`에 각각 접속했고, 두 경우 모두 호스트명 `AC`와 사용자 `air`를 반환했다.
- 보안 주의: 개인키 passphrase 입력창에 Pi 계정 비밀번호를 입력하지 않는다. 암호 없는 배포용 개인키는 PC의 사용자 SSH 디렉터리에만 보관하며 저장소나 Pi로 복사하지 않는다. 비밀번호 인증 비활성화는 이번 작업 범위에 포함하지 않았다.
- 재발 방지: 키 생성 직후 공개키 지문을 기록하고, Pi 등록 후에는 반드시 `BatchMode`로 별도 접속 검증을 수행한다.

## GNU stat 확인 출력에 경로가 반복됨

- 증상: 프로젝트 디렉터리 생성 후 `PATH`, `TYPE`, `MODE`, `OWNER` 사이에 경로가 반복돼 한 줄로 붙은 것처럼 보였다.
- 원인: `stat -c` 형식 문자열에서 `%n`을 줄바꿈으로 사용했지만 GNU `stat`에서 `%n`은 파일명을 출력한다.
- 재발: 2026-09-07 Zigbee 백업 파일 검증에서도 여러 필드를 한 형식 문자열에 넣으며
  같은 실수가 재발했다. 백업 파일 자체에는 영향이 없고 표시만 잘못됐다.
- 재발 방지: 여러 메타데이터를 출력할 때 줄바꿈 escape를 추측하지 않는다. 파일명은
  `printf`와 `basename`, 크기·권한·소유자는 별도 `stat -c` 호출로 한 줄씩 출력한다.
- 영향: 확인 출력만 잘못됐고 디렉터리 생성이나 권한에는 영향이 없었다.
- 해결: `readlink -f`로 절대 경로를 별도로 확인하고 `stat -c 'TYPE=%F MODE=%a OWNER=%U:%G'`로 메타데이터를 재검증했다.
- 검증: `/home/air/aircon-controller`, 형식 `directory`, 권한 `755`, 소유자 `air:air`를 확인했다.

## PowerShell에서 SSH로 전달한 Python 한 줄 명령의 따옴표가 깨짐

- 증상: 원격 가상환경에서 FastAPI와 Uvicorn 버전을 출력하려던 `python -c` 명령이 `SyntaxError: unexpected character after line continuation character`로 실패했다.
- 원인: PowerShell 문자열, SSH 원격 명령, Python 문자열까지 세 단계의 인용을 한 줄에 중첩하면서 Python에 전달될 따옴표가 손실됐다.
- 영향: 버전 확인 명령만 실패했다. 직전에 실행한 가상환경 Python과 `pip check`는 정상이며 설치 파일은 변경되지 않았다.
- 해결: 불필요한 중첩 Python 코드를 제거하고 `.venv/bin/python -m pip show fastapi uvicorn`의 결과를 `grep`으로 필터링했다.
- 검증: FastAPI `0.141.1`, Uvicorn `0.52.4`를 확인했다.
- 재발 방지: Windows→SSH 원격 검사에서는 가능한 한 단순한 프로그램 옵션을 사용하고, 여러 언어의 문자열 인용을 한 줄에 중첩하지 않는다.

Tailscale 서비스의 `/health`를 자동 검증할 때도 PowerShell이 원격 셸용 `$()`를 먼저 해석하는 같은 유형의 문제가 재발했다. 해결 시에는 `tailscale ip -4`를 별도의 SSH 명령으로 받아 형식을 검사하고, 검증된 주소를 두 번째 curl 명령에 값으로 전달했다. 실제 주소는 출력과 문서에서 제외했다.

## UI 명령은 HTTP 200인데 IR LED가 동작하지 않음

- 증상: UI에서 에어컨 명령을 누르면 API는 성공하지만 송신 LED와 에어컨 반응이 없다.
- 읽기 전용 확인: `/api/v1/ir/transmitter`가 `transport=mock-ir`,
  `hardware_output=false`와 실제 송신 없음 설명을 반환했다. `/dev/lirc0`는 수신 전용이고
  부팅 설정에는 `gpio-ir-tx`가 없었다.
- 원인: UI와 의미 기반 명령 API만 Pi에 배포됐고 Step 4 물리 송신 경로는 의도적으로 Mock에
  머물러 있었다. HTTP 성공은 명령 기록 성공이지 IR 방출 성공이 아니었다.
- 소프트웨어 처리: 실제 `IrCtlTransport`는 송신 가능한 장치를 기능 조회로 확인하고,
  명령을 raw pulse/space 파일로 직렬화해 `ir-ctl --send`를 실행한다. 장치 없음은 503,
  실행 오류는 502로 반환하며 실패한 명령을 성공 상태로 기록하지 않는다.
- 1차 배포 결과: GPIO18 송신 오버레이와 재부팅 후 `/dev/lirc0`가 raw IR 송신 가능,
  `/dev/lirc1`이 수신 가능으로 열렸다. 오버레이 적용 전 후보였던 `/dev/lirc1`을 송신기로
  지정하자 API가 `hardware_output=false`와 HTTP 503 보호 동작을 유지했다.
- 해결: 장치 번호를 추측하지 않고 각 `/dev/lirc*`의 `ir-ctl --features` 결과로 구분해
  운영 송신 장치를 `/dev/lirc0`로 정정한다.
- 소프트웨어 검증: 정정 후 상태 API가 `available=true`, `hardware_output=true`를 반환했고,
  `POWER_OFF` 1회가 38kHz·2프레임·179,670µs로 오류 없이 처리됐다.
- 후속 검증 순서로 카메라 광출력, HW-477 루프백과 실제 에어컨 반응을 제안했다. 실제로는
  거리·방향을 먼저 조정해 에어컨 반응을 확인했고, 정확한 성공 거리 측정은 남아 있다.

### 모듈 표시 LED는 점멸하지만 에어컨이 반응하지 않음

- 관찰: 최초 `POWER_OFF` 송신 시 모듈의 LED는 점멸했지만 에어컨은 반응하지 않았다.
- 해석: 기판의 가시광 표시 LED는 GPIO18과 트랜지스터의 저속 포락선 동작을 보여줄 뿐,
  투명 IR LED가 충분한 광량과 38kHz 반송파로 출력됐다는 증거는 아니다.
- 분리 진단: 투명 IR LED의 카메라 확인 → HW-477 5~10cm 루프백 캡처 → 원본 패킷과
  pulse/space 비교 → 근거리 에어컨 재시험 순서로 진행한다.
- 결과: 송신기와 에어컨 사이의 거리·방향을 조정한 뒤 실제 에어컨이 정상 동작했다. 회로와
  패킷은 유효하며 최초 실패는 제한된 광출력·송신 각도·조준 조건에 의한 도달 거리 문제로
  판단한다.
- 남은 개선: 설치 예정 거리에서 여러 번 반복하고, 필요하면 IR LED 구동 전류·트랜지스터
  핀 배열·광학 방향 또는 복수 LED 송신부를 검토한다. 정확한 성공 거리는 아직 측정하지 않았다.

## systemctl은 inactive인데 웹 서비스가 실제로 실행 중임

- 증상: `systemctl is-active aircon-controller`는 inactive를 반환했다.
- 원인: 서비스가 시스템 단위가 아닌 `air` 사용자의 systemd 사용자 단위로 설치돼 있다.
- 확인: `systemctl --user is-active aircon-controller`와
  `systemctl --user status aircon-controller`를 사용한다.
- 추가 혼동: 서비스는 보안을 위해 Tailscale IPv4에만 바인딩하므로 Pi 내부
  `http://127.0.0.1:8001` 요청은 실패하는 것이 정상이다.

## Bash 프롬프트가 갑자기 `>`로 바뀜

- 증상: `systemctl is-enabled tailscaled` 앞에 작은따옴표가 붙은 뒤 명령이 실행되지 않고 다음 줄 프롬프트가 `>`로 표시됐다.
- 원인: Bash는 닫히지 않은 작은따옴표 문자열의 나머지를 다음 줄에서 계속 입력받는다. `>`는 이때 표시되는 보조 프롬프트다.
- 해결: `Ctrl+C`로 미완성 입력을 취소하고 따옴표 없이 명령을 다시 실행했다.
- 검증: `tailscaled`의 enabled와 active 상태가 정상 출력됐다.
- 재발 방지: 프롬프트 문자와 명령을 함께 복사하지 않고 코드 블록 안의 명령 본문만 복사한다.

## PowerShell에서 긴 SSH 점검 명령의 인용과 CRLF가 깨짐

- 증상 1: 원격용 `$()` 안의 `dpkg`가 Windows PowerShell에서 먼저 실행되어
  `dpkg is not recognized`가 발생하고 원격 Bash에는 닫히지 않은 따옴표가 전달됐다.
- 증상 2: 원격 명령을 작은따옴표로 감싸도 네이티브 `ssh.exe` 인수 전달 과정에서 내부
  따옴표가 제거되어 Bash가 `syntax error near unexpected token '('`로 종료됐다.
- 증상 3: PowerShell here-string을 파이프로 보낼 때 CRLF가 유지되어 Linux 명령 옵션에
  `\r`이 붙고 `free: invalid option`이 발생했다.
- 영향: 모두 읽기 전용 사전 점검이었으며 Pi 파일·패키지·서비스는 변경되지 않았다.
- 해결: 짧은 명령은 SSH에 프로그램과 인수만 단순하게 전달한다. 여러 줄 설치·변경은
  LF로 저장한 `.sh` 파일을 로컬에서 작성·검증·배포한 뒤 Pi에서 실행한다.
- 검증: `ssh ... air@AC free -h`처럼 분리한 단일 명령으로 누락된 메모리 정보를 정상 확인했다.
- 재발 방지: PowerShell 문자열 안에 원격 `$()`, 작은따옴표, 파이프를 중첩한 대형 명령을
  만들지 않고 배포 스크립트와 체크섬을 사용한다.

같은 유형으로 Tailscale 주소를 얻고 `sed`로 출력을 가리려던 긴 명령도 Windows
PowerShell 파서에서 닫는 괄호와 대괄호를 잘못 해석했다. 주소 자체를 출력하지 않는 짧은
원격 명령으로 바꿔 해결했다. 비식별화는 복잡한 원격 정규식보다 처음부터 민감 값을
출력하지 않는 방식이 우선이다.

## 시스템 Python으로 테스트해 FastAPI를 찾지 못함

- 증상: `python -m pytest -q`가 네 테스트 파일을 수집하면서
  `ModuleNotFoundError: No module named 'fastapi'`로 중단됐다.
- 원인: 프로젝트 의존성이 설치된 `.venv`가 아닌 Windows 시스템 Python을 사용했다.
- 해결: `.venv\Scripts\python.exe -m pytest -q`로 다시 실행했다.
- 검증: 31개 테스트가 모두 통과했다.
- 재발 방지: 저장소 테스트는 항상 프로젝트 가상환경의 Python으로 실행한다.

## Windows bash.exe에 WSL 배포판이 없어 셸 문법 검사가 실패함

- 증상: `bash -n`이 `execvpe(/bin/bash) failed: No such file or directory`를 반환했다.
- 원인: PATH의 `bash.exe`는 WSL 실행기였지만 설치된 Linux 배포판이 없었다.
- 해결: 설치되어 있던 Git Bash의 Bash를 명시적으로 사용했다.
- 검증: Zigbee 설치·초기화·점검·백업 스크립트 네 개가 `bash -n`을 통과했고,
  배포 후 Pi에서도 같은 검사를 다시 통과했다.

## Zigbee2MQTT 첫 기동 점검에서 MQTT 상태가 시간 초과됨

- 증상: Mosquitto와 Zigbee2MQTT 컨테이너는 `Up`이었지만 첫 점검의
  `mosquitto_sub`가 15초 뒤 `Timed out`으로 종료됐다.
- 가설: MQTT 인증 실패, 동글 권한 문제, 잘못된 adapter 형식 또는 초기화 지연을
  구분해야 했다.
- 확인: 컨테이너 재시작 횟수는 0이었고 호스트와 컨테이너 모두 직렬 장치를 인식했다.
  로그상 Zigbee2MQTT 시작 약 29초 뒤 Coordinator 초기화와 MQTT `online` 발행이
  정상 완료됐다.
- 원인: 첫 점검이 기동 직후 시작됐고 대기시간 15초가 초기 Coordinator 구성 시간보다
  짧았다.
- 해결: 상태가 이미 올라온 뒤 재검사해 전체 점검이 통과했으며, 점검 스크립트의 MQTT
  대기시간을 60초로 늘렸다.
- 검증: firmware revision `20240710`, bridge `online`, 1883·8080 루프백 제한,
  기존 8001 health를 모두 확인했다.

## Zigbee 백업 직후 점검이 retained `offline`을 읽고 실패함

- 증상: 일관된 백업을 위해 두 컨테이너를 정지·재시작한 직후, 점검이
  `{"state":"offline"}`을 읽고 실패했다.
- 원인: Zigbee2MQTT가 종료하며 retained `offline`을 발행한다. 기존 점검은 MQTT에서
  처음 받은 메시지 한 개만 검사했기 때문에 새 프로세스가 곧 발행할 `online`을 기다리지
  않았다.
- 확인: 약 2초 뒤 로그에 새 `online`과 `Zigbee2MQTT started!`가 기록됐고 같은 점검이
  통과했다. 두 컨테이너의 비정상 재시작은 없었다.
- 해결: 최대 60초 동안 retained 상태를 반복 조회하면서 `online`인 경우에만 성공하도록
  점검 스크립트를 변경했다.
- 백업 검증: 백업은 39,102바이트, 권한 `600`, 소유자 `air:air`로 생성됐다. 실제
  SHA-256은 운영 기록으로 확인했지만 공개용 캡처에서는 제외했다.

## 재부팅 직후 retained `online`이 새 Coordinator 준비를 오인시킬 수 있음

- 관찰: 재부팅 직후 점검은 MQTT `online`을 반환했지만, 그 시점의 출력에는 현재 부팅의
  Coordinator firmware와 `Zigbee2MQTT started!` 로그가 아직 없었다.
- 위험: Mosquitto의 persistence가 재부팅 전 retained `online`을 복원하면 실제 직렬
  Coordinator 초기화가 끝나기 전에도 단순 MQTT 조회가 성공할 수 있다.
- 확인: 컨테이너의 `StartedAt`을 구한 뒤 그 시각 이후의 로그만 조회했다. 현재 부팅에서
  직렬 포트, Coordinator, MQTT 연결, 새 `online`, 시작 완료가 순서대로 기록됐다.
- 해결: 점검 스크립트가 현재 컨테이너의 `StartedAt` 이후 로그에서
  `Zigbee2MQTT started!`를 최대 60초 기다린 뒤 retained MQTT 상태를 확인하도록 변경했다.
- 검증 결과: 실제 Pi 재부팅 후 Docker, 두 컨테이너, ZBDongle-P, MQTT와 기존 8001 앱의
  자동 복구가 모두 확인됐다.

## 터미널 캡처 렌더러가 프로젝트 가상환경에서 Pillow를 찾지 못함

- 증상: `.venv\Scripts\python.exe scripts\render_terminal_capture.py ...` 실행이
  `ModuleNotFoundError: No module named 'PIL'`로 실패했다.
- 원인: 렌더링 스크립트는 Pillow를 사용하지만 프로젝트 개발 의존성에 명시되지 않아
  기존 `.venv`에 설치되지 않았다.
- 영향: TXT 원문과 Zigbee/Pi 상태에는 영향이 없으며 PNG 생성만 실패했다.
- 임시 확인: Pillow 12.2.0이 설치된 시스템 Python으로 같은 TXT를 렌더링해 PNG 생성과
  육안 검사를 완료했다.
- 해결: `pyproject.toml`의 `dev` 의존성에 `pillow>=11,<13`을 추가한다.
- 검증: 프로젝트 가상환경에 개발 의존성을 다시 설치해 Pillow 12.3.0을 받았다. 같은
  렌더러로 PNG를 다시 생성했고 전체 테스트 31개가 통과했다.

## Zigbee 도어센서 첫 인터뷰가 DatabaseEntry 오류로 실패함

- 증상: 센서가 `Wing`으로 네트워크에 나타난 직후 떠났고 인터뷰가
  `DatabaseEntry with ID '3' does not exist`로 실패했다.
- 관찰: 오류 전에 장치 이탈 로그가 있었고 Coordinator와 기존 TH01은 계속 정상 상태였다.
- 판단: 인터뷰가 사용하던 임시 장치 항목이 장치 이탈로 먼저 제거된 일시적 순서 문제다.
  이 한 번의 오류만으로 영구 데이터베이스 손상이라고 판단하지 않는다.
- 해결: 열린 가입 시간 안에 센서 RESET을 LED가 깜박일 때까지 약 5초 다시 눌렀다.
- 검증: 두 번째 인터뷰와 구성이 성공했고 `Wing/TS0203`, supported=true로 식별됐다.
  자석을 붙이고 떼었을 때 `contact=true/false`가 각각 들어왔다.
- 피한 조치: 서비스 재시작, Coordinator 초기화와 데이터베이스 수동 편집은 하지 않았다.

## PowerShell stdin으로 보낸 Bash 스크립트 끝에 CR 명령 오류가 남음

- 증상: 장치 2대 요약은 정상 출력됐지만 마지막에 `bash: $'\r': command not found`가
  출력됐다.
- 원인: PowerShell `Get-Content`의 네이티브 명령 파이프가 CR 문자를 원격 Bash
  표준입력에 포함했다.
- 영향: 읽기 전용 MQTT 요약이었으며 장치·Zigbee 데이터와 Pi 파일은 변경되지 않았다.
- 해결: 원격에서 `tr -d '\r' | bash -s`로 입력을 정규화했다. 실제 배포는 LF 파일을
  전송하고 체크섬과 `bash -n`을 확인하는 기존 절차를 유지한다.
- 검증: 동일 요약을 다시 실행해 TH01과 TS0203 두 장치가 모두 인터뷰 완료·지원됨으로
  오류 없이 출력됐다.

## 터미널 PNG의 한글이 네모로 표시됨

- 증상: TXT의 한글은 정상이지만 첫 PNG의 제목과 주석은 네모 글리프로 보였다. 전체
  본문을 한글 글꼴로 바꾼 중간 결과에서는 Bash 역슬래시가 원화 기호처럼 표시됐다.
- 원인: 렌더러가 우선 선택한 Consolas에 한글 글리프가 없고 Pillow는 운영체제처럼
  자동 글꼴 대체를 하지 않는다.
- 해결: 한글을 포함한 줄과 제목은 맑은 고딕, 명령·로그처럼 한글이 없는 줄은 기존
  고정폭 Consolas를 쓰도록 `render_terminal_capture.py`를 보완했다.
- 검증: 동일한 UZ-8D/TS0203 캡처를 다시 렌더링해 한글 주석, 영문 명령, 숫자와
  역슬래시가 모두 정상 표시되는 것을 육안으로 확인했다.

## 블로그용 JPEG에 촬영 위치와 휴대폰 정보가 남아 있음

- 증상: 사진 화면과 Windows 미리보기에는 개인정보가 보이지 않았지만 JPEG 내부에 GPS,
  촬영시각, 카메라 모델과 MakerNote가 남아 있었다. 블로그에서 다시 받은 파일은 플랫폼이
  EXIF를 제거해 원본과 다르게 보일 수도 있다.
- 위험: 원본 JPEG를 그대로 공개하면 사용한 블로그 서비스에 따라 촬영 위치가 함께
  배포될 수 있다.
- 확인: 좌표 자체는 출력하지 않고 EXIF GPS 태그 존재 여부와 값이 0이 아닌지만 검사한다.
- 해결: `.venv/Scripts/python.exe scripts/sanitize_blog_images.py --apply docs/assets/`로
  공개 자산을 정리한다. EXIF orientation은 픽셀에 먼저 적용해 사진 방향을 유지한다.
- 검증: 게시 직전에 `.venv/Scripts/python.exe scripts/sanitize_blog_images.py docs/assets/`
  를 실행하고 `PRIVATE_METADATA_COUNT=0`을 확인한다.

## Windows에서 Pi로 전송한 새 셸 스크립트가 직접 실행되지 않음

- 증상: `sudo ./scripts/setup_kiosk.sh`가 `command not found`로 끝났지만 `bash -n`은
  통과했다.
- 원인: Windows에서 새로 전송한 파일에 Linux 실행 비트가 없었다.
- 해결: 첫 설치는 `sudo bash scripts/setup_kiosk.sh`로 실행하고, 설치 스크립트가 자신과
  운영 런처에 `0755`를 적용하게 했다.
- 검증: 설치 완료 후 두 파일의 실행 권한과 키오스크 서비스 시작을 확인했다.

## 키오스크와 tty1 getty 전환 순서 때문에 프로세스가 SIGHUP으로 종료됨

- 증상: `aircon-kiosk.service`는 enabled였지만 시작 직후 inactive가 됐고 실행 프로세스는
  `signal=HUP`으로 종료됐다.
- 확인: 저널에서 키오스크 시작 이후 `getty@tty1` 정지가 실행된 순서를 확인했다.
- 원인: 같은 tty1을 쓰는 두 unit의 충돌 관계만 있고 종료·시작 순서가 없어서 전환 경쟁이
  발생했다.
- 해결: 키오스크 unit의 `After=`에 `getty@tty1.service`를 추가해 getty 정지가 먼저
  완료되도록 했다.
- 검증: 재적용 후 `active (running)`, `NRestarts=0`이며 미연결 HDMI를 기다리는 Bash와
  `sleep 5` 자식 프로세스를 확인했다. 기존 FastAPI 사용자 서비스와 Tailscale도 active였다.

## 문 이력은 0건인데 마지막 상태 변경 시각이 표시됨

- 증상: 문 센서 상세 화면에 `마지막 상태 변경 12:22`가 표시됐지만 열림·닫힘 이력은
  0건이었다. 마지막 보고와 수신 시각은 16:22였다.
- 시간 확인: 최신 Zigbee 원문 `last_seen`의 UTC 시각을 `Asia/Seoul`로 변환하면
  16:22가 맞았다. 서버 시계나 Zigbee 보고가 4시간 틀어진 문제가 아니었다.
- 원인: 첫 접점 보고는 기준 상태라 이벤트로 저장하지 않으면서도 백엔드가 그 시각을
  `last_changed_at`에 넣었고, UI가 이를 실제 변경으로 표현했다.
- 해결: 최초 보고에서는 변경 시각을 비워 두고 실제 접점 전환에서만 기록한다. 기존 DB는
  이력 0건인데 변경 시각이 있는 행만 시작 시 자동으로 비운다.
  UI에는 최초 상태 확인과 실제 변경을 분리하고 절대 시각을 한국 시간으로 고정했다.
- 첫 배포 실패: 최초 수신 시각과 센서 원문 보고 시각이 같다는 조건을 넣어 운영값이 보정되지
  않았다. 실제 전환은 항상 이벤트를 함께 만든다는 불변조건을 사용해 시간 동등 비교를
  제거했다. 실패 당시에도 이벤트 0건과 현재 상태는 그대로였다.
- 보존 범위: 현재 센서 상태, 최초·마지막 보고 시각과 실제 도어 이벤트는 삭제하지 않는다.
- 검증: 최초/반복/열림/닫힘, 기존 잘못된 값 보정, 실제 이벤트 보존을 포함해 전체 테스트
  62개가 통과했다. Pi 재배포 후 현재 닫힘, 최초 확인과 마지막 보고는 유지됐고
  `last_changed_at=None`, 도어 이벤트 0건을 API에서 확인했다.

## 한 번 개폐한 도어센서가 여러 번 열린 것처럼 보임

- 증상: 첫 개폐 실험 뒤 화면에 열림·닫힘 행이 여러 개 생겼고 모두 같은 분으로 보였다.
- 확인: DB에는 16초 동안 `open → closed → open → closed` 네 전환이 서로 다른 원문 보고
  시각으로 저장됐다. UI 렌더링 중복은 아니다.
- 표시상 혼동: 이력 화면이 초를 생략해 네 이벤트가 모두 같은 `20:00`으로 표시됐다.
- 현재 가설: 마지막 세 전환의 간격이 1.7초와 2.4초이므로 밀리초 단위 접점 바운스보다는
  자석을 놓는 동안 감지 거리 경계를 반복해서 넘은 가능성이 높다.
- 다음 검증: 본체와 자석 중앙선을 맞추고 닫힘 간격을 3~5mm로 고정한다. 자석을 3cm 이상
  확실히 떼고 10초, 다시 닫힘 위치에서 손을 떼고 10초 유지해 이벤트가 2건만 생기는지 본다.
- 해결 확인: 자석을 확실히 분리하고 정렬해 닫은 재실험에서는 7초 간격의 열림 1건과
  닫힘 1건만 기록됐고 현재 닫힘 상태가 유지됐다. 첫 현상은 자석이 감지 경계를 여러 번
  지난 것으로 결론 내렸으며 소프트웨어 디바운스는 추가하지 않았다.

## HDMI 화면이 cloud-init 완료 문구에서 바뀌지 않음

- 증상: Pi는 SSH 접속이 되지만 HDMI 화면에는 부팅 콘솔의 마지막 cloud-init 문구가 남고
  스마트홈 웹앱이 나타나지 않았다.
- 하드웨어 확인: HDMI-A-1은 연결됨, 1920×1200 모드와 USB 터치 입력이 인식됐다.
- 프로세스 확인: 키오스크 서비스는 `active`였지만 Cage 아래 Chromium 자식이 없고
  `/run/user/1000`에도 Wayland 소켓이 없었다.
- 숨은 오류 찾기: PAM이 Cage를 로그인 세션 scope로 이동하므로 `journalctl -u`에 핵심
  오류가 보이지 않았다. 현재 부팅 전체 로그에서 `run_kiosk.sh`와 Cage PID를 확인해
  `Unable to open Wayland socket: Invalid argument`를 찾았다.
- 원인: `ProtectSystem=strict`가 적용된 서비스에서 Wayland 런타임 디렉터리를 쓰기 예외로
  열지 않아 Cage가 디스플레이 소켓을 만들지 못했다. 홈의 Mesa 캐시도 같은 이유로
  읽기 전용이었다.
- 해결: `/run/user/1000`만 `ReadWritePaths`에 추가하고 `XDG_RUNTIME_DIR`을 명시했다. Mesa와
  Chromium 캐시는 이미 쓰기가 허용된 `runtime/kiosk/cache`로 지정했다. 전체 홈이나 시스템
  디렉터리의 쓰기 제한은 풀지 않았다.
- 검증: 재배포 후 `aircon-kiosk.service`는 `active`, `NRestarts=0`이었고
  `/run/user/1000/wayland-0` 및 Cage 아래 Chromium 자식 프로세스가 생성됐다. 새 세션에서
  Wayland 소켓 및 Mesa 캐시 읽기 전용 오류가 재발하지 않았으며 Tailscale 경유 health는
  200이었다.
- 상태: 로컬 수정과 테스트는 끝났으며 Pi 반영·실화면 검증 전이므로 아직 해결로 확정하지 않는다.

## SSE 추가 후 온습도 값이 정지 시간에도 바뀜

- 원인: 타이머 조회에만 시간 정책이 있고 실시간 메시지·재접속 강제 조회에는 없었다.
- 해결: 도어만 SSE로 즉시 표시하고 온습도는 설정된 자동 간격 또는 수동 조회로 표시한다.
  재접속 REST에서도 자동 갱신 활성화·한국 시간 정지 구간·마지막 갱신 이후 간격을 검사한다.
- 수신과 표시의 구분: 화면 정지는 MQTT 수신이나 센서 배터리 보고 주기를 바꾸지 않는다.
  Pi는 계속 저장하며 수동 버튼은 가장 최근 저장값을 읽는다.
- 검증: `node --test tests/test_sensor_refresh_policy.cjs`의 12개 테스트와 Python 74개 테스트
  통과. Pi 0.7.0에 배포하고 정적 파일 체크섬 11/11 일치를 확인했다.

## Pi editable 설치에서 setuptools.build_meta를 찾지 못함

- 증상: `pip install --no-deps --no-build-isolation -e .`가 `BackendUnavailable`로 실패했다.
- 원인: 설치된 앱의 런타임 의존성과 패키지를 만드는 빌드 의존성은 다르다. 실행 환경에
  setuptools가 없는데 빌드 격리까지 끄면 `pyproject.toml`의 백엔드를 불러올 수 없다.
- 해결: `.venv/bin/python -m pip install --no-deps -e .`로 기본 빌드 격리를 복원한다.
  이어서 `.venv/bin/python -m pip check`로 앱 의존성 무결성을 확인한다.
- 검증: 0.7.0 설치 성공, `No broken requirements found.`, 앱·키오스크 active,
  API 0.7.0과 SSE ready/keep-alive 확인. 전역 패키지 추가나 앱 의존성 업그레이드는 하지 않았다.
- 기록: [실패·복구 원문](assets/terminal/56-step3-install-build-recovery.txt)과
  [동일 내용 PNG](assets/terminal/56-step3-install-build-recovery.png).

## MQTT는 연결됐지만 Zigbee 가입 명령이 SRSP 시간 초과됨

- 관찰: 2026-09-08 도어 재페어링의 가입 열기와 닫기가 각각
  `SRSP - ZDO - mgmtPermitJoinReq after 6000ms`,
  `SRSP - AF - dataRequestExt after 6000ms`로 실패했다.
- 해석: 게이트웨이가 보낸 동글 제어 명령에 대한 응답 부재다. 센서 배터리나 UI만을
  원인으로 단정하지 않는다. USB UART 인식과 MQTT keepalive는 동글 명령 처리의
  정상 동작을 증명하지 않는다.
- 공식 근거: [Zigbee2MQTT FAQ의 어댑터 정지 안내](https://www.zigbee2mqtt.io/guide/faq/#zigbee2mqtt-crashes-after-some-time).
- 제안된 복구(미실행): 승인 후 Zigbee2MQTT만 정지 → 동글 USB를 뽑고 잠시 기다린 뒤
  다시 연결 → 기존 네트워크 데이터로 시작 → 가입 닫기 성공 응답 및 새 센서 보고 확인.
  DB 삭제, 네트워크 초기화, 펌웨어 변경부터 시도하지 않는다.
- 주의: 닫기 자체가 실패했다면 API나 retained bridge/info의 `permit_join=false`는
  이전 소프트웨어 상태일 수 있다. 복구 후 실제 제어 응답을 다시 검증한다.
- 상태: ISSUE-053 미해결. 원문과 PNG는 캡처 61에 보존했다.

## USB 재삽입 후 게이트웨이 시작 중 xHCI 호스트가 응답하지 않음

- 실제 증상: 컨테이너 시작 전에는 동글 경로가 있었으나 직렬 포트를 여는 중
  `xHCI host controller not responding, assume dead`, `HC died; cleaning up`이 기록됐다.
  이후 `/dev/ttyUSB0`이 없어지고 `lsusb`에는 root hub만 남았다.
- 의미: 커널이 USB 호스트를 동작 불가 상태로 처리한 것이다. 영구적인 하드웨어 파손을
  확정한 표현은 아니다. [Linux xHCI 처리 코드](https://github.com/torvalds/linux/blob/master/drivers/usb/host/xhci-ring.c).
- 이번 조치: 승인된 기존 Zigbee2MQTT 컨테이너 시작 1회만 수행했다. 초기화가 실패했으므로
  온습도 새 보고는 아직 검증하지 못했다. 실패 직전 센서 저장값을 최신 측정으로 쓰지 않는다.
- 제안: 별도 승인 후 Pi 정상 재부팅 1회. USB 재열거, 기존 네트워크 시작, 가입 닫기 성공
  응답, 온습도계의 새 보고를 순서대로 확인한다. 재부팅으로 회복되지 않으면 정상 종료 후
  전원 재연결을 검토한다. 지금 단계에서 펌웨어·USB 절전 설정·DB를 임의 변경하지 않는다.
- 전원 관측: `throttled=0x0`, 38.9°C였지만 모든 USB 전원 문제를 배제하지 않는다.
  [Raspberry Pi 전원 경고 설명](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply-warnings).
- 상태: ISSUE-055 복구 승인 대기. 캡처 63에 명령·오류·전원 상태를 보존했다.

### 2026-09-08 정상 재부팅 후 확인 결과

위 제안 이후 승인된 `sudo reboot` 1회를 실행했다. 새 boot ID와 08:43:54(KST) 부팅을
확인했고 USB UART, 앱·키오스크, Mosquitto와 Zigbee2MQTT가 복구됐다. 이번 시작 로그의
`zigbee-herdsman started (resumed)`와 `Zigbee2MQTT started!`를 확인한 뒤 가입 닫기를
요청했으며 08:45:26 `status=ok`, `time=0` 응답이 돌아왔다. 등록된 센서 2대는 유지됐다.

캡처 64는 운영 복구 증거다. 시작 시 온습도 값 재발행은 전날 `last_seen`을 포함하므로
새 센서 실측으로 계산하지 않았다. 이후 08:47:26(KST) TH01의 새로운 `last_seen`을
포함한 실제 MQTT 보고와 API 수신이 확인됐다(온도 25.08°C, 습도 표시 38.92%).
사용자 버튼 조작 여부는 미확인이며 도어 현장 개폐 검증은 별도 대기다.
최초 USB 정지 원인과 재발 방지는 아직 해결하지 않았고,
USB 재삽입 시 자동 시작 실패에 대한 운영 보완도 남아 있다.

## 장면이 다른 에어컨을 제어하거나 명령 후 표시 상태가 뒤집힘

- 로컬 재현: 장면의 타일과 `activeDeviceId`가 다른 경우 마지막으로 연 상세 기기로
  전송될 수 있었다. 명령 처리 중 상세 화면을 바꾸면 늦은 응답도 다른 화면에 적용됐다.
- 수정: 요청 대상 ID와 기기별 상태를 고정한다. 같은 기기의 중복 요청은 대기/거부하고
  서버에서도 송신과 저장을 같은 잠금 구간에서 처리한다.
- 검사: `node --test tests/test_device_ui.cjs` 및
  `python -m pytest tests/test_device_service.py`.
- 현재 검증은 로컬 mock 기준이며 실제 여러 송신 노드를 연결한 결과는 아니다.

## 늦은 센서 보고나 조회 응답 때문에 문 이력이 되돌아감

- MQTT source timestamp가 최신 저장 보고보다 엄격히 과거이면 상태/이력 변경에서
  제외한다. 동일 초의 보고와 timestamp 없는 보고는 별도 처리해 정상 개폐를 보존한다.
- 브라우저는 조회 중 도착한 SSE 최신 상태를 우선하고, 이력 조회 응답의 순서를 검사한다.
  네트워크 실패 때 기존 기록을 지우지 않는다.
- 검사: `python -m pytest tests/test_sensor_service.py`와
  `node --test tests/test_sensor_refresh_policy.cjs`.
- 이 보호 로직이 센서 자체 접점 흔들림·실제 반복 개폐를 제거하는 것은 아니다.
  원인 판단에는 원본 보고 시각과 payload가 필요하다. 게이트웨이 시계 역행도 별도 확인한다.

## ESP32-H2 전송 오류 후 추가 명령이 거부됨

- 2026-09-12 개선 소스는 `rmt_transmit` 오류 또는 완료 대기 timeout 후 오류 상태를
  유지한다. 비동기 드라이버가 여전히 이전 버퍼를 읽을 수 있어 재사용을 금지한 것이다.
- 실제 오류 로그를 저장하고 배선·USB·전원 조건을 확인한다. 반복 전송으로 덮지 말고
  현재 드라이버 상태를 재시작으로 초기화한 뒤 한 번씩 시험한다.
- 호스트 검사: `python -m pytest tests/test_h2_ir_firmware.py`.
  실기기 적용 여부는 부팅 도움말과 플래시 이력으로 구분한다.

## 새 PC의 펌웨어 helper가 COM 포트를 요구함

- `build`는 포트 없이 가능하지만 `flash`와 `monitor`는 실제 확인한 `-Port COMx`가
  필요하다. 이전 PC의 COM6를 자동 사용하지 않는 의도된 보호다.
- 도구 경로는 `-IdfPath`, `-IdfToolsPath`, 빌드 루트는 ASCII `-BuildRoot`로 지정한다.
  출력된 `BUILD_DIRECTORY`가 현재 빌드 위치다. 과거 공용 빌드 폴더/ZIP을 혼동하지 않는다.
- 검사: Windows에서 `python -m pytest tests/test_firmware_build_script.py`.
  이 테스트는 가짜 SDK로 helper 동작만 검사하며 실제 flash를 하지 않는다.

## A50 재부팅 뒤 무선 디버깅 허용창이 계속 기다림

- 암호·패턴을 제거해도 드래그 잠금화면이 남을 수 있다. 화면 켜짐만으로 잠금 해제가
  완료되지는 않는다. 0.4.0 실제 시험에서 드래그 해제 후 자체 관리 앱이 집 Wi-Fi 허용창을
  처리했다. 이 시험을 수동 조작 없는 복구로 기록하지 않는다.
- 사용자가 드래그 화면 제거를 요청한 경우에만, 확인된 페어링 기기에서 locksettings
  get-disabled와 비밀번호 인자 없는 verify 결과를 확인한다. 암호 없는 상태의 verify가
  실패하면 중단하며 암호를 추측하거나 clear 명령을 실행하지 않는다.
- 이 A50에서는 locksettings set-disabled true로 잠금 없음 설정을 적용했고 재조회는 true다.
  복원하려면 같은 암호 없는 조건에서 set-disabled false로 드래그 화면을 되돌릴 수 있다.
  이 A50의 후속 재부팅에서 잠금 없음 설정 유지와 손대지 않은 연결 복구를 확인했다.
  5분 연결 유지·화면 꺼짐 2분 SSH/ADB도 통과했다. 기록 125·129·130·133 참조.
- SSH RPC의 명시적 result=1은 요청 수락이다. TermuxAm은 이때 프로세스 종료 코드도 1을
  반환할 수 있다. 복구 성공은 별도의 TLS ADB 모델·식별자 검증으로 판단한다.
- 관리 앱은 등록 Wi-Fi 이름과 BSSID가 모두 일치하는 시스템 무선 디버깅 허용창만 처리한다.
  새 Wi-Fi/AP, 페어링 초기화, 보안 잠금 추가, 관리 권한 제거는 재설정·재검증 대상이다.

## A50 일반 앱 사용 중지와 복원

- scripts/android/a50_app_cleanup.py는 기본 미리보기이며 --apply만 실제 변경한다.
  대상 10개와 보호 대상 28개를 고정해 비슷한 이름의 시스템 앱을 처리하지 않는다.
- 최초 상태는 Git 제외 .deploy/a50/app-cleanup-20261002.json에 보존한다.
  --restore는 미리보기, --restore --apply는 실제 복원이다. 기본 활성(0)은 default-state,
  명시적 활성(1)은 enable을 사용한다. 최초 파일을 현재 disabled-user 값으로 덮어쓰지 않는다.
- 사용자 앱 삭제나 데이터 초기화 대신 disable-user를 사용했다. 대상마다 installed=true와
  데이터 디렉터리 식별값 유지를 확인했으며 데이터 내용 전체 검사로 표현하지 않는다.
- dumpsys package의 Hidden system packages는 업데이트 전 원본이다. 현재 Packages의
  활성 블록을 읽어야 한다. sharedUser 메타데이터는 이름만 보고 안전하다고 판단하지 않는다.
  실제 UID 사용 패키지 목록의 단독 사용 여부까지 확인한다. 기록 135~139 참조.

## A50 load average가 높지만 CPU는 낮음

- 2026-10-02 측정에서 CPU TOTAL은 2.8%·1.5%였고 D 상태 커널 작업은 각각 17개였다.
  /proc/stat의 procs_blocked는 0이었다. D 상태를 곧바로 저장장치 병목으로 해석하지 않는다.
- 일반 Linux load는 실행 중 작업과 중단 불가능한 대기 작업을 함께 계산한다.
  [커널 부하 계산 근거](https://github.com/torvalds/linux/blob/master/kernel/sched/loadavg.c).
  이 기기의 부하와 커널 대기는 관련 가능성이 있으나 정확한 대기 원인은 미확정이다.
- 두 번째 top 표본·앱별 PSS·MemAvailable을 함께 읽는다. 첫 top 표본은 측정 프로세스의
  초기 실행 비중이 높을 수 있다. 캐시를 지우거나 보안·전원 커널 작업을 종료하지 않는다.
  실제 자료는 기록 138·140과 블로그 2편이다.

## A50 중앙 서비스가 반복 종료되거나 준비 상태 503을 반환함

- 중앙 서비스 경로는 $PREFIX/var/service/aircon-central이며 기존 SSH 서비스와 분리한다.
  ~/.local/state/aircon-central/server.log와 service-log/current의 실제 오류를 먼저 읽는다.
- 5분 안에 비정상 종료 5회면 CENTRAL_RESTART_BLOCKED와 down 표시를 남긴다.
  부팅 훅은 이 중지를 해제하지 않는다. 디스크·의존성·DB·설정 문제를 수정한 뒤
  실패 기록 만료를 확인하고 sv-enable aircon-central로 명시적으로 시작한다.
- /health/live 성공은 프로세스 실행만 뜻한다. /health/ready=503이면 SQLite 준비를
  확인한다. 누락 DB를 readiness가 자동 생성하지 않는다. 원본·백업을 보존해 복구하며
  기록 없이 DB를 새로 만들거나 알려지지 않은 스키마를 덮어쓰지 않는다.
- 기본 배포는 미리보기다. 원격 변경 검사로 중단되면 deployment.json과 실제 파일의
  차이를 먼저 확인하고 사용자 변경을 보존한다. 부분 설치를 자동 삭제하지 않는다.
- 운영 명령과 구체적 경로는 services/central-server/README.md, 실제 기록은 143~148이다.


## A50 집·가족 API (2026-10-02)

- `ModuleNotFoundError: jwt`가 점검 스크립트에서만 발생: 시스템 Python 대신
  `$HOME/services/aircon-central/.venv/bin/python`으로 실행한다. 실제 서비스 상태는 health로 따로 확인한다.
  오류 158과 수정 후 160의 실제 출력 보존.
- `authentication_not_configured`/503: 실제 Firebase 프로젝트 ID가 비공개 config.json에 있는지 확인한다.
  임의 사용자 헤더나 검증 우회 모드를 추가하지 않는다. 설정 오류는 로그에 값 없이 종류만 남긴다.
- `authentication_unavailable`/503: Google 공개 인증서 HTTPS 연결과 시간·인증서 캐시 만료를 확인한다.
  만료된 키를 무한 재사용하거나 서명 검증을 끄지 않는다.
- 같은 초대가 수락 안 됨: 이메일·기존 계정 ID·24시간 만료·이미 사용 여부·이전 권한 회수를 확인한다.
  제외 이전 초대는 사용할 수 없으며 소유자가 새 초대를 발급해야 한다.
- 스키마 업데이트 실패: 중앙 서버 down/제한 로그를 확인하고 SSH는 유지한다.
  릴리스 체크섬·가상환경 pip check·DB integrity·backups의 원본 스키마를 확인한다.
  새 데이터 유무를 검토하기 전 백업을 덮어쓰거나 기존 데이터를 지우지 않는다.

## 가족 Android APK (2026-10-02)

- `google-services.json` 다운로드 대기 시간 초과는 Firebase 앱 등록 실패와 구분한다.
  콘솔에서 패키지·SHA 유형을 확인하고 실제 구성 파일을 `.deploy/family-app/`에 저장한다.
  실제 파일이 없으면 production 빌드를 완료했다고 기록하지 않는다. `--fixture-only`로 별도 시험만 가능하다.
- manifest의 application label 충돌: fixture manifest의 `tools:replace="android:label"`로
  시험 이름을 명시한다. 172의 오류와 175의 빌드 성공 기록을 보존했다.
- `closeSoftKeyboard` 모호성: `androidx.test.espresso.action.ViewActions.closeSoftKeyboard()`로
  지정한다. `doesNotExist()`는 ViewAssertions 정적 import가 필요하다. 173→175 참조.
- 시험을 다시 실행할 때 8765 포트가 열려 있으면 준비 도구는 기존 키·토큰을 덮어쓰지 않는다.
  `stop_family_fixture.py`로 기록 PID와 명령을 확인해 해당 시험 서버만 종료한 뒤 준비·빌드·설치한다.
- Gradle `daemon disappeared`의 원인을 로그와 실행 조건으로 판단한다. 170은 대기 점검 후
  개발자가 중단한 실행이며 메모리 부족의 증거가 아니다. Platform Tools 경고는 공식 SDK 패키지 추가로 해결했다.
- A50에 Google 계정이 0개인 경우 실제 로그인 성공을 주장하지 않는다. fixture UI/API 통과와
  사용자의 실제 Google 로그인 결과는 별도로 기록한다. HTTP localhost는 같은 휴대폰 내부를 뜻한다.
- release APK의 네트워크 XML을 소스 경로로 찾지 못하면 리소스 최적화에 따른 파일명 변경을
  확인한다. 실제 `aapt2 dump resources`의 xml/network_security_config 경로와 manifest 참조를
  비교한다. 정책을 끄거나 HTTP를 켜서 검사 오류를 우회하지 않는다. 190 오류와 191 수정 후 검사 참조.
- SDK의 다국어 리소스 표를 Windows 기본 CP949로 읽으면 디코딩 오류가 날 수 있다.
  검증 도구는 subprocess 출력에 encoding=UTF-8을 지정한다.

## A50 외부 HTTPS 시험 통로: 새 서비스 인식 지연

2026-10-02 첫 배포에서 `sv-enable aircon-public-tunnel`이
`unable to open supervise/ok: file does not exist`로 실패했다.
소스·훅 전송은 완료됐지만 runsvdir가 새 서비스 폴더를 아직 인식하지 못한 시점이었다.
읽기 전용 점검에서는 이후 서비스가 실행되고 터널에 연결된 것을 확인했다.
배포 도구에 최대 15초 인식 대기를 추가한 뒤 명시적인 재배포·정상 중지/시작을 확인했다.
원본 오류는 203, 해결은 204, 외부 검증은 205~206 캡처에 남겼다.
기존 중앙 API나 관리 SSH를 재시작할 필요는 없었다.

Windows 검사에서 `os.O_NONBLOCK` 상수가 없는 오류도 발견했다.
POSIX runit FIFO 제어가 없는 환경에서는 `down` 파일을 유지하고 플랫폼 예외를 처리하도록
수정해 7개 검사를 통과했다. A50 터널 네트워크 오류와 구분한다.

Quick Tunnel 재시작 후 예전 앱 주소가 연결되지 않으면
`verify_a50_tunnel.py`가 확인한 비공개 `endpoint.url`을 사용한다.
시험 주소는 재시작마다 바뀐다. 고정 주소가 필요하면 도메인과 named tunnel을 준비한다.

## A50 실제 release APK의 UI 검사와 캡처 경로

2026-10-02 실제 Google 로그인 후 APK 검사에 `ActivityTestRule`이 빠져 집 목록을 기다리다
실패했다(217). 원래 MainActivity를 명시적으로 실행한 뒤 정상 계정 세션을 사용하도록 수정했다.
한글 집 이름은 UI 자동화의 `ACTION_SET_TEXT`로 넣으며 토큰을 읽거나 로그인 절차를 우회하지 않는다.

대상은 실제 release 앱인데 검사 APK의 `getContext().getFilesDir()`에 캡처를 쓰려다 ENOENT가
발생했다(219). 원래 대상 앱의 `getExternalFilesDir("test-captures")`에 가린 PNG를 저장하고
실제 경로를 검사 결과로 전달해 읽는다. release 앱을 디버그 앱으로 바꾸거나 광범위한
저장소 권한을 추가하지 않는다. 최종 221 검사에서 OK (1 test), 4.26초·가린 이미지 추출을 확인했다.
검사 도구는 JUnit 성공 결과도 검사한다. adb 명령의 종료 코드 0만으로 검사 성공을 판정하지 않는다.

키보드 표시 후 좌표가 바뀌는 UI에서는 입력 후 UI 트리를 다시 읽고 저장 버튼을 선택한다.
UI 트리의 빈 EditText에는 안내 문구가 text로 반환될 수 있어 실제 입력과 구분한다(211~214).

실제 사용자·집 등록 후 읽기 전용 서버 점검에서 사용자/허브 수를 무조건 0으로 기대하지 않는다.
실제 수는 메타데이터로 기록하고 설정한 Firebase 발급자·DB 무결성·원래 식별자·소스 일치를 검증한다.

## FCM 설치 등록과 서버 키 다운로드는 서로 다른 단계다

2026-10-02 앱의 ‘알림 연결됨’과 실제 설치 등록 검사는 통과했다(237~238).
서버 전송 키가 없어도 등록은 가능하며, 이 상태에서 시험 전송은 503이다.
Google Cloud의 키 생성 안내는 A50 키 설치나 실제 수신 성공을 뜻하지 않는다.

키 생성 전에 브라우저 다운로드 이벤트 수집을 연결하지 않아 저장 경로를 얻지 못했다.
나중에 이벤트를 기다리는 방식은 타임아웃이었다. 알려진 정확한 파일명으로 사용자 폴더를
검색해도 처음 결과는 0이었다. 이후 사용자가 다시 다운로드한 파일을 바탕화면에서 확인해
서버에 연결했다(248~249). 기존 `google-services.json`은 앱 설정이며 서버 키가 아니다.
개인 키 내용을 채팅·터미널 캡처로 보내지 않는다. 경로가 없다고 중복 키를 만들지 않는다.
향후 새 다운로드를 수행할 때는 생성 버튼을 누르기 전에 수집을 준비한다.

파일이 확인되면 `configure_a50_fcm.py --source "[절대경로]"`로 미리보기하고, `--apply`로
전용 프로젝트·계정 확인 후 반영한다. 기존 다른 키가 있으면 중단한다. 준비 상태 200은
키 파싱과 API 가용성 검사이며 OAuth 전송 성공과 단말 수신 검사는 별도로 수행한다.

FCM 응답의 UNREGISTERED는 해당 등록 버전의 토큰만 비활성화한다.
일반 INVALID_ARGUMENT를 토큰 무효로 오인하지 않는다. 일시 오류는 만료·횟수 제한 안에서
재시도한다. 테스트의 가상 공급자 응답과 운영 Google API의 접수·실제 단말 표시는 구분한다.

실제 수신 검사에서 집 상세 화면이 나타나도 이벤트 조회 중에는 전송 버튼이 비활성이다.
첫 검사는 이를 기다리지 않아 `Own-family button did not accept click`으로 실패했다(251).
당시 DB 전송 작업은 0개였고 수신 성공으로 기록하지 않았다(253). 검사 helper가 실제
버튼 활성화를 기다리도록 수정하고 시험 APK만 빌드해 백그라운드 검사를 통과했다(255).
화면 꺼짐은 `PowerManager.isInteractive()`가 false인 뒤 요청하고 수신 때에도 false인지
확인하는 별도 검사로 통과했다(258). 실제 release APK와 로그인 데이터는 보존했다.

접근성 트리의 문구가 바뀐 직후에는 캡처 픽셀이 이전 프레임일 수 있다. 최초 수신 후 캡처는
집 목록을 보여줬다. 검사에 main UI idle·짧은 프레임 대기와 문구 재확인을 추가했고,
화면 꺼짐 수신 뒤 실제 ‘최근 알림 수신 완료’ 화면을 시각적으로 확인했다.

## Pi 독립 연결 배포 검사의 Windows 심볼릭 링크 오류

2026-10-02 `WinError 1314`는 로컬 Windows에서 Linux용 링크를 만들 권한이 없어서 발생했다.
로컬 플랫폼에 해당하지 않는 두 검사를 제외하고, `check_installer_posix.py`를 Pi 임시 폴더에서
실행해 실제 링크·체크섬·원본 DB 보존·원격 편집 보존을 확인했다. service runner는 대체 함수로
실제 운영 서비스 명령을 호출하지 않는다. 실패 기록 265와 Linux 검증 267을 보존했다.
시험 결과와 실제 운영 배포 성공은 구분한다.

Pi SSH 도구는 접속 모듈에서 A50 기록 도구의 경로를 준비한다. import 정렬 뒤 해당 도구를 먼저
import해 `ModuleNotFoundError`가 발생하면 `pi_session`의 명시적 export를 통해 가져온다.
민감한 키 stdout은 일반 기록 logger로 전달하지 않고 private_json 경로에서만 처리한다.

Android JUnit은 첫 상태 메시지 앞에 클래스명을 붙일 수 있다. 실제 native 준비 메시지의 끝을
정확히 확인하고 나서만 Pi 연결 시험 이벤트를 보낸다. native 실패 시 출력·실패 상태를 보존하며
Pi 이벤트를 보내지 않는다. 센서 변화를 가짜로 만들어 시험하지 않는다.


## 새 휴대폰의 시험 알림에서 “이미 등록됐거나 다른 등록과 충돌했어요”

2026-10-02: 사용자가 A50 이외 휴대폰에 0.2.0 APK를 설치하고 같은 Google 계정으로
로그인했다. 집의 `hub.connection_test` 기록은 보였지만 시험 알림 버튼에서 위 문구가 나왔다.
기록 조회는 가족 계정 권한으로 가능하며, 알림 수신은 각 휴대폰에서 별도로 켜야 한다.

읽기 전용 확인 당시 서버의 활성 설치는 1개(A50)였다. 코드상 시험 알림은 지정한 설치가
등록되지 않았으면 `installation_not_registered`와 HTTP 409를 응답한다. 0.2.0 화면은 모든
409를 같은 “충돌” 문구로 표시한다. 이 경우 실제 토큰·기기 ID 충돌이 확인된 것은 아니다.
사용자 휴대폰의 알림 설정 상태와 최종 수신은 아직 확인하지 않았다.

재현·해결 순서:

1. 집 목록 → 알림 설정 → 이 휴대폰 알림 켜기.
2. Android 알림 권한 요청이 나오면 사용자가 허용한다.
3. 알림 연결 확인을 눌러 “알림 연결됨”을 확인한다. 준비 중이면 잠시 기다린 뒤 다시 확인한다.
4. 집을 열어 이 휴대폰에 시험 알림 보내기를 누른다. 집당 1분 제한도 적용된다.
5. 계속 “알림 연결 확인 필요”라면 등록 단계의 오류를 조사한다. 앱 삭제·로그아웃이나
   기존 A50 등록 삭제부터 하지 않는다.

동일 계정도 서로 다른 설치 ID·증명·FCM 토큰이면 여러 휴대폰을 등록할 수 있다.
집 이벤트는 등록한 각 휴대폰으로 보내고, 시험 알림은 버튼을 누른 휴대폰 하나만 대상으로 한다.
집 기록에서 연결 시험이 보인다는 사실만으로 해당 휴대폰 FCM 수신을 확인한 것은 아니다.

실제 민감정보 없는 등록 수 점검: [298번 원문](assets/terminal/298-a50-second-phone-notification-diagnosis.txt).

0.3.0에서는 미등록·꺼짐·권한 차단·준비 중·실제 충돌을 구분한다. 사용자도 기존 폰에서 알림을 켠 후 수신 성공을 확인했다. [업데이트 재현](../server/docs/blog/mobile-app/08-notification-choices-and-home-management.md).

## 백그라운드 FCM 검사에서 전환 시각 조건 실패

0.3.0 재검사에서 서버 accepted와 별개로 native ‘Home 전환 이후 새 콜백/게시’ 조건이 실패했다(313).
기존 시험은 UI로 먼저 전송한 뒤 Home으로 이동하고 300ms 대기 후 기준 시각을 저장한다. 빠른 콜백과 전환이 경쟁할 수 있다.
실패 당시 세부 시각 자료는 부족하므로 실제 실패 원인을 확정하지 않았다. 같은 APK의 화면 꺼짐 후 요청 시험은 8.553초 통과했다(316).
백그라운드 확인 후 정상 소유자 API로 요청하도록 검사 순서를 바꾸고 콜백/게시 진단을 추가했다.
수정 검사는 8.902초, 새 콜백·전환 후 콜백·게시 모두 true로 통과(319). 실패를 삭제하거나 accepted를 실제 수신 증거로 대신하지 않는다.


## 가족 앱 버튼을 누르면 맨 위로 이동함

0.3.0의 알림 저장과 연결 확인은 새 ScrollView를 만들었다. onResume도 로그인 뒤 무조건 집 목록을 열었다. 0.4.0에서 알림 상태를 현재 뷰에서 갱신하고 기존 화면의 복귀 경로를 유지하며 집과 화면별 스크롤을 복원했다. 실제 A50에서 알림 상세 315px, 집 새로고침과 탭 복귀 200px을 유지했다. [재현과 실제 출력](../server/docs/blog/mobile-app/09-ui-redesign-and-scroll.md).

0.4.0에서는 설정 → 알림 설정 → 이 휴대폰에서 받기 스위치로 알림을 켠다. 종류와 간격을 바꾼 뒤 하단의 선택 저장을 누른다. 연결 준비 중에는 상태가 갱신될 때까지 기다리거나 알림 연결 확인을 누른다.

UI 검사도 화면의 실제 위치를 따라야 한다. 아래쪽 버튼을 누르고 위쪽 버튼을 찾을 때 아래로만 스크롤하면 실패한다. 접근성 노드의 화면 위치와 스크롤 영역을 비교해 앞으로 또는 뒤로 이동한다. 같은 APK에서 실패 338을 보존하고 수정 검사 341이 통과했다.
