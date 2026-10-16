"""iPhone home-screen web app under /app/ and Firebase's sign-in helper on this same domain.

Safari partitions storage between sites, so the web app signs in with authDomain set to this
server and the helper pages under /__/auth/ are fetched from the project's firebaseapp.com host
(decision record 0020). Only files inside central_server/webapp/ are ever served.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import logging
import re
import time
from pathlib import Path

import requests
from flask import Response, g, jsonify, redirect, request

from central_server import VERSION
from central_server.households import APIError
from central_server.limits import Limiter

FOLDER = Path(__file__).resolve().parent / 'webapp'
TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.webmanifest': 'application/manifest+json',
    '.json': 'application/json',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.txt': 'text/plain; charset=utf-8',
}
# Every segment starts with a letter, digit, '_' or '-': no dotfiles, '.', '..', empty segments,
# backslashes, drive letters or absolute paths.
FILE_NAME = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}){0,7}')
# Firebase's sign-in redirect loads Google's gapi loader (apis.google.com/js/api.js) into the
# page to talk to the /__/auth/iframe helper; every other script is served from /app/ itself.
APP_CSP = (
    "default-src 'self'; script-src 'self' https://apis.google.com; style-src 'self'; "
    "img-src 'self' data: https://lh3.googleusercontent.com; "
    "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
    "https://firebaseinstallations.googleapis.com https://fcmregistrations.googleapis.com "
    "https://www.googleapis.com; "
    "frame-src 'self'; worker-src 'self'; manifest-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'; object-src 'none'"
)

# Public Firebase web settings kept in the private config file (never in the repository).
WEB_FIELDS = {
    'api_key': re.compile(r'[A-Za-z0-9_-]{10,128}'),
    'app_id': re.compile(r'[A-Za-z0-9:._-]{1,128}'),
    'messaging_sender_id': re.compile(r'[0-9]{1,32}'),
    # A bare lowercase host name: no scheme, port, path or trailing dot.
    'auth_domain': re.compile(
        r'(?=[a-z0-9.-]{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?'),
}
PROJECT = re.compile(r'[a-z][a-z0-9-]{4,28}[a-z0-9]')  # Firebase/Google Cloud project id rules
HELPER_PATH = re.compile(r'[A-Za-z0-9_./-]{1,200}')
FORWARDED_REQUEST = ('Accept', 'Accept-Language', 'If-None-Match', 'If-Modified-Since')
FORWARDED_RESPONSE = ('Cache-Control', 'ETag', 'Last-Modified', 'Content-Security-Policy')
USER_AGENT = 'aircon-central/' + VERSION + ' firebase-auth-helper'
BODY_LIMIT = 2 * 1024 * 1024
HEADER_LIMIT = 8192
QUERY_LIMIT = 8192
TIMEOUT = (5, 10)  # connect, per read
DEADLINE = 20  # seconds for the whole body: the read timeout alone restarts on every chunk


def web_config(value):
    """Check the private config's optional 'web_app' block; None when it is absent."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(WEB_FIELDS):
        raise ValueError('Invalid web app configuration')
    for key, pattern in WEB_FIELDS.items():
        if not isinstance(value[key], str) or not pattern.fullmatch(value[key]):
            raise ValueError('Invalid web app configuration')
    return dict(value)


def helper_session():
    session = requests.Session()
    session.trust_env = False  # no inherited proxy, .netrc credentials or CA overrides
    # One shared session serves every visitor: never keep or replay a cookie between them.
    session.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
    return session


def response_headers(response) -> bool:
    """Apply /app/ and sign-in helper headers; False leaves the server-wide policy to the caller."""
    if g.get('auth_helper_relayed'):
        # Firebase's handler page loads Google scripts: its own CSP (if any) applies, not ours.
        response.headers.setdefault('Cache-Control', 'no-store')
        return True
    path = request.path
    if path == '/app' or path.startswith('/app/'):
        response.headers.setdefault('Cache-Control', 'no-store')  # files set no-cache themselves
        response.headers['Content-Security-Policy'] = APP_CSP
        response.headers['Referrer-Policy'] = 'same-origin'
        return True
    return False


