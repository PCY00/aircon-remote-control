# 스마트홈 소프트웨어 아키텍처

2026-10-05 로컬 코드 기준으로 그렸다. Pi 앱은 0.7.0, 중앙 서버와 가족 앱은 0.4.0, 중앙 DB는 스키마 4다. 앞으로 만들고 싶은 구조와 현재 돌아가는 코드를 섞지 않았다. 코드 위치는 아래와 `component-model.json`에 함께 남겼다.

[![전체 연결](smart-home-overview.svg)](smart-home-overview.svg)

## A0 컴포넌트 그림

[A0 SVG](smart-home-components-a0.svg) · [A0 PDF](smart-home-components-a0.pdf) · [컴포넌트·연결 모델 JSON](component-model.json)

[![A0 컴포넌트 그림](smart-home-components-a0.svg)](smart-home-components-a0.svg)

SVG는 가로 1189mm, 세로 841mm의 A0다. `viewBox="0 0 1682 1189"`, 본문 `font-size:12px`를 사용했다. 여기서 px는 SVG 안의 좌표 단위라 확대하면 글자도 함께 커진다. 제목은 더 크게 썼다. README 요약 그림은 화면에서 바로 읽도록 본문 16px를 사용한다. PDF는 같은 좌표와 내용을 벡터로 그렸고 한글 글꼴을 포함했다. 인쇄할 때 A0 가로 방향과 실제 크기를 선택한다.

상자는 책임을 나눈 컴포넌트다. 모든 상자가 별도 서버라는 뜻은 아니다. Pi의 FastAPI와 A50의 Flask 프로세스 안에서 동작하는 클래스도 역할별로 나눴다. Google 로그인처럼 해당 영역에서 사용하는 외부 의존성은 점선 상자로 표시했다. 화살표는 데이터가 전달되거나 호출되는 방향이고, 양쪽 화살표는 조회·등록의 왕복을 뜻한다. 내부 호출은 중요한 경로만 그렸다.

## 먼저 나누어 읽을 두 경로

**에어컨 제어:** 휴대폰·PC·터치 화면 → Tailscale → Pi 웹/API → DeviceService → MQTT → Zigbee2MQTT 외부 변환기 → Zigbee → ESP32-H2 → IR → 에어컨. MQTT의 센서 보고와 H2 명령은 같은 브로커를 쓰지만 서로 다른 메시지다. H2는 Wi-Fi·FCM에 연결하는 기기가 아니다. Pi GPIO IR은 선택할 수 있는 별도 송신 경로다. 기기에 H2 연결이 있으면 그 경로를 사용한다.

**가족 알림:** Zigbee 센서 → Pi SensorService·센서 DB·자동화 기록 → Pi 연결 서비스 → HTTPS 통로 → A50 허브 인증·이벤트 저장 → 현재 가족과 휴대폰별 알림 선택 → 영구 전송 대기열 → FCM → 가족 APK → Android 알림. 알림을 눌러 자세한 기록을 보는 과정은 Google 로그인 토큰을 사용하는 중앙 API 조회다. 가족 APK에 에어컨 제어 명령을 보내는 기능은 현재 없다.

## 컴포넌트와 실제 코드

