# Raspberry Pi → 가족 중앙 서버 연결

0.7.0에서는 기기 목록을 중앙 서버로 보낸다(2026-10-16 설계 결정 0019). `control_origin`을 준비한 Pi만 보낸다. Pi 앱의 `GET /api/v1/devices`와 `GET /api/v1/sensors`를 읽기만 하고, 에어컨·문 열림 센서·온습도 센서를 `PUT /v1/hub/inventory`로 보낸다. 기기마다 ID·이름·공간·종류·기능 블록·현재 상태·마지막 보고 시각·제어 가능 여부가 들어간다. 최대 50개, 본문 32KiB까지다.

- 이 버전부터 기기 이름과 공간 이름이 A50 중앙 서버로 나간다. 2026-10-16에 사용자가 승인했다. Zigbee 주소, MQTT 이름·토픽, 원시 MQTT 내용은 보내지 않는다. 이름이나 공간이 Zigbee 이름·주소와 같으면 기본 이름(`문 열림 센서`, `온·습도 센서`, `에어컨`)이나 빈 공간으로 바꿔 보낸다.
- 에어컨 ID는 Pi 등록 기기 ID 그대로이고 제어 heartbeat와 같다. 상태는 마지막 IR 명령에서 추정한 값이라 `inferred: true`를 붙인다. heartbeat 목록에 있는 에어컨만 `controllable: true`다.
- 센서 ID는 `sha256(에이전트 namespace + ":device:" + Pi 센서 ID)`의 앞 32자다. 문 기록과 온습도 기록 payload에도 같은 값을 `device_id`로 넣는다. 기록에는 여전히 이름·공간·MAC·원시 MQTT를 넣지 않는다.
- 목록이 바뀌면 보내고, 바뀌지 않아도 5분마다 한 번 보낸다. 보내는 간격은 최소 15초다. 중앙 서버가 404를 돌려주면(예전 서버) 1시간 동안 보내지 않고 로그를 한 번 남긴다. 429는 `Retry-After`만큼 기다린다. 다른 오류는 나중에 다시 보내고, heartbeat와 명령 조회는 막지 않는다. 허브 키 거절(401·403)은 다른 요청과 같이 서비스를 멈춘다.
- 모든 중앙 서버 요청은 `FamilySmartHome-Pi/0.7.0` 요청 표시를 쓴다.

0.5.1에서는 기존 알림 연결에 Carrier CS-A061GS·H2의 온도·풍량·운전 모드·풍향·부가 기능과 전원 끄기 요청을 연결했다. 0.5.0의 냉방 24°C 켜기·끄기 요청도 유지한다. `control_origin`을 별도로 준비한 Pi만 제어를 활성화한다. 검토한 명령 목록에서 Pi API 요청을 만들며 임의 URL·임의 요청 본문은 전달하지 않는다. 실행 전에 자기 대기 DB에 명령 ID를 저장해 같은 요청을 자동으로 다시 보내지 않는다. 스윙·표시등처럼 누를 때 상태가 바뀌는 명령도 같다. 프로세스가 중간에 멈췄다면 결과 불명으로 보고한다. 원본 센서 DB는 계속 읽기 전용으로 사용한다. [설정 순서](../../docs/aircon-app-control.md). 아래는 이전 알림 연결 단계의 기록이다.

상태: 2026-10-02, 사용자 승인 후 전용 키·집 연결·실제 Pi발 화면 꺼짐 FCM 수신·서비스 시작 완료.
서비스 active·enabled와 재시작 후 진행 위치 보존을 확인했다. 물리 문 이벤트·장시간 시험은 남아 있다.
중앙 서버 0.4.0과 독립 연결 서비스의 온습도 확장을 반영했다. 기존 Pi 앱과 센서 DB는 그대로 사용한다.

Python 표준 라이브러리만 사용한다. 기존 `runtime/sensors/sensors.sqlite3`의 문 상태 변화와
`runtime/automations/automations.sqlite3`의 경고 발생·해제 기록을 읽기 전용으로 조회한다.
처음 실행할 때 각 테이블의 마지막 번호를 저장해서 이전 기록을 알림으로 다시 보내지 않는다.
온습도는 같은 DB의 sensor_states 최신 보고 시각을 관찰한다. 첫 기준 행은 건너뛰고 새 보고의 유효한 온도·습도만 전달한다. 기록에는 MAC·방 이름·원시 MQTT를 넣지 않는다(0.7.0부터 이름과 공간은 기기 목록으로만 보낸다). 중앙 서버가 휴대폰별 선택과 1·5·15·60분 최소 간격을 적용한다. 보고 자체가 없는 동안 반복 발송하지 않으며 센서의 측정 주기도 변경하지 않는다. 실제 새 온습도 보고의 수신은 아직 확인 전이다.

