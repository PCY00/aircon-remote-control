# Zigbee/MQTT Step 2 — UZ-8D 도어센서 페어링

## 목표

실물 라벨 `UZ-8D` 도어·창문 센서를 제조사 클라우드 없이 ZBDongle-P 네트워크에
가입시키고, 실제 Zigbee 식별자와 MQTT 접점 값을 확인한다. 가입은 Coordinator에만
180초 허용하고 인터뷰 뒤 즉시 닫는다.

## 첫 시도 실패

가입 전 `permit_join=false`를 확인한 뒤 180초 동안 가입을 열었다. RESET을 누른 첫
시도에서 장치 제조사 `Wing`이 보였지만 장치가 인터뷰 중 네트워크를 떠났다. 이어서
다음 오류가 기록됐다.

```text
Interview failed for '[REDACTED_IEEE]' with error
'Error: DatabaseEntry with ID '3' does not exist'
```

로그 순서상 인터뷰가 참조하던 임시 장치 항목이 장치 이탈로 먼저 제거된 상황으로
판단했다. Coordinator, Zigbee2MQTT 데이터베이스 손상으로 단정할 근거는 없었으므로
서비스 재시작이나 데이터베이스 편집은 하지 않았다.

## 재페어링과 인터뷰 성공

가입 허용 시간이 남은 상태에서 사용자가 RESET을 표시등이 깜박일 때까지 약 5초 다시
눌렀다. 두 번째 가입에서 인터뷰와 구성이 모두 성공했다.

- 실물 모델: `UZ-8D`
- Zigbee 제조사: `Wing`
- Zigbee 모델: `TS0203`
- 유형: 배터리 전원 End Device
- Zigbee2MQTT 네이티브 지원: true
- 매칭 정의: Tuya Door/window sensor, definition v0.0.0
- OTA: false
- exposes: contact, battery, voltage, tamper, battery_low, linkquality

성공 직후 가입을 닫았고 `permit_join=false`, 종료 시각 없음으로 확인했다.

## 닫힘·열림 값 확정

첫 상태는 자석이 떨어진 상태에서 다음과 같이 보고됐다.

```json
{"battery":100,"battery_low":false,"contact":false,"tamper":false,"voltage":3200}
```

자석을 본체 중심 표시와 맞춰 10 mm 이내로 붙이자 `contact=true`가 들어왔고, 자석을
2~3 cm 이상 떼자 `contact=false`가 다시 들어왔다.

| 실제 상태 | MQTT `contact` | 관찰 linkquality |
|---|---:|---:|
| 닫힘, 자석 가까움 | `true` | 182 |
| 열림, 자석 떨어짐 | `false` | 218 |

따라서 UI와 자동화에서 `true=닫힘`, `false=열림`으로 사용한다. linkquality는 책상
근거리의 순간값이므로 실제 설치 위치 성능은 별도 반복 시험으로 판단한다.

## 최종 점검

- `permit_join=false`
- 등록된 비-Coordinator 장치: 2대
- `Zbeacon TH01`: 인터뷰 완료, 지원됨
- `Tuya TS0203`: 인터뷰 완료, 지원됨
- Zigbee2MQTT bridge: `online`
- MQTT 1883·Zigbee2MQTT 8080: loopback 전용 유지
- 기존 에어컨 웹앱 8001 health: 정상

읽기 전용 장치 요약 스크립트를 PowerShell `Get-Content` 파이프로 원격 Bash에 보낸 첫
실행은 요약을 출력한 뒤 끝에 `bash: $'\r': command not found`를 남겼다. 센서 상태나
Pi 파일에는 영향이 없었다. 표준입력에서 CR을 제거하는 `tr -d '\r' | bash -s` 방식으로
같은 요약을 다시 실행했고 경고 없이 장치 2대를 확인했다. 배포 스크립트는 계속 LF 파일
전송과 체크섬 검증 방식을 사용한다.

첫 PNG 렌더링에서는 Consolas 글꼴에 한글 글리프가 없어 주석과 제목이 네모로 표시됐다.
전체 본문을 한글 글꼴로 바꾼 중간 결과에서는 Bash 역슬래시가 원화 기호처럼 보였다.
렌더러가 한글이 들어간 줄과 제목에는 맑은 고딕, 명령·로그 줄에는 기존 Consolas를
선택하도록 보완하고 같은 자료를 다시 생성했다. 최종 PNG에서 한글, 영문 명령과
역슬래시를 모두 육안으로 확인했다.

블로그용 실제 명령·비식별화 출력은
`docs/assets/terminal/35-zigbee-ts0203-pairing-contact-test.txt/.png`에 보존했다.
IEEE 주소, 네트워크 주소와 사설 주소는 기록하지 않았다.

