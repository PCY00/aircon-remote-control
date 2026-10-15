# 기능 블록 기기 목록과 종류별 알림 중요도

2026-10-16. 사용자 선택: 가족 앱 첫 화면은 공간 중심(안 1)에 "지금 확인할 것" 영역을 더한다. 공간 이름은 Pi에서 중앙 서버로 보낸다.

## 배경

- 지금 중앙 서버는 제어 가능한 에어컨의 ID와 이름만 안다(`control_devices`). 문·온습도 센서는 기록으로만 들어오고 이름·공간·현재 상태가 없다.
- 알림 선택은 문·온습도·경고 세 칸으로 고정돼 있다. 전등·움직임·누수 센서가 생기면 표와 앱 화면을 함께 고쳐야 한다.
- Pi에는 이미 기기별 이름·공간(`sensor_metadata`, 등록 기기 JSON)과 모델 프로필의 기능 목록이 있다.

## 결정

### 1. Pi가 기기 목록을 보낸다

`PUT /v1/hub/inventory` (허브 인증). 본문은 `{"devices": [...]}` 하나이고 기기는 최대 50개, 본문 32KiB 이하다. 서버는 받을 때마다 그 허브의 목록을 통째로 바꾼다.

```json
{
  "id": "0123456789abcdef0123456789abcdef",
  "name": "현관문",
  "room": "현관",
  "type": "door_sensor",
  "capabilities": ["contact", "battery"],
  "state": {"contact": "closed", "battery_percent": 87},
  "reported_at": 1792130000.0,
  "controllable": false
}
```

- 키는 위 여덟 개가 모두 있어야 한다.
- `id`: 32자리 소문자 16진수.
  - 에어컨은 Pi 등록 기기 ID를 그대로 쓴다. 제어 heartbeat와 같은 ID다.
  - 센서는 `sha256(에이전트 namespace + ":device:" + Pi 센서 ID)`의 앞 32자다. Zigbee 주소나 MQTT 이름은 보내지 않는다.
- `name` 80자, `room` 40자 이하다. 제어·서식 문자(Cc, Cf)는 지운다. `room`은 빈 문자열을 허용한다.
- `type`, `capabilities` 항목과 `state` 키는 `[a-z][a-z0-9_]{0,31}` 형식이다.
  - 서버는 모르는 종류·블록도 형식만 맞으면 저장한다. 새 기기를 붙일 때 서버를 고치지 않기 위해서다.
  - `capabilities`는 중복 없이 최대 16개다.
- `state`: 최대 16개 키다. 값은 `null`, bool, 절댓값 1e9 이하의 유한한 수, 또는 Cc/Cf가 없는 40자 이하 문자열만 허용한다.
- `reported_at`: 기기가 마지막으로 보고한 시각(epoch 초) 또는 `null`이다. 서버 시각보다 300초 이상 미래이면 거절한다.
- `controllable`: 중앙 제어 명령을 받을 수 있는 기기인지 나타낸다. 실제 명령 허용은 지금처럼 제어 heartbeat 목록으로 판단한다.

Pi 연결 서비스는 목록이 바뀌었을 때만 보낸다. 바뀌지 않아도 5분마다 한 번 보내고, 보내는 간격은 최소 15초다. 서버가 404를 돌려주는 예전 버전이면 1시간 동안 보내지 않는다.

### 2. 블록 이름(1차)

| 종류 `type` | 블록 `capabilities` | 상태 키 `state` |
|---|---|---|
| `air_conditioner` | `power`, `setpoint`, `mode`, `fan`, `actions` | `power`, `mode`, `setpoint_c`, `fan`, `inferred` |
| `door_sensor` | `contact`, `battery` | `contact`(`open`/`closed`), `battery_percent`, `battery_low` |
| `climate_sensor` | `temperature`, `humidity`, `battery` | `temperature_c`, `humidity_percent`, `battery_percent`, `battery_low` |
| 나중: `light` | `power`, `brightness`, `color_temp` | `power`, `brightness_percent`, `color_temp_k` |
| 나중: `plug` | `power`, `power_meter` | `power`, `power_w` |
| 나중: `motion_sensor`, `leak_sensor` | `motion`, `leak`, `battery` | `motion`, `leak`, `battery_percent` |

- 에어컨 상태는 IR 명령에서 추정한 값이라 `inferred: true`를 붙인다.
- 앱은 아는 블록만 전용 모양으로 그리고, 모르는 블록과 상태 키는 이름·값 줄로 보여준다.

### 3. 가족이 읽는 목록

