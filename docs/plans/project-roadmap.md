# 프로젝트 단계

2026-08-29 사용자와 합의해 작업 순서를 다음처럼 정정했다.

1. **Step 1 — 개발 환경 구성**: Raspberry Pi OS, SSH, Python, FastAPI, systemd,
   Tailscale, 포트 8001 운영 환경
2. **Step 2 — IR 수신**: 리모컨 패킷 캡처·분석·복제 파일 저장, 계층형 코드와
   확장 가능한 리모컨 프로필
3. **Step 3 — UI 구성**: 모바일과 PC에서 사용할 웹 화면
4. **Step 4 — IR 송신**: 트랜지스터 구동 회로, 송신 백엔드, 실제 에어컨 제어 검증

예약은 리모컨의 TIMER 패킷을 재현하는 대신 Raspberry Pi 스케줄러가 명시적
ON/OFF 명령을 실행한다.

## 2026-08-30 완료 상태

- Step 2 캡처를 Carrier CS-A061GS 모델 프로필로 구조화했다.
- Step 3 UI가 사용할 모델 목록, 기기 등록, 의미 기반 제어 API를 구현했다.
- Room First UI를 FastAPI 루트 화면으로 편입하고 에어컨 상세 제어와 빠른 장면을 실제
  API 호출에 연결했다.
- 개발 PC에서는 `mock-ir`, 검증된 Raspberry Pi에서는 `ir-ctl` 전송 계층을 선택한다.
- GPIO18 송신 overlay와 P2N2222A 기반 5V IR 송신 회로를 구성했다.
- `/dev/lirc0` raw 송신과 API 실전송을 확인하고, 거리·방향을 조정한 뒤 실제 Carrier
  에어컨 반응까지 확인했다.
- 전체 과정을 [4편 블로그 초안](../blog/README.md)으로 재구성했다.

## 다음 단계 — Zigbee/MQTT 스마트홈 확장

후속 작업은 [Zigbee/MQTT 스마트홈 확장 4단계 계획](zigbee-mqtt-iot-roadmap.md)을 기준으로 한다.

1. Raspberry Pi에 ZBDongle-P, Mosquitto와 Zigbee2MQTT 게이트웨이를 구성한다.
2. 상용 Zigbee 온습도 센서와 도어/창문 센서를 페어링하고 MQTT payload를 확정한다.
3. 실제 센서 데이터를 기존 FastAPI/UI 및 최소 자동화 한 가지에 연결한다.
4. ESP32-H2 개발보드, 940 nm IR LED와 AO3400A 브레드보드 노드로 에어컨을 제어한다.

PCB, 배터리, Sleepy End Device Poll과 저전력 전원부는 이 네 단계가 끝난 다음 진행한다.
상세 부품표와 회로는
[ESP32-H2 배터리 Zigbee IR 노드 시제품](../hardware/esp32-h2-zigbee-ir-node.md)에 기록한다.
