# 2026-09-22 — 사용자 PCB 작업을 블로그 4편으로 정리

## 요청과 범위

사용자의 요청에 따라 설계 작업 기록을 [PCB 제작 블로그 시리즈](../blog/pcb-ir-node/README.md)로
구성했다. 기존 에어컨 IR 4편과 Zigbee/MQTT 4편을 덮어쓰지 않고 세 번째 시리즈로 분리한다.
하드웨어 기준은 2026-09-20 사용자 설계 작업본이며, 이전 `codex-revA`를 기준으로 되돌리지 않는다.

이번 작업은 게시용 문서·이미지·문서 검사 도구에 한정한다. Pi 배포, 펌웨어 변경, 회로도/PCB 수정,
제조사 업로드나 발주는 하지 않는다. ERC/DRC/CAM 수치는 기존 검증 기록을 인용하며 오늘
하드웨어 검증을 새로 실행한 것처럼 표현하지 않는다.

## 구성

1. 요구사항·부품 선정: AA 2개/USB, H2 모듈, GPIO4 IR, PCBA와 수납땜 분담.
2. 회로도 검토: 핀·패드 대조, SW1/SW2 실제 내부 접점, F1/F2/L1 패드 검토.
3. 아트워크: 원본 백업, 잠긴 배치 보존, 전원·USB·안테나·비아·라이브러리 오류 수정.
4. 주문 준비: ERC/DRC의 범위, BOM/CPL/CAM, 독립 재읽기, 주문 전 미리보기와 미측정 항목.

최종 `manufacturing/assembly/` 부품 선정 자료와 네트리스트를 교차 확인한다. 과거 개발보드의
GPIO8 또는 초기 BOM을 새 PCB의 GPIO4·TPS63802DLAT·3.3V IR 경로와 혼동하지 않게 구분한다.
문제의 원인·수정·검증·남은 한계를 각각 기술한다.

## 공개 이미지

기존 앞/뒷면 3D PNG와 터미널 75/76 TXT·PNG를 유지했다. 실제 최종 출력에서 아래 자료를
추가했고, 각 그림을 직접 열어 표시 내용과 개인 경로 노출 여부를 확인했다.

- `schematic.png`: 최종 KiCad 회로도 SVG → 폭 4400px PNG.
- `copper-top.png`, `copper-bottom.png`: 최종 동박·실크·외곽 SVG → 폭 2600px PNG.
- `gerber-top.png`, `gerber-bottom.png`: 독립 CAM 파서가 생성한 기존 PNG 복사.

SVG 변환은 기존 `scripts/hardware/render_svg_review.cjs`를 사용했다. 생성형 이미지나
가상 성공 화면을 사용하지 않는다. 이미지별 원본과 보는 방향은
[이미지 설명](../assets/hardware/user-pcb-20260920/README.md)에 보존한다.
3D 모델 누락·LED 일반 모델의 한계와 실물 사진이 아니라는 점을 본문에서도 표시한다.

## 검증 방법

`scripts/validate_pcb_blog.ps1`는 원고·목차·이미지 설명·이 기록의 UTF-8, 상대 링크 대상,
코드 블록 짝과 명백한 개인 경로·사설 주소·개인 키 표식을 읽기 전용으로 확인한다.
문장 의미·전체 보안·외부 URL·전기적 동작까지 검증하는 도구는 아니다.
기술 수치와 미완료 범위는 별도 문서 검토로 확인한다.

공개 이미지에는 `scripts/sanitize_blog_images.py`를 적용·검사한다. 새 CAD/CAM 이미지 7개
검사에서는 `PRIVATE_METADATA_COUNT=0`, `SANITIZED_COUNT=0`이었고, 추가 직후 전체 공개
이미지 112개 검사에서도 `PRIVATE_METADATA_COUNT=0`이었다. 이후 캡처가 추가되면 전체 수는 늘어난다.

독립 원고 검토에서도 최종 보고서·부품 선정·기록된 CLI 옵션과 모순되는 항목은 발견하지 못했다.
공개용 검사 기록은 [TXT](../assets/terminal/77-pcb-blog-publication-check.txt)와
[PNG](../assets/terminal/77-pcb-blog-publication-check.png)로 보존한다. 링크 검사 개수는 이 기록에
캡처 링크를 연결한 최종 원고 기준이며, 사진 수에는 이 검사 캡처도 포함한다.

최종 결과: 원고 4편을 포함한 Markdown 7개, 로컬 링크 63개, 이미지 삽입 11곳을 검사해
`ISSUES=0`이었다. 캡처를 포함한 전체 이미지 113개에서 `PRIVATE_METADATA_COUNT=0`을
확인했다. 저장된 릴리스 해시와 대조한 회로도·PCB·프로젝트 파일 3개도 변경이 없었다.

## 남은 단계

이번 결과는 게시용 원고이며 게시 서비스에 실제로 업로드한 것은 아니다. 실제 발주 시 부품 재고,
조립 옵션, 중심·회전·극성을 다시 확인해야 한다. USB 부팅·전원 전환·IR 거리·Zigbee 연결·
소비전류·배터리 수명은 보드 수령 후 검증할 항목으로 남겼다.
