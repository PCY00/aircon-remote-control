# [편하게 살자] 스마트홈 알림 - 라즈베리파이의 기록을 A50에 보내봤다

　시험 버튼으로 실제 알림을 받았다. 이제 라즈베리파이에서 들어오는 문 상태와 온습도 기록을 연결해보기로 했다.

　센서는 이미 Pi에서 읽고 있었다. 알림 때문에 센서 프로그램을 새로 만드는 대신, 기존 기록에서 새로 들어온 내용을 읽어 A50으로 보내는 프로그램을 붙였다.

　Pi에서 밖으로 보내는 연결이라 이 과정에서도 Pi 제어 서비스의 포트를 인터넷에 열지는 않았다.

　**앞에서 준비할 것:** 시험 알림을 받는 A50 가족 앱, 해당 집의 소유자 로그인, 기존 센서 프로그램이 돌아가는 Pi.

　이 글은 센서를 처음 붙이는 설명이 아니다. 아직 Pi에 센서 기록이 없다면 기존 센서 프로그램부터 준비하자. 센서 없이도 알림 설정과 화면 개선 글의 앱 설정과 화면은 사용할 수 있다.

## 기존 센서 기록이 있는지 확인했다

---

　이번 연결 프로그램은 기존 `aircon-controller`의 두 기록 파일을 읽는다. **본인의 Pi SSH 화면**에서 아래를 실행한다.

```sh
whoami
ls ~/aircon-controller/runtime/sensors/sensors.sqlite3
ls ~/aircon-controller/runtime/automations/automations.sqlite3
systemctl --user is-active aircon-controller
loginctl show-user "$(whoami)" -p Linger
```

　두 파일이 있고 기존 서비스가 `active`여야 한다.

| 파일 | 확인할 내용 |
| --- | --- |
| `runtime/sensors/sensors.sqlite3` | 문 변화가 저장되는 `door_events` 기록 |
| `runtime/automations/automations.sqlite3` | 자동화 결과가 저장되는 `automation_events` 기록 |

　없는 파일을 빈 파일로 만들면 센서가 연결되는 것이 아니다. 기존 프로그램의 위치나 기록 형식이 다르면 이 명령을 그대로 진행하지 말자.

　`Linger=yes`는 Pi에서 로그아웃해도 사용자 서비스가 유지되는 설정이다. 꺼져 있다면 기존 운영 방식을 확인한 뒤, 계속 실행할 본인의 Pi에서 아래처럼 켤 수 있다.

```sh
sudo loginctl enable-linger "$(whoami)"
```

## A50 접속 정보와 Pi 접속 정보를 나눴다

---

　PC가 A50에도 접속하고 Pi에도 접속한다. 그래서 어느 장비인지 헷갈리지 않게 서로 다른 설정 파일을 사용했다.

　Pi에는 기존 SSH 키를 쓰거나 새 전용 키를 등록한다. 새 키가 필요한 경우 **PC PowerShell**에서 실행한다. 이미 있는 키는 덮어쓰지 않는다.

```powershell
ssh-keygen -t ed25519 -f "$HOME/.ssh/pi-reader"
Get-Content "$HOME/.ssh/pi-reader.pub"
```

　표시된 공개키 한 줄을 복사한다. 기존 방법으로 접속한 **Pi SSH 화면**에서 아래 명령을 실행한다. `cat` 뒤 공개키를 붙여넣고 Enter, Ctrl+D로 입력을 끝낸다.

