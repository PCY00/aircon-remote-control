from __future__ import annotations

import pytest

from scripts.install_h2_zigbee_converter import enable_external_js


def test_adds_setting_without_changing_secret_or_other_keys() -> None:
    source = (
        b"advanced:\n  network_key: '!secret.yaml network_key'\n"
        b"  channel: 20\nfrontend:\n  enabled: true\n"
    )

    updated, action = enable_external_js(source)

    assert action == "added"
    assert updated == source.replace(
        b"advanced:\n", b"advanced:\n  enable_external_js: true\n", 1
    )


def test_replaces_false_and_leaves_true_unchanged() -> None:
    source = b"advanced:\n  enable_external_js: false\n  channel: 20\n"

    updated, action = enable_external_js(source)

    assert action == "false-to-true"
    assert b"enable_external_js: true" in updated
    assert enable_external_js(updated) == (updated, "already-enabled")


@pytest.mark.parametrize(
    "source",
    [
        b"frontend:\n  enabled: true\n",
        b"advanced:\n  enable_external_js: false\n  enable_external_js: true\n",
        b"advanced:\n  enable_external_js: maybe\n",
    ],
)
def test_rejects_ambiguous_config(source: bytes) -> None:
    with pytest.raises(ValueError):
        enable_external_js(source)
