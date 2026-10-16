// Web-only rules: the local dev-token guard, installation ids, push card states, error texts, homes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { devTokenFrom, isDevHost, storedDevToken, withoutDevToken } from '../central_server/webapp/js/logic/dev.js';
import { INSTALLATION_ID, SECRET, hex, newInstallation, requestId, uuid4, validInstallation } from '../central_server/webapp/js/logic/ids.js';
import { INSTALL_STEPS, isIOS, isStandalone, pushView, switchVisible, testBlocker } from '../central_server/webapp/js/logic/pushstate.js';
import { ApiError, NETWORK, describe, homeGone, routeMissing, signInMessage } from '../central_server/webapp/js/logic/errors.js';
import { chooseHome, favoritesKey, homeList, lastHomeKey, roleLabel, toggled } from '../central_server/webapp/js/logic/homes.js';

// Built at runtime: the reader-bundle audit rejects token-like literals in the repository.
const part = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
const JWT = [part({ alg: 'RS256' }), part({ sub: 'dev' }), Buffer.from('signature').toString('base64url')].join('.');

test('the dev token is read only on 127.0.0.1 and localhost', () => {
  assert.equal(devTokenFrom('127.0.0.1', '#dev-token=' + JWT), JWT);
  assert.equal(devTokenFrom('localhost', '#home&dev-token=' + JWT), JWT);
  assert.equal(devTokenFrom('localhost', '#dev-token=' + JWT + '&alerts'), JWT);
  for (const host of ['roomrelay.top', 'www.roomrelay.top', 'localhost.', 'localhost.roomrelay.top', '127.0.0.1.nip.io',
    '[::1]', '::1', '0.0.0.0', '127.0.0.2', 'LOCALHOST', '', null, undefined]) {
    assert.equal(devTokenFrom(host, '#dev-token=' + JWT), null, String(host));
    assert.equal(storedDevToken(host, JWT), null, String(host));
    assert.equal(isDevHost(host), false, String(host));
  }
  assert.equal(devTokenFrom('localhost', '#home'), null);
  assert.equal(devTokenFrom('localhost', '#dev-token='), null);
  assert.equal(devTokenFrom('localhost', '#dev-token=<script>'), null);
  assert.equal(devTokenFrom('localhost', '#xdev-token=' + JWT), null);
  assert.equal(storedDevToken('127.0.0.1', JWT), JWT);
  assert.equal(storedDevToken('127.0.0.1', null), null);
  assert.equal(withoutDevToken('#dev-token=' + JWT), '');
  assert.equal(withoutDevToken('#alerts&dev-token=' + JWT), '#alerts');
  assert.equal(withoutDevToken('#device/abc'), '#device/abc');
});

test('installation ids are uuid4 and secrets 64 hex characters', () => {
  assert.equal(hex([0, 15, 255]), '000fff');
  const zero = uuid4(new Uint8Array(16));
  assert.equal(zero, '00000000-0000-4000-8000-000000000000');
  assert.equal(uuid4(new Uint8Array(16).fill(255)), 'ffffffff-ffff-4fff-bfff-ffffffffffff');
  assert.throws(() => uuid4(new Uint8Array(15)));
  let counter = 0;
  const fill = (bytes) => { for (let i = 0; i < bytes.length; i++) bytes[i] = (counter++ * 37) & 255; return bytes; };
  const made = newInstallation(fill);
  assert.match(made.installation, INSTALLATION_ID); assert.match(made.secret, SECRET);
  assert.equal(validInstallation(made), true);
  assert.equal(validInstallation({ installation: made.installation, secret: 'short' }), false);
  assert.equal(validInstallation(null), false);
  assert.match(requestId(fill), INSTALLATION_ID, 'Command request ids pass the server installation-id format');
  const real = newInstallation((bytes) => globalThis.crypto.getRandomValues(bytes));
  assert.match(real.installation, INSTALLATION_ID); assert.match(real.secret, SECRET);
});

