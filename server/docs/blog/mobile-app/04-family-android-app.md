# [편하게 살자] 스마트홈 알림 - Google 로그인하는 Android 앱을 만들었다

　서버가 사람과 집을 구분하게 만들었다. 이제 휴대폰에 설치할 앱을 만들기로 했다.

　그동안 쓰던 ‘A50 관리 자동 복구’ 앱은 서버용 폰을 관리하는 앱이다. 가족이 설치해서 집 소식을 보는 앱은 따로 만들었다. 두 앱의 역할이 다르다.

　먼저 Google 로그인부터 붙였다. 집 화면을 보여주기 전에 누구의 요청인지 알아야 하기 때문이다. 나는 다른 휴대폰에서 로그인이 되는 것을 먼저 확인했고, 뒤에는 A50에도 같은 가족 앱을 설치했다.

　**앞에서 준비할 것:** Google 로그인을 켜둔 본인 Firebase 프로젝트, PC의 Python 환경과 JDK 17. 아래 명령은 **PC PowerShell**에서 실행한다.

## 앱을 만든 사람을 구분할 키를 준비했다

---

　PC에 준비해둔 JDK 17을 다시 사용한다. PowerShell을 새로 열었다면 프로젝트 폴더로 이동하고 `$jdk17`에 본인 JDK 17 폴더를 다시 넣자.

```powershell
.venv/Scripts/python.exe scripts/android/prepare_family_tools.py --java-home $jdk17
.venv/Scripts/python.exe scripts/android/prepare_family_signing.py
```

　두 번째 명령이 가족 앱의 서명 키를 만든다. 서명은 나중에 앱을 업데이트할 때 같은 제작자가 만든 파일인지 구분하는 표시다. **개인 키와 암호 파일은 따로 안전하게 백업하자.** 업데이트할 때도 처음 키를 써야 한다.

　출력에는 SHA-1과 SHA-256이라는 공개 표시도 나온다. 이 표시는 Firebase에 등록하지만, 개인 키나 암호 파일은 올리지 않는다. 관리 자동 복구 앱과 가족 앱의 키도 따로 사용한다.

## Firebase에 이 앱을 등록했다

---

　Firebase Console → 프로젝트 설정 → 일반 → 내 앱에서 Android 앱을 추가한다.

| 입력할 것 | 넣는 값 |
| --- | --- |
| 패키지 이름 | `com.aircon.family` |
| 표시 이름 | 본인이 알아보기 쉬운 이름 |
| SHA-1과 SHA-256 | 방금 만든 가족 앱의 공개 표시 |
| Google 로그인 | 사용 설정을 켠 상태 |

　패키지 이름은 Android가 앱을 구분하는 이름이다. 여기서는 소스와 같은 `com.aircon.family`를 사용한다.

　설정을 저장한 뒤 **새 `google-services.json`을 내려받는다.** 이 파일은 앱이 어느 Firebase 프로젝트를 사용할지 알려준다. 시험 알림 글에서 만드는 서버용 비밀키와는 다른 파일이다.

```powershell
$firebaseProject = '본인의-Firebase-프로젝트-ID'
$googleConfig = 'C:\본인의_비공개_폴더\google-services.json'
.venv/Scripts/python.exe scripts/android/import_family_firebase.py --source $googleConfig --project-id $firebaseProject
```

　프로젝트, 패키지 이름, 서명 표시와 Google 로그인 설정을 확인하고 `.deploy/family-app`에 복사한다. 파일 내용은 출력하지 않는다.

　서명 표시를 등록하기 전에 받은 JSON을 그대로 쓰지 말자. 필요한 설정을 저장한 뒤 다시 내려받아야 앱에 맞는 정보가 들어간다.

## 설치할 APK를 만들었다

---

　APK는 Android 앱을 설치하는 파일이다. 아래 명령으로 소스를 APK로 만들고, 만들어진 파일의 서명과 로그인 설정을 확인한다.