| 실행 위치 | 컴포넌트 | 하는 일 | 코드 |
| --- | --- | --- | --- |
| 각 집 Pi | FastAPI + 웹 화면 | 기기·센서·자동화 API, SSE와 화면 제공 | [`app/main.py`](../../app/main.py), [`app/static/`](../../app/static/) |
| 각 집 Pi | PahoSensorBridge | MQTT 보고 수신, Zigbee 가입 관리, H2 요청·결과 연결 | [`app/integrations/mqtt.py`](../../app/integrations/mqtt.py) |
| 각 집 Pi | SensorService + SensorStore | 값 확인, 최신 상태와 문 변화 기록 | [`app/sensors/`](../../app/sensors/) |
| 각 집 Pi | DeviceService + 명령 해석·송신 | 기기 JSON, 명령 프로필, H2 또는 Pi IR 선택 | [`app/devices/`](../../app/devices/), [`device_profiles/`](../../device_profiles/) |
| 각 집 Pi | AutomationService + EventHub | 문이 열린 채 에어컨이 켜진 조건의 경고, 화면 갱신 | [`app/automations/`](../../app/automations/), [`app/events.py`](../../app/events.py) |
| 각 집 Pi | Mosquitto + Zigbee2MQTT | MQTT와 Zigbee 장치 연결, H2 외부 변환기 | [`deploy/zigbee/`](../../deploy/zigbee/) |
| 에어컨 앞 H2 | Zigbee IR 펌웨어 | 요청 확인·중복 처리·작업 큐, IR 송신과 송신 결과 응답 | [`firmware/esp32-h2-zigbee-ir-node/`](../../firmware/esp32-h2-zigbee-ir-node/) |
| 각 집 Pi | 독립 연결 서비스 | 기존 DB를 읽어 새 기록 수집, 자체 진행 위치·전송 대기 저장 | [`services/pi-central-agent/agent.py`](../../server/services/pi-central-agent/agent.py) |
| A50 + Cloudflare | HTTPS 터널 | A50에서 시작한 통로로 외부 HTTPS 요청 전달 | [`services/central-tunnel/`](../../server/services/central-tunnel) |
| A50 | Flask API + FirebaseIdentity | 사용자/허브 인증 경로 구분, Google 공개 키로 ID 토큰 확인 | [`api.py`](../../server/services/central-server/central_server/api.py), [`auth.py`](../../server/services/central-server/central_server/auth.py) |
| A50 | Households | 집 소속·역할, 지정 계정 초대, 허브 연결, 기록 격리 | [`households.py`](../../server/services/central-server/central_server/households.py) |
| A50 | PushStore + Preferences | 설치 토큰·증명·binding, 종류별 수신 선택, 온습도 간격, 전송 작업 | [`push.py`](../../server/services/central-server/central_server/push.py), [`preferences.py`](../../server/services/central-server/central_server/preferences.py) |
| A50 | PushWorker + FCMSender | 전송 직전 권한·설정 확인, 만료·재시도, FCM HTTP v1 요청 | [`push.py`](../../server/services/central-server/central_server/push.py), [`fcm.py`](../../server/services/central-server/central_server/fcm.py) |
| 가족 휴대폰 | FirebaseSession + ApiClient | Google 로그인·Firebase 세션, HTTPS 사용자 API | [`FirebaseSession.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/FirebaseSession.java), [`ApiClient.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/ApiClient.java) |
| 가족 휴대폰 | FamilyActivity | 홈·기록·설정, 가족 관리와 알림 선택, 오류 안내·스크롤 유지 | [`FamilyActivity.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/FamilyActivity.java) |
| 가족 휴대폰 | PushManager + PushSyncWorker | WorkManager로 FCM 토큰·설치 증명·알림 선택을 중앙에 등록 | [`PushManager.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/PushManager.java), [`PushSyncWorker.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/PushSyncWorker.java) |
| 가족 휴대폰 | FamilyMessagingService + PushPolicy | 현재 계정·binding·중복·수신 선택 확인 후 Android 알림 표시 | [`FamilyMessagingService.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/FamilyMessagingService.java), [`PushPolicy.java`](../../server/android/family-app/app/src/main/java/com/aircon/family/PushPolicy.java) |

## 집과 가족이 섞이지 않게 하는 연결

한 사용자에게 여러 집의 가족 등록이 있을 수 있고, 한 집에는 여러 가족과 여러 휴대폰이 붙는다. **현재 DB는 집마다 활성 허브 한 대만 허용한다.** Pi를 더 붙이는 기능을 이미 지원하는 것처럼 그리지 않았다.

사용자 요청은 Firebase ID 토큰으로 계정을 확인한 뒤 현재 `memberships`를 읽는다. 다른 집의 ID를 넣어도 소속이 없으면 조회할 수 없다. `owner`만 초대·가족 역할 변경·참여 해제·허브 연결·집 삭제·시험 알림을 요청한다. 현재 `member`와 `viewer`는 일반 집·기록 조회 범위가 같으며, 두 역할에 별도의 에어컨 제어 권한은 구현되어 있지 않다.