## 운영 경로

| 항목 | Pi 사용자 홈 아래 경로 |
| --- | --- |
| 코드 | `services/aircon-central-agent/releases/<체크섬>/` |
| 현재 코드 | `services/aircon-central-agent/current` |
| 전용 키·주소 | `.config/aircon-central-agent/config.json` (0600) |
| 전송 대기열·진행 위치 | `.local/state/aircon-central-agent/outbox.sqlite3` |
| 로그 | `.local/state/aircon-central-agent/agent.log` (1MiB × 최대 4개) |
| 사용자 서비스 | `.config/systemd/user/aircon-central-agent.service` |

config.json의 정확한 항목은 `endpoint`, `hub_token`, `source_data_dir`다. 주소는 승인한 HTTPS
origin만 허용한다. 허브 키는 이 Pi의 전용 키이고 source_data_dir은 확인한 기존 runtime 절대경로다.
실제 설정은 저장소에 넣지 않는다. 연결 도구가 비공개 SSH 입력으로 설정을 작성한다.

## 미리보기와 첫 연결

노트북의 프로젝트 폴더에서 실행한다. `pi_session.py`는 기존 배포에서 확인한 SSH 별칭·사용자·키를
사용한다. 다른 사람이 재현할 때는 자신의 Pi 접속 정보를 먼저 확인해서 지정해야 한다. 사용자·호스트는
`-`로 시작할 수 없고(ssh 옵션 주입 방지), `docs/assets/terminal/` 기록에는 Pi 호스트·사용자·키 경로·
`user@host`·`*.ts.net` 이름을 `[REDACTED_...]`로 바꿔 저장한다.
A50 SSH·ADB 관리 준비, 실제 Google 소유자 로그인, FCM 설치 등록, 중앙 서버 0.3.1이 선행 조건이다.

```powershell
.venv/Scripts/python.exe scripts/pi/deploy_central_agent.py
.venv/Scripts/python.exe scripts/pi/link_central_agent.py --home-name "A50 테스트 집"
```

두 명령의 기본 동작은 미리보기다. 기존 원격 파일 변경, 기존 키·등록 정보가 발견되면 보존하고 중단한다.
`deploy_central_agent.py --apply`는 독립 코드·서비스 파일만 설치한다. 첫 설치에서 서비스를 시작하지 않는다.

전용 키 발급·집 연결·자동 전송을 구체적으로 승인한 뒤 실행할 첫 연결 명령:

```powershell
.venv/Scripts/python.exe scripts/pi/link_central_agent.py --home-name "A50 테스트 집" --apply
```

실제 Google SDK의 소유자 권한 확인 → 코드 배포 → 전용 허브 키 발급 → Pi에 비공개 설정 작성 →
10분 유효 일회용 코드를 정상 소유자 API로 사용 → 과거 기록 건너뛰기 → 실제 연결 시험 기록 전송·
A50 FCM 콜백과 알림 게시 확인 → 사용자 서비스 자동 시작 순서다. Google 토큰과 장기 허브 키는
노트북 파일·APK·로그에 저장하지 않는다. 짧은 등록 코드는 무시되는 로컬 임시 파일과 앱의 자체
저장 공간에만 전달하고 사용 후 제거한다. 실제 센서 변화는 새 물리 이벤트로 별도 확인한다.
A50의 `~/.config/aircon-central/pi-central-hub.json`에는 `hub_id`·`created_at`만 남긴다. 허브 키와 등록
코드는 Pi로 넘기는 일회성 전달에만 쓴다. 이 변경 전에 연결한 A50은 그 파일에 허브 키가 남아 있으므로
`verify_central_agent.py`가 `Provisioning record still holds ...`로 실패한다. 서버 DB는 허브 키 해시만 들고
있어 파일은 확인에 필요 없으니, A50에서 `hub_id`·`created_at`만 남긴 0600 파일로 직접 바꾼 뒤 다시 확인한다.

중간 실패 후에는 남은 키·등록·설정부터 조사한다. 전체 연결 명령을 반복해 새 키를 발급하거나
이미 연결된 집을 덮어쓰지 않는다. 연결 완료 전 실패하면 새 서비스는 자동 시작되지 않는다.

## 전송과 복구

