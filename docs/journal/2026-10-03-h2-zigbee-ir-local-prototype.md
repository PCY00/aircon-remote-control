# 2026-10-03 — H2 Zigbee IR 펌웨어 로컬 시제품

## 출발점과 경계

GPIO5 만능기판에서 기존 USB 콘솔 펌웨어의 Carrier `POWER_OFF`를 1회 보내고,
사용자가 실제 에어컨이 꺼졌다고 확인했다. 그 결과를 Zigbee 명령으로 재현하기 위한
**별도** 펌웨어 프로젝트를 로컬에 만들었다. 로컬 준비 시점에는 보드 플래시,
Pi 배포, Zigbee 가입, 에어컨 추가 송신을 하지 않았다. 이후 사용자의 명시적 요청으로
보드에 플래시한 결과는 아래에 이어 쓴다. Zigbee 경유 제어는 여전히 미검증이다.

## 설계

- `firmware/esp32-h2-zigbee-ir-node/`에 ESP-IDF 5.5.4 / Espressif Zigbee SDK 2.0.4
  기반의 End Device를 분리했다. 기존 USB 콘솔 펌웨어는 보존한다.
- 기존에 1회 실기 성공한 Carrier `POWER_OFF` 원시 데이터와 타이밍을 그대로
  사용하고, RMT 출력을 GPIO5로 고정했다. 부팅·가입 시 자동 IR 송신은 없다.
- Home Automation endpoint 10의 비표준 클러스터 `0xFF00`에서 `POWER_OFF`만
  수락한다. 프로토콜 버전·프로필·명령·요청 ID와 길이를 검증한다. 잘못된 명령은
  IR 작업 큐에 넣지 않는다.
- 요청 ID는 최근 8개를 RAM에서 중복 방지한다. 이 기록은 재부팅 시 사라지므로
  영구 중복 방지는 아니다. IR 완료 응답의 `sent`는 RMT 전송 완료를 뜻하며,
  에어컨이 꺼졌다는 측정 결과는 아니다.
- Zigbee2MQTT용 외부 변환기 후보를 별도 파일로 작성했다. 현장 서비스에는 설치하지
  않았으며, 외부 JavaScript 허용 설정도 바꾸지 않았다.

## 로컬 검증과 문제 해결

- 처음 빌드에서는 복사된 스테이징 `sdkconfig`에 Zigbee 기능이 활성화되지 않아
  Zigbee 헤더를 찾지 못했다. `sdkconfig.defaults`에 Zigbee End Device 설정을
  명시하고, 기존 스테이징 설정이 잘못된 경우 `set-target esp32h2`를 다시 수행하게
  했다.
- 다음 빌드에서는 `main` 컴포넌트가 Zigbee 라이브러리 의존성을 선언하지 않아
  헤더를 찾지 못했다. `main/CMakeLists.txt`의 `REQUIRES`에 해당 컴포넌트를 추가했다.
- 이후 실제 ESP-IDF 5.5.4 빌드가 성공했다. 최종 4MB 설정 앱 바이너리
  `0x7c930` bytes, 앱 파티션 여유 `0x6e6d0` bytes (47%).
  [출력 발췌 TXT](../assets/terminal/351-h2-zigbee-local-build.txt),
  [PNG](../assets/terminal/351-h2-zigbee-local-build.png). 최종 빌드 바이너리의
  SHA-256은 `9780678D6E014BEDC9C7DF8FB7D07C6A9FF4039AF277BED3E43BE09A7EB5FFCE`이다.
- 호스트 프로토콜 테스트 2개 통과. 기존 USB 펌웨어의 Carrier 명령 상수와
  타이밍이 일치하며, 잘못된 요청은 거부됨을 확인했다.
  [테스트 TXT](../assets/terminal/352-h2-zigbee-local-checks.txt),
  [PNG](../assets/terminal/352-h2-zigbee-local-checks.png).
- Zigbee2MQTT 2.14.1이 고정한 `zigbee-herdsman` 10.9.2와
  `zigbee-herdsman-converters` 26.105.0을 **로컬 임시 폴더**에 설치했다.
  변환기 로드, `request_id=12345`의 6바이트 요청 변환과 7바이트 결과 해석,
  `POWER_TOGGLE` 거부를 가짜 endpoint로 확인했다. 실제 게이트웨이 로드·무선
  전송까지 검증한 것은 아니다.

