# 시작 전에 준비할 것

이 시리즈는 남는 Galaxy A50을 작은 서버로 만들고, 집의 소식을 휴대폰 알림으로 받는 과정을 설명한다. 서버는 요청을 받아 기록을 보관하는 장비다. 여기서는 A50이 그 역할을 하고, 라즈베리파이는 집의 센서 기록을 보내는 역할을 한다.

1편부터 9편까지 순서대로 읽는다. **현재 제공하는 코드는 서버와 앱의 최신 상태인 0.4.0이다.** 글에 있는 예전 화면과 실행 결과는 당시 직접 해본 기록이다. 현재 코드를 설치하기 위해 예전 버전을 차례로 설치할 필요는 없다.

## 필요한 장비와 계정

- Windows PC 한 대. 명령어는 PowerShell에서 실행한다.
- Galaxy A50 SM-A505N. 이 글에서 직접 사용한 환경은 Android 11, One UI 3.1이다. 다른 모델에서는 배터리 설정이나 부팅 후 동작이 다를 수 있다.
- PC와 A50이 함께 연결된 집 Wi-Fi와 충전기.
- 본인의 Google 계정. Firebase는 Google 로그인과 알림 기능을 준비하는 서비스다.
- 다른 휴대폰은 외부 연결을 확인할 때 있으면 좋다. A50에도 가족 앱을 설치해 알림을 받을 수 있다.
- 7편부터는 기존 센서 프로그램이 돌아가는 Raspberry Pi가 필요하다. 그 프로그램은 문 상태와 온습도를 파일에 기록하고 있어야 한다. 7편에서 필요한 파일을 먼저 확인한다.

초기화할 휴대폰에 필요한 자료가 있으면 먼저 백업한다. 이 글은 개인 프로젝트의 시험 환경을 설명한다. 화면 잠금을 없애는 선택이 있으므로 금융 앱이나 중요한 개인 자료가 들어 있는 휴대폰에는 그대로 적용하지 않는다.

## 코드와 글을 준비한다

