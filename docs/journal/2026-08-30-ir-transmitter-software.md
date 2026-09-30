# 2026-08-30 Step 4 IR 송신 소프트웨어

## 출발점과 증상

사용자가 5V IR 송신 모듈과 P2N2222A 배선을 준비한 뒤 UI 명령이 동작하지 않는다고
보고했다. Raspberry Pi를 변경하지 않고 SSH로 읽기 전용 상태를 확인했다.

- 사용자 단위 `aircon-controller` 서비스는 enabled·active였다.
- 서비스는 의도한 대로 Tailscale IPv4의 8001에만 리스닝했다.
- `/api/v1/ir/transmitter`는 `mock-ir`, `hardware_output=false`를 반환했다.
- 기존 `/dev/lirc0`는 raw IR 수신만 가능하고 송신 기능은 없었다.
- `/boot/firmware/config.txt`에는 `gpio-ir-tx` 오버레이가 없었다.

따라서 UI와 명령 해석 문제는 아니며, 성공 응답은 Mock 기록 성공일 뿐 실제 광출력을
의미하지 않았다. 시스템 서비스 상태를 처음 조회했을 때 inactive였던 이유는 앱이 사용자
서비스로 설치돼 있었기 때문이다. Pi 내부 127.0.0.1 요청 실패도 Tailscale 주소 전용 바인딩의
의도한 결과였다.

## 로컬 구현

`app/devices/transport.py`에 `IrCtlTransport`를 추가했다.

1. `ir-ctl` 실행 파일과 설정된 `/dev/lirc` 장치 존재 확인
2. `ir-ctl --features` 결과에서 raw 송신 지원 확인
3. Carrier 프로필의 6바이트 프레임을 MSB 우선 bit로 변환
4. 리더 pulse/space, bit pulse, 0/1 space, stop pulse와 프레임 간격 생성
5. 임시 ASCII 송신 파일을 만들어 셸 없이 `ir-ctl --send` 실행
6. 동시 송신을 잠금으로 직렬화하고 최근 100건만 메모리에 기록
7. 장치 없음은 HTTP 503, 실행 실패·제한 시간 초과는 HTTP 502로 반환
8. 송신이 실패하면 등록 기기의 마지막 요청 상태를 갱신하지 않음

개발 PC 기본값은 계속 `mock`이다. 운영 서비스에는 다음 환경을 명시한다.

```text
AIRCON_IR_TRANSPORT=ir-ctl
AIRCON_IR_TRANSMITTER_DEVICE=/dev/lirc0
AIRCON_IR_SEND_TIMEOUT=5
```

오버레이 적용 전에는 `/dev/lirc1`을 후보로 두었으나 실제 재부팅 결과 `/dev/lirc0`이 송신,
`/dev/lirc1`이 수신 장치로 열렸다. 모든 `/dev/lirc*`의 기능을 조회한 결과로 운영 설정을
`/dev/lirc0`으로 정정했다.

## 파형 직렬화 근거

원본 캡처는 리더 뒤 48개의 데이터 bit가 있고 마지막 데이터 space 뒤에 stop pulse가 온다.
반복 프레임은 stop pulse 다음 약 5.15ms space 뒤 새 리더로 시작한다. 구현은 `frames_hex`에
이미 포함된 반복 횟수를 그대로 출력하고 마지막 프레임 뒤에는 불필요한 space를 추가하지 않는다.

전원 OFF 생성 파형과 `power-off-from-cool-17-high-01.ir` 원본을 다음 분류로 정규화해
완전히 같은 순서임을 테스트했다.

- leader pulse
- bit pulse
- zero/one space
- 프레임 간 long gap
- 마지막 stop pulse

이는 파형 파일 생성이 캡처 구조와 같다는 검증이다. 38kHz 반송파는 여전히 판매 자료
기준이며 오실로스코프로 측정하지 않았다.

## 검증 결과

- 전체 테스트: `31 passed`
- 변경 파일 Ruff 검사: 통과
- 전체 저장소 Ruff: 기존 블로그 보조 스크립트 2개의 import 정렬 문제로 실패하며 이번
  송신 변경과 무관
- 1차 Pi 배포: 38개 파일의 SHA-256 일치 확인
- 부팅 설정: `dtoverlay=gpio-ir-tx,gpio_pin=18` 추가 후 재부팅 완료
- 장치 기능: `/dev/lirc0` raw 송신 가능, `/dev/lirc1` raw 수신 가능
- 서비스: enabled·active, Tailscale 전용 8001 health 정상
- 최초 서비스 설정이 수신 장치 `/dev/lirc1`을 가리켜 API가 안전하게 송신 불가를 반환함

## 다음 하드웨어 검증 순서

1. 에어컨을 향하지 않고 스마트폰 카메라로 짧은 광출력 확인
2. HW-477 수신기로 송신 파형을 다시 캡처해 원본과 비교
3. 실제 에어컨의 전원 OFF 반응을 사용자 관찰로 확인

## 2차 설정 수정과 최초 송신

사용자의 추가 승인을 받은 뒤 로컬 기준본과 Pi 사용자 서비스의 송신 장치를 검증된
`/dev/lirc0`으로 수정했다. 설정 파일 3개의 원격 SHA-256이 로컬과 일치했고 서비스는
재시작 후 active 상태를 유지했다. 상태 API는 다음을 반환했다.

- transport: `ir-ctl`
- available: `true`
- hardware_output: `true`
- device: `/dev/lirc0`

첫 실제 검증은 부작용이 가장 작은 `power_off` 패킷을 한 번만 전송했다. `ir-ctl` 실행은
성공했고 API 기록은 38kHz, 2프레임, 총 179,670µs, `status=sent`였다. 최근 서비스 로그에
오류는 없었다. 이 결과는 커널 송신 장치가 파형을 접수했다는 뜻이며, IR LED의 실제 광출력과
에어컨 수신 성공은 아직 확인하지 않았다. 사용자의 물리 관찰 전에는 완전 해결로 처리하지 않는다.

사용자는 최초 송신 때 모듈 LED가 점멸했지만 에어컨은 동작하지 않았다고 확인했다. 눈으로
보이는 기판 표시 LED라면 GPIO와 스위칭 동작의 근거는 되지만 투명 IR LED의 38kHz 광출력이나
광량을 증명하지는 않는다. 다음 검증은 스마트폰 카메라로 투명 IR LED를 확인한 뒤 HW-477을
송신기 정면 5~10cm에 놓고 동일한 `power_off`를 재캡처해 광출력·반송파·파형을 분리 진단한다.

이후 사용자가 송신기와 에어컨 사이의 거리·방향을 조정하자 에어컨이 정상 동작했다. 따라서
GPIO18 오버레이, P2N2222A 스위칭 회로, `ir-ctl` 전송과 Carrier `POWER_OFF` 패킷의 실제 제어
경로가 끝까지 동작함을 확인했다. 최초 실패는 파장 변화가 아니라 현재 모듈의 제한된 광출력,
약 20도인 판매 자료상 송신 각도, 설치 거리 또는 조준 조건의 영향으로 판단한다. 성공 거리의
정확한 수치는 아직 측정하지 않았으므로 추후 설치 위치를 정할 때 거리별 반복 시험이 필요하다.
