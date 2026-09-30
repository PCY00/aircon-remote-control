# Zigbee/MQTT 스마트홈 확장 블로그 구성

기존 에어컨 원격 제어 4편 이후 이어지는 두 번째 4편 시리즈다. 실제 명령·출력·사진을
확보한 단계부터 본문을 작성하고, 남은 단계는 계획과 캡처 목록을 함께 관리한다.

1. **[Step 1 — Raspberry Pi를 Zigbee/MQTT 게이트웨이로 만들기](01-raspberry-pi-zigbee-mqtt-gateway.md)** — 완료 (2026-09-06)
   - ZBDongle-P 인식, Mosquitto, Zigbee2MQTT, 보안, 자동 시작과 복구
2. **[Step 2 — 알리 Zigbee 온습도·도어 센서를 제조사 클라우드 없이 연결하기](02-commercial-zigbee-sensors.md)** — 개발 완료 (2026-09-07)
   - 호환성 확인, 페어링, MQTT payload 분석, 이름·백업·재부팅 복구
   - 실제 설치 위치와 장시간 보고 주기는 Step 3 최종 통합시험으로 이관
3. **[Step 3 — FastAPI 스마트홈 UI에 Zigbee 센서와 자동화 연결하기](03-fastapi-sensor-dashboard.md)** — 게시 원고·구현·Pi 배포 완료, 후속 현장시험 분리 (2026-09-08)
   - 상태 정규화, 실시간 카드, 오프라인 처리, 13인치 터치 대시보드, 첫 자동화
   - SQLite 상태·도어 이력·센서 설정, REST API와 반응형 센서 UI 구현 완료
   - 30/60/120초 Zigbee 가입 마법사와 Zigbee2MQTT 장치 목록 구현 완료
   - Cage/Chromium 키오스크의 실제 13인치 화면·터치·재부팅 검증 완료
   - v0.7.0 SSE·문 열림 냉방 경고 배포, Python 74개·Node 12개 테스트 통과
   - 온습도 KST 자동 갱신 정지·간격·수동 정책 유지, 도어는 SSE 실시간 표시
   - 재부팅 후 TH01 새 MQTT 보고와 API 수신까지 실제 검증
   - USB/xHCI 장애·복구와 13인치 화면 전원 분리 판단을 실패 기록으로 포함
   - 실제 문 전환·경고 발생/해제와 화면 전원 분리 장기 관찰은 후속 검증으로 구분
4. **Step 4 — ESP32-H2 Zigbee IR 노드로 에어컨 제어하기**
   - 브레드보드 회로, RMT, Zigbee custom cluster, external converter, 실기 제어

세부 작업, 완료 기준과 단계별 캡처 체크리스트는
[`../../plans/zigbee-mqtt-iot-roadmap.md`](../../plans/zigbee-mqtt-iot-roadmap.md)를 기준으로 한다.

Step 1의 실제 명령, 실패 원인, 해결과 검증 기록은
[`../../journal/2026-09-05-zigbee-step1-gateway.md`](../../journal/2026-09-05-zigbee-step1-gateway.md)에
정리되어 있다. 블로그용 터미널 자료는 `../../assets/terminal/23-*.txt/.png`부터
`31-*.txt/.png`까지 이어진다.

Step 2의 센서 라벨·설명서 판독, 페어링 절차와 진행 기록은
[`../../hardware/zigbee-commercial-sensors.md`](../../hardware/zigbee-commercial-sensors.md)와
[`../../journal/2026-09-06-zigbee-step2-sensors.md`](../../journal/2026-09-06-zigbee-step2-sensors.md)에
정리한다. UZ-8D 도어센서의 첫 인터뷰 실패, 재페어링과 접점 의미 확정은
[`../../journal/2026-09-07-zigbee-step2-door-sensor.md`](../../journal/2026-09-07-zigbee-step2-door-sensor.md)에
이어진다. 실물 사진은 `../../assets/hardware/zigbee/`에 장치별로 보존한다.
게시용 본문은 [`02-commercial-zigbee-sensors.md`](02-commercial-zigbee-sensors.md)다.

Step 3의 v0.7.0 배포·체크섬·API·SSE 연결 검증 범위는
[2026-09-08 운영 배포 기록](../../journal/2026-09-08-step3-pi-live-deployment.md)에 정리한다.
터미널 자료는 [운영 배포 검증](../../assets/terminal/55-step3-sse-automation-pi-deployment.png)과
[패키지 설치 오류 복구](../../assets/terminal/56-step3-install-build-recovery.png)를 함께 보존한다.
연결 성공만 확인한 상태를 실물 센서·자동화 전체 성공으로 표현하지 않는다.

PCB, 배터리, Sleepy End Device 소비전류 최적화와 케이스는 이번 시리즈에서 다루지 않고
브레드보드 시제품 측정 결과를 확보한 뒤 별도 시리즈로 진행한다.

2026-09-22: 먼저 진행한 전용 PCB 설계·제조 파일 준비 과정은
[PCB 제작 블로그 4편](../pcb-ir-node/README.md)으로 분리했다. 이 설계 기록의 작성은
이 문서의 Step 4 실기 검증 완료나 배터리 수명 검증을 의미하지 않는다.
