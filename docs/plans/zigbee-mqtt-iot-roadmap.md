# Zigbee/MQTT 스마트홈 확장 4단계 계획

## 목적과 범위

기존 Raspberry Pi 기반 웹앱을 Zigbee 스마트홈 중앙 서버로 확장한다. ZBDongle-P와
Zigbee2MQTT를 사용해 상용 센서의 상태를 로컬 MQTT로 수집하고, 기존 FastAPI/UI에
연결한 뒤 ESP32-H2 브레드보드 IR 노드로 Carrier CS-A061GS 에어컨을 제어한다.

이번 4단계의 최종 경로는 다음과 같다.

```text
사용자 → 웹 UI:8001 → FastAPI → 로컬 MQTT → Zigbee2MQTT
                                              ↓
                                        ZBDongle-P
                                              ↓ Zigbee
                   ┌──────────────────────────┼─────────────────────────┐
             온습도 센서               도어/창문 센서           ESP32-H2 IR 노드
                                                                      ↓ IR
                                                                 에어컨
```

스마트 온습도 센서와 도어/창문 센서는 MQTT 클라이언트가 아니다. 센서는 Zigbee로
통신하고 Zigbee2MQTT가 이를 로컬 MQTT 토픽으로 변환한다. 외부 클라우드, Smart Life,
Alexa와 Home Assistant는 이번 필수 구성에 포함하지 않는다.

## 공통 원칙

- 인터넷에 MQTT `1883`이나 Zigbee2MQTT 관리 화면을 직접 공개하지 않는다.
- 웹앱의 외부 접근은 기존과 같이 Tailscale과 포트 `8001`을 사용한다.
- Zigbee 네트워크 키, MQTT 비밀번호, 사설 주소와 장치 고유 ID를 저장소나 블로그에 공개하지 않는다.
- Pi 설정을 바꾸기 전 로컬 기준본과 배포 목록을 만들고 매번 사용자 승인을 받는다.
- `/dev/ttyUSB0` 대신 확인된 `/dev/serial/by-id/...` 고정 경로를 사용한다.
- USB 동글은 2.4 GHz 간섭을 줄이기 위해 USB 연장선으로 Pi 본체와 거리를 둔다.
- UI와 자동화는 MQTT 토픽이나 Zigbee Cluster를 직접 다루지 않고 의미 기반 기기 계층을 사용한다.
- 모든 단계에서 실제 명령·출력 TXT, 블로그용 PNG, 장치/배선 사진, 실패와 해결 기록을 남긴다.

## Step 1 — Raspberry Pi Zigbee/MQTT 게이트웨이

상태: **완료** (2026-09-06)

### 목표

ZBDongle-P를 Zigbee Coordinator로 구동하고 Raspberry Pi에 재부팅 후 자동 복구되는
로컬 MQTT와 Zigbee2MQTT 실행 환경을 만든다.

### 구현 작업

1. 현재 USB 식별, `cp210x` 드라이버, 고정 직렬 경로와 `dialout` 권한을 다시 확인한다.
2. 설치 방식은 재현성과 격리를 위해 `Mosquitto + Zigbee2MQTT` Docker Compose 구성을
   우선안으로 검토하고, 기존 FastAPI는 현재 systemd 서비스로 유지한다.
3. 실제 적용 시점에 공식 지원 버전을 확인해 이미지 버전을 고정한다.
4. Zigbee2MQTT 어댑터를 `zstack`으로 설정하고 ZBDongle-P의 고정 직렬 경로를 연결한다.
5. MQTT는 로컬 호스트/내부 컨테이너 네트워크에서만 사용하고 인증 정보를 런타임
   비밀 파일에 둔다.
6. Zigbee 채널, PAN ID, Extended PAN ID와 네트워크 키를 최초 생성 후 고정한다.
7. Zigbee2MQTT의 영구 데이터와 Coordinator 백업을 코드 배포 경로와 분리한다.
8. 서비스 자동 시작, 정상 종료, 로그 순환, 재부팅 복구를 확인한다.
9. 관리 화면은 초기에는 SSH 터널 또는 Tailscale 전용 경로로만 접근한다.

