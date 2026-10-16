# 본인 장비의 설정을 준비하는 방법

이 폴더에는 설정 파일의 모양만 보여주는 예시가 있다. 실제 주소와 키는 들어 있지 않다. 예시의 대문자 항목을 그대로 사용하면 연결되지 않는다.

현재 중앙 서버 0.8.0과 Android 앱 0.6.2의 개인 설정도 같은 `.deploy/` 아래에서 관리한다. iPhone은 [웹앱 설정과 설치 순서](../../docs/ios-web-app.md)를 추가로 따른다. Firebase 웹 설정과 전송용 서비스 계정 개인 키는 서로 다른 값이며, 전송 키를 웹앱에 넣지 않는다.

[시작 전에 준비할 것](../../docs/blog/mobile-app/00-reader-start.md)을 읽고 [1편](../../docs/blog/mobile-app/01-galaxy-a50-preparation.md)의 순서대로 `setup_connections.py`를 실행한다. 도구는 본인이 확인한 주소와 키로 `.deploy/` 아래에 실제 설정을 만든다. 이미 있는 설정은 덮어쓰지 않는다.

`connection.example.json`은 SSH 접속 정보, `adb.example.json`은 휴대폰 화면을 관리하는 연결 정보, `pi-connection.example.json`은 7편에서 사용하는 라즈베리파이 접속 정보다. `.deploy/`의 실제 파일은 블로그 첨부나 Git에 넣지 않는다.

Firebase의 `google-services.json`은 본인 프로젝트에서 내려받는다. 서비스 계정 JSON과 앱 서명 개인 키도 본인이 준비한다. 다른 사람의 키나 블로그 작성자의 서버 주소를 복사하는 단계는 없다.
