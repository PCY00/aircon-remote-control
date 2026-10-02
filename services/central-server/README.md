# A50 중앙 서버 실행 기반

버전 0.3.1. 집·가족 권한과 Firebase Google ID 토큰 검증 API, 설치별 FCM 등록·영구 전송 대기열을 포함한다. A50의 실제 Google 계정 설치 등록·전송 키 연결·백그라운드와 화면 꺼짐 조건의 실제 FCM 수신 및 알림 게시를 확인했다. Pi 연결 준비·미리보기와 원래 알림 만료시간 유지도 검증했다. 다른 가족 단말·장시간·실제 Pi 운영 연결은 검증 전이다.
Pi의 기존 app/·MQTT·IR 서비스와 데이터베이스는 사용하지 않는다.

## 구성

- Flask 3.1.3 + Waitress 3.0.2, 고정한 requirements.txt.
- 기본 바인딩: 휴대폰 내부 127.0.0.1:8001, 작업 스레드 2개.
- GET /: 준비 상태 화면. GET /health/live: 프로세스 생존.
- GET /health/ready: 실제 SQLite 메타데이터 읽기 가능 여부, 실패하면 503.
- SQLite WAL + 5초 쓰기 대기, 초기 메타데이터 보존. 스키마 3은 집·가족·초대·허브·이벤트에 설치·알림·전송 작업을 추가한다.
- 중앙 서버만 runit으로 관리하며 기존 공개키 SSH 부팅 스크립트를 유지한다.

## 설치·명시적인 배포

프로젝트 루트에서 기존 A50 SSH 연결 설정과 전용 호스트 키 기록을 사용한다.
설정 파일에는 실제 연결값과 비밀정보가 있어 Git에서 제외한다.

```text
python scripts/android/a50_record.py --label central-runtime-packages --script scripts/android/prepare_a50_runtime.sh --timeout 600
python -m pytest tests/test_central_server_foundation.py -q
python scripts/android/deploy_a50_central.py
python scripts/android/deploy_a50_central.py --apply
```

첫 명령은 python, python-pip, termux-services와 필요한 의존성을 설치한다.
pkg의 Python 패키지가 컴파일 도구도 설치했으며 이번 A50에서는 디스크 추가 사용
예상이 588MB로 출력됐다. 장비의 기본 pip를 별도로 업그레이드하지 않는다.
앱 의존성은 가상환경에 설치하고, 인증용 cryptography는 Termux 패키지를 system-site-packages로 사용한다. Termux의 MarkupSafe는 실제 네이티브 빌드를 했다.

배포 도구 기본 동작은 읽기 전용 미리보기다. 소스 변경은 로컬에서 수행한다.
이전 배포 기록과 실제 파일이 다르거나 추적되지 않은 설치 경로·훅이 있으면
덮어쓰지 않고 중단한다. --apply는 소스 체크섬별 새 릴리스 디렉터리와 원자적
current 링크를 사용한다. DB·로그·비밀정보는 릴리스 전송 목록에서 제외한다.
현재는 단일 가상환경을 공유하므로 이후 의존성 변경은 별도 백업·복구 계획과 함께 한다.

## 장비 경로

| 대상 | 경로 |
| --- | --- |
| 읽기용 배포 기록 | ~/services/aircon-central/deployment.json |
| 릴리스 소스 | ~/services/aircon-central/releases/v0.3.0-소스해시/ |
| 실행 소스 링크 | ~/services/aircon-central/current |
| 가상환경 | ~/services/aircon-central/.venv/ |
| 영구 DB | ~/.local/share/aircon-central/central.sqlite3 |
| 앱·부팅·재시작 기록 | ~/.local/state/aircon-central/ |
| runit 서비스 | $PREFIX/var/service/aircon-central/ |
| 별도 부팅 훅 | ~/.termux/boot/20-start-central |

서버 부팅 훅은 termux-wake-lock 후 서비스 데몬 시작을 요청한다.
sshd·ssh-agent의 기존 down 파일은 그대로 유지하며 관리 SSH는 기존 10-start-ssh가 실행한다.
중앙 서비스가 고장나도 원격 SSH 경로를 서비스 프로세스에 종속시키지 않는다.

## 점검·정상 중지·재시작

아래 명령은 휴대폰 SSH 셸에서 실행한다.

```sh
export SVDIR="$PREFIX/var/service"
sv status "$SVDIR/aircon-central"
curl --fail --silent http://127.0.0.1:8001/health/ready
tail -n 30 ~/.local/state/aircon-central/server.log
tail -n 30 ~/.local/state/aircon-central/service-log/current
sv -w 15 down "$SVDIR/aircon-central"
sv -w 15 up "$SVDIR/aircon-central"
```