```powershell
.venv/Scripts/python.exe scripts/android/build_family_app.py
.venv/Scripts/python.exe scripts/android/verify_family_apk.py
```

　처음에는 필요한 제작 도구와 파일을 받느라 시간이 걸릴 수 있다. 결과는 `tmp/family-app-build`에 나온다.

| 파일 | 용도 |
| --- | --- |
| `family-release.apk` | 일반 휴대폰에 설치할 앱. 서버 연결은 HTTPS를 사용한다. |
| `family-debug.apk` | 개발하면서 확인할 때 쓰는 앱 |

　내 APK를 그대로 설치하면 내 Firebase 설정을 사용하게 된다. 따라 만드는 사람은 **본인 프로젝트와 본인 서명 키로 만든 release 파일**을 사용하자.

　파일 비교에 사용하는 SHA-256도 사람마다 달라지는 것이 정상이다. 내가 만든 파일의 숫자와 맞추는 것이 아니라, 본인이 만든 파일과 복사한 파일이 같은지 비교하면 된다.

## 휴대폰에 설치하고 로그인했다

---

　A50에 설치할 때는 아래처럼 실행한다. 첫 명령은 설치할 파일만 보여주고, 두 번째가 실제 설치다.

```powershell
.venv/Scripts/python.exe scripts/android/install_test_family_app.py --production-only --release
.venv/Scripts/python.exe scripts/android/install_test_family_app.py --production-only --release --apply
```

　다른 휴대폰에는 같은 `family-release.apk`를 복사해 설치할 수 있다. 파일 앱에서 APK를 열고, 본인이 만든 파일인지 확인한 뒤 해당 파일 앱의 설치 허용을 잠깐 켠다.

　앱에서 ‘Google로 계속하기’를 누르고 본인 계정을 선택한다. A50에 Google 계정이 없다면 설정의 계정 추가부터 해야 한다. 비밀번호는 본인이 직접 입력한다.

![가족 앱의 실제 Google 로그인 시작 화면](../../assets/hardware/family-app/05-production-login.png)

　나는 A50과 떨어져 있을 때 PC로 그 화면을 보면서 직접 로그인했다. 계정을 추가하는 동안에는 캡처를 남기지 않았다. A50에도 가족 앱을 설치하고 설정에서 Google 계정을 추가한 뒤 로그인한다. 다른 휴대폰에서 이미 만든 집은 같은 계정으로 로그인하면 다시 보이므로 새 집을 중복으로 만들 필요는 없다. 서버 주소를 만든 다음에는 A50 앱에도 같은 주소를 저장하고 해당 집을 열어둔다.

## 로그인은 됐는데 서버 주소가 필요했다

---

　Google 로그인은 됐다. 그런데 다른 휴대폰에서 A50의 서버에 들어가려면 어디로 연결해야 할까?

　A50 서버 설치 글의 서버는 A50 안에서만 열려 있다. 다른 휴대폰에 `localhost`를 넣으면 그 휴대폰 자신을 찾는다. 그래서 다음에는 앱이 찾아갈 HTTPS 주소를 따로 만들었다.

　이 시점에 앱이 ‘연결 설정’을 보여주는 것은 다음 작업이 남았다는 뜻이다.

　로그인 오류가 나면 Google 사용 설정, 패키지 이름, SHA-1 등록과 새 JSON을 순서대로 확인하자. `INSTALL_FAILED_UPDATE_INCOMPATIBLE`은 기존 앱과 서명 키가 다르다는 뜻이다. 데이터를 지우기 전에 기존 앱을 어떤 키로 만들었는지 먼저 본다.

　**여기까지 확인할 것:** 본인의 설정으로 만든 앱이 설치되고 Google 로그인이 된다.

　이제 앱도 준비됐다. 다음은 밖에서도 A50에 연결할 주소를 만드는 일이다.
