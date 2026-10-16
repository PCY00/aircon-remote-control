# A50 중앙 서버 실행 기반

0.8.0/스키마 8은 iPhone 가족을 위한 홈 화면 웹앱을 추가한다(결정 기록 0020). 7→8 갱신은 기존 데이터를 그대로 두고 빈 표 1개(`quiet_hours`)만 만든다. 2026-10-16에 A50에 배포해 기존 집·허브·가족·설치와 서버 지문이 유지되는 것을 확인했다. 웹 설정을 넣은 뒤 `/app/config.json`과 Google 로그인 페이지 진입까지 확인했다. 실제 iPhone 로그인·홈 화면 추가·푸시 수신은 남아 있다. [설치 순서](../../docs/ios-web-app.md).

## 홈 화면 웹앱 (0.8.0)

- `GET /app`은 `/app/`으로 308 이동한다. `GET /app/`은 `central_server/webapp/index.html`을 준다.
- `GET /app/<파일>`은 `central_server/webapp/` 안의 파일만 준다. 확장자는 `.html` `.js` `.mjs` `.css` `.webmanifest` `.json` `.png` `.svg` `.ico` `.txt`만 받는다. `..`, 절대 경로, 역슬래시, 점으로 시작하는 이름, 폴더, 폴더 밖을 가리키는 링크는 모두 404 `not_found`다.
- 파일은 `Cache-Control: no-cache`로 보내고 내용 해시 ETag와 Last-Modified를 붙인다. 바뀌지 않았으면 304다. `/app/sw.js`에는 `Service-Worker-Allowed: /app/`를 붙인다.
- `/app/` 아래 응답의 콘텐츠 보안 정책은 스크립트를 같은 출처와 Firebase 로그인 로더 `https://apis.google.com`에서만 허용한다. 스타일·작업자는 같은 출처만, 연결은 같은 출처와 Firebase 로그인·FCM 등록 주소만, 그림은 같은 출처·`data:`·Google 프로필 사진 주소만 허용한다. `Referrer-Policy: same-origin`도 붙인다. 다른 경로의 헤더는 바꾸지 않았다.
- `GET /app/config.json`은 비공개 설정의 웹 Firebase 값과 서버 버전을 `no-store`로 돌려준다. 웹 설정이나 프로젝트 ID가 없으면 503 `web_not_configured`다.

### 로그인 도우미 전달

Safari는 사이트마다 저장소를 나누므로 로그인 도메인을 웹앱과 같은 도메인으로 두고 Firebase의 로그인 도우미 화면을 이 서버가 대신 가져온다.

- `GET /__/auth/*`와 `GET /__/firebase/init.json`은 `https://<프로젝트 ID>.firebaseapp.com`의 같은 경로와 쿼리로 전달한다. 대상 호스트는 설정한 프로젝트 ID로만 정하고 요청에서 받지 않는다. 프로젝트 ID가 없거나 형식이 틀리면 503 `auth_helper_not_configured`다.
- 경로는 영문·숫자·`_./-`만 받고 `..`은 거절한다. Firebase로는 Accept, Accept-Language, If-None-Match, If-Modified-Since와 고정 User-Agent만 보낸다. 쿠키와 Authorization은 보내지 않고 Firebase가 준 쿠키도 저장하지 않는다. 프록시 환경 변수는 쓰지 않고 리디렉션은 따라가지 않는다.
- 응답은 상태 코드와 본문, Content-Type, Cache-Control, ETag, Last-Modified, Content-Security-Policy(Firebase가 보낸 경우)만 돌려준다. Firebase 처리 화면은 Google 스크립트를 불러오므로 서버 기본 보안 정책은 붙이지 않고 nosniff만 붙인다.
- 연결 5초, 읽기 10초, 본문 전체 20초 제한이고 본문은 2MiB까지다. 실패하면 502 `auth_helper_unavailable`이다. 서버 기록에는 정해진 결과 이름만 남긴다. 주소와 쿼리(OAuth 코드가 들어 있음)는 남기지 않는다.
- 요청 주소(`CF-Connecting-IP`, 없으면 연결 주소)마다 분당 120회까지다. 넘으면 429 `rate_limited`와 `Retry-After`다.

