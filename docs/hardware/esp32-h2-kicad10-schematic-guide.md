# KiCad 10.0.1 — AA·USB ESP32-H2 IR 노드 회로도 따라 그리기

작성: 2026-09-18. **회로도 작성 안내 초안이며 제조 승인 도면이 아니다.**

[Rev A BOM](esp32-h2-aa-usb-ir-bom.md)의 후속 안내다. 기존 Excel/JSON은 당시 초안으로
보존한다. 아래 0402 구매 후보는 아직 기존 Excel에 반영하지 않았다. 최종 제조 BOM은
검토 완료된 회로도에서 다시 출력한다. 이 문서만으로 구매·PCBA 발주하지 않는다.

신규 PCB용으로 설명하며, 기존 SuperMini GPIO8 배선·펌웨어나 Raspberry Pi는 변경하지 않았다.
H2 시제품의 카메라 발광 확인과 실제 에어컨 제어 성공은 별개다. 후자는 아직 확인하지 않았다.

## 0. 이번 설계의 범위와 비용 원칙

- ESP32-H2-MINI-1-H4S 모듈을 쓴다. SuperMini 개발보드나 ESP32-H2 단품 칩이 아니다.
- LR6 알카라인 AA 2개 직렬 또는 USB-C 5 V. 충전 회로는 넣지 않는다.
- USB와 AA는 직접 병렬 연결하지 않는다. 전원 선택 후 승강압하여 H2·IR에 3.3 V를 공급한다.
- SMD는 JLCPCB 조달 확인품을 우선하고, IR LED·배터리 홀더는 직접 납땜 대상으로 분리한다.
- 일반 신호용 저항과 작은 바이패스는 **0402 inch = 1005 metric = 1.0 × 0.5 mm**를 기본으로 한다.
  주문 화면의 `0402`와 KiCad의 `0402_1005Metric`은 이 경우 같은 크기다.
- 0201로 더 줄이지 않는다. 부품 단가·실장 비용이 반드시 더 싸지는 않으며 첫 PCB 검증도 어려워진다.
- IR 33 Ω 저항은 0.5 W급 1210, 전원 MLCC는 유효 용량을 검토한 0805/1206 후보를 유지한다.
- 가능하면 SMD는 한 면에 배치하고 같은 값은 같은 MPN을 재사용해 부품 종류 수를 줄인다.

