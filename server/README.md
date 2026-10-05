# Galaxy A50 가족 서버와 Android 앱 만들기

## 블로그를 따라 할 코드 내려받기

블로그에서 사용하는 앱·중앙 서버·Pi 연결 서비스·설치 도구·글과 공개용 사진을 **이 `server` 폴더에 함께 넣었다.** 별도로 코드 ZIP을 블로그에 첨부할 필요 없이 이 GitHub 폴더를 연결하면 된다.

**A50 관련 코드의 기준 위치는 이 폴더 한 곳이다.** 저장소 루트의 `app`, `firmware`, `deploy` 등은 Pi 에어컨 제어용이다. A50 앱·서버·설치 도구·테스트를 루트에 다시 복사하지 않는다.

이 저장소의 **main → Code → Download ZIP**에서 현재 코드를 내려받는다. ZIP에는 저장소 전체가 들어 있으므로 압축을 푼 뒤 안쪽의 **`server` 폴더**를 사용한다. 이 폴더를 `C:\`로 옮기고 `smart-home-reader`로 이름을 바꾸면 아래 글의 경로와 같다. 이미 같은 이름의 폴더가 있다면 새 빈 경로를 사용한다.

```text
server/                 ← 이 폴더에서 시작한다
├─ scripts/             PC에서 휴대폰·Pi를 준비하는 도구
├─ services/            중앙 서버·HTTPS 통로·Pi 연결 서비스
├─ android/             가족 앱과 A50 관리 앱 소스
├─ examples/mobile-app/ 본인 설정을 만들 때 참고할 예시
├─ docs/                따라 하기 글과 공개용 사진
└─ tests/               준비 도구와 서버의 동작 확인
```

처음에는 [시작 안내](docs/blog/mobile-app/00-reader-start.md)와 [직접 진행한 글 모음](docs/blog/mobile-app/README.md)을 읽는다. 글에 들어 있는 PC 명령은 `scripts`, `services`, `android`, `docs`가 바로 아래에 보이는 폴더에서 실행한다. 실제 계정 설정·접속 키·FCM 전송 키·APK는 올리지 않았으며, 본인 Firebase 프로젝트와 앱 서명으로 설치 파일을 만든다.

Python 3.12를 설치한 뒤 PowerShell에서 필요한 Python 도구를 준비한다. 이 명령은 휴대폰에 연결하거나 서버를 변경하지 않는다.

```powershell
Set-Location C:\smart-home-reader
Get-ChildItem scripts, services, android, docs
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r examples/mobile-app/requirements-reader.txt
.venv/Scripts/python.exe -m pip check
```

### Git으로 내려받는 경우

ZIP 대신 Git을 사용한다면 새 빈 경로에 아래처럼 `main`의 현재 코드를 내려받는다. 명령을 실행할 위치는 저장소 루트가 아니라 안쪽 `server` 폴더다.

```powershell
git clone --branch main --single-branch https://github.com/PCY00/aircon-remote-control.git C:\smart-home-project
Set-Location C:\smart-home-project\server
```

아래 내용은 전체 연결을 한눈에 보는 설치 안내다. 세부 화면과 실패·해결 과정은 위 글 모음에 정리했다.

자동 확인을 실행할 때도 이 폴더에서 `.venv/Scripts/python.exe -m pytest -q`를 사용한다. `pytest.ini`가 A50 테스트 위치를 지정한다. 루트의 Pi 테스트와 각각 실행한다.

이 문서는 [메인 설치 가이드](../README.md)의 **맨 마지막에 있는 선택 단계**를 자세히 설명한다. 먼저 Raspberry Pi의 Zigbee 센서와 웹 대시보드가 동작하도록 메인 가이드 1~9단계를 끝낸다. A50 서버가 없어도 집 안 제어와 Tailscale 접속은 가능하다.

남는 Galaxy A50은 가족 계정과 알림을 처리하는 중앙 서버다. Pi에서 새로 발생한 문·온습도·경고 기록을 받아 가족 앱에서 조회하고, 선택한 알림을 Firebase Cloud Messaging(FCM)으로 보낸다. **가족 앱에는 현재 에어컨 조작 기능이 없다.** 냉방·끄기 명령은 Pi의 웹 대시보드에서 사용한다.

```text
Zigbee 센서 → Pi의 기존 웹앱·센서 DB → Pi 전용 연결 서비스
                                         │ HTTPS·기기별 비밀 키
                                         ▼
                              A50 중앙 서버·가족 권한
                                         │ FCM
                                         ▼
                              가족 Android 앱의 알림·기록
