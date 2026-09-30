# ESP32-H2 USB 전원 Zigbee IR 시제품

## 현재 필요한 부품

| 부품 | 규격 | 수량 |
|---|---|---:|
| MCU | `ESP32-H2 SuperMini`, 18핀 범용 보드 | 1 |
| IR LED | Vishay `TSAL6200`, 940 nm, 5 mm | 3 |
| MOSFET | `AO3400A`가 실장된 Breakout 또는 SOT-23-to-DIP 어댑터 | 2 |
| 최초 시험 저항 | 47 ohm, 0.5 W | 3 |
| 출력 강화 비교 저항 | 39 ohm, 0.5 W | 3 |
| Gate 직렬 저항 | 100 ohm, 0.25 W | 3 |
| Gate 풀다운 | 100 kohm, 0.25 W | 3 |
| 전원 버퍼(출력 확장 시) | 47~100 uF, 6.3 V 이상 | 1 |
| 바이패스 | 100 nF 세라믹 | 1 |
| 조립 | 브레드보드와 점퍼선 | 1세트 |
| Pi Coordinator | SONOFF `ZBDongle-P`와 차폐 USB 2.0 연장선 | 각 1 |

배터리, TP4056, MCP1700, TPS63031과 외부 5 V 어댑터는 이번 시험에 필요 없다.

## 회로

```text
ESP32-H2 DevKit USB-C
          │
          ├── 보드 내부 3.3 V → ESP32-H2
          │
          └── 보드 5V 핀 ── 47 ohm/0.5 W ── TSAL6200 Anode(+)
                                                   Cathode(-)
                                                        │
                                               AO3400A Drain
                                               AO3400A Source ── GND

ESP32-H2 GPIO5 ── 100 ohm ── AO3400A Gate
                                      │
                                   100 kohm
                                      │
                                     GND

보드 5V ── 100 nF ── GND

[LED를 늘리거나 전원 문제가 확인될 때 추가]
보드 5V ── 47~100 uF ── GND
```

전해 커패시터는 극성이 있다. 추가할 경우 `+`를 5 V, `-`를 GND에 연결한다.

## 개발보드의 콘덴서와 외부 부하

실제 사용할 보드는 Espressif의 공식 `ESP32-H2-DevKitM-1`이 아니라 18핀
`ESP32-H2 SuperMini`다. SuperMini는 여러 판매자가 같은 이름과 비슷한 기판으로
판매하는 범용 보드이며, Espressif가 회로와 부품표를 관리하는 공식 개발보드가 아니다.
확인 가능한 자료에서도 5 V 핀과 USB-C 전원, 3.3 V LDO, 배터리 충전 회로의 존재는
확인되지만 5 V 레일 커패시터의 정확한 값과 실장 여부는 판매 버전마다 보증되지 않는다.
따라서 공식 DevKitM-1의 `20 uF + 0.1 uF` 값을 이 보드에 적용하지 않는다.

TSAL6200의 순방향 전압은 100 mA에서 보통 1.35 V, 최대 1.6 V다. AO3400A는
`VGS=2.5 V`에서도 `RDS(on)` 최대 48 milliohm이므로, 5 V와 47 ohm을 사용한 LED 한
분기의 순간 전류는 대략 다음 범위다. 실제 보드 5 V는 USB 케이블과 쇼트키 다이오드
전압 강하 때문에 이보다 조금 낮을 수 있다.

```text
I ≈ (5.0 V - 1.35 V) / 47 ohm ≈ 78 mA
```

38 kHz, 1/3 duty에서 LED가 켜지는 한 구간은 약 8.8 us다. 이 전류는 TSAL6200의
연속 전류 정격 100 mA보다 낮고 정상 USB 전원이 공급하기에 작다. 한편 AO3400A의 빠른
스위칭 에지가 긴 점퍼선에 잡음을 만들 수 있으므로, **SuperMini 시험에서는 외부
100 nF 세라믹을 IR LED/MOSFET 분기의 5 V와 GND 사이에 가깝게 장착한다.**

IR LED 한 개와 47 ohm 구성에는 `220 uF`가 필요하지 않다. USB 5 V에 큰 커패시터를
직접 추가하면 연결 순간 충전 전류만 커지므로 첫 시험에서는 사용하지 않는다. LED를
두 개 이상으로 늘리거나 송신 때 재부팅·USB 끊김·Zigbee 불안정이 측정되면 먼저
`47~100 uF`를 추가한다. 보유한 `220 uF`는 이런 문제가 실제 확인되고 더 작은 벌크
커패시터가 없을 때만 시험용으로 사용한다.

