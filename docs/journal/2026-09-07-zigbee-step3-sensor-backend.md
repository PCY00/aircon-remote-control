# Zigbee/MQTT Step 3 — 센서 백엔드 첫 구현

## 이번 작업 범위

Step 2에서 확정한 실제 MQTT 필드를 FastAPI 내부의 의미 기반 센서 상태로 변환하고,
재부팅 뒤에도 마지막 상태와 도어 전환 시각이 남도록 SQLite 저장 계층을 구현했다. 이번
먼저 로컬 기준본과 Mock 데이터로 검증한 뒤 승인받은 11개 파일만 Raspberry Pi에
배포했다.

```text
Zigbee2MQTT MQTT message
        ↓ PahoSensorBridge
SensorService normalization
        ↓
SensorStore (SQLite)
        ↓
FastAPI REST API
```

## 데이터 정규화 규칙

| Zigbee2MQTT 원문 | 내부 상태 | 의미 |
|---|---|---|
| `contact=true` | `door_state=closed` | 자석이 붙은 닫힘 |
| `contact=false` | `door_state=open` | 자석이 떨어진 열림 |
| `temperature` | `temperature_c` | 섭씨 온도 |
| `humidity` | `humidity_percent` | 상대습도 % |
| `battery` | `battery_percent` | 배터리 % |
| `voltage` | `voltage_mv` | 배터리 전압 mV |
| `linkquality` | `linkquality` | Zigbee2MQTT 링크 품질 |

부분 보고도 이전 상태와 병합한다. 예를 들어 도어센서가 배터리만 보고해도 기존
`door_state`와 센서 종류는 유지된다. 숫자는 허용 범위를 벗어나거나 NaN/무한대이면
상태에 반영하지 않는다.

## 도어 이벤트 중복 방지

앱이 처음 보는 `closed` 또는 `open`은 기준 상태로 저장하되 이벤트는 만들지 않는다.
이후 이전 상태와 새 상태가 실제로 다를 때만 `door_events`에 한 행을 추가한다.

```text
첫 closed 보고       → 현재 상태만 저장
closed 반복 보고     → 이력 추가 없음
open 보고            → closed → open 이벤트 저장
open 반복 보고       → 이력 추가 없음
closed 보고          → open → closed 이벤트 저장
```

이 규칙은 같은 payload의 반복 보고나 재연결 시 상태 재전달이 문을 실제보다 여러 번
열고 닫은 것처럼 보이게 하는 문제를 막는다. `last_seen`이 시간대가 포함된 ISO 시각이면
센서 보고 시각으로 UTC 변환해 저장하고, 별도로 Raspberry Pi가 받은 시각도 유지한다.

## MQTT 연결 방식

- Paho MQTT 2.x Callback API VERSION2를 명시했다.
- FastAPI 시작 때 백그라운드 네트워크 루프를 시작하고 종료 때 정리한다.
- 연결 성공 콜백에서 `zigbee2mqtt/+`를 다시 구독해 재연결 뒤 구독이 복원되게 했다.
- MQTT를 사용하지 않는 로컬 개발에서는 no-op 어댑터를 사용한다.
- 호스트, 포트, 인증정보, base topic과 keepalive는 환경 변수로만 받는다.
- MQTT 비밀번호의 실제 값은 저장소에 넣지 않았다.

## 추가한 API

| 메서드와 경로 | 용도 |
|---|---|
| `GET /api/v1/sensors/status` | MQTT 연결과 저장 센서 수 |
| `GET /api/v1/sensors` | 모든 센서의 마지막 상태 |
| `GET /api/v1/sensors/{device_id}` | 센서 하나의 마지막 상태 |
| `GET /api/v1/sensors/{device_id}/events` | 최근 도어 상태 전환 이력 |

## 검증 결과

프로젝트 가상환경에 `paho-mqtt 2.1.0`을 설치했다. 새 테스트는 첫 관측, 반복 보고,
열림·닫힘 전환, 부분 payload 병합, 온습도 정규화, 시간대 변환, 잘못된 메시지 거부,
SQLite 재생성 뒤 복원, FastAPI API와 MQTT 생명주기를 포함한다.

```text
Ruff:   All checks passed!
Pytest: 51 passed in 1.95s
```

관련 캡처는 `docs/assets/terminal/38-step3-sensor-backend-local-tests.txt/.png`에 있다.

