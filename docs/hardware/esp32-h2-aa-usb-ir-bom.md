# AA 2개·USB-C ESP32-H2 Zigbee IR 노드 BOM

작성일: 2026-09-18 / Rev A / **회로 설계용 초안 — 제조 주문용 확정 BOM 아님**

PCB·배터리 제품화 후속 단계의 후보 부품표다. 기존 SuperMini USB 시제품과 구분한다.
이 문서 작성으로 기존 배선, GPIO, 펌웨어, Raspberry Pi 설정을 바꾸지 않았다.

- [Excel BOM](../../outputs/01a04ca7-bom-20260918/ESP32-H2-AA-USB-IR-BOM-RevA.xlsx): 부품·대수별 수량, 조달 정보, 설계 조건
- [기계 판독용 기준 목록](bom/esp32-h2-aa-usb-ir-rev-a.json): 33개 품목 행, 일부는 같은 규격을 묶은 행
- [후속 KiCad 10.0.1 작성 가이드](esp32-h2-kicad10-schematic-guide.md): 검증한 심볼·풋프린트, 0402 부품 선정, 단계별 연결. 아래 Rev A/Excel과는 구분되는 후속 검토이며 제조 BOM은 회로 확정 후 다시 출력한다.
- 수량은 노드 1대 기준이다. Excel `BOM!B3`에서 제작 대수를 바꾸면 총수량이 바뀐다.
- MOQ, 실장 손실분, 예비 부품, PCB, 케이스, 배송·세금은 별도다. 가격을 확인하지 못한 항목을 0원으로 계산하지 않았다.

## 기본 조건

- 전원: 일반 LR6 알카라인 AA 1.5 V 2개 직렬 또는 USB-C 5 V. 충전 기능 없음.
- MCU: `ESP32-H2-MINI-1-H4S`. 모듈 내부의 RF 회로, PCB 안테나, 32 MHz 크리스털, 플래시를 활용한다.
- IR: `TSAL6200` 1개, `AO3400A` 로우사이드 구동. H2와 IR은 모두 안정화된 3.3 V를 사용한다.
- USB-C는 전원과 네이티브 USB Serial/JTAG 다운로드용이다. USB-UART IC는 넣지 않는다.
- 자동 USB 우선 선택을 포함한 안이다. 최저가 BOM 또는 배터리 수명 최적화 완료안이라는 의미는 아니다.
- 14500 리튬이온 셀, 리튬 충전기, 5 V 직결 모듈 전원은 이 설계에 사용하지 않는다.

## 핵심 선정 부품

| 역할 | 부품 | 개/대 | 조달 코드 | 확인 범위 |
|---|---|---:|---|---|
| Zigbee 모듈 | ESP32-H2-MINI-1-H4S | 1 | C47967030 | JLC 등록, Standard 전용·X-ray 필수 |
| USB/AA 전원 선택 | TPS2116DRLR | 1 | C3235557 | JLC 등록, 역류 차단 기능 |
| 3.3 V 승강압 | TPS63802DLAR | 1 | C2845237 | JLC 등록, 저부하 PFM 사용 후보 |
| DC-DC 인덕터 | XFL4015-471MEC, 0.47 µH | 1 | C18221164 (LCSC) | LCSC 등록; JLC 조달 미확인 |
| IR LED 스위치 | AO3400A | 1 | C20917 | JLC 등록; N채널 |
| AA 역극성 보호 | DMP2035U-7 | 1 | C110499 | JLC 등록; P채널 |
| IR LED | TSAL6200 | 1 | C55528 | THT, 직접 납땜 후보 |
| USB-C | HRO TYPE-C-31-M-12 | 1 | C165948 | 데이터 지원 16핀; 전용 풋프린트 확인 |
| 데이터/CC ESD | TPD2EUSB30DRTR | 2 | C97502 | 각 2채널; D+/D−와 CC1/CC2 보호 후보 |
| AA 2개 홀더 | Keystone 2462 | 1 | 별도 조달 | 기구 치수 확정 전 후보 |