### 완료 기준

- Zigbee2MQTT가 동글을 열고 Coordinator 모델과 펌웨어 정보를 로그에 출력한다.
- MQTT의 `zigbee2mqtt/bridge/state`가 `online`이 된다.
- Pi 재부팅 후 Mosquitto와 Zigbee2MQTT가 자동으로 정상 복구된다.
- 외부 일반 네트워크에서 MQTT와 관리 화면에 접근할 수 없다.
- Coordinator 백업과 복구 위치가 문서화되어 있다.

### 블로그 캡처

- `lsusb`, `/dev/serial/by-id`, 사용자 권한
- Mosquitto/Zigbee2MQTT 설치 버전
- 최초 Coordinator 연결 성공 로그
- MQTT bridge 상태 구독 결과
- 재부팅 전후 서비스 상태와 실패 시 로그

## Step 2 — 상용 Zigbee 센서 2종 연동

상태: **개발 완료, 현장 검증은 Step 3 최종 통합시험으로 이관** (2026-09-07)

### 목표

알리에서 구입한 Zigbee 스마트 온습도 센서와 Zigbee 3.0 도어/창문 센서를 제조사
클라우드 없이 ZBDongle-P 네트워크에 직접 가입시키고 실제 MQTT 데이터를 분석한다.

### 구현 작업

1. 포장, 제품 라벨, 모델 번호와 판매 페이지를 촬영·보존한다.
2. 정확한 모델과 Zigbee `modelID`/`manufacturerName`을 Zigbee2MQTT 지원 목록에서 확인한다.
3. 네트워크 가입을 짧은 시간만 허용하고 온습도 센서를 먼저 공장 초기화·페어링한다.
4. 인터뷰 완료 후 안정적인 내부 ID와 사람이 보는 표시 이름을 구분해 등록한다.
5. 온도, 습도, 배터리, 전압, 링크 품질, 가용성의 실제 MQTT 메시지를 캡처한다.
6. 도어/창문 센서를 같은 방식으로 페어링하고 열림/닫힘과 배터리 상태를 캡처한다.
7. 접점의 `contact=true/false`가 실제 열림/닫힘 중 어느 쪽인지 실험으로 확정한다.
8. Coordinator 근처와 실제 설치 위치에서 수신 품질과 누락 여부를 비교한다.
9. Zigbee2MQTT와 Pi를 재시작해 두 센서가 재페어링 없이 복귀하는지 확인한다.

### 완료 기준

- 온습도 변화와 문 열림/닫힘이 MQTT에 반복해서 정상 수신된다.
- 각 필드의 단위, 의미, 갱신 주기와 미지원 항목이 기록되어 있다.
- 재부팅 후 두 센서가 기존 이름과 네트워크 연결을 유지한다.
- 실제 설치 위치에서 반복 동작 시험 중 이벤트 누락이 없다.

### 블로그 캡처

- 제품과 라벨 사진, Zigbee2MQTT 지원 모델 확인
- `Permit join`과 페어링 성공 로그
- 온도/습도 MQTT 원문
- 문 닫힘·열림 MQTT 원문 비교
- 실제 설치 위치와 링크 품질
- 페어링 실패가 있었다면 초기화 방법과 해결 화면

### 현재 준비 상태

- 실물 사진 13장과 설명서를 장치별로 보존했다.
- 도어센서는 실물 `UZ-8D`, 온습도 센서는 실물 `Z3-P3-L`로 확인했다.
- 설명서 모델명과 실제 Zigbee 식별자를 분리해 기록했다.
- 제한 시간 동안 장치 한 대만 가입시키는 절차와 로컬 도구를 준비했다.
- 온습도 센서 외관 `Z3-P3-L`은 실제 인터뷰에서 `Zbeacon TH01`로 식별됐고 네이티브
  지원과 온도·습도·배터리·전압 MQTT 보고를 확인했다.
