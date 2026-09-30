# 프로젝트 기록

이 디렉터리는 구현 결과뿐 아니라 프로젝트가 진행된 과정과 실패·복구 경험을 블로그 자료로 보존한다.

## 기록 위치

- `journal/`: 날짜별 진행 과정과 실험 결과
- `decisions/`: 중요한 설계 결정과 선택 이유
- `hardware/`: 장비 식별, 배선, 측정 결과
- `operations/`: 배포 후 서비스 상태 확인과 운영 절차
- `plans/`: 단계별 구현 범위, 순서와 완료 조건
- `references/`: 제조사 설명서와 외부 자료에서 확인한 사실
- `blog/`: 에어컨 IR·Zigbee/MQTT·PCB 제작을 구분한 시리즈별 게시용 원고와 목차
- `troubleshooting.md`: 재현 가능한 증상과 해결 방법
- `issues.md`: 해결 전후를 포함한 이슈 목록

## 기록 규칙

- 관찰 사실과 추정을 분리한다.
- 명령은 비밀 값을 제거한 형태로 기록한다.
- 실패한 시도도 삭제하지 않고 왜 실패했는지 남긴다.
- 해결 여부와 검증 방법을 함께 기록한다.

현재 환경 문서:

- [PCB 제작 블로그 4편 — 부품·회로도·배선·JLCPCB 주문 준비](blog/pcb-ir-node/README.md)
- [사용자 PCB 검토용 릴리스 메모](hardware/user-pcb-release-notes.md)
- [KiCad 10.0.1 — H2 노드 회로도 단계별 작성·심볼·풋프린트](hardware/esp32-h2-kicad10-schematic-guide.md)
- [AA 2개·USB-C ESP32-H2 IR 노드 BOM — PCB 설계 초안](hardware/esp32-h2-aa-usb-ir-bom.md)
- [전체 코드 개선과 검증 — 2026-09-12](journal/2026-09-12-project-improvements.md)
- [ESP32-H2 새 PC 개발 인수인계](operations/esp32-h2-supermini-ai-handoff-prompt.md)
- [4편 블로그 구성과 게시용 초안](blog/README.md)
- [기존 에어컨 리모컨](hardware/remote-control.md)
- [보유 IR 송수신 모듈](hardware/ir-modules.md)
- [Raspberry Pi 실행 환경](hardware/raspberry-pi.md)
- [웹 서비스 운영](operations/web-service.md)
- [Step 2 — IR 수신·패킷 복제 구현](plans/step-2-ir-learning-control.md)
- [정정된 프로젝트 단계](plans/project-roadmap.md)
- [IR 수신 소프트웨어 구조와 API](architecture/ir-receiver.md)
- [향후 ESP32-H2 Zigbee IR 노드와 로컬 MQTT 구조](architecture/zigbee-ir-node-future.md)
- [ESP32-H2 배터리 Zigbee IR 노드 부품표와 배선](hardware/esp32-h2-zigbee-ir-node.md)
- [현재 USB 전원 ESP32-H2 Zigbee IR 시제품](hardware/esp32-h2-usb-ir-prototype.md)
- [상용 Zigbee 도어·온습도 센서 식별 기록](hardware/zigbee-commercial-sensors.md)
- [기기 프로필·등록·전송 계층](architecture/device-profiles.md)
- [IR 수신 소프트웨어 구현 기록](journal/2026-08-29-ir-receiver-software.md)
- [Carrier 프로필과 Mock 제어 API 구현 기록](journal/2026-08-30-device-profile-api.md)
- [Room First UI와 실제 API 연결 기록](journal/2026-08-30-ui-api-connection.md)
- [로컬 아이콘 시스템과 사용자 선택기](journal/2026-08-30-local-icon-system.md)
- [Room First UI Raspberry Pi 배포](journal/2026-08-30-pi-ui-deployment.md)
- [Step 4 IR 송신 소프트웨어 구현](journal/2026-08-30-ir-transmitter-software.md)
- [IR 신호 전체 수집 매트릭스](plans/ir-signal-capture-matrix.md)
- [Carrier CS-A Series 설명서 확인 기록](references/carrier-cs-a-series-manual.md)
- [예약 실행은 Raspberry Pi가 담당](decisions/0004-server-side-scheduling.md)
- [Room First 스마트홈 UI](decisions/0005-room-first-smart-home-ui.md)
- [지원 프로필과 런타임 업로드 분리](decisions/0006-device-profile-runtime-separation.md)
- [ESP32-H2 배터리 Zigbee IR 노드를 먼저 검증](decisions/0007-esp32-h2-battery-zigbee-ir-prototype.md)
- [첫 ESP32-H2 Zigbee IR 노드는 USB 전원으로 검증](decisions/0008-usb-powered-esp32-h2-ir-first.md)
- [Zigbee 장치는 제한 시간 동안 한 대씩 페어링](decisions/0010-time-limited-zigbee-pairing.md)
- [13인치 로컬 터치 대시보드와 Tailscale 원격 접근](decisions/0011-local-touch-dashboard-and-tailscale.md)
- [Zigbee 센서 모니터링과 갱신 정책](architecture/zigbee-sensor-monitoring.md)
- [Zigbee/MQTT Step 2 센서 페어링 기록](journal/2026-09-06-zigbee-step2-sensors.md)
- [Zigbee/MQTT Step 2 UZ-8D 도어센서 페어링](journal/2026-09-07-zigbee-step2-door-sensor.md)
- [블로그 Step 2 — 상용 Zigbee 온습도·도어 센서 연동](blog/zigbee-mqtt/02-commercial-zigbee-sensors.md)
- [블로그 Step 3 — FastAPI 센서 대시보드](blog/zigbee-mqtt/03-fastapi-sensor-dashboard.md)
- [Raspberry Pi OS Lite 키오스크 운영](operations/kiosk-display.md)
- [13인치 터치 키오스크 설치·디버깅 기록](journal/2026-09-07-touch-kiosk-setup.md)
- [Zigbee 센서 레지스트리와 제한 시간 페어링](journal/2026-09-07-zigbee-sensor-registry-pairing.md)
- [Zigbee SSE 실시간 갱신과 첫 안전 자동화](journal/2026-09-07-zigbee-step3-live-automation.md)
- [Step 3 실시간 대시보드 Pi 0.7.0 배포·설치 복구](journal/2026-09-08-step3-pi-live-deployment.md)
