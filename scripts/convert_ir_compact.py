"""Convert ir-ctl compact receive output into pulse/space send format."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

TOKEN = re.compile(r"[+-]\d+")


def convert(source: Path, output: Path) -> None:
    tokens = TOKEN.findall(source.read_text(encoding="utf-8"))
    if not tokens:
        raise ValueError(f"No IR timing tokens found in {source}")

    expected_positive = True
    lines = ["# Generated from ir-ctl compact receive output."]
    for index, token in enumerate(tokens):
        value = int(token)
        if (value > 0) != expected_positive:
            raise ValueError(f"Unexpected sign at token {index}: {token}")
        lines.append(f"{'pulse' if value > 0 else 'space'} {abs(value)}")
        expected_positive = not expected_positive

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    convert(args.source, args.output)


if __name__ == "__main__":
    main()
