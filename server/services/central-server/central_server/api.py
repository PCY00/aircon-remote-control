"""Strict user and hub routes; requester-supplied IDs never establish membership."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import wraps

from flask import Blueprint, g, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, UnsupportedMediaType

from central_server.households import APIError, Households
from central_server.identity import ServerIdentity
from central_server.limits import Limiter
from central_server.push import PushStore
from central_server.control import ALLOWED_ACTIONS, Controls
from central_server.inventory import BODY_BYTES, Inventory, validate
from central_server.preferences import CATEGORIES, CHOICES, INTERVALS


def register(app, database, identity_verifier):
    service = Households(database)
    app.extensions['households'] = service
    push = PushStore(database)
    app.extensions['push'] = push
    control = Controls(database)
    app.extensions['control'] = control
    inventory = Inventory(database)
    app.extensions['inventory'] = inventory
    identity = ServerIdentity(database)
    # Process-local: the A50 runs one worker process. Keys are authenticated hub ids. The Pi sends
    # its device list on change at most every 15 s (5760/day), so the daily cap stays above that.
    limits = app.extensions['limits'] = {'hub_events': Limiter((120, 60), (20000, 86400)),
                                         'hub_inventory': Limiter((12, 60), (6000, 86400)),
                                         'identity': Limiter((60, 60))}  # per client, no global cap
    api = Blueprint('households', __name__, url_prefix='/v1')

    def bearer():
        value = request.headers.get('Authorization','')
        pieces = value.split(' ')
        if (len(pieces) != 2 or pieces[0].casefold() != 'bearer'
                or not 1 <= len(pieces[1]) <= 8192):
            raise APIError('invalid_credentials', 401)
        return pieces[1]

    def user_route(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            token = bearer()
            if identity_verifier is None:
                raise APIError('authentication_not_configured', 503)
            identity = identity_verifier.verify(token)
            g.user = service.user(identity)
            return function(*args, **kwargs)
        return wrapped

    def body(fields):
        try:
            value = request.get_json()  # deep nesting raises RecursionError, not a JSON error
        except (BadRequest, UnsupportedMediaType, ValueError, RecursionError) as error:
            raise APIError('invalid_body', 400) from error
        if not isinstance(value, dict) or set(value) != set(fields):
            raise APIError('invalid_body', 400)
        return value

    def text(value, *, maximum=128):
        # Control (Cc) and format (Cf: bidi overrides, zero-width) characters never reach screens;
        # a lone surrogate (Cs) cannot be stored as UTF-8 and would otherwise surface as a 500.
        if (not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum
                or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in value)):
            raise APIError('invalid_body', 400)
        return value.strip()

    def hub_auth():
        # Credential first: an unauthenticated body never reaches the JSON parser.
        token = bearer()
        if not token.startswith('hub_'):
            raise APIError('invalid_hub_credentials', 401)
        with control.transaction() as conn:
            hub = control.hub(conn, token)
        return token, hub['id']

    def role(value):
        if value not in ('member','viewer'):
            raise APIError('invalid_role', 400)
        return value

    @app.errorhandler(APIError)
    def error_response(error):
        response = jsonify(error=error.code)
        if error.status == 401:
            response.headers['WWW-Authenticate'] = 'Bearer'
        if error.retry_after:
            response.headers['Retry-After'] = str(error.retry_after)
        return response, error.status

    @api.get('/server-identity')
    def server_identity():
        # Unauthenticated by design: the app pins this key before it trusts any server reply.
        nonce = request.args.get('nonce', '')
        host = request.headers.get('Host', '').strip().lower()
        if (not re.fullmatch(r'[0-9a-f]{32}', nonce) or not host or len(host) > 255
                or any(c.isspace() for c in host)):
            raise APIError('invalid_body', 400)
        # Per client (Cloudflare's visitor address behind the tunnel, else the peer): a stranger
        # holding the URL must not lock every phone out of its trust check. Signing is ~0.1 ms.
        client = (request.headers.get('CF-Connecting-IP') or request.remote_addr or '')[:64]
        wait = limits['identity'].take(client)
        if wait:
            raise APIError('rate_limited', 429, retry_after=wait)
        return jsonify(identity.describe(nonce, host))

    @api.get('/me')
    @user_route
    def me():
        return jsonify(user_id=g.user, homes=service.homes(g.user))

    def installation_id(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
            raise APIError('invalid_body', 400)
        return value

    def installation_secret(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
            raise APIError('invalid_body', 400)
        return value

    @api.put('/installations/<installation>')
    @user_route
    def register_installation(installation):
        value = body(['secret', 'token'])
        token = value['token']
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_:.-]{32,4096}', token):
            raise APIError('invalid_body', 400)
        return jsonify(push.register(g.user, installation_id(installation),
                                     installation_secret(value['secret']), token))

    @api.post('/installations/<installation>/unregister')
    @user_route
    def unregister_installation(installation):
        value = body(['secret', 'binding'])
        return jsonify(push.unregister(g.user, installation_id(installation), installation_secret(value['secret']),
                                       installation_id(value['binding'])))

    @api.post('/homes/<home>/notifications/test')
    @user_route
    def notification_test(home):
        value = body(['installation_id'])
        if service.home(home, g.user)['role'] != 'owner':
            raise APIError('owner_required', 403)
        if not app.config['PUSH_SENDER_READY']:
            raise APIError('notifications_not_configured', 503)
        return jsonify(push.test(home, g.user, installation_id(value['installation_id']))), 202

    @api.put('/installations/<installation>/preferences')
    @user_route
    def notification_preferences(installation):
        value = body(['secret', 'door', 'climate', 'warning', 'climate_interval_minutes'])
        if (any(type(value[key]) is not bool for key in ('door','climate','warning'))
                or type(value['climate_interval_minutes']) is not int
                or value['climate_interval_minutes'] not in (1,5,15,60)):
            raise APIError('invalid_notification_preferences', 400)
        options = {key:value[key] for key in ('door','climate','warning','climate_interval_minutes')}
        return jsonify(push.set_preferences(g.user, installation_id(installation),
                       installation_secret(value['secret']), options))

    @api.put('/installations/<installation>/notification-levels')
    @user_route
    def notification_levels(installation):
        value = body(['secret', 'levels', 'report_interval_minutes'])
        levels, interval = value['levels'], value['report_interval_minutes']
        # Every configurable category, every time: a missing one is a client bug, not a default.
        if (not isinstance(levels, dict) or set(levels) != set(CATEGORIES)
                or any(not isinstance(levels[name], str) or levels[name] not in CHOICES[name]
                       for name in CATEGORIES)
                or type(interval) is not int or interval not in INTERVALS):
            raise APIError('invalid_notification_preferences', 400)
        return jsonify(push.set_levels(g.user, installation_id(installation),
                       installation_secret(value['secret']), levels, interval))

    @api.get('/homes')
    @user_route
    def homes():
        return jsonify(homes=service.homes(g.user))

    @api.post('/homes')
    @user_route
    def create_home():
        value = body(['name'])
        return jsonify(service.create_home(g.user, text(value['name'], maximum=80))), 201

    @api.get('/homes/<home>')
    @user_route
    def home_detail(home):
        return jsonify(service.home(home, g.user))

    @api.delete('/homes/<home>')
    @user_route
    def delete_home(home):
        value = body(['confirmation_name'])
        return jsonify(service.delete_home(home, g.user, text(value['confirmation_name'], maximum=80)))

    @api.get('/homes/<home>/members')
    @user_route
    def members(home):
        return jsonify(members=service.members(home, g.user))

    @api.post('/homes/<home>/invitations')
    @user_route
    def invite(home):
        value = body(['email','role'])
        email = text(value['email'], maximum=254).casefold()
        if not re.fullmatch(r'[^\s@]{1,128}@[^\s@]{1,128}', email):
            raise APIError('invalid_email', 400)
        return jsonify(service.invitation(home, g.user, email, role(value['role']))), 201

    @api.post('/invitations/accept')
    @user_route
    def accept():
        value = body(['invitation_token'])
        return jsonify(service.accept(g.user, text(value['invitation_token'])))

    @api.patch('/homes/<home>/members/<target>')
    @user_route
    def change_member(home, target):
        value = body(['role'])
        return jsonify(service.change_member(home, g.user, target, role=role(value['role'])))

    @api.post('/homes/<home>/members/<target>/revoke')
    @user_route
    def revoke_member(home, target):
        body([])
        return jsonify(service.change_member(home, g.user, target))

    @api.get('/homes/<home>/hubs')
    @user_route
    def hubs(home):
        return jsonify(hubs=service.hubs(home, g.user))

    @api.post('/homes/<home>/hubs/claim')
    @user_route
    def claim(home):
        value = body(['claim_code'])
        return jsonify(service.claim(home, g.user, text(value['claim_code'])))

    @api.post('/homes/<home>/hubs/<hub>/revoke')
    @user_route
    def revoke_hub(home, hub):
        body([])
        return jsonify(service.revoke_hub(home, g.user, hub))

    @api.post('/hub/events')
    def ingest():
        token, hub = hub_auth()
        wait = limits['hub_events'].take(hub)
        if wait:
            raise APIError('rate_limited', 429, retry_after=wait)
        value = body(['event_id','kind','payload'])
        event_id = text(value['event_id'], maximum=64)
        kind = text(value['kind'], maximum=64)
        try:
            encoded = json.dumps(value['payload'], ensure_ascii=False, allow_nan=False).encode()
        except (ValueError, TypeError, RecursionError) as error:
            raise APIError('invalid_body', 400) from error
        if (not re.fullmatch(r'[A-Za-z0-9_-]+', event_id)
                or not re.fullmatch(r'[a-z][a-z0-9_.-]+', kind)
                or not isinstance(value['payload'], dict)
                or len(encoded) > 2048):
            raise APIError('invalid_body', 400)
        return jsonify(service.ingest(token, event_id, kind, value['payload']))

    @api.get('/homes/<home>/events')
    @user_route
    def events(home):
        return jsonify(events=service.events(home, g.user))

    @api.get('/homes/<home>/events/<int:event>')
    @user_route
    def event_detail(home, event):
        if event > 2**63-1:  # SQLite INTEGER range; larger ids cannot exist.
            raise APIError('not_found', 404)
        return jsonify(service.events(home, g.user, event)[0])

    @api.get('/homes/<home>/control')
    @user_route
    def control_status(home):
        return jsonify(control.status(home, g.user))

    @api.get('/homes/<home>/devices')
    @user_route
    def home_devices(home):
        return jsonify(inventory.devices(home, g.user))

    @api.post('/homes/<home>/control/commands')
    @user_route
    def control_command(home):
        value = body(['request_id', 'device_id', 'action'])
        if not isinstance(value['action'], str) or value['action'] not in ALLOWED_ACTIONS:
            raise APIError('invalid_body', 400)
        device = value['device_id']
        if not isinstance(device, str) or not re.fullmatch(r'[a-f0-9]{32}', device):
            raise APIError('invalid_body', 400)
        return jsonify(control.enqueue(home, g.user, installation_id(value['request_id']), device, value['action'])), 202

    @api.get('/homes/<home>/control/commands/<command>')
    @user_route
    def control_result(home, command):
        return jsonify(control.command(home, g.user, command))

    @api.put('/hub/control/status')
    def hub_control_status():
        token, _ = hub_auth()
        value = body(['devices'])
        devices = value['devices']
        if not isinstance(devices, list) or len(devices) > 20:
            raise APIError('invalid_body', 400)
        seen = set()
        for device in devices:
            if (not isinstance(device, dict) or set(device) != {'id', 'name'}
                    or not isinstance(device['id'], str) or not re.fullmatch(r'[a-f0-9]{32}', device['id'])
                    or device['id'] in seen or not isinstance(device['name'], str)):
                raise APIError('invalid_body', 400)
            # Hub names reach family screens: strip Cc/Cf/Cs here so one odd name cannot drop the heartbeat.
            device['name'] = text(''.join(c for c in device['name']
                                          if unicodedata.category(c) not in ('Cc', 'Cf', 'Cs')), maximum=80)
            seen.add(device['id'])
        return jsonify(control.heartbeat(token, devices))

    @api.put('/hub/inventory')
    def hub_inventory():
        token, hub = hub_auth()
        wait = limits['hub_inventory'].take(hub)
        if wait:
            raise APIError('rate_limited', 429, retry_after=wait)
        # 50 named devices with state need more than the app-wide 16 KiB; Werkzeug enforces this
        # route's own cap while reading, so an oversized body is never parsed.
        request.max_content_length = BODY_BYTES
        try:
            value = body(['devices'])
        except RequestEntityTooLarge as error:
            raise APIError('body_too_large', 413) from error
        return jsonify(inventory.replace(token, validate(value['devices'], inventory.clock())))

    @api.post('/hub/control/next')
    def hub_control_next():
        token, _ = hub_auth()
        body([])
        return jsonify(control.next(token))

    @api.post('/hub/control/<command>/result')
    def hub_control_result(command):
        token, _ = hub_auth()
        value = body(['attempt_token', 'state'])
        if value['state'] not in ('sent', 'failed', 'unknown', 'expired'):
            raise APIError('invalid_body', 400)
        return jsonify(control.result(token, command, installation_secret(value['attempt_token']), value['state']))

    app.register_blueprint(api)
