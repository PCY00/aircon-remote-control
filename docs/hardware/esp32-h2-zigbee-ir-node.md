# ESP32-H2 배터리 Zigbee IR 노드 시제품

## 목표

3.7 V 1셀 리튬폴리머 배터리로 동작하는 Zigbee Sleepy End Device가 명령을 받은 뒤
940 nm IR LED로 Carrier CS-A061GS 에어컨 패킷을 송신하는 첫 시제품을 만든다.

이 부품표는 납땜과 펌웨어 검증이 쉬운 1차 시제품용이다. 개발보드 자체의 전원 LED와
USB-UART 회로 때문에 이 상태로 6~12개월 수명을 보장하지 않는다.

## 확정 부품표

| 구분 | 권장 부품 | 수량 | 선정 이유 |
|---|---|---:|---|
| MCU 개발보드 | Espressif `ESP32-H2-DevKitM-1-N4` | 1 | 공식 보드, PCB 안테나, Zigbee 3.0, RMT, J5 전류 측정 헤더 |
| 배터리 | 보호회로 내장 1S LiPo 3.7 V, 1000 mAh, JST-PH 2.0 | 1 | 6~12개월 목표에 500 mAh보다 여유가 큼 |
| 소형 비교 배터리 | 보호회로 내장 1S LiPo 3.7 V, 500 mAh | 선택 | 크기와 실제 수명 비교용 |
| 충전기 | TP4056 USB-C 충전+보호 완제품 모듈 | 1 | 저렴하고 납땜된 모듈 상태로 사용 가능 |
| 3.3 V 전원 | `MCP1700-3302E/TO` 3.3 V LDO, TO-92 | 2 | 저렴한 스루홀 부품, 250 mA, 낮은 대기전류 |
| IR LED | Vishay `TSAL6200`, 940 nm, 5 mm | 3 | ±17° 절반 세기 각도, 리모컨용 고출력 펄스 대응 |
| 광각 비교 LED | Vishay `TSAL6400`, 940 nm, 5 mm | 선택 2 | ±25°로 범위는 넓고 정면 세기는 낮음 |
| MOSFET | AOS `AO3400A` SOT-23 또는 해당 부품 실장 Breakout | 3 | VGS=2.5 V에서 RDS(on)이 규정되어 3.3 V GPIO 구동에 적합 |
| LED 저항 | 33 ohm, 0.5 W | 5 | 1셀 LiPo 완충 전압에서 약 100 mA 이하로 시작하는 기본값 |
| LED 비교 저항 | 47 ohm, 0.5 W | 5 | 광출력이 조금 낮은 안전한 최초 점등 시험용 |
| 게이트 직렬 저항 | 100 ohm, 0.25 W | 5 | GPIO 순간 충전 전류와 링잉 완화 |
| 게이트 풀다운 | 100 kohm, 0.25 W | 5 | 부팅·리셋 중 IR LED가 임의로 켜지는 현상 방지 |
| IR 버퍼 커패시터 | 220 uF, 6.3 V 이상, 저ESR 권장 | 2 | IR 펄스 순간 배터리 전압 강하 완화 |
| 바이패스 | 100 nF 세라믹 | 5 | 고주파 노이즈 억제 |
| 전원 벌크 | 10 uF 세라믹 또는 저ESR | 3 | LDO 입출력 근처 보조 디커플링 |
| LDO 안정화 | 1 uF 세라믹 | 4 | MCP1700 입출력의 필수 안정화 커패시터 |
| MCU 펄스 버퍼 | 100 uF, 6.3 V 이상 | 2 | Zigbee 송수신 순간 전압 강하 완화 |
| 전원 스위치 | SPST 슬라이드 스위치 | 1 | 충전·배선 작업 중 시스템 분리 |
| 연결 | JST-PH 2.0 피그테일, 핀헤더, 점퍼선, 만능기판 | 필요량 | 시제품 조립 |

라즈베리파이 쪽에는 다음 부품을 별도로 사용한다.