## 다음 현장 검증

새 펌웨어를 올리면 현재 보드에서 동작하는 USB 콘솔 시험 펌웨어가 교체된다.
사용자에게 교체 범위를 확인받은 뒤 포트를 다시 식별하고 플래시해야 한다. 이후
Zigbee 가입, 변환기 로드, 요청 ID 상관관계, 실제 에어컨 반응을 각각 확인한다.
일반 인터넷 공개나 Zigbee 네트워크 초기화는 이 과정에 필요하지 않다.

## 펌웨어 교체 착수

사용자가 펌웨어 교체를 명시적으로 요청했다. COM6의 장치를 ESP32-H2 리비전 1.2로
재확인했고, 물리 플래시 크기가 **4MB**임을 확인했다. 고유 MAC은 공개 기록에
남기지 않는다. 교체 전 플래시 전체 4,194,304 bytes를 저장소 밖
`C:\esp\aircon-h2-backups\before-zigbee-2026-10-03-4mb.bin`에 읽어 백업했다.
이 파일은 원래 펌웨어와 장치별 데이터가 들어갈 수 있어 블로그에 첨부하지 않는다.
백업 SHA-256은 `66A42B2D87931830E257FD7F5E3D7E6B55B035431258D6B7A493A869B18BB638`이다.
처음 Zigbee 빌드 설정의 플래시 크기는 2MB였으므로 실물에 맞춰 4MB로 고치고
다시 빌드했다. [백업 명령과 검증 TXT](../assets/terminal/353-h2-zigbee-preflash-backup.txt),
[PNG](../assets/terminal/353-h2-zigbee-preflash-backup.png).

## COM6 펌웨어 교체·첫 부팅 결과

- 4MB 설정으로 다시 빌드한 후 `-Action flash -Variant zigbee-ir-node -Port COM6`을
  실행했다. 부트로더, 파티션 테이블, OTA 초기 데이터, 앱 이미지 네 영역에서
  모두 `Hash of data verified.`가 출력됐고 명령은 종료 코드 0으로 끝났다.
  [플래시 TXT](../assets/terminal/354-h2-zigbee-flash.txt),
  [PNG](../assets/terminal/354-h2-zigbee-flash.png).
- 모니터에서 `SPI Flash Size : 4MB`, 앱 이름 `aircon_h2_zigbee_ir_node`,
  `GPIO5 IR ready; waiting for Zigbee; no automatic IR on boot`를 확인했다.
  이 부팅 점검에서는 IR 제어 명령을 보내지 않았다.
- 첫 네트워크 스티어링은 `Zigbee join failed: 0x03`이었다. SDK 2.0.4의
  `EZB_BDB_STATUS_NO_NETWORK`에 해당한다. 즉 해당 시도에서 가입 가능한
  네트워크를 찾지 못했다는 뜻이며, 가입 허용 창·거리·게이트웨이 상태 중 어느
  요인이 원인인지 아직 확인하지 않았다. 펌웨어 부팅 성공과 네트워크 가입 실패를
  구분한다. 자동 반복 재시도, Pi 설정 변경, 네트워크 초기화는 하지 않았다.
  [첫 부팅 TXT](../assets/terminal/355-h2-zigbee-first-boot-no-network.txt),
  [PNG](../assets/terminal/355-h2-zigbee-first-boot-no-network.png).

## 제한 시간 가입과 인터뷰 결과

사용자 승인 후 로컬 COM6의 H2와 Pi 게이트웨이를 다시 확인했다. Zigbee2MQTT와
Mosquitto 컨테이너는 실행 중이었고 가입은 `permit_join=false`였다. Pi에서 쓰는
`scripts/zigbee_join_control.sh`가 로컬 기준본과 SHA-256으로 일치하는 것도 확인했다.
기존 센서 등록 정보나 네트워크 설정 파일은 수정하지 않았다.