위 C 코드는 확인한 제조사·부품번호에만 대응한다. 판매처의 동명 호환품, 접미사 변경품,
다른 패키지를 자동 대체하지 않는다. JLC/LCSC 등록 확인은 현재 재고 확보나 견적 확정과 다르다.
TSAL6200의 JLC 페이지에는 wave soldering과 지그 필요가 표시된다. LED와 배터리 홀더를
직접 납땜하는 방식과 일괄 조립 견적을 비교한다.

## 저항·커패시터와 기타 부품

아래는 전기적 규격 후보다. 정확한 제조사 MPN·JLC 코드는 회로/기구 검토 후 선정해야 한다.
MLCC는 같은 표시 용량이어도 전압 인가 후 유효 용량이 다를 수 있다.

| 품목 | 규격 | 개/대 | 위치 / 목적 |
|---|---|---:|---|
| USB PPTC | hold 0.5 A, 6 V 이상 | 1 | USB 입력, 저항·온도 특성 미확정 |
| AA PPTC | hold 1 A, 6 V 이상 | 1 | 배터리 단락 보호, 낮은 직렬 저항 필요 |
| 배터리 전원 스위치 | SPST/SPDT, 1 A @5 V DC 이상 | 1 | 배터리만 차단; USB 연결 시 동작 유지 |
| 순간동작 버튼 | NO 택트 | 2 | BOOT, RESET |
| CC 저항 | 5.1 kΩ ±1%, 0603 | 2 | CC1/CC2 각각 GND |
| USB 데이터 저항 | 22 Ω ±1%, 0603 | 2 | GPIO26/27 근처, 최초 후보 |
| 풀업 저항 | 10 kΩ ±1%, 0603 | 3 | EN, GPIO9, GPIO8 |
| USB 임계 상단 저항 | 300 kΩ ±1%, 0603 | 1 | TPS2116 PR1 분압 |
| 100 kΩ 저항 | ±1%, 0603 | 3 | PR1 하단, IR 게이트 풀다운, 역극성 보호 Gate |
| DC-DC FB 상단 | 511 kΩ ±1%, 0603 | 1 | 3.3 V 설정 |
| DC-DC FB 하단 | 91 kΩ ±1%, 0603 | 1 | 3.3 V 설정 |
| IR 게이트 직렬 | 100 Ω ±1%, 0603 | 1 | MOSFET Gate |
| IR LED 직렬 | 33 Ω ±1%, 0.5 W 이상 | 1 | 1210 후보, 3.3 V 전용 시작값 |
| 입력 커패시터 | 4.7 µF, 16 V, X7R/X5R | 2 | USB 입력·AA 보호 후 입력 |
| 전원 커패시터 | 10 µF, 10 V, X7R/X5R | 2 | 승강압 입력·H2 모듈 입구 |
| 출력 커패시터 | 22 µF, 10 V, X7R/X5R | 2 | 승강압 출력·IR 부하 가까이 |
| 바이패스 | 100 nF, 16 V 이상, X7R | 3 | H2·IR·승강압 입력 |
| EN 커패시터 | 1 µF, 10 V, X7R/X5R | 1 | EN 지연 |
| 전류 측정 분리 링크 | 0 Ω, 정격 1 A 이상 | 1 | 0805 후보 |
| 알카라인 건전지 | LR6 AA 1.5 V | 2 | 동일 종류 새 셀 |

예비 자리는 배터리 측정 분압/필터 및 상태 LED다. 현재 수량 0(DNP, 미실장)이며,
값이 확정되거나 회로가 검증된 것으로 취급하지 않는다. 상시 전원 표시 LED는 기본 제외한다.
전원·GND·EN·GPIO9·USB·IR 신호·배터리 전류 측정 패드는 PCB에 마련한다. 빈 패드는 구매 부품이 아니다.

## 전원 설계 근거