```

현재는 A50 Android 11, 가족 앱 0.4.0, 중앙 서버 0.4.0/DB 스키마 4의 **시험 구성**이다. 사용한 A50에는 최신 보안 업데이트가 제공되지 않는다. 공개 인터넷에서 오래 운영할 서버나 안전이 중요한 원격 제어 장치로 완성된 상태가 아니다. Cloudflare Quick Tunnel은 테스트용이며 주소와 가동 시간이 고정되지 않는다. 공유기 포트포워딩으로 Pi나 A50의 내부 포트를 직접 열지 않는다.

## 1. 무엇을 준비하나

| 준비물 | 역할과 이 저장소의 파일 |
| --- | --- |
| 메인 가이드를 마친 Pi | Zigbee 센서·문 기록·온습도·대시보드. [Pi 연결 서비스 코드](services/pi-central-agent/) |
| 남는 Galaxy A50와 충전기·Wi-Fi | Termux에서 중앙 API 실행. [A50 준비 과정](docs/blog/mobile-app/01-galaxy-a50-preparation.md) |
| 개발 PC | 이 저장소와 Python 가상환경, Git, A50에 대한 공개키 SSH 연결. Android 앱 빌드에는 JDK 17과 [도구 준비 스크립트](scripts/android/prepare_family_tools.py) |
| Firebase 프로젝트와 Google 계정 | 앱 Google 로그인과 FCM. 앱 패키지 이름은 `com.aircon.family` |
| 앱 전용 서명 키와 Android 설정 파일 | [가족 앱 소스](android/family-app/). 실제 파일은 Git 제외 폴더 `.deploy/family-app/`에만 보관 |
| FCM 전송용 서비스 계정 JSON | A50 서버에서 Google에 알림을 요청하는 **별도 개인 키**. 앱의 `google-services.json`과 다름 |
| 외부 HTTPS 경로 | 현재 [A50 시험용 터널](services/central-tunnel/) 사용. 영구 주소는 아직 없음 |

이 저장소에 실제 비밀번호·개인 키·Google 서비스 계정 JSON·운영 주소는 없다. Git에서 제외한 `.deploy/`의 값은 **각자 자신의 장비와 Firebase 프로젝트로 채워야 한다.** 다른 사람의 프로젝트 ID, 앱 서명 지문, 집 이름, SSH 주소를 그대로 복사하지 않는다. 아래 명령은 `server` 폴더를 연 Windows PowerShell에서 실행한다. 이 폴더를 `C:\smart-home-reader`로 옮겼다면 그 경로에서 실행한다. Pi와 A50에서 직접 실행할 명령은 따로 표시한다.

## 2. A50에 원격 관리 통로 만들기

1. 자신이 소유한 A50을 충전 중인 Wi-Fi에 연결한다. F-Droid 배포의 Termux와 Termux:Boot를 설치하고 한 번씩 연다. Termux에서 `pkg update`, `pkg install openssh`를 실행한다.
2. PC에서 **A50 전용 SSH 키**를 만들고 공개키만 Termux의 `~/.ssh/authorized_keys`에 넣는다. Termux의 SSH는 이 구성에서 포트 `8022`를 썼다. 실제 사용자명·주소·호스트 키는 자신의 기기에서 읽어야 한다. [1편](docs/blog/mobile-app/01-galaxy-a50-preparation.md)의 화면 꺼짐·재부팅·SSH 순서를 따라간다.
3. PC의 `.deploy/a50/connection.json`에 자신의 `host`, `port`, `user`, `identity_file`, `known_hosts_file`을 기록한다. SSH 호스트 키를 처음 얻을 때는 A50에서 본 지문과 대조한다. 접속 도구 [`scripts/android/a50_ssh.py`](scripts/android/a50_ssh.py)는 호스트 키 검사를 끄지 않는다. 무선 ADB 관리가 필요한 작업에는 `.deploy/a50/adb.json`도 별도로 필요하며, 필드와 첫 페어링 순서는 [A50 관리 앱 안내](android/a50-manager/README.md)를 따른다.

```powershell
.\.venv\Scripts\python.exe scripts/android/a50_ssh.py "whoami"
```

위 접속이 실패하면 서버 배포로 넘어가지 않는다. 잠금화면을 없애거나 무선 디버깅을 자동 복구하는 설정은 **이전 A50 실험의 선택 사항**이다. 보안을 약하게 만드는 설정을 다른 휴대폰에 그대로 복제하지 않는다.

## 3. 중앙 서버와 가족 권한 준비

[중앙 서버 코드와 운영 설명](services/central-server/README.md)을 참고한다. A50 안의 Termux에 Python과 서비스 관리 도구를 준비하고, **PC 로컬 코드 → A50** 순서로만 배포한다. `deploy_a50_central.py`는 인수를 빼면 변경 미리보기이며 `--apply`에서 서버를 잠시 중지·갱신·재시작한다. 기존 DB와 비밀 파일은 소스 배포 대상이 아니다.

```powershell
.\.venv\Scripts\python.exe scripts/android/a50_record.py --label central-runtime-packages --script scripts/android/prepare_a50_runtime.sh --timeout 600
.\.venv\Scripts\python.exe scripts/android/deploy_a50_central.py
# 미리보기의 대상과 기존 사용자 변경을 살핀 뒤에만:
.\.venv\Scripts\python.exe scripts/android/deploy_a50_central.py --apply
.\.venv\Scripts\python.exe scripts/android/verify_a50_central.py
```

Firebase Console에서 본인의 프로젝트를 만들고 Authentication의 Google 로그인 제공자를 켠다. A50 중앙 서버는 Firebase ID 토큰을 검사하고 집별 가족 권한을 별도로 확인한다. 로그인만으로 모든 집을 읽을 수 있게 만들지 않는다. 프로젝트 ID는 자신의 실제 값으로 바꾸고 아래 비공개 설정 도구를 사용한다. [집·가족·초대 설명](docs/blog/mobile-app/03-household-permissions.md)에 역할과 초대 절차가 있다.

```powershell
.\.venv\Scripts\python.exe scripts/android/a50_record.py --label auth-dependencies --script scripts/android/prepare_a50_auth.sh --timeout 300
.\.venv\Scripts\python.exe scripts/android/configure_a50_firebase.py --project-id "<내_Firebase_프로젝트_ID>"
.\.venv\Scripts\python.exe scripts/android/verify_a50_households.py
```

중앙 API는 A50 내부 `127.0.0.1:8001`에만 바인딩한다. 이는 Pi 대시보드의 `8001`과 **서로 다른 기기**다. A50 Termux의 `curl http://127.0.0.1:8001/health/ready`가 성공해야 다음 단계로 간다.

