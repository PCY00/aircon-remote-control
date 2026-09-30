"""Synthetic captures whose decoded bytes are easy to verify."""


def make_frame(payload: bytes) -> list[int]:
    tokens = [4_300, -4_300]
    for value in payload:
        for shift in range(7, -1, -1):
            tokens.append(560)
            tokens.append(-1_600 if value & (1 << shift) else -520)
    tokens.append(560)
    return tokens


def make_capture(payload: bytes = bytes.fromhex("b2 4d bf 40 20 df"), frames: int = 2) -> str:
    result: list[int] = []
    for index in range(frames):
        if index:
            result.append(-5_150)
        result.extend(make_frame(payload))
    return " ".join(str(token) for token in result)
