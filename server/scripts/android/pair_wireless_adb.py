"""Pair Android Wi-Fi ADB using a local masked prompt, with sanitized records."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog


def validate_endpoint(value: str) -> str:
    try:
        address, port = value.rsplit(":", 1)
        parsed_address = ipaddress.IPv4Address(address)
        parsed_port = int(port)
    except (ValueError, ipaddress.AddressValueError) as error:
        raise argparse.ArgumentTypeError("Use an IPv4 address and port.") from error
    if not parsed_address.is_private or parsed_address.is_unspecified or parsed_address.is_loopback:
        raise argparse.ArgumentTypeError("Use the phone's private Wi-Fi address.")
    if not 1 <= parsed_port <= 65535:
        raise argparse.ArgumentTypeError("Invalid pairing port.")
    return f"{parsed_address}:{parsed_port}"


def redact_output(value: str, endpoint: str, code: str) -> str:
    value = value.replace(code, "[REDACTED_PAIRING_CODE]")
    value = value.replace(endpoint, "[REDACTED_PAIRING_ENDPOINT]")
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[REDACTED_ADDRESS]", value)
    value = re.sub(r"(?i)(guid\s*[=:]\s*)[^\s)]+", r"\1[REDACTED_DEVICE_ID]", value)
    value = re.sub(r"(?i)\b(?:adb-)[A-Za-z0-9_.-]+", "[REDACTED_DEVICE_ID]", value)
    return value


def write_transcript(directory: Path, contents: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    numbers = [
        int(match.group(1))
        for path in directory.glob("*.txt")
        if (match := re.match(r"^(\d+)-", path.name))
    ]
    number = max(numbers, default=0) + 1
    while True:
        path = directory / f"{number:02d}-a50-wireless-adb-pairing.txt"
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(contents)
            return path
        except FileExistsError:
            number += 1


def write_result(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=validate_endpoint)
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--transcript-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.adb.is_file():
        parser.error("The portable adb executable was not found.")

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    code = simpledialog.askstring(
        "A50 무선 연결",
        "휴대폰의 페어링 창을 열어둔 상태에서\n"
        "6자리 Wi-Fi 페어링 코드를 입력하세요.\n\n"
        f"대상: {args.endpoint}\n\n"
        "코드는 채팅·파일·명령 인자에 저장하지 않습니다.",
        show="*",
        parent=root,
    )
    if code is None:
        write_result(args.result, {"status": "cancelled", "command_executed": False})
        root.destroy()
        return 2
    code = code.strip()
    if not re.fullmatch(r"[0-9]{6}", code):
        write_result(args.result, {"status": "invalid_code", "command_executed": False})
        messagebox.showerror(
            "A50 무선 연결", "휴대폰에 표시된 숫자 6자리를 입력해야 합니다.", parent=root
        )
        root.destroy()
        return 2

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [str(args.adb.resolve()), "pair", args.endpoint],
            input=code + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=flags,
            check=False,
        )
        output = redact_output(completed.stdout, args.endpoint, code)
        success = completed.returncode == 0 and "Successfully paired" in completed.stdout
        status = "paired" if success else "failed"
        returncode: int | None = completed.returncode
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or b""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        output = redact_output(partial, args.endpoint, code) + "\nPAIRING_TIMEOUT_SECONDS=30\n"
        status = "timeout"
        returncode = None
    except OSError:
        output = "ADB_PROCESS_START_FAILED\n"
        status = "process_error"
        returncode = None

    code = ""
    transcript = write_transcript(
        args.transcript_dir,
        "# Actual Wi-Fi ADB pairing attempt; identifiers removed\n"
        "# Pairing code entered in a private local prompt, passed through stdin\n\n"
        "$ adb pair [REDACTED_PHONE_IP]:[REDACTED_PAIR_PORT]\n"
        + output.rstrip()
        + f"\n\nPAIRING_STATUS={status}\nPROCESS_EXIT_CODE={returncode}\n",
    )
    write_result(
        args.result,
        {"status": status, "returncode": returncode, "transcript_name": transcript.name},
    )
    if status == "paired":
        messagebox.showinfo(
            "A50 무선 연결",
            "페어링이 완료됐습니다. 채팅에서 다음 연결 확인을 진행합니다.",
            parent=root,
        )
    else:
        messagebox.showerror(
            "A50 무선 연결",
            "페어링을 완료하지 못했습니다. 코드는 채팅에 보내지 말고,\n"
            "채팅에서 다음 안내를 확인하세요.",
            parent=root,
        )
    root.destroy()
    return 0 if status == "paired" else 1


if __name__ == "__main__":
    raise SystemExit(main())
