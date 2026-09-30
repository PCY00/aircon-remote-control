# ESP32-H2 Zigbee IR 노드 확장 구상

## 문서 상태

- 상태: 향후 적용을 위한 아키텍처 구상
- 현재 테스트 구조: Raspberry Pi가 로컬 GPIO를 통해 IR을 직접 송신
- 전환 목표: Raspberry Pi는 중앙 서버가 되고, 공간별 ESP32-H2 노드가 Zigbee로 명령을 받아 IR을 송신
- 적용 시점: Carrier CS-A061GS의 로컬 IR 송신과 웹 제어를 먼저 검증한 뒤 별도 단계에서 진행

현재 구현을 이 구조에 곧바로 종속시키지 않는다. 대신 전송 계층을 인터페이스로 분리해 나중에 로컬 GPIO 전송기를 Zigbee 전송기로 교체할 수 있게 한다.

## 목표 구조

```text
외부 사용자
    ↓ Tailscale
Raspberry Pi 중앙 서버
    ├─ FastAPI 웹/API
    ├─ 기기 카탈로그와 등록 정보
    ├─ 장면·자동화
    ├─ IR 모델 프로필과 명령 선택
    └─ 로컬 MQTT Broker
            ↓
      Zigbee Gateway/Coordinator
            ↓ Zigbee
      ├─ 거실 ESP32-H2 IR 노드
      ├─ 침실 ESP32-H2 IR 노드
      └─ 향후 센서·스위치 노드
```

라즈베리파이만 Wi-Fi 또는 Ethernet과 Tailscale을 사용한다. 공간별 IR 노드는 Wi-Fi에 직접 접속하지 않고 Zigbee 망에만 참여한다.

## 통신 계층 구분

MQTT와 Zigbee는 대체 관계가 아니다.

```text
MQTT       = 애플리케이션 메시지 전달 규칙
Zigbee     = 저전력 무선 네트워크
Wi-Fi      = IP 기반 무선 네트워크
Thread     = 저전력 IPv6 메시 네트워크
Matter     = IP 기반 스마트홈 애플리케이션 표준
```

추천 초기 구성에서는 MQTT가 라즈베리파이 내부에서만 동작한다. ESP32-H2 노드는 MQTT나 Wi-Fi를 알 필요 없이 Zigbee 명령만 처리한다.

```text
FastAPI → 로컬 MQTT → Zigbee 어댑터 → Coordinator → ESP32-H2
```

향후 필요하면 로컬 MQTT를 제거하고 FastAPI의 Zigbee 어댑터가 Coordinator와 직접 통신하도록 바꿀 수 있다. 상위의 기기 명령 인터페이스는 유지한다.

## 노드 하드웨어 최소 구성

```text
ESP32-H2 기반 IR 노드
├─ ESP32-H2 모듈: MCU + IEEE 802.15.4 Zigbee 무선
├─ IR LED
├─ IR LED 구동용 트랜지스터 또는 MOSFET
├─ 베이스/게이트 및 LED 전류 제한 저항
├─ 전원과 디커플링 부품
└─ 선택 부품
   ├─ 페어링 버튼
   ├─ 상태 LED
   └─ 물리 리모컨 감시·학습용 IR 수신기
```

IR 송신에는 기본적으로 출력 GPIO 하나면 된다. 반송파와 펄스 타이밍은 ESP32-H2의 RMT 주변장치가 로컬에서 생성한다. 네트워크 지연으로 IR 타이밍을 직접 만들지 않는다.

IR은 벽을 통과하지 않고 방향 영향을 받으므로 노드는 공간 단위로 배치한다. 한 공간에서 여러 제품을 제어하려면 노드 위치를 조정하거나 서로 다른 방향의 IR LED를 여러 개 사용한다.

## 전원 전략

최종 목표는 공간별 배터리 구동 Zigbee Sleepy End Device다. 다만 2026-09-01 최신
결정에 따라 최초 기능 시제품에서는 배터리를 제외하고 ESP32-H2 개발보드의 USB 전원을
사용한다. Zigbee 가입, 명령 전달과 RMT IR 송신을 먼저 완성한 뒤 배터리와 Poll 소비전류를
최적화한다.

최초 목표는 다음과 같다.

- ESP32-H2-DevKitM-1을 USB로 구동해 기능과 프로토콜을 먼저 검증
- 개발보드 5 V, 940 nm IR LED와 3.3 V 구동이 보장된 N채널 MOSFET 사용
- 기능 완성 후 보호회로 내장 1셀 LiPo와 저전력 전원부 추가
- Poll 간격은 1초로 시작해 2초, 3초, 5초의 지연과 소비 전류 비교
- 500 mAh는 6개월 가능성 시험, 1000 mAh는 6~12개월 목표
- 기능 완성 후 전용 PCB와 저전력 Zigbee MCU로 최적화
- IR LED의 순간 전류는 MCU GPIO가 아니라 MOSFET 회로가 담당

개발보드 상태의 전원 LED와 USB-UART 소비를 최종 제품 수명으로 간주하지 않는다. 상세
부품과 배선은 [ESP32-H2 배터리 Zigbee IR 노드 시제품](../hardware/esp32-h2-zigbee-ir-node.md)에
기록한다.

## IR 프로필과 전송 노드의 역할

라즈베리파이가 모델 프로필의 기준본을 관리한다.

```text
device_profiles/
└─ air_conditioner/
   └─ Carrier/
      └─ CS-A061GS/
         ├─ profile.json
         ├─ packet.md
         ├─ commands.json
         ├─ captures/
         └─ assets/
```

