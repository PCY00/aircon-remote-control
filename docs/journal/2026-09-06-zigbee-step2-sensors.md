# Zigbee/MQTT Step 2 — 상용 센서 준비와 페어링

## 범위

Zigbee 3.0 온습도 센서와 도어·창문 센서를 제조사 클라우드 없이 기존 ZBDongle-P
네트워크에 연결한다. 이번 기록은 실물 식별과 안전한 페어링 준비부터 시작한다.

## 실물 자료 정리

사용자가 제공한 사진 13장을 표시 순서대로 분류했다.

- 1~6: 도어·창문 센서 `UZ-8D`
- 7~13: 온습도 센서 `Z3-P3-L`

원본 JPEG는 내용 변경 없이 `docs/assets/hardware/zigbee/`에 의미 있는 파일명으로
복사했고 각 파일의 SHA-256을 계산해 복사 완료를 확인했다. 공개 문서에는 원래 메신저
파일명 대신 장치와 장면을 설명하는 파일명을 사용한다.

## 식별 결과

도어센서 설명서는 여섯 모델을 함께 다루지만 실물 라벨은 `UZ-8D`다. 설명서 모델군에
포함된 `ZD08`은 Zigbee2MQTT 지원 목록에 존재하지만 이를 `UZ-8D`와 동일하다고 볼
근거는 아직 없다.

온습도 센서 실물 라벨은 `Z3-P3-L`이며 설명서에는 DC 3 V, AAA 2개, 대기 전류 20 µA
이하, -10~55 °C, 0~99 %RH가 적혀 있다. 외관 모델명만으로 Zigbee2MQTT 지원 여부를
확정할 수 없으므로 실제 인터뷰 결과를 기준으로 판단한다.

상세 식별표와 사진 링크는
[`../hardware/zigbee-commercial-sensors.md`](../hardware/zigbee-commercial-sensors.md)에
정리했다.

## 페어링 설계

- 장치 한 대씩 가입시킨다.
- 온습도 센서를 먼저 페어링한다.
- `permit_join`은 기본 180초, 최대 254초로 제한한다.
- 가능하면 전체 네트워크가 아니라 Coordinator를 통한 가입으로 제한한다.
- 성공 또는 실패 확인 후 즉시 가입을 닫는다.
- 장치 인터뷰 결과에서 실제 `modelID`, `manufacturerName`, 지원 여부와 exposes를 얻는다.
- 로그와 MQTT 원문을 보존하되 IEEE 주소 등 고유 식별자는 `[REDACTED_IEEE]`로 바꾼다.

이 작업을 재현하기 위한 `scripts/zigbee_join_control.sh`를 로컬에 작성했다. Pi에 파일을
전송하고 가입을 여는 작업은 Zigbee 네트워크 상태를 바꾸므로 별도 승인을 받은 뒤에만
수행한다.

## 페어링 전 읽기 전용 확인

- Zigbee2MQTT 2.14.1, Mosquitto 2.1.2와 기존 8001 앱이 모두 정상이다.
- MQTT bridge는 `online`이고 1883·8080은 계속 루프백에만 바인딩되어 있다.
- 현재 Coordinator에 가입된 장치는 0대다.
- 동적 가입 상태는 `permit_join=false`, 종료 시각 없음으로 확인했다.
- 컨테이너에 설치된 `zigbee-herdsman-converters` 26.105.0 정의에서 실물 라벨
  `UZ-8D`와 `Z3-P3-L` 문자열을 직접 검색했으나 일치 항목이 없었다.

문자열 일치가 없다는 사실만으로 미지원이라고 확정할 수는 없다. Tuya 계열은 외관
모델과 다른 Zigbee 식별자나 fingerprint로 기존 정의에 매칭될 수 있으므로 실제 인터뷰를
진행해 `supported` 값과 exposes를 확인한다.

### 확인 중 발생한 문제

첫 변환기 검색은 일반적인 `node_modules/zigbee-herdsman-converters/dist/devices` 경로를
가정해 실행했지만 이 이미지가 pnpm 가상 저장소 구조를 사용해 검색 경로가 없었다.
읽기 전용 명령만 실패했으며 컨테이너에는 영향이 없었다. `find`로 실제
`zigbee-herdsman-converters@26.105.0` 경로를 찾은 뒤 다시 검색해 두 모델 모두 직접
문자열 일치 없음으로 확인했다.

로컬 스크립트를 PowerShell 파이프로 원격 Bash 표준입력에 보내 상태만 확인한 시도에서는
`BASH_SOURCE`가 없는 실행 형태와 CRLF 변환이 겹쳐 진단 메시지가 발생했다. MQTT 응답에서
가입이 닫힌 사실은 읽었지만 명령 종료값은 실패였다. 원인은 Step 1에서 경험한 Windows
표준입력 개행 문제와 같은 계열이다. 실제 작업은 LF 파일을 체크섬 검증 후 Pi에 배포해
실행하며, 스크립트 자체도 `BASH_SOURCE`가 없는 경우를 처리하도록 보강했다.
같은 파일을 Git Bash의 파일 입력 리디렉션으로 다시 전달한 읽기 전용 검사는 오류 없이
`permit_join=false`와 종료 시각 없음 및 Bash 문법 통과를 반환했다.

