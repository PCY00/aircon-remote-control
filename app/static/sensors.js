(() => {
  const root = document.getElementById('room-first-design-studio');
  if (!root) return;

  const SETTINGS_KEY = 'smart-home.sensor-refresh-policy.v1';
  const DISPLAY_TIME_ZONE = 'Asia/Seoul';
  const DEFAULT_SETTINGS = Object.freeze({
    enabled: true,
    pauseStart: '07:00',
    pauseEnd: '19:00',
    intervalMinutes: 5
  });
  const ALLOWED_ICONS = new Set(['door-open', 'thermometer-sun', 'droplets', 'activity', 'radio-tower']);
  const announcer = root.querySelector('[data-announcer]');
  const overview = root.querySelector('[data-sensor-overview]');
  const refreshButtons = [...root.querySelectorAll('[data-refresh-sensors], [data-refresh-current-sensor]')];
  const settingsDialog = root.querySelector('[data-sensor-settings-dialog]');
  const settingsForm = root.querySelector('[data-sensor-settings-form]');
  const managerDialog = root.querySelector('[data-sensor-manager-dialog]');
  const editorForm = root.querySelector('[data-sensor-editor-form]');
  let sensors = [];
  let zigbeeDevices = [];
  let bridgeStatus = null;
  let joinStatus = null;
  let settings = loadSettings();
  let currentSensorId = '';
  let detailReturnView = 'home';
  let autoRefreshTimer = null;
  let refreshInFlight = false;
  let joinRequestInFlight = false;
  let joinCountdownTimer = null;
  let joinPollTimer = null;
  let joinDeadlineMs = 0;
  let renderedManagerSignature = '';
  let eventSource = null;
  let lastClimateRefreshAt = null;
  const eventHistory = new Map();
  const historyRequests = new Map();
  const historyErrors = new Map();

  function loadJson(key, fallback) {
    try {
      const stored = window.localStorage.getItem(key);
      return stored ? JSON.parse(stored) : fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function loadSettings() {
    const loaded = loadJson(SETTINGS_KEY, {});
    const saved = loaded && typeof loaded === 'object' ? loaded : {};
    const interval = Number(saved.intervalMinutes);
    return {
      enabled: typeof saved.enabled === 'boolean' ? saved.enabled : DEFAULT_SETTINGS.enabled,
      pauseStart: /^\d{2}:\d{2}$/.test(saved.pauseStart || '') ? saved.pauseStart : DEFAULT_SETTINGS.pauseStart,
      pauseEnd: /^\d{2}:\d{2}$/.test(saved.pauseEnd || '') ? saved.pauseEnd : DEFAULT_SETTINGS.pauseEnd,
      intervalMinutes: [1, 5, 10, 30, 60].includes(interval) ? interval : DEFAULT_SETTINGS.intervalMinutes
    };
  }

  async function apiCall(path, options = {}) {
    const headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, { ...options, headers });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload && typeof payload.detail === 'string' ? payload.detail : '센서 API 요청을 처리하지 못했어요.';
      throw new Error(detail);
    }
    return payload;
  }

  function createIcon(name) {
    const icon = document.createElement('i');
    icon.dataset.lucide = name;
    icon.setAttribute('aria-hidden', 'true');
    return icon;
  }

  function refreshIcons() {
    if (!window.lucide) return;
    window.lucide.createIcons({ attrs: { 'aria-hidden': 'true', 'stroke-width': 2 } });
  }

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function setIcon(container, name) {
    const current = container.querySelector('[data-lucide]');
    if (current?.dataset.lucide === name) return false;
    if (current) current.replaceWith(createIcon(name));
    else container.prepend(createIcon(name));
    return true;
  }

  function defaultMetadata(sensor) {
    if (sensor.kind === 'door_contact') {
      return { displayName: '문 열림 센서', room: '공간 미지정', icon: 'door-open' };
    }
    if (sensor.kind === 'temperature_humidity') {
      return { displayName: '온·습도 센서', room: '공간 미지정', icon: 'thermometer-sun' };
    }
    return { displayName: sensor.device_id, room: '공간 미지정', icon: 'activity' };
  }

  function sensorMetadata(sensor) {
    const fallback = defaultMetadata(sensor);
    const saved = sensor.metadata || {};
    return {
      displayName: typeof saved.display_name === 'string' && saved.display_name.trim() ? saved.display_name.trim() : fallback.displayName,
      room: typeof saved.room === 'string' && saved.room.trim() ? saved.room.trim() : fallback.room,
      icon: ALLOWED_ICONS.has(saved.icon) ? saved.icon : fallback.icon
    };
  }

  function numeric(value, suffix = '') {
    return typeof value === 'number' && Number.isFinite(value) ? `${value}${suffix}` : '—';
  }

  function formatDateTime(value) {
    if (!value) return '기록 없음';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '기록 없음';
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: DISPLAY_TIME_ZONE,
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    }).format(date);
  }

  function formatTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: DISPLAY_TIME_ZONE,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    }).format(date);
  }

  function relativeTime(value) {
    if (!value) return '보고 없음';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '보고 없음';
    const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return '방금 전';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}분 전`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}시간 전`;
    return `${Math.floor(hours / 24)}일 전`;
  }

  function minutesOfDay(value) {
    const [hour, minute] = value.split(':').map(Number);
    return hour * 60 + minute;
  }

  function isPauseTime(date = new Date()) {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: DISPLAY_TIME_ZONE,
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(date);
    const now = Number(parts.find((part) => part.type === 'hour').value) * 60
      + Number(parts.find((part) => part.type === 'minute').value);
    const start = minutesOfDay(settings.pauseStart);
    const end = minutesOfDay(settings.pauseEnd);
    if (start === end) return true;
    if (start < end) return now >= start && now < end;
    return now >= start || now < end;
  }

  function climateRefreshAllowed(automatic, now = new Date()) {
    if (!automatic) return true;
    return settings.enabled && !isPauseTime(now)
      && (lastClimateRefreshAt === null
        || now.getTime() - lastClimateRefreshAt >= settings.intervalMinutes * 60 * 1000);
  }

  function policySummary() {
    if (!settings.enabled) return '자동 갱신 꺼짐 · 수동으로만 확인';
    const suffix = isPauseTime() ? ' · 지금은 일시 정지' : ` · ${settings.intervalMinutes}분 간격`;
    return `${settings.pauseStart}~${settings.pauseEnd} 자동 갱신 안 함${suffix}`;
  }

  function updatePolicyText() {
    const summary = policySummary();
    root.querySelectorAll('[data-sensor-policy-summary], [data-more-sensor-policy]').forEach((node) => {
      node.textContent = summary;
    });
    const preview = root.querySelector('[data-sensor-settings-preview]');
    if (preview) preview.textContent = summary;
  }

  function setLoading(loading) {
    refreshButtons.forEach((button) => {
      button.dataset.loading = String(loading);
      button.disabled = loading;
    });
    const discoverButton = root.querySelector('[data-discover-sensors]');
    if (discoverButton && managerDialog.open) {
      discoverButton.dataset.loading = String(loading);
      discoverButton.disabled = loading;
    }
  }

  function bridgeLabel() {
    if (!bridgeStatus) return { label: '센서 연결 확인 중', state: 'loading' };
    if (bridgeStatus.connected) return { label: `Zigbee 센서 연결됨 · ${sensors.length}개`, state: 'online' };
    if (!bridgeStatus.enabled) return { label: `로컬 미연결 · 저장 센서 ${sensors.length}개`, state: 'offline' };
    if (bridgeStatus.running) return { label: `MQTT 재연결 중 · 저장 센서 ${sensors.length}개`, state: 'offline' };
    return { label: 'MQTT 연결 중단', state: 'offline' };
  }

  function updateBridgeView() {
    const target = root.querySelector('[data-sensor-connection]');
    const result = bridgeLabel();
    setText(target, result.label);
    target.dataset.state = result.state;
  }

  function sensorCard(sensor) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sensor-card';
    button.dataset.sensorId = sensor.device_id;

    const top = document.createElement('span');
    top.className = 'sensor-card-top';
    const icon = document.createElement('span');
    icon.className = 'sensor-card-icon';
    const battery = document.createElement('span');
    battery.className = 'sensor-card-battery';
    top.append(icon, battery);

    const value = document.createElement('strong');
    value.className = 'sensor-card-value';

    const name = document.createElement('span');
    name.className = 'sensor-card-name';
    const details = document.createElement('span');
    details.className = 'sensor-card-meta';
    const room = document.createElement('span');
    const last = document.createElement('span');
    details.append(room, last);
    button.append(top, value, name, details);
    button.addEventListener('click', () => openSensorDetail(button.dataset.sensorId, 'home'));
    updateSensorCard(button, sensor);
    return button;
  }

  function updateSensorCard(button, sensor) {
    const meta = sensorMetadata(sensor);
    const state = sensor.state || {};
    button.dataset.kind = sensor.kind;
    button.dataset.sensorId = sensor.device_id;
    if (sensor.kind === 'door_contact') button.dataset.doorState = state.door_state || 'unknown';
    else delete button.dataset.doorState;

    const iconChanged = setIcon(button.querySelector('.sensor-card-icon'), meta.icon);
    setText(
      button.querySelector('.sensor-card-battery'),
      typeof state.battery_percent === 'number' ? `배터리 ${state.battery_percent}%` : '배터리 —'
    );
    const primary = sensor.kind === 'door_contact'
      ? (state.door_state === 'open' ? '열림' : (state.door_state === 'closed' ? '닫힘' : '확인 필요'))
      : (sensor.kind === 'temperature_humidity'
          ? `${numeric(state.temperature_c, '°C')} · ${numeric(state.humidity_percent, '%')}`
          : '상태 확인');
    setText(button.querySelector('.sensor-card-value'), primary);
    setText(button.querySelector('.sensor-card-name'), meta.displayName);
    setText(button.querySelector('.sensor-card-meta span:first-child'), meta.room);
    setText(
      button.querySelector('.sensor-card-meta span:last-child'),
      sensor.kind === 'door_contact' && sensor.last_changed_at
        ? `변경 ${relativeTime(sensor.last_changed_at)}`
        : `보고 ${relativeTime(sensor.last_reported_at)}`
    );
    return iconChanged;
  }

  function renderOverviewMessage(kind, detailMessage) {
    const signature = `${kind}:${detailMessage}`;
    if (overview.dataset.renderSignature === signature) return;
    const empty = document.createElement('div');
    empty.className = 'sensor-empty-state';
    empty.append(createIcon(kind === 'error' ? 'circle-alert' : 'radio-tower'));
    const title = document.createElement('strong');
    title.textContent = kind === 'error' ? '센서 상태를 불러오지 못했어요' : '아직 저장된 센서 보고가 없어요';
    const detail = document.createElement('small');
    detail.textContent = detailMessage;
    empty.append(title, detail);
    if (kind !== 'error') {
      const manage = document.createElement('button');
      manage.type = 'button';
      manage.className = 'section-manage';
      manage.textContent = '센서 추가 방법 보기';
      manage.addEventListener('click', openSensorManager);
      empty.append(manage);
    }
    overview.replaceChildren(empty);
    overview.dataset.renderSignature = signature;
    refreshIcons();
  }

  function renderOverview(errorMessage = '') {
    if (errorMessage && sensors.length === 0) {
      renderOverviewMessage('error', errorMessage);
      return;
    }
    if (sensors.length === 0) {
      renderOverviewMessage('empty', '페어링된 센서를 한 번 작동시키면 여기에 나타납니다.');
      return;
    }

    overview.dataset.renderSignature = 'sensors';
    overview.querySelectorAll('.sensor-empty-state').forEach((node) => node.remove());
    const knownIds = new Set(sensors.map((sensor) => sensor.device_id));
    overview.querySelectorAll('.sensor-card').forEach((card) => {
      if (!knownIds.has(card.dataset.sensorId)) card.remove();
    });

    let iconsChanged = false;
    sensors.forEach((sensor, index) => {
      let card = overview.querySelector(`.sensor-card[data-sensor-id="${CSS.escape(sensor.device_id)}"]`);
      if (!card) {
        card = sensorCard(sensor);
        iconsChanged = true;
      } else {
        iconsChanged = updateSensorCard(card, sensor) || iconsChanged;
      }
      const currentAtIndex = overview.children[index];
      if (currentAtIndex !== card) overview.insertBefore(card, currentAtIndex || null);
    });
    if (iconsChanged) refreshIcons();
  }

  function tileStatus(sensor) {
    const state = sensor.state || {};
    if (sensor.kind === 'door_contact') {
      const label = state.door_state === 'open' ? '열림' : (state.door_state === 'closed' ? '닫힘' : '상태 확인');
      return `${label} · ${relativeTime(sensor.last_changed_at || sensor.last_reported_at)}`;
    }
    if (sensor.kind === 'temperature_humidity') {
      return `${numeric(state.temperature_c, '°C')} · 습도 ${numeric(state.humidity_percent, '%')}`;
    }
    return `마지막 보고 ${relativeTime(sensor.last_reported_at)}`;
  }

  function updateSensorTile(tile, sensor) {
    const meta = sensorMetadata(sensor);
    tile.dataset.room = meta.room;
    tile.dataset.sensorId = sensor.device_id;
    tile.dataset.deviceKind = 'sensor';
    tile.dataset.deviceCapabilities = 'status,history';
    tile.setAttribute('aria-pressed', 'true');
    const iconChanged = setIcon(tile, meta.icon);
    setText(tile.querySelector('strong'), meta.displayName);
    setText(tile.querySelector('small'), tileStatus(sensor));
    return iconChanged;
  }

  function updateConnectedCounts() {
    const connectedCount = root.querySelectorAll('.device-grid .device-tile:not([data-demo-device])').length;
    setText(root.querySelector('[data-device-count]'), String(connectedCount));
    setText(root.querySelector('[data-more-device-count]'), String(connectedCount));
    setText(root.querySelector('[data-more-sensor-count]'), String(sensors.length));
  }

  function syncDeviceTiles() {
    const grid = root.querySelector('.device-grid');
    const knownIds = new Set(sensors.map((sensor) => sensor.device_id));
    grid.querySelectorAll('[data-sensor-id]').forEach((tile) => {
      if (!knownIds.has(tile.dataset.sensorId)) tile.remove();
    });

    let iconsChanged = false;
    sensors.forEach((sensor) => {
      let tile = grid.querySelector(`[data-sensor-id="${CSS.escape(sensor.device_id)}"]`);
      if (!tile) {
        tile = document.createElement('button');
        tile.type = 'button';
        tile.className = 'device-tile sensor-device-tile';
        tile.append(createIcon('activity'));
        const dot = document.createElement('span');
        dot.className = 'sensor-live-dot';
        dot.setAttribute('aria-hidden', 'true');
        const name = document.createElement('strong');
        const status = document.createElement('small');
        tile.append(dot, name, status);
        tile.addEventListener('click', () => openSensorDetail(sensor.device_id, 'home'));
        grid.append(tile);
        iconsChanged = true;
      }
      iconsChanged = updateSensorTile(tile, sensor) || iconsChanged;
    });

    updateConnectedCounts();
    if (iconsChanged) refreshIcons();
  }

  function addFact(list, label, value) {
    const row = document.createElement('div');
    row.className = 'sensor-fact';
    const term = document.createElement('dt');
    term.textContent = label;
    const description = document.createElement('dd');
    description.textContent = value;
    row.append(term, description);
    list.append(row);
  }

  function syncFacts(list, entries) {
    entries.forEach(([label, value], index) => {
      let row = list.children[index];
      if (!row) {
        addFact(list, label, value);
        row = list.children[index];
      }
      setText(row.querySelector('dt'), label);
      setText(row.querySelector('dd'), value);
    });
    while (list.children.length > entries.length) list.lastElementChild.remove();
  }

  function renderDoorEvents(sensor) {
    const block = root.querySelector('[data-door-history-block]');
    const list = root.querySelector('[data-door-event-list]');
    const empty = root.querySelector('[data-door-event-empty]');
    const events = eventHistory.get(sensor.device_id) || [];
    const historyError = historyErrors.get(sensor.device_id);
    empty.textContent = historyError && events.length === 0
      ? '기록을 불러오지 못했어요. 최신 저장값 확인을 다시 눌러 주세요.'
      : '아직 상태가 바뀐 기록이 없어요.';
    block.hidden = false;
    const signature = JSON.stringify([sensor.device_id, events.map((event) => [event.state, event.previous_state, event.occurred_at])]);
    if (list.dataset.renderSignature === signature) {
      empty.hidden = events.length !== 0;
      return false;
    }
    list.replaceChildren();
    events.forEach((event) => {
      const item = document.createElement('li');
      item.className = 'door-event';
      const icon = document.createElement('span');
      icon.className = 'door-event-icon';
      icon.append(createIcon(event.state === 'open' ? 'door-open' : 'door-closed'));
      const copy = document.createElement('span');
      copy.className = 'door-event-copy';
      const title = document.createElement('strong');
      title.textContent = event.state === 'open' ? '문이 열렸어요' : '문이 닫혔어요';
      const transition = document.createElement('small');
      transition.textContent = `${event.previous_state === 'open' ? '열림' : '닫힘'} → ${event.state === 'open' ? '열림' : '닫힘'}`;
      copy.append(title, transition);
      const time = document.createElement('time');
      time.dateTime = event.occurred_at;
      time.textContent = formatDateTime(event.occurred_at);
      item.append(icon, copy, time);
      list.append(item);
    });
    list.dataset.renderSignature = signature;
    empty.hidden = events.length !== 0;
    return events.length !== 0;
  }

  function renderSensorDetail() {
    const sensor = sensors.find((item) => item.device_id === currentSensorId);
    if (!sensor) return;
    const meta = sensorMetadata(sensor);
    const state = sensor.state || {};
    setText(root.querySelector('[data-sensor-detail-name]'), meta.displayName);
    setText(root.querySelector('[data-sensor-detail-room]'), meta.room);
    let iconsChanged = setIcon(root.querySelector('.sensor-detail-icon'), meta.icon);

    const primary = root.querySelector('[data-sensor-detail-primary]');
    const secondary = root.querySelector('[data-sensor-detail-secondary]');
    if (sensor.kind === 'door_contact') {
      setText(primary, state.door_state === 'open' ? '문 열림' : (state.door_state === 'closed' ? '문 닫힘' : '상태 확인'));
      setText(secondary, sensor.last_changed_at
        ? `마지막 상태 변경 ${formatDateTime(sensor.last_changed_at)}`
        : `실제 상태 변경 기록 없음 · 최초 상태 확인 ${formatDateTime(sensor.first_seen_at)}`);
      iconsChanged = renderDoorEvents(sensor) || iconsChanged;
      root.querySelector('[data-climate-refresh-note]').hidden = true;
    } else if (sensor.kind === 'temperature_humidity') {
      setText(primary, `${numeric(state.temperature_c, '°C')}`);
      setText(secondary, `습도 ${numeric(state.humidity_percent, '%')} · 마지막 보고 ${relativeTime(sensor.last_reported_at)}`);
      root.querySelector('[data-door-history-block]').hidden = true;
      root.querySelector('[data-climate-refresh-note]').hidden = false;
    } else {
      setText(primary, '상태 확인');
      setText(secondary, `마지막 보고 ${relativeTime(sensor.last_reported_at)}`);
      root.querySelector('[data-door-history-block]').hidden = true;
      root.querySelector('[data-climate-refresh-note]').hidden = true;
    }

    const facts = root.querySelector('[data-sensor-facts]');
    const entries = [
      ['Zigbee 이름', sensor.device_id],
      ['최초 상태 확인', formatDateTime(sensor.first_seen_at)],
      ['마지막 보고', formatDateTime(sensor.last_reported_at)],
      ['수신 시각', formatDateTime(sensor.last_received_at)],
      ['배터리', numeric(state.battery_percent, '%')],
      ['신호 품질', numeric(state.linkquality)]
    ];
    if (typeof state.voltage_mv === 'number') entries.push(['배터리 전압', numeric(state.voltage_mv, 'mV')]);
    syncFacts(facts, entries);
    if (iconsChanged) refreshIcons();
  }

  function openSensorDetail(deviceId, returnView = 'home') {
    currentSensorId = deviceId;
    detailReturnView = returnView;
    root.querySelector('[data-home-view]').hidden = true;
    root.querySelector('[data-devices-view]').hidden = true;
    root.querySelector('[data-automation-view]').hidden = true;
    root.querySelector('[data-more-view]').hidden = true;
    root.querySelector('[data-aircon-detail]').hidden = true;
    root.querySelector('[data-sensor-detail]').hidden = false;
    root.classList.add('show-device-detail');
    renderSensorDetail();
    if (announcer) announcer.textContent = `${sensorMetadata(sensors.find((item) => item.device_id === deviceId)).displayName} 상세 열림`;
  }

  function closeSensorDetail() {
    root.querySelector('[data-sensor-detail]').hidden = true;
    root.classList.remove('show-device-detail');
    const destination = root.querySelector(`[data-nav="${detailReturnView}"]`) || root.querySelector('[data-nav="home"]');
    destination.click();
  }

  function renderManagerList({ force = false } = {}) {
    const list = root.querySelector('[data-sensor-manager-list]');
    const empty = root.querySelector('[data-sensor-manager-empty]');
    const signature = JSON.stringify(sensors.map((sensor) => [sensor.device_id, sensorMetadata(sensor)]));
    if (!force && renderedManagerSignature === signature) return;
    list.replaceChildren();
    sensors.forEach((sensor) => {
      const meta = sensorMetadata(sensor);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sensor-manager-item';
      const icon = document.createElement('span');
      icon.append(createIcon(meta.icon));
      const copy = document.createElement('span');
      const name = document.createElement('strong');
      name.textContent = meta.displayName;
      const detail = document.createElement('small');
      detail.textContent = `${meta.room} · ${sensor.device_id}`;
      copy.append(name, detail);
      const action = document.createElement('span');
      action.textContent = sensor.metadata?.customized ? '수정' : '설정';
      button.append(icon, copy, action);
      button.addEventListener('click', () => openSensorEditor(sensor.device_id));
      list.append(button);
    });
    renderedManagerSignature = signature;
    empty.hidden = sensors.length !== 0;
    refreshIcons();
  }

  function roomNames() {
    const names = [...root.querySelectorAll('[data-room-tab]:not([data-system-room]) span')]
      .map((node) => node.textContent.trim())
      .filter(Boolean);
    return ['공간 미지정', ...new Set(names)];
  }

  function openSensorEditor(deviceId) {
    const sensor = sensors.find((item) => item.device_id === deviceId);
    if (!sensor) return;
    const meta = sensorMetadata(sensor);
    editorForm.hidden = false;
    editorForm.elements.device_id.value = deviceId;
    editorForm.elements.display_name.value = meta.displayName;
    const roomSelect = editorForm.elements.room;
    roomSelect.replaceChildren();
    roomNames().forEach((room) => {
      const option = document.createElement('option');
      option.value = room;
      option.textContent = room;
      roomSelect.append(option);
    });
    roomSelect.value = roomNames().includes(meta.room) ? meta.room : '공간 미지정';
    editorForm.elements.icon.value = meta.icon;
    root.querySelector('[data-sensor-editor-id]').textContent = `Zigbee 식별자 · ${deviceId}`;
    editorForm.elements.display_name.focus();
  }

  function stopJoinTimers() {
    if (joinCountdownTimer) window.clearInterval(joinCountdownTimer);
    if (joinPollTimer) window.clearInterval(joinPollTimer);
    joinCountdownTimer = null;
    joinPollTimer = null;
  }

  function safeZigbeeName(name) {
    return /^0x[0-9a-f]{16}$/i.test(name || '') ? '새 Zigbee 기기' : (name || '이름 확인 중');
  }

  function renderZigbeeDevices() {
    const list = root.querySelector('[data-zigbee-device-list]');
    const empty = root.querySelector('[data-zigbee-device-empty]');
    list.replaceChildren();
    zigbeeDevices.forEach((device) => {
      const item = document.createElement('li');
      const icon = document.createElement('span');
      icon.append(createIcon(device.interviewing ? 'loader-circle' : (device.supported ? 'badge-check' : 'triangle-alert')));
      const copy = document.createElement('span');
      const name = document.createElement('strong');
      name.textContent = safeZigbeeName(device.friendly_name);
      const model = device.model || device.model_id || '모델 확인 중';
      const detail = document.createElement('small');
      if (device.interviewing) detail.textContent = `${model} · 연결 정보 확인 중`;
      else if (device.interview_state === 'FAILED') detail.textContent = `${model} · 인터뷰 실패`;
      else if (!device.supported) detail.textContent = `${model} · 지원 정의 없음`;
      else detail.textContent = `${model} · 연결됨`;
      copy.append(name, detail);
      item.append(icon, copy);
      list.append(item);
    });
    empty.hidden = zigbeeDevices.length !== 0;
    refreshIcons();
  }

  function renderJoinStatus() {
    const status = root.querySelector('[data-zigbee-join-status]');
    const openButton = root.querySelector('[data-open-zigbee-join]');
    const closeButton = root.querySelector('[data-close-zigbee-join]');
    const duration = root.querySelector('[data-zigbee-join-duration]');
    const supported = Boolean(joinStatus?.supported);
    const active = supported && Boolean(joinStatus?.permit_join) && joinDeadlineMs > Date.now();
    const remaining = active ? Math.max(0, Math.ceil((joinDeadlineMs - Date.now()) / 1000)) : 0;

    if (!supported) {
      status.textContent = '이 서버에서는 Zigbee 가입을 제어할 수 없어요.';
      status.dataset.state = 'offline';
    } else if (active) {
      status.textContent = `새 기기 연결 허용 중 · ${remaining}초 남음`;
      status.dataset.state = 'open';
    } else {
      status.textContent = '새 기기 연결 차단됨';
      status.dataset.state = 'closed';
    }
    openButton.hidden = active;
    closeButton.hidden = !active;
    openButton.disabled = joinRequestInFlight || !supported;
    closeButton.disabled = joinRequestInFlight;
    duration.disabled = joinRequestInFlight || active;
  }

  function startJoinTimers() {
    stopJoinTimers();
    if (!managerDialog.open || !joinStatus?.permit_join) return;
    joinCountdownTimer = window.setInterval(() => {
      renderJoinStatus();
      if (joinDeadlineMs <= Date.now()) refreshJoinPanel({ silent: true });
    }, 1000);
    joinPollTimer = window.setInterval(async () => {
      await Promise.all([
        refreshJoinPanel({ silent: true }),
        refreshSensors({ automatic: true, force: true })
      ]);
    }, 3000);
  }

  async function refreshJoinPanel({ silent = false } = {}) {
    try {
      const [status, devices] = await Promise.all([
        apiCall('/api/v1/zigbee/join'),
        apiCall('/api/v1/zigbee/devices')
      ]);
      joinStatus = status;
      joinDeadlineMs = status.permit_join
        ? Date.now() + Math.max(0, Number(status.remaining_seconds) || 0) * 1000
        : 0;
      zigbeeDevices = Array.isArray(devices.items) ? devices.items : [];
      renderJoinStatus();
      renderZigbeeDevices();
      startJoinTimers();
    } catch (error) {
      joinStatus = { supported: false, permit_join: false };
      joinDeadlineMs = 0;
      renderJoinStatus();
      if (!silent && announcer) announcer.textContent = `Zigbee 상태 확인 실패: ${error.message}`;
    }
  }

  async function openJoin() {
    if (joinRequestInFlight) return;
    joinRequestInFlight = true;
    renderJoinStatus();
    const duration = Number(root.querySelector('[data-zigbee-join-duration]').value);
    try {
      joinStatus = await apiCall('/api/v1/zigbee/join', {
        method: 'POST',
        body: JSON.stringify({ duration_seconds: duration })
      });
      joinDeadlineMs = Date.now() + Math.max(0, Number(joinStatus.remaining_seconds) || 0) * 1000;
      if (announcer) announcer.textContent = `Zigbee 새 기기 연결을 ${duration}초 동안 허용했어요`;
    } catch (error) {
      if (announcer) announcer.textContent = `Zigbee 연결 허용 실패: ${error.message}`;
    } finally {
      joinRequestInFlight = false;
      renderJoinStatus();
      startJoinTimers();
    }
  }

  async function closeJoin({ silent = false } = {}) {
    if (joinRequestInFlight || !joinStatus?.permit_join) {
      stopJoinTimers();
      return;
    }
    joinRequestInFlight = true;
    renderJoinStatus();
    try {
      joinStatus = await apiCall('/api/v1/zigbee/join', { method: 'DELETE' });
      joinDeadlineMs = 0;
      if (!silent && announcer) announcer.textContent = 'Zigbee 새 기기 연결을 닫았어요';
    } catch (error) {
      if (announcer) announcer.textContent = `Zigbee 연결 종료 확인 실패: ${error.message}`;
    } finally {
      joinRequestInFlight = false;
      stopJoinTimers();
      renderJoinStatus();
    }
  }

  function openSensorManager() {
    editorForm.hidden = true;
    renderManagerList({ force: true });
    managerDialog.showModal();
    refreshJoinPanel();
  }

  function scheduleAutoRefresh() {
    if (autoRefreshTimer) window.clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
    if (!settings.enabled) return;
    autoRefreshTimer = window.setInterval(() => {
      updatePolicyText();
      if (!document.hidden && !isPauseTime()) refreshSensors({ automatic: true });
    }, settings.intervalMinutes * 60 * 1000);
  }

  function mergeSensorSnapshot(incoming, current, preferCurrentOnTie = false) {
    if (!current) return incoming;
    const currentTime = Date.parse(current.last_received_at) || 0;
    const incomingTime = Date.parse(incoming.last_received_at) || 0;
    const latest = currentTime > incomingTime || (preferCurrentOnTie && currentTime === incomingTime) ? current : incoming;
    const currentMetadataTime = Date.parse(current.metadata?.updated_at) || 0;
    const incomingMetadataTime = Date.parse(incoming.metadata?.updated_at) || 0;
    const metadata = currentMetadataTime > incomingMetadataTime ? current.metadata : incoming.metadata;
    return latest.metadata === metadata ? latest : { ...latest, metadata };
  }

  async function refreshDoorHistory(deviceId) {
    const requestId = (historyRequests.get(deviceId) || 0) + 1;
    historyRequests.set(deviceId, requestId);
    try {
      const history = await apiCall(`/api/v1/sensors/${encodeURIComponent(deviceId)}/events?limit=20`);
      if (historyRequests.get(deviceId) !== requestId) return;
      eventHistory.set(deviceId, Array.isArray(history.items) ? history.items : []);
      historyErrors.delete(deviceId);
    } catch (_error) {
      if (historyRequests.get(deviceId) === requestId) historyErrors.set(deviceId, true);
      // A temporary network failure must not erase previously confirmed events.
    }
  }

  async function refreshSensors({ automatic = false, force = false } = {}) {
    if (refreshInFlight) return;
    if (automatic && isPauseTime() && !force) return;
    refreshInFlight = true;
    setLoading(true);
    const previousById = new Map(sensors.map((sensor) => [sensor.device_id, sensor]));
    try {
      const [status, list] = await Promise.all([
        apiCall('/api/v1/sensors/status'),
        apiCall('/api/v1/sensors')
      ]);
      bridgeStatus = status;
      // SSE may have updated or discovered a sensor while these GETs were in flight.
      const currentById = new Map(sensors.map((sensor) => [sensor.device_id, sensor]));
      // Reconnect/pairing may refresh door state, but must not bypass the climate policy.
      const allowClimate = climateRefreshAllowed(automatic);
      (Array.isArray(list.items) ? list.items : []).forEach((sensor) => {
        if (sensor.kind === 'temperature_humidity' && !allowClimate) return;
        const current = currentById.get(sensor.device_id);
        currentById.set(sensor.device_id, mergeSensorSnapshot(sensor, current, current !== previousById.get(sensor.device_id)));
      });
      sensors = [...currentById.values()].sort((left, right) => left.device_id.localeCompare(right.device_id));
      if (allowClimate) lastClimateRefreshAt = Date.now();
      const doorSensors = sensors.filter((sensor) => {
        if (sensor.kind !== 'door_contact') return false;
        const previous = previousById.get(sensor.device_id);
        return !eventHistory.has(sensor.device_id)
          || historyErrors.has(sensor.device_id)
          || previous?.last_changed_at !== sensor.last_changed_at
          || (!automatic && currentSensorId === sensor.device_id);
      });
      await Promise.all(doorSensors.map((sensor) => refreshDoorHistory(sensor.device_id)));
      updateBridgeView();
      renderOverview();
      syncDeviceTiles();
      if (currentSensorId) renderSensorDetail();
      if (managerDialog.open) renderManagerList();
      const now = new Date();
      root.querySelector('[data-sensor-last-refresh]').textContent = `${formatTime(now.toISOString())} 확인`;
      if (announcer && !automatic) announcer.textContent = `센서 ${sensors.length}개 최신 저장값 확인 완료`;
    } catch (error) {
      bridgeStatus = null;
      updateBridgeView();
      renderOverview(error.message);
      if (announcer) announcer.textContent = `센서 새로고침 실패: ${error.message}`;
    } finally {
      refreshInFlight = false;
      setLoading(false);
      updatePolicyText();
    }
  }

  async function applyLiveSensorUpdate(sensor) {
    if (!sensor || typeof sensor.device_id !== 'string') return;
    // Climate cards use only the configured interval or an explicit manual refresh.
    // MQTT ingestion/storage continues on the Pi even while display refresh is paused.
    if (sensor.kind === 'temperature_humidity') return;
    const index = sensors.findIndex((item) => item.device_id === sensor.device_id);
    if (index >= 0) sensors[index] = mergeSensorSnapshot(sensor, sensors[index]);
    else sensors.push(sensor);
    sensors.sort((left, right) => left.device_id.localeCompare(right.device_id));

    if (sensor.kind === 'door_contact' && sensor.event_recorded) {
      await refreshDoorHistory(sensor.device_id);
    }
    updateBridgeView();
    renderOverview();
    syncDeviceTiles();
    if (currentSensorId === sensor.device_id) renderSensorDetail();
    if (managerDialog.open) renderManagerList();
    const latest = sensors.find((item) => item.device_id === sensor.device_id);
    root.querySelector('[data-sensor-last-refresh]').textContent = `${formatTime(latest.last_received_at)} 실시간`;
  }

  function connectEventStream() {
    if (!window.EventSource || eventSource) return;
    eventSource = new EventSource('/api/v1/events');
    eventSource.onopen = () => refreshSensors({ automatic: true, force: true });
    eventSource.onmessage = async (message) => {
      try {
        const event = JSON.parse(message.data);
        window.dispatchEvent(new CustomEvent('smart-home:event', { detail: event }));
        if (event.type === 'sensor.updated') {
          await applyLiveSensorUpdate(event.data?.sensor);
        }
      } catch (error) {
        console.error('실시간 이벤트 처리 실패', error);
      }
    };
    window.addEventListener('beforeunload', () => eventSource?.close(), { once: true });
  }

  root.querySelectorAll('[data-refresh-sensors], [data-refresh-current-sensor]').forEach((button) => {
    button.addEventListener('click', () => refreshSensors());
  });

  root.querySelectorAll('[data-open-sensor-settings]').forEach((button) => {
    button.addEventListener('click', () => {
      settingsForm.elements.pause_start.value = settings.pauseStart;
      settingsForm.elements.pause_end.value = settings.pauseEnd;
      settingsForm.elements.pause_end.setCustomValidity('');
      settingsForm.elements.interval_minutes.value = String(settings.intervalMinutes);
      settingsForm.elements.enabled.checked = settings.enabled;
      updatePolicyText();
      settingsDialog.showModal();
    });
  });

  root.querySelector('[data-close-sensor-settings]').addEventListener('click', () => settingsDialog.close());

  function updateSettingsPreview() {
    // Clear the previous custom error before the browser performs submit validation.
    settingsForm.elements.pause_end.setCustomValidity('');
    const start = settingsForm.elements.pause_start.value;
    const end = settingsForm.elements.pause_end.value;
    const interval = Number(settingsForm.elements.interval_minutes.value);
    const enabled = settingsForm.elements.enabled.checked;
    const preview = root.querySelector('[data-sensor-settings-preview]');
    preview.textContent = enabled ? `${start}~${end}에는 멈추고, 그 외 시간에는 ${interval}분마다 확인` : '자동 갱신을 사용하지 않고 수동으로만 확인';
  }
  settingsForm.addEventListener('input', updateSettingsPreview);

  settingsForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const start = settingsForm.elements.pause_start.value;
    const end = settingsForm.elements.pause_end.value;
    if (start === end) {
      settingsForm.elements.pause_end.setCustomValidity('시작과 종료 시각은 다르게 설정해 주세요.');
      settingsForm.reportValidity();
      return;
    }
    settingsForm.elements.pause_end.setCustomValidity('');
    settings = {
      enabled: settingsForm.elements.enabled.checked,
      pauseStart: start,
      pauseEnd: end,
      intervalMinutes: Number(settingsForm.elements.interval_minutes.value)
    };
    let persisted = true;
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch (_error) {
      persisted = false;
    }
    updatePolicyText();
    scheduleAutoRefresh();
    settingsDialog.close();
    if (announcer) announcer.textContent = persisted
      ? '센서 화면 자동 갱신 설정 저장 완료'
      : '설정을 현재 탭에 적용했어요. 브라우저 저장소를 사용할 수 없어 새로고침하면 초기화돼요.';
  });

  root.querySelectorAll('[data-open-sensor-manager]').forEach((button) => button.addEventListener('click', openSensorManager));
  root.querySelector('[data-open-zigbee-join]').addEventListener('click', openJoin);
  root.querySelector('[data-close-zigbee-join]').addEventListener('click', () => closeJoin());
  root.querySelector('[data-close-sensor-manager]').addEventListener('click', async () => {
    await closeJoin({ silent: true });
    managerDialog.close();
  });
  managerDialog.addEventListener('cancel', async (event) => {
    event.preventDefault();
    await closeJoin({ silent: true });
    managerDialog.close();
  });
  root.querySelector('[data-discover-sensors]').addEventListener('click', () => refreshSensors());
  root.querySelector('[data-cancel-sensor-edit]').addEventListener('click', () => { editorForm.hidden = true; });

  editorForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!editorForm.reportValidity()) return;
    const deviceId = editorForm.elements.device_id.value;
    const displayName = editorForm.elements.display_name.value.trim();
    const submitButton = editorForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      const updated = await apiCall(`/api/v1/sensors/${encodeURIComponent(deviceId)}/metadata`, {
        method: 'PATCH',
        body: JSON.stringify({
          display_name: displayName,
          room: editorForm.elements.room.value,
          icon: ALLOWED_ICONS.has(editorForm.elements.icon.value) ? editorForm.elements.icon.value : 'activity'
        })
      });
      const index = sensors.findIndex((sensor) => sensor.device_id === deviceId);
      if (index >= 0) sensors[index] = mergeSensorSnapshot(updated, sensors[index]);
      editorForm.hidden = true;
      renderedManagerSignature = '';
      renderManagerList({ force: true });
      renderOverview();
      syncDeviceTiles();
      if (currentSensorId === deviceId) renderSensorDetail();
      if (announcer) announcer.textContent = `${displayName} 센서 설정을 서버에 저장했어요`;
    } catch (error) {
      if (announcer) announcer.textContent = `센서 설정 저장 실패: ${error.message}`;
    } finally {
      submitButton.disabled = false;
    }
  });

  root.querySelector('[data-close-sensor]').addEventListener('click', closeSensorDetail);
  root.querySelector('[data-edit-current-sensor]').addEventListener('click', () => {
    openSensorManager();
    openSensorEditor(currentSensorId);
  });

  root.querySelectorAll('[data-nav]').forEach((button) => {
    button.addEventListener('click', () => {
      root.querySelector('[data-sensor-detail]').hidden = true;
      if (!root.querySelector('[data-aircon-detail]').hidden) return;
      root.classList.remove('show-device-detail');
    });
  });

  const countObserver = new MutationObserver(() => {
    const expected = String(root.querySelectorAll('.device-grid .device-tile:not([data-demo-device])').length);
    if (root.querySelector('[data-device-count]').textContent !== expected || root.querySelector('[data-more-device-count]').textContent !== expected) {
      updateConnectedCounts();
    }
  });
  countObserver.observe(root.querySelector('[data-device-count]'), { childList: true, characterData: true, subtree: true });
  countObserver.observe(root.querySelector('[data-more-device-count]'), { childList: true, characterData: true, subtree: true });

  updatePolicyText();
  scheduleAutoRefresh();
  refreshSensors();
  connectEventStream();
})();
