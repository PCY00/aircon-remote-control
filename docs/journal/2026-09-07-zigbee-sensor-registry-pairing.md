# 2026-09-07 — Zigbee 센서 레지스트리와 제한 시간 페어링

## 목적

브라우저마다 따로 저장하던 센서 표시 설정을 FastAPI 서버에 영구 보존하고, SSH나
Zigbee2MQTT 관리 화면 없이 스마트홈 UI에서 새 센서를 안전하게 추가한다.

## 구현

- SQLite에 `sensor_metadata` 테이블을 추가했다.
- 표시 이름, 공간, 아이콘과 사용자 수정 여부를 센서 상태와 함께 반환한다.
- `PATCH /api/v1/sensors/{device_id}/metadata`로 설정을 검증하고 저장한다.
- Zigbee2MQTT의 공식 MQTT API를 감싼 가입 상태 조회·시작·종료 API를 추가했다.
- 가입 시간은 UI에서 30/60/120초만 선택할 수 있고 서버 최대값도 120초로 제한했다.
- `bridge/info`의 `permit_join_end`로 남은 시간을 계산한다.
- 센서 관리 창을 닫거나 사용자가 취소하면 0초 요청을 보내 즉시 닫는다.
- `bridge/devices`에서 Coordinator를 제외한 기기의 인터뷰·지원·모델 정보를 표시한다.
- 로컬 Mock/비활성 MQTT 환경에서는 가입 버튼을 비활성화하고 이유를 보여 준다.

## 발견한 문제와 해결

첫 전체 테스트에서 메타데이터를 저장했는데도 응답의 `metadata`가 `null`이었다.
SQLite 쓰기와 조인은 정상이었고 원인은 `sqlite3.Row` 열 존재 확인 방식이었다.
`"display_name" in row`는 키가 아니라 값 포함 여부를 검사하므로 항상 기대와 다르게
동작했다. `row.keys()`를 집합으로 바꾼 뒤 키를 검사하도록 수정했다.

회귀 테스트는 다음을 확인한다.

- 저장 직후 이름·공간·아이콘 반환
- 새 `SensorStore` 인스턴스로 다시 열어도 설정 유지
- 허용하지 않은 아이콘과 없는 센서 거부
- Zigbee 가입 시간이 120초를 넘지 않음
- transaction이 일치하는 Zigbee2MQTT 응답 처리
- 가입 시작과 즉시 종료
- Coordinator를 제외한 장치 목록

![센서 레지스트리와 페어링 로컬 테스트](../assets/terminal/52-step3-sensor-registry-pairing-local-tests.png)

## 공개 기록 주의

장치 목록 API와 캡처에는 IEEE 주소를 노출하지 않는다. MQTT 비밀번호, 사설 IP와 실제
장치 고유 식별자도 문서에 저장하지 않는다. 런타임 센서 DB는 코드 배포 대상이 아니다.

## 검증 상태

- JavaScript 문법 검사 통과
- Ruff 통과
- 전체 회귀 테스트 70개 통과
- 로컬 시각 검증에서 MQTT 비활성 안내와 가입 버튼 비활성화 확인

## Raspberry Pi 배포와 실제 MQTT 왕복

사용자가 승인한 1회 배포에서 앱 코드와 정적 자산 7개, `pyproject.toml` 1개만
전송했다. SQLite DB, MQTT 인증정보와 Zigbee2MQTT 설정은 동기화하지 않았다. 원격
SHA-256이 로컬 기준본과 모두 일치한 뒤 editable 패키지를 `0.6.0`으로 갱신하고 사용자
`aircon-controller` 서비스와 시스템 `aircon-kiosk` 서비스만 재시작했다.

첫 점검 스크립트는 센서 API 응답을 배열로 잘못 가정해 센서 수를 1개로 출력하고
메타데이터 검사에서 예외가 났다. 실제 앱 장애가 아님을 응답 최상위 키만 읽어 확인했고,
`items` 봉투를 명시적으로 해석하도록 점검식을 고쳤다. PowerShell이 원격 Bash의 명령
치환을 먼저 해석하지 않도록 원격 명령 전체도 단일 인용했다.

수정한 점검 결과는 다음과 같다.

- health 정상, 패키지 `0.6.0`
- MQTT 연결됨
- 저장 센서 2개와 각 센서의 서버 메타데이터 확인
- Zigbee 가입 기본 차단
- Coordinator를 제외한 Zigbee2MQTT 기기 2개
- 가입을 30초로 열면 남은 시간 30초
- 즉시 종료 뒤 가입 차단·남은 시간 0초
- 시험 전후 기기 수 2개로 동일
- 앱과 키오스크 서비스 active, 재시작 횟수 0, 최근 경고 없음
- 운영 UI에서 최신 자산, 차단 상태와 기존 기기 2개 표시 확인
- 키오스크용 마우스 커서 숨김 유지

마지막 커서 점검은 처음에 존재하지 않는 CSS 클래스 이름과 공백까지 고정한 문자열을
찾아 실패했다. 실행 중 Chromium의 `?kiosk=1`과 실제
`html[data-kiosk="true"] * { cursor: none !important; }` 규칙을 따로 검사해 둘 다
존재함을 재확인했다. 이는 운영 UI 실패가 아니라 점검식의 거짓 음성이었다.

![센서 레지스트리와 페어링 Pi 배포](../assets/terminal/53-step3-sensor-registry-pairing-pi-deployment.png)