- 도어센서 외관 `UZ-8D`은 실제 인터뷰에서 `Wing/TS0203`으로 식별됐고 Tuya 네이티브
  정의에 매칭됐다. 자석을 붙이고 떼어 `contact=true`는 닫힘, `false`는 열림으로
  확인했다.
- 두 센서의 근거리 페어링과 기본 상태 보고는 완료했다. Pi 전체 재부팅 뒤 서비스,
  장치 등록과 내부 이름이 유지되는 것도 확인했다. 실제 설치 위치 반복 시험, 자동 보고
  주기와 재부팅 뒤 첫 실측 보고 확인은 남아 있다.
- 내부 이름은 `sensor_temperature_01`, `sensor_door_01`로 지정했고 Zigbee2MQTT 재시작
  뒤 유지되는 것을 확인했다. 페어링 완료 상태 런타임 백업도 생성했다.

## Step 3 — FastAPI·웹 UI·자동화 통합

상태: **Raspberry Pi v0.7.0 배포·연결 검증 완료, 현장 통합시험 대기** (2026-09-08)

### 목표

Zigbee2MQTT의 토픽을 기존 스마트홈 기기 계층으로 감싸고, 웹 UI에서 센서 상태를
실시간 확인하며 간단한 로컬 자동화를 실행한다.

### 구현 작업

1. `DeviceTransport` 아래에 MQTT/Zigbee 게이트웨이 어댑터를 추가한다.
2. FastAPI 시작·종료 수명주기에 MQTT 연결, 재연결과 구독을 연결한다.
3. Zigbee friendly name을 내부 기기 ID에 매핑하고 원시 payload를 공통 상태로 정규화한다.
4. 온도, 습도, 접점, 배터리, 마지막 수신 시간과 온라인/오프라인 상태를 제공한다.
5. REST는 현재 상태와 이력을 제공하고, UI 실시간 갱신은 SSE 또는 WebSocket 중 기존
   구조에 적합한 한 가지로 구현한다.
6. 공간별 카드에 온습도 센서와 도어 센서를 추가하고 모바일/PC 반응형 화면을 확인한다.
7. 13인치 Raspberry Pi 직결 터치 화면에서는 벽면 대시보드 모드를 제공한다. 큰 터치
   영역, 항상 보이는 센서 요약, 빠른 장면과 에어컨 제어를 2~3열로 배치한다.
8. Raspberry Pi OS Lite에는 데스크톱이 없으므로 최소 그래픽 환경과 Chromium 키오스크
   자동 시작·장애 복구를 별도 설치하고, 터치만으로 전체 기능을 사용할 수 있게 한다.
9. 최소 자동화 한 가지를 구현한다. 첫 후보는 문이 일정 시간 열린 상태에서 에어컨이
   켜져 있으면 UI 경고와 이벤트 기록을 남기는 규칙이다.
10. MQTT 연결 끊김, 센서 배터리 부족, 오래된 값과 장치 오프라인을 정상 상태와 구분한다.
11. 로컬 터치 화면은 인터넷이 끊겨도 제어 가능해야 하며, 외부 접속은 계속 Tailscale로
    제한한다. 현재 Tailscale IP 단일 바인딩에서 로컬 loopback 접근을 함께 제공할 안전한
    방식을 구현 전에 검증하고 `0.0.0.0` 무방비 바인딩은 사용하지 않는다.
12. Mock MQTT 테스트와 실제 센서 통합 테스트를 분리한다.
13. 도어센서의 열림·닫힘 상태 전환을 수신 시각과 함께 SQLite에 기록하고, 같은 상태의
    반복 보고와 retained 재생으로 이력이 중복되지 않게 한다.