외부 커패시터는 회로를 성립시키는 부품이 아니라, 외부 MOSFET이 38 kHz로 IR LED
부하를 끊을 때 배선 인덕턴스와 전원 임피던스로 생기는 변동을 줄이는 보강 부품이다.

다음 조건에서는 MOSFET과 LED 가까이에 벌크 커패시터를 추가한다.

- 송신할 때 보드가 재부팅되거나 USB 로그가 끊김
- Zigbee 연결이 불안정해짐
- 점퍼선이 길거나 IR LED를 두 개 이상 병렬 분기로 늘림
- 오실로스코프 측정에서 5 V 레일 변동이 확인됨

100 nF 세라믹은 극성이 없고 빠른 에지를 줄이는 역할이다. 전해 커패시터는 더 긴 전류
펄스의 전원 버퍼 역할이다. 최종 PCB에서도 부하 가까이에 100 nF를 두고, LED 수와 전원
배선의 실제 측정값에 따라 47~100 uF 벌크 용량을 결정한다.

## 저항 선택

완충 배터리가 아니라 USB 5 V를 사용하므로 이전의 33 ohm 기준을 그대로 쓰지 않는다.

- 47 ohm: 약 70~80 mA 수준의 안전한 최초 시험값
- 39 ohm: 실제 동작 확인 후 출력 거리를 늘리는 기본 후보
- 33 ohm 이하: 실제 전류를 측정하기 전에는 사용하지 않음

TSAL6200 한 개로 먼저 시험한다. 두 개를 사용할 때는 LED마다 저항을 하나씩 사용하고
MOSFET만 공유한다.

```text
5V ── 47 ohm ── LED1 ──┐
                        ├── AO3400A Drain
5V ── 47 ohm ── LED2 ──┘
```

## 핀 선택

- IR 출력: GPIO5
- MOSFET Source와 ESP32-H2 GND는 공통
- GPIO8: 보드 RGB LED이므로 피함
- GPIO9: BOOT 핀이므로 피함
- GPIO13: SuperMini의 파란 LED와 연결되어 있어 피함

## 전원 주의

- USB와 별도 5 V 전원을 동시에 연결하지 않는다.
- IR LED를 GPIO나 5 V에 저항 없이 직접 연결하지 않는다.
- AO3400A Gate 풀다운 100 kohm을 생략하지 않는다.
- 최초에는 IR LED 한 개와 47 ohm으로 시험하고 100 nF만 부하 가까이에 연결한다.
- MOSFET Breakout의 G/D/S 표기는 제품마다 배치가 다를 수 있으므로 확인한다.

## 최초 시험 순서

1. ESP32-H2를 USB로만 켜고 펌웨어 다운로드와 로그를 확인한다.
2. MOSFET Gate 풀다운과 100 ohm Gate 저항을 먼저 연결한다.
3. 100 nF를 IR 부하 가까이 연결하고 47 ohm과 TSAL6200 한 개를 5 V 레일에 연결한다.
4. RMT로 약 38 kHz, 약 1/3 Duty 파형을 송신한다.
5. 에어컨 수신부 가까이에서 실제 반응을 확인한다.
6. 재부팅·USB 끊김·Zigbee 불안정이 있으면 47~100 uF를 부하 가까이에 추가한다.
7. 성공 후 39 ohm 또는 LED 두 개 구성을 비교하고, LED를 늘릴 때는 벌크 커패시터도 추가한다.
8. IR 단독 성공 후 Zigbee Coordinator와 명령 전달을 연결한다.

## 공식 참고 자료

- [ESP32-H2 SuperMini 핀과 보드 정보](https://www.espboards.dev/esp32/esp32-h2-super-mini/)
- [동일 형상 SuperMini 보드 조사와 회로도 입수 한계](https://medium.com/@androidcrypto/esp32-h2-super-mini-small-form-factor-big-impact-lora-epaper-environment-sensor-and-battery-bcd469ee633a)
- [Espressif ESP32-H2 하드웨어 전원 설계 지침](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32h2/schematic-checklist.html)
- [Vishay TSAL6200 데이터시트](https://www.vishay.com/docs/81010/tsal6200.pdf)
- [AOS AO3400A 제품 사양](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a)