재부팅 후에도 중지 상태를 유지하려면 sv-disable aircon-central,
복원하려면 sv-enable aircon-central을 쓴다. 재시작 제한으로 자동 중지됐을 때는
먼저 로그·의존성·데이터베이스·디스크를 확인하고 원인을 수정한다.
5분 실패 기록이 만료된 뒤 sv-enable을 실행한다. 실패 기록을 자동으로 지우지 않는다.

## 제한과 검증

앱 로그와 서비스 stdout/stderr 로그는 각각 1MiB 파일+백업 3개로 제한한다.
부팅 기록은 최근 100줄을 유지한다. 5분 안에 비정상 종료 5회면 down 상태와
오류 기록을 남기고 자동 재시작을 중단한다. SIGTERM/SIGINT 정상 중지는 실패로 세지 않는다.
소유자 SSH로 원인을 확인하고 명시적으로 다시 시작할 수 있다.

```text
python scripts/android/verify_a50_central.py
python scripts/android/verify_a50_central.py --exercise-recovery --reboot
```

첫 명령은 읽기 전용 점검이다. 두 번째는 명시적으로 서버 프로세스 1회 종료·
기기 정상 재부팅·화면 꺼짐 2분 확인을 한다. 저장소 식별값과 SSH 부팅 파일의
비공개 기준값을 장비에서만 비교하며 공개 기록에는 비교 결과만 남긴다.

이 기반의 성공은 실제 가족 인증·가구 격리·알림 발송 성공을 뜻하지 않는다.
다른 집 Pi 연결 경로와 인증을 구성하기 전에는 휴대폰 내부 API로 운영한다.
기반 구축 당시 공유기 포트포워딩·Pi 서비스 변경·Firebase 키 설치는 하지 않았다. 이후 변경은 아래 날짜별 후속 항목과 FCM 운영 절차를 따른다.

## 공식 자료

2026-10-02 후속 작업: [별도 시험용 HTTPS 터널](../central-tunnel/README.md)을 A50에 구성했다.
이 API의 루프백 바인딩·Firebase 검증·가구별 권한은 유지한다.
실제 A50의 배포 APK로 사용자 Google 로그인·API 연결·집 등록·소유자 화면·클라이언트 재실행을 확인했다.
고정 운영 주소·실제 Pi 연결은 후속 항목이다. FCM의 현재 구현·검증 범위는 아래 항목을 따른다.

