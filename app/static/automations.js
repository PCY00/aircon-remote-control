(() => {
  const root = document.getElementById('room-first-design-studio');
  if (!root) return;

  const DISPLAY_TIME_ZONE = 'Asia/Seoul';
  const list = root.querySelector('[data-automation-list]');
  const empty = root.querySelector('[data-automation-empty]');
  const count = root.querySelector('[data-automation-count]');
  const eventList = root.querySelector('[data-automation-event-list]');
  const eventEmpty = root.querySelector('[data-automation-event-empty]');
  const alertBox = root.querySelector('[data-automation-alert]');
  const announcer = root.querySelector('[data-announcer]');
  let rules = [];
  let events = [];
  let loading = false;

  async function apiCall(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {})
      }
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.detail || '자동화 API 요청을 처리하지 못했어요.');
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
    window.lucide?.createIcons({ attrs: { 'aria-hidden': 'true', 'stroke-width': 2 } });
  }

  function formatDateTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '시간 확인 불가';
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: DISPLAY_TIME_ZONE,
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(date);
  }

  function delayLabel(seconds) {
    if (seconds < 60) return `${seconds}초`;
    return `${Math.round(seconds / 60)}분`;
  }

  function ruleStatus(rule) {
    if (!rule.enabled) return '꺼짐 · 감시하지 않음';
    if (rule.state?.warning_active) return '경고 발생 중';
    if (rule.condition?.active) return `조건 감지 · ${delayLabel(rule.delay_seconds)} 확인 중`;
    return '정상 · 문과 에어컨 상태 감시 중';
  }

  function renderAlert() {
    const active = rules.find((rule) => rule.state?.warning_active);
    alertBox.hidden = !active;
    if (!active) return;
    root.querySelector('[data-automation-alert-title]').textContent = active.name;
    root.querySelector('[data-automation-alert-message]').textContent = '문이 열린 채 에어컨이 켜져 있어요.';
  }

  async function updateRule(ruleId, changes, control) {
    if (control) control.disabled = true;
    try {
      const updated = await apiCall(`/api/v1/automations/${encodeURIComponent(ruleId)}`, {
        method: 'PATCH',
        body: JSON.stringify(changes)
      });
      const index = rules.findIndex((rule) => rule.id === ruleId);
      if (index >= 0) rules[index] = updated;
      renderRules();
      if (announcer) announcer.textContent = `${updated.name} 설정을 저장했어요`;
    } catch (error) {
      if (announcer) announcer.textContent = `자동화 설정 저장 실패: ${error.message}`;
      await refresh();
    } finally {
      if (control?.isConnected) control.disabled = false;
    }
  }

  function renderRules() {
    list.replaceChildren();
    rules.forEach((rule) => {
      const item = document.createElement('article');
      item.className = 'automation-item live-automation-item';
      item.dataset.warning = String(Boolean(rule.state?.warning_active));

      const main = document.createElement('div');
      main.className = 'live-automation-main';
      const icon = document.createElement('span');
      icon.className = 'live-automation-icon';
      icon.append(createIcon(rule.state?.warning_active ? 'triangle-alert' : 'shield-check'));
      const copy = document.createElement('div');
      copy.className = 'automation-copy';
      const title = document.createElement('strong');
      title.textContent = rule.name;
      const detail = document.createElement('small');
      detail.textContent = ruleStatus(rule);
      copy.append(title, detail);
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'automation-toggle';
      toggle.setAttribute('aria-pressed', String(Boolean(rule.enabled)));
      toggle.textContent = rule.enabled ? '켜짐' : '꺼짐';
      toggle.addEventListener('click', () => updateRule(rule.id, { enabled: !rule.enabled }, toggle));
      main.append(icon, copy, toggle);

      const controls = document.createElement('div');
      controls.className = 'automation-rule-controls';
      const label = document.createElement('label');
      label.textContent = '경고까지 기다릴 시간';
      const select = document.createElement('select');
      select.setAttribute('aria-label', `${rule.name} 대기 시간`);
      [60, 180, 300, 600, 900, 1800].forEach((seconds) => {
        const option = document.createElement('option');
        option.value = String(seconds);
        option.textContent = delayLabel(seconds);
        option.selected = seconds === Number(rule.delay_seconds);
        select.append(option);
      });
      select.disabled = !rule.enabled;
      select.addEventListener('change', () => updateRule(rule.id, { delay_seconds: Number(select.value) }, select));
      controls.append(label, select);
      item.append(main, controls);
      list.append(item);
    });
    const activeCount = rules.filter((rule) => rule.enabled).length;
    count.textContent = `${activeCount}개 활성 · ${rules.length}개`;
    empty.hidden = rules.length !== 0;
    renderAlert();
    refreshIcons();
  }

  function renderEvents() {
    eventList.replaceChildren();
    events.forEach((event) => {
      const row = document.createElement('div');
      row.className = 'automation-event';
      const resolved = event.event_type === 'warning_resolved';
      row.append(createIcon(resolved ? 'circle-check' : 'triangle-alert'));
      const copy = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = resolved ? '경고 해제' : '경고 발생';
      const detail = document.createElement('small');
      detail.textContent = event.message;
      copy.append(title, detail);
      const time = document.createElement('time');
      time.dateTime = event.occurred_at;
      time.textContent = formatDateTime(event.occurred_at);
      row.append(copy, time);
      eventList.append(row);
    });
    eventEmpty.hidden = events.length !== 0;
    refreshIcons();
  }

  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      const [rulePayload, eventPayload] = await Promise.all([
        apiCall('/api/v1/automations'),
        apiCall('/api/v1/automations/events?limit=20')
      ]);
      rules = Array.isArray(rulePayload.items) ? rulePayload.items : [];
      events = Array.isArray(eventPayload.items) ? eventPayload.items : [];
      renderRules();
      renderEvents();
    } catch (error) {
      count.textContent = '연결 확인 필요';
      list.replaceChildren();
      const message = document.createElement('p');
      message.className = 'automation-empty';
      message.textContent = `자동화 상태를 불러오지 못했어요: ${error.message}`;
      list.append(message);
    } finally {
      loading = false;
    }
  }

  window.addEventListener('smart-home:event', (event) => {
    const type = event.detail?.type || '';
    if (type === 'stream.ready' || type.startsWith('automation.')) refresh();
  });

  refresh();
})();