- 5초마다 새 기록을 조회한다. 원본 DB를 수정하거나 MQTT·IR 명령을 실행하지 않는다.
- 기록 ID와 본문을 자체 SQLite 대기열에 저장하고 재시도 때 유지한다. 중앙 서버는 허브별 ID로 중복을 차단한다.
- 문·경고 기록의 만료시간은 발생 시점부터 240초다. 만료된 기록은 뒤늦은 알림으로 보내지 않는다.
- 중앙 서버도 원래 만료시간을 유지한다. 전송 도중 만료된 기록은 보관할 수 있지만 새 알림 작업을 만들지 않는다.
- 일시 오류는 최대 8회·만료시간 안에서 재시도한다. 대기열은 미완료 1,000건, 완료 기록은 최근 100건으로 제한한다.
- 중앙 서버가 `429`로 응답하면 대기열 전체를 `Retry-After`(없으면 30초, 1~300초로 제한) 동안 보류한다. 시도 횟수에
  세지 않고 버리지 않으며, 같은 기록 ID로 다시 보내므로 중복 알림도 만들지 않는다. 서비스는 멈추지 않는다.
- 센서 한 개가 5분에 10회를 넘게 바뀌면(접촉 불량·위조 MQTT) 그 이후 변화는 최신 상태 1건으로 합쳐 보낸다.
  보내는 시각은 60초 뒤와 만료 5초 전 중 이른 쪽이고, 재시작 뒤 밀린 기록처럼 남은 시간이 없으면 바로 보낸다.
  중간 상태는 버리고 진행 위치는 그대로 전진하므로 다시 읽지 않는다. 약 5분에 한 번
  `RELAY_COALESCED sensor=<해시 앞 12자리> dropped=<건수>`를 남긴다. 경고 기록은 자동화 원본 전체를 한 묶음으로 센다.
  상수는 `agent.py`의 `RELAY_BUDGET_WINDOW`·`RELAY_BUDGET_TRANSITIONS`·`RELAY_COALESCE_DELAY`·`RELAY_COALESCE_MARGIN`이다.
- 온습도 보고는 센서별로 보고 시각 기준 60초(`CLIMATE_MIN_INTERVAL`)에 한 건만 보낸다. 건너뛴 보고도 진행 위치는
  이동한다. 대기열에서는 문·경고 기록을 온습도보다 먼저 보내며, 429 보류가 끝난 뒤에도 같은 순서다.
- Pi 사용자 계정은 docker 그룹에 속해 있다. 서비스 유닛은 `InaccessiblePaths=-/run/docker.sock`으로 데몬 소켓을 가린다.
  유닛 변경은 `deploy_central_agent.py --apply`로 새 release 체크섬과 함께 배포하고 `verify_central_agent.py`로 확인한다.
- DB 교체·기록 번호 초기화·인증 거절은 조사 대상으로 기록한다. 서비스를 무한 재시작하지 않는다.
  systemd는 300초 동안 시작을 3회로 제한한다.
- 제어를 켜지 않은 Pi는 원본 DB 오류가 5회 연속되면 멈춘다. `control_origin`을 켠 Pi는 원본 DB 교체·초기화·부재·
  예상 밖 오류에도 멈추지 않는다. 알림 진행 위치는 그대로 두고 `SOURCE_INSPECTION_REQUIRED`·`SOURCE_TEMPORARILY_UNAVAILABLE`을
  약 5분마다 기록하며 제어 heartbeat·명령 조회는 매 주기 계속한다. 허브 키 거절(401·403)은 알림과 제어를 함께 멈춘다.
  대기열·제어·결과 재전송의 반복 오류도 약 5분에 한 줄만 기록한다.
- 제어 결과 보고가 400·404·409로 거절되면(중앙 DB 복원·허브 재연결 등) 그 결과는 더 보내지 않는다. 일시 오류는 다음
  주기에 다시 보내며 heartbeat·명령 조회를 막지 않는다. Pi 앱 명령 요청은 H2 결과 대기(18초)보다 긴 20초까지 기다린다.
  Pi 앱의 4xx·503 거절은 실패, 시간 초과·502·500·연결 끊김은 결과 불명으로 보고하고 어느 쪽도 다시 보내지 않는다.
  지원하지 않는 명령, 방금 알리지 않은 기기, 잘못된 남은 시간은 실행하지 않고 실패(또는 만료)로 보고한다.
- 기존 사용자 세션의 linger가 켜진 상태인지 먼저 확인한다. 새 서비스의 읽기·쓰기 경로를 구분하고 로그 크기를 제한한다.

연결 완료한 Pi에서 첫 연결 명령을 재실행하지 않는다. 운영 상태의 읽기 전용 확인은 다음 명령이다.

```powershell
.venv/Scripts/python.exe scripts/pi/verify_central_agent.py
```

현재 시험용 HTTPS 주소는 터널 프로세스가 바뀌면 변경된다. 고정 주소·장시간 운용·다른 가족
휴대폰 수신은 후속 검증이 필요하다. [블로그 7편](../../docs/blog/mobile-app/07-raspberry-pi-event-relay.md)에
실제 증거와 승인 전·후의 구분을 기록한다.