def register(app, *, firebase_project=None, web_settings=None, folder=None, http=None):
    folder = Path(folder) if folder is not None else FOLDER
    project = (firebase_project if isinstance(firebase_project, str)
               and PROJECT.fullmatch(firebase_project) else None)
    web_settings = web_config(web_settings)
    session = http if http is not None else helper_session()
    limiter = app.extensions.setdefault('limits', {})['auth_helper'] = Limiter((120, 60))
    log = logging.getLogger('central_server')

    def serve(name):
        suffix = Path(name).suffix
        if not FILE_NAME.fullmatch(name) or suffix not in TYPES:
            raise APIError('not_found', 404)
        root = folder.resolve()
        expected = root.joinpath(*name.split('/'))
        try:
            target = expected.resolve(strict=True)
            if target != expected or not target.is_relative_to(root) or not target.is_file():
                raise APIError('not_found', 404)  # symlinked paths and folders
            modified = target.stat().st_mtime
            data = target.read_bytes()
        except (OSError, RuntimeError):
            raise APIError('not_found', 404) from None
        response = Response(data, content_type=TYPES[suffix])
        response.headers['Cache-Control'] = 'no-cache'  # always revalidate; 304 when unchanged
        if name == 'sw.js':
            response.headers['Service-Worker-Allowed'] = '/app/'
        response.set_etag(hashlib.sha256(data).hexdigest())
        response.last_modified = int(modified)
        return response.make_conditional(request)

    @app.get('/app')
    def web_app_root():
        return redirect('/app/', 308)

    @app.get('/app/')
    def web_app_index():
        return serve('index.html')

    @app.get('/app/config.json')
    def web_app_config():
        if web_settings is None or project is None:
            raise APIError('web_not_configured', 503)
        return jsonify(firebase={'apiKey': web_settings['api_key'],
                                 'authDomain': web_settings['auth_domain'],
                                 'projectId': project,
                                 'appId': web_settings['app_id'],
                                 'messagingSenderId': web_settings['messaging_sender_id']},
                       server_version=VERSION)  # Cache-Control: no-store (default)

    @app.get('/app/<path:name>')
    def web_app_file(name):
        return serve(name)

    def relay(path):
        if project is None:
            raise APIError('auth_helper_not_configured', 503)
        try:
            query = request.query_string.decode('ascii')
        except UnicodeDecodeError:
            raise APIError('invalid_query', 400) from None
        if len(query) > QUERY_LIMIT:
            raise APIError('invalid_query', 400)
        client = (request.headers.get('CF-Connecting-IP') or request.remote_addr or '')[:64]
        wait = limiter.take(client)
        if wait:
            raise APIError('rate_limited', 429, retry_after=wait)
        # The host comes only from server configuration; the request supplies path and query.
        url = 'https://' + project + '.firebaseapp.com' + path + ('?' + query if query else '')
        headers = {'User-Agent': USER_AGENT}
        for key in FORWARDED_REQUEST:
            value = request.headers.get(key)
            if value and len(value) <= 1024 and value.isascii() and value.isprintable():
                headers[key] = value
        # Exceptions can carry the URL, whose query holds OAuth codes: log a fixed outcome only.
        try:
            upstream = session.request(request.method, url, headers=headers, timeout=TIMEOUT,
                                       allow_redirects=False, stream=True)
        except Exception:
            log.warning('AUTH_HELPER_RELAY outcome=unavailable')
            raise APIError('auth_helper_unavailable', 502) from None
        try:
            declared = upstream.headers.get('Content-Length', '')
            if declared.isdigit() and int(declared) > BODY_LIMIT:
                outcome = 'too_large'
            else:
                outcome, size, chunks = None, 0, []
                deadline = time.monotonic() + DEADLINE
                for chunk in upstream.iter_content(65536):
                    size += len(chunk)
                    if size > BODY_LIMIT:
                        outcome = 'too_large'
                        break
                    if time.monotonic() > deadline:
                        outcome = 'too_slow'
                        break
                    chunks.append(chunk)
            status = upstream.status_code
            if outcome is None and not (isinstance(status, int) and 200 <= status <= 599):
                outcome = 'invalid_status'
        except Exception:
            outcome = 'unavailable'
        finally:
            try:
                upstream.close()
            except Exception:
                pass
        if outcome:
            log.warning('AUTH_HELPER_RELAY outcome=%s', outcome)
            raise APIError('auth_helper_unavailable', 502)
        if status >= 500:
            log.warning('AUTH_HELPER_RELAY outcome=upstream_error')
        response = Response(b''.join(chunks), status=status,
                            content_type=safe(upstream.headers.get('Content-Type'))
                            or 'application/octet-stream')
        for key in FORWARDED_RESPONSE:
            value = safe(upstream.headers.get(key))
            if value:
                response.headers[key] = value
        g.auth_helper_relayed = True
        return response

    def safe(value):
        return (value if isinstance(value, str) and 0 < len(value) <= HEADER_LIMIT
                and value.isascii() and value.isprintable() else None)

    @app.get('/__/auth/<path:name>')
    def auth_helper(name):
        if not HELPER_PATH.fullmatch(name) or '..' in name or '//' in name:
            raise APIError('not_found', 404)
        return relay('/__/auth/' + name)

    @app.get('/__/firebase/init.json')
    def firebase_init():
        return relay('/__/firebase/init.json')