Pi 요청은 사용자 토큰 대신 전용 허브 키를 사용한다. A50은 키의 해시로 활성 허브를 찾고 **서버에 저장된 허브의 집**을 선택한다. Pi가 요청 본문에 임의의 집을 지정하는 구조가 아니다. 허브 키 발급은 관리 도구가 맡고, 소유자 API에서 10분 유효 연결 코드를 한 번 사용해 집에 붙인다. 가족 초대는 지정 Google 계정만 수락하며, 24시간 유효하고 한 번 사용한다.

FCM 토큰이나 주제를 알고 있다는 이유로 가족 권한을 주지 않는다. 전송 대상을 고를 때와 실제 전송 직전에 현재 집·사용자·가족·설치 상태와 `binding`을 다시 읽는다. 알림 선택도 다시 확인한다. 앱에서 로그아웃하거나 토큰이 바뀌는 동안 이전 응답이 새 등록을 되살리지 않도록 설치 세대를 구분한다. 이미 FCM에 전달한 알림을 회수하는 구조는 아니다.

## 기록 저장과 알림 전송은 구분했다

| 저장/전달 | 담는 것 | 의미 |
| --- | --- | --- |
| Pi 센서 SQLite | 최신 센서 상태, 문 변화 | 원본 측정·변화 기록 |
| Pi 자동화 SQLite | 경고 발생·해제, 규칙 상태 | 원본 자동화 기록 |
| Pi 기기 JSON·프로필 | 등록 기기, H2 연결, 명령 데이터, 마지막 원하는 상태 | 에어컨 실제 상태 측정값은 아님 |
| Pi 연결 서비스 SQLite | 수집한 위치와 전송 대기 | 기존 DB를 수정하지 않고 이어서 전송 |
| A50 중앙 SQLite | 집·가족·허브·이벤트·설치·알림 선택·전송 작업·감사 기록 | 가족 권한과 기록·전송의 기준 |
| Pi EventHub / SSE | 실행 중 화면 갱신 메시지 | 메모리 스트림, 가족 알림 전송 대기열과 별개 |
| FCM data 메시지 | 메시지 ID, 설치 binding, 수신 계정, 종류·분류 | 문 상태·온습도 수치·집 이름 같은 상세 기록은 보내지 않음 |
| APK SharedPreferences | 설치 증명, binding, 선택, 중복 수신 기억, 마지막 수신 시각 | 서버 수신 확인 ACK는 아님 |

Pi 연결 서비스는 처음 실행할 때 마지막 기록 위치를 시작점으로 삼는다. 오래된 기록을 새 알림으로 다시 쏟아내지 않는다. 5초마다 문·경고의 새 행과 온습도 최신 보고 시각을 읽는다. 온습도는 센서가 새로 보고한 값만 전달하고 측정 주기를 바꾸지 않는다.

문·경고·온습도 선택과 온습도 1·5·15·60분 간격은 **휴대폰 설치 단위**다. 현재 온습도 간격은 해당 설치의 온습도 알림 전체에 적용되며, 집이나 센서별로 각각 다른 타이머가 있는 것은 아니다. 기본값은 문·경고 켜짐, 온습도 꺼짐, 간격 5분이다. 보고가 없으면 주기적으로 같은 값을 보내지 않는다.

이벤트 수집은 `(hub_id, sender_event_id)`로 중복을 확인한다. 같은 ID·같은 내용은 기존 결과를 돌려주고, 같은 ID·다른 내용은 충돌로 처리한다. 중앙 이벤트 저장과 전송 대기 생성은 같은 DB 트랜잭션에서 한다. 이 방식은 수집 단계의 중복을 줄이지만, 외부 FCM 전달 전체를 정확히 한 번으로 보장하지는 않는다. APK도 최근 메시지 ID로 중복을 거른다.

