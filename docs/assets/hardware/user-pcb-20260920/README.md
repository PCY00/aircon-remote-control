# 사용자 PCB 공개용 이미지

설계 기준은 2026-09-20 사용자 설계 작업본 `artwork-current`다. 실물 촬영 자료가 아니라
검증에 사용한 설계·제조 파일의 시각화다. 이미지의 색을 실제 솔더마스크 색이나 주문 옵션으로
해석하지 않는다. 2026-09-22 원고 정리 과정에서 회로도·동박·CAM 이미지를 추가했다.

| 공개 파일 | 원본·생성 방법 | 주의사항 |
| --- | --- | --- |
| `front.png` | 작업본 `checks/3d-top.png` | 앞면 CAD 3D 렌더 |
| `back.png` | 작업본 `checks/3d-bottom.png` | 뒤집어 본 뒷면 CAD 3D 렌더 |
| `schematic.png` | `checks/schematic-svg/IR_ESP32H2.svg` → 기존 `render_svg_review.cjs`, 폭 4400px | 원본 크기로 확대해서 읽는다 |
| `copper-top.png` | `checks/final-top-copper.svg` → 같은 렌더러, 폭 2600px | F.Cu·F.SilkS·Edge.Cuts, 동박 채움 포함 |
| `copper-bottom.png` | `checks/final-bottom-copper.svg` → 같은 렌더러, 폭 2600px | B.Cu·B.SilkS·Edge.Cuts, 앞에서 투영한 방향이므로 글씨가 뒤집혀 보임 |
| `gerber-top.png` | `checks/gerber-top.png` 복사 | 실제 CAM을 Gerbonara 1.6.3으로 재읽은 앞면 시각화 |
| `gerber-bottom.png` | `checks/gerber-bottom.png` 복사 | 실제 CAM을 재읽어 뒷면에서 바라본 방향으로 표시 |

`copper-bottom.png`와 `gerber-bottom.png`는 보는 방향이 달라 좌우가 반대다. 새 배선 차이나
제조 오류를 나타내는 것이 아니다. SVG→PNG 변환과 PNG 복사는 회로도·PCB·제조 파일을 수정하지 않는다.

J1/SW1/SW2/SW3는 3D 모델 부재로 몸체가 보이지 않을 수 있다. D1의 일반적인 빨간 LED 모델은
TSAL6200의 실물 외관이나 파장·광출력을 재현하지 않는다. 모델 누락은 해당 부품의 BOM 누락을 뜻하지 않는다.

추가 이미지에는 개인정보가 들어간 파일 경로나 도면 표제란이 없는지 육안으로 확인했다.
메타데이터는 `scripts/sanitize_blog_images.py`로 검사하며, 새로운 이미지를 추가하면 다시 검사한다.

관련 글: [PCB 제작 시리즈](../../../blog/pcb-ir-node/README.md).
