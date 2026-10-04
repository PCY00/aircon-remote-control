# 2026-10-03 — H2 만능기판 시제품의 GPIO 핀 재확인

## 상황

사용자가 ESP32-H2 SuperMini, IR LED, MOSFET, 저항 및 100 nF 커패시터를 만능기판에
조립하고 앞면·뒷면·측면과 배선도 사진을 제공했다. 사용자는 전원 투입 전 배선 측정을
마쳤다고 보고했다. 측정값 자체는 전달받지 않았으므로 사진만으로 납땜·전기적 연결을
완료 검증한 것으로 기록하지 않는다.

## 진단

- PC에서 COM6을 Espressif USB 직렬 장치로 식별했다. 장치 고유 식별자는 공개용
  [터미널 캡처](../assets/terminal/348-h2-perfboard-gpio-mismatch.txt)에서 제거했다.
- USB 콘솔에 송신을 일으키지 않는 `h`를 보내 정상 응답을 확인했다.
- 실제 부팅 로그는 `IR output ready: GPIO5, 38 kHz, duty 33%`였다. 점검 당시 로컬
  `firmware/esp32-h2-ir-node/main/main.c`는 이전 GPIO8 시험 설정을 유지하고 있었으나,
  실물 핀 확인 뒤 GPIO5로 정정했다. 보드 플래시는 하지 않았다.
- 현재 보드 앱에는 `5` 카메라 명령도 없으므로 최신 로컬 소스가 플래시된 상태가 아니다.
- 제출된 배선도에는 GPIO8이 표시됐지만 사용자가 실물 만능기판은 GPIO5에 연결했다고
  확인했다. **보고된 실물 배선과 현재 보드 펌웨어의 GPIO 번호는 일치**한다.
  앞서 내린 불일치 판단은 배선도만 근거로 한 잘못된 추정이었다.
- GPIO8로 그려진 원본은 `../assets/hardware/esp32-h2-supermini-user-wiring-gpio8-original.png`에
  보존했다. 이 그림의 파란 신호선을 GPIO5로 옮긴 편집본은
  `../assets/hardware/esp32-h2-supermini-user-wiring-gpio5-edited.png`이다.
  편집본은 이미지 생성 도구로 수정한 설명용 그림이며, 작은 핀 인쇄와 실제 전기적
  연결을 증명하지는 않는다. 로컬 SVG 배선도도 GPIO5로 정정했다.
- 사용자는 현재 플래시된 GPIO5 펌웨어가 이전 시험에서 동작했다고 보고했다. 이는 새
  만능기판에서의 발광이나 에어컨 반응을 아직 검증한 것은 아니다.
- 핀 정정 전 호스트 테스트에서는 `python -m pytest tests/test_h2_ir_firmware.py -q`가
  7개 통과했다. 핀 정정 후 같은 명령의 재실행은 Windows C 컴파일러가 한글 작업
  경로를 처리하지 못해 테스트 준비 단계에서 7개 모두 오류가 났다. 이는 H2 보드
  실행 결과가 아니며 테스트 통과로 간주하지 않는다.
- 핀 정정 후 `scripts/esp32_h2_firmware.ps1 build`: ESP-IDF 5.5.4에서 성공,
  앱 크기 0x2d4a0 bytes. 보드에 플래시하지 않았다.
- 공개용 이미지 검사: `IMAGE_COUNT=432`, `PRIVATE_METADATA_COUNT=0`.

## 카메라 시험 전 계획

현재 플래시된 GPIO5 펌웨어를 그대로 사용해 카메라용 IR 발광을 먼저 시험하기로 했다.
펌웨어 플래시는 필요하지 않으며 실행하지 않았다. 그 뒤 Carrier 명령의 실제 에어컨
반응, Zigbee/MQTT 연결 순서로 검증한다. 이 계획을 세운 시점에는 만능기판의
IR 발광·에어컨 제어·Zigbee 통신 성공이 미확인이었다. 카메라 시험 결과는 아래에
별도로 기록한다.

## GPIO5 카메라 테스트 명령

- COM6에서 기존 펌웨어의 `c`를 1회 전송했다. 기록:
  [349-h2-perfboard-gpio5-camera-test.txt](../assets/terminal/349-h2-perfboard-gpio5-camera-test.txt).
- 실제 응답은 `camera test: ten 20 ms IR bursts on GPIO5`와
  `camera test complete`였다. 이는 펌웨어가 전송을 완료했다는 로그이며,
  IR LED의 실제 발광을 증명하지 않는다.
- 사용자는 휴대폰 카메라에서 점멸이 보였다고 확인했고, 약 6.8초 영상도 제공했다.
  영상의 약 2.3초 프레임에는 IR LED가 카메라에서 분홍색으로 보이는 장면이 있다.
  따라서 이 만능기판의 **카메라 관찰 기준 발광은 확인**했다. 다만 영상만으로
  반송파 주파수·광량·에어컨 수신 성공을 확인할 수는 없다.
- 원본 영상은 저장소 밖에 그대로 보관하고, 블로그용 사본은 오디오와 원본
  메타데이터를 제거해 H.264 MP4로 저장했다:
  [공개용 영상](../assets/hardware/esp32-h2-supermini-ir-gpio5-camera-test.mp4),
  [발광 프레임](../assets/hardware/esp32-h2-supermini-ir-gpio5-camera-flash.png).
  공개용 영상에는 기술적 인코더·컨테이너 태그만 있고 촬영 시각·위치·기기 모델
  태그와 오디오 스트림은 없다. 카메라 발광 시험 단계에서는 에어컨 제어 명령을
  보내지 않았다.

## Carrier POWER_OFF 첫 실기 시험

- 사용자의 실기 시험 요청 후 COM6 연결을 확인하고 기존 펌웨어의 `f` 명령을
  **한 번만** 보냈다. 기록:
  [350-h2-perfboard-carrier-power-off-first-test.txt](../assets/terminal/350-h2-perfboard-carrier-power-off-first-test.txt).
- 보드는 `sending POWER_OFF: 2 frames, 100 symbols`와 `sent POWER_OFF`를 보고했다.
  이는 RMT 송신 완료 로그이며 에어컨 수신·전원 꺼짐의 증거가 아니다.
- 이후 사용자가 **에어컨이 실제로 꺼졌다**고 현장에서 확인했다. 따라서 이
  1회 시험에서는 GPIO5 만능기판의 IR 송신으로 Carrier 에어컨 전원 끄기에
  성공했다. 사용자의 현장 보고이며 별도 계측·영상 증빙은 없다.
- 반복 성공률, 송신 거리·각도, 장시간 안정성, Zigbee/MQTT 경유 제어는
  아직 검증하지 않았다.
