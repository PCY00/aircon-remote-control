"""Signed user routes reject ID injection and foreign-device test sends."""

import uuid

from tests.test_central_households import environment as environment


def test_installation_endpoints_require_verified_user_and_exact_body(environment):
    _, app, _, _, call = environment
    device = str(uuid.uuid4())
    path = "/v1/installations/" + device
    body = {"secret": "a" * 64, "token": "token_" + "a" * 40}
    assert app.test_client().put(path, json=body).status_code == 401
    assert call("owner", "PUT", path, body | {"user_id": "outsider"}).status_code == 400
    assert call("owner", "PUT", path, body).status_code == 200
    assert call("outsider", "PUT", path, body | {"secret": "b" * 64}).status_code == 409
    assert (
        call(
            "outsider",
            "POST",
            path + "/unregister",
            {"secret": "a" * 64, "binding": str(uuid.uuid4())},
        ).status_code
        == 404
    )
    assert call("owner", "PUT", "/v1/installations/" + "-" * 36, body).status_code == 400


def test_test_send_checks_home_owner_installation_and_configuration(environment):
    _, app, _, _, call = environment
    home = call("owner", "POST", "/v1/homes", {"name": "one"}).json["id"]
    device = str(uuid.uuid4())
    foreign = str(uuid.uuid4())
    body = {"secret": "a" * 64, "token": "token_" + "a" * 40}
    call("owner", "PUT", "/v1/installations/" + device, body)
    call("outsider", "PUT", "/v1/installations/" + foreign, body | {"token": "token_" + "b" * 40})
    path = f"/v1/homes/{home}/notifications/test"
    assert call("outsider", "POST", path, {"installation_id": foreign}).status_code == 404
    assert call("owner", "POST", path, {"installation_id": device}).status_code == 503
    app.config["PUSH_SENDER_READY"] = True
    assert call("owner", "POST", path, {"installation_id": foreign}).status_code == 409
    assert (
        call("owner", "POST", path, {"installation_id": device, "token": "arbitrary"}).status_code
        == 400
    )
    assert call("owner", "POST", path, {"installation_id": device}).status_code == 202
    assert call("owner", "POST", path, {"installation_id": device}).status_code == 429