### 비공개 설정의 `web_app`

`~/.config/aircon-central/config.json`에 선택 항목 `web_app`을 더할 수 있다. Firebase 콘솔에서 웹 앱을 등록하면 받는 값이다. 브라우저에 공개되는 값이지만 저장소에는 넣지 않는다. 프로젝트 ID는 기존 `firebase_project_id`를 쓴다.

```json
{
  "firebase_project_id": "[PROJECT_ID]",
  "fcm_service_account_file": "[서비스_계정_JSON_경로]",
  "web_app": {
    "api_key": "[WEB_API_KEY]",
    "app_id": "[WEB_APP_ID]",
    "messaging_sender_id": "[SENDER_ID]",
    "auth_domain": "[웹앱을_여는_도메인]"
  }
}
```

- 네 값 모두 빈 값이 아닌 문자열이다. `auth_domain`에는 `https://`, 포트, 경로 없이 소문자 호스트 이름만 쓴다.
- 형식이 틀리면 서버가 시작하지 않고 `STARTUP_CONFIGURATION_FAILED`만 기록한다. `web_app`이 없으면 `/app/` 파일은 열리지만 `/app/config.json`은 503이다. 시작할 때 `WEB_APP_CONFIGURED` 또는 `WEB_APP_NOT_CONFIGURED`를 기록한다.
- 환경 변수는 새로 쓰지 않는다.

### 서버가 처리하는 방해 금지 시간

iOS는 받은 웹 푸시를 모두 화면에 보여준다. 그래서 웹앱의 방해 금지 시간은 서버가 처리한다. Android 앱은 이 경로를 쓰지 않고 지금처럼 휴대폰에서 처리한다.

- `PUT /v1/installations/<id>/quiet-hours`. 본문은 `secret`, `enabled`(true/false), `start_minute`, `end_minute`(0~1439), `utc_offset_minutes`(-840~840) 다섯 개다. 키가 빠지거나 더 있으면 400 `invalid_body`, 값의 종류나 범위가 틀리면 400 `invalid_quiet_hours`다. 설치 증명이 맞지 않으면 404다.
- 응답은 `{"status": "saved", "quiet_hours": {...}}`이고 secret은 돌려주지 않는다. 휴대폰마다 한 줄이다. 그 휴대폰이 다른 계정으로 로그인해 저장하면 이전 값을 바꾸고, 저장하기 전에는 이전 계정의 값을 적용하지 않는다.
- 켜져 있고 휴대폰 기준 지금 분((UTC 분 + 차이) mod 1440)이 시작 이상 끝 미만이면 중요도가 `alert`인 알림은 보내지 않는다. 시작이 끝보다 크면 자정을 넘기고, 둘이 같으면 적용하지 않는다. 긴급(`urgent`)과 기타(연결 시험 등)는 항상 보낸다.
- 기록을 받을 때 대기열에 넣지 않고, 이미 대기 중인 알림도 보내기 직전에 다시 확인해 `quiet_hours`로 취소한다. 미뤘다가 나중에 보내지 않는다. 이 시간에 보내지 않은 정기 보고는 최소 간격 계산에 넣지 않는다.
- 설치 등록을 정리할 때 이 값도 함께 지운다.

### 웹 푸시와 배포 도구

