# Galaxy A50 중앙 서버 후보 — 실제 화면 자료

2026-10-02: Wi-Fi ADB로 직접 캡처한 공개용 화면 7장을 보존했다.
원본 작업용 화면은 Git 제외 임시 폴더에서 관리하며, 계정·주소·인증값이 있는
화면은 공개 폴더에 넣지 않는다.

| 자료 | 상태 |
| --- | --- |
| 초기화 재부팅·환영 사진 | 사용자 요청으로 생략 |
| 모델·OS·보안 패치 | ADB 실제 출력으로 SM-A505N, Android 11, 2023-02-01 확인 |
| Termux 실행 | 01-termux-background-preparation.png |
| SSH 준비 완료 실제 폰 화면 | 02-termux-public-key-ssh-ready.png |
| Termux:Boot 최초 실행 | 03-termux-boot-first-launch.png |
| 자체 관리 앱 최초 설정 | 04-a50-management-auto-recovery.png; 설치 직후 실제 화면, 지속 연결 증거는 아님 |
| 0.4.0 재부팅 후 관리 앱 | 05-a50-manager-v04-after-no-swipe-reboot.png; 드래그 잠금 제거 후 수동 조작 없는 재부팅 뒤 실제 화면, 연결 검증은 기록 130 |
| 앱 정리 전 YouTube 정보 | 06-youtube-before-disable.png; 실제 사용 중지 버튼 |
| 앱 정리 후 YouTube 정보 | 07-youtube-after-disable.png; 사용 안함·켜기 버튼, 설치 데이터 보존 |
| Firebase Google 로그인 제공자 | firebase-google-enabled.jpg; 실제 노트북 콘솔, Google 사용 설정됨·Spark 무료, 개인 계정 영역 제외 |
| 화면 꺼짐·재부팅 접속 | 실제 명령 기록 85·92 TXT/PNG |
| 메모리·저장 공간 | 실제 명령 기록 93 TXT/PNG |

초기화 사진을 얻기 위해 초기화를 반복하지 않는다.
화면의 메시지만으로 SSH 성공을 주장하지 않고 실제 원격 응답을 근거로 삼는다.
Terminal PNG는 실제 출력 재구성이며 이 폴더의 실제 화면 캡처와 구분한다.

공개 이미지 메타데이터는 scripts/sanitize_blog_images.py로 정리하고
게시 전 PRIVATE_METADATA_COUNT=0을 확인한다.
