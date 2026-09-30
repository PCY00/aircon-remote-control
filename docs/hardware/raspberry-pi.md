# Raspberry Pi 실행 환경

## 2026-08-29 읽기 전용 점검

- 호스트명: `AC`
- 모델: Raspberry Pi 4 Model B Rev 1.4
- 메모리: 2GB 모델, 운영체제에서 약 1.8GiB 확인
- 저장장치: 약 29GB, 사용 2.1GB, 여유 26GB
- 운영체제: Debian GNU/Linux 13.5 (Trixie), 64-bit
- 아키텍처: arm64/aarch64
- 커널: Linux 6.18.34+rpt-rpi-v8
- Python: 3.13.5
- 파일시스템: ext4, `noatime`
- 시간대: Asia/Seoul, NTP 동기화 정상
- 점검 당시 온도: 36.0℃
- 저전압·스로틀링 기록: 없음 (`throttled=0x0`)
- 실패 상태의 systemd 서비스: 없음

사설 IP와 로그인 비밀번호는 기록하지 않았다.

## 설치 상태

이미 설치됨:

- OpenSSH Server
- `python3-venv`
- `rsync`
- `curl`
- `gpiod`와 `gpioinfo`
- `v4l-utils`와 `ir-ctl`
- Tailscale 1.102.3
- 프로젝트 Python 가상환경과 FastAPI/Uvicorn 런타임
- 에어컨 제어 애플리케이션 사용자 systemd 서비스

아직 설치되지 않음:

- Git
- LIRC 사용자 도구

배포는 SCP/SSH와 체크섬 비교로 설계하므로 Raspberry Pi의 Git 설치는 현재 필수가 아니다.

## GPIO와 IR 상태

- GPIO character device가 정상적으로 존재한다.
- 로그인 사용자는 `gpio`, `i2c`, `spi`, `input` 그룹에 포함되어 있다.
- `/dev/lirc*` 장치는 아직 없다.
- `gpio-ir` 및 `gpio-ir-tx` 오버레이는 아직 활성화되지 않았다.
- `gpio_ir` 또는 LIRC 관련 커널 모듈은 아직 로드되지 않았다.

IR 핀과 모듈 전압을 확정한 다음 오버레이를 설정한다.

## SSH 상태

- SSH 서비스는 활성화 및 부팅 자동 시작 상태다.
- 초기 점검 당시 `authorized_keys`는 빈 파일이었다.
- Windows에 프로젝트 전용 ED25519 키를 만들고 공개키 인증을 구성했다.
- 자동 배포용 개인키는 프로젝트 밖의 Windows 사용자 SSH 저장소에만 보관한다.
- 암호와 대화형 입력을 허용하지 않는 `BatchMode` 접속을 IP와 호스트명 `AC` 양쪽에서 검증했다.

## Tailscale과 웹 서비스 상태

- `tailscaled`: enabled, active
- Tailscale 백엔드: Running
- Tailscale IPv4: 할당됨, 실제 주소는 기록하지 않음
- `aircon-controller.service`: 사용자 서비스로 enabled, active
- `air` 사용자 linger: yes
- 웹 서비스 포트: `8001`
- 바인딩 범위: Pi의 Tailscale IPv4만 사용
- 내부 `/health`: HTTP 200, `status=ok`
- Windows PC의 Tailscale 주소 직접 `/health`: HTTP 200, `status=ok`
- Tailscale ping 경로: direct
- 서비스 시작 후 확인 시 재시작 횟수: 0

서비스 구성 중 재부팅은 하지 않았다. 실제 부팅 복구 검증은 별도 승인 후 수행한다.
실제 집 밖 셀룰러·외부 Wi-Fi 환경의 접속 검증도 아직 수행하지 않았다.
