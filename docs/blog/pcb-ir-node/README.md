# ESP32-H2 Zigbee IR 리모컨 PCB 만들기 — 블로그 4편

개발보드와 브레드보드에서 실험하던 IR 송신 회로를 전용 PCB로 옮기는 과정을 정리했다.
부품을 고르는 이유부터 회로도 검토, 배치·배선, 제조 파일 확인까지 연결해서 읽는 시리즈다.

**원고 정리일은 2026-09-22, 설계·검사 결과의 기준일은 2026-09-20이다.**
현재 결과물은 사용자 검토용 시제품 제조 패키지다. JLCPCB 발주나 실물 동작 검증을
완료했다는 뜻은 아니며, 이번 글 작성으로 회로·펌웨어를 다시 수정하지 않았다.

## 읽는 순서

| 편 | 게시용 본문 | 이번 편에서 다루는 질문 |
| --- | --- | --- |
| 1 | [AA 배터리와 USB로 쓰는 Zigbee IR 노드: 요구사항과 부품 선정](01-requirements-and-parts.md) | 어떤 보드를 만들고, 왜 이 부품을 골랐나? |
| 2 | [KiCad 회로도 검토: ERC가 놓친 버튼 접점 오류](02-kicad-schematic-review.md) | 회로 연결과 실제 부품의 핀·패드는 어떻게 대조하나? |
| 3 | [85×40mm PCB 아트워크: 배치 의도를 지키며 배선하기](03-pcb-layout-and-routing.md) | 안테나, 전원, USB, 배터리 홀더를 어떻게 배치했나? |
| 4 | [JLCPCB 주문 준비: BOM·CPL·Gerber를 다시 검증하기](04-jlcpcb-manufacturing-checks.md) | 파일을 만들었다는 것과 주문해도 된다는 것은 어떻게 다른가? |

앞선 [에어컨 원격 제어 시리즈](../README.md), [Zigbee/MQTT 확장 시리즈](../zigbee-mqtt/README.md)와
별도인 PCB 제작 시리즈다. 이 네 편이 작성됐다고 앞선 Zigbee Step 4의 실기 검증까지
완료된 것으로 보지는 않는다.

## 이 시리즈에서 쓰는 기준본

사용자가 작성한 `IR_ESP32H2` 회로도와 PCB를 백업하고 `artwork-current` 작업본에서 정리한
결과를 사용한다. 이전 `codex-revA`는 복구 가능하게 별도 보관한 과거 설계이며 이번 글의
부품표·배선 기준이 아니다. 초기 BOM 문서의 값보다 최종 프로젝트와 제조용 부품표를 우선한다.

| 구분 | 현재 기록 |
| --- | --- |
| 설계 도구 | KiCad 10.0.1 |
| 보드 | 85×40mm, 2층, 안테나 쪽 외곽 절개 유지 |
| 실장 | 전기 부품 42개: 앞면 41개, 뒷면 배터리 홀더 BT1 1개 |
| 조립 분담 | PCBA 앞면 40개 / BT1·D1 직접 납땜 예정 |
| 새 PCB IR 출력 | GPIO4 — 이전 개발보드 GPIO8과 다름 |
| 전원 | AA 2개 또는 USB 입력 → 전원 선택 → 3.3V, 충전 기능 없음 |
| 소프트웨어 검사 | 현재 활성화한 ERC·DRC 기준 오류/경고 0, 미연결·회로도 일치 차이 0 |
| 미완료 | JLC 조립 미리보기 승인·발주·수령·실물 테스트·배터리 수명 측정 |

## 이미지와 실행 증거

본문에는 아래 자료를 연결했다. 게시 플랫폼에 옮길 때는 각 이미지를 업로드하고 상대 링크를
해당 플랫폼의 주소로 바꾼다. 회로도처럼 글씨가 작은 그림은 원본 크기 확대 링크도 유지한다.

| 자료 | 용도와 구분 |
| --- | --- |
| [앞면 3D](../../assets/hardware/user-pcb-20260920/front.png) · [뒷면 3D](../../assets/hardware/user-pcb-20260920/back.png) | CAD 렌더링. 실물 사진 아님 |
| [회로도](../../assets/hardware/user-pcb-20260920/schematic.png) | 저장된 최종 회로도의 KiCad SVG 출력에서 생성 |
| [앞면 동박](../../assets/hardware/user-pcb-20260920/copper-top.png) · [뒷면 동박](../../assets/hardware/user-pcb-20260920/copper-bottom.png) | KiCad 레이어 출력. 뒷면은 보드 위에서 투영한 좌표 방향 |
| [Gerber 앞면](../../assets/hardware/user-pcb-20260920/gerber-top.png) · [Gerber 뒷면](../../assets/hardware/user-pcb-20260920/gerber-bottom.png) | 실제 제조 파일을 별도 파서로 읽은 시각화 |
| [최종 검사 PNG](../../assets/terminal/75-user-pcb-final-verification.png) · [TXT](../../assets/terminal/75-user-pcb-final-verification.txt) | 당시 실행 결과를 민감정보 제거 후 이미지로 렌더링한 터미널 기록 |
| [제조 파일 출력 PNG](../../assets/terminal/76-user-pcb-cam-export.png) · [TXT](../../assets/terminal/76-user-pcb-cam-export.txt) | 당시 실행 명령과 결과. 새로 성공한 것처럼 만든 예시 출력 아님 |

3D 모델이 없는 J1/SW1/SW2/SW3의 몸체는 생략될 수 있다. 빨간 LED 모델도 실제 TSAL6200의
외관·광학 특성을 나타내지 않는다. 제조 판단은 회로도·풋프린트·제조 파일을 기준으로 한다.
이미지의 유래와 표시 방향은 [이미지 설명](../../assets/hardware/user-pcb-20260920/README.md)에 남겼다.

## 게시 전 마지막 확인

- [ ] 이미지와 글 링크를 블로그에 업로드한 실제 주소로 교체한다.
- [ ] CAD·BOM·CPL을 독자에게 배포할 경우 **동일한 검증본을 한 묶음으로** 첨부하고, 외부 라이브러리의 배포 조건을 확인한다.
- [ ] 가격·재고·PCBA 옵션은 주문 시점에 다시 확인한다. 본문의 선정 기록은 실시간 견적이 아니다.
- [ ] DRC 0을 무결점·인증·실물 성공으로 표현하지 않는다. 비활성 검사와 남은 검증을 함께 남긴다.
- [ ] 기기 고유 식별자·사설 주소·계정·절대 개인 경로가 새 캡처에 포함되지 않았는지 확인한다.
- [ ] 추가한 사진을 포함해 `python scripts/sanitize_blog_images.py docs/assets/`가 `PRIVATE_METADATA_COUNT=0`인지 확인한다.

이번 공개용 이미지에는 개인 메타데이터가 없음을 검사했다. 검사 결과와 원고 링크 확인은
[원고 정리 기록](../../journal/2026-09-22-pcb-blog-series.md)에 남긴다.

## 실물이 도착하면 이어 쓸 내용

보드 외관·실장 방향 검사, BT1/D1 수납땜, 제한된 전원에서 초기 기동 확인, GPIO4 펌웨어 적용,
USB/배터리 전원 동작, IR 파형·거리, Zigbee 통신, 대기·송신 전류와 장기 수명을 추가로 기록한다.
이 항목들은 **다음 실험의 계획**이며 현재 완료한 결과가 아니다.

근거 문서: [설계 작업 기록](../../journal/2026-09-20-user-pcb-artwork.md),
[검토용 릴리스 메모](../../hardware/user-pcb-release-notes.md).