14. 온습도는 기본 `07:00–19:00`에 자동 갱신하지 않고 수동 요청만 허용한다. 수동 전용
    시작·종료 시각, 자동 갱신 활성화 여부와 간격을 설정 가능하게 하고, Sleepy End
    Device의 능동 조회 지원 여부를 실기로 확인해 새 측정, 보고 대기와 캐시 재조회를
    구분한다.
15. `기기 추가 → Zigbee 센서` 마법사에서 제한 시간 가입, 장치 발견, 지원 여부 확인,
    표시 이름·공간·아이콘 지정과 내부 ID 생성을 처리한다. 성공·취소·만료 뒤에는 가입
    허용을 자동으로 닫고, 새 센서 종류는 Zigbee2MQTT `exposes`를 capability로 변환해
    카드와 상태 필드를 구성한다.

### 현재 구현 상태

- [완료] Paho MQTT 2.x 어댑터와 FastAPI 수명주기 연결 경계
- [완료] `zigbee2mqtt/<friendly_name>` JSON을 공통 센서 상태로 정규화
- [완료] SQLite에 마지막 상태와 실제 도어 전환 이력 영구 저장
- [완료] 현재 센서·개별 센서·도어 이력·MQTT 상태 REST API
- [완료] Python 단위·회귀 테스트 74개와 Node 화면 갱신 정책 테스트 12개 통과
- [완료] Raspberry Pi MQTT 인증정보 적용, 서비스 재시작과 MQTT 연결 검증
- [완료] 두 센서 저장 상태와 실제 도어 전환 이력을 API에서 확인
- [완료] 온습도 화면 수동 갱신 및 KST `07:00–19:00` 자동 화면 갱신 금지 정책
- [완료] 온습도 SSE 화면 반영 차단, 재연결·강제 REST 자동 조회에서도 활성화/정지/간격 유지
- [완료] 공간별 센서 카드, 도어 이력 상세와 서버 영구 저장 센서 이름·공간·아이콘 설정
- [완료] Cage/Chromium 키오스크 설치, 자동 시작과 디스플레이 미연결 대기 상태 검증
- [완료] 13인치 화면 출력·터치, 재부팅 후 키오스크 자동 복구와 커서 숨김 검증
- [완료] 30/60/120초 제한 Zigbee 가입 API·UI, 취소/만료 자동 차단과 장치 목록
- [대기] 화면 회전·절전 현장 설정
- [배포·연결 검증 완료] SSE HTTP 200, `stream.ready`와 keep-alive 수신; 재연결 시 REST 복구
- [배포·로컬 검증 완료] 문 열림+에어컨 켜짐 지연 경고, 중복 방지와 발생·해제 이력
- [대기] 새 도어 전환의 SSE 화면 반영과 실물 조건으로 경고 발생·해제 검증
- [대기] MQTT 단절·재연결 현장 통합시험

승인된 11개 파일(227,084 bytes)을 배포하고 로컬·Pi SHA-256 일치를 확인했다. 앱과
키오스크는 모두 `active`, `NRestarts=0`이었으며 MQTT 연결, 저장 센서 2개와 Zigbee 장치
2개를 확인했다. 가입은 `permit_join=false`로 유지했다. 경고 규칙은 활성·300초 지연,
경고 비활성·이력 0건이었다. 이번 점검은 실물 조작과 IR 명령 없이 수행했으며 새 센서
SSE 이벤트도 관찰되지 않았으므로 실제 문 전환·경고 시험의 성공 근거로 삼지 않는다.
자세한 과정은 [2026-09-08 운영 배포 기록](../journal/2026-09-08-step3-pi-live-deployment.md)에 남긴다.

### 완료 기준

- 웹 UI에 도어 상태는 실시간으로, 온습도 값과 보고 시각은 설정된 화면 갱신 정책에 맞게 반영된다.
- 도어 열림·닫힘마다 발생 시각이 기록되고 현재 상태와 최근 이력을 함께 확인할 수 있다.
- 온습도 자동 갱신 시간대·간격을 변경할 수 있고, 수동 요청 결과가 새 보고인지 기존
  저장값인지 구분된다.
