# A50 관리 자동 복구 앱

Android 11 A50 시험 서버에서 재부팅 후 무선 디버깅을 복구하기 위한 내부 관리용 앱이다.
실물 설치본과 로컬 소스는 0.4.0이다. 설치 APK의 SHA-256 일치와 서비스 연결을 확인했다.
고객용 스마트홈 APK나 중앙 API를 구현한 앱은 아니다.

## 동작과 권한

- 기존 Android TLS 무선 디버깅·페어링을 사용한다.
- 기존 Android Wi-Fi 허용창과 페어링을 사용한다. 소유자가 이미 허용한 Wi-Fi 이름을
  권한으로 보호된 최초 구성에서 Wi-Fi 이름과 접속 지점(BSSID)을 등록하고,
  두 값이 정확히 일치하는 시스템 무선 디버깅 허용창만 자동 확인한다.
- 접근성 서비스는 System UI·설정 창에만 연결된다. 무선 디버깅 문구·등록한 Wi-Fi의
  정확한 이름과 접속 지점·계속 허용 체크박스·허용 버튼을 확인한 경우만 조작한다.
  이름의 부분 일치, 다른 Wi-Fi, 일반 앱·권한창에는 동작하지 않는다.
- 접근성 권한 자체는 넓은 권한이다. 검토한 자체 코드에만 부여하며 어떤 창을 처리하는지는
  TrustedWifiApproval.java와 실제 재부팅 시험으로 확인한다. 네트워크 이름은 앱의
  비공개 환경설정에 저장하고 로그·공개 캡처에는 남기지 않는다.
- 변경하는 시스템 설정은 `adb_wifi_enabled=1` 하나다.
- 부팅 완료·자체 업데이트 시 Wi-Fi와 설정 권한을 확인하고 복구를 요청한다.
- Wi-Fi가 연결된 때의 보조 복구 작업을 15분 간격으로 예약한다.
  Android 절전과 JobScheduler가 실행 시점을 늦출 수 있으므로 즉시 복구 보장은 아니다.
- 루팅, 앱 삭제, 네트워크 초기화, 공개 인터넷 포트 개방은 수행하지 않는다.
- 자동 복구 끄기 버튼은 부팅 복구와 예약 작업을 중지한다.
  현재 무선 디버깅 설정을 강제로 끄지는 않는다.

요청하는 일반 권한은 RECEIVE_BOOT_COMPLETED, ACCESS_NETWORK_STATE,
WRITE_SECURE_SETTINGS와 WAKE_LOCK이다. 설정 권한은 시스템 설정을 바꿀 수 있는 넓은 권한이므로
검토한 자체 APK에만 최초 ADB 설정으로 부여한다. 구현은 위 설정 하나에 한정한다.
INTERNET 권한이나 사진·연락처·계정 권한은 요청하지 않는다. 접근성 서비스 바인딩은
Android 시스템 권한 BIND_ACCESSIBILITY_SERVICE로 보호한다.
복구 요청 때 화면을 15초만 깨우고 자동으로 만료시키는 Android 11용 구성이다.
화면을 끄고 무선 디버깅을 한 번 비활성화한 실제 시험에서 SSH 요청 후 약 9초 만에 복구됐다.
등록 구성 수신은 WRITE_SECURE_SETTINGS 권한이 있는 호출자만 허용한다.
StatusReceiver는 설정을 수정하지 않으며 식별정보 없는 상태만 SSH에 반환한다.
RecoveryReceiver는 비공개 난수 토큰이 일치한 요청만 처리한다. 토큰은 앱 비공개 설정과
Git 제외 로컬 설정에만 저장한다. Activity 시작 응답으로 성공을 추정하지 않고
실제 수신 응답과 ADB 기기 검증을 사용한다.

## 빌드와 최초 설정

Microsoft OpenJDK 17과 Google Android API 30·Build Tools 34를 휴대용으로 준비하고
공식 체크섬을 검증한다. `tmp/a50-build-tools/paths.json`의 실제 도구 경로를 사용한다.

    python scripts/android/build_a50_manager.py

빌드 소스는 이 폴더다. Windows aapt의 한글 경로 문제를 피하기 위해 패키징 단계만
ASCII 임시 경로에서 수행한다. APK는 `tmp/a50-manager-build/a50-manager.apk`에 생성한다.
서명 키와 서명 암호는 저장소 밖 사용자 전용 경로에 보관하며 명령 인자에 암호를 넣지 않는다.
같은 키를 보존해 업데이트를 설치한다.

설치 도구는 기본 실행 시 미리보기만 출력한다. 실제 최초 설치·업데이트는
페어링된 A50의 모델·식별자를 확인한 뒤 수행한다. 기존 앱 데이터와 다른 접근성
서비스 목록을 보존하며 현재 승인한 Wi-Fi/AP와 비공개 복구 토큰을 구성한다.

    python scripts/android/install_a50_manager.py
    python scripts/android/install_a50_manager.py --apply --configure-current-wifi

