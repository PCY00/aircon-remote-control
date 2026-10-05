# 0014 — A50에서 직접 실행하는 시험용 HTTPS 통로

날짜: 2026-10-02. 상태: 시험용 임시 주소 배포·외부 TLS/인증 차단 검사 완료.

## 배경과 요청 범위

사용자는 다른 휴대폰에서 실제 Google 로그인 성공을 확인했다. 서버 주소는 아직 없었고,
외부 휴대폰용 중앙서버 HTTPS 주소를 만들자는 안내에 “만들자”라고 요청했다.
이 요청을 중앙 가족 API에 한정한 HTTPS 외부 경로 구성 권한으로 적용했다.
도메인은 아직 없다고 답했다. 구매·공유기 설정·Pi 제어 API 공개는 요청하지 않았다.

## 선택

A50 Termux의 공식 `cloudflared` 패키지로 Cloudflare Quick Tunnel을 실행한다.
중앙 API의 루프백 8001 바인딩을 유지하고, A50이 Cloudflare에 연결을 시작한다.
Cloudflare에서 TLS가 종료되며 요청·인증 헤더를 처리하므로 신뢰하는 중계 서비스에 포함된다.
중앙 서버의 Firebase 인증·가구별 권한은 그대로 적용한다. Pi Tailscale 경로는 유지한다.
터널은 별도 runit 서비스로 관리하며 중앙 API·SSH 서비스에 종속시키지 않는다.

Cloudflare 계정·도메인이 필요 없는 시험 단계다. 주소가 프로세스 재시작 때 바뀌고
가동 시간 보장이 없어 고정 운영 주소의 완료로 간주하지 않는다.
고정 주소와 제품 배포는 도메인·named tunnel 준비 후 별도 진행한다.

## 근거와 확인

- 설치 시 기존 패키지 0개 업그레이드, cloudflared 1개 추가(2026.9.3-1).
- 별도 소스·실행 훅 4개, 체크섬 배포와 원격 변경 보존.
- Windows 검사에서 POSIX 상수 부재를 발견해 플랫폼 예외를 처리했고 7개 검사 통과.
- runit의 새 서비스 인식 지연을 발견해 인식 대기를 추가한 뒤 배포·서비스 재시작 확인.
- 외부 시스템 인증서 검증을 켠 HTTPS 요청으로 readiness 200, 인증 없는 요청과
  위조 토큰의 401 거부, 응답 no-store 확인.
- 중앙 소스·DB 런타임 식별자·SSH 부팅 파일 유지.
- 실제 Google 토큰의 서버 수락·집 만들기는 사용자의 앱 시험으로 확인할 항목이다.
- 후속 검증에서 A50의 원래 배포 APK·실제 Google 계정으로 HTTPS 집 목록·집 등록·
  소유자 관리 화면·클라이언트 재실행 후 세션 유지를 확인했다(5편 보충).
- 기기 재부팅·장시간·FCM·실제 Pi 연결은 이번 확인에 포함하지 않는다.

## 관련 자료

[5편](../../server/docs/blog/mobile-app/05-external-https-connection.md),
[서비스 운영 절차](../../server/services/central-tunnel/README.md),
[Cloudflare 공식 Quick Tunnel 제한](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
