"""Verify Firebase Google sign-in using Google's HTTPS public certificates."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

import jwt
from cryptography import x509

from central_server.households import APIError, Identity

CERTIFICATE_URL = ('https://www.googleapis.com/robot/v1/metadata/x509/'
                   'securetoken@system.gserviceaccount.com')


class Certificates:
    def __init__(self):
        self.lock = threading.Lock()
        self.keys = {}
        self.expires = 0.0
        self.retry_after = 0.0

    def get(self):
        with self.lock:
            now = time.monotonic()
            if now < self.expires:
                return self.keys
            if now < self.retry_after:
                raise APIError('authentication_unavailable', 503)
            try:
                with urllib.request.urlopen(CERTIFICATE_URL, timeout=5) as response:
                    if response.geturl() != CERTIFICATE_URL:
                        raise ValueError('Unexpected certificate endpoint')
                    raw = response.read(262145)
                    if len(raw) > 262144:
                        raise ValueError('Certificate response too large')
                    certs = json.loads(raw)
                    if (not isinstance(certs, dict) or not certs or any(
                            not isinstance(kid, str) or not isinstance(cert, str)
                            for kid, cert in certs.items())):
                        raise ValueError('Invalid certificate mapping')
                    keys = {kid: x509.load_pem_x509_certificate(cert.encode()).public_key()
                            for kid, cert in certs.items()}
                    maximum = re.search(r'\bmax-age=(\d+)\b', response.headers.get('Cache-Control',''))
                    age = int(response.headers.get('Age', '0'))
                    lifetime = max(0, min(int(maximum[1]), 86400)-age) if maximum else 0
                self.keys, self.expires = keys, time.monotonic()+lifetime
                return keys
            except (OSError, ValueError, TypeError, AttributeError) as error:
                self.retry_after = time.monotonic()+5
                raise APIError('authentication_unavailable', 503) from error


class FirebaseIdentity:
    def __init__(self, project: str, *, certificates=None):
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]', project):
            raise ValueError('Invalid Firebase project ID')
        self.project = project
        self.certificates = certificates if certificates is not None else Certificates()

    def verify(self, token: str) -> Identity:
        if not isinstance(token, str) or not 1 <= len(token) <= 8192:
            raise APIError('invalid_credentials', 401)
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            if (header.get('alg') != 'RS256' or not isinstance(kid, str)
                    or not 1 <= len(kid) <= 128):
                raise ValueError('Invalid token header')
            key = self.certificates.get().get(kid)
            if key is None:
                raise ValueError('Unknown signing key')
            issuer = 'https://securetoken.google.com/'+self.project
            claims = jwt.decode(token, key, algorithms=['RS256'], audience=self.project,
                                issuer=issuer, options={'require':
                                    ['exp','iat','auth_time','aud','iss','sub']})
            now = time.time()
            if claims['aud'] != self.project:
                raise ValueError('Firebase audience must be the project ID')
            if any(type(claims[name]) is not int for name in ('exp','iat','auth_time')):
                raise ValueError('Invalid time claims')
            if (claims['auth_time'] < 0 or claims['auth_time'] > now
                    or claims['iat'] < 0 or claims['iat'] > now or claims['exp'] <= now):
                raise ValueError('Invalid authentication time')
            if not isinstance(claims['sub'], str) or not 1 <= len(claims['sub']) <= 128:
                raise ValueError('Invalid subject')
            firebase = claims.get('firebase')
            email = claims.get('email')
            if (not isinstance(firebase, dict) or firebase.get('sign_in_provider') != 'google.com'
                    or claims.get('email_verified') is not True or not isinstance(email, str)
                    or not re.fullmatch(r'[^\s@]{1,128}@[^\s@]{1,128}', email)):
                raise ValueError('Verified Google email required')
            return Identity(issuer, claims['sub'], email.casefold())
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as error:
            raise APIError('invalid_credentials', 401) from error
