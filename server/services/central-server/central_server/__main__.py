"""Launch the foundation on the phone's loopback interface."""

from __future__ import annotations

import logging
import json
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from waitress import serve

from central_server import VERSION
from central_server.auth import FirebaseIdentity
from central_server.inventory import BODY_BYTES
from central_server.storage import initialize
from central_server.web import create_app
from central_server.web_app import web_config


def main():
    os.umask(0o077)
    data = Path(os.environ.get('A50_CENTRAL_DATA_DIR') or
                Path.home() / '.local/share/aircon-central')
    state = Path(os.environ.get('A50_CENTRAL_STATE_DIR') or
                 Path.home() / '.local/state/aircon-central')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = RotatingFileHandler(state/'server.log', maxBytes=1048576,
                                  backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    database = data / 'central.sqlite3'
    try:
        initialize(database)
    except Exception as error:
        logging.error('STARTUP_DATABASE_FAILED kind=%s', type(error).__name__)
        raise SystemExit(1) from None
    config_path = Path.home()/'.config/aircon-central/config.json'
    try:
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
        if not isinstance(config, dict) or set(config)-{'firebase_project_id', 'fcm_service_account_file',
                                                        'web_app'}:
            raise ValueError('Invalid private configuration')
        project = os.environ.get('A50_FIREBASE_PROJECT_ID') or config.get('firebase_project_id')
        # Optional public Firebase web settings for /app/config.json; without them the /app/
        # files still load but the web app reports that sign-in is not configured.
        web = web_config(config.get('web_app'))
        verifier = FirebaseIdentity(project) if project else None
        sender = None
        if config.get('fcm_service_account_file'):
            from central_server.fcm import FCMSender
            sender = FCMSender(project, Path(config['fcm_service_account_file']))
    except (OSError, ValueError, TypeError):
        logging.error('STARTUP_CONFIGURATION_FAILED')
        raise SystemExit(1) from None
    print(f'CENTRAL_START version={VERSION} bind=loopback port=8001', flush=True)
    logging.info('CENTRAL_START version=%s bind=loopback port=8001', VERSION)
    if sender:
        from central_server.push import PushStore, PushWorker
        PushWorker(PushStore(database), sender).start()
        logging.info('FCM_SENDER_CONFIGURED')
    else:
        logging.info('FCM_SENDER_NOT_CONFIGURED')
    logging.info('WEB_APP_CONFIGURED' if web and project else 'WEB_APP_NOT_CONFIGURED')
    # Waitress refuses a body of max_request_body_size bytes or more. Its cap fits the 32 KiB
    # device-list route; Flask keeps every other route at 16 KiB (MAX_CONTENT_LENGTH).
    serve(create_app(database, identity_verifier=verifier, push_sender_ready=sender is not None,
                     firebase_project=project, web_config=web), host='127.0.0.1', port=8001, threads=2,
          connection_limit=32, channel_timeout=15, max_request_header_size=16384,
          max_request_body_size=BODY_BYTES+1, expose_tracebacks=False)


if __name__ == '__main__':
    main()