## 4. 다른 휴대폰에서 접속할 HTTPS 주소 만들기

현재 저장소는 [Cloudflare Quick Tunnel](services/central-tunnel/README.md)을 A50에서 시작한다. A50 내부 API를 HTTPS로 이어 주지만, 터널 주소를 아는 것만으로 집 데이터에 접근하게 만들지는 않는다. Google 로그인과 서버의 가족 권한 검사는 그대로 적용한다. 다만 Cloudflare가 HTTPS를 종료하는 외부 중계자이고, 이 임시 주소는 재시작 때 바뀔 수 있다. 운영용 고정 주소가 필요한 사람은 여기서 멈추고 별도 설계를 해야 한다.

```powershell
.\.venv\Scripts\python.exe scripts/android/a50_record.py --label tunnel-package-install --script scripts/android/prepare_a50_tunnel.sh --timeout 300
.\.venv\Scripts\python.exe scripts/android/deploy_a50_tunnel.py
# 미리보기 뒤 테스트용 HTTPS 경로가 필요할 때만:
.\.venv\Scripts\python.exe scripts/android/deploy_a50_tunnel.py --apply
.\.venv\Scripts\python.exe scripts/android/verify_a50_tunnel.py
```

실제 주소는 Git 제외 폴더의 `.deploy/a50/tunnel-endpoint.json`에 둔다. 블로그나 이슈에 복사하지 않는다. 터널이 다시 뜨면 앱의 연결 주소도 새 주소로 바꿔야 한다.

## 5. 가족 앱 빌드·로그인

[가족 앱 README](android/family-app/README.md)에 Android 도구·Firebase 등록·서명 절차가 더 자세히 있다. 먼저 전용 서명 키를 준비한다. Firebase Console에 Android 패키지 `com.aircon.family`와 **자신의 앱 서명 SHA-1·SHA-256**을 등록하고 `google-services.json`을 받는다. Android 앱 설정 JSON에는 서버 전송용 개인 키가 들어 있지 않으며, FCM 서버 키를 APK에 넣어서도 안 된다.

```powershell
.\.venv\Scripts\python.exe scripts/android/prepare_family_tools.py
.\.venv\Scripts\python.exe scripts/android/prepare_family_signing.py
.\.venv\Scripts\python.exe scripts/android/import_family_firebase.py --source "<내_google-services.json_절대경로>" --project-id "<내_Firebase_프로젝트_ID>"
.\.venv\Scripts\python.exe scripts/android/build_family_app.py
.\.venv\Scripts\python.exe scripts/android/verify_family_apk.py
```

서명 키와 Firebase Android 설정은 `.deploy/family-app/`에만 둔다. 빌드 결과의 배포용 파일은 `tmp/family-app-build/family-release.apk`다. `fixture`는 가짜 계정·임시 서버용이니 실사용 휴대폰에는 **release APK**를 설치한다. A50 무선 ADB가 준비됐다면 아래 도구로 대상과 변경을 미리 본 뒤 설치한다. 일반 Android 휴대폰에는 같은 release APK를 직접 설치해 본인이 Google 로그인하면 된다. 기존 설치본을 업데이트할 때는 **같은 서명 키**로 빌드해야 앱 데이터가 유지된다.

