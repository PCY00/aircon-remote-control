"""Strict user and hub routes; requester-supplied IDs never establish membership."""

from __future__ import annotations

import json
import re
from functools import wraps

from flask import Blueprint, g, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from central_server.households import APIError, Households
from central_server.push import PushStore


def register(app, database, identity_verifier):
    service = Households(database)
    app.extensions['households'] = service
    push = PushStore(database)
    app.extensions['push'] = push
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
            value = request.get_json()
        except (BadRequest, UnsupportedMediaType) as error:
            raise APIError('invalid_body', 400) from error
        if not isinstance(value, dict) or set(value) != set(fields):
            raise APIError('invalid_body', 400)
        return value

    def text(value, *, maximum=128):
        if (not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum
                or any(ord(c)<32 for c in value)):
            raise APIError('invalid_body', 400)
        return value.strip()

    def role(value):
        if value not in ('member','viewer'):
            raise APIError('invalid_role', 400)
        return value

    @app.errorhandler(APIError)
    def error_response(error):
        response = jsonify(error=error.code)
        if error.status == 401:
            response.headers['WWW-Authenticate'] = 'Bearer'
        return response, error.status

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
        token = bearer()
        if not token.startswith('hub_'):
            raise APIError('invalid_hub_credentials', 401)
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
        return jsonify(service.events(home, g.user, event)[0])

    app.register_blueprint(api)