`GET /v1/homes/<home>/devices`. 조회 전용 가족을 포함해 집 구성원이면 읽을 수 있다.

```json
{"devices": [...], "updated_at": 1792130000.0, "hub_online": true}
```

`updated_at`은 Pi가 마지막으로 목록을 보낸 시각이다. 목록이 없으면 `devices: []`, `updated_at: null`이다.

### 4. 기록에 기기 참조를 붙인다

Pi 연결 서비스는 문 기록과 온습도 기록 payload에 `device_id`(위 목록 ID)를 넣는다. 앱은 이 값으로 기록에 기기 이름과 공간을 보여준다. 예전 기록에는 없으므로 앱은 종류 이름으로 대신 보여준다.

### 5. 알림은 종류 × 중요도

| 알림 종류 | 해당 기록 | 기본 중요도 | 고를 수 있는 값 |
|---|---|---|---|
| `safety` 안전 | `safety.*`, `sensor.leak_detected`, `sensor.smoke_detected` | 긴급 | 긴급, 알림 |
| `security` 보안 | `sensor.door_changed`, `sensor.open`, `sensor.closed`, `sensor.motion_detected` | 알림 | 넷 다 |
| `device` 기기 | `device.*` | 알림 | 넷 다 |
| `environment` 환경 | `environment.*`, `sensor.climate_threshold` | 조용히 | 넷 다 |
| `report` 정기 보고 | `sensor.climate_report` | 끔 | 넷 다 |
| `automation` 자동화 | `automation.*` | 알림 | 넷 다 |
| `family` 가족 | `family.*` | 조용히 | 넷 다 |
| `other` 기타 | 그 밖의 것(연결 시험 등) | 항상 보냄 | 고르지 않음 |

중요도 값은 `urgent`(긴급), `alert`(알림), `quiet`(조용히), `off`(끔)다.

- 서버는 긴급·알림만 휴대폰으로 보낸다. 조용히와 끔은 기록에만 남는다. 앱의 알림 탭은 끔인 종류를 "전체" 목록에서 빼고, 해당 종류 칩을 고르면 보여준다.
- 정기 보고는 지금처럼 휴대폰별 최소 간격(1·5·15·60분)을 지킨다.
- FCM 데이터에는 예전 앱을 위해 기존 `category`(`door`, `climate`, `warning`, `other`)를 그대로 두고 `alert_category`, `level`을 더한다. 예전 앱은 모르는 종류를 버리므로 안전·기기 같은 새 종류는 받지 않는다.
- FCM에는 지금처럼 기기 이름·수치를 넣지 않는다. 앱은 종류별 문구를 보여주고, 자세한 내용은 앱을 열어 인증된 API로 읽는다.
- 방해 금지 시간은 휴대폰 시계 기준으로 앱이 처리한다. 긴급은 항상 소리를 내고, 알림은 방해 금지 시간이면 조용한 채널로 보여준다.

새 API는 `PUT /v1/installations/<id>/notification-levels`다.

```json
{"secret": "...", "levels": {"safety": "urgent", "security": "alert", "device": "alert",
  "environment": "quiet", "report": "off", "automation": "alert", "family": "quiet"},
 "report_interval_minutes": 5}
```

- 일곱 종류를 모두 보내야 한다.
- 예전 API(`/preferences`)도 그대로 둔다. 예전 앱이 문·온습도·경고를 바꾸면 보안·정기 보고·자동화 중요도를 알림 또는 끔으로 맞춘다.
- 새 API로 저장하면 예전 표의 세 칸도 같은 뜻으로 맞춘다.
- 스키마 7로 올릴 때 기존 휴대폰별 선택을 새 표로 옮긴다.

## 결과와 남은 일

- 중앙 서버 0.7.0, DB 스키마 7. 기존 집·가족·설치·기록은 보존한다.
- Pi 연결 서비스 0.7.0. 이 버전부터 기기 이름과 공간 이름이 A50 중앙 서버로 나간다. 2026-10-16에 사용자가 승인했다. Zigbee 주소와 원시 MQTT 내용은 계속 보내지 않는다.
- 가족 앱 0.6.1은 새 목록 API를 쓴다. 예전 서버(404)이면 제어 목록과 기록으로 기기를 만들어 보여준다.
- 아직 없는 것: 자동화 탭과 빠른 실행, 전등 실제 제어(전등 기기가 아직 없음), 서버가 직접 만드는 배터리·응답 없음 알림. 배터리와 응답 없음은 앱이 목록에서 계산해 "지금 확인할 것"에만 보여준다.