| 구분 | 권장 부품 | 수량 | 선정 이유 |
|---|---|---:|---|
| Zigbee Coordinator | SONOFF `ZBDongle-P` (TI CC2652P) | 1 | Coordinator 펌웨어 기본 탑재, Zigbee2MQTT 지원, 외장 안테나 |
| USB 연장선 | 차폐된 USB 2.0 연장선 0.5~1 m | 1 | Raspberry Pi 4와 USB 3 주변의 2.4 GHz 간섭 회피 |

USB 동글은 이 네트워크에서 `Router`가 아니라 하나뿐인 `Coordinator`로 사용한다.
나중에 메시 범위 확장이 필요하면 상시전원 Zigbee Router를 별도로 추가한다.

AO3400A는 SMD 부품이므로 첫 시험에서는 핀이 G/D/S로 표시된 Breakout을 쓰는 편이
안전하다. 판매처마다 Breakout 핀 순서가 다를 수 있으므로 실크와 데이터시트를 확인한다.

## 추가로 필요한 장비

- DC 전압·저항·연속성·mA 측정이 가능한 디지털 멀티미터
- 납땜 인두, 납, 플럭스
- 가능하면 전류 파형을 적산할 수 있는 전력 프로파일러

이 단계부터 멀티미터는 선택 장비가 아니다. LDO 출력이 3.3 V인지 확인하지 않고
ESP32-H2에 연결하지 않는다. JST 커넥터도 판매처에 따라 극성이 뒤바뀐 사례가 있으므로
빨간색 선만 믿지 않고 실제 극성을 측정한다.

## 왜 이 LED와 MOSFET을 선택했는가

`TSAL6200`은 940 nm, ±17° 제품이며 연속 순방향 전류 정격은 100 mA, 지정된 짧은 펄스
조건의 피크 정격은 200 mA다. 첫 시제품은 정격 한계까지 밀지 않고 33 ohm 또는 47 ohm
저항으로 시작한다.

`AO3400A`는 2.5 V 게이트 전압에서 최대 RDS(on)이 48 milliohm으로 규정되어 있다.
따라서 ESP32-H2의 3.3 V GPIO로 확실히 켤 수 있고 100~200 mA IR 펄스에는 충분한
여유가 있다. 단순히 문턱 전압 `VGS(th)`만 낮은 MOSFET을 고르면 안 된다.

한 방향의 먼 거리 성능이 우선이면 `TSAL6100`(±10°), 설치 오차에 대한 관용도가
우선이면 `TSAL6400`(±25°)을 비교할 수 있다. 첫 기준은 중간 각도의 `TSAL6200`이다.

## 기본 회로

첫 시제품은 충전할 때 시스템 전원을 끄고 배터리를 충전 모듈에 연결하는 구성을 사용한다.

```text
보호회로 내장 1S LiPo
 BAT+ ── 전원 스위치 ── SYS_BAT+ ──┬─ MCP1700 VIN
                                    │
                                    └─ 33 ohm/0.5 W ── IR LED Anode
 BAT- ──────────────────────────────┬─ MCP1700 GND
                                    └─ 시스템 GND

MCP1700 VOUT ── ESP32-H2 DevKit 3V3
MCP1700 GND  ── ESP32-H2 DevKit GND

MCP1700 VIN  ── 1 uF ── GND
MCP1700 VOUT ── 1 uF + 100 uF ── GND

ESP32-H2 GPIO5 ── 100 ohm ── AO3400A Gate
                                  │
                               100 kohm
                                  │
                                 GND

IR LED Cathode ── AO3400A Drain
AO3400A Source  ── GND

SYS_BAT+ ── 220 uF ── GND     # IR LED/MOSFET 가까이
SYS_BAT+ ── 100 nF ── GND
```

ESP32-H2-DevKitM-1에서는 GPIO5를 첫 IR 출력 핀으로 사용한다. GPIO8은 보드 RGB LED,
GPIO9는 BOOT, GPIO13/14는 보드 리비전에 따라 32.768 kHz 크리스털과 연결될 수 있어
첫 배선에서는 피한다.

