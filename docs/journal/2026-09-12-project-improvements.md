# 2026-09-12 전체 코드 점검과 안정성 개선

## 범위와 실행 상태

사용자가 전체 개선 가능 사항 점검과 수정을 요청했다. 웹 UI, API/저장소,
ESP32-H2 펌웨어와 새 PC용 빌드 절차를 병렬로 검토했다.
로컬 기준본만 수정했다. Raspberry Pi 배포·서비스 재시작·실제 IR 송신·보드 플래시는
수행하지 않았다. 운영 데이터, 등록 정보, 배선과 GPIO8 설정도 변경하지 않았다.

기존 Python 테스트는 74개 모두 통과했지만 동시 명령, 지연된 응답, 다중 에어컨과
RMT 타임아웃 경로를 충분히 검사하지 않았다. 해당 조건을 새 회귀 테스트로 추가했다.

## 발견한 문제와 수정

| 영역 | 증상·원인 | 수정 및 검증 기준 |
| --- | --- | --- |
| 여러 에어컨 | 재접속 때 첫 기기만 복원하고 화면이 단일 상태를 공유 | 등록된 에어컨과 공간을 모두 복원하고 기기 ID별 상태 유지 |
| 빠른 장면 | 장면의 타일만 선택하고 마지막 상세 화면의 기기 ID로 전송 가능 | 전송 대상 ID를 명시적으로 고정하고 실제 함수 호출을 테스트 |
| 명령 중 화면 이동 | 늦은 성공/실패 응답이 다른 에어컨의 화면을 변경 가능 | 요청 대상의 상태만 갱신·복구하고 같은 기기 중복 전송 차단 |
| 서버 명령 동시성 | 실제 송신 순서와 마지막 저장 상태가 역전 가능 | 명령 해석→송신→상태 저장→알림을 서비스 잠금으로 직렬화 |
| 센서 과거 보고 | 오래된 source timestamp의 패킷이 최신 문 상태를 되돌려 가짜 이력 생성 가능 | SQLite 트랜잭션에서 엄격히 오래된 보고의 상태 변경만 무시하고 수신 시각은 기록 |
| 센서 화면 경쟁 | REST 요청 대기 중 들어온 SSE 최신 상태를 낡은 REST가 덮어씀 | 수신 시각 비교 및 동률일 때 요청 중 발생한 실시간 갱신 우선 |
| 문 이력 조회 | 응답 도착 순서 역전 또는 조회 실패로 기존 이력이 바뀌거나 사라짐 | 요청 순번 검사, 실패 시 기존 이력 유지와 재조회 안내 |
| 센서 표시 설정 | 이름·공간 변경을 다른 탭에 알리지 않음 | 저장 후 센서 변경 이벤트 발행 |
| 자동 갱신 설정 | 시작/종료가 같은 시각인 오류를 고친 뒤에도 브라우저 유효성 오류가 남음 | 입력 시 사용자 정의 유효성 오류 해제; 저장소 쓰기 실패도 안내 |
| SQLite 연결 | `with connection`이 트랜잭션은 마치지만 연결을 닫지는 않음 | 센서/자동화 저장소 연결을 finally에서 닫고 예외 롤백 및 close 테스트 |
| ESP32-H2 RMT | 전송이 끝나기 전 timeout으로 함수가 반환하면 스택의 파형 버퍼가 무효화될 위험 | 정적 버퍼 유지, 오류 시 송신 중단 시도 및 추가 송신 차단; 중단 실패도 테스트 |
| ESP32-H2 시험 | 긴 카메라 시험을 여러 명령으로 반복해야 함 | `5` 명령: 명목 5초, 25회 짧은 burst. 실제 에어컨 명령 아님 |
| 새 PC 빌드 | 이전 PC의 COM 포트 기본값, 도구 경로 덮어쓰기, 서로 다른 작업 폴더의 빌드 충돌 | flash/monitor에 COM 필수, 기존 도구 경로 보존, 체크아웃별 ASCII 빌드 경로, 잘못된 타깃 차단 |

### 구체적인 원인 확인

- 기존 서버 동시성 재현에서 송신은 `cool_24_high` → `power_off`였지만 마지막 저장
  명령은 `cool_24_high`로 남는 경우를 확인했다. 전송 드라이버에만 잠금이 있으면
  송신 후 저장 순서까지 보장하지 못하므로 서비스 전체 처리 구간에 잠금을 추가했다.
- 과거 도어 보고가 현재 상태를 덮어쓰는 재현에서는 실제 새 전환이 아닌 과거 패킷 때문에
  `open`, `closed` 이력이 추가됐다. 동일 타임스탬프나 타임스탬프가 없는 보고는
  무조건 버리지 않는다. 같은 초 안의 정상 개폐를 보존하는 테스트도 추가했다.
- SQLite 연결 미종료는 Windows 임시 DB 정리에서 `WinError 32`로도 드러났다.
  연결 소멸 시점을 가비지 컬렉터에 맡기지 않도록 수정했다.
- 펌웨어의 기존 packet bytes, pulse/space, 프레임 수, GPIO8, 38 kHz 설정과 duty는
  유지했다. 데이터 상수만 `main/carrier_profile.h`로 분리했다.

## 로컬 검증

