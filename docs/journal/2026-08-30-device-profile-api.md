# 2026-08-30 Carrier 프로필과 Mock 제어 API

## 목표

UI 프로토타입을 실제 하드웨어 코드에 바로 결합하기 전에 Carrier CS-A061GS만 등록하고
제어할 수 있는 모델 카탈로그, 의미 기반 API와 Mock 전송 경계를 만든다. IR 송신 회로는
아직 준비되지 않았으므로 이 단계에서 GPIO를 구동하지 않는다.

## 구현

- `device_profiles/air_conditioner/Carrier/CS-A061GS/` 생성
- 캡처한 명시 명령과 냉방 Gray-code 생성 규칙을 `commands.json`으로 구조화
- 지원 모델 조회, 기기 등록, 의미 기반 명령 API 추가
- 미지원 모델의 제품 사진 필수·리모컨 사진과 PDF 선택 업로드 추가
- 등록 기기와 요청 자료를 `runtime/`에 분리 저장
- `DeviceTransport` 인터페이스와 `MockIrTransport` 추가
- Mock 송신 기록에 `hardware_output: false`를 명시
- 상태형 명령만 추정 상태를 갱신하고 토글 명령은 실행 기록만 남기도록 분리

## 디버깅과 검증

첫 전체 Ruff 실행에서 이번 코드가 아닌 기존 `scripts/convert_ir_compact.py`와
`scripts/render_terminal_capture.py`의 import 정렬 경고 2건이 발견됐다. 관련 없는 사용자
파일은 수정하지 않고 새 테스트의 import만 자동 정렬했다. `app`와 `tests` 범위 Ruff는
통과했다.

자동 테스트 결과:

```text
21 passed
```

검증 항목:

- Carrier 프로필 목록과 상세 조회
- 거실 에어컨 등록
- 냉방 24℃·강풍을 `b2 4d 3f c0 40 bf` 2프레임으로 해석
- 명시적 OFF 캡처 선택
- 미지원 프로필과 불완전 냉방 명령 거부
- 제품·리모컨 사진과 매뉴얼의 런타임 저장
- 잘못된 제품 사진 확장자 거부

## 남은 한계

- 이번 구현은 로컬에만 있으며 Raspberry Pi에는 배포하지 않았다.
- UI 프로토타입은 아직 새 API를 호출하지 않는다.
- Mock이므로 에어컨 동작은 일어나지 않는다.
- 냉방 21–30℃ 생성 패킷과 38kHz 반송파는 Step 4 실제 송신 전에 검증한다.
