# ADR 0009: Zigbee 게이트웨이는 Docker Compose로 격리한다

## 상태

채택, 2026-09-05

## 결정

기존 FastAPI 애플리케이션은 현재 사용자 systemd 서비스를 유지한다. 새 Mosquitto와
Zigbee2MQTT만 별도의 Docker Compose 프로젝트 `aircon-zigbee`로 실행한다.

- Mosquitto: `eclipse-mosquitto:2.1.2-alpine`
- Zigbee2MQTT: `ghcr.io/koenkk/zigbee2mqtt:2.14.1`
- MQTT host bind: `127.0.0.1:1883`
- Zigbee2MQTT frontend host bind: `127.0.0.1:8080`
- ZBDongle-P adapter: `zstack`, host의 `/dev/serial/by-id/...`를 컨테이너
  `/dev/ttyUSB0`에 매핑
- Zigbee channel: `20`

## 이유

- Node.js와 Zigbee2MQTT 의존성을 Pi 호스트 Python 환경에서 분리한다.
- 블로그 독자가 같은 Compose 파일과 이미지 버전으로 재현할 수 있다.
- 버전 업데이트와 롤백 범위를 컨테이너 이미지로 제한한다.
- 영구 데이터와 비밀정보를 코드 배포 대상에서 분리할 수 있다.
- 기존 포트 8001 서비스와 수명주기를 분리한다.

## 보안

MQTT와 관리 화면은 루프백에만 게시한다. 컨테이너 내부 Mosquitto는 익명 접속을
거부하고 무작위 비밀번호를 사용한다. Zigbee 네트워크 키와 관리 토큰도 Pi에서만
무작위 생성하며 `runtime/zigbee/`에 권한 `600`으로 저장한다.

## 선택하지 않은 대안

Zigbee2MQTT를 Node.js와 systemd로 직접 설치할 수 있지만 Node/pnpm/빌드 도구와
업데이트 절차가 호스트에 결합된다. Raspberry Pi 전체를 컨테이너화하는 방식은 정상
운영 중인 FastAPI 서비스를 불필요하게 변경하므로 선택하지 않았다.

## 결과와 주의점

- Pi에 Docker 서비스가 추가된다.
- `air` 사용자는 Docker 그룹에 들어가며 이는 사실상 높은 시스템 권한을 갖는다는
  보안상 의미가 있다. Pi를 단일 목적 장비로 운용하고 SSH 접근을 제한한다.
- 동글 장치 전달과 볼륨 권한을 별도로 관리해야 한다.
- 이미지 태그는 자동으로 `latest`를 따라가지 않고 검토·백업 후 명시적으로 갱신한다.
- 백업은 Zigbee2MQTT와 Mosquitto를 함께 잠시 정지한 일관된 스냅샷으로 만든다. 백업에는
  네트워크 키와 인증정보가 포함되므로 Pi 안에서 권한 `600`으로만 보관한다.
