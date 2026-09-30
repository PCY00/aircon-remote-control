# ESP32-H2 SuperMini 개발 AI 인수인계 프롬프트

아래 전체를 다른 컴퓨터의 AI에게 전달한다. 저장소 경로와 COM 포트는 새 컴퓨터에서
실제로 확인한 값으로 바꾼다.

```text
나는 기존 스마트홈/에어컨 원격 제어 프로젝트의 ESP32-H2 SuperMini 개발을 이
컴퓨터에서 이어가려고 한다. 추측으로 처음부터 다시 만들지 말고 아래 상태를 기준으로
기존 코드를 검사한 뒤 계속 진행해라.

[가장 먼저 할 일]

1. 이 저장소의 AGENTS.md를 끝까지 읽고 적용한다.
2. 저장소 전체를 새 컴퓨터에 동기화한 뒤 현재 변경 사항을 보존한다.
3. 실제 저장소 루트와 ESP32-H2가 연결된 COM 포트를 새 컴퓨터에서 탐지한다.
   이전 컴퓨터의 사용자명, 절대 경로 또는 COM6를 그대로 가정하지 않는다.
4. 작업 기준본은 저장소 안의 firmware/esp32-h2-ir-node이다.
   BUILD_DIRECTORY에 표시되는 C:\esp\aircon-h2-ir-node-<checkout-hash>는
   빌드용 임시 복사본이므로 직접 수정하지 않는다.
5. 비밀번호, MAC 주소, 사설 IP, 인증 키 등은 출력·문서·캡처에 남기지 않는다.

[프로젝트의 최종 흐름]

웹 UI
→ Raspberry Pi FastAPI/자동화
→ Raspberry Pi의 MQTT + Zigbee2MQTT
→ ZBDongle-P Zigbee coordinator
→ ESP32-H2 Zigbee 노드
→ RMT 38 kHz IR 송신
→ Carrier CS-A061GS 에어컨

ESP32-H2에는 Wi-Fi가 없다. MQTT를 ESP32-H2가 직접 사용하는 구조가 아니다.
MQTT는 Raspberry Pi에서 끝나고 Zigbee2MQTT가 MQTT 명령과 Zigbee 메시지를 연결한다.
현재 ESP32-H2는 USB 전원 프로토타입이며 배터리·deep sleep·PCB 최적화는 뒤 단계다.

[현재 하드웨어]

- 보드: ESP32-H2 SuperMini
- IR LED: Vishay TSAL6200 계열 940 nm 5 mm IR LED 1개
- MOSFET: AO3400A N-channel
- 현재 IR 제어 GPIO: GPIO8
- GPIO8은 보드 내장 addressable RGB LED 데이터선 및 스트래핑 기능과 공유된다.
  현재 프로토타입에서는 실제 GPIO8 배선과 맞추기 위해 사용 중이다. 최종 제품 핀은
  Zigbee 통합 뒤 부팅 안정성과 내장 LED 간섭을 검토해 다시 결정한다.

현재 검증된 배선:

USB-C → ESP32-H2 SuperMini 전원
보드 5V → 47 ohm → TSAL6200 anode(+)
TSAL6200 cathode(-) → AO3400A Drain
AO3400A Source → GND
GPIO8 → 100 ohm → AO3400A Gate
AO3400A Gate → 100 kohm → GND
100 nF ceramic capacitor → 5V와 GND 사이

모든 GND는 공통이다. 배선 변경은 USB 전원을 뺀 상태에서 한다. IR LED 전류 제한
저항을 제거하지 않는다. 5V와 3.3V 핀을 혼동하지 않는다.

[확정된 하드웨어 관찰]

- 기존 에어컨 리모컨의 IR은 같은 휴대폰 카메라에서 보였다.
- TSAL6200을 전류 제한 저항과 함께 직접 시험했을 때 카메라에서 발광이 보였다.
- 최초에는 실제 회로가 GPIO5라고 잘못 판단해 펌웨어를 GPIO5로 만들었고 발광이
  보이지 않았다.
- 실제 연결 핀은 GPIO8이었다. 펌웨어도 GPIO8로 변경한 뒤 외부 IR LED 점멸이
  휴대폰 카메라에서 확인됐다.
- 따라서 최종 원인은 GPIO5 불량이 아니라 펌웨어 GPIO5와 실제 GPIO8 배선의 불일치였다.
- GPIO8의 카메라용 발광은 확인됐지만 38 kHz 반송파 실측은 하지 않았다. Carrier POWER_OFF 명령에는 아직
  에어컨이 반응하지 않았다. 실제 에어컨 제어를 성공했다고 기록하면 안 된다.

[현재 펌웨어]

2026-09-12 로컬 소스에는 TX 오류 보호와 5초 시험 명령이 추가됐다. 이 개선본을
실제 보드에 다시 플래시하지는 않았다. 소스·빌드 산출물·현재 보드에 설치된 버전을
동일하다고 가정하지 말고 플래시 이력과 부팅 도움말을 함께 확인한다.

주요 파일:

- firmware/esp32-h2-ir-node/main/main.c
- firmware/esp32-h2-ir-node/main/carrier_profile.h
- firmware/esp32-h2-ir-node/CMakeLists.txt
- firmware/esp32-h2-ir-node/main/CMakeLists.txt
- firmware/esp32-h2-ir-node/sdkconfig.defaults
- firmware/esp32-h2-ir-node/README.md
- scripts/esp32_h2_firmware.ps1

도구 버전:

- ESP-IDF 5.5.4
- target: esp32h2
- console: USB Serial/JTAG
- 추후 ESP Zigbee SDK 2.0.0 연동 예정

IR 설정:

- RMT resolution: 1 MHz
- carrier: 38 kHz
- duty: 33%
- idle: LOW
- GPIO: GPIO8
- leader: pulse 4350 us, space 4350 us
- data pulse: 560 us
- zero space: 520 us
- one space: 1610 us
- frame gap: 5150 us
- bit order: observed MSB first
- Carrier 상태 패킷은 동일 프레임을 2번 전송

현재 USB 콘솔 명령:

- c: 에어컨 명령이 아닌 카메라용 38 kHz 점멸 시험
- 5: 카메라 시험을 5초간 실행(25회 짧은 burst, 에어컨 명령 없음)
- n: Carrier CS-A061GS 켜기, 냉방 17 C, 강풍
- f: Carrier CS-A061GS 명시적 POWER_OFF
- h: 도움말

한 번에 명령 1개를 보내고 완료를 기다린다. TX 오류가 발생하면 오류 상태를 유지하고
추가 전송을 거부하며 재시작이 필요하다. 전송 버퍼는 정적으로 유지되어 timeout 뒤에도
드라이버가 해제된 스택 메모리를 참조하지 않는다.

패킷:

- POWER_ON_COOL_17_HIGH: B2 4D 3F C0 00 FF, 2회
- POWER_OFF: B2 4D 7B 84 E0 1F, 2회

원본과 프로필:

- device_profiles/air_conditioner/Carrier/CS-A061GS/commands.json
- device_profiles/air_conditioner/Carrier/CS-A061GS/packet.md
- signals/remote-16214-15597/raw/power-off-from-cool-17-high-01.ir
- signals/remote-16214-15597/raw/power-off-from-cool-17-high-01.compact
- signals/remote-16214-15597/metadata/power-off-from-cool-17-high-01.json
- docs/journal/2026-09-11-zigbee-step4-esp32-h2-ir-bringup.md

[Windows 빌드 주의사항]

저장소 경로에 한글이 있어 ESP-IDF Kconfig가 cp949 UnicodeDecodeError를 낸 적이 있다.
단순 junction은 CMake가 실제 한글 경로로 환원해서 해결되지 않았다. 현재
scripts/esp32_h2_firmware.ps1은 저장소의 펌웨어 소스만
C:\esp\aircon-h2-ir-node-<checkout-hash>로 복사하고 그 ASCII 경로에서 생성·빌드한다.
BUILD_DIRECTORY 출력으로 산출물 위치를 찾는다. 이전 aircon-h2-ir-node-build 폴더는
보존하지만 새 빌드에 사용하지 않는다. flash/monitor에는 -Port 지정이 필수다.

새 컴퓨터에 ESP-IDF가 다른 경로로 설치됐다면 -IdfPath로 실제 경로를 전달한다.
COM 포트도 반드시 탐지한 실제 값을 사용한다.
설치 도구 경로는 -IdfToolsPath 또는 기존 IDF_TOOLS_PATH를 사용하며 기본값은
C:\Espressif다. ASCII 임시 디렉터리의 상위 경로는 -BuildRoot로 변경할 수 있다.

PowerShell 예시:

./scripts/esp32_h2_firmware.ps1 build -IdfPath <ESP-IDF-5.5.4-path>
./scripts/esp32_h2_firmware.ps1 flash -Port <actual-COM-port> -IdfPath <ESP-IDF-5.5.4-path>
./scripts/esp32_h2_firmware.ps1 monitor -Port <actual-COM-port> -IdfPath <ESP-IDF-5.5.4-path>

보드가 COM 포트에 연결됐다 끊기는 상태라면 다음 ROM downloader 복구 절차가 실제로
동작했다.

1. USB를 뺀다.
2. BOOT 버튼을 누른다.
3. BOOT를 누른 상태에서 USB를 연결한다.
4. 약 2초 뒤 BOOT를 놓는다.
5. COM 포트가 유지되는지 확인하고 플래시한다.
6. 플래시 뒤에는 BOOT를 누르지 않고 USB를 정상 재연결해 앱 부팅을 확인한다.

이전 컴퓨터에서는 시리얼 모니터가 간헐적으로 ClearCommError와 USB 재연결을 보고했다.
카메라 시험과 패킷 전송은 재연결 뒤 실행되기도 했지만 원인은 확정되지 않았다. 새
컴퓨터에서 케이블, USB 포트, 보드 전원, 실제 재부팅 로그를 나눠 검사하고 결과를
기록한다. 단순히 성공으로 숨기지 않는다.

[다음 작업 우선순위]

1. 새 컴퓨터에서 기존 펌웨어를 수정 없이 빌드·플래시한다.
2. 정상 앱 부팅 로그에서 GPIO8, 38 kHz를 확인한다.
3. c 명령으로 외부 IR LED 카메라 점멸을 다시 확인한다.
4. HW-477 수신기를 IR LED 정면 5~10 cm에 놓고 f 신호를 재수신한다.
5. H2에서 재수신한 pulse/space를 저장소의 power-off 원본과 비교한다.
6. 프레임, 비트 순서 및 간격이 일치하면 에어컨 수신창 5~10 cm 정면에서
   POWER_OFF를 제한된 횟수로 시험한다.
7. 근거리에서도 실패하면 출력 세기와 광학 방향을 검토한다. 근거 없이 저항부터 낮추거나
   반복 송신하지 않는다.
8. IR 파형과 실제 에어컨 반응을 확인한 뒤 ESP Zigbee SDK를 추가해 Zigbee 명령을
   의미 기반 IR 명령으로 매핑한다.

HW-477은 복조 수신기이므로 pulse/space 포락선은 비교할 수 있지만 정확한 반송파
주파수 자체는 측정할 수 없다. 카메라 발광 역시 38 kHz 실측을 의미하지 않는다.
필요시 적합한 광검출 회로와 측정장비로 반송파를 별도 확인한다.

Zigbee를 추가할 때 UI나 Raspberry Pi가 raw IR timing을 직접 다루게 만들지 않는다.
예를 들어 POWER_OFF 또는 COOL_24_HIGH 같은 의미 기반 명령을 Zigbee attribute/command로
전달하고, ESP32-H2의 기기 프로필 계층이 실제 패킷을 선택하도록 분리한다.

[완료 및 기록 규칙]

- 실행한 명령과 실제 출력만 근거로 판단한다.
- 빌드 성공, RMT 전송 완료, 카메라 발광, 재수신 파형 일치, 실제 에어컨 반응을 각각
  다른 검증 단계로 취급한다.
- 중요한 명령과 오류는 UTF-8 TXT와 PNG로 docs/assets/terminal에 남긴다.
- 사진은 docs/assets/hardware 아래에 두고 EXIF/XMP 제거 후
  scripts/sanitize_blog_images.py 검사에서 PRIVATE_METADATA_COUNT=0을 확인한다.
- 정확한 실패 증상, 가설, 시도, 해결책과 미해결 항목을 docs/journal 및
  docs/troubleshooting.md에 기록한다.
- 저장소의 사용자 변경을 보존하고 C:\esp 임시 빌드 복사본을 기준본으로 만들지 않는다.

먼저 저장소와 새 PC 환경을 읽기 전용으로 점검한 뒤, 발견한 상태와 첫 실행 계획을
짧게 보고하고 진행해라. 펌웨어 플래시는 내가 요청한 ESP32-H2 개발 범위에서 허용하지만,
배선·전류 제한 저항·GPIO 핀 변경은 변경 이유와 안전 영향을 먼저 알려라.
```