USB 5 V와 역극성 보호된 AA 전원을 TPS2116에서 선택하고, TPS63802에서 3.3 V로 안정화한다.
TPS2116의 VIN1에는 USB, VIN2에는 AA, MODE에는 VIN1을 연결하는 우선 모드가 후보다.
PR1에 300 kΩ/100 kΩ 분압을 사용하면 공칭 전환점은 약 4.0 V다. 비교기·저항 오차와
히스테리시스, 케이블 강하에 따른 실제 전환을 확인해야 한다. USB와 AA 양극을 직결하지 않는다.

TPS63802는 1.3–5.5 V 동작 범위지만 **시동에는 1.8 V 초과 입력이 필요**하다.
TPS2116은 1.6 V 이상이며 배터리·퓨즈·스위치·MOSFET 전압 강하도 있으므로, 처음에는
AA 팩의 부하 전압 2.0 V를 시험 하한 가정으로 둔다. 제조사가 보장한 배터리 사용 하한이라는 뜻은 아니다.

출력 설정은 제조사 3.3 V 예제의 511 kΩ/91 kΩ를 따른다. 계산상
`0.5 × (1 + 511/91) ≈ 3.308 V`이며, 실제 정확도는 기준전압·저항 오차에 좌우된다.
하단 저항은 제조사 지침상 100 kΩ 이하로 둔다. MODE=LOW(PFM)를 기준으로 하고,
인덕터 포화전류·MLCC 유효 용량·배선 루프 면적은 참조 설계와 실측으로 확인한다.

H2 모듈과 IR이 동시에 동작할 때를 고려해 3.3 V 0.5 A급 과도 부하를 검토한다.
이는 평균 소모량이 아니다. 입력 2.0 V, 효율 85%라는 **가정**에서 출력 3.3 V/0.5 A라면
입력 전류는 약 0.97 A이므로, AA 내부저항·퓨즈·접점을 포함한 전압 강하가 중요하다.
최종 펌웨어의 실제 동시 피크를 측정해 이 예산을 조정한다.

Q2는 배터리 역극성 보호용이며 U2의 USB 역류 차단 기능과 대체 관계가 아니다.
P채널 하이사이드 보호 방향과 바디 다이오드를 회로도에서 검토해야 한다.
PPTC는 즉시 동작하는 전자식 전류 제한기가 아니며 동작 온도·트립 시간·정상 저항을 확인한다.

**장기 무인 사용을 위한 저전압 차단은 아직 미완성이다.** 배터리 전압 측정만으로 차단을
보장하지 않는다. 감독 IC 또는 적절한 래치/전원 차단 회로의 필요성을 회로 설계 단계에서 결정한다.
USB가 연결된 상태, 배터리만 있는 상태, OFF 상태에서 ADC로 역급전되지 않도록 해야 한다.

## IR 전류 및 GPIO

3.3 V 공급, LED Vf=1.35 V 가정, MOSFET 전압 강하를 생략하면:

- `I ≈ (3.3 − 1.35) / 33 ≈ 59 mA`
- 저항 ON 구간 전력 `≈ (3.3 − 1.35)² / 33 ≈ 0.115 W`
- 이는 명목 계산이다. LED Vf=1.35 V는 데이터시트의 특정 시험 조건 값으로, 약 60 mA에서의 보장값이 아니다.
- 38 kHz·약 1/3 duty를 시작점으로 삼되 주파수·전류·온도·실제 거리를 측정한다.
- 0.5 W급 저항은 여유를 둔 후보이며 패키지 이름만으로 전력 정격을 판단하지 않는다.
- 광출력 확대를 위해 저항을 낮추거나 LED를 추가하는 것은 별도 전류·열 검증 이후다.

현재 SuperMini 실험은 **GPIO8에서 카메라 발광 확인**까지이며 H2의 실제 에어컨 OFF 성공은
확인되지 않은 상태다. 이 신규 PCB에서는 GPIO8/9의 부트 스트랩과 IR 게이트 풀다운이
충돌하지 않도록 비스트랩 핀 사용을 검토한다. GPIO 번호는 회로도 단계에서 확정하며,
이 BOM을 보고 기존 보드 배선을 바꾸지 않는다.

