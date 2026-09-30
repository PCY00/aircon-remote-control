# 13인치 터치 디스플레이 키오스크

## 목표

Raspberry Pi OS Lite에는 데스크톱과 브라우저가 없으므로 화면만 연결하면 콘솔이 나온다.
전체 데스크톱 대신 Wayland 키오스크 컴포지터인 Cage에서 Chromium 하나만 실행해 스마트홈
웹앱을 전체화면으로 표시한다.

```text
Pi 부팅
  → aircon-controller와 Tailscale 준비
  → HDMI/DSI 연결 대기
  → Cage Wayland 세션
  → Chromium kiosk
  → Pi 자신의 Tailscale 주소:8001
```

Raspberry Pi OS는 Bookworm 이후 Wayland를 기본·권장 방향으로 사용한다. Cage는 하나의
애플리케이션만 최대화해 실행하는 전용 Wayland 키오스크 컴포지터이므로 Lite 환경에 전체
데스크톱을 설치하는 것보다 목적이 분명하다.

## 설치되는 패키지

- `cage`: 단일 앱 Wayland 키오스크 컴포지터
- `chromium`: 대시보드 브라우저
- `chromium-sandbox`: 브라우저 샌드박스
- `fonts-noto-cjk`: 한글 UI 글꼴

## 설치

```bash
cd ~/aircon-controller
sudo bash scripts/setup_kiosk.sh
```

`bash`로 처음 실행하면 Windows에서 전송한 파일의 실행 비트가 없어도 설치할 수 있다.
설치 과정에서 두 키오스크 스크립트 모두 실행 권한을 갖도록 정리한다.

설치 스크립트는 패키지를 설치하고 `/etc/systemd/system/aircon-kiosk.service`를 만든 뒤
서비스를 활성화한다. 디스플레이가 연결되지 않았으면 서비스는 실패를 반복하지 않고 연결을
기다린다.

## 화면 연결

1. 가능하면 Pi 전원을 끈 상태에서 HDMI를 연결한다.
2. 터치 디스플레이가 USB 터치 케이블을 요구하면 HDMI와 별도로 USB도 연결한다.
3. 전원을 켜면 키오스크 서비스가 디스플레이와 웹 서비스 준비를 기다린 뒤 전체화면으로
   대시보드를 연다.

현재 웹 서버는 공용 LAN 전체가 아니라 Tailscale 주소에만 바인딩된다. 키오스크 실행
스크립트가 `tailscale ip -4`로 Pi 자신의 주소를 구하므로 소스에 사설 주소를 저장하지
않는다. 키오스크 브라우저만 루트 URL에 `?kiosk=1`을 붙인다. 웹앱은 이 표시가 있을 때만
마우스 커서를 숨기므로 같은 사이트를 PC 브라우저로 열었을 때는 커서가 정상적으로 보인다.

## 확인 명령

```bash
systemctl status aircon-kiosk --no-pager
journalctl -u aircon-kiosk -n 100 --no-pager
cat /sys/class/drm/card*-*/status
```

`PAMName=login`이 Cage를 로그인 세션 scope로 옮긴 뒤의 로그는 `journalctl -u`만으로
누락될 수 있다. 서비스가 active인데 Chromium이 없다면 현재 부팅 로그도 함께 확인한다.

```bash
journalctl -b --no-pager | grep -E 'run_kiosk.sh|cage|chromium|Wayland socket'
pgrep -a -f 'cage|chromium'
find /run/user/1000 -maxdepth 1 -name 'wayland-*' -ls
```

성공 로그는 다음 순서로 나타난다.

```text
Display detected. Preparing dashboard kiosk.
Dashboard is healthy. Starting Chromium kiosk.
```

성공 상태에서는 Cage뿐 아니라 Chromium 자식 프로세스와 `/run/user/1000/wayland-*`
소켓도 나타나야 한다. `active`라는 서비스 상태 하나만으로 화면 성공을 판정하지 않는다.

`ProtectSystem=strict`를 사용하는 unit에서는 Cage가 소켓을 만들 수 있도록
`/run/user/1000`을 `ReadWritePaths`에 포함해야 한다. 캐시는 홈 기본 경로 대신 쓰기가 허용된
`runtime/kiosk/cache`를 사용한다. 이 두 경로가 빠지면 Cage PID만 남아 서비스가 active로
보이면서 Chromium은 시작되지 않을 수 있다.

## 복구

키오스크가 반복 재시작하거나 화면이 보이지 않으면 SSH에서 먼저 중지한다.

```bash
sudo systemctl stop aircon-kiosk
```

다시 시작하려면 다음을 실행한다.

```bash
sudo systemctl start aircon-kiosk
```

실제 디스플레이를 연결한 뒤 해상도, 방향, 터치 좌표와 장시간 화면 유지 여부를 별도로
검증한다. 화면 모델과 해상도를 확인하기 전에는 회전이나 강제 해상도 설정을 넣지 않는다.

## 참고

- Raspberry Pi 공식 문서: https://www.raspberrypi.com/documentation/computers/configuration.html
- Raspberry Pi 공식 키오스크 튜토리얼: https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/
- Debian Cage 매뉴얼: https://manpages.debian.org/trixie/cage/cage.1.en.html