## 실행과 오류 복구

Pi의 FastAPI와 연결 서비스는 별도 사용자 systemd 서비스다. A50은 Termux:Boot가 wake-lock과 runit을 시작하고, 중앙 API·HTTPS 터널·관리 SSH를 분리했다. 중앙 서버가 실패해도 관리 SSH가 같은 프로세스 때문에 함께 중단되는 구조는 아니다. 노트북은 개발·명시적 배포·SSH/ADB 관리에 쓰며 운영 알림을 중계하지 않는다.

Pi 대기열은 미완료 1,000건과 완료 최근 100건으로 제한한다. 센서 알림은 발생 시점부터 240초 만료를 유지하고, 일시 오류는 최대 8회 시도 범위에서 재전송한다. 허브 인증 거절은 서비스를 멈추고 원인을 확인하게 한다. 원본 DB 교체나 기록 번호 초기화도 조용히 초기화하지 않는다.

중앙 전송 작업은 최대 300초 또는 Pi가 보낸 원래 만료시각 중 빠른 쪽을 사용한다. 일시 전송 오류는 최대 6회 시도하며, 무효 FCM 토큰은 해당 등록 세대만 비활성화한다. 기간이 지난 알림의 전송 접수와 실제 Android 표시를 같은 결과로 취급하지 않는다. 로그는 크기를 제한하고, 반복 시작 실패도 무한히 재시작하지 않는다.

## 경계와 남아 있는 확인

Pi 웹/API의 8001, MQTT 1883, Zigbee2MQTT 관리 화면 8080은 일반 인터넷에 직접 열지 않는다. Pi 제어는 Tailscale 사설망을 사용한다. A50은 자기 기기 내부 `127.0.0.1:8001`로 받고 Cloudflare가 외부 HTTPS를 종료해 전달한다. 두 기기의 8001은 서로 다른 서비스다. FCM 전송용 개인 키는 A50의 비공개 설정에만 있으며, APK·이 그림·GitHub에는 넣지 않는다.

Quick Tunnel은 재시작하면 주소가 바뀔 수 있다. 고정 도메인, 운영 가동 시간, 여러 집의 실제 부하 시험이 끝난 구조는 아니다. 실제 로그인·집 등록·화면 꺼짐 시험 알림·Pi 연결 시험은 기존 기록에 있다. 물리 센서부터 가족 앱까지 이어지는 전체 시험, 다른 가족 계정 수신과 장시간 운영은 남아 있다. 이 문서를 만들면서 기기 재부팅·새 센서 시험·서비스 배포를 실행하지 않았다.

## 그림을 다시 만드는 방법

생성 소스는 [`scripts/render_software_architecture.py`](../../scripts/render_software_architecture.py)다. 이 파일의 좌표·컴포넌트·설명을 바꾸고 다시 실행하면 SVG 두 개, A0 PDF와 JSON 모델이 함께 나온다. `component-model.json`은 생성된 색인이다. SVG는 글자를 편집할 수 있는 텍스트로 보존하고, 스크립트·외부 이미지·외부 글꼴 다운로드를 넣지 않는다.

Python 환경에 `reportlab`을 설치하고 저장소 루트에서 실행한다.

```powershell
python -m pip install reportlab
python scripts/render_software_architecture.py
```

기본 글꼴은 Windows의 맑은 고딕이다. 다른 OS에서는 한글이 있는 TrueType 글꼴을 직접 지정한다. 글꼴 파일을 저장소에 복사할 필요는 없다.

```bash
python scripts/render_software_architecture.py --font /path/to/Korean-Regular.ttf --bold-font /path/to/Korean-Bold.ttf
```

그림을 만든 뒤에는 PDF 페이지 크기, 한글 표시, 화살표 방향과 README 그림을 실제로 열어 확인한다. 생성 도구는 글자가 상자 밖으로 나가거나 코드 근거 파일이 없으면 중단한다. 오늘은 PDF가 A0 한 페이지인지와 래스터 그림 없이 글자·선·상자로 그려졌는지도 확인했다.
