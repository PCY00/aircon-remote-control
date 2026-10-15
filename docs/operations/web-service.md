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

`run_pi.sh`는 `AIRCON_HOST`가 지정되지 않으면 `tailscale ip -4`로 주소를 조회한다. 주소가 없으면 시작에 실패하고 systemd가 5초 후 다시 시도한다. 따라서 `0.0.0.0`, LAN 주소와 공용 인터페이스에 자동으로 열리지 않는다. 조회한 주소는 `AIRCON_HOST`로 내보내 앱의 허용 Host 목록에 포함시키고, `--limit-concurrency 64`로 동시에 열 수 있는 연결 수를 제한한다(초과분은 503).

## 브라우저 경계 보호 (로그인 없는 서비스)

이 서비스는 설계상 로그인이 없고 Tailnet 안에서만 열린다. 대신 앱이 다음을 직접 거른다.

- Host 허용 목록: 바인딩 주소(`AIRCON_HOST`), `127.0.0.1`, `localhost`, `::1`, 그리고
  `AIRCON_ALLOWED_HOSTS`(쉼표 구분, 예: Tailscale MagicDNS 이름)에 적은 이름만 받는다.
  포트는 비교하지 않는다. 연결이 실제로 도착한 서버 주소도 허용한다. 그 밖의 Host는
  HTTP 400 `{"detail": "Host header is not this service"}`로 거부한다(DNS 리바인딩 차단).
  MagicDNS 이름으로 접속하려면 `runtime/app.env`에 `AIRCON_ALLOWED_HOSTS=<이름>`을 적고
  서비스를 재시작한다. 키오스크(`http://<Tailscale IP>:8001/?kiosk=1`), 가족의 IP 접속,
  `run_local.ps1`의 loopback, 중앙 에이전트(`control_origin`)는 그대로 동작한다.
- 교차 사이트 변경 차단: GET/HEAD/OPTIONS가 아닌 요청에 `Origin`이 있으면 스킴·호스트·
  포트가 요청 자신의 출처(`http://<Host 헤더>`)와 같거나, 허용 호스트 + 서비스 포트
  (`AIRCON_PORT`)여야 한다. 같은 주소라도 포트가 다른 다른 서비스(예: 키오스크에서 연
  Zigbee2MQTT 화면 `127.0.0.1:8080`)는 다른 출처로 본다. `Sec-Fetch-Site: cross-site`면
  Origin이 없어도 거부한다 (HTTP 403 JSON). `curl`, 테스트 클라이언트, 에이전트처럼 두 헤더가 없는 요청은 그대로
  허용한다. SSE(`/api/v1/events`)와 GET은 영향이 없다. FastAPI 0.141 이상은
  `application/json`이 아닌 본문을 JSON으로 읽지 않으므로 단순 폼 요청으로 JSON API를
  호출할 수 없다(`pyproject.toml` 하한).
- 본문 크기: 모든 경로 1 MiB. `POST /api/v1/device-requests`는 `Content-Length`가 없으면
  411, `AIRCON_MAX_UPLOAD_BYTES × 3 + 64 KiB`를 넘으면 413이다. 저장 총량은
  `AIRCON_DEVICE_REQUEST_QUOTA_BYTES`(기본 200 MiB)를 넘으면 507, 같은 프로세스에서
  시간당 20건을 넘으면 429 `Retry-After`를 돌려준다. 403·411·413으로 거부된 요청은
  이 횟수에 들어가지 않는다.
- 실시간 스트림: `/api/v1/events` 구독은 32개까지이며 초과하면 503 `Retry-After: 30`이다.
- Zigbee 가입 열기(`POST /api/v1/zigbee/join`)는 Coordinator만 대상으로 하고, 한 번 열면
  닫기(`DELETE`) 전에는 5분 동안 다시 열 수 없다(429). 열기·닫기 요청은 요청한 클라이언트
  주소와 함께 로그에 남는다.
- `air` 사용자는 Zigbee 스택 때문에 `docker` 그룹에 속한다. 이 호스트 설정은 그대로
  두되, `aircon-controller.service`와 `aircon-kiosk.service`에
  `InaccessiblePaths=-/run/docker.sock`을 넣어 웹앱과 키오스크 프로세스에서는 Docker
  소켓이 보이지 않게 한다(unit 변경 후 `daemon-reload` 필요).
- 웹앱은 Zigbee2MQTT 계정을 공유하지 않고 `aircon-controller` 브로커 계정을 쓴다.
  권한은 `deploy/zigbee/mosquitto/acl.conf`로 제한하며 `scripts/setup_app_mqtt.sh`가
  계정과 `runtime/app.env`를 만든다. 자세한 재배포 순서는 `deploy/zigbee/README.md`.

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

요청한 배포·운영 복구 범위에서 서비스 재시작이 필요하면 대상과 중단 영향을 먼저
안내하고 실행한다. 별도 범위의 운영 변경은 사용자에게 확인한다.

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

## ESP32-H2 Zigbee IR 연결

H2는 Zigbee2MQTT에 먼저 가입해야 한다. 현재 펌웨어는 공장 초기 보드의 부팅 때
자동으로 가입을 시도하므로 전용 등록 버튼이 없다. 가입을 잠시 허용한 뒤 USB
전원을 연결하고, 인터뷰 성공을 확인한 즉시 가입을 닫는다. BOOT 버튼은 현재
펌웨어의 가입 버튼이 아니다. 이미 가입된 보드는 이 절차를 반복하지 않는다.

웹의 기존 에어컨 상세 화면에서 ‘ESP32-H2 Zigbee IR 연결·변경’을 눌러 목록의
H2를 선택한다. 새 에어컨 등록 과정에서는 ‘Zigbee IR’ 연결 방식을 선택할 수 있다.
서버는 `AIRCON_H2_IR_01`이 지원됨·인터뷰 성공으로 확인될 때만 연결한다.
연결된 Carrier CS-A061GS에는 명시적인 끄기, 냉방 온도·풍량, 자동/제습/송풍
모드와 캡처한 부가 기능 명령을 제공한다. 요청 ID와 명령 이름을 H2의 `sent`
응답과 대조하고 자동 재전송은 하지 않는다. 화면의 상태는 **마지막 요청값**이지
실제 에어컨 상태를 측정한 값이 아니다. 냉방 21–30°C 프레임은 프로필 규칙으로
추정한 값이고, LED 명령의 실제 효과도 미확인이다. 우선 확인된 17–20°C에서
하나씩 현장 검증한다. 다른 네트워크로 이전하기 위한 Zigbee 정보 삭제나
재초기화는 이 연결 절차에 포함하지 않는다.

## 계획된 13인치 직결 터치 화면

현재 운영 서비스는 Tailscale IPv4 한 개에만 바인딩돼 있고 Pi OS Lite에는 키오스크용
그래픽 환경을 설치하지 않았다. 13인치 터치 디스플레이가 준비되면 로컬 패널용 loopback
접근과 외부 Tailscale 접근을 동시에 제공하는 구성을 별도 승인 후 적용한다.

목표는 로컬 Chromium이 `127.0.0.1` 경로로 동작하고 외부 접속은 계속 Tailnet으로만
제한하는 것이다. 구현 전까지 현재 바인딩을 바꾸지 않으며 `0.0.0.0:8001` 공개나 공유기
포트포워딩은 사용하지 않는다. 상세 결정은
[`../decisions/0011-local-touch-dashboard-and-tailscale.md`](../decisions/0011-local-touch-dashboard-and-tailscale.md)에
기록한다.