- FCM 메시지마다 `webpush` 블록을 더한다. 헤더는 `Urgency`(긴급·알림은 `high`)와 `TTL`(초)뿐이다. 데이터는 Android와 같고 기기 이름·공간·수치는 넣지 않는다.
- `deploy_a50_central.py`는 `central_server/webapp/` 아래 파일을 하위 폴더까지 함께 보낸다. 점으로 시작하는 이름과 `__pycache__`는 뺀다.
- 줄바꿈(CRLF→LF) 정리는 텍스트 파일(`.py` `.js` `.mjs` `.css` `.html` `.json` `.webmanifest` `.svg` `.txt` `.md`, `.env.example`, Termux 훅)에만 한다. PNG·ICO 같은 바이너리는 바이트를 그대로 보낸다. PNG 파일 머리에 CR LF 바이트가 들어 있어 바꾸면 그림이 깨지기 때문이다.
- 장비 설치기는 루트·드라이브·역슬래시·`..`이 들어간 파일 이름을 거절한다.

0.7.0/스키마 7은 Pi가 보내는 기기 목록과 알림 종류별 중요도를 추가한다(결정 기록 0019). 6→7 갱신은 기존 집·가족·허브·설치·기록·명령 데이터를 그대로 두고 표 3개(`hub_inventory`, `hub_devices`, `notification_levels`)를 만든다. 휴대폰마다 저장해 둔 문·온습도·경고 선택은 같은 뜻의 보안·정기 보고·자동화 중요도로 옮긴다. 배포 전 일관 백업은 이전과 같이 만든다.

## 기기 목록과 알림 중요도 (0.7.0)

- `PUT /v1/hub/inventory`: 허브 키로만 받고, 키를 먼저 확인한 뒤 본문을 읽는다. 본문은 `{"devices": [...]}` 하나이고 기기는 50개, 본문은 32KiB까지다. 다른 경로는 계속 16KiB다. 기기마다 `id`, `name`, `room`, `type`, `capabilities`, `state`, `reported_at`, `controllable` 여덟 키가 모두 있어야 한다.
- 이름(80자)과 공간(40자, 빈 값 허용)에서는 제어·서식 문자를 지운다. 그 밖에 형식이 하나라도 틀리면 목록 전체를 400 `invalid_body`로 거절한다. 모르는 종류·블록·상태 키도 형식만 맞으면 저장한다. `reported_at`은 0 이상이고 서버 시각보다 300초 넘게 미래이면 거절한다.
- 받을 때마다 그 허브의 목록을 보낸 순서대로 통째로 바꾸고 `{"status": "stored", "count": N}`을 돌려준다. 허브마다 분당 12회·하루 6000회까지 받는다(Pi의 최소 간격 15초로 계속 보내도 하루 5760회). 넘으면 429 `rate_limited`와 `Retry-After`, 32KiB를 넘으면 413 `body_too_large`다.
- `GET /v1/homes/<home>/devices`: 조회 전용 가족을 포함한 집 구성원이 읽는다. 응답은 `{"devices": [...], "updated_at": ..., "hub_online": ...}`이다. 목록이 없으면 `devices: []`, `updated_at: null`이다. `hub_online`은 제어 화면과 같은 기준(마지막 제어 heartbeat 25초 이내)이다.
- 허브를 해제하거나 집을 지우면 그 허브의 기기 이름·공간·상태 행을 바로 지운다.
- 알림 종류는 안전·보안·기기·환경·정기 보고·자동화·가족·기타다. 중요도는 `urgent`(긴급), `alert`(알림), `quiet`(조용히), `off`(끔)이고 휴대폰으로는 긴급·알림만 보낸다. 기타(연결 시험 등)는 고를 수 없고 항상 보낸다. 정기 보고는 이전처럼 휴대폰별 최소 간격(1·5·15·60분)을 지킨다.
- `PUT /v1/installations/<id>/notification-levels`: `secret`, 일곱 종류의 `levels`, `report_interval_minutes`를 모두 보내야 한다. 안전은 긴급·알림만 고를 수 있다. 틀리면 400 `invalid_notification_preferences`다. 저장하면 예전 표의 문·온습도·경고 칸도 같은 뜻으로 맞춘다.
- 예전 `PUT /v1/installations/<id>/preferences`도 그대로 동작한다. 켠 칸은 보안·정기 보고·자동화를 알림으로, 끈 칸은 끔으로 맞춘다. 다만 이미 같은 뜻의 값(켬이면 긴급, 끔이면 조용히)이면 그 값을 유지한다. 예전 앱은 세 칸을 늘 함께 보내므로 한 칸만 바꿔도 나머지 선택이 지워지지 않게 하기 위해서다.
- FCM 데이터에는 예전 앱을 위한 `category`(`door`, `climate`, `warning`, `other`)를 그대로 두고 `alert_category`와 `level`을 더한다. 정기 보고는 긴급이 아니면 Android 우선순위를 NORMAL로, 나머지는 HIGH로 보낸다. 기기 이름·공간·수치는 넣지 않는다.

