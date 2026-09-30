# 사용자 PCB 아트워크 릴리스 메모

기록 기준: 2026-09-20. **상태: 사용자 검토용 시제품 제조 패키지 완료 / 실물 검증·주문 승인 아님.** Gerber/드릴 독립 재읽기도 통과했다.

## 기준 설계와 보존 조건

이번 작업은 사용자가 직접 만든 `IR_ESP32H2` 회로도·PCB를 기준으로 한다. 이전의 별도 `codex-revA` 설계가 아니다. 수정본은 `artwork-current`에서 관리하고 원본은 변경하지 않는다.

- 검증한 백업: `user-design-20260920-022829` — 254개 파일
- 이전 Rev A 보관: 같은 스냅샷의 `retired-codex-revA` — 복구 가능
- 기존 보드 외곽: 85 × 40mm
- 전기 부품: 42개 — 앞면 41개, 뒷면 BT1 1개
- 잠긴 배치 보존: BT1, D1, J1, SW3, U2의 위치·회전·면
- 실장면: BT1 뒷면, 나머지 앞면
- 원본 회로도·PCB 해시: 작업 중 변경되지 않음 확인

## 작업본 변경 내역

| 변경 | 이유 | 현재 상태 |
| --- | --- | --- |
| SW1/SW2 위쪽 패드 1/1, 아래쪽 2/2 | 실제 버튼의 내부 공통 접점에 맞춤 | 프로젝트 내부 `cypark:TS-1187A-B-A-B_XKB`에 반영 |
| 하단 중복 외곽선 5mm 제거 | 중복 선분 정리 | 전체 외곽 크기 유지 |
| 미잠금 부품을 외곽 안으로 정리 | 부품 배치·배선 준비 | 잠긴 5개는 보존 |
| 모듈 패드 내 비아 9개 → 패드 사이 텐팅 비아 4개 | 납 흡입 위험 감소 | 드릴 가장자리–패드 최소 약0.22123mm 확인 |
| 중요 전원·IR·USB 수동 배선 및 자동 배선 보완 | 민감 경로 우선 관리·전체 연결 | 최종 미연결 0건 |
| F1 패드 1.25×2.00mm, 중심±1.40mm | 최대 몸체 폭 대응 | 제조사 권장 도면이 아닌 설계상 조정 |
| F2 패드 1.00×1.90mm, 중심±1.50mm | Yenji 권장 land 적용 | 반영 완료 |
| L1 패드 0.80×1.80mm, 중심±0.80mm | Murata 권장 land 적용 | 양면 코어 동박·몸체 비아 금지 영역 반영 |
| R16 0805 표기, ESD 비-A형 데이터시트, 부품 조달 필드 | 형상·주문 정보 일치 | 반영 완료 |
| 라이브러리 저장 시 zone 좌표 변환 수정 | L1/U2 금지 영역 저장 오류 방지 | 위치 원점 정규화 후 최종 native 검사 통과 |

이 변경 이외의 사용자 배선은 가능한 범위에서 유지했다. 최종 작업본의 잠긴 5개 부품은 입력본과 정확히 일치하며 원본 파일 해시도 유지되었다. 배선·비아 항목은 402개, 비아는 38개(0.3mm 드릴 36개, 0.4mm 2개)이며 모두 텐팅 설정이다.

## 반드시 알아야 할 버튼 오류