- [Flask의 Waitress 배포 안내](https://flask.palletsprojects.com/en/stable/deploying/waitress/)
- [Waitress 설정](https://docs.pylonsproject.org/projects/waitress/en/stable/api.html)
- [Termux 서비스 관리](https://github.com/termux/termux-services/blob/master/README.md)


## 집·가족 API 운영 (0.2.0)

Authentication의 Google 제공자를 설정한 실제 Firebase 프로젝트 ID는 장비의
~/.config/aircon-central/config.json에 {"firebase_project_id":"[PROJECT_ID]"}로 기록한다.
이 파일과 서비스 계정 키는 배포 소스에 넣지 않는다. 현재 검증은 공개 인증서만 사용한다.
미설정은 인증된 사용자 API도 503이며 임의 사용자 헤더·query ID로 우회할 수 없다.

프로젝트 루트에서 아래 SSH 기록 도구를 사용한다.

```text
python scripts/android/a50_record.py --label auth-dependencies --script scripts/android/prepare_a50_auth.sh --timeout 300
python scripts/android/configure_a50_firebase.py --project-id [FIREBASE_PROJECT_ID]
python scripts/android/test_a50_households.py
python scripts/android/verify_a50_households.py
```

사용자 API는 Authorization: Bearer [FIREBASE_ID_TOKEN]을 사용한다.
GET /v1/me, GET/POST /v1/homes, GET /v1/homes/{home}, GET /members,
POST /invitations, POST /v1/invitations/accept, PATCH /members/{target},
POST /members/{target}/revoke, GET /hubs, POST /hubs/claim,
POST /hubs/{hub}/revoke, GET /events 및 /events/{id}.
앞에서 별도 절대 경로를 적지 않은 하위 경로는 /v1/homes/{home} 아래다.
요청 스키마·역할·24시간/한 번 초대는 central_server/api.py 및 블로그 3편을 따른다.
공개 소유자 승격·제어 명령 API는 없다. member/viewer는 현재 같은 조회 범위다.

운영자 SSH에서 current 디렉터리로 이동해 서버 가상환경 Python으로 아래를 실행한다.
실제 허브 키 발급은 다음 Pi 연결 작업에서 수행하며 현재 운영 DB에는 허브가 없다.

```sh
cd ~/services/aircon-central/current
$HOME/services/aircon-central/.venv/bin/python -m central_server.admin provision-hub --output /private/new-hub.json
```

출력 부모 폴더는 먼저 비공개 권한으로 준비한다. 기존 출력 파일은 덮어쓰지 않는다.
발급한 hub_token과 claim_code는 비밀이며 stdout·캡처·Git에 넣지 않는다.
등록 코드 10분, 한 번. 일반 HTTP에는 발급 경로가 없다.
POST /v1/hub/events는 기기 토큰과 event_id/kind/payload만 받으며 집은 기기 등록에서 결정한다.

업데이트는 정상 중지 뒤 SQLite backup API로 일관 백업을 만든다.
백업은 ~/.local/share/aircon-central/backups/에 보존하며 자동 복원하거나 지우지 않는다.
스키마 2 뒤 0.1.0로 소스 링크만 돌려서는 호환되지 않는다. 장애 시 SSH를 유지하고 원인을
수정해 앞으로 복구하거나, 새 데이터가 생겼는지 검토한 뒤 명시적으로 백업 복원을 결정한다.

Google 서명 검증은 Firebase 계정의 전역 토큰 폐기 확인을 포함하지 않는다.
집별 가족 제외는 현재 DB 권한으로 즉시 차단한다. 실제 Google 계정 로그인은 APK에서 검증해야 한다.

## 설치별 FCM 운영 (0.3.0)

스키마 3은 설치 등록·알림 메시지·전송 작업 테이블을 추가한다. 기존 집과 계정은 보존한다.
Firebase 인증을 통과한 사용자만 자신의 설치를 등록하며, 이벤트 저장 시 해당 집의 활성 가족과
설치로 전송 대상을 결정한다. 토큰·계정·등록 버전과 가족 권한을 전송 직전에 다시 확인한다.
앱은 알림 설정을 켠 경우만 등록하고 로그아웃·주소 변경 즉시 로컬 수신을 차단한다.

전송은 Google Auth Library와 FCM HTTP v1을 사용한다. 서비스 계정 JSON은 배포 소스 밖
`~/.config/aircon-central/fcm-service-account.json`에 0600 권한으로 보관한다.
같은 폴더의 config.json에 `fcm_service_account_file`을 지정하면 전송 작업자가 시작된다.
설정이 없으면 설치 등록은 가능하지만 소유자의 시험 알림 API는 503으로 응답한다.

```powershell
.venv/Scripts/python.exe scripts/android/configure_a50_fcm.py --source "[서버키_JSON_절대경로]"
.venv/Scripts/python.exe scripts/android/configure_a50_fcm.py --source "[서버키_JSON_절대경로]" --apply
```

첫 명령은 미리보기다. 실제 반영은 프로젝트·전용 계정·RSA 키를 검사하고 비공개 SSH 입력으로
전달한 뒤 중앙 API만 재시작한다. 기존의 다른 키는 덮어쓰지 않는다. 설치 증명·FCM 토큰·키를
로그나 APK에 쓰지 않는다. 상태 `accepted`는 Google의 접수이며 휴대폰 표시 성공을 뜻하지 않는다.

현재 A50의 실제 계정 설치 등록과 전송 전용 키 연결을 완료했고 관련 로컬 검사 76개가 통과했다.
실제 Google FCM 접수·단말 콜백·알림 게시를 백그라운드·화면 꺼짐 즉시 시험에서 확인했다.
관리 SSH·터널 주소·기존 계정과 집은 유지했다. 다른 가족 단말·장시간·실제 Pi는 후속 검증이다.
[블로그 6편](../../docs/blog/mobile-app/06-family-fcm-notifications.md)에 준비부터 다운로드·UI 검사
실패의 해결, 실제 수신 판단 기준과 재현 명령까지 정리했다.

## Pi 원래 알림 만료시간 유지 (0.3.1)

허브 이벤트 payload의 선택 항목 `notification_expires_at`을 검증하고 알림 만료시간으로 사용한다.
이미 만료된 도착 기록은 저장할 수 있지만 새 전송 작업을 만들지 않는다. 재시도·중복 처리에서도
원래 만료시간을 유지한다. 기존 형식은 수신 시점부터 300초 기본값을 유지한다. 스키마는 3이다.
[독립 Pi 연결 서비스](../pi-central-agent/README.md)의 준비는 완료했고 최초 인증키·집 연결은 승인 전이다.