Pi의 기존 제어 스크립트로 Coordinator의 새 기기 가입을 **120초** 열었다. 성공
응답과 `permit_join=true`를 받은 뒤 PC의 `idf.py monitor`를 연결하여 보드를
재시작했다. H2는 약 2.9초 뒤 `Zigbee joined; IR remains idle until a valid command
arrives`를 출력했다. Zigbee2MQTT 로그에는 23:07:04(KST) 새 기기 가입,
23:07:05 인터뷰 성공이 남았다. 바로 가입을 닫았고 Coordinator의 `time=0`,
`status=ok` 응답과 최종 `permit_join=false`를 확인했다.
[가입 절차 TXT](../assets/terminal/356-h2-zigbee-timed-join.txt),
[PNG](../assets/terminal/356-h2-zigbee-timed-join.png).

인터뷰 모델은 `AIRCON_H2_IR_01`, 제조사 문자열은 `DIY Aircon`으로 확인됐다.
Zigbee2MQTT 2.14.1은 현재 이 모델을 **미지원**으로 표시한다. 예상한 대로 로컬에
준비한 외부 변환기는 아직 Pi에서 로드되지 않았다. 이 변환기 로드는 게이트웨이에서
외부 JavaScript 실행을 허용하는 설정 변경을 포함하므로 이번 가입 작업에 섞지
않았다. 무선 가입 성공과 `POWER_OFF` 명령 송수신·실제 에어컨 반응은 별개다.
이번 작업에서 IR 명령을 보내지 않았다.
[게이트웨이 인터뷰 TXT](../assets/terminal/357-h2-zigbee-interview-unsupported.txt),
[PNG](../assets/terminal/357-h2-zigbee-interview-unsupported.png).

## 외부 변환기 적용과 재시작 검증

사용자가 Zigbee2MQTT 변환기 적용을 추가로 승인했다. 공식 문서에서 2.11.0 이후
새 설치는 외부 변환기가 기본 비활성이고, `advanced.enable_external_js`가 임의
JavaScript 실행을 허용하는 설정임을 확인했다. 따라서 이 파일 한 개만 검토·설치하고
런타임 디렉터리를 `0700`, 변환기·설정을 `0600`으로 유지했다. MQTT와 프런트엔드의
기존 루프백 바인딩이나 Zigbee 네트워크 키·채널·등록 기기는 바꾸지 않았다.

로컬에서 변환기 `node --check`, 설치 스크립트·펌웨어 프로토콜 테스트 7개,
Ruff 검사를 통과했다. 새 소스 파일 두 개를 Pi 프로젝트의 같은 상대 경로에
전송하고 SHA-256 일치를 확인했다. Pi 런타임 구성 파일의 해시를 미리보기에서
확인한 후, 그 값을 비교·교환 조건으로 적용했다. 기존 설정은 Pi의 비공개 백업
디렉터리에 복사했으며, `advanced.enable_external_js: true`만 추가하고 검토된
변환기를 런타임 폴더에 설치했다.
[로컬 검사·미리보기 TXT](../assets/terminal/358-h2-converter-preview-and-checks.txt),
[PNG](../assets/terminal/358-h2-converter-preview-and-checks.png).

`aircon-zigbee2mqtt` 컨테이너만 재시작했다. 23:16:07(KST)에
`Loaded external converter 'aircon-h2-ir.mjs'`, 23:16:08에
`Zigbee2MQTT started!`가 확인됐다. 기기 요약은 기존 TH01·TS0203와 H2의
총 3대가 모두 인터뷰 완료·지원됨을 표시했다. 확인용 스크립트는 생성된 정의가
있어도 `supported=false`일 수 있다는 점을 바로잡아, MQTT의 실제 `supported`
필드를 우선 읽게 수정했다. 가입 창은 여전히 `permit_join=false`였다.
[적용·검증 TXT](../assets/terminal/359-h2-converter-loaded-supported.txt),
[PNG](../assets/terminal/359-h2-converter-loaded-supported.png).

이 결과는 변환기 로드와 모델 인식의 증거다. `POWER_OFF` Zigbee 요청/응답과
실제 IR 송신·에어컨 반응은 아직 시험하지 않았고, 웹앱의 제어 경로도 바꾸지 않았다.

## Zigbee POWER_OFF 단일 송신과 현장 반응

