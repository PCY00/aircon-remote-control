# 웹 서비스 운영

## 구성

- 프로젝트: `/home/air/aircon-controller`
- Python: 프로젝트의 `.venv`
- 실행 스크립트: `scripts/run_pi.sh`
- 사용자 서비스: `~/.config/systemd/user/aircon-controller.service`
- 포트: `8001`
- 바인딩: 실행 시 조회한 Raspberry Pi의 Tailscale IPv4 한 개
- 쓰기 가능 경로: `runtime/`
- 운영 송신 계층: `AIRCON_IR_TRANSPORT=ir-ctl`
- 현재 검증된 송신 장치: `/dev/lirc0` (`gpio-ir-tx`, GPIO18)
- 현재 검증된 수신 장치: `/dev/lirc1` (`gpio-ir`, GPIO17)

장치 번호는 오버레이 구성에 따라 달라질 수 있으므로 번호보다 `ir-ctl --features` 결과를
최종 근거로 사용한다.

`run_pi.sh`는 `AIRCON_HOST`가 지정되지 않으면 `tailscale ip -4`로 주소를 조회한다. 주소가 없으면 시작에 실패하고 systemd가 5초 후 다시 시도한다. 따라서 `0.0.0.0`, LAN 주소와 공용 인터페이스에 자동으로 열리지 않는다.

## 자동 실행

서비스는 `default.target`에 enabled 상태이며 `air` 사용자의 linger가 활성화돼 있다. SSH 로그아웃 후에도 사용자 서비스가 유지되고 Pi 부팅 시 사용자 로그인 없이 시작될 수 있다.

실제 재부팅 검증은 별도 승인 후 수행한다. 이번 구성에서는 재부팅하지 않고 enabled, active, linger와 실행 프로세스를 확인했다.

## 상태 확인

Pi에서 다음 명령은 상태를 읽기만 한다.

```bash
systemctl --user status aircon-controller.service
systemctl --user is-enabled aircon-controller.service
systemctl --user is-active aircon-controller.service
```

최근 로그:

```bash
journalctl --user -u aircon-controller.service -n 100 --no-pager
```

Pi 내부 health 확인:

```bash
ts_ip="$(tailscale ip -4)"
curl --fail --silent --show-error "http://${ts_ip}:8001/health"
```

Tailnet에 연결된 Windows PC에서 확인할 때는 Pi의 실제 주소를 문서에 저장하지 않고 현재 값을 확인해 사용한다.

```powershell
tailscale ping <PI_TAILSCALE_IPV4>
curl.exe --noproxy "*" --fail --silent --show-error `
    http://<PI_TAILSCALE_IPV4>:8001/health
```

SSH 터널이나 LAN 주소가 아니라 `100.x` Tailscale 주소를 사용해야 Tailnet 경로를 검증할 수 있다. 같은 LAN에서 성공하더라도 실제 집 밖의 셀룰러·외부 Wi-Fi 검증은 별도로 수행한다.

## 서비스 조작

다음 명령은 실행 상태를 바꾸므로 자동화 에이전트가 실행할 때는 매번 사용자 승인을 받는다.

```bash
systemctl --user restart aircon-controller.service
systemctl --user stop aircon-controller.service
systemctl --user start aircon-controller.service
```

unit 파일을 변경한 경우에만 설정을 다시 읽는다.

```bash
systemctl --user daemon-reload
systemctl --user restart aircon-controller.service
```

## IR 송신 운영 확인

GPIO18 송신 오버레이 적용과 재부팅 후 장치 번호를 추측하지 않고 기능으로 확인한다.

```bash
for device in /dev/lirc*; do
    echo "== ${device} =="
    ir-ctl --device="${device}" --features
done
```

`Device can send raw IR`이 표시되는 장치를 `AIRCON_IR_TRANSMITTER_DEVICE`로 지정한다.
수신 전용 장치를 지정하면 API 상태가 `hardware_output: false`가 되며 명령 요청은 HTTP 503으로
실패한다. 송신 프로세스가 오류 또는 제한 시간 초과로 끝나면 HTTP 502를 반환하고 성공한
기기 상태로 기록하지 않는다.

```bash
ts_ip="$(tailscale ip -4)"
curl --fail --silent --show-error "http://${ts_ip}:8001/api/v1/ir/transmitter"
```

최초 `POWER_OFF` 소프트웨어 송신은 1회 성공했다. 다음 물리 검증은 에어컨을 향하지 않고
스마트폰 카메라의 IR 점멸, 이어서 기존 HW-477의 재캡처 순서로 진행한다. API의
`hardware_output: true`는 운영체제가 송신을 접수했다는 뜻이며 에어컨이 명령을 수행했다는
확인값은 아니다.

실제 Tailscale IP, 계정 정보와 인증 URL은 문서에 기록하지 않는다.

## 계획된 13인치 직결 터치 화면

현재 운영 서비스는 Tailscale IPv4 한 개에만 바인딩돼 있고 Pi OS Lite에는 키오스크용
그래픽 환경을 설치하지 않았다. 13인치 터치 디스플레이가 준비되면 로컬 패널용 loopback
접근과 외부 Tailscale 접근을 동시에 제공하는 구성을 별도 승인 후 적용한다.

목표는 로컬 Chromium이 `127.0.0.1` 경로로 동작하고 외부 접속은 계속 Tailnet으로만
제한하는 것이다. 구현 전까지 현재 바인딩을 바꾸지 않으며 `0.0.0.0:8001` 공개나 공유기
포트포워딩은 사용하지 않는다. 상세 결정은
[`../decisions/0011-local-touch-dashboard-and-tailscale.md`](../decisions/0011-local-touch-dashboard-and-tailscale.md)에
기록한다.