- 지원 Zigbee 센서를 SSH 없이 UI에서 안전하게 추가할 수 있고 가입 창이 자동으로 닫힌다.
- 13인치 터치 화면에서 전체 화면 키오스크가 자동 시작되고 큰 터치 영역으로 제어된다.
- 휴대폰·PC·13인치 패널이 같은 웹앱과 API를 사용하며 화면 크기에 맞게 재배치된다.
- Zigbee/MQTT가 끊겨도 FastAPI가 죽지 않고 재연결하며 상태를 `offline/stale`로 표시한다.
- 자동화 규칙의 조건, 지연, 중복 방지와 실행 이력이 검증된다.
- UI 코드에는 Zigbee Cluster와 원시 MQTT 토픽이 노출되지 않는다.

### 블로그 캡처

- MQTT 원문과 정규화된 API 응답 비교
- 모바일/PC 센서 카드
- 13인치 터치 대시보드 전체 화면과 재부팅 후 키오스크 자동 복구
- 문 열림 전후 실시간 UI 변화
- MQTT 중단과 자동 재연결 로그
- 자동화 조건 충족과 실행 이력

## Step 4 — ESP32-H2 Zigbee IR 노드와 에어컨 제어

상태: **진행 중 — ESP32-H2 ROM 복구·IR 단독 펌웨어 빌드/플래시/안정 부팅 완료**

### 목표

ESP32-H2-DevKitM-1, 940 nm IR LED, AO3400A와 브레드보드로 Zigbee IR 노드를 만들고,
기존 웹 UI에서 보낸 에어컨 명령이 MQTT와 Zigbee를 거쳐 실제 에어컨을 제어하게 한다.

### 구현 작업

1. ESP-IDF와 ESP Zigbee SDK 버전을 고정하고 별도 펌웨어 프로젝트를 만든다.
2. USB 전원, GPIO5, Gate 저항/풀다운, AO3400A, LED 전류 제한 저항과 TSAL6200 한 개로
   기존 회로를 다시 검증한다.
3. Zigbee 없이 ESP32-H2 RMT만으로 Carrier IR 명령을 송신해 에어컨 반응을 먼저 확인한다.
4. H2를 Zigbee End Device로 구성하고 Basic/Identify 및 제조사 정의 Cluster를 등록한다.
5. Zigbee2MQTT external converter가 MQTT 명령을 H2의 짧은 Zigbee 명령으로 변환하게 한다.
6. 최초 시제품에서는 검증된 Carrier 명령 테이블을 H2 펌웨어/NVS에 넣고
   `profile_id + command_id + request_id`만 전송한다.
7. H2는 Zigbee 수신 후 RMT로 38 kHz 반송파와 IR 타이밍을 로컬 생성한다. 긴 raw IR
   타이밍을 실시간 Zigbee 패킷으로 스트리밍하지 않는다.
8. H2가 `accepted`, `sent`, `failed` 상태와 요청 번호를 응답하게 해 중복 실행을 막는다.
9. 기존 FastAPI의 `IrTransport`에 `ZigbeeIrTransport`를 추가하고 에어컨 기기의 전송
   방식을 로컬 GPIO와 Zigbee 중 선택할 수 있게 한다.
10. 전원, 냉방 온도, 풍량과 운전 모드를 제한된 횟수로 실기 검증하고 거리·방향을 기록한다.

### 완료 기준

- H2가 ZBDongle-P 네트워크에 가입하고 재시작 후 자동 복귀한다.
- MQTT 명령, Zigbee 수신, H2 응답과 IR 송신을 같은 요청 번호로 추적할 수 있다.
- 웹 UI에서 최소 `켜기`, `끄기`, 냉방 온도 변경과 풍량 변경이 실제 에어컨에 적용된다.
- 잘못된 프로필/명령, Zigbee 오프라인과 IR 송신 실패가 API 오류로 구분된다.
- 같은 명령 반복 시험과 실제 배치 거리에서 성공률이 기록되어 있다.