전체 저장소를 대상으로 한 추가 Ruff 검사에서는 기존
`scripts/convert_ir_compact.py`의 import 블록 뒤 빈 줄 하나를 자동 정렬하라는 경고가
남아 있었다. 이번 센서 코드와 `app`, `tests` 범위는 모두 통과했고 해당 IR 변환기는
이번 변경 범위가 아니므로 함께 고치지 않았다. 기능 테스트 실패는 아니다.

## 남은 작업

1. 배포 전 Raspberry Pi의 실제 MQTT 접속 경계와 런타임 비밀 파일을 확인한다.
2. 승인 후 코드와 의존성을 한 번 배포하고 실제 센서 payload로 상태·이력을 검증한다.
3. 온습도 수동 조회와 `07:00–19:00` 자동 조회 금지, 설정 가능한 시간·간격을 구현한다.
4. REST 위에 SSE 실시간 이벤트를 추가하고 모바일·PC·13인치 센서 카드를 만든다.
5. SSH 없이 가입 가능한 Zigbee 센서 추가 마법사와 첫 자동화를 구현한다.

배터리식 Sleepy End Device는 `/get` 요청에 즉시 답하지 않을 수 있다. 따라서 이후 UI는
`요청 접수`, `새 보고 수신`, `마지막 저장값 표시`를 서로 다른 상태로 보여줘야 한다.

실제 `Zbeacon TH01`의 현재 Zigbee2MQTT 지원 정의를 확인한 결과 temperature, humidity,
battery와 voltage 모두 `/get` 읽기를 지원하지 않는다. 이 모델에는 능동 측정 요청이나
예약 `/get`을 보내지 않는다. 사용자가 정한 자동 갱신 시간·간격은 센서 송신 주기가 아니라
서버에 이미 들어온 최신값을 화면에 반영하는 주기로 적용하고, 수동 갱신도 서버 저장값을
즉시 다시 읽는 기능임을 UI에서 분명히 표시한다. 센서는 자체 보고 규칙에 따라 계속 MQTT
메시지를 보내며 FastAPI는 화면 갱신 시간과 무관하게 이를 저장한다.

## Raspberry Pi 배포와 운영 검증

배포 전 읽기 전용 확인에서 기존 8001 사용자 서비스는 active였고 Mosquitto 컨테이너도
실행 중이었다. 애플리케이션용 `AIRCON_MQTT_*` 환경 변수는 아직 없었다. 사용자의 승인을
받아 다음 11개 파일만 삭제 없이 전송했다.

- `app/integrations/` 2개
- `app/sensors/` 4개
- `app/main.py`, `app/settings.py`
- `pyproject.toml`
- systemd 템플릿과 MQTT 설정 스크립트

전송량은 46,397바이트였으며 로컬·원격 SHA-256이 모두 일치했다. Pi 가상환경에
`paho-mqtt 2.1.0`을 설치하고 기존 Zigbee2MQTT 런타임 비밀에서 MQTT 사용자명과
비밀번호만 읽어 `runtime/app.env`를 생성했다. 값 자체는 출력하지 않았고 파일은
`600`, 소유자는 `air:air`로 확인했다.

이때 Pi의 기존 editable 패키지 메타데이터는 `0.3.0`이었다. 이전 코드 반영 때
`pip install -e .`를 다시 실행하지 않아 코드와 패키지 메타데이터 버전이 달랐던 것으로
판단한다. 이번 설치에서 프로젝트 버전을 `0.5.0`으로 갱신했고 오류 없이 완료됐다.

사용자 systemd 단위에 선택적 `EnvironmentFile`을 연결하고 8001 서비스를 한 번
재시작했다. 검증 결과는 다음과 같다.

```text
aircon-controller     active / enabled
paho-mqtt             2.1.0
runtime/app.env       mode 600, air:air
sensor SQLite         present
/health               ok
MQTT                   enabled=true, running=true, connected=true
stored_sensor_count   0
```

`stored_sensor_count=0`은 MQTT 연결 실패가 아니다. 앱이 구독한 뒤 배터리식 센서가 아직
새 보고를 보내지 않았고, 장치 상태 토픽은 앱 구독 시점에 retained 상태가 재생된다고
가정할 수 없기 때문이다. 가짜 payload를 발행해 성공 화면을 만들지 않았다. 실제 두
센서의 다음 자율 보고 또는 사용자의 현장 버튼·도어 조작 후 상태와 이벤트 저장을 Step 3
통합 검증으로 이어간다.

