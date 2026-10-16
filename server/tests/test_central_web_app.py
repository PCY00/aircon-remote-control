"""Home-screen web app files, per-route headers, private web config and the sign-in helper relay."""

import email.message
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

import pytest
import requests
from requests.structures import CaseInsensitiveDict

sys.path.insert(0, str(Path(__file__).parents[1] / "services/central-server"))
from central_server import VERSION, web_app
from central_server.storage import initialize
from central_server.web import create_app

WEB = dict(api_key="test-web-key-0123456789", app_id="1:123456789012:web:0123456789abcdef",
           messaging_sender_id="123456789012", auth_domain="home.example.test")
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
FILES = {
    "index.html": (b"<!doctype html><title>home</title>\r\n", "text/html"),
    "sw.js": (b"self.addEventListener('push', () => {});\n", "text/javascript"),
    "app.js": (b"import './vendor/firebase-app.js';\n", "text/javascript"),
    "module.mjs": (b"export const ready = true;\n", "text/javascript"),
    "styles/app.css": (b"body{margin:0}\n", "text/css"),
    "manifest.webmanifest": (b'{"name":"home","start_url":"/app/"}', "application/manifest+json"),
    "data/labels.json": (b'{"door":"door"}', "application/json"),
    "icons/icon-192.png": (PNG, "image/png"),
    "icons/mark.svg": (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
    "favicon.ico": (b"\x00\x00\x01\x00\r\n", "image/x-icon"),
    "vendor/LICENSE.txt": (b"Apache-2.0\n", "text/plain"),
    "vendor/firebase-app.js": (b"export function initializeApp(){}\n", "text/javascript"),
}
HIDDEN = {  # present in the folder but never served
    ".hidden.js": b"hidden",
    ".well-known/assetlinks.json": b"[]",
    "README.md": b"# notes",
    "server.py": b"SECRET = 1",
    "private.env": b"KEY=1",
    "config.json": b'{"leak": true}',  # the configured route answers instead of this file
}
APP_CSP = ("default-src 'self'; script-src 'self' https://apis.google.com; style-src 'self'; "
           "img-src 'self' data: https://lh3.googleusercontent.com; "
           "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
           "https://firebaseinstallations.googleapis.com https://fcmregistrations.googleapis.com "
           "https://www.googleapis.com; frame-src 'self'; worker-src 'self'; manifest-src 'self'; "
           "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
STRICT_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"


class Upstream:
    """Stands in for the requests session: records each call and replays one canned answer."""

    def __init__(self):
        self.calls, self.error = [], None
        self.answer(200, b"<html>handler</html>", {"Content-Type": "text/html; charset=utf-8"})

    def answer(self, status, body=b"", headers=None, chunks=None, chunk_error=None):
        self.status, self.headers = status, CaseInsensitiveDict(headers or {})
        self.chunks = chunks if chunks is not None else ([body] if body else [])
        self.chunk_error = chunk_error

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        if self.error:
            raise self.error
        return Answer(self)


class Answer:
    def __init__(self, upstream):
        self.upstream, self.status_code, self.headers = upstream, upstream.status, upstream.headers
        self.closed = False

    def iter_content(self, size):
        yield from self.upstream.chunks
        if self.upstream.chunk_error:
            raise self.upstream.chunk_error

    def close(self):
        self.closed = True


@pytest.fixture
def site(tmp_path):
    db = tmp_path / "central.sqlite3"
    initialize(db)
    folder = tmp_path / "webapp"
    for name, (data, _) in FILES.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    for name, data in HIDDEN.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    (tmp_path / "outside.html").write_bytes(b"outside the web app")
    upstream = Upstream()

    def make(**changes):
        options = dict(firebase_project="test-project", web_config=dict(WEB), webapp_folder=folder,
                       auth_http=upstream) | changes
        return create_app(db, **options)
    return make, folder, upstream


def test_app_root_redirects_and_index_is_served(site):
    make, _, _ = site
    client = make().test_client()
    moved = client.get("/app")
    assert moved.status_code == 308 and moved.headers["Location"] == "/app/"
    index = client.get("/app/")
    assert index.status_code == 200 and index.data == FILES["index.html"][0]
    assert index.mimetype == "text/html" and index.headers["Content-Type"] == "text/html; charset=utf-8"
    assert client.get("/app/index.html").data == index.data


@pytest.mark.parametrize("name", sorted(FILES))
def test_each_allowed_file_has_its_type_and_exact_bytes(site, name):
    make, _, _ = site
    response = make().test_client().get("/app/" + name)
    data, mimetype = FILES[name]
    assert response.status_code == 200 and response.data == data  # PNG CR LF bytes untouched
    assert response.mimetype == mimetype
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["ETag"] and response.headers["Last-Modified"]
    assert response.headers["Content-Security-Policy"] == APP_CSP


@pytest.mark.parametrize("path", [
    "/app/../outside.html", "/app/%2e%2e/outside.html", "/app/..%2foutside.html",
    "/app/icons/../../outside.html", "/app/./index.html", "/app/.hidden.js",
    "/app/.well-known/assetlinks.json", "/app/README.md", "/app/server.py", "/app/private.env",
    "/app/styles", "/app/styles/", "/app/icons", "/app/missing.js", "/app/missing/app.js",
    "/app/icons%5cicon-192.png", "/app/icons\\icon-192.png", "/app/%5c..%5coutside.html",
    "/app/C:/outside.html", "/app/index.html.", "/app/INDEX.HTML", "/app/index.html%00.js",
    "/app/index.html:stream.js", "/app/app.js~", "/app/" + "a/" * 9 + "deep.js",
    "/app/" + "x" * 101 + ".js",
])
def test_paths_outside_rules_are_not_found(site, path):
    make, _, _ = site
    response = make().test_client().get(path)
    assert response.status_code == 404 and response.json == {"error": "not_found"}, path
    assert b"outside the web app" not in response.data and b"SECRET" not in response.data


@pytest.mark.parametrize("path", ["/app//etc/hosts.txt", "/app/icons//icon-192.png", "/app/%2Foutside.html"])
def test_doubled_slashes_never_leave_the_folder(site, path):
    make, _, _ = site
    response = make().test_client().get(path, follow_redirects=True)
    assert response.status_code in (200, 404)
    assert b"outside the web app" not in response.data
    if response.status_code == 200:
        assert response.data == FILES["icons/icon-192.png"][0]  # merged to the same in-folder file


def test_a_symlink_leading_out_of_the_folder_is_refused(site, tmp_path):
    make, folder, _ = site
    try:
        os.symlink(tmp_path / "outside.html", folder / "linked.html")
        os.symlink(tmp_path, folder / "linked-folder", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need extra privileges on this system")
    client = make().test_client()
    for path in ("/app/linked.html", "/app/linked-folder/outside.html"):
        response = client.get(path)
        assert response.status_code == 404 and b"outside" not in response.data


def test_missing_folder_or_index_is_not_found(site, tmp_path):
    make, folder, _ = site
    client = make(webapp_folder=tmp_path / "no-such-folder").test_client()
    assert client.get("/app/").status_code == 404
    (folder / "index.html").unlink()
    response = make().test_client().get("/app/")
    assert response.status_code == 404 and response.json == {"error": "not_found"}


def test_headers_per_route(site):
    make, _, _ = site
    client = make().test_client()
    for path in ("/app/", "/app/app.js", "/app/sw.js", "/app/config.json", "/app/missing.js", "/app"):
        response = client.get(path)
        assert response.headers["Content-Security-Policy"] == APP_CSP, path
        assert response.headers["X-Content-Type-Options"] == "nosniff", path
        assert response.headers["Referrer-Policy"] == "same-origin", path
    assert client.get("/app/sw.js").headers["Service-Worker-Allowed"] == "/app/"
    assert "Service-Worker-Allowed" not in client.get("/app/app.js").headers
    assert client.get("/app/").headers["Cache-Control"] == "no-cache"
    for path in ("/app/config.json", "/app/missing.js", "/app"):
        assert client.get(path).headers["Cache-Control"] == "no-store", path
    # Every other route keeps today's headers exactly.
    for path in ("/", "/health/live", "/health/ready", "/v1/me", "/no-such-route", "/apps/", "/application"):
        response = client.get(path)
        assert response.headers["Content-Security-Policy"] == STRICT_CSP, path
        assert response.headers["Cache-Control"] == "no-store", path
        assert response.headers["X-Content-Type-Options"] == "nosniff", path
        assert "Referrer-Policy" not in response.headers, path


def test_unchanged_files_revalidate_with_304(site):
    make, folder, _ = site
    client = make().test_client()
    first = client.get("/app/app.js")
    etag, modified = first.headers["ETag"], first.headers["Last-Modified"]
    same = client.get("/app/app.js", headers={"If-None-Match": etag})
    assert same.status_code == 304 and same.data == b""
    assert same.headers["ETag"] == etag and same.headers["Cache-Control"] == "no-cache"
    assert same.headers["Content-Security-Policy"] == APP_CSP
    assert client.get("/app/app.js", headers={"If-Modified-Since": modified}).status_code == 304
    assert client.get("/app/app.js", headers={"If-None-Match": '"other"'}).status_code == 200
    head = client.head("/app/app.js")
    assert head.status_code == 200 and head.data == b"" and head.headers["ETag"] == etag
    (folder / "app.js").write_bytes(b"export const changed = 1;\n")
    changed = client.get("/app/app.js", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.data == b"export const changed = 1;\n"
    assert changed.headers["ETag"] != etag  # the ETag is the content hash


def test_config_json_returns_public_web_settings_only_when_configured(site):
    make, _, _ = site
    response = make().test_client().get("/app/config.json")
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert response.json == {
        "firebase": {"apiKey": WEB["api_key"], "authDomain": WEB["auth_domain"],
                     "projectId": "test-project", "appId": WEB["app_id"],
                     "messagingSenderId": WEB["messaging_sender_id"]},
        "server_version": VERSION,
    }
    for changes in (dict(web_config=None), dict(firebase_project=None),
                    dict(firebase_project="Bad_Project"), dict(firebase_project="x.test/evil")):
        refused = make(**changes).test_client().get("/app/config.json")
        assert refused.status_code == 503 and refused.json == {"error": "web_not_configured"}, changes
        assert refused.headers["Cache-Control"] == "no-store"
    # The static files still load without the web settings.
    assert make(web_config=None).test_client().get("/app/").status_code == 200


def test_web_config_validation():
    assert web_app.web_config(None) is None
    assert web_app.web_config(dict(WEB)) == WEB
    for broken in ({k: v for k, v in WEB.items() if k != "app_id"}, WEB | dict(extra="x"), [], "x",
                   WEB | dict(api_key=""), WEB | dict(api_key="has space 0123456789"),
                   WEB | dict(api_key=1234567890123), WEB | dict(messaging_sender_id="12a"),
                   WEB | dict(app_id="1:2:web:<script>"), WEB | dict(app_id="x" * 129),
                   WEB | dict(auth_domain="https://home.example.test"),
                   WEB | dict(auth_domain="home.example.test:443"),
                   WEB | dict(auth_domain="home.example.test/path"),
                   WEB | dict(auth_domain="Home.Example.Test"), WEB | dict(auth_domain="home.example.test."),
                   WEB | dict(auth_domain="localhost"), WEB | dict(auth_domain="-bad.example.test"),
                   WEB | dict(auth_domain="a" * 64 + ".example.test"), WEB | dict(auth_domain=None)):
        with pytest.raises(ValueError):
            web_app.web_config(broken)
    with pytest.raises(ValueError):
        create_app(Path("unused.sqlite3"), web_config=WEB | dict(auth_domain="https://x.test"))


def test_private_config_web_app_block_reaches_the_server(tmp_path, monkeypatch):
    from central_server import __main__ as entry
    home = tmp_path / "home"
    config = home / ".config/aircon-central/config.json"
    config.parent.mkdir(parents=True)
    monkeypatch.setattr(entry.Path, "home", lambda: home)
    monkeypatch.setenv("A50_CENTRAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("A50_CENTRAL_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("A50_FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.setattr(entry.os, "umask", lambda mask: 0)
    monkeypatch.setattr(entry, "RotatingFileHandler", lambda *args, **kwargs: logging.NullHandler())
    served = []
    monkeypatch.setattr(entry, "serve", lambda app, **options: served.append(app))
    config.write_text(json.dumps({"firebase_project_id": "test-project", "web_app": WEB}))
    entry.main()
    assert served[-1].test_client().get("/app/config.json").json["firebase"] == {
        "apiKey": WEB["api_key"], "authDomain": WEB["auth_domain"], "projectId": "test-project",
        "appId": WEB["app_id"], "messagingSenderId": WEB["messaging_sender_id"]}
    for broken in (WEB | {"auth_domain": "https://home.example.test"}, {"api_key": "x"}, "text"):
        config.write_text(json.dumps({"firebase_project_id": "test-project", "web_app": broken}))
        with pytest.raises(SystemExit):
            entry.main()
    config.write_text(json.dumps({"firebase_project_id": "test-project"}))
    entry.main()
    assert served[-1].test_client().get("/app/config.json").status_code == 503
    assert len(served) == 2


def test_relay_forwards_path_and_query_to_the_configured_project_only(site):
    make, _, upstream = site
    client = make().test_client()
    query = ("apiKey=test-web-key&appName=%5BDEFAULT%5D&authType=signInViaRedirect"
             "&redirectUrl=https%3A%2F%2Fhome.example.test%2Fapp%2F&v=12.19.0")
    response = client.get("/__/auth/handler?" + query, headers={
        "Host": "evil.example.test", "X-Forwarded-Host": "evil.example.test"})
    assert response.status_code == 200 and response.data == b"<html>handler</html>"
    method, url, options = upstream.calls[-1]
    assert method == "GET" and url == "https://test-project.firebaseapp.com/__/auth/handler?" + query
    assert options["allow_redirects"] is False and options["timeout"] == (5, 10)
    assert options["stream"] is True
    for path in ("/__/auth/handler.js", "/__/auth/iframe", "/__/auth/iframe.js",
                 "/__/auth/experiments.js", "/__/firebase/init.json"):
        assert client.get(path).status_code == 200
        assert upstream.calls[-1][1] == "https://test-project.firebaseapp.com" + path
    client.get("/__/auth/handler?project=evil&host=evil.example.test")
    assert upstream.calls[-1][1].startswith("https://test-project.firebaseapp.com/__/auth/handler?")
    head = client.head("/__/auth/iframe")
    assert head.status_code == 200 and upstream.calls[-1][0] == "HEAD"
    assert client.post("/__/auth/handler").status_code == 405


@pytest.mark.parametrize("path", [
    "/__/auth/../firebase/init.json", "/__/auth/%2e%2e/x", "/__/auth/a/../../x", "/__/auth/a%40evil.test",
    "/__/auth/a%3Fb", "/__/auth/a%23b", "/__/auth/a%5cb", "/__/auth/a:b", "/__/auth/a%20b",
    "/__/auth/" + "a" * 201, "/__/auth/", "/__/firebase/other.json", "/__/auth/a//b",
])
def test_relay_refuses_paths_outside_its_characters(site, path):
    make, _, upstream = site
    response = make().test_client().get(path)
    assert response.status_code in (404, 308), path
    assert not upstream.calls, path


def test_relay_forwards_only_safe_request_headers(site):
    make, _, upstream = site
    client = make().test_client()
    client.get("/__/auth/handler", headers={
        "Cookie": "sid=private-cookie", "Authorization": "Bearer private-token",
        "X-Forwarded-For": "203.0.113.9", "CF-Connecting-IP": "203.0.113.9",
        "User-Agent": "Mozilla/5.0 (iPhone)", "Referer": "https://home.example.test/app/?code=x",
        "Accept": "text/html", "Accept-Language": "ko-KR,ko;q=0.9",
        "If-None-Match": '"abc"', "If-Modified-Since": "Wed, 14 Oct 2026 00:00:00 GMT",
        "Origin": "https://home.example.test"})
    headers = upstream.calls[-1][2]["headers"]
    assert headers == {"User-Agent": "aircon-central/" + VERSION + " firebase-auth-helper",
                       "Accept": "text/html", "Accept-Language": "ko-KR,ko;q=0.9",
                       "If-None-Match": '"abc"', "If-Modified-Since": "Wed, 14 Oct 2026 00:00:00 GMT"}
    assert "cookies" not in upstream.calls[-1][2] and "auth" not in upstream.calls[-1][2]
    client.get("/__/auth/handler", headers={"Accept-Language": "x" * 1025})
    assert "Accept-Language" not in upstream.calls[-1][2]["headers"]


def test_relay_returns_only_safe_response_headers_without_our_csp(site):
    make, _, upstream = site
    upstream.answer(200, b"<html>handler</html>", {
        "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=1800",
        "ETag": '"upstream-etag"', "Last-Modified": "Wed, 14 Oct 2026 00:00:00 GMT",
        "Content-Security-Policy": "script-src 'self' https://apis.google.com",
        "Set-Cookie": "sid=upstream; Path=/", "Access-Control-Allow-Origin": "*",
        "Location": "https://evil.example.test/", "Content-Encoding": "gzip",
        "Content-Length": "20", "Strict-Transport-Security": "max-age=1", "X-Upstream": "1"})
    response = make().test_client().get("/__/auth/handler")
    assert response.status_code == 200 and response.data == b"<html>handler</html>"
    assert response.headers["Content-Security-Policy"] == "script-src 'self' https://apis.google.com"
    assert response.headers["Cache-Control"] == "public, max-age=1800"
    assert response.headers["ETag"] == '"upstream-etag"'
    assert response.headers["Last-Modified"] == "Wed, 14 Oct 2026 00:00:00 GMT"
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    for name in ("Set-Cookie", "Access-Control-Allow-Origin", "Location", "Content-Encoding",
                 "Strict-Transport-Security", "X-Upstream", "Referrer-Policy"):
        assert name not in response.headers, name
    upstream.answer(200, b"{}", {"Content-Type": "application/json"})
    plain = make().test_client().get("/__/firebase/init.json")
    assert "Content-Security-Policy" not in plain.headers  # never the global default-src 'none'
    assert plain.headers["Cache-Control"] == "no-store" and plain.headers["X-Content-Type-Options"] == "nosniff"
    upstream.answer(200, b"raw", {})
    assert make().test_client().get("/__/auth/iframe").headers["Content-Type"] == "application/octet-stream"


@pytest.mark.parametrize("status", [304, 404, 500, 503])
def test_relay_passes_upstream_status_through(site, status):
    make, _, upstream = site
    upstream.answer(status, b"" if status == 304 else b"upstream page", {"ETag": '"e"', "Content-Type": "text/html"})
    response = make().test_client().get("/__/auth/handler", headers={"If-None-Match": '"e"'})
    assert response.status_code == status
    assert response.data == (b"" if status == 304 else b"upstream page")


def test_real_session_ignores_proxies_and_never_keeps_cookies():
    session = web_app.helper_session()
    assert session.trust_env is False
    header = email.message.Message()
    header["Set-Cookie"] = "sid=private; Path=/; Secure"

    class Reply:
        def info(self):
            return header
    request = urllib.request.Request("https://test-project.firebaseapp.com/__/auth/handler")
    session.cookies.extract_cookies(Reply(), request)
    assert len(session.cookies) == 0
    ordinary = requests.Session()
    ordinary.cookies.extract_cookies(Reply(), request)
    assert len(ordinary.cookies) == 1  # the fixture would set a cookie on a default session


def test_relay_caps_the_body_and_never_logs_the_query(site, caplog):
    make, _, upstream = site
    client = make().test_client()
    secret = "?code=private-oauth-code&state=private-state"
    limit = web_app.BODY_LIMIT
    upstream.answer(200, headers={"Content-Length": str(limit + 1)}, chunks=[b"x"])
    with caplog.at_level(logging.INFO):
        declared = client.get("/__/auth/handler" + secret)
        upstream.answer(200, chunks=[b"x" * 65536] * (limit // 65536) + [b"x"])
        streamed = client.get("/__/auth/handler" + secret)
    for response in (declared, streamed):
        assert response.status_code == 502 and response.json == {"error": "auth_helper_unavailable"}
        assert response.headers["Content-Security-Policy"] == STRICT_CSP  # our own error page
    assert "AUTH_HELPER_RELAY outcome=too_large" in caplog.text
    assert "private" not in caplog.text and "firebaseapp" not in caplog.text
    upstream.answer(200, chunks=[b"x" * 65536] * (limit // 65536))
    assert len(client.get("/__/auth/handler").data) == limit


@pytest.mark.parametrize("failure", ["connect", "read", "status"])
def test_upstream_failures_are_502_with_a_fixed_log_line(site, caplog, failure):
    make, _, upstream = site
    url = "https://test-project.firebaseapp.com/__/auth/handler?code=private-oauth-code"
    if failure == "connect":
        upstream.error = requests.ConnectionError("failed " + url)
    elif failure == "read":
        upstream.answer(200, chunks=[b"part"], chunk_error=requests.exceptions.ChunkedEncodingError(url))
    else:
        upstream.answer(99, b"odd")
    with caplog.at_level(logging.INFO):
        response = make().test_client().get("/__/auth/handler?code=private-oauth-code")
    assert response.status_code == 502 and response.json == {"error": "auth_helper_unavailable"}
    assert "AUTH_HELPER_RELAY outcome=" in caplog.text
    assert "private" not in caplog.text and "firebaseapp" not in caplog.text


@pytest.mark.parametrize("project", [None, "", "Bad_Project", "evil.example.test/x", "a" * 31, 7])
def test_relay_without_a_valid_project_id_is_503_and_calls_nothing(site, project):
    make, _, upstream = site
    response = make(firebase_project=project).test_client().get("/__/auth/handler")
    assert response.status_code == 503 and response.json == {"error": "auth_helper_not_configured"}
    assert not upstream.calls


def test_relay_rate_limit_is_per_visitor(site):
    make, _, upstream = site
    app = make()
    clock = [100.0]
    app.extensions["limits"]["auth_helper"].clock = lambda: clock[0]
    client = app.test_client()
    noisy = {"CF-Connecting-IP": "203.0.113.5"}
    for _ in range(120):
        assert client.get("/__/auth/handler", headers=noisy).status_code == 200
    limited = client.get("/__/auth/handler", headers=noisy)
    assert limited.status_code == 429 and limited.json == {"error": "rate_limited"}
    assert int(limited.headers["Retry-After"]) >= 1
    assert len(upstream.calls) == 120  # the refused request never reached Firebase
    assert client.get("/__/auth/handler", headers={"CF-Connecting-IP": "198.51.100.7"}).status_code == 200
    assert client.get("/__/auth/handler").status_code == 200  # keyed by the peer without the header
    clock[0] += 1
    assert client.get("/__/auth/handler", headers=noisy).status_code == 200
