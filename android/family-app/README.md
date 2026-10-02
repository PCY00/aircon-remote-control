# 가족 스마트홈 Android 앱

2026-10-02: Google 로그인·집 등록·가족 초대 화면 구현, 시험 APK 빌드·서명 검증,
Android 단위 검사 2개와 A50 실기기 UI/API 검사 2개 통과. Firebase 앱·두 지문 등록 완료.
실제 Firebase 구성 검증·production 개발/배포 APK 빌드·서명·시험 토큰 제외 검사 완료.
A50에 배포 APK를 설치하고 Firebase 초기화·로그인 시작 화면을 확인했다.
사용자가 다른 휴대폰에서 실제 계정 Google 로그인 성공을 확인했다.
외부 서버 연결·서버의 실제 토큰 검증·FCM은 아직 검증 전이다.
기존 a50-manager와 독립된 앱이다. 결과는 블로그 4편·날짜별 기록에 남긴다.

## 준비물

- 이 저장소와 Windows의 Python 가상환경.
- Android 8 이상 휴대폰, Google 계정과 Google Play 서비스.
- 무료 Firebase 프로젝트의 Google 로그인 제공자.
- 기존 A50 SSH/ADB 관리 설정(실제 값은 .deploy/a50 아래, Git 제외).
- Google 로그인이 허용된 앱 서명 키와 Firebase Android 앱 등록.
- HTTPS 중앙 서버 주소. 현재 A50 서버는 내부 연결만 있어 외부 연결 작업이 필요하다.

## 재현 순서

1. 기존 A50 관리 준비·중앙 서버·가족 권한 단계를 블로그 1~3편 순서로 완료한다.
2. 로컬에서 `python scripts/android/prepare_family_tools.py`를 실행한다.
   공식 Android SDK 36·Build Tools 36.0.0·Platform Tools와 Gradle 8.13을 체크섬 검증 후 로컬 캐시에 설치한다.
   JDK 17은 앞선 관리 앱 빌드 도구를 재사용한다. 설치 도구가 SDK의 공식 라이선스 기록을 만든다.
   다른 환경에서는 JDK 17을 준비하고 `--java-home <JDK_17_절대경로>`를 지정하거나 JAVA_HOME을 설정한다.
3. `python scripts/android/prepare_family_signing.py`로 가족 앱 전용 서명 키를 만든다.
   기존 관리 앱의 키는 그대로 유지한다. 서명 키·비밀번호는 저장소 밖에서 보관한다.
4. Firebase Console → 프로젝트 설정 → Android 앱 추가.
   패키지 `com.aircon.family`, 닉네임 `가족 스마트홈`으로 등록한다.
   로컬 .deploy/family-app/signing.json의 공개 SHA-1·SHA-256 지문을 프로젝트의 앱에 추가한다.
   개인 키와 비밀번호를 업로드하지 않는다. 앱 패키지 이름은 이후 바꿀 수 없으므로 정확히 입력한다.
5. Firebase의 google-services.json을 받아 `.deploy/family-app/google-services.json`에 저장한다.
   Google OAuth 웹 클라이언트 ID가 포함된 최신 파일을 사용한다. 이 설정 파일은 Git에서 제외한다.
   `python scripts/android/import_family_firebase.py --source "<다운로드한 파일 경로>" --project-id <프로젝트 ID>`로
   프로젝트·Android 패키지·전용 SHA-1·웹 클라이언트를 확인하고 비공개 폴더에 복사할 수 있다.
6. `python scripts/android/build_family_app.py`로 단위 검사·개발/배포 APK를 빌드한다.
   소스는 로컬 android/family-app이 기준이며 빌드는 별도 ASCII 경로에서 수행한다.
   서명 키나 설정 파일을 앱 소스 폴더에 복사하지 않는다.
