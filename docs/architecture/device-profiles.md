# 기기 프로필·등록·전송 계층

## 목적

UI가 Carrier 패킷이나 GPIO 번호를 직접 알지 않게 한다. 사용자는 기기 모델과 원하는
상태를 고르고, 모델 프로필이 패킷으로 변환하며, 전송 계층이 실제 하드웨어를 담당한다.

```text
웹 UI·장면
  → 의미 기반 명령
  → 등록 기기와 모델 프로필
  → 모델별 명령 해석기
  → DeviceTransport
      ├─ MockIrTransport       현재 PC 테스트
      ├─ IrCtlTransport        Raspberry Pi gpio-ir-tx + /dev/lirc 송신
      └─ ZigbeeIrTransport     향후 ESP32-H2
```

## 기준본과 런타임 데이터

지원 모델은 코드와 함께 검토·배포한다.

```text
device_profiles/
└─ air_conditioner/
   └─ Carrier/
      └─ CS-A061GS/
         ├─ profile.json
         ├─ commands.json
         ├─ packet.md
         ├─ captures/README.md
         └─ assets/README.md
```

- `profile.json`: 모델 식별, 기능, 파일 위치, 검증 상태
- `commands.json`: 프로그램이 읽는 구조화된 명령과 생성 규칙
- `packet.md`: 사람이 읽는 측정 근거와 미확정 항목
- `captures`: 루트 `signals/`에 있는 원본 캡처 인덱스
- `assets`: 사진·설명서 기록 위치 인덱스

미지원 모델 요청은 Pi가 생성하는 런타임 데이터이므로 배포 대상에서 분리한다.

```text
runtime/device_requests/<기기 종류>/<브랜드>/<모델>/
├─ requests/<request-id>.json
├─ photos/product-<request-id>.<ext>
├─ photos/remote-<request-id>.<ext>  # 선택
└─ manuals/manual-<request-id>.pdf   # 선택
```

제품 사진은 필수다. 리모컨 사진과 PDF 매뉴얼은 선택 사항이다. 업로드 파일은 크기,
허용 확장자와 파일 시그니처를 검사하고 원래 파일명을 저장 경로에 사용하지 않는다.

## 의미 기반 제어

냉방 24℃·강풍 요청 예시:

```json
{
  "action": "set_state",
  "power": true,
  "mode": "cool",
  "temperature_c": 24,
  "fan": "high"
}
```

LED나 풍향처럼 결과 상태를 단정할 수 없는 명령은 별도 즉시 명령으로 보낸다.

```json
{
  "action": "execute",
  "command_id": "swing_toggle"
}
```

상태형 명령만 등록 기기의 `last_desired_state`를 갱신한다. 즉시·토글 명령은 마지막
명령 기록만 갱신한다. IR은 단방향이므로 이 상태에는
`confirmation: inferred_from_ir_command`를 붙여 실제 기기 확인값과 구분한다.

## Carrier CS-A061GS 인코딩

전원 OFF, 자동·제습·송풍과 특수 기능은 실측 프레임을 사용한다. 냉방은 실측한 풍량
바이트와 온도 Gray-code 규칙을 조합한다. 17–20℃에서 규칙을 확인했지만 21–30℃는 아직
개별 캡처하지 않았으므로 API 응답에 생성 출처와 송신 미검증 경고가 포함된다.

반송파 38kHz는 판매자 자료에 근거한 값으로 계측 완료 값이 아니다. Mock 전송기는 이
구조를 검증하되 GPIO나 IR LED를 구동하지 않는다. `IrCtlTransport`는 명령의 바이트를
MSB 우선으로 펼쳐 리더, 비트 pulse/space, 끝 pulse와 프레임 간격을 `ir-ctl` 원시 송신
형식으로 만든다. 한 장치에서 동시에 두 명령을 보내지 않도록 잠그고, 실패한 송신은 등록
기기의 마지막 요청 상태로 기록하지 않는다.
