# 2026-08-30 Room First UI Raspberry Pi 배포

## 배포 전 확인

- 대상: `air@AC:/home/air/aircon-controller`
- 사용자 서비스: enabled, active
- 기존 Tailscale `/health`: 정상
- 배포 미리보기에서 원격 변경 6개, 누락 11개, 동일 15개 확인
- Pi 가상환경에 새 업로드 API가 요구하는 `python-multipart`가 없음을 확인
- 초기 배포 스크립트가 `device_profiles/`를 포함하지 않는 누락을 발견하고 로컬에서 수정

## 사용자 승인 범위

- 로컬 기준본 37개 파일 전송
- 대상 하위 디렉터리 생성, 기존 대상 파일 덮어쓰기, 원격 삭제 없음
- Pi 가상환경의 프로젝트와 필수 의존성 갱신
- `aircon-controller.service` 1회 재시작
- SHA-256, 서비스 상태, Tailscale health와 UI 검증
- 재부팅과 systemd unit 설치·변경은 범위에서 제외

## 실행 결과

- 전송: 37개 파일, 638,670바이트
- 원격 SHA-256: 전체 일치
- `device_profiles/air_conditioner/Carrier/CS-A061GS/` 포함
- 애플리케이션 패키지: `0.2.0`에서 `0.3.0`으로 갱신
- `python-multipart 0.0.32` 설치
- FastAPI·Uvicorn 등 기존 충족 의존성은 유지
- `pip check`: `No broken requirements found`
- 서비스 재시작: 성공, active

## 검증

Pi 내부 Tailscale 경로:

- `/health`: HTTP 200, 서비스 상태 `ok`
- `/api/v1/system`: 포트 8001, Room First UI 확인
- `/`: HTTP 200, HTML
- `/static/vendor/lucide.min.js`: HTTP 200, 423,290바이트
- `/api/v1/device-profiles`: Carrier CS-A061GS 프로필 반환

Windows PC에서 Tailscale 경로:

- Tailscale ping 성공
- `/health`: HTTP 200
- `/`: HTTP 200
- 로컬 Lucide 정적 파일: HTTP 200

실제 Tailscale 주소는 기록하지 않았다. IR 송신 전송 계층은 계속 Mock이므로 이번 배포로
실제 에어컨에 적외선이 전송되지는 않는다.

## 로그 관찰

`journalctl --user` 단독 조회에서는 저널 파일이 없다는 메시지가 나왔지만,
`systemctl --user status`에는 애플리케이션 시작 완료와 검증 요청의 HTTP 200 로그가 보였다.
현재 서비스 검증에는 지장이 없으며 장기 로그 보존 설정은 후속 운영 점검으로 남긴다.