배포와 검증 자료는
`docs/assets/terminal/39-step3-sensor-backend-pi-deployment.txt/.png`에 저장했다.

## 센서 대시보드 첫 UI 구현

기존의 `장면 먼저 → 공간 → 기기` 흐름은 유지하고 빠른 장면 바로 아래에 `집 상태`
영역을 추가했다. UI는 새로 만든 센서 전용 CSS와 JavaScript로 분리해 기존 에어컨 제어
코드와 결합도를 낮췄다.

- 도어센서: 현재 열림·닫힘, 마지막 상태 변경 시각, 최근 20개 전환 이력
- 온습도 센서: 온도, 습도, 배터리, 링크 품질과 마지막 보고 시각
- 공통: MQTT 연결 상태, 저장 센서 수, 수동 새로고침, 오류·빈 상태
- 상세 화면: 센서 식별자와 수신 시각 등 진단 정보
- 센서 관리: API에서 발견된 센서의 표시 이름·공간·아이콘 지정
- 반응형: 휴대폰 1~2열, PC와 13인치 화면 2열 및 기존 좌측 내비게이션

자동 화면 갱신은 기본적으로 `07:00~19:00` 동안 멈추고 그 밖의 시간에 5분 간격으로
동작한다. 시작·종료 시각, 간격과 사용 여부를 설정할 수 있고 수동 새로고침은 언제든
가능하다. 이 설정은 현재 브라우저의 `localStorage`에 저장되므로 13인치 대시보드와
휴대폰은 각자 화면 갱신 정책을 가질 수 있다. 센서를 강제로 깨우는 기능은 아니다.

센서 이름·공간·아이콘도 이번 첫 UI에서는 브라우저별 설정이다. 여러 화면에서 동일한
구성을 공유하는 서버측 센서 레지스트리는 후속 작업으로 남긴다. Zigbee 네트워크 가입
허용도 아직 UI에서 직접 켜지 않으며, 이미 Zigbee2MQTT에 보고된 센서를 발견하고 화면에
등록하는 범위까지만 구현했다.

로컬 미리보기는 실제 API 형식의 임시 SQLite 데이터로 문 열림·닫힘 두 전환과 온습도
값을 넣어 구성했다. 이 데이터는 `runtime_preview/`에만 있으며 운영 데이터나 배포
대상에는 포함하지 않는다. JavaScript 문법 검사와 55개 Python 테스트는 통과했다.

## 센서 UI Raspberry Pi 배포

사용자의 승인을 받아 다음 정적 파일 3개만 삭제 없이 전송했다.

- `app/static/index.html`
- `app/static/sensors.css`
- `app/static/sensors.js`

`aircon-controller` 사용자 서비스를 한 번 재시작한 뒤 세 파일의 원격 SHA-256이 로컬과
모두 일치함을 확인했다. 서비스는 active/enabled였고 MQTT도 connected 상태였다. 실제
SQLite에는 `door_contact`, `temperature_humidity` 두 센서가 저장되어 새 UI가 읽을
데이터도 확인됐다.

첫 HTTP 검증은 `127.0.0.1:8001`로 요청해 모두 연결 실패했다. 처음에는 서비스 기동
실패를 의심했지만 `systemctl status`, 프로세스와 리스닝 소켓을 함께 확인한 결과 Uvicorn은
정상 실행 중이었고 보안 설정에 따라 Raspberry Pi의 Tailscale 주소에만 바인딩되어 있었다.
현재 열린 8001 리스닝 주소를 사용해 다시 검사하자 `/health`, `/`, 센서 CSS와 JavaScript가
모두 HTTP 200을 반환했다. 즉 배포 장애가 아니라 검증 대상 주소를 잘못 선택한 것이
원인이었다.

이 차이는 이후 13인치 로컬 키오스크를 구성할 때도 중요하다. 현재 설정에서 Chromium은
`127.0.0.1:8001`이 아니라 Pi 자신의 Tailscale 주소 또는 그 주소로 해석되는 이름을 열어야
한다. Lite 이미지는 그래픽 환경과 브라우저가 없으므로 디스플레이만 연결하면 콘솔이
나오는 것이 정상이다. 키오스크용 최소 X 환경과 Chromium 설치는 별도 승인 작업으로
진행한다.

실패와 해결 검증 자료는
`docs/assets/terminal/41-step3-sensor-ui-pi-deployment.txt/.png`에 저장했다.