```sh
mkdir -p ~/.ssh
chmod 700 ~/.ssh
cat >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

　개인키 내용을 붙여넣는 것이 아니다. 마지막 SHA256 표시는 PC의 첫 접속에서 나오는 값과 비교한다. 기존 키를 계속 쓸 사람은 새 키를 만들지 않고 그 파일 경로를 사용하자.

　**PC PowerShell**에서 본인이 접속해본 Pi 주소와 사용자명을 넣는다. Tailscale을 쓰고 있다면 본인의 Pi 사설 주소를 넣으면 된다.

```powershell
$piHost = '본인이_확인한_Pi주소'
$piUser = '본인의_Pi사용자명'
$piKey = "$HOME/.ssh/pi-reader"
$piKnownHosts = "$HOME/.ssh/pi-reader-known-hosts"
ssh -i $piKey -o "UserKnownHostsFile=$piKnownHosts" "$piUser@$piHost" 'echo PI_CONNECTION_OK'
.venv/Scripts/python.exe scripts/reader/setup_connections.py pi --host $piHost --user $piUser --identity-file $piKey --known-hosts-file $piKnownHosts
```

　Pi의 신원 표시가 같은지 확인한 뒤 첫 연결을 허용한다. 확인된 접속 정보는 `.deploy/pi-central-agent/connection.json`에 저장된다. 내 사용자명이나 장비 주소는 공개 소스에서 뺐다.

## 어느 집에 붙일지 먼저 봤다

---

　A50 앱에서 연결할 집을 열고 알림 받기를 켜둔다. 해당 집의 소유자로 로그인돼 있어야 한다. 앞에서 통로를 만들며 저장한 `.deploy/a50/tunnel-endpoint.json`도 필요하다.

　**PC PowerShell**에서 확인용 앱을 만든 뒤 첫 연결을 미리 본다.

```powershell
.venv/Scripts/python.exe scripts/android/build_family_app.py --production-smoke-only
.venv/Scripts/python.exe scripts/pi/link_central_agent.py --home-name '우리 집'
```

　`우리 집`은 본인 앱에 보이는 이름으로 바꾼다. 이 명령은 A50과 Pi 시간, 기존 기록 파일과 앱의 소유자 상태를 확인한다. 아직 키를 만들거나 전달 서비스를 시작하지 않는다.

　**새 서버와 새 Pi를 처음 연결할 때 쓰는 명령**이다. 이미 허브나 연결 설정이 있으면 멈추는 것이 정상이다. 기존 상태를 지우고 계속 반복하지 말자.

## 첫 연결을 실행했다

---

　어느 집을 연결하는지 확인한 뒤 `--apply`를 붙인다.

```powershell
.venv/Scripts/python.exe scripts/pi/link_central_agent.py --home-name '우리 집' --apply
```

　Pi만의 비밀 연결 키를 만들고, A50의 소유자 앱에서 짧게 유효한 등록 코드를 수락한다. 그다음 Pi에 기록 전달 프로그램을 설치하고 시작한다. 키 내용은 공개 로그에 남기지 않는다.

　기존 센서 프로그램은 다시 시작하지 않았다. 이미 쌓인 옛 기록도 한꺼번에 알림으로 보내지 않게 했다. 설치하자마자 지난 문 열림이 몰려오면 지금 생긴 일인지 헷갈리기 때문이다.

　처음에는 **Pi 연결 확인 알림**을 보낸다. 실제로 문이 열렸다는 뜻은 아니다.

## 연결 알림은 받았다

---

```powershell
.venv/Scripts/python.exe scripts/pi/verify_central_agent.py
```

　Pi의 전달 서비스와 A50 등록 상태를 확인한다. 그다음 실제 휴대폰에 연결 확인 알림이 왔는지 본다.

![Pi를 연결한 뒤 실제 앱에 표시된 수신 상태](../../assets/hardware/family-app/13-a50-pi-connection-fcm-receipt.png)

　내 A50에서는 Pi 연결 알림을 받았다. Pi에서 온 온습도 기록을 앱에서 읽는 것도 확인했다.

| 확인한 일 | 결과 |
| --- | --- |
| 실제 Pi의 연결 확인 알림 | A50에서 수신 확인 |
| Pi의 온습도 기록 | 앱에서 조회 확인 |
| 문을 직접 열고 닫아서 오는 알림 | 아직 별도 시험이 필요함 |
| 서로 다른 가족 계정의 실제 수신 | 아직 별도 시험이 필요함 |

　여기까지 보고 문 센서 알림까지 전부 끝났다고 쓰지는 않았다. 본인 환경에서는 문을 직접 열고 닫고, Pi의 새 기록과 휴대폰 알림이 둘 다 생기는지 확인하자. 온습도도 새 측정값으로 따로 확인해야 한다.

## 연결 도중 멈추면 남은 상태부터 보자

---

　키나 설정이 생긴 뒤 실패했다면 `verify_central_agent.py`로 현재 상태부터 읽는다. 키와 가족 기록을 지워 처음부터 반복하면 중복 연결이나 기록 손실이 생길 수 있다.

　시험용 통로 주소가 바뀐 경우도 있다. 새 키를 만들기 전에 현재 HTTPS 주소와 Pi에 저장한 서버 주소부터 비교하자.

　**여기까지 확인할 것:** Pi 연결 확인 알림이 도착하고 Pi의 새 센서 기록을 앱에서 읽을 수 있다. 실제 문·온습도 알림은 각 센서의 새 기록으로 따로 확인한다.

　이제 Pi의 기록까지 들어온다. 그런데 모든 사람이 같은 알림을 받고 싶은 것은 아니다. 다음에는 휴대폰마다 선택하게 만들어보자.
