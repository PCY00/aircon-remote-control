# iPhone 가족을 위한 홈 화면 웹앱

2026-10-16. 사용자 요청: 초대한 가족이 iPhone을 쓰면 웹으로 홈 화면에 추가해 쓰게 한다. 비용이 들지 않는 방식으로 한다.

## 결정

- 중앙 서버(A50)가 `https://roomrelay.top/app/`에서 웹앱(PWA)을 직접 제공한다. 별도 호스팅, Apple 개발자 등록, Mac은 쓰지 않는다.
- 웹앱은 Android 앱과 같은 API와 같은 화면 규칙을 쓴다. 공간별 홈, 지금 확인할 것, 기능 블록 기기 화면, 알림 종류 × 중요도는 [결정 0019](0019-capability-inventory-and-alert-levels.md)를 따른다.
- 웹앱 1차 범위: 로그인, 초대 수락, 새 집 만들기, 집 바꾸기, 홈·종류별·기기 화면, 에어컨 조작, 알림 탭, 알림 설정(받기, 종류별 중요도, 정기 보고 간격, 방해 금지 시간), 로그아웃이다.
- 집 소유자 관리(가족 초대·역할·허브 연결·집 삭제)는 Android 앱에서 한다. 웹앱은 그 자리에 Android 앱에서 관리한다는 안내만 둔다.

## 경로와 서버 동작 (중앙 서버 0.8.0, DB 스키마 8)

| 경로 | 동작 |
|---|---|
| `GET /app/` | `central_server/webapp/index.html` |
| `GET /app/<파일>` | `central_server/webapp/` 안의 정해진 확장자 파일만 제공한다. 폴더 밖 경로는 404다. |
| `GET /app/sw.js` | 서비스 워커. 범위는 `/app/` |
| `GET /app/config.json` | 비공개 설정의 웹 Firebase 값을 돌려준다. 설정이 없으면 503 `web_not_configured`다. |
| `GET /__/auth/*`, `GET /__/firebase/init.json` | `https://<프로젝트>.firebaseapp.com`의 같은 경로로 전달한다. 가져오는 대상 호스트는 프로젝트 ID로만 정하고 요청에서 받지 않는다. |

- `/app/` 응답의 콘텐츠 보안 정책은 스크립트를 같은 출처에서만 허용한다. 예외는 Firebase 리디렉션 로그인이 불러오는 Google 로그인 로더(`https://apis.google.com`) 하나다. Firebase 웹 SDK 12.19.0 파일은 웹앱 폴더에 넣어 함께 제공하고 실행 중에 외부 CDN을 쓰지 않는다. 받은 원본의 해시는 `webapp/vendor/README.md`에 적는다.
- Safari의 저장소 분리 때문에 로그인 도메인(authDomain)을 `roomrelay.top`으로 두고 `/__/auth/` 요청을 Firebase로 전달한다. Firebase가 권하는 방식이다.
- 비공개 설정 `~/.config/aircon-central/config.json`에 `web_app`을 더한다. `{"api_key", "app_id", "messaging_sender_id", "auth_domain"}` 네 값이고, 프로젝트 ID는 기존 값을 쓴다. 이 값들은 Firebase 웹 설정이라 브라우저에 공개되는 값이지만 저장소에는 넣지 않는다.

## 알림

- 웹 푸시는 iOS 16.4 이상에서 홈 화면에 추가한 웹앱만 받는다. 권한 요청은 홈 화면 앱 안에서 사용자가 버튼을 눌렀을 때만 한다.
- 등록은 Android와 같은 `PUT /v1/installations/<id>`(FCM 웹 토큰), `PUT /v1/installations/<id>/notification-levels`를 쓴다.
- FCM 메시지에 `webpush` 블록(Urgency, TTL)을 더한다. 데이터 내용은 Android와 같고 기기 이름과 값은 넣지 않는다.
- 웹 푸시는 받은 알림을 숨길 수 없다(iOS는 모든 푸시를 표시해야 한다). 그래서 방해 금지 시간을 서버에서 처리한다.
  - 경로는 `PUT /v1/installations/<id>/quiet-hours`다. 본문은 `{"secret", "enabled", "start_minute", "end_minute", "utc_offset_minutes"}`다.
  - 시작·끝은 0~1439분이고, 시작이 끝보다 크면 자정을 넘긴다. 둘이 같으면 적용하지 않는다.
  - 켜져 있고 휴대폰 기준 현재 시각이 그 범위 안이면, 중요도가 `alert`인 알림은 보내지 않는다. `urgent`와 `other`는 보낸다.
  - Android 앱은 이 경로를 쓰지 않고 지금처럼 휴대폰에서 처리한다.

## 확인 방법과 남은 일

- 로컬: 서버 테스트, 웹앱 계산 규칙의 Node 테스트, 가상 데이터 서버와 개발용 토큰으로 만든 휴대폰 크기 화면 캡처. 개발용 토큰 입력은 `127.0.0.1`·`localhost`에서만 동작한다.
- 사용자가 할 Firebase·Google Cloud 콘솔 작업이 세 가지 있다.
  - 웹 앱 등록
  - `roomrelay.top`을 로그인 허용 도메인에 추가
  - OAuth 웹 클라이언트에 `https://roomrelay.top/__/auth/handler` 리디렉션 URI 추가
- 실제 로그인과 웹 푸시는 초대받은 가족의 iPhone으로 확인한다.
