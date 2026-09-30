# IR 수신 소프트웨어 구조와 API

## 계층

```text
FastAPI routes (app/main.py)
        ↓
capture lifecycle (app/ir/service.py)
   ↙          ↓             ↘
backend    profile        store
ir-ctl     generic /      JSON + compact + .ir
or mock    Carrier
              ↓
      protocol-neutral parser
```

- `backend.py`: 수신 장치 인터페이스와 Raspberry Pi `ir-ctl` 구현
- `mock.py`: GPIO가 없는 PC 테스트 구현
- `parser.py`: signed-microseconds 파형 검증, 프레임 분리, 비트·바이트 변환
- `profiles.py`: 모델별 제약과 해석을 플러그인처럼 등록하는 경계
- `store.py`: 원본·재송신용 파일·메타데이터를 원자적으로 저장
- `service.py`: 한 번에 하나만 수신하고 작업 상태와 취소·종료를 관리
- `main.py`: HTTP 입출력만 담당하며 하드웨어 명령을 직접 실행하지 않음

새 리모컨은 `RemoteProfile` 계약을 구현해 `ProfileRegistry`에 등록한다. Linux 장치가
바뀌면 `ReceiverBackend` 계약만 새로 구현한다. API와 저장 계층은 바꾸지 않는다.

## 캡처 흐름

1. `POST /api/v1/ir/captures`가 UUID와 `capturing` 상태를 즉시 반환한다.
2. 백그라운드에서 `ir-ctl --one-shot --receive --device=/dev/lirc0`을 실행한다.
3. 범용 파서가 pulse/space 교대, 프레임 수, 비트 수와 타이밍을 검증한다.
4. 선택한 프로필이 모델별 조건을 추가 검증한다.
5. `runtime/captures/`에 세 파일을 저장한다.

```text
<uuid>.json     메타데이터, 상태와 분석 결과
<uuid>.compact  수신한 signed microseconds 원본
<uuid>.ir       향후 ir-ctl --send에 사용할 pulse/space 형식
```

시간초과·분석 실패·사용자 취소도 JSON으로 남기므로 실패 과정을 재현할 수 있다.

## 요청 예시

```json
{
  "name": "cool-18-high",
  "profile_id": "carrier-16214-15597",
  "timeout_seconds": 90
}
```

캐리어 프로필은 각 프레임이 48비트(6바이트)인지 검증한다. 아직 완전히 해독하지
않은 필드는 의미를 추측해 버리지 않고 `payload_hex`와 원본 타이밍으로 보존한다.
