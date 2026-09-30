import pytest

from app.ir.parser import IrParseError, analyze_capture, normalize_compact, to_irctl_send_text
from app.ir.profiles import Carrier1621415597Profile
from tests.ir_samples import make_capture


def test_analyzes_two_identical_48_bit_frames() -> None:
    analysis = analyze_capture(make_capture())

    assert analysis["token_count"] == 199
    assert analysis["frame_count"] == 2
    assert analysis["frames_identical"] is True
    assert analysis["first_frame"] == {
        "payload_hex": "b2 4d bf 40 20 df",
        "byte_count": 6,
        "complement_pairs": [True, True, True],
    }
    assert analysis["timing_us"] == {
        "pulse_median": 560,
        "short_space_median": 520,
        "long_space_median": 1600,
        "interframe_gaps": [5150],
    }


def test_accepts_a_single_frame() -> None:
    analysis = analyze_capture(make_capture(frames=1))

    assert analysis["token_count"] == 99
    assert analysis["frame_count"] == 1
    assert analysis["frames_identical"] is True


def test_ignores_idle_space_after_the_final_stop_pulse() -> None:
    raw = make_capture() + " -17146"

    analysis = analyze_capture(raw)

    assert analysis["frame_count"] == 2
    assert analysis["first_frame"]["payload_hex"] == "b2 4d bf 40 20 df"


def test_carrier_profile_rejects_non_48_bit_packet() -> None:
    with pytest.raises(IrParseError, match="48 bits"):
        Carrier1621415597Profile().analyze(make_capture(bytes.fromhex("aa 55"), frames=1))


@pytest.mark.parametrize("raw", ["", "-500 500", "500 500", "500 0"])
def test_rejects_invalid_compact_capture(raw: str) -> None:
    with pytest.raises(IrParseError):
        analyze_capture(raw)


def test_generates_stable_replay_files() -> None:
    raw = "4300 -4300 560 -520 560"

    assert normalize_compact(raw) == raw + "\n"
    assert to_irctl_send_text(raw) == (
        "pulse 4300\nspace 4300\npulse 560\nspace 520\npulse 560\n"
    )
