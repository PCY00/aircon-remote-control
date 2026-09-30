# 0012. 디스플레이 전원과 Raspberry Pi USB 전원 분리

- 상태: 채택
- 날짜: 2026-09-08

## 배경

운영 장비는 Raspberry Pi 4 Model B Rev 1.4이며, 본체 전원에는 Raspberry Pi 공식
27W USB-C 전원 공급 장치(SC1417, 판매 페이지 표기 5.1V/5A)를 사용한다. 화면은
AliExpress 상품 ID `1005011932746434`의 13.3인치 1920×1200 터치 휴대용 모니터다.
기존에는 모니터에 별도 어댑터를 연결하지 않고 Pi의 USB-A에서 전원을 공급했다.

Pi 4의 공식 권장 전원은 5V/3A이며 현재 본체 어댑터의 용량은 충분하다. 그러나
Pi 4의 네 USB-A 포트가 주변 장치에 공급할 수 있는 전류는 전체 합계 1.2A다.
본체에 더 큰 전원 공급 장치를 연결해도 Pi 4의 이 하류 USB 한도는 증가하지 않는다.
13.3인치 화면의 실제 입력 정격과 순간 소비전류는 아직 제품 라벨로 확인하지 않았다.

## 결정

디스플레이 전원은 제조사가 지원하는 전원 입력 포트와 적정 정격의 별도 어댑터에서
공급한다. Pi에는 영상용 HDMI와 필요한 터치 데이터 연결만 남기고, Zigbee Coordinator는
Pi의 USB에 연결한다. 모니터의 전원·터치가 같은 포트에 결합돼 있다면 포트 표기와
설명서를 확인한 뒤 별도 전원 입력 포트를 사용하거나 역전류 방지 규격이 명확한
전원형 USB 허브를 검토한다. 지원 여부가 불명확한 Y 케이블이나 이중 전원 공급은 쓰지 않는다.

Zigbee Coordinator는 2.4GHz 간섭을 줄이기 위해 가능하면 50cm 이상의 USB 연장 케이블로
Pi와 화면·HDMI 케이블에서 떨어뜨리고 USB 2.0 포트에 연결한다.

## 근거와 한계

- Raspberry Pi 공식 문서: Pi 4 USB 주변 장치 전원은 네 포트 전체 1.2A
- Raspberry Pi 공식 문서: Pi 4 권장 입력 전원은 5V/3A
- Zigbee2MQTT 공식 문서: Pi 3/4의 간섭과 다른 USB 장치 영향을 분리하기 위해 USB 연장선과
  전원형 허브를 점검 방법으로 권장
- 과거 장애 당시 `xHCI host controller not responding`, `HC died`가 기록됐으나
  `vcgencmd get_throttled=0x0`이었다. 이것만으로 USB 과부하를 확정하거나 배제할 수 없다.
- 모니터 제거 후 현재 동글과 서비스가 정상인 것은 비교 기준일 뿐 장기 인과관계 증명은 아니다.

## 참고

- [사용 중인 공식 27W 전원 공급 장치](https://www.eleparts.co.kr/goods/view?no=14468286)
- [사용 중인 13.3인치 터치 모니터](https://ko.aliexpress.com/item/1005011932746434.html)
- [Raspberry Pi USB 전원 한도](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#maximum-power-output)
- [Zigbee2MQTT 네트워크 안정성](https://www.zigbee2mqtt.io/how_tos/how_to_improve_network_range_and_stability.html)
