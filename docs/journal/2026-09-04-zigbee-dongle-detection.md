# Zigbee USB 동글 인식 확인

## 목적

Raspberry Pi에 연결한 SONOFF ZBDongle-P 후보 장치가 운영체제에서 직렬 장치로 정상 인식되는지 확인했다. 이번 점검은 읽기 전용으로만 수행했으며 패키지 설치나 시스템 설정 변경은 하지 않았다.

## 확인 결과

- USB 식별자: `10c4:ea60`
- USB 인터페이스: Silicon Labs `CP2102N USB to UART Bridge Controller`
- 커널 드라이버: `cp210x`
- 동적 장치 경로: `/dev/ttyUSB0`
- 고정 장치 경로: `/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller-...-if00-port0`
- 장치 권한: `root:dialout`, 모드 `0660`
- 서비스 사용자 `air`: `dialout` 그룹 포함

따라서 Linux USB/직렬 인식과 서비스 사용자의 포트 접근 권한은 정상이다. Zigbee2MQTT 설정에는 재부팅이나 USB 연결 순서에 따라 달라질 수 있는 `/dev/ttyUSB0` 대신 `/dev/serial/by-id/...` 고정 경로를 사용한다.

블로그용 증거 자료는 다음 두 파일로 보존했다.

- `../assets/terminal/23-zbdongle-p-usb-detection.txt`: 민감정보를 제거한 명령과 원문 출력
- `../assets/terminal/23-zbdongle-p-usb-detection.png`: 위 원문을 그대로 렌더링한 블로그용 이미지

## 아직 검증하지 않은 항목

- 동글 내부 무선 칩과 코디네이터 펌웨어의 실제 응답
- Zigbee2MQTT의 어댑터 연결
- Zigbee 기기 가입과 송수신

위 항목은 Mosquitto와 Zigbee2MQTT 설치·설정 후 검증한다. 현재 Pi에서는 두 프로세스와 systemd 서비스가 발견되지 않았다.

## 다음 작업 후보

1. 로컬에서 Zigbee2MQTT/Mosquitto 구성과 복구 절차를 설계한다.
2. Pi 변경 파일, 설치 패키지, 서비스 영향을 정리한다.
3. 사용자 승인을 받은 한 번의 배포 작업으로 설치한다.
4. Zigbee2MQTT가 고정 직렬 경로로 코디네이터를 여는지 확인한다.
5. 지원되는 릴레이 한 개를 페어링해 MQTT `ON`/`OFF` 왕복을 검증한다.
