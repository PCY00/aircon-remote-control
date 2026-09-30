# 에어컨 원격 제어

Raspberry Pi 4B와 적외선 송수신 모듈을 이용해 기존 벽걸이 에어컨 리모컨 신호를 캡처·재생하고, Tailscale을 통해 외부에서 제어하는 프로젝트다.

## 현재 단계

- 리모컨이 단방향 IR 방식임을 PCB 사진으로 확인했다.
- 로컬 작업공간을 기준본으로 사용한다.
- 웹/API 서비스는 포트 `8001`을 사용한다.
- Step 1의 Raspberry Pi 배포, systemd 자동 실행과 Tailscale 접속 구성을 완료했다.
- Step 2의 계층형 IR 수신 코드와 학습 API를 로컬에서 구현·검증했다.
- Carrier CS-A061GS 지원 프로필, 기기 등록 API와 Mock/`ir-ctl` IR 전송 계층을 구현했다.
- Step 3의 Room First 반응형 웹 UI를 루트 화면에 편입하고 실제 기기 API에 연결했다.
- Step 4의 GPIO18 송신 overlay, P2N2222A 구동 회로와 실제 `ir-ctl` 전송 계층을 Pi에
  적용했고, 거리·방향을 조정한 뒤 Carrier 에어컨의 실제 반응을 확인했다.
- 후속 Zigbee Step 3의 센서 대시보드와 Raspberry Pi OS Lite용 Cage/Chromium 키오스크를
  Pi에 적용했다. 센서 표시 이름·공간·아이콘은 서버 SQLite에 영구 저장하며,
  Zigbee2MQTT 가입을 30/60/120초 동안만 여는 센서 추가 화면도 구현했다.
- SSE 실시간 전달과 `문 열림 냉방 경고` 자동화를 2026-09-08 Pi v0.7.0에 배포했다.
  Python 74개·Node 12개 테스트, 배포 파일 체크섬과 운영 API·SSE 연결을 확인했다.
  실제 문 조작에 따른 화면 반영·경고 발생/해제와 MQTT 단절·화면 회전/절전 현장 검증은
  남아 있으므로 후속 Zigbee Step 3 전체 완료는 아직 아니다.
- 도어는 SSE로 즉시 표시하고, 온습도는 한국 시간 `07:00–19:00` 자동 갱신 정지와
  설정 간격을 지킨다. 수동 새로고침과 최초 화면 로드는 최신 저장값을 읽는다.
  [이번 운영 배포 기록](docs/journal/2026-09-08-step3-pi-live-deployment.md)에 검증 범위를 남겼다.

단계별 상세 계획:

- [프로젝트 단계](docs/plans/project-roadmap.md)
- [4편 블로그 구성과 게시용 초안](docs/blog/README.md)
- [후속 PCB 제작 블로그 4편](docs/blog/pcb-ir-node/README.md)
- [Step 2 — IR 수신 구현](docs/plans/step-2-ir-learning-control.md)
- [IR 수신 소프트웨어 구조와 API](docs/architecture/ir-receiver.md)

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\run_local.ps1
```

확인 주소:

- `http://127.0.0.1:8001/`: 반응형 스마트홈 UI
- `http://127.0.0.1:8001/health`
- `http://127.0.0.1:8001/docs`

## IR 수신 API

- `GET /api/v1/ir/receiver`: 수신 장치와 진행 중인 학습 확인
- `GET /api/v1/ir/profiles`: 사용 가능한 리모컨 프로필 확인
- `POST /api/v1/ir/captures`: 비동기 원샷 수신 시작
- `GET /api/v1/ir/captures`: 저장된 학습 목록
- `GET /api/v1/ir/captures/{id}`: 분석·저장 결과 확인
- `POST /api/v1/ir/captures/{id}/cancel`: 진행 중인 수신 취소
- `DELETE /api/v1/ir/captures/{id}`: 학습 결과와 파일 삭제

## 기기·제어 API

- `GET /api/v1/device-profiles`: 지원 기기 모델 목록
- `GET /api/v1/device-profiles/{profile_id}`: 모델 기능과 명령 목록
- `POST /api/v1/device-requests`: 미지원 모델 사진·선택 매뉴얼 접수
- `POST /api/v1/devices`: 지원 모델을 이름과 공간에 등록
- `GET /api/v1/devices`: 등록 기기 목록과 마지막 추정 상태
- `POST /api/v1/devices/{id}/commands`: 의미 기반 상태 또는 즉시 명령 실행
- `GET /api/v1/ir/transmitter`: 현재 송신 전송 계층 상태
- `GET /api/v1/ir/transmissions`: 현재 프로세스의 최근 송신 기록

