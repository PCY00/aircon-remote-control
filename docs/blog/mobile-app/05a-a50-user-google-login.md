# 5편 보충 — A50을 만지지 않고 직접 Google 로그인하기

사용자가 A50에 가족 APK를 설치해 시험해 달라고 요청했고, Google 로그인은 직접 하겠다고 했다.
서버용 A50에는 Google 계정이 없으므로 가상 계정 검사만으로 실제 로그인을 대신하지 않는다.
노트북에 A50 화면을 띄워 사용자에게 로그인 입력을 넘기는 방법을 준비했다.

## 설치 확인

```powershell
python scripts/android/install_test_family_app.py --production-only --release --apply
```

4편에서 검증한 서명·해시의 배포 APK를 `install -r`로 다시 설치한다. 앱 데이터를 삭제하지 않는다.
설치 Success·앱 COLD 실행 527ms·Firebase 세션 초기화·로그인 시작 화면 확인을 기록했다(208).
이 결과는 실제 Google 로그인 성공과 구분한다.

## 화면 도구 준비

```powershell
python scripts/android/prepare_a50_mirror.py
python scripts/android/open_a50_mirror.py
```

공식 Genymobile/scrcpy v4.1 Windows 64비트 ZIP(11,305,298바이트)의 공식 SHA-256을 확인했다.
저장소의 `tmp/`에 압축을 풀며 Windows 전체 설치나 장비의 네트워크 변경은 하지 않는다.
실행 전 준비된 모든 파일을 검증한 ZIP과 다시 비교한다.
기존 무선 ADB를 자동으로 찾아 모델·고유 장치 값을 확인한 뒤 그 A50만 선택한다.
장치 주소나 ADB 포트를 새로 입력하거나 USB를 연결할 필요가 없다.

`A50 - Family Smart Home` 창이 열리면 사용자가 직접 앱의 Google 버튼을 눌러 로그인한다.
비밀번호·인증 코드를 채팅에 보내거나 자동화 도구에 보관하지 않는다.
음성 전송·영상 녹화·자동 클립보드 동기화를 끄며 로그인 입력 중에는 블로그 캡처를 하지 않는다.
입력은 사용자가 직접 하고, 완료 보고 후 가족 앱의 결과만 별도로 확인한다.

Google 또는 Android가 보안 화면의 미러링을 제한하면 그 보호를 우회하지 않는다.
그 경우 A50에서 직접 입력 가능한 시점에 계정 추가를 완료한다.
화면 도구는 현재 노트북의 ADB 연결을 사용하며 임의의 다른 PC에서 인터넷만으로 접속하는
원격 관리 주소를 새로 만든 것이 아니다.

시험이 끝나면 화면 창의 닫기를 눌러 미러링을 종료한다. 중앙 서버·SSH는 그대로 동작한다.
실제 로그인·API 연결·집 등록은 아직 사용자 로그인 완료 후 검증할 항목이다.

공식 자료: [scrcpy 프로젝트](https://github.com/Genymobile/scrcpy),
[Windows 배포와 검증값](https://github.com/Genymobile/scrcpy/blob/master/doc/windows.md),
[무선 ADB 연결](https://github.com/Genymobile/scrcpy/blob/master/doc/connection.md),
[클립보드 동기화 옵션](https://github.com/Genymobile/scrcpy/blob/master/doc/control.md).
