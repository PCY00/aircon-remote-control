"""The web-config tool accepts only a well-formed console snippet; values are built at runtime."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts/android"))
from set_a50_web_config import HOST, parse  # noqa: E402

KEY = "AIza" + "Fixture_" * 4 + "abc"  # 35 characters after the prefix, fictional


def snippet(**changes):
    values = dict(apiKey=KEY, authDomain="example-family.firebaseapp.com", projectId="example-family",
                  storageBucket="example-family.appspot.com", messagingSenderId="123456789012",
                  appId="1:123456789012:web:0123456789abcdef")
    values.update(changes)
    body = ",\n  ".join(f'{k}: "{v}"' for k, v in values.items() if v is not None)
    return "const firebaseConfig = {\n  " + body + "\n};"


def test_console_snippet_and_json_both_parse():
    expected = {"api_key": KEY, "app_id": "1:123456789012:web:0123456789abcdef",
                "messaging_sender_id": "123456789012", "project_id": "example-family"}
    assert parse(snippet()) == expected
    json_text = '{"apiKey": "%s", "appId": "1:123456789012:web:0123456789abcdef", ' \
                '"messagingSenderId": "123456789012", "projectId": "example-family"}' % KEY
    assert parse(json_text) == expected


@pytest.mark.parametrize("changes", [
    {"apiKey": None}, {"apiKey": "AIzaShort"}, {"appId": "1:123:android:abc"},
    {"messagingSenderId": "12ab"}, {"projectId": "Bad_Project"},
])
def test_missing_or_malformed_fields_are_refused(changes):
    with pytest.raises(ValueError):
        parse(snippet(**changes))


def test_conflicting_duplicate_values_are_refused():
    with pytest.raises(ValueError):
        parse(snippet() + '\nappId: "1:123456789012:web:ffffffffffffffff"')


def test_auth_domain_must_be_a_bare_hostname():
    assert HOST.fullmatch("roomrelay.top")
    for bad in ("https://roomrelay.top", "roomrelay.top/app", "localhost", "a..b.top"):
        assert not HOST.fullmatch(bad)