리튬 배터리의 3.7 V는 공칭값이고 실제 범위는 대략 4.2 V에서 방전 말기 전압까지다.
ESP32-H2 모듈의 권장 전원은 3.0~3.6 V이므로 배터리를 3V3 핀에 직접 연결하지 않는다.
MCP1700은 Buck-Boost가 아니므로 배터리 전압이 낮아지면 3.3 V를 더는 유지하지 못한다.
첫 시제품은 방전 말기 용량 일부를 포기하고 기능을 싸고 간단하게 검증한다.

## 저항의 시작값

실제 전류는 배터리 전압, LED 순방향 전압, 배선 저항에 따라 달라진다. 완충 4.2 V,
LED 순방향 전압 약 1.3~1.5 V를 가정하면 다음 값으로 시작할 수 있다.

- 47 ohm: 낮은 광출력으로 배선과 파형을 먼저 확인
- 33 ohm: 기본 실사용 후보
- 27/22 ohm: 실제 전류와 LED 펄스 조건을 측정한 뒤에만 검토

저항을 제거하거나 GPIO에 IR LED를 직접 연결하지 않는다.

IR LED를 두 개 쓰면 각 LED에 저항을 하나씩 둔다.

```text
SYS_BAT+ ── 33 ohm ── LED1 ──┐
                              ├─ MOSFET Drain
SYS_BAT+ ── 33 ohm ── LED2 ──┘
```

LED 두 개를 병렬로 연결하면서 저항 하나만 공유하지 않는다.

## 충전 방식

### 첫 시제품 기본

- 보호회로 내장 배터리와 TP4056 USB-C 충전·보호 완제품 모듈을 사용한다.
- `B+`, `B-`에는 배터리, `OUT+`, `OUT-`에는 부하를 연결한다.
- 500 mAh 셀에는 기본 1 A 모듈을 사용하지 않고 500 mA 이하로 설정된 제품을 고른다.
- 1000 mAh 셀도 제조사가 1 A 충전을 허용하는지 먼저 확인한다.
- 첫 구성에서는 장치를 끈 상태로 충전한다.

TP4056도 시스템 PowerPath 관리 IC가 아니다. 장치가 동작하는 상태로 충전하면 부하
때문에 충전 종료 판정이 부정확해질 수 있다.

### 충전 중에도 동작해야 할 때

`BQ24074` PowerPath 충전 Breakout을 사용한다.

```text
USB-C/5 V → BQ24074 IN
LiPo      ↔ BQ24074 BAT
BQ24074 OUT → 3.3 V 전원 변환 → ESP32-H2
            └→ IR LED 전원
```

BQ24074의 OUT은 고정 3.3 V가 아니므로 여전히 ESP32-H2 앞에는 3.3 V 변환기가 필요하다.

## 펌웨어 최초 제한값

- RMT 반송파: 캡처 데이터에 맞춘 약 38 kHz
- 반송파 Duty: 약 1/3부터 시작
- 동시에 하나의 명령만 송신
- 부팅 즉시 MOSFET Gate를 Low로 설정
- 프로필에 지정된 반복 횟수 이상 임의 반복 금지
- IR 송신 후 Zigbee로 `received`, `sent` 상태를 구분해 응답
- SED Poll 간격은 1초로 기능을 확인한 뒤 2초, 3초, 5초 순서로 비교

IR 타이밍은 Zigbee 패킷 도착 시간에 맞춰 GPIO를 직접 토글하지 않는다. 명령 데이터는
로컬에 캐시하고 RMT가 38 kHz 반송파와 마크/스페이스 시간을 생성한다.

## 단계별 검증

