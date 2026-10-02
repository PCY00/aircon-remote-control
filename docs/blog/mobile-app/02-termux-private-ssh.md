# Wi-Fi로 A50에 접근하고 공개키 SSH 연결하기

상태: **무선 ADB 페어링·기기 점검·공개키 SSH 접속 완료** (2026-10-02)

## 확인한 환경

기기에서 직접 확인한 값은 Galaxy A50 SM-A505N, Android 11, 보안 패치
2023-02-01, Termux 0.118.3, OpenSSH 10.5p1이다. One UI 3.1은 사용자 보고다.
USB 없이 Android 11 무선 디버깅으로 첫 연결을 준비했다. 긴 공개키 명령은
이 연결로 입력하고 이후 작업은 SSH로 실행했다.

## 연결 과정

1. 개발자 옵션의 무선 디버깅을 켜고 페어링 창을 연다.
2. PC의 Google 공식 Platform-Tools로 실제 표시된 주소에 페어링한다.
3. 페어링 포트와 접속 포트는 다르므로 실제 접속 주소를 확인한다.
4. 연결된 기기의 모델·OS를 확인하고 Termux를 연다.
5. 전용 Ed25519 공개키를 기존 authorized_keys를 보존하며 등록한다.
6. 8022 포트에서 공개키 인증 SSH를 실행하고 PC에서 새 연결을 검증한다.

개인키와 전용 known_hosts는 저장소 밖에 보관한다. 주소·앱 사용자명도
.deploy/a50/connection.json에만 두며 이 경로는 Git에서 제외된다.
다음 작업에서도 같은 키와 호스트 기록으로 접속한다.

    .venv/Scripts/python.exe scripts/android/a50_ssh.py 'echo SSH_CONNECTION_OK'

위 명령은 로컬 관리 도구 사용 예다. 실제 최초 연결 증거는 아래 기록이다.
호스트 키가 바뀌면 자동으로 무시하지 않고 연결을 거부한다.
현재 검증된 접속 범위는 같은 Wi-Fi다. 외부 사설망 경로는 후속 단계다.

## 실제 오류와 해결

- F-Droid Termux에서 run-as com.termux는 package not debuggable로 실패했다.
  초기 명령은 무선 ADB의 터미널 입력으로 실행했다.
- 첫 공개키 등록 후 Permission denied (publickey)가 발생했다.
  Android input text가 %s를 공백으로 바꿔 printf 형식 문자열을 변형했다.
  공개키 한 줄 등록을 echo로 바꿔 성공했다. 기존 파일을 통째로 덮어쓰지 않았다.
- 터미널의 준비 메시지만으로 성공을 판단하지 않고 PC에서 실제
  SSH_CONNECTION_OK 응답과 종료 코드 0을 확인했다.

## 증거

각 TXT와 같은 이름의 PNG를 함께 보존한다. 터미널 PNG는 실제 실행 로그에서
민감정보를 제거해 렌더링한 자료이며 휴대폰 화면 캡처와 구분한다.

- [80 — 실제 무선 페어링](../../assets/terminal/80-a50-wireless-adb-pairing.txt)
- [81 — 모델·패치·run-as 실패](../../assets/terminal/81-a50-initial-device-inspection.txt)
- [83 — 최초 공개키 접속 실패](../../assets/terminal/83-a50-public-key-ssh-connection.txt)
- [84 — 수정 후 SSH 성공](../../assets/terminal/84-a50-public-key-ssh-corrected.txt)

![공개키 SSH 설정 후 실제 Termux 화면](../../assets/hardware/galaxy-a50-server/02-termux-public-key-ssh-ready.png)

이어서 [백그라운드 유지와 재부팅 복구](03-background-recovery.md)를 검증했다.

## 공식 자료

- https://f-droid.org/en/packages/com.termux/
- https://github.com/termux/termux-app#installation
- https://developer.android.com/tools/adb
- https://developer.android.com/tools/releases/platform-tools