아래 명령은 저장소 루트에서 실행한다. 모든 테스트의 장치/통신 의존성은 mock/stub이며
실제 에어컨 제어를 하지 않는다. C 호스트 테스트는 실제 `main.c`를 컴파일해 기존
Pi 프로필과 OFF/ON 전체 파형을 비교한다(마지막 RMT 종료용 1 µs idle은 별도 처리).

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
node --test tests/test_device_ui.cjs tests/test_sensor_refresh_policy.cjs
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/esp32_h2_firmware.ps1 build
```

- Python: **94 passed in 50.06s**. 새 테스트 20개 포함.
- Node: **23 passed, 0 failed, 0 skipped**.
- Ruff: **All checks passed!** 기존 변환 스크립트의 import 간격 오류도 정리했다.
- 의존성: `python -m pip check` → **No broken requirements found.**
- ESP-IDF 5.5.4 실제 빌드: **exit code 0**, `Project build complete.` 확인.
  앱 `aircon_h2_ir_node.bin` 185,504 bytes, bootloader 22,160 bytes,
  partition table 3,072 bytes 생성. 앱 파티션 여유 공간 82%.
- `Get-FileHash -Algorithm SHA256`으로 로컬과 `BUILD_DIRECTORY`의 CMakeLists.txt,
  sdkconfig.defaults, main/CMakeLists.txt, main/main.c, main/carrier_profile.h를 비교해
  **5/5 일치**를 확인했다. 이는 빌드 소스 일치 확인이지 보드 설치 상태 확인이 아니다.
- 첫 실행은 별도 스테이징 경로에서 ESP-IDF 공통 구성요소와 bootloader까지 컴파일해
  오래 걸렸다. 스테이징에는 `.git`을 복사하지 않아 `git describe` 기반 버전 판별
  메시지가 나왔으나, 컴파일 오류는 아니며 최종 바이너리가 생성됐다.

실제 실행 결과의 발췌는 [캡처 71 원문](../assets/terminal/71-project-improvement-verification.txt)과
[동일 내용 PNG](../assets/terminal/71-project-improvement-verification.png)에 보존한다.
실제 펌웨어 빌드는 [캡처 72 원문](../assets/terminal/72-h2-ir-improved-build.txt)과
[동일 내용 PNG](../assets/terminal/72-h2-ir-improved-build.png)에 별도로 보존한다.

## 공개 자료·개발 환경 정리

- 원본 원격 첨부, 펌웨어 build/managed_components/sdkconfig와 ZIP은 Git 제외 대상으로
  추가했다. 파일을 삭제한 것은 아니며 `.gitignore`가 사진 메타데이터를 제거해 주는
  것도 아니다. 공개 사진은 계속 sanitizer를 거친다.
- README의 매 단계 승인 문구를 현재 AGENTS.md의 범위별 사전 안내 규칙과 맞췄다.
- 새 PC 인수인계에서 카메라 발광과 정확한 반송파 측정을 구분했다. HW-477은
  복조된 pulse/space 비교용이며 정확한 38 kHz 반송파 실측 장비가 아니다.
- 공개 이미지 최종 검사: `python scripts/sanitize_blog_images.py docs/assets/` →
  **IMAGE_COUNT=101, PRIVATE_METADATA_COUNT=0**. 캡처 71·72 PNG는 직접 열어 가독성도 확인했다.
- 빌드 스테이징 경로는 helper가 출력하는 `BUILD_DIRECTORY`를 따른다. 기존
  `C:\esp\aircon-h2-ir-node-build`와 과거 ZIP은 자동 갱신되지 않는 이전 자료다.
  다른 PC에는 저장소의 펌웨어 폴더와 helper 최신본을 함께 전달한다.

## 남은 항목과 한계

1. ESP32-H2의 카메라 발광은 확인됐지만 **실제 에어컨 POWER_OFF 성공은 미확인**이다.
   개선본을 플래시하지 않았고, 출력 주파수·파형 재수신·광출력 검증도 이번에 하지 않았다.
2. ESP32-H2 간헐적 USB 재연결과 Pi USB/Zigbee 장애의 물리적 원인은 별도 검증 대상이다.
   이번 코드 수정으로 해결됐다고 주장하지 않는다.
3. 빠른 장면 및 수동 공간 편집 전체를 서버에 영구 저장하는 모델은 아직 없다. 기기에
   저장된 공간 복원과는 별개다. 재시작·여러 화면 동기화를 위한 후속 작업으로 남긴다.
4. 기기 명령 잠금은 **단일 서비스 프로세스** 기준이다. 현재 단일 worker 운영에는 맞지만
   다중 worker로 늘리려면 프로세스 간 명령 큐·잠금 설계가 필요하다.
5. 센서 source clock이 과거로 돌아가는 경우는 타임스탬프만으로 늦은 패킷과 구분할 수
   없다. 임의 DB 삭제로 우회하지 말고 게이트웨이 시각·보고 원문을 먼저 확인한다.
6. 빌드 스테이징 복사는 소스에서 제거된 파일을 삭제하지 않는다. 향후 파일 삭제/이동
   때는 새로운 ASCII `-BuildRoot`로 깨끗하게 빌드해 오래된 헤더의 영향을 배제한다.
7. Zigbee IR 통합, PCB·배터리 제품화, 공용 인터넷 접근 구조는 이번 안정성 수정의
   범위가 아니며 기존 단계 계획대로 별도 진행한다.