### 블로그 캡처

- 브레드보드 배선과 부품 방향
- ESP32-H2 빌드/플래시 및 부팅 로그
- Zigbee 가입과 external converter 인식
- MQTT → Zigbee → RMT 요청 번호 추적 로그
- 웹 UI 조작과 실제 에어컨 반응 사진 또는 영상
- 거리·방향·LED 개수별 성공률 비교

## Step 4 이후로 미루는 작업

다음 항목은 이번 완료 조건에 포함하지 않는다.

- ESP32-H2 모듈 직접 실장 PCB
- LiPo/코인셀 전원과 충전·보호 회로
- Sleepy End Device 소비전류와 6~12개월 배터리 최적화
- 다중 IR LED와 완성형 케이스
- 프로필 무선 배포, OTA와 롤백의 제품 수준 구현
- KC/EMC/배터리 안전 인증 및 양산 설계
- Smart Life, Alexa, Google Home, Home Assistant 또는 Matter 연동

PCB 단계에 들어가기 전 이번 브레드보드 시제품에서 실제 전류, Zigbee 지연, 패킷 크기,
IR 도달 거리와 발열을 측정해 부품과 전원 구조를 확정한다.

## 예상 코드·데이터 경계

```text
deploy/zigbee/                  # 배포 가능한 Compose/설정 템플릿
app/integrations/mqtt/          # MQTT 연결과 재연결
app/transports/zigbee/          # Zigbee2MQTT 의미 기반 어댑터
firmware/esp32-h2-ir-node/      # ESP32-H2 펌웨어
device_profiles/...             # 에어컨 프로필 기준본
runtime/                        # Pi 전용 영구 데이터, 동기화 제외
docs/blog/zigbee-mqtt/          # 후속 4편 블로그
docs/assets/terminal/           # 실제 출력 TXT/PNG
docs/assets/hardware/zigbee/    # 동글·센서·배선 사진
```

폴더명은 구현 전에 현재 코드 구조와 충돌 여부를 확인한 뒤 확정한다. Pi의 실제 런타임
경로도 배포 승인 요청 때 명시하며 이 계획만으로 생성하지 않는다.

## 단계 의존성과 중단 조건

```text
Step 1 Gateway
    ↓ Coordinator online
Step 2 Sensors
    ↓ 실제 MQTT 스키마 확정
Step 3 Web/API
    ↓ 의미 기반 Zigbee 어댑터 확정
Step 4 H2 IR node
    ↓ 실기 제어 성공
향후 PCB·저전력 제품화
```

- Step 1에서 Coordinator가 열리지 않으면 센서 페어링으로 넘어가지 않는다.
- Step 2에서 정확한 제품이 미지원이면 외부 converter 가능성을 조사하되, 지원된 것처럼 진행하지 않는다.
- Step 3은 실제 센서 payload를 확보한 뒤 스키마를 고정한다.
- Step 4는 RMT 단독 IR 성공 후 Zigbee 계층을 연결한다.

## 공식 근거

- [Zigbee2MQTT 시작 안내](https://www.zigbee2mqtt.io/guide/getting-started/)
- [Zigbee2MQTT Linux 설치](https://www.zigbee2mqtt.io/guide/installation/01_linux.html)
- [Zigbee2MQTT Z-Stack 어댑터](https://www.zigbee2mqtt.io/guide/adapters/zstack.html)
- [Espressif ESP Zigbee SDK 소개](https://docs.espressif.com/projects/esp-zigbee-sdk/en/latest/esp32/introduction.html)
- [Espressif Zigbee ZCL Custom Cluster](https://docs.espressif.com/projects/esp-zigbee-sdk/en/latest/esp32/user-guide/zcl_custom.html)
- [ESP32-H2 RMT](https://docs.espressif.com/projects/esp-idf/en/latest/esp32h2/api-reference/peripherals/rmt.html)