개발 PC의 기본 송신 계층은 `mock-ir`이다. 검증된 Raspberry Pi에서는
`AIRCON_IR_TRANSPORT=ir-ctl`과 송신 가능한 LIRC 장치를 지정해 같은 API가 실제 IR을
출력한다. `hardware_output: true`는 커널 송신 장치에 명령을 전달했다는 뜻이며 에어컨 상태
변경 확인을 의미하지 않는다.

UI에서 전원·온도·모드·풍량과 빠른 장면의 에어컨 동작은 위 API를 실제로 호출한다.
풍향·경제·쾌속·LED도 즉시 명령 API에 연결되어 있다. `예시`로 표시되는 조명·TV 카드는
로컬 프로토타입이며 실제 제어 API에 등록되지 않는다. 연결된 Zigbee 센서는 아래 센서
API에서 읽어 실제 카드로 표시한다.

## Zigbee 센서 API

- `GET /api/v1/sensors/status`: FastAPI의 MQTT 연결 상태와 저장된 센서 수
- `GET /api/v1/sensors`: 정규화된 모든 센서의 마지막 상태
- `GET /api/v1/sensors/{device_id}`: 센서 하나의 마지막 상태
- `GET /api/v1/sensors/{device_id}/events`: 도어 열림·닫힘 전환 이력
- `PATCH /api/v1/sensors/{device_id}/metadata`: 표시 이름·공간·아이콘 저장
- `GET /api/v1/zigbee/join`: 현재 Zigbee 가입 허용 상태와 남은 시간
- `POST /api/v1/zigbee/join`: 30~120초 동안 새 Zigbee 기기 가입 허용
- `DELETE /api/v1/zigbee/join`: 가입 허용 즉시 종료
- `GET /api/v1/zigbee/devices`: Coordinator를 제외한 Zigbee2MQTT 기기 목록
- `GET /api/v1/events`: 센서·기기·자동화 상태의 SSE 실시간 스트림
- `GET /api/v1/automations`: 서버에서 실행되는 자동화 규칙과 현재 상태
- `PATCH /api/v1/automations/{rule_id}`: 규칙 활성화와 경고 지연 변경
- `GET /api/v1/automations/events`: 자동화 경고 발생·해제 이력

센서 상태는 `runtime/sensors/sensors.sqlite3`에 저장하며 런타임 데이터는 배포 대상과
분리한다. `contact=true`는 `closed`, `false`는 `open`으로 정규화한다. 첫 관측은 기준
상태만 저장하고 이후 실제 상태 전환만 이력에 추가한다.

13인치 직결 화면은 `aircon-kiosk.service`가 Cage와 Chromium을 전체화면으로 실행한다.
디스플레이, Tailscale 주소와 API health가 준비될 때까지 기다리며 자세한 설치·복구 절차는
[키오스크 운영 문서](docs/operations/kiosk-display.md)에 정리했다.

운영 Pi의 MQTT 인증정보는 저장소의 `.env.example`에 넣지 않는다.
`scripts/setup_app_mqtt.sh`가 기존 Zigbee2MQTT 런타임 비밀에서 필요한 두 값만 읽어
권한 `600`의 `runtime/app.env`를 만들고 사용자 systemd 서비스에 연결한다.

지원 모델 기준본:

- [`Carrier CS-A061GS`](device_profiles/air_conditioner/Carrier/CS-A061GS/packet.md)
- [기기 프로필과 런타임 데이터 구조](docs/architecture/device-profiles.md)

## 운영 원칙

최근 점검: [2026-09-12 전체 개선·검증 기록](docs/journal/2026-09-12-project-improvements.md).
ESP32-H2 개발을 다른 PC에서 이어갈 때는
[인수인계 문서](docs/operations/esp32-h2-supermini-ai-handoff-prompt.md)와
[펌웨어 기준본](firmware/esp32-h2-ir-node/README.md)을 사용한다.

- 요청 범위 내 라즈베리파이 변경은 대상과 서비스 영향을 먼저 안내하고 진행한다.
  초기화·삭제·펌웨어 교체 등 별도 확인 대상은 `AGENTS.md`를 따른다.
- 외부 접근은 Tailscale을 사용하며 공용 인터넷 포트포워딩은 하지 않는다.
- 비밀번호와 인증 키는 Git 및 프로젝트 문서에 저장하지 않는다.
- 작업 기록과 문제 해결 과정은 [`docs/`](docs/index.md)에 누적한다.
