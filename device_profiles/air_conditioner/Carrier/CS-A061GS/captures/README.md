# 캡처 인덱스

원본 데이터는 `signals/remote-16214-15597/`에 보존한다. 프로필 폴더에 원본을 복사하지
않는 이유는 패킷을 수정할 때 서로 다른 두 기준본이 생기는 것을 막기 위해서다.

주요 연결:

- 전원 ON: `power-on-cool-17-high-01`
- 전원 OFF: `power-off-from-cool-17-high-01`
- 모드: `mode-auto-17-high-01`, `mode-cool-17-high-01`,
  `mode-dry-17-high-01`, `mode-fan-only-17-high-01`
- 풍량: `cool-18-fan-auto-to-low-01`, `cool-18-fan-low-to-medium-01`,
  `cool-18-fan-medium-to-high-01`, `cool-18-fan-high-to-auto-01`
- 온도: `cool-17-fan-auto-temp-down-01`부터 `cool-20-fan-auto-temp-up-01`
- 특수 기능: `economy-press-01-multiframe`, `turbo-cool-press-01`,
  `led-command-press-01`, `airflow-fix-command-press-01`,
  `airflow-swing-toggle-press-01`

각 ID에는 `metadata/<id>.json`, `raw/<id>.compact`, `raw/<id>.ir`가 대응한다.