## Step 3 최종 통합시험으로 이관한 작업

- [완료] 장치의 안정적인 내부 friendly name 지정
- [완료] 이름 변경 뒤 Zigbee2MQTT 재시작과 이름 유지 확인
- [완료] 현재 두 장치와 Coordinator 런타임 백업
- [완료] Pi 전체 재부팅 뒤 재페어링 없이 두 센서 등록과 서비스가 복구되는지 확인
- 실제 설치 위치에서 닫힘·열림 반복 및 누락 여부 확인
- 자동 보고 주기 관찰
- 재부팅 후 도어 전환과 TH01 새 실측 보고가 다시 들어오는지 현장에서 확인

## 안정적인 내부 이름과 백업

사용자가 보는 공간명·기기명과 MQTT 토픽에 쓰는 내부 이름을 분리하기 위해 모델별 장치가
정확히 한 대인지 먼저 검사하고 다음 이름을 지정했다.

| 모델 | Zigbee2MQTT 내부 이름 |
|---|---|
| TH01 온습도 센서 | `sensor_temperature_01` |
| TS0203 도어센서 | `sensor_door_01` |

두 이름 변경 응답과 즉시 검증이 모두 성공했다. 이어서 기존
`scripts/backup_zigbee_stack.sh`로 Mosquitto와 Zigbee2MQTT를 정상 정지한 뒤 런타임을
백업하고 두 컨테이너를 다시 시작했다. 백업 파일은 권한이 제한된 Pi 런타임 폴더에 있으며
네트워크 키와 MQTT 비밀번호를 포함하므로 저장소와 블로그에 넣지 않는다. 실제 SHA-256은
현장에서 확인하고 공개 캡처에서는 `[REDACTED_SHA256]`으로 가렸다.

재시작 후 Coordinator 초기화, MQTT `online`, 1883·8080 loopback 제한과 기존 8001
앱 health가 모두 정상이다. 읽기 전용 장치 요약에서도 두 내부 이름, 인터뷰 완료와 지원
상태가 유지됐다. 이 검증은 Zigbee2MQTT 컨테이너 재시작에 대한 것이며 Pi 전체 재부팅
검증은 아직 남아 있다.

최신 백업의 메타데이터를 읽는 첫 명령에서는 과거 ISSUE-009와 동일하게 GNU `stat`의
`%n`을 줄바꿈으로 오해해 경로가 반복됐다. 읽기 전용 표시 문제로 백업에는 영향이 없었다.
파일명은 `printf`와 `basename`, 크기·권한·소유자는 각각 별도 `stat -c`로 출력해
41,449바이트, mode `600`, 소유자 `air:air`를 정상 확인했다.

관련 캡처: `docs/assets/terminal/36-zigbee-friendly-names-and-backup.txt/.png`

## Pi 전체 재부팅 검증 준비

재부팅 직전 가입 허용이 닫힌 상태, 센서 2대의 내부 이름·인터뷰·지원 상태, MQTT bridge
`online`, 1883·8080 loopback 제한과 8001 앱 health를 다시 확인했다.

승인 후 `sudo -n systemctl reboot`를 시도했으나 `sudo: a password is required`로 종료돼
재부팅은 일어나지 않았다. 일반 `systemctl reboot`도 `Interactive authentication required`를
반환했다. 비밀번호를 명령이나 캡처에 남기지 않고 SSH TTY의 `sudo` 프롬프트에만 입력해
전체 재부팅을 실행했다.

SSH 오프라인을 실제로 관찰한 뒤 약 34초 만에 다시 접속됐다. 현재 부팅의 컨테이너 시작
로그에서 직렬 포트 열림, Coordinator 초기화, MQTT 연결과 Zigbee2MQTT 시작 완료를
확인했다. Mosquitto·Zigbee2MQTT·Tailscale·8001 사용자 서비스는 모두 자동 복구됐고,
두 센서의 내부 이름·인터뷰·지원 상태와 `permit_join=false`도 유지됐다.

재부팅 직후 센서별 MQTT 토픽에는 retained payload가 없어 이전 온습도와 접점값이 자동
재생되지 않았다. 따라서 Step 3 앱이 마지막 상태와 도어 전환 이력을 SQLite에 보존하고,
마지막 실제 보고 시각과 캐시 값을 구분해야 한다. 사용자가 외부에 있어 도어 열림·닫힘과
온습도 센서 버튼을 통한 새 실측 보고 확인은 현장 검증 항목으로 남겼다.

관련 캡처: `docs/assets/terminal/37-zigbee-post-pairing-reboot-recovery.txt/.png`
