# SSH 접속에서 막혔을 때

처음 연결은 [1편의 공개키 등록](01-galaxy-a50-preparation.md)을 따른다. 이 글은 실제로 만난 오류를 설명하는 보충 자료다.

`Permission denied (publickey)`가 나오면 PC의 개인키와 A50에 등록한 공개키가 한 쌍인지 확인한다. 공개키 파일을 옮긴 뒤 `authorized_keys`에 한 줄로 들어갔는지도 본다. 파일 전체를 지우고 다시 만들지 않는다.

작성자는 처음에 화면 입력 도구가 공개키 등록 명령을 바꿔 접속하지 못했다. 독자 절차는 공개키 파일 자체를 ADB로 보내고 Termux에서 읽도록 정리했다. [처음 실패한 출력](../../assets/terminal/83-a50-public-key-ssh-connection.txt)과 [다시 접속한 출력](../../assets/terminal/84-a50-public-key-ssh-corrected.txt)을 함께 남겼다.

휴대폰 신원 표시가 달라졌다는 메시지는 무시하지 않는다. 본인이 초기화한 장비인지, 주소가 다른 장비로 바뀌었는지 먼저 확인한다. 실제 주소와 신원 표시를 공개 캡처에 남기지 않는다.

[1편으로 돌아가기](01-galaxy-a50-preparation.md)
