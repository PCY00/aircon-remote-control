"""Loopback service health and household APIs exposed through the existing HTTPS tunnel."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string

from central_server import VERSION
from central_server.storage import ready
from central_server import web_app

STATUS_PAGE = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>스마트홈 중앙 서버</title><style>
body{margin:0;background:#f3f6fa;color:#182438;font-family:system-ui,sans-serif}
main{max-width:540px;margin:12vh auto;padding:32px;background:white;border-radius:24px}
.label{color:#52657f;font-size:14px}h1{font-size:28px;margin:16px 0}
.state{padding:18px;background:{{ '#e7f5ec' if healthy else '#fff2dd' }};border-radius:14px}
p{line-height:1.7}footer{margin-top:32px;color:#61728a;font-size:13px}
@media(max-width:600px){main{margin:40px 16px;padding:24px}}</style>
<main><div class="label">SMART HOME · A50</div><h1>스마트홈 중앙 서버</h1>
<div class="state">{{ '● 정상 동작 중' if healthy else '● 저장소 확인 필요' }}</div>
<p>서버 실행 환경{{ '과 저장소가 준비됐습니다.' if healthy else '은 실행 중입니다.' }}</p>
<p>{{ '집 등록과 가족 권한 API가 준비됐습니다.' if auth_ready else 'Google 로그인 설정을 기다리고 있습니다. 가족 데이터 접근은 잠겨 있습니다.' }}</p>
<p>가족 앱에서 집의 알림과 기록을 확인하고, 연결된 에어컨의 전원·온도·풍량·운전 모드를 조작할 수 있습니다.</p>
<footer>시험 운영 · 버전 {{ version }}</footer></main></html>'''


def create_app(database: Path, *, identity_verifier=None, push_sender_ready=False,
               firebase_project=None, web_config=None, webapp_folder=None, auth_http=None) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384)
    app.config['PUSH_SENDER_READY'] = push_sender_ready
    started = time.monotonic()

    def database_ready():
        try:
            return ready(database)
        except (sqlite3.Error, OSError):
            logging.getLogger('central_server').warning('DATABASE_READINESS_FAILED')
            return False

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if web_app.response_headers(response):
            return response  # /app/ and the sign-in helper set their own cache and CSP headers
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
        )
        return response

    @app.get('/health/live')
    def live():
        return jsonify(status='ok', service='aircon-central', version=VERSION,
                       uptime_seconds=round(time.monotonic()-started, 1), scope='households')

    @app.get('/health/ready')
    def readiness():
        healthy = database_ready()
        return jsonify(status='ready' if healthy else 'unavailable',
                       database='ok' if healthy else 'unavailable'), 200 if healthy else 503

    @app.get('/')
    def index():
        healthy = database_ready()
        return render_template_string(STATUS_PAGE, healthy=healthy, version=VERSION, auth_ready=identity_verifier is not None), (
            200 if healthy else 503
        )

    from central_server.api import register
    register(app, database, identity_verifier)
    # Home-screen web app for iPhone family members (decision record 0020).
    web_app.register(app, firebase_project=firebase_project, web_settings=web_config,
                     folder=webapp_folder, http=auth_http)
    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        logging.getLogger('central_server').warning('DATABASE_OPERATION_FAILED kind=%s', type(error).__name__)
        return jsonify(error='storage_unavailable'), 503
    return app