7. 결과는 `tmp/family-app-build/family-debug.apk`, `family-release.apk`이다.
   개발 APK는 같은 A50의 루프백 HTTP 주소만 시험용으로 허용한다.
   배포 APK는 HTTPS만 허용하며 소유자가 안내한 서버 주소를 설정해야 한다.
8. `python scripts/android/verify_family_apk.py`로 실제 서명·Firebase 구성 포함·시험 토큰 제외·
   manifest가 참조하는 HTTPS 정책을 검사한다.
9. 관리 연결이 준비된 A50에 설치하려면 아래 순서로 미리보기와 실제 반영을 구분한다.

```text
python scripts/android/install_test_family_app.py --production-only --release
python scripts/android/install_test_family_app.py --production-only --release --apply
```

2026-10-02 배포 APK 0.1.0: 3,888,953바이트.
SHA-256: `30842377eaaba3626b9dd80c7888a092e99227927f265e23d4c4a6e8406ca12b`.
실제 Google 계정이 있는 휴대폰에서 설치 후 ‘Google로 계속하기’를 선택한다.
로그인 뒤 서버 주소가 없으면 연결 설정 화면을 보여 준다. 아직 실제 외부 서버 주소는 제공되지 않았다.

google-services.json의 앱 구성 정보는 APK 안에 포함되는 클라이언트 정보다.
Firebase 서버 관리 권한을 주는 서비스 계정 개인 키를 APK에 넣지 않는다.
Firebase 구성 값으로 집 권한을 부여하지 않고, 중앙 서버가 사용자 토큰과 현재 가족 등록을 검사한다.

## 앱 동작

- Google Credential Manager → Google ID 토큰 → Firebase Authentication 로그인.
- Firebase ID 토큰을 중앙 API에 보내 현재 집 목록을 가져온다.
- 새 집 만들기, 이메일과 역할로 초대 발급, 지정 계정의 초대 수락.
- 소유자만 가족 관리·역할 변경·참여 해제·기기 등록.
- 집·알림 기록 조회와 로그아웃. 계정 변경 뒤 오래된 응답은 화면에 반영하지 않는다.
- 인증·서버 장애 때 성공한 화면을 꾸미지 않고 오류를 표시한다. POST는 자동 재전송하지 않는다.
- FCM과 기기 실물 연결·제어 API는 후속 작업이다.

## 독립된 실기기 동작 시험

실제 Google 계정을 대신 조작하지 않는다. 원격 기기에 계정이 없으면 실제 로그인 시험은
사용자가 계정이 있는 휴대폰에서 실행할 때 확인한다.

```text
python scripts/android/prepare_family_fixture.py
python scripts/android/build_family_app.py --fixture-only
python scripts/android/verify_family_apk.py
python scripts/android/install_test_family_app.py
python scripts/android/install_test_family_app.py --apply
python scripts/android/stop_family_fixture.py
```

fixture 빌드는 별도 패키지 `com.aircon.family.fixture`와 가상 계정 표시를 사용한다.
시험 서버는 127.0.0.1:8765와 임시 저장소를 사용하며 운영 DB와 계정을 변경하지 않는다.
40분 후 스스로 종료한다. 실제 검증 코드는 시험용 RSA 서명과 집별 권한을 검사한다.
시험 토큰은 .deploy와 별도 fixture APK에만 포함하며 production APK에는 들어가지 않는다.
최종 시험 절차·결과·캡처는 완료한 실행에 근거해 기록한다.
실제 Google 구성 파일이 준비됐다면 `--fixture-only` 대신 `--tests`로 production APK도 빌드한다.
시험 뒤 fixture 서버를 종료하면 시험 APK의 화면 데이터 연결도 종료된다.

## 공식 문서

- [Firebase Android Google 로그인](https://firebase.google.com/docs/auth/android/google-signin)
- [Credential Manager Google 로그인](https://developer.android.com/identity/sign-in/credential-manager-siwg)
- [Firebase Android 설정](https://firebase.google.com/docs/android/setup)