## 배터리 수명과 부품비

TPS63802의 동작 대기전류 11 µA, TPS2116의 1.32 µA는 각 데이터시트의 전형값이며
장치 전체 소비전류가 아니다. FB 분압, H2 수면·폴링, 각 누설전류·변환 효율·IR 송신도
포함해야 한다. 서로 다른 전원 레일의 전류를 단순 합산해 수명을 보장하지 않는다.

Zigbee SED는 주기적으로 부모 장치에 대기 명령을 확인한다. 폴링 주기·응답 지연·메시지
보관시간을 함께 검증한다. 이 BOM만으로 AA 2개 6개월~1년을 보장하지 않는다.

전원부 IC와 Coilcraft 인덕터는 값이 싼 것만을 우선한 조합이 아니다. 주문 수량을 정한 뒤
전체 견적을 확인한다. 원가가 높으면 우선 전원 자동 선택을 유지할지, 더 저렴한 동등
인덕터/전원 IC를 검증할지 비교한다. 어떤 대체든 풋프린트·리플·대기전류·시동 조건을 재검토한다.

## PCB 제작 전 남은 일

1. 현재 H2 보드에서 IR 실동작과 Zigbee 연결을 검증한다.
2. 회로도 작성 및 핀 배정, ERC, EN·BOOT·USB·전원 경로를 검토한다.
3. 스위치·퓨즈·수동소자의 정확한 MPN, 패키지와 조달을 확정한다.
4. 저전압 차단·배터리 감지·ESD/과전압 보호의 범위를 확정한다.
5. 안테나 keepout, 접지, 승강압 전류 루프, USB 배선과 케이스/홀더 크기를 검토한다.
6. 모든 전원 조합과 전환, 저전압 재시동, 부하 순간 변동, 역류·누설을 실측한다.
7. 주문 수량별 부품·Standard PCBA·X-ray·지그·배송 포함 견적 및 재고를 확인한다.
8. 최종 BOM과 위치 파일(CPL)을 회로/PCB에서 다시 내보낸다. 현재 임시 회로기호를 그대로 주문에 사용하지 않는다.

## 자료

제조사 사양을 전기적 근거로 사용하고 JLC/LCSC는 주문 코드 확인에 사용했다. 양쪽의
사양 표기가 다르면 제조사 최신 데이터시트를 우선한다. BOM Excel의 구매 정보 시트에
행별 출처를 기록했다.

- [Espressif H2 모듈 데이터시트](https://documentation.espressif.com/esp32-h2-mini-1_mini-1u_datasheet_en.html)
- [Espressif H2 하드웨어 지침](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32h2/schematic-checklist.html)
- [Espressif USB-C 하드웨어 지침](https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_overview/usb_typec_hardware_guide.html)
- [TI TPS2116](https://www.ti.com/lit/ds/symlink/tps2116.pdf)
- [TI TPS63802](https://www.ti.com/lit/ds/symlink/tps63802.pdf)
- [Coilcraft XFL4015-471](https://www.coilcraft.com/en-us/products/power/shielded-inductors/molded-inductor/xfl/xfl4015/xfl4015-471/)
- [Vishay TSAL6200](https://www.vishay.com/docs/81010/tsal6200.pdf)
- [AOS AO3400A](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf)
- [Diodes DMP2035U](https://www.diodes.com/datasheet/download/DMP2035U.pdf)
- [TI TPD2EUSB30](https://www.ti.com/product/TPD2EUSB30)
- [Keystone AA 홀더](https://beta.keyelco.com/product.cfm/product_id/1027/checkStock/1)
- [Zigbee SED 폴링](https://docs.silabs.com/zigbee/9.0.0/zigbee-concepts-network/end-devices)
