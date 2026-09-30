# 첫 ESP32-H2 Zigbee IR 노드는 USB 전원으로 검증한다

## 상태

- 결정일: 2026-09-01
- 상태: 채택
- 이전 배터리 시제품 결정: 전원 최적화 단계로 연기

## 결정

첫 ESP32-H2 Zigbee IR 노드는 배터리, 충전기와 전압 변환기를 제외하고
ESP32-H2-DevKitM-1의 USB 전원을 사용한다.

USB의 5 V 레일에서 전류 제한 저항을 거쳐 940 nm IR LED를 공급하고, ESP32-H2의
3.3 V GPIO가 AO3400A MOSFET Gate를 구동한다. 기능 검증이 끝난 뒤에만 배터리와
Sleepy End Device 소비전류 최적화를 다시 진행한다.

## 이유

- Zigbee 가입, 명령 규격, RMT 파형과 IR 출력 문제를 전원 문제와 분리할 수 있다.
- 배터리 충전·보호·저전력 전원부를 구매하기 전에 핵심 기능을 확인할 수 있다.
- 개발 중에는 USB 로그와 펌웨어 다운로드를 계속 사용할 수 있다.

## 관련 문서

- [USB 전원 ESP32-H2 IR 시제품](../hardware/esp32-h2-usb-ir-prototype.md)
- [향후 배터리 시제품 부품 검토](../hardware/esp32-h2-zigbee-ir-node.md)

