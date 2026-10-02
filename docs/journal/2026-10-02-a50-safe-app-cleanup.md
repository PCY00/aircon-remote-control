# 2026-10-02 — A50 일반 앱 정리와 원격 운영 보존

## 범위와 조건

사용자는 남은 작업 중 1번인 앱·자원 정리를 진행하라고 요청했다.
휴대폰과 떨어져 있어 직접 조작할 수 없다고 명시했다.
기존 SSH·페어링 ADB와 관리 앱 0.4.0을 사용했고 새 연결값 입력·허용 버튼·사진을
사용자에게 요구하지 않았다. 정상 재부팅 검증 외 별도 초기화는 하지 않았다.
Pi에는 접속·배포하지 않았고 중앙 API·데이터베이스·FCM은 구축 전이다.

## 읽기 전용 기준 측정

scripts/android/inspect_a50_resources.py를 추가했다. 실제 기기를 검증한 뒤
메모리·CPU·전원·앱·프로세스·관리 앱 상태를 읽는다.
전체 원문은 Git 제외 tmp/에 저장하고 공개 기록에는 주소·식별값·앱 사용자·
데이터 디렉터리 식별값을 제외한 필요한 출력만 보존했다.

동일 부팅·USB 충전·화면 꺼짐 표본에서 MemAvailable은 정리 직전
1,518,352 KiB(1482.8 MiB), 직후 1,510,472 KiB(1475.1 MiB)였다.
free만 늘었고 available 개선은 확인되지 않았다. 캐시·zRAM을 비우지 않았다.
dumpsys cpuinfo TOTAL은 각각 2.8%, 1.5%였지만 서로 다른 시간 표본이다.
정리 효과로 CPU가 특정 비율만큼 개선됐다고 주장하지 않는다.
top의 첫 표본은 측정 프로세스의 초기 실행 영향을 받으므로 3초 간격 두 번째도 읽었다.

높은 load average와 D 상태 커널 작업 17개가 함께 보였다.
보안·제조사 작업(tz_worker_threa, scsi_srpmb_work, ree_time, tz_iwsock,
simpleinteracti)이었으며 procs_blocked는 두 표본 모두 0이었다.
일반 Linux 부하는 실행 작업·중단 불가능한 대기를 함께 세므로 높은 숫자만으로
CPU 과부하를 단정하지 않았다. 정확한 제조사 커널 대기의 원인은 미확정이다.
강제 종료·루팅·커널·전원 관리 변경은 하지 않았다.

## 사전 검사 실패와 수정

1. 135: 실제 dumpsys 출력의 Package 뒤 공백·CR 처리가 맞지 않아 활성 상태
   파싱을 거부했다. 앱 변경 전에 중단했다. Hidden system packages의 옛 상태를
   섞지 않도록 활성 Packages 영역과 출력 형식을 수정했다.
2. 136: sharedUser가 있으면 모두 거부하는 검사 때문에 Maps에서 중단했다.
   추가 확인 결과 Maps·Android Auto·AR는 자기 패키지 이름의 sharedUser이며
   실제 UID 사용 목록에서도 각각 자기 패키지 하나뿐이었다.
3. 검증된 단독 사용만 허용하고 공용 시스템 UID·상시 앱·라이브러리 제공 앱은
   계속 거부했다. 해당 예외와 복원 기본/명시적 상태를 포함한 6개 검사를 추가했다.
4. 137: 실제 미리보기 정상. 28개 보호 대상·별도 SSH·각 대상 상태 확인 완료.
   최초 상태 기록은 Git 제외 .deploy/a50/에 저장했으며 이후 덮어쓰지 않는다.

## 실제 적용

139에서 YouTube, Google TV, Photos, Drive, Gmail, Maps, Meet/Duo,
Android Auto, Google Play Services for AR, Game Launcher 총 10개를
pm disable-user --user 0으로 변경했다. 삭제·pm clear·계정 등록 정보 삭제는 없었다.
다음 앱마다 설치 유지·enabled=3·데이터 디렉터리 식별값 유지와 핵심 28개 활성을
확인했다. 실제 데이터 내용 전체의 동일성을 검사한 결과는 아니다.
GMS, Google Services Framework, Play Store, WebView, 설치·권한 관리자,
홈·설정·키보드·전화·블루투스·네트워크·충전·관리 앱은 유지했다.

YouTube의 전후 실제 ADB 화면은 공개 자료 06·07이다. 사용 중지 후 ‘켜기’ 버튼과
설치 용량 유지가 보인다. 대상 10개 중 기존에 실행 중이던 4개 PSS 합계
196,464 KiB가 이후 목록에서 없어졌다. 전체 메모리 절감량으로 표현하지 않는다.
전체 MemAvailable은 약 7.7 MiB 감소했으며 설정 화면 실행 등 다른 변화도 있었다.
개별 앱 실행 제한은 완료지만 뚜렷한 전체 메모리 개선은 입증하지 못했다.

## 복원·검증

scripts/android/a50_app_cleanup.py 기본 동작은 미리보기다.
--restore --apply는 보존한 최초 enabled=0이면 default-state, 1이면 enable로
복원한다. 원래 상태를 강제로 1로 통일하지 않는다.
실제 전체 복원이나 장애를 강제로 만드는 복원 시험은 실행하지 않았다.
로컬 pytest 검사 17개(정리 6개+기존 접속 11개)와 관련 Ruff 검사가 통과했다.

정리 후 정상 재부팅을 1회 실행했다. 명령 응답은 10초 시간 초과여서 요청을
반복하지 않았다. 최초 명령부터 실제 검증된 ADB 연결까지 121.2초였다.
기기의 자체 부팅 복구가 집 Wi-Fi 허용창을 확인했고 PC의 SSH 복구 RPC는
필요하지 않았다. SSH도 독립 응답했고 28개 보호 앱·10개 사용 중지 상태·
설치·데이터 디렉터리 식별값·잠금 없음 저장값·Termux partial wake lock을 확인했다.
홈 화면에서 화면을 끈 뒤 15초 간격 8회 ADB 연결을 검증하고 2분 뒤 SSH도
응답했다. 최종 관리 상태는 interactive=false, service_connected=true, wifi_adb=1.
정리 후 재부팅·화면 꺼짐 단기 검증은 통과했다. 실제 원문은 141이다.

## 증거와 남은 작업

공개 실제 명령 기록: 135~141 TXT와 같은 이름 PNG.
실제 폰 화면: docs/assets/hardware/galaxy-a50-server/06·07 PNG.
블로그: docs/blog/mobile-app/02-a50-central-server.md.
공개 자료 최종 검사는 142 TXT/PNG에 보존했다. 변경 문서·기록 13개에서
비공개 설정값 검출 0, 상대 링크 누락 0, 자료 전체 이미지 185개에서
PRIVATE_METADATA_COUNT=0을 확인했다. 최초 상태와 원문 작업 폴더의 Git 제외도 확인했다.
다음 범위는 중앙 서비스 기반 구축이다. 다른 네트워크·장시간 가동·실제 API 응답·
FCM 발송·가구 격리를 이번 단기 앱 정리 시험의 성공으로 기록하지 않는다.
