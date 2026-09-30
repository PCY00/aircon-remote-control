# 상용 Zigbee 센서 2종 식별 기록

## 기록 기준

2026-09-06에 촬영한 실물 라벨과 동봉 설명서를 기준으로 정리했다. 실물 라벨에서 직접
읽은 값은 **확인됨**, 설명서에 여러 모델이 함께 표기된 값은 **설명서 공통 정보**, 실제
Zigbee 네트워크에서 확인한 값은 **인터뷰·동작 확인 결과**로 구분한다.

제품 외관에 인쇄된 모델명과 Zigbee Basic Cluster가 보고하는 `modelID` 또는
`manufacturerName`은 다를 수 있다. 따라서 지원 여부와 MQTT 필드는 페어링 인터뷰가
끝나기 전에는 확정하지 않는다.

## 도어·창문 센서

### 확인된 실물 정보

- 제품 종류: Smart Door Window Sensor
- 실물 모델: `UZ-8D`
- 배치 번호: `A2604`
- 무선 규격: Zigbee 3.0
- 전원: CR2032, DC 3 V
- 정격 전류 표기: 1 mA
- 제조사 표기: Shenzhen Forever Young Technology Co., Ltd.

### 설명서 공통 정보

- 설명서 적용 모델: `ZD08`, `ZD03`, `ZD05`, `UZ-8D`, `UZ-3D`, `UZ-5D`
- 구성: 본체, 자석, CR2032 배터리, 양면 접착 패드, 설명서
- 페어링 표시등이 깜박이지 않으면 RESET을 표시등이 깜박일 때까지 길게 누른다.
- 본체의 중심선과 자석 표시를 맞추고 간격을 10 mm 이하로 둔다.
- 본체는 고정된 문틀, 자석은 움직이는 문이나 창 쪽에 설치하는 것을 권장한다.
- 실내용이며 물과 습기를 피한다.
- 배터리 절약을 위해 대기 상태로 들어가는 장치이며 설명서는 게이트웨이 오프라인
  판정 시간을 2시간보다 길게 두라고 안내한다.

### Zigbee 인터뷰·접점 동작 결과

2026-09-07에 ZBDongle-P와 Zigbee2MQTT 2.14.1로 실제 페어링했다.

- 외관 모델과 Zigbee 모델 매핑: `UZ-8D` → `TS0203`
- Zigbee 제조사: `Wing`
- 유형: 배터리 전원 `EndDevice`
- 인터뷰: 성공
- Zigbee2MQTT 지원: Tuya Door/window sensor 네이티브 정의, definition v0.0.0
- OTA: 미지원
- exposes: `contact`, `battery`, `voltage`, `tamper`, `battery_low`, `linkquality`

첫 완전한 MQTT 상태는 `contact=false`, 배터리 100 %, 전압 3200 mV,
`tamper=false`, `battery_low=false`였다. 설명서대로 자석을 본체 중심선에 10 mm 이내로
붙이자 `contact=true`, 2~3 cm 이상 떼자 다시 `contact=false`가 보고됐다. 따라서 이
장치에서 `true=닫힘`, `false=열림`으로 확정한다. 책상 근거리 시험 중 두 전환의
linkquality는 각각 182와 218이었지만 실제 설치 위치의 품질을 뜻하지는 않는다.

첫 RESET 시도에서는 장치가 `Wing`으로 나타난 직후 네트워크를 떠나 인터뷰가
`DatabaseEntry with ID '3' does not exist`로 실패했다. 가입 창을 닫거나 서비스를
재시작하지 않고 RESET을 약 5초 다시 눌러 페어링 모드에 넣었고, 두 번째 인터뷰와
구성은 정상 완료됐다. 데이터베이스를 수동 편집하지 않았다.

동봉 설명서의 모델군에는 `ZD08`도 포함되지만 실제 Zigbee 식별자는 `TS0203`이었다.
외관 모델명만으로 지원 정의를 고르지 않고 실제 인터뷰 결과를 기준으로 해야 한다.

### 아직 확인하지 않은 항목

- 정확한 상태·배터리 자동 보고 주기
- 실제 설치 위치 링크 품질과 반복 동작 누락률
- 재부팅 뒤 등록 유지는 확인했으며, 첫 물리 상태 전환 보고 복귀는 Step 3 통합시험에서 확인

### 사진

- [설명서 사양](../assets/hardware/zigbee/door-uz-8d-01-manual-specifications.jpg)
- [설치 방법](../assets/hardware/zigbee/door-uz-8d-02-installation.jpg)
- [실물 라벨](../assets/hardware/zigbee/door-uz-8d-03-product-label.jpg)
- [절전·설치 주의](../assets/hardware/zigbee/door-uz-8d-04-manual-special-notes.jpg)
- [설명서 표지](../assets/hardware/zigbee/door-uz-8d-05-manual-cover.jpg)
- [제조사 표기](../assets/hardware/zigbee/door-uz-8d-06-manufacturer-declaration.jpg)

## 온습도 센서

### 확인된 실물 정보

- 제품 종류: Temperature & Humidity Sensor
- 실물 모델: `Z3-P3-L`
- 무선 규격: Zigbee 3.0
- 입력 전압: DC 3 V
- 전원: LR03/AAA 1.5 V 2개
- 제조사 표기: Shenzhen New Green Energy Technologies Co Ltd

### 설명서 사양과 동작

- 대기 전류: 20 µA 이하
- 사용 온도: -10~55 °C
- 사용 습도: 0~99 %RH
- 빠른 연결 모드: 전원을 넣고 RESET을 5초 동안 누른 뒤 놓으면 표시등이 천천히
  깜박인다고 안내한다.