test('standalone and iOS detection', () => {
  assert.equal(isStandalone(true, false), true); assert.equal(isStandalone(undefined, true), true); assert.equal(isStandalone(undefined, false), false);
  assert.equal(isIOS('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', 'iPhone', 5), true);
  assert.equal(isIOS('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'MacIntel', 5), true, 'iPadOS desktop mode');
  assert.equal(isIOS('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'MacIntel', 0), false);
  assert.equal(isIOS('Mozilla/5.0 (Linux; Android 14)', 'Linux armv8l', 5), false);
  assert.deepEqual([...INSTALL_STEPS], ['Safari 공유 버튼', '홈 화면에 추가', '홈 화면 아이콘으로 열기']);
});

test('the push card asks for the home screen first, then follows the Android states', () => {
  const env = { dev: false, standalone: true, supported: true, ios: true, permission: 'granted' };
  const push = { enabled: true, binding: 'b', pending: false, error: null };
  assert.equal(pushView({ ...env, dev: true }, push).detail, '개발 모드에서는 알림을 받지 않아요.');
  assert.equal(pushView({ ...env, dev: true, standalone: false }, push).mode, 'install', 'dev mode still shows the home-screen steps');
  const install = pushView({ ...env, standalone: false }, push);
  assert.equal(install.mode, 'install'); assert.equal(switchVisible(install), false);
  assert.equal(pushView({ ...env, supported: false }, push).mode, 'unsupported');
  const off = pushView(env, { ...push, enabled: false });
  assert.equal(off.title, '알림 받기 꺼짐'); assert.equal(off.detail, '켜면 아래에서 고른 중요도대로 받아요.'); assert.equal(switchVisible(off), true);
  assert.equal(pushView({ ...env, permission: 'denied' }, push).title, '휴대폰 알림 허용 필요');
  assert.equal(pushView(env, { ...push, error: '인터넷 연결을 확인해 주세요.' }).detail, '인터넷 연결을 확인해 주세요.');
  const ready = pushView(env, push);
  assert.equal(ready.title, '알림 연결됨'); assert.equal(testBlocker(ready), null);
  const preparing = pushView(env, { ...push, pending: true });
  assert.equal(preparing.title, '알림 연결 준비 중');
  assert.equal(testBlocker(preparing).title, '알림 연결 준비 중이에요');
  assert.equal(testBlocker(off).title, '이 휴대폰 알림을 켜주세요');
  assert.equal(testBlocker(install).title, '이 휴대폰 알림을 켜주세요');
});

test('api errors reuse the Android wording', () => {
  assert.equal(describe(new Error('x')), NETWORK);
  assert.equal(describe(new ApiError(0, '')), NETWORK);
  assert.equal(describe(new ApiError(503, 'control_offline')), 'Pi가 연결되지 않았어요. Pi와 서버 연결을 확인해 주세요.');
  assert.equal(describe(new ApiError(403, 'control_forbidden')), '집 소유자와 가족만 에어컨을 조작할 수 있어요.');
  assert.equal(describe(new ApiError(409, 'control_busy')), '앞선 명령의 결과를 기다리고 있어요. 잠시 후 확인해 주세요.');
  assert.equal(describe(new ApiError(429, 'control_rate_limit')), '명령을 너무 빠르게 보냈어요. 잠시 후 다시 눌러 주세요.');
  assert.equal(describe(new ApiError(409, 'already_member')), '이미 이 집에 참여하고 있어요. 집 목록에서 해당 집을 열어 주세요.');
  assert.equal(describe(new ApiError(409, 'zzz')), '현재 등록 상태에서는 요청을 완료할 수 없어요. 화면을 새로고침한 뒤 다시 확인해 주세요.');
  assert.equal(describe(new ApiError(429, 'test_rate_limited')), '요청이 너무 잦아요. 시험 알림은 1분에 한 번 보낼 수 있어요. 잠시 후 다시 시도해 주세요.');
  assert.equal(describe(new ApiError(401, 'invalid_credentials')), '로그인을 확인할 수 없어요. 다시 로그인해 주세요.');
  assert.equal(describe(new ApiError(403, 'owner_required')), '집 소유자만 사용할 수 있는 기능이에요.');
  assert.equal(describe(new ApiError(404, 'invalid_invitation')), '초대가 만료됐거나 이 계정으로 사용할 수 없어요. 새 초대를 받아 주세요.');
  assert.equal(describe(new ApiError(404, 'not_found')), '요청한 항목이 없거나 접근할 수 없어요. 집 목록에서 다시 확인해 주세요.');
  assert.equal(describe(new ApiError(400, 'invalid_body')), '입력 내용을 확인해 주세요.');
  assert.equal(describe(new ApiError(503, 'notifications_not_configured')), '서버의 알림 전송 설정이 아직 준비되지 않았어요. 집 소유자에게 확인해 주세요.');
  assert.equal(describe(new ApiError(502, '')), '서버에서 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.');
  assert.equal(homeGone(new ApiError(404, 'not_found')), true); assert.equal(homeGone(new ApiError(404, '')), false);
  assert.equal(routeMissing(new ApiError(404, '')), true); assert.equal(routeMissing(new ApiError(404, 'not_found')), false);
  assert.equal(signInMessage('auth/network-request-failed'), '네트워크 연결을 확인한 뒤 다시 로그인해 주세요.');
  assert.equal(signInMessage('auth/whatever'), '로그인을 마치지 못했어요. 잠시 후 다시 시도해 주세요.');
});

test('homes: roles, last-used choice and favorites', () => {
  assert.equal(roleLabel('owner'), '소유자'); assert.equal(roleLabel('member'), '가족'); assert.equal(roleLabel('viewer'), '조회 전용');
  const homes = homeList({ homes: [{ id: 'a', name: '우리 집', role: 'owner' }, { id: 'b', name: '부모님 집', role: 'viewer' }, { id: '', name: 'x' }, null] });
  assert.equal(homes.length, 2);
  assert.equal(chooseHome(homes, 'b'), 'b'); assert.equal(chooseHome(homes, 'gone'), 'a'); assert.equal(chooseHome([], 'a'), null);
  assert.equal(homeList(null).length, 0);
  assert.notEqual(lastHomeKey('u1'), lastHomeKey('u2')); assert.notEqual(favoritesKey('a'), favoritesKey('b'));
  assert.deepEqual(toggled(['x'], 'y'), { ids: ['x', 'y'], added: true });
  assert.deepEqual(toggled(['x', 'y'], 'x'), { ids: ['y'], added: false });
});