로컬 `scripts/test_h2_zigbee_power_off.py`를 구문 검사하고 관련 테스트 7개를
통과했다. Pi에 기존 동일 파일이 없는 것을 확인한 후, 이 파일 한 개만 전송했다.
로컬·Pi SHA-256은 모두
`3dc56d6e72f58140c6ccac8f21d1892413befb081dcfe7ae0b3d20cfaaefd8e6`으로
일치했다. 서비스 재시작이나 Zigbee 가입 상태 변경은 없었다.

Pi 미리보기 23:22:56(KST)는 게이트웨이 온라인, H2 지원됨,
`permit_join=false`, MQTT 발행 0회를 확인했다. 사용자 준비 후 23:23:02(KST)
`--send`를 **한 번** 실행했다. 요청 ID `12495794`로 `POWER_OFF`를 MQTT에
1회 발행했고 같은 ID의 `accepted`와 `sent` 결과를 수신했다. 도구는 응답
타임아웃에도 자동 재전송하지 않도록 작성했다. 이번에는 타임아웃이 발생하지
않았다. 이어 사용자가 현장에서 에어컨이 실제로 꺼졌다고 답했다. 이 관찰은
펌웨어의 RMT 송신 완료와 별도 근거로 취급한다.

[단일 송신 TXT](../assets/terminal/360-h2-zigbee-power-off-one-shot.txt),
[PNG](../assets/terminal/360-h2-zigbee-power-off-one-shot.png).
Zigbee→H2→IR→에어컨 끄기 경로는 1회 성공했고, 웹앱/API 경로 전환은 아직이다.

## 웹 제어/API 연결과 버튼 없는 등록 방식

현재 Zigbee 펌웨어의 공장 초기 보드는 첫 부팅에서 network steering을 시작한다.
별도 등록 버튼은 구현하지 않았고 BOOT 버튼은 등록 용도가 아니다. Pi의
Zigbee2MQTT에서 가입을 잠시 허용하고 USB 전원을 넣는 방식으로 앞선 120초 가입
시험에 성공했다. 지금 H2는 이미 가입돼 있으므로 웹에서 재가입 대신 기존 기기를
에어컨에 바인딩했다. NVS 초기화나 펌웨어 변경은 하지 않았다.

로컬에는 H2 명령 송신·결과 요청 ID 대조·18초 응답 대기·무재시도, 에어컨당
H2 연결과 해제 API, 화면의 ‘송신기 연결’·‘에어컨 끄기’ 동작을 구현했다.
`power_off` 외 명령은 서버와 화면에서 막는다. 로컬 검사에서 일반 Python
테스트 210개 통과·2개 건너뜀, UI 테스트 6개 통과, 변경 Python 파일 Ruff
통과. Windows의 `tests/test_h2_ir_firmware.py`는 유니코드 경로의 호스트 C
컴파일러 문제로 이 회차 테스트에서 제외했다.

Pi의 기존 웹 파일 다섯 개를 확인했다. 둘은 문서화된 과거 배포 해시,
나머지 셋은 기존 로컬 기준본과 일치했다. 다섯 파일을 Pi 안에 백업하고
단방향 배포 후 체크섬을 검증했다. 웹 서비스를 재시작했을 때 열린 연결의
종료 대기로 약 90초간 `deactivating`이었고 이후 `active (running)` 및
`Application startup complete`를 확인했다. 배포 과정에 Zigbee2MQTT, 펌웨어,
기존 센서 저장 데이터는 변경하지 않았다.

Tailscale 경유로 `/health=ok`, 에어컨 등록 1대, H2 지원·인터뷰 성공 1대,
웹 화면 HTTP 200과 등록 안내 문구를 확인했다. 그 에어컨에 H2 바인딩을
저장하고 다시 읽었을 때 `type=h2_ir`이었다. **이번 웹 검증에서는 IR 명령을
보내지 않았다.** 따라서 웹 버튼에서 실제 에어컨이 꺼지는지는 아직 현장 확인
전이다.

[로컬 검사 TXT](../assets/terminal/361-h2-web-control-local-checks.txt),
[PNG](../assets/terminal/361-h2-web-control-local-checks.png).
[Pi 배포·등록 TXT](../assets/terminal/362-h2-web-control-pi-deployment.txt),
[PNG](../assets/terminal/362-h2-web-control-pi-deployment.png).
