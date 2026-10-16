// What the "이 휴대폰 알림" card says. Web push reaches iPhone only from a home-screen app (iOS 16.4+),
// so the standalone check comes before anything else. Texts follow FamilyActivity.pushState().

export const INSTALL_STEPS = Object.freeze(['Safari 공유 버튼', '홈 화면에 추가', '홈 화면 아이콘으로 열기']);

export function isStandalone(navigatorStandalone, displayModeStandalone) {
  return navigatorStandalone === true || displayModeStandalone === true;
}
/** iPhone, iPod, and iPad (which reports itself as a Mac with touch). */
export function isIOS(userAgent, platform, maxTouchPoints) {
  return /iPhone|iPad|iPod/.test(userAgent || '') || (platform === 'MacIntel' && maxTouchPoints > 1);
}

/**
 * env: {dev, standalone, supported, ios, permission}; push: {enabled, binding, pending, error}.
 * Returns {mode, title, detail}; only modes 'off', 'denied', 'error', 'preparing', 'ready' show the switch.
 */
export function pushView(env, push) {
  // The home-screen guidance comes first, also in local dev mode, so it can be checked in a browser.
  if (!env.standalone) {
    return {
      mode: 'install', title: '홈 화면에 추가하면 알림을 받아요',
      detail: env.ios ? '' : '브라우저 메뉴에서 홈 화면에 추가한 뒤 그 아이콘으로 열어 주세요.',
    };
  }
  if (env.dev) return { mode: 'dev', title: '알림 받기 꺼짐', detail: '개발 모드에서는 알림을 받지 않아요.' };
  if (!env.supported) {
    return { mode: 'unsupported', title: '이 휴대폰은 웹 알림을 받을 수 없어요', detail: 'iPhone은 iOS 16.4 이상에서 받을 수 있어요.' };
  }
  if (!push.enabled) return { mode: 'off', title: '알림 받기 꺼짐', detail: '켜면 아래에서 고른 중요도대로 받아요.' };
  if (env.permission !== 'granted') {
    return {
      mode: 'denied', title: '휴대폰 알림 허용 필요',
      detail: env.permission === 'denied' ? '설정 앱 → 알림 → 스마트홈에서 알림을 허용해 주세요.' : '스위치를 다시 켜서 알림을 허용해 주세요.',
    };
  }
  if (push.error) return { mode: 'error', title: '알림 연결 확인 필요', detail: push.error };
  if (push.binding && !push.pending) return { mode: 'ready', title: '알림 연결됨', detail: '이 휴대폰에만 적용돼요.' };
  return { mode: 'preparing', title: '알림 연결 준비 중', detail: '휴대폰을 연결하고 고른 중요도를 적용하고 있어요.' };
}
/** The switch is shown (and usable) only where the click can actually ask for permission. */
export function switchVisible(view) { return ['off', 'denied', 'error', 'preparing', 'ready'].includes(view.mode); }

/** Why a test notification cannot be requested yet, as {title, detail}, or null when it can. */
export function testBlocker(view) {
  if (view.mode === 'ready') return null;
  if (view.mode === 'off' || view.mode === 'install' || view.mode === 'unsupported' || view.mode === 'dev')
    return { title: '이 휴대폰 알림을 켜주세요', detail: '설정의 ‘이 휴대폰 알림’에서 ‘이 휴대폰에서 받기’를 켜고 연결을 확인해 주세요.' };
  if (view.mode === 'denied') return { title: '휴대폰에서 알림을 허용해 주세요', detail: '설정 앱 → 알림 → 스마트홈에서 알림을 허용해 주세요.' };
  if (view.mode === 'error') return { title: '알림 연결을 확인해 주세요', detail: view.detail || '알림 연결 상태를 확인한 뒤 다시 시도해 주세요.' };
  return { title: '알림 연결 준비 중이에요', detail: '잠시 후 ‘알림 연결 확인’을 눌러 주세요. ‘알림 연결됨’이 되면 시험 알림을 보낼 수 있어요.' };
}