0.6.0/스키마 6은 설치마다 하나뿐인 서버 신원 키와 남용 한도를 추가한다. 5→6 갱신은 기존 집·가족·허브·알림 선택·명령 데이터를 그대로 두고 `server_identity` 테이블 1개와 키 1개만 만든다. 배포 전 일관 백업은 이전과 같이 만든다. 아래 0.5.1 내용은 이전 단계의 기록이다.

## 서버 신원과 앱의 주소 고정 (0.6.0)

임시 HTTPS 주소(Cloudflare Quick Tunnel)는 바뀔 때마다 가족 앱에 다시 붙여 넣는다. 누군가 가짜 중계 주소를 건네면 로그인 ID 토큰을 가로챌 수 있다. 그래서 서버는 처음 시작할 때 ECDSA P-256 키를 한 번 만들어 DB에 보관하고(파일 권한 0600, 다시 시작해도 바뀌지 않음), 앱은 그 공개키 지문을 고정한다.

- `GET /v1/server-identity?nonce=<소문자 16진수 32자>`: 인증 없이 응답하며 요청 주소(터널 뒤에서는 `CF-Connecting-IP`, 아니면 연결 주소)마다 분당 60회로 제한하고 전체 상한은 두지 않는다(서명 비용이 작고 Waitress가 동시 처리를 제한하므로, 주소를 아는 제3자가 다른 휴대폰의 확인을 막을 수 없다). `host`는 서버가 받은 `Host` 헤더(소문자, 포트 유지)이고 `signature`는 `aircon-central-identity\n<nonce>\n<host>\n<issued_at>`(UTF-8)의 SHA-256 ES256 서명(DER)이다. `public_key`는 DER SubjectPublicKeyInfo의 표준 base64, `fingerprint`는 그 DER의 SHA-256 소문자 16진수다. 잘못된 nonce는 400 `invalid_body`.
- 앱은 서명이 공개키로 맞는지, 서명된 `host`가 자신이 입력한 주소와 같은지, 지문이 고정한 값과 같은지 확인한다. 중계 서버는 자기 호스트 이름이 들어간 서명을 만들 수 없다.
- 소유자는 SSH에서 지문을 읽어 앱 설정 화면의 지문과 비교한다. 개인키는 출력하지 않는다.

```sh
cd ~/services/aircon-central/current
$HOME/services/aircon-central/.venv/bin/python -m central_server.admin identity
```

- 주소가 바뀌어도 안전한 이유: 키는 주소와 무관하게 설치마다 하나다. 새 주소에서 받은 응답의 지문이 고정한 지문과 같고 서명된 `host`가 새로 입력한 주소와 같으면 같은 서버이므로 앱이 새 주소를 받아들여도 된다.
- 처음 연결(TOFU)이 막지 못하는 것: 맨 처음 지문을 고정하는 순간에 이미 가짜 주소에 연결했다면 가짜 키를 고정한다. 첫 연결과 지문 불일치 경고가 날 때는 반드시 SSH로 읽은 지문과 눈으로 비교한다. 휴대폰 분실·루팅, 서버 DB 유출(키 포함), 다른 서버 결함은 이 키가 막지 않는다. DB를 바꿔 키가 달라지면 모든 앱에서 다시 비교해야 한다.

