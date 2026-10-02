# A50 중앙 API의 시험용 HTTPS 통로

사용자가 다른 휴대폰용 외부 중앙서버 주소 생성을 요청한 범위에서 구성했다.
Cloudflare Quick Tunnel을 A50에서 직접 실행한다. 노트북은 운영 중계에 사용하지 않는다.
기존 중앙 API는 `127.0.0.1:8001`을 유지한다. Pi 제어 API·공유기·관리 SSH를 변경하지 않는다.

**시험용이다.** 터널 프로세스가 다시 시작되면 주소가 바뀌며, 가동 시간 보장이 없다.
고정 주소는 별도 도메인과 named tunnel 구성 후 제공한다. 서비스 재시작 전에 앱 사용자에게
주소 변경을 안내한다. 자동 복구는 접속 주소까지 고정하는 기능이 아니다.

## 배포

프로젝트 루트에서 확인된 A50 SSH 설정과 전용 호스트 키를 사용한다.

```powershell
python scripts/android/a50_record.py --label tunnel-package-install --script scripts/android/prepare_a50_tunnel.sh --timeout 300
python -m pytest tests/test_a50_public_tunnel.py -q
python scripts/android/deploy_a50_tunnel.py
python scripts/android/deploy_a50_tunnel.py --apply
python scripts/android/verify_a50_tunnel.py
```

`deploy_a50_tunnel.py`는 기본 읽기 전용 미리보기다. 기존 원격 관리 파일·링크가 바뀌었거나
추적되지 않은 디렉터리가 있으면 덮어쓰지 않는다. 소스 4개를 체크섬별 릴리스로 배포한다.
`cloudflared` 패키지의 기본 서비스는 비활성 상태로 둔다.

| 대상 | 경로 |
| --- | --- |
| 소스·배포 기록 | `~/services/aircon-public-tunnel/` |
| 별도 runit 서비스 | `$PREFIX/var/service/aircon-public-tunnel/` |
| 현재 주소·상태, 비공개 로그 | `~/.local/state/aircon-public-tunnel/` |
| 검증 후 노트북의 비공개 주소 사본 | `.deploy/a50/tunnel-endpoint.json` |

원래 중앙 서비스의 부팅 훅이 runit 서비스 디렉터리를 실행하므로 새 부팅 훅을 추가하지 않는다.
부팅 후 실행은 이 구조로 구성했으며, 이번 단계에서 실제 기기 재부팅은 시험하지 않았다.
최초 배포 후 명시적인 서비스 중지·재시작과 HTTPS 연결을 확인했다.

## 접근과 기록

사용자 요청은 HTTPS로 Cloudflare에 도착하고, A50에서 시작한 암호화 터널로 중앙 API에 전달된다.
Cloudflare가 HTTPS를 종료하므로 요청 내용과 인증 헤더를 처리하는 서비스에 포함된다.
Google ID 토큰 검증·집 소속·역할 검사는 중앙 API가 계속 수행한다. URL은 권한 증명이 아니다.
준비 화면과 health는 공개이며, 사용자·가족 API는 인증이 필요하다.
별도 Cloudflare 이메일 인증 페이지는 네이티브 APK 요청과 맞지 않아 설정하지 않는다.

원문 cloudflared 로그와 실제 주소는 비공개 상태 디렉터리에만 저장한다.
원문 로그·서비스 로그는 각각 1MiB 파일과 백업 3개로 제한한다.
5분 안에 비정상 종료 5회면 `down` 상태로 남겨 반복 재시작을 멈춘다.
정상 중지와 재시작은 실패 횟수에 넣지 않는다. 재시작 이력이 손상되면 중단한다.
시작·종료할 때 주소 상태를 갱신해 중지된 주소를 현재 주소로 전달하지 않는다.
주소 파일은 0600이며, 실제 로그와 주소를 Git이나 블로그에 게시하지 않는다.

## 운영 중지와 복구

아래는 A50 SSH 셸에서 실행한다. 중앙 API·DB·관리 SSH는 중지하지 않는다.

```sh
export SVDIR="$PREFIX/var/service"
sv status "$SVDIR/aircon-public-tunnel"
sv-disable aircon-public-tunnel
sv -w 20 down "$SVDIR/aircon-public-tunnel"
```

재개는 원인을 확인한 뒤 `sv-enable aircon-public-tunnel`을 명시적으로 실행한다.
재시작 예산을 소진했으면 최소 5분의 실패 창이 지난 뒤 재개한다. 실패 기록을 지우지 않는다.
재개 후 `verify_a50_tunnel.py`로 새 주소와 HTTPS 응답을 확인하고 앱 주소를 갱신한다.

공식 자료: [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
[고정 Tunnel 준비](https://developers.cloudflare.com/tunnel/get-started/),
[Termux cloudflared 패키지](https://github.com/termux/termux-packages/blob/master/packages/cloudflared/build.sh).

후속 확인: A50의 실제 Google 로그인 세션과 원래 배포 APK로 HTTPS 집 목록·집 등록·
소유자 관리 화면·클라이언트 재실행 후 로그인/주소 유지를 확인했다.
이 결과가 Quick Tunnel 주소의 고정·가동 시간 보장이나 FCM 수신을 뜻하지는 않는다.