아래 개별 설치 명령은 참고용이다. APK 전송과 신뢰 구성도 필요하므로 도구 사용을 우선한다.

    adb shell pm install -r /data/local/tmp/a50-manager.apk
    adb shell pm grant com.aircon.a50manager android.permission.WRITE_SECURE_SETTINGS
    adb shell dumpsys deviceidle whitelist +com.aircon.a50manager
    adb shell am start -n com.aircon.a50manager/.MainActivity

APK 원격 전송과 각 명령은 확인된 A50에만 실행한다. 기존 기기 식별자를 검사하고
모호한 기기를 거부하는 `scripts/android/a50_adb.py`로 재접속한다.

    python scripts/android/a50_adb.py --rediscover -- shell getprop ro.product.model

## 실제 검증과 한계

서명·매니페스트 검사는 빌드 결과 기록 101에 보존한다.
0.1.0 설치·설정 권한 부여·화면 캡처를 기록 102에 보존했다. 재부팅 직후 실제 ADB·SSH
복구는 기록 103에서 확인했다. 이후 ADB가 끊기고 Wi-Fi 허용 팝업이 확인됐다(104).
항상 허용 뒤에도 재부팅 복구가 실패했다(105). 부팅 로그의 keyStore 파싱 오류와
현재 접속 지점의 실제 신뢰 저장을 확인했다(107). 시스템 파일을 덮어쓰거나
페어링 정보를 삭제하지 않았다. 0.2.0은 이미 허용한 Wi-Fi의 시스템 허용창을
자동 확인하며 설치·구성은 기록 110, 실제 재부팅·지속성 시험은 기록 112에 보존한다.
112에서는 240초 내 ADB 복구가 실패해 5분 지속·화면 꺼짐 후속 시험에 도달하지 못했다.
SSH에서 읽은 상태는 서비스 연결됨, wifi_adb=0이었다. 화면이 꺼진 때 실제 허용창을
조회할 수 있는지 점검했다. 화면만 켜는 것으로 0.2.0은 복구되지 않았다.
0.4.0에서 검사 대기를 매 이벤트마다 취소하지 않도록 수정하고 여러 시스템 창을 조회한다.
라이브 서비스 연결과 검사 횟수도 읽을 수 있다. 시스템 신뢰 파일 오류를 해결했다고 표현하지 않는다.
실제 창은 영어 제목·본문·체크박스와 한글 취소 버튼이 함께 표시됐다(123).
체크박스 런타임 ID는 android:id/alwaysUse이며 검토한 CheckBox 문구 조건으로 처리됐다.
SSH 복구 수락 응답 result=1에 TermuxAm 종료 코드 1이 함께 반환된 것을 확인했다.
클라이언트는 명시적 수락 응답과 종료 코드 0 또는 1을 함께 검사하도록 수정했다(124).
Wi-Fi 이름·접속 지점 판별 14개를 JVM에서 검사했다. 현재 ADB 선택·RPC 검증은 기록 126에 보존한다.
첫 0.4.0 재부팅은 드래그 잠금 해제에 사용자 도움이 필요했다(125). 사용자의 명시적 요청으로
암호 없는 기기의 잠금 화면을 Android 설정에서 없앴다(129). 앱에 보안 잠금 해제 기능을
추가하지 않았다. 잠금 설정 유지와 수동 조작 없는 재부팅 시험은 별도 기록 130이다.
130에서는 재부팅 명령 뒤 5초 대기 후 131.7초의 자동 발견 대기로 연결됐고 잠금 없음이
유지됐다. PC의 SSH RPC 없이 부팅 복구로 허용창 처리가 완료됐다. 5분 ADB 유지와
홈 화면·화면 꺼짐 2분 SSH/ADB 검사도 통과했다. 최종 읽기 상태는 interactive=false다(133).
같은 Wi-Fi·충전·암호 없는 초기 검증이며 24시간·외부 사설망·새 AP 조건은 미검증이다.
Wi-Fi 신뢰가 해제되거나 페어링 키가 만료·삭제된 경우, 처음 보는 Wi-Fi에 접속하는 경우,
관리 앱 강제 종료·절전 제한·권한 해제에는 추가 설정이 필요할 수 있다.
일반 서버용 SSH 부팅 복구는 Termux:Boot 경로로 별도 유지한다.

SSH만 연결될 때 상태 확인:

    am broadcast -a com.aircon.a50manager.STATUS -n com.aircon.a50manager/.StatusReceiver

PC의 ADB 도구는 기기 미발견 시 기존 검증된 SSH 키·호스트 기록으로 토큰 보호
복구 수신기를 호출하고 다시 발견할 수 있다. 호출은 최대 8회, 30초 이상 간격으로
연결 제한시간 안에서만 시도하며 설정 .deploy/a50/adb.json의 ssh_recovery_enabled로 제어한다.

공식 자료:

- https://developer.android.com/reference/android/Manifest.permission#WRITE_SECURE_SETTINGS
- https://developer.android.com/reference/android/app/job/JobInfo.Builder
- https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/dev/adb_wifi.md