- 호환 모드: 연결되지 않을 때 RESET을 10초 동안 누른 뒤 놓으면 표시등이 빠르게
  깜박인다고 안내한다.
- 절전형 장치이므로 설정값 변경 후 동기화가 필요하면 버튼을 한 번 눌러 깨우라고
  안내한다.
- 실내의 평평하고 건조하며 깨끗한 곳에 놓거나 양면테이프로 부착한다.

### Zigbee 인터뷰 결과

2026-09-06에 ZBDongle-P와 Zigbee2MQTT 2.14.1로 실제 페어링했다.

- 외관 모델과 Zigbee 모델 매핑: `Z3-P3-L` → `TH01`
- Zigbee 제조사: `Zbeacon`
- 유형: 배터리 전원 `EndDevice`
- 인터뷰: 성공
- Zigbee2MQTT 지원: 네이티브 지원, definition v0.0.0
- OTA: 미지원
- exposes: `battery`, `temperature`, `humidity`, `voltage`, `linkquality`
- 보정 옵션: 온도·습도 offset과 표시 정밀도 0~3자리

첫 완전한 MQTT 상태는 온도 25.59 °C, 상대습도 39.73 %, 배터리 100 %, 전압
3000 mV였다. 센서를 손으로 감싸고 버튼을 짧게 눌러 깨운 뒤 온도 25.77 °C,
상대습도 48.15 %로 변경된 상태가 수신됐다. 책상 근거리 페어링 중 linkquality는
156~247 범위였지만 이 값만으로 실제 설치 위치 성능을 판단하지 않는다.

온도와 습도가 실제 자극에 따라 변하고 MQTT로 보고되는 것은 확인했다. 다만 관찰 시간이
짧아 정기 보고 주기와 변화 임계값은 아직 확정하지 않았다. Zigbee2MQTT 공식
[`Zbeacon TH01`](https://www.zigbee2mqtt.io/devices/TH01.html) 문서도 실제 exposes와
일치한다.

### 아직 확인하지 않은 항목

- 정확한 자동 보고 주기와 변화 임계값
- 실제 설치 위치 링크 품질과 누락률
- 재부팅 뒤 등록 유지는 확인했으며, 버튼으로 깨운 첫 보고 복귀는 Step 3 통합시험에서 확인

### 사진

- [실물 라벨](../assets/hardware/zigbee/temperature-z3-p3-l-01-product-label.jpg)
- [설치 방법](../assets/hardware/zigbee/temperature-z3-p3-l-02-installation.jpg)
- [전원·네트워크 설정](../assets/hardware/zigbee/temperature-z3-p3-l-03-network-configuration.jpg)
- [제품 구성](../assets/hardware/zigbee/temperature-z3-p3-l-04-product-description.jpg)
- [설명서 표지](../assets/hardware/zigbee/temperature-z3-p3-l-05-manual-cover.jpg)
- [제품 사양](../assets/hardware/zigbee/temperature-z3-p3-l-06-product-parameters.jpg)
- [페어링 방법](../assets/hardware/zigbee/temperature-z3-p3-l-07-pairing-instructions.jpg)

## 페어링 순서

1. 게이트웨이가 정상이고 현재 가입 허용이 닫혀 있는지 확인한다.
2. 온습도 센서만 준비하고 가입을 180초 동안 Coordinator에서만 허용한다.
3. RESET 5초 방식으로 시도하고, 실패한 경우에만 10초 호환 모드를 시도한다.
4. 인터뷰 성공 여부, 네이티브 지원 여부와 실제 exposes를 확인한다.
5. 가입을 즉시 닫고 원시 MQTT 메시지를 민감정보 제거 후 보존한다.
6. 온도·습도·배터리 보고를 확인한 뒤 도어센서를 같은 방식으로 한 대만 페어링한다.
7. 도어센서의 자석을 붙이고 떼어 닫힘·열림 값을 실험으로 확정한다.

가입 전에는 `friendly_name`을 추측해 설정하지 않는다. 인터뷰 성공 후 내부 식별자와
표시 이름을 분리하고, 공개 자료에는 IEEE 주소와 Coordinator 고유값을 넣지 않는다.

두 센서 모두 위 절차대로 한 대씩 페어링했고, 각 인터뷰 성공 직후 가입 창을 닫았다.
최종 확인에서 `permit_join=false`, 등록 장치 2대, 두 장치 모두 인터뷰 완료·지원됨,
MQTT bridge `online`이었다.

운영용 내부 이름은 온습도 센서 `sensor_temperature_01`, 도어센서 `sensor_door_01`로
지정했다. 이 이름은 MQTT 연결을 위한 안정적인 ID이며 UI에 표시할 방 이름과 기기
이름은 별도 데이터로 관리한다. 이름 변경 뒤 Zigbee2MQTT를 재시작해 두 이름이 유지되는
것을 확인하고 현재 런타임 백업을 만들었다.

## 외부 확인 자료

- [Zigbee2MQTT 지원 기기 목록](https://www.zigbee2mqtt.io/supported-devices/)
- [Zigbee2MQTT ZD08 항목](https://www.zigbee2mqtt.io/devices/ZD08.html)
- [Zigbee2MQTT Zbeacon TH01 항목](https://www.zigbee2mqtt.io/devices/TH01.html)
- [Zigbee2MQTT Tuya TS0203 항목](https://www.zigbee2mqtt.io/devices/TS0203.html)
- [Zigbee2MQTT 페어링 안내](https://www.zigbee2mqtt.io/guide/usage/pairing_devices.html)
- [Zigbee2MQTT 새 장치 지원 절차](https://www.zigbee2mqtt.io/advanced/support-new-devices/01_support_new_devices.html)