1. 배터리를 연결하지 않은 상태에서 극성과 단락 여부를 확인한다.
2. 배터리와 MCP1700만 연결하고 출력이 3.3 V인지 측정한다.
3. ESP32-H2만 연결해 부팅과 Zigbee 예제 동작을 확인한다.
4. 47 ohm 저항과 IR LED 한 개로 MOSFET 송신 회로를 연결한다.
5. 휴대전화 카메라로 IR 점멸 여부를 참고 확인한다.
6. TSAL6200을 에어컨 수신부에 가까이 조준해 실제 제어를 검증한다.
7. 33 ohm으로 바꾸고 거리와 각도를 비교한다.
8. Zigbee SED Poll 주기별 명령 지연과 평균 소비 전류를 기록한다.
9. 개발보드 J5로 모듈 전류와 전체 배터리 전류를 구분해 측정한다.

휴대전화 카메라에 보인다는 사실은 38 kHz 변조와 패킷 타이밍이 맞다는 증거가 아니다.
최종 검증은 에어컨 반응과 송신 타이밍 데이터로 수행한다.

## 2차 저전력 PCB 후보

- MCU: `ESP32-H2-MINI-1` 모듈부터 적용
- 목표 미달 시 MCU: `EFR32MG22` 또는 `CC26xx` 계열 재검토
- 전원: `TPS63900` 3.3 V Buck-Boost 후보
- 충전: 충전식 제품이면 PowerPath와 배터리 온도 감시 포함
- 상태 LED: 생산·페어링 중에만 켜고 평상시 완전 차단
- USB-UART: 최종 제품에서 제거하거나 전원 차단 가능하게 구성
- IR LED: 설치 방향에 따라 TSAL6200 한 개 또는 LED별 저항을 둔 두 개

첫 시제품의 MCP1700은 값이 싸고 대기전류가 작지만 배터리 방전 전압 전체를 활용하지
못한다. TPS63900은 75 nA급 대기전류와 Buck-Boost 동작을 제공하므로 최종 PCB 후보로
기록하되, WSON 패키지와 PCB 레이아웃은 별도 설계·조립 단계에서 검증한다.

## 안전 주의

- 부풀거나 손상된 LiPo를 사용하지 않는다.
- 배터리를 납땜 인두, 금속 공구와 가연물 근처에 방치하지 않는다.
- 보호회로가 없는 셀을 시제품에 직접 사용하지 않는다.
- 충전 전류는 배터리 제조사 정격을 넘기지 않는다.
- JST 극성을 실제 측정한다.
- 배선 변경은 배터리와 USB를 모두 분리한 상태에서 한다.
- IR LED와 MOSFET의 G/D/S 또는 A/K 방향을 데이터시트로 확인한다.

## 공식 참고 자료

- [ESP32-H2-DevKitM-1 사용자 안내서](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html)
- [ESP32-H2-MINI-1 데이터시트](https://documentation.espressif.com/esp32-h2-mini-1_mini-1u_datasheet_en.html)
- [ESP32-H2 RMT](https://docs.espressif.com/projects/esp-idf/en/latest/esp32h2/api-reference/peripherals/rmt.html)
- [Vishay TSAL6200 데이터시트](https://www.vishay.com/docs/81010/tsal6200.pdf)
- [Vishay TSAL6400 데이터시트](https://www.vishay.com/docs/81011/tsal6400.pdf)
- [AOS AO3400A 제품 사양](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a)
- [Microchip MCP1700 제품 사양](https://www.microchip.com/en-us/product/mcp1700)
- [Top Power TP4056 데이터시트](https://www.toppwr.com/uploadfile/file/20230304/640301eae1260.pdf)
- [TI BQ24074 제품 사양](https://www.ti.com/product/BQ24074)
- [TI TPS63900 제품 사양](https://www.ti.com/product/TPS63900)
- [SONOFF ZBDongle-P 제품 사양](https://sonoff.tech/en-us/products/sonoff-zigbee-3-0-usb-dongle-plus-zbdongle-p/58)
- [Zigbee2MQTT zStack 어댑터](https://www.zigbee2mqtt.io/guide/adapters/zstack.html)
