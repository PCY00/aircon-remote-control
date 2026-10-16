# Firebase 웹 SDK (고정 버전)

가족 웹앱이 쓰는 Firebase JS SDK 12.19.0 ES 모듈 세 개다. Firebase SDK 세 파일을 같은 출처에서 제공하기 위해
실행 중에 외부 CDN에서 받지 않고 이 폴더의 파일을 쓴다.

- 받은 곳: `https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js`, `https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js`, `https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging.js`
- 바꾼 것: import 문의 `https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js`를 `./firebase-app.js`로 바꾼 것뿐이다 (`firebase-auth.js`, `firebase-messaging.js`에 하나씩). `firebase-app.js`는 받은 그대로다.
- 다시 받기: 저장소 루트에서 `python -I server/scripts/web/fetch_firebase_sdk.py`
- 해시 확인(네트워크 없음): `python -I server/scripts/web/fetch_firebase_sdk.py --verify`

| 파일 | 원본 크기(바이트) | 받은 원본 SHA-256 | 이 폴더 파일 SHA-256 |
|---|---:|---|---|
| `firebase-app.js` | 106558 | `39a50952b5def557337b2290069c7d7371f3515ad46c44a43b9c520f734d8d14` | `39a50952b5def557337b2290069c7d7371f3515ad46c44a43b9c520f734d8d14` |
| `firebase-auth.js` | 157113 | `59f60ce3adcb4c85a5260e963fd14134eec088de5b18ddfb9e95771c72f65264` | `0f99fc82c189cc62a37ef58558bbe91a54b83d47a8592b03144e3dc15c678b5c` |
| `firebase-messaging.js` | 37630 | `7572acc95d2f0182ef70bb16b2920b022340bde54cea5962704c745488e98b23` | `61812e6268be19a6b26ff8322202d058f94b1083af6e46cc1e42d58c98bdf683` |