관련 캡처: `docs/assets/terminal/32-zigbee-step2-sensor-preflight.txt/.png`

터미널 PNG를 만들 때 프로젝트 `.venv`에는 렌더러가 사용하는 Pillow가 없어
`ModuleNotFoundError: No module named 'PIL'`이 발생했다. 시스템 Python에는 Pillow
12.2.0이 있어 우선 동일 TXT를 정상 렌더링했고, 재현 가능한 새 환경에서도 동작하도록
개발 의존성에 `pillow>=11,<13`을 추가했다. Pi 운영 의존성에는 포함하지 않는다.
프로젝트 가상환경에 개발 의존성을 다시 설치한 뒤 Pillow 12.3.0으로 같은 PNG를
재생성했고 전체 테스트 31개가 통과했다.

전체 Ruff 검사에서는 이번에 사용한 렌더러와 기존 `convert_ir_compact.py`에 각각
불필요한 빈 줄 한 개가 있었다. 렌더러는 수정해 개별 검사를 통과시켰다. 기존 IR 변환
스크립트의 빈 줄은 현재 Zigbee 작업과 무관한 기존 변경이므로 이번에는 수정하지 않고
전체 Ruff의 남은 1건으로 기록한다.

렌더링 의존성 실패와 해결 캡처:
`docs/assets/terminal/33-terminal-capture-pillow-fix.txt/.png`

## 온습도 센서 실제 페어링

승인 후 `scripts/zigbee_join_control.sh` 한 파일만 Pi의 같은 상대 경로에 전송했다.
로컬과 원격 SHA-256이 일치했고 원격 `bash -n`도 통과했다. 서비스 재시작은 없었다.

가입을 Coordinator 대상으로 180초 열고 사용자가 실물 `Z3-P3-L`의 RESET을 5초간
누른 뒤 놓았다. 장치는 즉시 가입했고 인터뷰와 구성이 성공했다.

- Zigbee 제조사: `Zbeacon`
- Zigbee 모델: `TH01`
- 장치 유형: 배터리 전원 End Device
- Zigbee2MQTT 네이티브 지원: true
- exposes: battery, temperature, humidity, voltage, linkquality
- 첫 상태: 25.59 °C, 39.73 %RH, 100 %, 3000 mV

인터뷰 성공 직후 가입을 수동으로 닫아 `permit_join=false`와 종료 시각 없음을 확인했다.
사용자가 센서를 손으로 감싸고 버튼을 짧게 누른 뒤 온도는 25.77 °C, 습도는 48.15 %RH로
갱신됐다. 따라서 단순 가입뿐 아니라 온도·습도 속성 보고까지 실제로 확인했다.

고유 IEEE 주소와 네트워크 주소는 원시 로그 확인에만 사용하고 캡처에서는 제거했다.
읽기 전용 요약 도구도 장치 수, 모델, 제조사, 인터뷰와 지원 여부만 출력하도록 만들었다.
최종 요약은 장치 1대, `Zbeacon TH01`, 인터뷰 완료, 지원됨을 반환했다. 스택과 기존
8001 앱도 페어링 뒤 정상 상태를 유지했다.

관련 캡처: `docs/assets/terminal/34-zigbee-th01-pairing-and-report.txt/.png`

도어센서의 실제 페어링, 첫 인터뷰 실패와 재시도, 접점 의미 확정은 날짜가 바뀐 뒤
계속되어 [`2026-09-07-zigbee-step2-door-sensor.md`](2026-09-07-zigbee-step2-door-sensor.md)에
분리 기록했다.

## 진행 상태

- [x] 제품·설명서 사진 13장 원본 보존
- [x] 실물 모델, 전원, 제조사와 페어링 절차 문서화
- [x] 공식 Zigbee2MQTT 지원 목록 사전 대조
- [x] 제한 시간 가입 제어 스크립트 로컬 작성
- [x] Pi 배포 전 미리보기와 승인
- [x] 온습도 센서 페어링·인터뷰
- [x] 온도·습도·배터리 MQTT 캡처와 변화 실험
- [x] 도어센서 페어링·인터뷰
- [x] 닫힘·열림 MQTT 캡처와 의미 확정
- [x] Raspberry Pi 전체 재부팅 뒤 서비스·센서 등록·내부 이름 복구
- [→ Step 3] 설치 위치 통신, 재부팅 후 새 보고와 장시간 자동 보고 주기 검증

## Step 2 마감 결정

센서 두 대의 식별, 네이티브 지원, 실제 MQTT 필드와 도어 접점 의미가 확정돼 Step 3
개발에 필요한 입력 계약은 확보했다. Raspberry Pi 전체 재부팅 뒤 게이트웨이·웹앱과
센서 등록도 유지됐다. 사용자가 외부에 있어 바로 수행할 수 없는 설치 위치 반복시험,
재부팅 후 첫 실측 보고와 장시간 자동 보고 주기 관찰은 Step 3 마지막 현장 통합시험으로
이관한다. 미측정 항목을 완료로 간주하지는 않는다.

게시용 본문:
[`../blog/zigbee-mqtt/02-commercial-zigbee-sensors.md`](../blog/zigbee-mqtt/02-commercial-zigbee-sensors.md)
