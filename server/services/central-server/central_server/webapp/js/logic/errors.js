// Actionable messages without server bodies or technical error codes. Wording of
// ApiErrorMessages.java; only the two texts that point at the Android "server address" setting say
// "인터넷 연결"/"잠시 후" instead, because the web app is always served by its own server.

export class ApiError extends Error {
  /** status 0 means the request never got an HTTP answer (offline, blocked). */
  constructor(status, code) {
    super(code ? `api ${status} ${code}` : `api ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = code || '';
  }
}

export const NETWORK = '서버에 연결할 수 없어요. 인터넷 연결을 확인해 주세요.';

export function describe(failure) {
  if (!(failure instanceof ApiError) || failure.status === 0) return NETWORK;
  const { status, code } = failure;
  switch (code) {
    case 'control_offline': return 'Pi가 연결되지 않았어요. Pi와 서버 연결을 확인해 주세요.';
    case 'control_forbidden': return '집 소유자와 가족만 에어컨을 조작할 수 있어요.';
    case 'control_device_unavailable': return '이 에어컨의 Pi 연결을 확인해 주세요.';
    case 'control_busy': return '앞선 명령의 결과를 기다리고 있어요. 잠시 후 확인해 주세요.';
    case 'control_rate_limit': return '명령을 너무 빠르게 보냈어요. 잠시 후 다시 눌러 주세요.';
    case 'control_request_conflict': return '요청 정보를 확인하지 못했어요. 화면을 새로고침해 주세요.';
    default: break;
  }
  if (status === 409) {
    switch (code) {
      case 'installation_not_registered': return '이 휴대폰의 알림 등록이 완료되지 않았어요. 알림 설정에서 알림을 켜고 연결을 확인해 주세요.';
      case 'installation_conflict': return '이 휴대폰의 알림 등록 정보가 다른 등록과 충돌했어요. 집 소유자에게 확인을 요청해 주세요.';
      case 'installation_limit': return '이 계정에 등록된 알림 수신 기기가 10대예요. 사용하지 않는 기기에서 알림을 끈 뒤 다시 시도해 주세요.';
      case 'already_member': return '이미 이 집에 참여하고 있어요. 집 목록에서 해당 집을 열어 주세요.';
      case 'home_hub_exists': return '이 집에는 이미 기기가 등록돼 있어요. 등록된 기기를 확인해 주세요.';
      case 'owner_protected': return '집 소유자의 참여나 권한은 여기서 변경할 수 없어요.';
      case 'identity_conflict': return '계정 정보가 기존 등록과 일치하지 않아요. 집 소유자에게 확인을 요청해 주세요.';
      default: return '현재 등록 상태에서는 요청을 완료할 수 없어요. 화면을 새로고침한 뒤 다시 확인해 주세요.';
    }
  }
  if (status === 429) return '요청이 너무 잦아요. 시험 알림은 1분에 한 번 보낼 수 있어요. 잠시 후 다시 시도해 주세요.';
  if (status === 401) return '로그인을 확인할 수 없어요. 다시 로그인해 주세요.';
  if (status === 403) {
    if (code === 'owner_required') return '집 소유자만 사용할 수 있는 기능이에요.';
    if (code === 'account_disabled') return '이 계정은 현재 사용이 중지돼 있어요. 집 소유자에게 확인해 주세요.';
    return '이 기능을 사용할 권한이 없어요. 집 소유자에게 확인해 주세요.';
  }
  if (status === 404) {
    if (code === 'invalid_invitation') return '초대가 만료됐거나 이 계정으로 사용할 수 없어요. 새 초대를 받아 주세요.';
    if (code === 'invalid_claim') return '기기 등록 코드가 만료됐거나 이미 사용됐어요. 새 코드를 확인해 주세요.';
    return '요청한 항목이 없거나 접근할 수 없어요. 집 목록에서 다시 확인해 주세요.';
  }
  if (status === 400) {
    if (code === 'confirmation_required') return '집 이름을 정확히 입력해야 삭제할 수 있어요.';
    if (code === 'invalid_notification_preferences') return '알림 종류와 온습도 수신 간격을 다시 선택해 주세요.';
    if (code === 'invalid_email') return 'Google 계정 이메일 주소를 확인해 주세요.';
    if (code === 'invalid_quiet_hours') return '방해 금지 시간을 다시 선택해 주세요.';
    return '입력 내용을 확인해 주세요.';
  }
  if (status === 503) {
    if (code === 'notifications_not_configured') return '서버의 알림 전송 설정이 아직 준비되지 않았어요. 집 소유자에게 확인해 주세요.';
    if (code === 'authentication_not_configured') return '서버의 로그인 설정이 아직 준비되지 않았어요. 집 소유자에게 확인해 주세요.';
    return '서버가 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.';
  }
  if (status >= 500) return '서버에서 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.';
  return '서버 응답을 확인할 수 없어요. 잠시 후 다시 시도해 주세요.';
}

/** The household no longer lists this account (left, revoked or deleted): 404 not_found. */
export function homeGone(failure) {
  return failure instanceof ApiError && failure.status === 404 && failure.code === 'not_found';
}
/** A 404 without a JSON error code: the route itself is missing (older server). */
export function routeMissing(failure) {
  return failure instanceof ApiError && failure.status === 404 && failure.code === '';
}

/** Firebase Auth error code → Korean text for the login screen. */
export function signInMessage(code) {
  switch (code) {
    case 'auth/network-request-failed': return '네트워크 연결을 확인한 뒤 다시 로그인해 주세요.';
    case 'auth/unauthorized-domain': case 'auth/operation-not-allowed': case 'auth/invalid-api-key':
    case 'auth/auth-domain-config-required':
      return '서버의 로그인 설정이 아직 준비되지 않았어요. 집 소유자에게 확인해 주세요.';
    case 'auth/user-disabled': return '이 계정은 현재 사용이 중지돼 있어요. 집 소유자에게 확인해 주세요.';
    case 'auth/web-storage-unsupported':
      return '이 브라우저에서는 로그인 정보를 저장할 수 없어요. 개인정보 보호 브라우징을 끄고 다시 열어 주세요.';
    case 'auth/redirect-cancelled-by-user': case 'auth/user-cancelled': return '로그인을 취소했어요.';
    default: return '로그인을 마치지 못했어요. 잠시 후 다시 시도해 주세요.';
  }
}
