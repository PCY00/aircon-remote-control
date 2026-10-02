# 화면을 끄고 Termux SSH를 유지하기

상태: **화면 꺼짐 중 120초 작업·새 SSH 접속·재부팅 자동 복구 성공** (2026-10-02)

## 화면과 CPU의 절전을 구분하기

화면을 계속 켜 둘 필요는 없다. Termux에 배터리 최적화 예외를 주고
termux-wake-lock으로 CPU 실행을 유지한다. 실제 점검에서 Android 예외 목록,
Termux foreground service, termux:service-wakelock을 확인했다.
충전·Wi-Fi가 유지되는 환경에서 시험했다.

## 실제 화면 꺼짐 시험

Termux에서 홈 화면으로 이동하고 화면을 끈 다음, 기존 SSH 연결에서
10초 간격 작업을 12회 수행했다. 중간에 별도의 SSH 연결도 새로 열었다.

| 확인 대상 | 실제 결과 |
| --- | --- |
| 초기 화면 상태 | mScreenState=OFF |
| 이후 삼성 화면 상태 | DOZE_SUSPEND, 일반 화면 비활성 |
| CPU 유지 | termux:service-wakelock 유지 |
| 화면 꺼짐 중 새 SSH 접속 | NEW_SSH_WHILE_SCREEN_OFF_OK |
| 기존 연결의 120초 작업 | 12회 출력, BACKGROUND_JOB_COMPLETED, 종료 코드 0 |

DOZE_SUSPEND는 여기서 읽은 디스플레이 상태다. Android의 장시간 device-idle
Doze 시험을 수행했다는 의미로 해석하지 않는다.
2분 시험은 초기 동작 확인이며 야간·24시간 안정성을 보장하는 결과가 아니다.

증거: [85 TXT](../../assets/terminal/85-a50-screen-off-ssh-test.txt),
[85 PNG](../../assets/terminal/85-a50-screen-off-ssh-test.png).

## 재부팅 자동 시작 준비

Termux와 같은 F-Droid 배포처의 Termux:Boot 0.8.1을 설치하고 앱을 한 번 열었다.
Boot 앱도 배터리 최적화 예외에 넣었다.

로컬 기준본 scripts/android/start-a50-ssh.sh를 휴대폰의
~/.termux/boot/10-start-ssh에 배포했다. 구문 검사와 로컬·원격 SHA-256 일치를
확인했다. 이 스크립트는 wake lock을 요청하고 8022 SSH를 공개키 인증으로 시작한다.
부팅 로그는 ~/.local/state/a50-server/bootstrap.log에 쓰며 실행 시 이전 로그를
100줄로 줄인다. SSH 프로세스가 이미 있으면 중복으로 시작하지 않는다.

검증한 SSH 시작 옵션은 Port 8022, PubkeyAuthentication yes,
PasswordAuthentication no, KbdInteractiveAuthentication no다.
이는 해당 시작 명령의 유효 설정이며 기본 sshd_config 전체를 변경한 것은 아니다.

![실제 Termux:Boot 최초 실행 화면](../../assets/hardware/galaxy-a50-server/03-termux-boot-first-launch.png)

증거: [91 TXT](../../assets/terminal/91-a50-termux-boot-after-unlock.txt),
[91 PNG](../../assets/terminal/91-a50-termux-boot-after-unlock.png).

## 준비 중 만난 오류

- 무선 APK 설치는 25초 제한에서 시간 초과됐다. 잠금 해제 뒤 명시적인 원격
  파일 경로로 전송하고 pm install을 실행해 성공했다. 잠금이 시간 초과의
  유일한 원인이었다고 확정하지 않는다.
- adb install --no-streaming은 대상이 디렉터리라는 오류를 냈다.
  APK를 /data/local/tmp/a50-termux-boot.apk로 명시해서 전송했다.
- Windows에서 텍스트 모드로 SSH 표준입력에 보낸 스크립트는 줄바꿈이
  CRLF로 바뀌어 셸 구문 검사에 실패했다. UTF-8 바이트로 전송해 LF를 보존했다.
  구문 검사 전에 실제 부팅 경로에 설치하지 않아 실패한 파일은 실행 대상이 되지 않았다.

실패 기록 86~89와 해결 기록 90~91을 삭제하지 않고 보존했다.
사용자는 시험 전에 휴대폰 잠금을 직접 해제하고 이후 잠금 설정을 없앴다고
알려줬다. 잠금을 다시 설정했을 때의 첫 부팅 동작은 별도로 확인해야 한다.

## 실제 재부팅 시험

A50을 정상 재부팅하고 앱을 여는 명령 없이 SSH 접속만 확인했다.
재부팅 명령으로부터 146.8초 뒤에 새 연결이 성공했다. 기기의 uptime이 초기화됐고,
새 부팅 로그의 SSH_START_COMMAND_COMPLETED와 새 SSH 프로세스를 확인했다.
그 뒤 로컬 관리 도구로도 MANAGEMENT_HELPER_OK 응답을 받았다.

증거: [92 TXT](../../assets/terminal/92-a50-reboot-auto-ssh-test.txt),
[92 PNG](../../assets/terminal/92-a50-reboot-auto-ssh-test.png),
[93 TXT](../../assets/terminal/93-a50-final-management-check.txt).

## 남은 검증

- 야간·24시간 생존, Wi-Fi 재연결과 주소 변경.
- 삼성 절전 앱 목록의 장기 영향, 서버 프로세스 자체의 재시작 관리.
- 외부 사설망 접속. 중앙 API·FCM은 아직 구성하지 않았다.

SSH에 다시 접속할 수 있도록 준비했으며 AI가 상시 실행되는 자동 감시를 설정한 것은 아니다.

## 공식 자료

- https://github.com/termux/termux-boot
- https://f-droid.org/en/packages/com.termux.boot/
- https://developer.android.com/training/monitoring-device-state/doze-standby
