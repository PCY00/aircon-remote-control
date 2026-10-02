# 가족 스마트홈 앱·공기계 중앙 서버 — 진행 중 기록

상태: 2026-10-02, SM-A505N 공개키 SSH·무선 ADB 자동 관리의 초기 검증 완료. 드래그 잠금을 없앤 뒤 수동 조작 없는 재부팅 복구·5분 ADB 유지·화면 꺼짐 2분 SSH/ADB를 확인했다. 일반 앱 정리 뒤 중앙 API·SQLite·서비스 감독을 설치했다. 같은 Wi-Fi·충전·암호 없는 조건이다. 실제 Google 로그인·시험용 외부 HTTPS·집 등록을 A50의 배포 APK로 확인했다. 서버 0.3.0과 앱 0.2.0의 FCM 설치 등록도 완료했다. 전용 서버 키 연결 후 실제 FCM 콜백·알림 게시를 백그라운드와 화면 꺼짐 즉시 시험에서 확인했다. 다른 가족 단말·장시간·실제 Pi 연결은 남아 있다.

기존 IR·Zigbee/MQTT·PCB 시리즈와 구분해 Android 앱과 가구별 중앙 서비스를 기록한다.
사용자와 1편의 범위를 원격 관리 준비까지로 합의했다. 2편은 운영 환경 최적화와
중앙 서버 구축이다. 이후 편수는 가구 권한·APK·FCM 검증 진행에 맞춰 정한다.

## 블로그 구성

1. [A50 초기화·SSH·백그라운드·재부팅 복구](01-galaxy-a50-preparation.md): SSH·ADB 자동 관리 초기 검증 완료, 장시간·다른 네트워크 조건은 후속 시험.
2. [운영 환경 정리·중앙 서버 구축](02-a50-central-server.md): 앱 정리·중앙 API 기반·SQLite·프로세스 복구·조작 없는 재부팅·화면 꺼짐 2분 시험 완료. 가구 인증·FCM은 후속 작업.
3. [Google 로그인·집 등록·가족 권한](03-household-permissions.md): Firebase 무료 프로젝트·Google 제공자 설정, A50 0.2.0 배포와 서명한 가상 계정으로 가구 격리 검증 완료. 실제 APK 로그인·FCM·Pi 연결은 후속 작업.
4. [가족 Android APK·Google 로그인 연결](04-family-android-app.md): 앱·지문 등록, 실제 구성의 production APK 빌드·서명·시험 토큰 제외·A50 설치와 시작 화면 확인 완료. 사용자가 다른 휴대폰에서 실제 계정 로그인 성공을 확인했다. 외부 서버 연결은 검증 전.
5. [다른 휴대폰에서 A50 연결](05-external-https-connection.md): 시험용 HTTPS 터널·외부 TLS·인증 차단 확인. [보충](05a-a50-user-google-login.md)에서 A50의 실제 Google 계정·배포 APK로 집 등록·소유자 화면·앱 재실행 검사를 통과했다. 고정 주소는 후속 준비.
6. [가족에게만 보내는 FCM 알림](06-family-fcm-notifications.md): 서버 0.3.0·앱 0.2.0 배포, 전용 서버 키·실제 계정 설치 등록, 백그라운드·화면 꺼짐 조건의 실제 FCM 콜백·알림 게시 확인 완료. 다른 가족 단말·장시간·실제 Pi는 후속 검증.
7. [Raspberry Pi 기록을 가족 알림으로 연결](07-raspberry-pi-event-relay.md): 독립 연결 서비스·만료시간 유지 구현, 로컬 88개·Pi Linux 2개 검사, 실제 배포 미리보기·A50 0.3.1 반영·실제 Google 소유자 확인 완료. Pi 키 발급·집 연결·자동 전송 승인 대기.
8. 이후: 다른 가족 단말·장시간 시험·고정 주소 준비.

1편 보충 자료: [SSH 세부 기록](02-termux-private-ssh.md),
[백그라운드·부팅 세부 기록](03-background-recovery.md).
보충 자료의 기존 파일명 번호는 블로그 편수를 뜻하지 않는다.

5편 보충 자료: [A50 화면을 노트북에 띄워 사용자 직접 Google 로그인](05a-a50-user-google-login.md).

## 기록 기준

- 실제 기기 상태와 실행 로그를 바탕으로 작성한다.
- 계획·성능 추정·실제 검증을 구분한다.
- 터미널 기록은 민감정보를 제거한 TXT와 PNG를 함께 보존한다.
- 기록 PNG는 실제 출력의 재구성 자료임을 밝힌다.
- 사용자에게 필요한 실물 사진을 해당 단계 직전에 요청한다.
- 일반 SSH 접근과 Android 설정 화면 접근을 구분한다.
- 현재 노트북은 개발 도구로 사용하며 중앙 서버 운영 설정을 바꾸지 않는다.

설계 제안: [가구별 권한·FCM](../../plans/mobile-app-household-notifications.md)

진행 기록: [2026-10-01 준비](../../journal/2026-10-01-android-central-server-preparation.md)

검증 기록: [2026-10-02 화면 꺼짐·재부팅](../../journal/2026-10-02-a50-background-ssh-verification.md)

앱 정리 기록: [2026-10-02 안전한 앱 사용 중지](../../journal/2026-10-02-a50-safe-app-cleanup.md)

서버 기반 기록: [2026-10-02 중앙 서버 실행 환경](../../journal/2026-10-02-a50-central-runtime.md)

가족 권한 기록: [2026-10-02 Firebase·집별 접근 분리](../../journal/2026-10-02-a50-household-permissions.md)

사진 목록: [A50 자료](../../assets/hardware/galaxy-a50-server/README.md)
