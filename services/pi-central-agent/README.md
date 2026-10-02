# Raspberry Pi → 가족 중앙 서버 연결

상태: 2026-10-02, 로컬 구현·검사·실제 Pi 미리보기 완료. 키 발급과 집 연결·운영 서비스 시작은 승인 전이다.
중앙 서버 0.3.1은 A50에 반영했다. 기존 Pi 앱과 센서 DB는 그대로 사용한다.

Python 표준 라이브러리만 사용한다. 기존 `runtime/sensors/sensors.sqlite3`의 문 상태 변화와
`runtime/automations/automations.sqlite3`의 경고 발생·해제 기록을 읽기 전용으로 조회한다.
처음 실행할 때 각 테이블의 마지막 번호를 저장해서 이전 기록을 알림으로 다시 보내지 않는다.
온습도 측정값 전체를 주기적으로 전송하는 기능은 포함하지 않는다.

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
사용한다. 다른 사람이 재현할 때는 자신의 Pi 접속 정보를 먼저 확인해서 지정해야 한다.
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

중간 실패 후에는 남은 키·등록·설정부터 조사한다. 전체 연결 명령을 반복해 새 키를 발급하거나
이미 연결된 집을 덮어쓰지 않는다. 연결 완료 전 실패하면 새 서비스는 자동 시작되지 않는다.

## 전송과 복구

- 5초마다 새 기록을 조회한다. 원본 DB를 수정하거나 MQTT·IR 명령을 실행하지 않는다.
- 기록 ID와 본문을 자체 SQLite 대기열에 저장하고 재시도 때 유지한다. 중앙 서버는 허브별 ID로 중복을 차단한다.
- 문·경고 기록의 만료시간은 발생 시점부터 240초다. 만료된 기록은 뒤늦은 알림으로 보내지 않는다.
- 중앙 서버도 원래 만료시간을 유지한다. 전송 도중 만료된 기록은 보관할 수 있지만 새 알림 작업을 만들지 않는다.
- 일시 오류는 최대 8회·만료시간 안에서 재시도한다. 대기열은 미완료 1,000건, 완료 기록은 최근 100건으로 제한한다.
- DB 교체·기록 번호 초기화·인증 거절은 조사 대상으로 기록한다. 서비스를 무한 재시작하지 않는다.
  systemd는 300초 동안 시작을 3회로 제한한다.
- 기존 사용자 세션의 linger가 켜진 상태인지 먼저 확인한다. 새 서비스의 읽기·쓰기 경로를 구분하고 로그 크기를 제한한다.

현재 시험용 HTTPS 주소는 터널 프로세스가 바뀌면 변경된다. 고정 주소·장시간 운용·다른 가족
휴대폰 수신은 후속 검증이 필요하다. [블로그 7편](../../docs/blog/mobile-app/07-raspberry-pi-event-relay.md)에
실제 증거와 승인 전·후의 구분을 기록한다.