원본 ERC는 0건이고 회로도/PCB 패드 네트 차이도 0건이었다. 그러나 XKB TS-1187A의 위쪽 A–B 단자는 내부 연결이고, 아래쪽 C–D도 내부 연결이다. 기존 풋프린트의 1/2를 EN–GND 및 BOOT–GND에 사용하면 누르지 않아도 두 신호가 접지로 단락된다. ERC는 부품 내부 접점을 풋프린트로부터 추론하지 않는다. [XKB 제조사 도면](https://datasheet.lcsc.com/datasheet/pdf/56c8799ae5193945a16a1ffbe378246a.pdf)

임시 감사용 `TS-1187A-B-A-B_XKB_2Pin`은 검증용 이름이며, 실제 프로젝트에는 원래 라이브러리 이름 `cypark:TS-1187A-B-A-B_XKB`로 수정된 접점 매핑을 저장했다. 기존 형상·패드 위치·크기는 유지했다. 다른 4단자 버튼을 대체 구매할 때도 같은 내부 접점이라고 가정하지 말고 해당 제조사 도면을 다시 확인한다.

F1/F2/L1 검토에는 [BNstar 정확한 부품 자료](https://datasheet.lcsc.com/datasheet/pdf/9805b486ee62b848d009b5edc742c366.pdf), [Yenji 제조사 land 도면](https://file.elecfans.com/web2/M00/78/08/poYBAGNoe5eAXgHvAAWgpvrl3s4691.pdf), [Murata 규격서](https://pim.murata.com/asset/pim4/inductor/J(E)TE243A-0006_PDF_INDUCTOR)를 사용했다. 수치 비교와 F1의 판단 한계는 `tmp/user-pcb-audit-20260920/passive-land-review.md`에 기록했다.

## 완료한 검증과 제조 출력

- [x] KiCad 10.0.1 native ERC 오류·경고 0건
- [x] KiCad 10.0.1 native DRC 오류·경고 0건
- [x] 미연결 0건, 회로도/PCB 일치 차이 0건
- [x] 잠긴 5개 부품 위치·회전·면 및 원본 파일 해시 보존 확인
- [x] 최종 선택 부품과 실제 패키지 정보 반영, R16 표기 및 ESD 데이터시트 정리
- [x] Gerber 9개 레이어 + job 1개 + PTH/NPTH 드릴 2개 생성(12개)
- [x] PCBA 앞면 40개 부품 / 27개 BOM 묶음으로 BOM·CPL 생성
- [x] CSV 왕복 읽기, 좌표 원점, 입력 해시 및 CAM 출력 해시 검증
- [x] 실제 검증 터미널 TXT/PNG와 앞·뒷면 3D PNG 저장, 해당 PNG 3개 메타데이터 검사 0건
- [x] Gerbonara 1.6.3 독립 재읽기: 외곽 8개 선분·85×40mm, PTH 46개(슬롯 4개 포함), NPTH 6개와 패드 중심·원점 일치

독립 검사 기록은 작업본 `checks/cam-independent.json`이다. 양면 마스크에서 비아 38개의 개방이 없고 뒷면 페이스트가 비어 있음을 확인했다. KiCad job 파일의 85.05×40.05mm 표시는 0.05mm 외곽선 두께를 포함한 경계이며 실제 가공 중심선은 85×40mm다. 별도 파서는 Excellon의 도금 유형을 unknown으로 보고했지만 원본 드릴 헤더의 Plated/NonPlated 구분을 직접 확인했다. 패드 중심 일치는 전체 개구 형상이나 실물 성능 보장을 뜻하지 않는다.

최종 검사는 프로젝트의 현재 error/warning 설정 기준이다. 비활성 검사 범위는 `checks/final-erc.json`, `checks/final-drc.json`의 `ignored_checks`를 함께 확인한다. 검사 결과와 보존 검증은 `checks/release-validation.json`에 있다. 초기 DRC의 121건 위반·68건 미연결은 수정 전 참고값이다.

조립 파일은 `manufacturing/assembly/`에 있다. BT1과 D1은 직접 납땜하므로 BOM/CPL의 PCBA 대상에서 제외했고, J1은 포함했다. 드릴·실장 원점은 `(64.5,94.0)mm`이며 CPL 좌표는 이 원점 기준이다. 출력 도구 자체의 `assembly-export.json`은 그 도구가 수행하지 않은 검사도 범위 밖으로 나열하므로, 프로젝트 전체의 최종 검증은 별도의 `release-validation.json`과 함께 읽어야 한다.

`manufacturing/assembly/README-assembly.md`의 주의사항을 주문 전에 확인한다. 특히 KiCad 원점이 실제 흡착 중심임을 보장하지 않으므로 **JLC 미리보기에서 각 부품 중심·회전·극성을 사용자가 검토해야 한다.** 현재 재고·견적·Standard PCBA/X-ray 같은 조립 조건도 주문 시 다시 확인한다. 이 패키지는 주문을 실행하거나 승인한 기록이 아니다.

## 시각 자료의 범위

3D 앞·뒷면은 배치 참고용이다. J1/SW1/SW2/SW3처럼 3D 모델이 없는 부품의 몸체는 생략될 수 있으며, 일반적인 빨간 LED 모델은 실제 TSAL6200의 외관·광학 특성을 뜻하지 않는다. 원본 CAD와 제조 도면의 치수를 우선한다.

공개용 자료: [검증 TXT](../assets/terminal/75-user-pcb-final-verification.txt), [검증 PNG](../assets/terminal/75-user-pcb-final-verification.png), [앞면 3D](../assets/hardware/user-pcb-20260920/front.png), [뒷면 3D](../assets/hardware/user-pcb-20260920/back.png). 해당 PNG 3개는 메타데이터 검사에서 `PRIVATE_METADATA_COUNT=0`을 확인했다.

## 유지한 시제품 한계

AA 2개와 USB를 전원 선택 회로로 합쳐 3.3V를 만드는 구조이며, 충전 회로는 없다. 별도의 AA 저전압 차단·전압 측정 기능은 구현되어 있지 않다. 배터리 수명 목표와 장기 방전 보호는 별도 검증·설계 과제다. 배터리 스위치를 꺼도 USB 연결 중에는 보드가 켜질 수 있다.

실물 USB 연결·부팅, 전원 전환, 대기 전류, IR 출력과 도달 거리, Zigbee 연결, 온도 상승은 아직 이 PCB에서 측정하지 않았다. PCB 소프트웨어 검사와 하드웨어 검증을 구분한다.

진행 근거: [2026-09-20 작업 기록](../journal/2026-09-20-user-pcb-artwork.md). 독립 회로 감사 자료는 프로젝트 임시 폴더 `tmp/user-pcb-audit-20260920/`에 보관한다. 공용 문서에는 개인 절대 경로와 인증 정보를 포함하지 않는다.
