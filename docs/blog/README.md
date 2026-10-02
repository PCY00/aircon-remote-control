# 에어컨 원격 제어 프로젝트 — 4편 블로그 구성

이 디렉터리는 Raspberry Pi와 기존 에어컨 리모컨으로 시작한 스마트홈 프로젝트를
네 단계로 나눈 게시용 초안이다. 각 글은 앞 글의 결과를 입력으로 사용하지만, 필요한
배경과 결과를 다시 설명해 한 편씩 독립적으로 읽을 수 있게 구성했다.

## 전체 순서

1. [Step 1 — Raspberry Pi 원격 제어 개발 환경 구성](step-1-development-environment.md)
2. [Step 2 — 기존 리모컨 IR 신호 하이재킹](step-2-ir-hijacking.md)
3. [Step 3 — Room First UI 구성과 IR 코드 연결](step-3-ui-and-api.md)
4. [Step 4 — IR 송신기 구성과 실제 에어컨 제어](step-4-ir-transmitter-control.md)

## 단계 사이의 관계

```text
Step 1
Raspberry Pi · SSH · FastAPI · systemd · Tailscale · 8001
                         ↓
Step 2
기존 리모컨 → HW-477 → 원시 IR 캡처 → Carrier 프로필
                         ↓
Step 3
반응형 UI → 의미 기반 API → 모델별 명령 선택
                         ↓
Step 4
GPIO18 → P2N2222A → 5V IR 송신기 → 실제 에어컨
```

## 공개 전 공통 점검

- 사설 IP, 계정, 비밀번호, SSH 개인키와 Tailnet 식별자는 공개하지 않는다.
- 판매 자료로만 확인한 38kHz 반송파는 계측값처럼 표현하지 않는다.
- API의 송신 성공과 에어컨의 실제 동작 확인을 구분한다.
- 17~20℃는 실측 규칙, 21~30℃는 생성 규칙이라는 차이를 유지한다.
- 터미널 이미지는 `SANITIZED TERMINAL RECORD`로 표시된 재구성 자료임을 밝힌다.
- 제품 사진과 터미널 이미지의 게시 순서·대체 텍스트를 최종 플랫폼에 맞춰 조정한다.

## 현재 완료 상태

- Step 1: 완료 — Tailscale 전용 8001 서비스와 자동 실행 검증
- Step 2: 완료 — 48비트 IR 프레임 수집·분석·저장 API 검증
- Step 3: 완료 — 반응형 Room First UI와 Carrier 의미 기반 API 연결
- Step 4: 완료 — GPIO18 실송신과 실제 Carrier 에어컨 반응 확인

향후 ESP32-H2 Zigbee 노드, MQTT, 조명과 센서 확장은 이 4편 이후 별도 시리즈로 다룬다.

## 후속 시리즈

- [Zigbee/MQTT 스마트홈 확장](zigbee-mqtt/README.md): 게이트웨이, 상용 센서, UI 통합과 H2 노드 실험
- [ESP32-H2 Zigbee IR 리모컨 PCB 만들기 — 4편](pcb-ir-node/README.md): 부품 선정, 회로도 검토, PCB 배선, JLCPCB 주문 준비
- [가족 스마트홈 앱·공기계 중앙 서버 — 진행 중](mobile-app/README.md): A50 원격 관리·중앙 API·가구별 권한과 가족 APK 시험 기록. 실제 Google 로그인·외부 연결·FCM은 후속 검증.

PCB 시리즈는 사용자 설계의 시제품 제조 파일 준비까지 정리한 글이다. 아직 발주·실물 테스트를
마친 상태가 아니며, 기존 시리즈의 미완료 실험과 별도로 관리한다.
