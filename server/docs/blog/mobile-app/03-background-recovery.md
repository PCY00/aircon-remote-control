# 화면을 끄거나 재부팅한 뒤 접속이 안 될 때

설정 순서는 [1편](01-galaxy-a50-preparation.md)을 따른다. Termux와 Termux Boot는 같은 배포처에서 설치하고 Boot를 한 번 열어야 한다. 두 앱의 배터리 최적화 예외와 절전 앱 목록을 확인한다.

SSH와 무선 디버깅은 서로 다른 연결이다. SSH가 되는 상태에서 ADB만 끊겼다면 서버 전체가 멈췄다고 생각하지 않는다. 무선 디버깅, 집 Wi-Fi 허용창과 드래그 잠금을 확인한다.

작성자는 Windows에서 만든 부팅 파일의 줄바꿈 때문에 실행 오류를 만났다. 독자용 `prepare_phone_boot.py`는 휴대폰에서 사용할 줄바꿈으로 저장한다. 기존 부팅 파일의 내용이 다르면 덮어쓰지 않고 멈춘다.

[실제 화면 꺼짐 기록](../../assets/terminal/85-a50-screen-off-ssh-test.txt)과 [실제 재부팅 기록](../../assets/terminal/92-a50-reboot-auto-ssh-test.txt)은 같은 Wi-Fi와 충전, 잠금 없음 조건에서 해본 짧은 시험이다. 다른 조건과 하루 이상 사용은 별도로 확인한다.

[1편으로 돌아가기](01-galaxy-a50-preparation.md)