```powershell
.\.venv\Scripts\python.exe scripts/android/install_test_family_app.py --production-only --release
# 설치 대상 A50을 확인하고 실제 설치할 때만:
.\.venv\Scripts\python.exe scripts/android/install_test_family_app.py --production-only --release --apply
```

앱에서 `Google로 계속하기`로 본인 계정에 로그인하고, **4단계의 A50 HTTPS 주소**를 연결 설정에 넣는다. 소유자 계정으로 집을 만들고 가족을 초대할 수 있다. 초대받은 사람은 지정된 Google 계정으로 수락한다. 앱의 홈·기록·설정 구조는 [화면 안내](docs/blog/mobile-app/09-ui-redesign-and-scroll.md)를 참고한다.

## 6. 푸시 알림 켜기

FCM은 Google의 알림 전달 서비스다. Firebase 프로젝트에서 **FCM HTTP v1용 전송 전용 서비스 계정**을 만들고, 그 JSON 개인 키를 [FCM 연결 절차](docs/blog/mobile-app/06-family-fcm-notifications.md)에 따라 A50의 비공개 저장소에만 넣는다. 서버 키는 앞 단계의 Android용 `google-services.json`과 다른 파일이다. 여기서 키 내용을 README·캡처·APK에 복사하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/android/configure_a50_fcm.py --source "<내_FCM_서버키_JSON_절대경로>"
# 미리보기에서 기존 키를 덮어쓰지 않는지 살핀 뒤:
.\.venv\Scripts\python.exe scripts/android/configure_a50_fcm.py --source "<내_FCM_서버키_JSON_절대경로>" --apply
```

가족 앱의 `알림 설정 → 이 휴대폰 알림 켜기 → 알림 연결 확인`에서 연결 상태를 본다. 소유자는 자기 집에서 **이 휴대폰에 시험 알림 보내기**를 한 번 눌러 수신 여부를 볼 수 있다. 휴대폰마다 문·경고·온습도 종류와 온습도 **1/5/15/60분 최소 알림 간격**을 고를 수 있다. 이는 Zigbee 센서의 측정 주기나 Pi 화면의 자동 갱신 시간을 바꾸는 설정이 아니다. Android에서 앱 알림 권한을 껐다면 먼저 휴대폰 설정에서 켜야 한다.

## 7. Pi를 내 집에 연결하기

Pi의 기존 센서 DB·제어 서비스는 그대로 두고 [독립 연결 서비스](services/pi-central-agent/README.md)가 **새 기록만 읽어** A50으로 보낸다. 먼저 [Pi 연결 글](docs/blog/mobile-app/07-raspberry-pi-event-relay.md)에 따라 자신의 확인된 SSH 접속 정보를 `.deploy/pi-central-agent/connection.json`에 준비한다. 접속 정보가 없으면 도구가 중단되며 임의의 주소로 연결하지 않는다. A50 SSH, 실제 소유자 로그인, FCM 설치 등록, HTTPS 주소가 준비되지 않았다면 첫 연결을 실행하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/pi/deploy_central_agent.py
.\.venv\Scripts\python.exe scripts/pi/link_central_agent.py --home-name "<내_집_이름>"
# Pi·집·미리보기 내용을 확인하고 첫 연결을 할 때만 한 번:
.\.venv\Scripts\python.exe scripts/pi/link_central_agent.py --home-name "<내_집_이름>" --apply
.\.venv\Scripts\python.exe scripts/pi/verify_central_agent.py
```

첫 연결은 A50의 집에 Pi 전용 키를 만들고 Pi의 비공개 설정에 넣는다. **이미 연결된 Pi에서 `--apply`를 반복하지 않는다.** 중간 실패라면 남은 키·등록·서비스 상태부터 살핀다. 이전 문 기록을 새 알림으로 쏟아내지 않도록 현재 기록 위치를 시작점으로 삼는다. 전송 완료 표시가 실제 휴대폰 수신을 뜻하지는 않으므로 앱의 새 알림과 기록을 함께 본다.

현재 실제 A50에서는 Google 로그인·집 등록·앱의 백그라운드/화면 꺼짐 시험 FCM·Pi 연결 시험 알림이 동작했다. 실제 물리 문 열림·닫힘에서 앱까지의 전체 흐름, 다른 가족 계정의 장시간 수신, 깊은 절전·네트워크 변경은 추가 시험이 필요하다. 날짜별 시행착오와 화면 자료는 [A50·가족 앱 시리즈](docs/blog/mobile-app/README.md)에 있다.