[GitHub의 서버 코드](https://github.com/PCY00/aircon-remote-control/tree/main/server)를 열고 **Code → Download ZIP**을 누른다. ZIP은 여러 파일을 하나로 묶은 압축 파일이다. 블로그에 코드 ZIP을 따로 첨부하지 않아도 이 링크에서 `main`의 현재 코드를 받을 수 있다.

GitHub에서 내려받는 ZIP에는 저장소 전체가 들어 있다. 압축을 풀고 **안쪽 저장소 폴더의 `server` 폴더**를 `C:\`로 옮긴 뒤 이름을 `smart-home-reader`로 바꾼다. `C:\smart-home-reader` 바로 아래에 `scripts`, `services`, `android`, `docs`가 보여야 한다. 다른 폴더를 쓴다면 아래 경로만 바꾼다. 이미 같은 폴더가 있는 독자는 새 빈 경로를 사용해 기존 파일을 지킨다.

**이후 PC 명령어는 항상 이 폴더를 연 PowerShell에서 실행한다.** 휴대폰에서 입력할 명령은 별도로 ‘A50 Termux’라고 적는다. Termux는 휴대폰에서 명령어를 입력할 수 있게 해주는 앱이다.

```powershell
Set-Location C:\smart-home-reader
Get-ChildItem scripts, services, android, docs
```

## PC에 Python을 준비한다

[Python 공식 Windows 다운로드](https://www.python.org/downloads/windows/)에서 Python 3.12를 설치한다. 설치 화면의 Python 실행 경로 추가 항목도 선택한다. 이 설명의 PC 명령은 Python 3.12 환경에서 확인했다.

PowerShell을 새로 열고 아래 명령을 실행한다. `.venv`는 이 프로젝트에서 쓸 Python과 필요한 도구를 모아두는 폴더다. 명령어마다 그 폴더의 Python을 지정하므로 PowerShell 실행 정책을 바꾸거나 별도 활성화 명령을 실행할 필요는 없다.

```powershell
Set-Location C:\smart-home-reader
py -3.12 --version
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r examples/mobile-app/requirements-reader.txt
.venv/Scripts/python.exe -m pip check
```

마지막에 `No broken requirements found.`가 나오면 필요한 Python 도구끼리 충돌하지 않는다는 뜻이다. `py`가 없으면 설치와 경로 설정을 확인한다. `.venv`가 이미 있다면 같은 이름의 폴더를 새로 만들지 않고 기존 환경을 확인한다.

## 휴대폰 연결 도구와 앱 제작 도구를 준비한다

[Android 공식 Platform Tools](https://developer.android.com/tools/releases/platform-tools)에서 Windows 파일을 내려받고 `C:\android`에 압축을 푼다. `C:\android\platform-tools\adb.exe`가 있어야 한다. ADB는 PC에서 Android 휴대폰을 연결하고 앱을 설치하는 도구다.

```powershell
$adb = 'C:\android\platform-tools\adb.exe'
& $adb version
ssh -V
```

`adb`의 버전과 SSH의 버전이 나오면 된다. SSH는 PC에서 휴대폰이나 라즈베리파이에 명령을 보내는 연결 방법이다. Windows에 `ssh`가 없으면 설정의 선택적 기능에서 OpenSSH 클라이언트를 설치한다.

앱을 만들 때는 [Adoptium의 JDK 17](https://adoptium.net/temurin/releases/?version=17)도 필요하다. Windows x64 설치 파일로 설치하고 설치 위치를 적어둔다. JDK는 앱 소스를 설치 파일로 만드는 데 쓰는 도구다. `java.exe`가 들어 있는 `bin`의 상위 폴더가 JDK 설치 위치다.

```powershell
# 본인이 설치한 실제 JDK 17 폴더로 바꾼다.
$jdk17 = 'C:\Program Files\Eclipse Adoptium\본인이_설치한_JDK17_폴더'
& "$jdk17/bin/java.exe" -version
```

버전이 `17`로 시작하는지 확인한다. 위 예시 폴더 이름을 그대로 복사하면 파일을 찾을 수 없다.

PowerShell을 새로 열면 프로젝트 폴더로 다시 이동하고 `$jdk17` 같은 이름에 본인 값을 다시 넣는다. `$`로 시작하는 이름은 뒤의 명령에서 다시 쓸 값을 담아두는 메모라고 생각하면 된다. 예시를 바꿀 때는 따옴표를 남기고 그 안의 내용만 본인 값으로 바꾼다.

## 본인 값으로 바꿔야 하는 것

| 값 | 어디서 확인하는가 | 사용하는 편 |
| --- | --- | --- |
| A50 Wi-Fi 주소 | 휴대폰의 무선 디버깅 화면 | 1편 |
| 페어링 포트와 연결 포트 | 무선 디버깅의 서로 다른 두 화면 | 1편 |
| Termux 사용자명 | A50에서 `whoami` 실행 | 1편 |
| JDK 17 설치 폴더 | PC에 설치한 위치 | 1편과 4편 |
| Firebase 프로젝트 ID | 본인이 만든 프로젝트의 설정 | 3편과 4편 |
| HTTPS 서버 주소 | 5편 도구가 만든 비공개 설정 파일 | 5편 이후 |
| Pi 주소와 사용자명 | 본인의 기존 Raspberry Pi 접속 정보 | 7편 |

실제 값은 `.deploy`라는 로컬 설정 폴더에 들어간다. 이 폴더와 개인 키는 GitHub와 공개 자료에서 제외한다. 설정 파일의 모양은 [설정 예시](../../../examples/mobile-app/README.md)에서 볼 수 있다. 대문자로 적힌 예시는 실제 값이 아니다.

## 글을 읽는 순서

1편에서 PC와 A50의 연결을 준비한다. 2편에서 A50에 서버를 설치한다. 3편에서 Google 로그인 설정을 만들고, 4편에서 본인 프로젝트와 연결된 앱을 만든다. 5편에서 다른 장소에서도 접근할 주소를 준비한다. 6편에서 시험 알림을 받는다. 7편에서 Pi의 기록을 연결한다. 8편에서 받고 싶은 알림과 가족을 관리하고, 9편에서 화면을 편하게 사용하는 방법을 확인한다.

[전체 목차](README.md) · [1편으로 이동](01-galaxy-a50-preparation.md)
