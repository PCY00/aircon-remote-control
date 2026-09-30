"""Protocol-neutral parsing for ``ir-ctl`` mode2 pulse/space captures."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

HEADER_MIN_US = 3_000
BIT_SPLIT_US = 1_000
DATA_SPACE_MAX_US = 3_000


class IrParseError(ValueError):
    """Raised when a raw capture cannot be interpreted safely."""


@dataclass(frozen=True)
class ParsedFrame:
    """One decoded IR frame."""

    index: int
    bit_count: int
    bytes_hex: list[str]
    payload_hex: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "bit_count": self.bit_count,
            "bytes": self.bytes_hex,
            "payload_hex": self.payload_hex,
        }


def parse_compact_tokens(raw: str) -> list[int]:
    """Parse signed microsecond durations and enforce pulse/space alternation."""

    try:
        tokens = [int(item) for item in raw.split()]
    except ValueError as exc:
        raise IrParseError("capture contains a non-integer duration") from exc

    if not tokens:
        raise IrParseError("capture is empty")
    if tokens[0] <= 0:
        raise IrParseError("capture must start with a positive pulse")
    if any(token == 0 for token in tokens):
        raise IrParseError("capture contains a zero-duration token")
    if any((index % 2 == 0) != (token > 0) for index, token in enumerate(tokens)):
        raise IrParseError("capture does not alternate positive pulses and negative spaces")
    return tokens


def _frame_starts(tokens: list[int]) -> list[int]:
    starts = [0]
    for index in range(3, len(tokens) - 2, 2):
        if (
            abs(tokens[index]) >= HEADER_MIN_US
            and tokens[index + 1] >= HEADER_MIN_US
            and abs(tokens[index + 2]) >= HEADER_MIN_US
        ):
            starts.append(index + 1)
    return starts


def _bits_to_bytes(bits: list[int]) -> list[int]:
    result: list[int] = []
    for offset in range(0, len(bits), 8):
        value = 0
        for bit in bits[offset : offset + 8]:
            value = (value << 1) | bit
        result.append(value)
    return result


def _decode_frame(index: int, tokens: list[int]) -> ParsedFrame:
    if len(tokens) < 5:
        raise IrParseError(f"frame {index} is too short")
    if tokens[0] < HEADER_MIN_US or abs(tokens[1]) < HEADER_MIN_US:
        raise IrParseError(f"frame {index} has no recognizable leader")

    # A timeout-based capture can include the idle space after the final stop pulse.
    # It has no following pulse and therefore is not a data-bit space.
    frame_tokens = tokens[:-1] if len(tokens) % 2 == 0 else tokens
    data_spaces = [abs(frame_tokens[position]) for position in range(3, len(frame_tokens), 2)]
    bits = [int(duration >= BIT_SPLIT_US) for duration in data_spaces]
    if not bits or len(bits) % 8:
        raise IrParseError(f"frame {index} bit count is not a non-zero multiple of 8")

    values = _bits_to_bytes(bits)
    bytes_hex = [f"{value:02x}" for value in values]
    return ParsedFrame(
        index=index,
        bit_count=len(bits),
        bytes_hex=bytes_hex,
        payload_hex=" ".join(bytes_hex),
    )


def _median_or_none(values: list[int]) -> int | None:
    return round(median(values)) if values else None


def analyze_capture(raw: str) -> dict[str, object]:
    """Decode frames and expose timing facts without assuming a remote model."""

    tokens = parse_compact_tokens(raw)
    starts = _frame_starts(tokens)
    frames: list[ParsedFrame] = []
    interframe_gaps: list[int] = []

    for frame_index, start in enumerate(starts):
        if frame_index + 1 < len(starts):
            next_start = starts[frame_index + 1]
            end = next_start - 1
            interframe_gaps.append(abs(tokens[end]))
        else:
            end = len(tokens)
        frames.append(_decode_frame(frame_index, tokens[start:end]))

    pulses = [token for token in tokens[::2] if token < HEADER_MIN_US]
    spaces = [abs(token) for token in tokens[1::2]]
    short_spaces = [value for value in spaces if value < BIT_SPLIT_US]
    long_spaces = [value for value in spaces if BIT_SPLIT_US <= value < DATA_SPACE_MAX_US]
    payloads = [frame.payload_hex for frame in frames]
    first_bytes = [int(value, 16) for value in frames[0].bytes_hex]
    complement_pairs = [
        first_bytes[index] ^ first_bytes[index + 1] == 0xFF
        for index in range(0, len(first_bytes) - 1, 2)
    ]

    return {
        "format": "signed-microseconds-v1",
        "token_count": len(tokens),
        "frame_count": len(frames),
        "frames": [frame.to_dict() for frame in frames],
        "frames_identical": len(set(payloads)) == 1,
        "first_frame": {
            "payload_hex": frames[0].payload_hex,
            "byte_count": len(frames[0].bytes_hex),
            "complement_pairs": complement_pairs,
        },
        "timing_us": {
            "pulse_median": _median_or_none(pulses),
            "short_space_median": _median_or_none(short_spaces),
            "long_space_median": _median_or_none(long_spaces),
            "interframe_gaps": interframe_gaps,
        },
    }


def normalize_compact(raw: str) -> str:
    """Return a stable one-line representation suitable for exact replay later."""

    return " ".join(str(token) for token in parse_compact_tokens(raw)) + "\n"


def to_irctl_send_text(raw: str) -> str:
    """Convert signed durations to the text format accepted by ``ir-ctl --send``."""

    lines: list[str] = []
    for token in parse_compact_tokens(raw):
        kind = "pulse" if token > 0 else "space"
        lines.append(f"{kind} {abs(token)}")
    return "\n".join(lines) + "\n"