노드는 에어컨 모델이나 UI를 직접 해석하지 않는다. 라즈베리파이가 선택한 명령을 캐시된 IR 데이터로 변환해 송신하는 제한된 역할을 맡는다.

긴 에어컨 IR 타이밍 배열을 매 실행마다 Zigbee로 전달하면 패킷 분할과 재전송이 많아진다. 따라서 다음 방식을 사용한다.

1. 최초 등록 또는 프로필 갱신 시 압축된 IR 프로필을 노드에 전송한다.
2. 노드는 프로필 ID, 버전, 해시와 명령 데이터를 로컬 플래시에 캐시한다.
3. 평상시에는 작은 `profile_id + command_id` 메시지만 보낸다.
4. 노드에 프로필이 없거나 해시가 다르면 실행을 거부하고 갱신을 요청한다.
5. 노드는 IR 송신 후 요청 번호와 성공·실패 결과를 응답한다.

## 메시지 예시

라즈베리파이 내부의 의미 기반 명령 예시:

```json
{
  "device_id": "living-room-aircon",
  "desired_state": {
    "power": true,
    "mode": "cool",
    "temperature": 24,
    "fan": "strong"
  }
}
```

프로필 해석 후 Zigbee IR 노드에 보내는 실행 메시지 예시:

```json
{
  "protocol_version": 1,
  "request_id": 1042,
  "node_id": "living-room-ir",
  "profile_id": "air_conditioner/Carrier/CS-A061GS",
  "profile_version": 1,
  "command_id": "cool_24_strong"
}
```

노드 응답 예시:

```json
{
  "protocol_version": 1,
  "request_id": 1042,
  "status": "sent"
}
```

JSON은 설명용 논리 형식이다. 실제 Zigbee 전송에서는 필드 번호와 정수 ID를 사용하는 짧은 바이너리 메시지로 인코딩할 수 있다.

## 소프트웨어 경계

상위 제어 코드는 전송 방식에 의존하지 않는다.

```text
DeviceCommandService
        ↓
IrTransport
├─ LocalGpioIrTransport       # 현재 테스트
├─ ZigbeeIrTransport          # 향후 ESP32-H2
└─ MockIrTransport            # PC 개발·자동 테스트
```

다른 IoT 장비도 같은 방식으로 어댑터를 추가한다.

```text
DeviceTransport
├─ IR
├─ Zigbee
├─ Wi-Fi MCU
├─ MQTT
├─ Matter/Thread
└─ 외부 플랫폼 어댑터
```

UI와 장면·자동화는 `에어컨 켜기`, `24°C 냉방` 같은 의미 기반 명령만 생성한다. GPIO 번호, Zigbee Cluster, MQTT Topic과 IR 타이밍 배열은 하위 어댑터 내부에 둔다.

## Zigbee와 Thread 전환 가능성

현재 DIY 구현과 빠른 검증에는 Zigbee를 우선 고려한다. 장기적으로 Matter 호환이 중요해지면 Thread와 Matter 어댑터를 추가한다.

ESP32-H2는 Zigbee와 Thread용 IEEE 802.15.4 무선을 지원하므로 하드웨어를 유지하면서 펌웨어와 게이트웨이 계층을 변경할 여지가 있다. 단, Zigbee와 Thread를 동시에 지원한다고 가정하지 않고 실제 SDK·메모리·인증 조건을 전환 시점에 다시 검증한다.

## 보안과 운영 원칙

- 노드 페어링은 사용자가 요청한 시간에만 허용한다.
- Zigbee 네트워크 키와 MQTT 인증 정보는 저장소에 기록하지 않는다.
- 모든 명령에 요청 번호를 넣어 중복 실행과 응답 매칭을 처리한다.
- 프로필 파일은 버전과 해시를 검증한다.
- 노드 펌웨어와 프로필 갱신 실패 시 이전 정상 버전을 유지한다.
- 실제 기기 상태와 `IR 송신 성공`은 동일하지 않다. IR은 기본적으로 단방향이므로 UI 상태에는 추정 상태임을 반영한다.

## 단계적 전환 계획

Carrier CS-A061GS의 Raspberry Pi 로컬 IR 송신, 의미 기반 명령과 Mock/API 검증은 완료했다.
후속 구현은 [Zigbee/MQTT 스마트홈 확장 4단계 계획](../plans/zigbee-mqtt-iot-roadmap.md)을
기준으로 다음 순서로 진행한다.

1. Raspberry Pi에 ZBDongle-P Coordinator, 로컬 MQTT와 Zigbee2MQTT를 구성한다.
2. 상용 온습도 및 도어/창문 센서로 페어링과 실제 MQTT 데이터 경로를 검증한다.
3. FastAPI/UI에 센서 상태, 오프라인 처리와 최소 자동화를 연결한다.
4. USB 전원 ESP32-H2, 940 nm IR LED와 MOSFET 브레드보드 노드를 만들어
   `LocalGpioIrTransport`와 `ZigbeeIrTransport`의 동일한 의미 기반 제어를 비교한다.
5. 위 기능 검증 후 프로필 무선 갱신, 공간별 노드, SED Poll, 배터리 수명과 PCB를 진행한다.

## 참고 자료

- [Espressif ESP32-H2 제품 개요](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32h2/product-overview.html)
- [Espressif ESP32-H2 RMT 문서](https://docs.espressif.com/projects/esp-idf/en/stable/esp32h2/api-reference/peripherals/rmt.html)
- [Espressif Zigbee SDK 소개](https://docs.espressif.com/projects/esp-zigbee-sdk/en/latest/esp32h2/introduction.html)
- [MQTT 공식 사양](https://mqtt.org/mqtt-specification/)
- [Thread 공식 개요](https://threadgroup.org/what-Is-thread/overview)