## 남용 한도 (0.6.0)

- `POST /v1/hub/events`: 허브마다 분당 120회·하루 20000회(온습도 센서 여러 대가 분마다 보고해도 넘지 않는 값). 넘으면 429 `rate_limited`와 `Retry-After`. Pi 연결 서비스는 5초마다 최대 1건을 보내며 429를 일시 오류로 보고 나중에 다시 보낸다.
- 집마다 최신 이벤트 5000개만 보존하고 더 오래된 이벤트와 그 전송 기록은 지운다. 집마다 대기 중 전송 작업은 500개까지이며 넘으면 가장 오래된 미전송 작업부터 버리고 `PUSH_QUEUE_CAPPED`만 기록한다. 전송 작업자는 직전에 보낸 집이 아닌 집을 먼저 처리한다.
- 제어 기기 목록은 마지막 상태 보고에 있는 기기만 남긴다(허브당 최대 20개).
- 계정당 활성 집 20개, 집당 유효한 초대 20개. 넘으면 429 `quota_exceeded`. 계정당 설치 등록 행은 50개까지이며 로그아웃한 등록부터 재사용한다. 로그아웃 뒤 30일 지난 등록과 만료 뒤 30일 지난 초대는 시간별 정리에서 지운다.
- 같은 FCM 토큰을 같은 계정의 다른 설치가 등록하거나, 이전 등록이 로그아웃 상태이거나 30일 넘게 다시 등록하지 않았으면 토큰이 새 등록으로 옮겨가고 이전 등록은 비활성화된다. 다른 계정의 살아 있는 등록이 가진 토큰은 409 `installation_conflict`로 거절해 남이 알림을 끊을 수 없게 한다. 앱은 수신자·바인딩이 다른 알림을 버린다. 설치 증명이 다른 재등록도 409 `installation_conflict`다.
- 허브 경로는 본문을 읽기 전에 허브 키를 먼저 확인하고, 지나치게 중첩된 JSON은 400 `invalid_body`다. 이름 항목은 제어 문자와 서식 문자(양방향 재정의, 폭 없는 문자)를 거절하고, 허브가 보낸 기기 이름에서는 그 문자만 지운다. Google ID 토큰의 `iat`/`auth_time`은 60초 앞선 값까지 허용하며 `exp`는 그대로 엄격하다.

0.6.0은 스키마 6이다. 5→6 갱신은 기존 데이터를 그대로 두고 서버 신원 키 표 하나만 추가한다(2026-10-15 A50 배포에서 집·가족·허브·기록 수 유지 확인). 0.5.1부터 집별 에어컨 명령 대기열로 온도·풍량·운전 모드·풍향·부가 기능과 전원 끄기를 전달한다. 소유자·가족만 요청하고 조회 전용은 거절한다. 해당 집의 전용 허브 키로만 명령을 받아가며, 전달 전에 현재 가족 권한과 기기 연결을 다시 확인한다. 명령은 30초 만료이며 한 번 전달한 명령은 다시 전달하지 않는다. IR 송신 결과를 받지 못하면 결과 불명으로 남긴다. 4→5 갱신은 집·가족·허브·알림 선택을 유지한 채 테이블 3개만 추가하며, 0.5.0→0.5.1은 같은 스키마 5를 사용한다. [제어 연결과 확인 범위](../../docs/aircon-app-control.md). 아래 0.4.0 내용은 이전 단계의 기록이다.