H2의 JLC 등록품 `C47967030`은 확인 당시 **Standard PCBA 전용, X-ray 필요**였다.
Standard에서는 Basic도 feeder 비용 대상이므로 “Basic이면 실장 준비 비용이 없다”고 계산하지 않는다.
TPS2116·TPS63802를 유지한 자동 전원 전환안은 **최저가 설계로 확정한 것이 아니다**.
최종 제작 수량·재고·실장 견적을 보고 전원부 원가를 다시 비교한다.
[H2 등록품](https://jlcpcb.com/partdetail/50203214-ESP32_H2_MINI_1H4S/C47967030),
[JLC PCBA 비용](https://jlcpcb.com/help/article/pcb-assembly-price).

## 진행 순서

1. 프로젝트와 라이브러리를 준비한다.
2. USB-C 입력·데이터·ESD 부분을 그린다. **첫 화면 검토 지점**이다.
3. AA 입력·역극성 보호·USB 우선 전원 선택을 그린다.
4. 3.3 V 승강압 회로를 그린다. **전용 CAD·인덕터 조달 확정 전 PCB 배치 보류**.
5. H2 전원·BOOT·RESET·USB를 연결한다.
6. IR LED·MOSFET을 연결한다.
7. ERC → 부품·패드 대조 → PCB/DRC → JLC 조달·CPL 검토 순으로 진행한다.

처음에는 한 장의 A3 회로도에 기능별로 구역을 나눠도 된다. 회로도에서 부품 위치는
PCB의 실제 위치가 아니다. 배선 교차를 줄이기 위해 같은 이름의 net label을 사용한다.

## 1. 프로젝트와 라이브러리

1. KiCad 프로젝트 관리자에서 **파일 → 새 프로젝트**를 선택하고 이름을 `zigbee_ir_h2`로 지정한다.
2. 생성된 `.kicad_sch`를 열고 페이지 설정에서 A3를 선택한다. 기본 grid를 임의로 바꾸지 않는다.
3. 아래 순서에서 `A`는 심볼 추가, `E`는 속성, `R`은 회전, `W`는 배선, `L`은 net label이다.
   단축키를 바꿨다면 해당 메뉴를 이용한다.
4. 심볼의 속성에 `MPN`, `LCSC`, `Assembly`, `Datasheet` 필드를 기록한다.
   예: MPN=`TYPE-C-31-M-12`, LCSC=`C165948`, Assembly=`JLC`.
   `LCSC`는 사용자 정의 필드명이며 JLC 업로드 열에 나중에 매핑한다.
5. 직접 납땜할 부품은 `Assembly=Manual`로 표시한다. PCB에서 삭제하거나 완제품 BOM에서
   누락시키지 않고, **JLC 실장용 BOM/CPL만 별도 필터링**한다.

### Espressif 공식 라이브러리 설치

KiCad 10.0.1 기본 라이브러리에는 `ESP32-H2-MINI-1`을 확인하지 못했다.
Espressif 공식 애드온을 사용한다.

1. [공식 릴리스](https://github.com/espressif/kicad-libraries/releases/tag/3.2.1)에서
   `espressif-kicad-addon.zip`을 내려받는다. Source code ZIP과 다르다.
2. KiCad 프로젝트 관리자의 **Plugin and Content Manager / 플러그인 및 콘텐츠 관리자**에서
   **Install from File / 파일에서 설치**로 ZIP을 선택하고 적용한다.
3. 공식 설치 안내에 따른 라이브러리 이름은 `PCM_Espressif`다.
4. 심볼 `PCM_Espressif:ESP32-H2-MINI-1`을 선택하고 Value/MPN에
   `ESP32-H2-MINI-1-H4S`를 적는다.
5. 풋프린트도 `PCM_Espressif:ESP32-H2-MINI-1`을 선택한다. `MINI-1U`는 외장 안테나형이므로 다르다.

3.2.1 메타데이터는 KiCad 10.0.0 이상을 명시한다. 이번 검토는 공식 10.0.1 라이브러리
소스 및 제조사 애드온 대조이며, 사용자의 KiCad 10 GUI 설치·실행을 대신 완료한 것은 아니다.
[Espressif 설치 설명](https://github.com/espressif/kicad-libraries),
[KiCad 10 회로도 설명서](https://docs.kicad.org/10.0/en/eeschema/eeschema.html).

### 확인한 심볼·풋프린트 대응

| 부품/역할 | KiCad 심볼 | 풋프린트 | 비고 |
|---|---|---|---|
| H2 모듈 U1 | `PCM_Espressif:ESP32-H2-MINI-1` | `PCM_Espressif:ESP32-H2-MINI-1` | 제조사 애드온 |
| USB J1 | `Connector:USB_C_Receptacle_USB2.0_16P` | `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` | C165948 전용 |
| 전원 선택 U2 | `Power_Management:TPS2116DRL` | `Package_TO_SOT_SMD:SOT-583-8` | MPN TPS2116DRLR |
| 승강압 U3 | **별도 작성/검증 필요** | **TI DLA0010A 전용 필요** | 기본 10.0.1에 TPS63802 없음 |
| IR MOSFET Q1 | `Transistor_FET:AO3400A` | `Package_TO_SOT_SMD:SOT-23` | G1, S2, D3 |
| 역극성 보호 Q2 | `Transistor_FET:Q_PMOS_GSD` | `Package_TO_SOT_SMD:SOT-23` | Value=DMP2035U-7, G1/S2/D3 |
| USB ESD U4/U5 | `Power_Protection:TPD2EUSB30` | `Package_TO_SOT_SMD:Texas_DRT-3` | Value=TPD2EUSB30DRTR |
| 일반 저항 | `Device:R` | `Resistor_SMD:R_0402_1005Metric` | 아래 MPN별 값을 입력 |
| 작은 MLCC | `Device:C` | `Capacitor_SMD:C_0402_1005Metric` | 무극성 |
| IR 전류 제한 R15 | `Device:R` | `Resistor_SMD:R_1210_3225Metric` | 33 Ω, 0.5 W 후보 |
| IR LED D1 | `Device:LED` | `LED_THT:LED_D5.0mm` | TSAL6200, 1=K, 2=A |
| AA 홀더 BT1 | `Device:Battery` | `Battery:BatteryHolder_Keystone_2462_2xAA` | **Keystone 2462에만 적용** |

TPD2EUSB30 기본 심볼의 Datasheet 필드는 A 접미사 문서를 가리키므로 구매할
`TPD2EUSB30DRTR`의 [TI 문서](https://www.ti.com/lit/ds/symlink/tpd2eusb30.pdf)로 바꾼다.
칩의 두 채널은 보호 입력이며, 심볼 좌우 핀이 데이터의 입력→출력 경로라는 뜻이 아니다.

`TPS63802`는 2×3 mm라는 외형만 보고 일반 DFN-10을 지정하면 안 된다. DLA0010A는
서로 다른 크기의 전력 패드를 가진다. 제조사 CAD를 가져오거나 프로젝트 전용 라이브러리에
작성한 뒤 **핀 번호, 패드 치수, paste aperture**를 도면과 대조해야 한다.
이 가이드에 완성된 U3 CAD가 포함된 것은 아니다.

## 2. USB-C부터 그리기 — 지금 진행할 구역

먼저 아래 7개 부품을 배치한다. USB 전원 퓨즈와 벌크 커패시터는 다음 전원 구역에서 붙인다.

| 참조 | 수량 | 값 / 정확한 MPN | JLC |
|---|---:|---|---|
| J1 | 1 | HRO `TYPE-C-31-M-12` | [C165948](https://jlcpcb.com/partdetail/Korean_HropartsElec-TYPE_C_31_M12/C165948) |
| R1, R2 | 2 | 5.1 kΩ 1%, `0402WGF5101TCE` | [C25905](https://jlcpcb.com/partdetail/C25905) |
| R3, R4 | 2 | 22 Ω 1%, `0402WGF220JTCE` | [C25092](https://jlcpcb.com/partdetail/25835-0402WGF220JTCE/C25092) |
| U4, U5 | 2 | `TPD2EUSB30DRTR` | [C97502](https://jlcpcb.com/partdetail/TexasInstruments-TPD2EUSB30DRTR/C97502) |

모든 저항을 같은 크기로 하는 것이 아니라, 이 표의 R1–R4를 0402로 지정한다.

### 2-1. 전원과 CC

1. J1의 VBUS 핀 그룹에 `VBUS_RAW` 라벨을 붙인다. A4/A9/B4/B9가 같은 net이다.
2. GND 핀 그룹과 SH/셸을 GND에 연결한다. 첫 보드에서는 셸을 기판 GND에 연결한다.
3. `CC1 (A5) → R1 5.1 kΩ → GND`를 배선한다.
4. `CC2 (B5) → R2 5.1 kΩ → GND`를 별도로 배선한다. CC1과 CC2를 서로 묶지 않는다.
5. SBU1/A8과 SBU2/B8은 미사용이다. 각각 No Connect의 × 표시를 놓는다.

### 2-2. USB 데이터

1. `D− A7`와 `D− B7`을 같은 net `USB_DM_CONN`으로 묶는다.
2. `USB_DM_CONN → R3 22 Ω → USB_DM`으로 연결한다.
3. `D+ A6`와 `D+ B6`을 같은 net `USB_DP_CONN`으로 묶는다.
4. `USB_DP_CONN → R4 22 Ω → USB_DP`로 연결한다.
5. 나중에 `USB_DM`은 H2 모듈 **26번 패드/GPIO26**, `USB_DP`는 **27번 패드/GPIO27**로 간다.

같은 이름/번호 그룹이 심볼에서 겹쳐 있는 전원 핀은 겹친 핀을 하나씩 분리하지 않아도 된다.
반면 심볼에 따로 표시된 A/B 데이터선은 실제로 각각 연결한다. R3/R4는 PCB에서 H2 쪽에 둔다.

### 2-3. ESD는 선에 직렬로 넣지 않는다

- U4 pin 1 → `USB_DP_CONN`, pin 2 → `USB_DM_CONN`, pin 3 → GND.
- U5 pin 1 → CC1, pin 2 → CC2, pin 3 → GND.
- PCB에서는 J1에 가깝게 배치하고 GND 귀환 경로를 짧게 한다.
- U4의 pin 1에서 pin 2로 데이터가 통과하는 것이 아니다. 두 개의 독립된 보호 채널이다.

**첫 검토 체크:** CC 저항 2개 독립 / D+·D− 뒤바뀜 없음 / SBU × / VBUS와 3V3 분리 /
ESD GND 연결. 여기까지 회로도 화면을 확인하고 전원 구역으로 넘어간다.
USB-C 셸 고정 다리가 THT이므로 JLC의 커넥터 조립 범위·추가 납땜 여부도 주문 때 확인한다.
[USB-C CC 근거](https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_overview/usb_typec_hardware_guide.html),
[H2 USB 핀·저항 근거](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32h2/schematic-checklist.html).

## 3. AA 입력과 USB 우선 전원 선택

이 구역부터 퓨즈·스위치·벌크 MLCC의 정확한 JLC MPN을 추가 선정해야 한다.
회로 기능을 먼저 이해하되 `TBD`인 부품으로 PCB를 발주하지 않는다.

1. USB: `VBUS_RAW → F1 (USB PPTC 후보) → USB_5V`.
2. AA: `BT1 양극 → F2 (배터리 PPTC 후보) → SW1 (배터리 전원 스위치) → BAT_SW`.
   BT1 음극은 GND. 이 스위치로는 USB 전원이 꺼지지 않는다.
3. Q2=DMP2035U-7: **D/pin3 → BAT_SW**, **S/pin2 → BAT_PROTECTED**,
   **G/pin1 → R14 100 kΩ → GND**. 역극성 보호용으로 드레인이 배터리 입력 쪽이다.
4. C1 4.7 µF: USB_5V–GND. C2 4.7 µF: BAT_PROTECTED–GND.
5. U2 TPS2116DRL을 아래처럼 연결한다.

| U2 핀 | 연결 |
|---|---|
| 1 GND | GND |
| 2, 7 VOUT | `VSYS` — 물리 두 패드 모두 연결 |
| 3 VIN1 | USB_5V |
| 4 PR1 | R8/R9 분압 중간점 |
| 5 MODE | USB_5V |
| 6 VIN2 | BAT_PROTECTED |
| 8 ST | 사용하지 않으면 No Connect × |

R8=300 kΩ은 USB_5V→PR1, R9=100 kΩ은 PR1→GND. 공칭 USB 전환 기준 약 4 V인
USB 우선 선택 초안이다. 핀 전압·오차·전원 전환 중 강하는 별도 시험한다.
Q2의 역극성 보호와 U2의 입력 간 역류 방지는 다른 기능이다. USB로 알카라인을 충전하지 않는다.
[TI 전원 선택 회로](https://www.ti.com/lit/ds/symlink/tps2116.pdf),
[Q2 핀 및 정격](https://www.diodes.com/datasheet/download/DMP2035U.pdf).

## 4. TPS63802로 3.3 V 만들기 — CAD·조달 보류 항목 포함

U3 심볼을 별도로 준비할 때 다음 핀 표를 사용한다. `TPS63802DLAR / DLA0010A` 기준이다.

| 핀 | 이름 | 연결 초안 |
|---|---|---|
| 1 | EN | 시험용은 VSYS. 최종 저전압 차단 회로 확정 필요 |
| 2 | MODE | GND, 절전 PFM |
| 3 | AGND | GND, 조용한 FB 귀환 경로 |
| 4 | FB | R10/R11 중간점 |
| 5 | PG | 미사용 시 ×, 사용하면 풀업 필요 |
| 6 | VOUT | `3V3_REG` |
| 7 | L2 | L1 인덕터의 한쪽 |
| 8 | GND | 전력 GND |
| 9 | L1 | L1 인덕터의 반대쪽 |
| 10 | VIN | VSYS |

- L1: 0.47 µH. **U3 pin9와 pin7 사이**이며 GND로 가는 부품이 아니다.
- R10: 511 kΩ, 3V3_REG→FB. R11: 91 kΩ, FB→AGND. 공칭 약 3.308 V.
- C3: 10 µF, VSYS→GND. C9: 100 nF, VSYS→GND.
- C4: 22 µF, 3V3_REG→GND. 값만 보지 말고 DC bias 후 유효 용량을 확인한다.
- R16: 정격 검토된 0 Ω 링크로 3V3_REG→`+3V3` 부하망을 연결한다. 전류 측정 때 분리할 자리다.
- H2 입구 C5=10 µF, IR 입구 C6=22 µF도 +3V3–GND에 병렬로 추가한다.

**남은 조건:** TPS63802 전용 CAD, JLC에서 조달 가능한 정확한 인덕터와 벌크 MLCC,
저전압 차단·시동·부하 과도응답. Rev A의 XFL4015-471MEC는 LCSC 등록만 확인했으며
JLC 조달 완료품으로 취급하지 않는다. 아무 0.47 µH 인덕터로 대체하지 않는다.
입력/출력 MLCC가 바이어스·온도에서 요구 유효 용량을 만족하지 않으면 병렬 수량을 늘린다.
스위칭 루프와 AGND/전력 GND 배치는 TI 권고대로 검토한다.
[TI 핀 표·회로·패키지 도면](https://www.ti.com/lit/ds/symlink/tps63802.pdf).

## 5. H2 모듈 최소 동작 회로

**아래 숫자는 개발보드 헤더 순서가 아니라 MINI-1 모듈의 패드 번호다.**

1. U1 pad3/3V3 → +3V3. 모든 GND 패드와 중앙 GND 패드를 GND로 연결한다.
2. C7=100 nF, C5=10 µF를 모듈 전원 입구 +3V3–GND에 병렬로 둔다.
3. U1 pad8/EN: +3V3→R5 10 kΩ→EN. EN→C10 1 µF→GND.
   RESET 순간 버튼 SW3은 EN–GND에 연결한다.
4. U1 pad23/GPIO9: +3V3→R6 10 kΩ→GPIO9. BOOT 순간 버튼 SW2는 GPIO9–GND에 연결한다.
5. U1 pad22/GPIO8은 +3V3로 R7 10 kΩ 풀업한다. 다운로드 스트랩과 IR 출력을 겸용하지 않는다.
6. U1 pad26/GPIO26→USB_DM, pad27/GPIO27→USB_DP.
7. pad15/VBAT는 기본 모듈 내부에서 3V3에 연결되어 있으므로 외부 AA·5 V를 연결하지 않는다.
   기본 모듈 구성에서는 외부 배선 없이 둔다. VBAT 이름만 보고 배터리 입력으로 쓰지 않는다.
8. 이 초안의 IR_TX 후보는 **pad18/GPIO4**다. MTCK/JTAG 기능과 공유하므로 USB Serial/JTAG
   사용 전제다. 최종 핀 배정·새 펌웨어 설정은 검토 후 확정한다. 기존 GPIO8 시제품은 그대로 둔다.
9. 사용하지 않는 GPIO/NC에는 의도적인 미연결 표시를 한다. 전원·GND나 사용 신호에 ×를 넣어
   ERC 오류를 숨기지 않는다.

모듈에 안테나·RF 회로·32 MHz 크리스털이 있으므로 이를 외부에 다시 만들지 않는다.
PCB에서는 안테나 keepout을 모든 관련 구리층과 부품 배치에 적용한다.
BOOT/RESET 택트의 실제 MPN을 정한 다음 풋프린트를 정한다. 버튼을 누르기 전부터
연결된 같은 쪽 다리를 두 네트로 오인하지 않는다.
[H2 모듈 핀·내부 구성](https://documentation.espressif.com/esp32-h2-mini-1_mini-1u_datasheet_en.html).

## 6. IR 송신부

1. `+3V3 → R15 33 Ω/0.5 W → D1 TSAL6200 A(애노드, pin2)`.
2. `D1 K(캐소드, pin1) → Q1 AO3400A D(pin3)`.
3. `Q1 S(pin2) → GND`.
4. `IR_TX → R12 100 Ω → Q1 G(pin1)`.
5. `Q1 G → R13 100 kΩ → Q1 S/GND`. 풀다운은 100 Ω 저항의 **MOSFET 쪽**에 둔다.
6. C6=22 µF와 C8=100 nF는 송신부 +3V3–GND에 병렬. LED에 직렬로 넣지 않는다.

LED 전류는 GPIO가 아니라 3.3 V 전원에서 공급된다. GPIO는 MOSFET gate만 제어한다.
3.3 V, Vf=1.35 V라는 가정에서 약 59 mA, R15의 ON 구간 전력은 약 0.115 W다.
그래서 R15는 일반 0402/62.5 mW 저항과 다르게 취급한다. 0.5 W는 여유를 둔 후보이며
실제 전류·온도·송신거리 확인 전 저항을 더 낮추지 않는다.
[Vishay LED 데이터](https://www.vishay.com/docs/81010/tsal6200.pdf),
[AO3400A 핀·3.3 V 구동 근거](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf).

### 추가 선정한 작은 수동소자

JLC 등록 및 표기 규격을 확인한 후보들이다. 실시간 재고 예약·최저가 견적은 아니다.

| 값/용도 | MPN | JLC | 풋프린트 |
|---|---|---|---|
| 10 kΩ 1%, R5/R6/R7 | 0402WGF1002TCE | [C25744](https://jlcpcb.com/partdetail/C25744) | R_0402_1005Metric |
| 100 Ω 1%, R12 | 0402WGF1000TCE | [C25076](https://jlcpcb.com/partdetail/C25076) | R_0402_1005Metric |
| 100 kΩ 1%, R9/R13/R14 | 0402WGF1003TCE | [C25741](https://jlcpcb.com/partdetail/C25741) | R_0402_1005Metric |
| 100 nF 16 V X7R, C7/C8/C9 | CL05B104KO5NNNC | [C1525](https://jlcpcb.com/partdetail/C1525) | C_0402_1005Metric |
| 1 µF 25 V X5R, C10 | CL05A105KA5NQNC | [C52923](https://jlcpcb.com/partdetail/C52923) | C_0402_1005Metric |
| 33 Ω 1% 0.5 W, R15 | 1210W2F330JT5E | [C407192](https://jlcpcb.com/partdetail/395749-1210W2F330JT5E/C407192) | R_1210_3225Metric |

저항값뿐 아니라 구매 MPN·허용오차·전력 정격도 회로도에 기록한다.

## 7. 직접 납땜할 THT 구매 기준

| 부품 | 기준 구매처/주문 코드 | 적용 |
|---|---|---|
| Vishay TSAL6200 | [DigiKey 751-1204-ND](https://www.digikey.com/en/products/detail/vishay-semiconductor-opto-division/TSAL6200/1681339) | 940 nm, 5 mm, 2.54 mm lead pitch. 위 D1 풋프린트 후보 |
| Keystone 2462 | [DigiKey 36-2462-ND](https://www.digikey.com/en/products/detail/keystone-electronics/2462/303811) | AA 2개 PCB 장착 홀더. 위 BT1 전용 풋프린트 |

가격 우선이면 AliExpress에서 **동일 제조사·동일 MPN**을 비교한다. 이번에는 TSAL6200의
동일품·정품 여부와 현재 주문 가능성을 확인한 AliExpress 링크를 확보하지 못했다.
940 nm 또는 5 mm라는 설명만 같은 LED를 TSAL6200 동일품으로 취급하지 않는다.
엘레파츠도 정확한 동일품 상품 페이지를 확인하기 전 링크를 만들어 제시하지 않는다.

배터리 홀더는 더 저렴한 AA 2개 직렬 **전선형** 제품으로 바꿀 수 있다. 이 경우 제품의
실측 크기·선 굵기를 확인하고 PCB에 전선 납땜 패드/커넥터를 마련한다. Keystone 2462
풋프린트에 알리의 임의 홀더가 맞는다고 가정하지 않는다. 구매 링크/도면을 먼저 확정한다.

## 8. 제조로 넘어가기 전 체크

- [ ] USB 블록을 화면으로 검토했다. 전원과 데이터 핀을 번호로 대조했다.
- [ ] U3 DLA0010A 전용 심볼/풋프린트를 확보하고 pad 번호·치수·paste를 검토했다.
- [ ] 인덕터·퓨즈·스위치·버튼·벌크 MLCC·미확정 저항의 정확한 JLC MPN을 확정했다.
- [ ] 저전압 차단을 설계했다. 시험용 EN=VSYS를 장기 배터리 제품 완성안으로 오인하지 않는다.
- [ ] USB VBUS 인러시, 호스트 연결 시 허용 전류/열거 전 부하, 역류·과전류를 검토했다.
- [ ] KiCad ERC를 실행했다. power-input 경고는 실제 공급 경로 확인 후 필요한 곳에만 PWR_FLAG를 둔다.
- [ ] 모든 GND/전원 패드, 숨은 패드, 안테나 keepout을 확인했다.
- [ ] 제조사 핀 번호 ↔ 심볼 핀 번호 ↔ 풋프린트 패드 번호를 1:1 대조했다.
- [ ] PCB DRC, 전류 경로, 스위칭 레이아웃, USB 차동 배선, 커넥터 기구 위치를 검토했다.
- [ ] JLC 미리보기에서 부품 방향/극성/CPL 회전을 눈으로 검토했다.
- [ ] Manual 부품은 PCB·완제품 BOM에 유지하고 JLC 실장 목록에서만 제외했다.
- [ ] 첫 보드에서 전원 단독/동시/전환, 부팅, USB, 전류, IR 거리와 에어컨 제어를 시험한다.

아직 `.kicad_sch`/`.kicad_pcb`를 생성하거나 ERC/DRC를 통과시킨 결과는 없다.
지금 제공한 것은 **확인된 라이브러리·조달 후보를 이용한 단계별 작성 안내**다.

## 검증 기준과 기록

- 공식 KiCad 심볼 tag `10.0.1`, commit `7058584a0fbe9aa2f1c9ff2acf7847726ff6922c`.
- 공식 KiCad 풋프린트 tag `10.0.1`, commit `3d2b27e687a44c97f02109afb2acfeebbc8dd75f`.
- Espressif 애드온 검토 commit `dd76561812ab300351234ba6e0ec1295641796f0`, metadata 3.2.1.
- [KiCad 심볼 원본](https://gitlab.com/kicad/libraries/kicad-symbols/-/tree/10.0.1),
  [풋프린트 원본](https://gitlab.com/kicad/libraries/kicad-footprints/-/tree/10.0.1).
- [라이브러리 검사 원문](../assets/terminal/74-kicad10-library-audit.txt),
  [검사 캡처](../assets/terminal/74-kicad10-library-audit.png).