0.4.0/스키마 4 당시 기록: 설치별 알림 종류·온습도 최소 간격, 설치 증명 기반 선택 저장, 전송 직전 선택 재검사, 소유자 이름 확인 후 집·가족 권한·허브·초대·대기 전송 비활성화를 포함한다. 3→4 일관 백업 후 반영, 기존 집 2·설치 2 보존과 실제 A50 0.3.0 수신을 확인했다. 집 삭제의 실사용 데이터 제거는 시험하지 않았다. [상세 재현과 검증](../../docs/blog/mobile-app/08-notification-choices-and-home-management.md). 아래는 기존 구축 단계의 기록이다.

버전 0.3.1. 집·가족 권한과 Firebase Google ID 토큰 검증 API, 설치별 FCM 등록·영구 전송 대기열을 포함한다. A50의 실제 Google 계정 설치 등록·전송 키 연결·백그라운드와 화면 꺼짐 조건의 실제 FCM 수신 및 알림 게시를 확인했다. 전용 키로 Pi를 소유자 집에 연결하고, 실제 Pi발 연결 시험 알림·자동 전송 시작·연결 서비스 재시작 후 진행 위치 보존도 검증했다. 실제 물리 문 변화·다른 가족 단말·장시간 시험은 검증 전이다.
중앙 서버가 Pi의 원본 DB를 직접 수정하거나 Pi의 MQTT에 직접 접속하지 않는다. 0.5.0의 명령은 Pi 연결 서비스가 기존 에어컨 API로 전달한다.

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
| 릴리스 소스 | ~/services/aircon-central/releases/v<버전>-<소스해시>/ |
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
이후 고정 주소와 Pi 연결을 마쳤다. 현재는 중앙 서버 0.8.0이며 실제 iPhone 로그인·푸시 수신은 남아 있다. 아래는 초기 단계의 설명이다.

- [Flask의 Waitress 배포 안내](https://flask.palletsprojects.com/en/stable/deploying/waitress/)
- [Waitress 설정](https://docs.pylonsproject.org/projects/waitress/en/stable/api.html)
- [Termux 서비스 관리](https://github.com/termux/termux-services/blob/master/README.md)


## 집·가족 API 운영 (0.2.0)

Authentication의 Google 제공자를 설정한 실제 Firebase 프로젝트 ID는 장비의
~/.config/aircon-central/config.json에 {"firebase_project_id":"[PROJECT_ID]"}로 기록한다.
이 파일과 서비스 계정 키는 배포 소스에 넣지 않는다. 공개 인증서로 사용자 토큰을 확인하며, 실제 Android Google 로그인도 확인했다. iPhone 계정 로그인은 남아 있다.
미설정은 인증된 사용자 API도 503이며 임의 사용자 헤더·query ID로 우회할 수 없다.

저장소의 `server/` 폴더에서 아래 SSH 기록 도구를 사용한다.

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
공개 소유자 승격 API는 없다. 현재 owner와 member는 에어컨 제어 API를 쓸 수 있고 viewer는 조회만 한다. 제어 경로는 `/v1/homes/{home}/control/commands`다.

운영자 SSH에서 current 디렉터리로 이동해 서버 가상환경 Python으로 아래를 실행한다.
첫 설치에서 허브 키를 한 번 발급해 집에 연결한다. 현재 시험 환경의 Pi는 이미 연결돼 있으므로 아래 발급·첫 연결을 반복하지 않는다.

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
집별 가족 제외는 현재 DB 권한으로 즉시 차단한다. 실제 Android 계정 로그인과 이전 버전의 FCM 수신은 확인했고, 최신 휴대폰·iPhone의 수신은 추가 확인이 필요하다.

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
[독립 Pi 연결 서비스](../pi-central-agent/README.md)는 사용자 승인 뒤 전용 허브 키·집 연결을 완료했다.
실제 Pi 연결 기록과 화면 꺼짐 FCM 수신·서비스 시작·재시작 후 진행 위치 보존을 확인했다.
물리 문 센서 이벤트·다른 가족 단말·장시간 시험은 후속 검증이다.
