"""Build the small Android recovery helper with portable official SDK tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, default=Path("tmp/a50-build-tools/paths.json"))
    parser.add_argument("--output", type=Path, default=Path("tmp/a50-manager-build"))
    args = parser.parse_args()
    paths = json.loads(args.tools.read_text(encoding="utf-8"))
    source = Path("android/a50-manager").resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    compilation = Path(tempfile.mkdtemp(prefix="compile-", dir=output))
    classes = compilation / "classes"
    dex = compilation / "dex"
    classes.mkdir(exist_ok=True)
    dex.mkdir(exist_ok=True)
    packaging = Path(tempfile.mkdtemp(prefix="aircon-a50-manager-"))
    if not str(packaging).isascii():
        raise RuntimeError("aapt requires an ASCII staging path on Windows.")
    shutil.copyfile(source / "AndroidManifest.xml", packaging / "AndroidManifest.xml")
    shutil.copyfile(paths["android_jar"], packaging / "android.jar")
    shutil.copytree(source / "res", packaging / "res", dirs_exist_ok=True)
    private = Path.home() / ".codex/device-keys"
    private.mkdir(parents=True, exist_ok=True)
    key = private / "a50-manager.p12"
    password = private / "a50-manager-password.txt"
    records = []

    def run(command: list[str], label: str) -> None:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90
        )
        text = result.stdout + result.stderr
        text = text.replace(str(Path.cwd()), "[LOCAL_PROJECT]")
        text = text.replace(str(private), "[PRIVATE_SIGNING_DIRECTORY]")
        text = text.replace(str(Path.home()), "[REDACTED_LOCAL_HOME]")
        records.append(f"$ {label}\n{text}EXIT_CODE={result.returncode}\n")
        print(label + ": EXIT_CODE=" + str(result.returncode), flush=True)
        if result.returncode:
            raise RuntimeError(text)

    try:
        java_files = [str(path) for path in sorted((source / "src").rglob("*.java"))]
        run(
            [
                paths["javac"],
                "-encoding",
                "UTF-8",
                "-source",
                "8",
                "-target",
                "8",
                "-bootclasspath",
                paths["android_jar"],
                "-d",
                str(classes),
                *java_files,
            ],
            "javac [Android API 30, Java 8 bytecode, local source files]",
        )
        run(
            [
                paths["java"],
                "-cp",
                paths["d8_jar"],
                "com.android.tools.r8.D8",
                "--lib",
                paths["android_jar"],
                "--min-api",
                "26",
                "--output",
                str(dex),
                *[str(path) for path in sorted(classes.rglob("*.class"))],
            ],
            "D8 [compile DEX]",
        )
        unsigned = packaging / "unsigned.apk"
        run(
            [
                paths["aapt"],
                "package",
                "-f",
                "-M",
                str(packaging / "AndroidManifest.xml"),
                "-S",
                str(packaging / "res"),
                "-I",
                str(packaging / "android.jar"),
                "-F",
                str(unsigned),
            ],
            "aapt [package manifest in ASCII staging]",
        )
        with zipfile.ZipFile(unsigned, "a") as archive:
            archive.write(dex / "classes.dex", "classes.dex")
        aligned = packaging / "aligned.apk"
        run([paths["zipalign"], "-f", "4", str(unsigned), str(aligned)], "zipalign [align APK]")
        if not key.exists():
            if password.exists():
                raise RuntimeError("Signing password exists without key; preserve and investigate.")
            password.write_text(secrets.token_urlsafe(32), encoding="utf-8")
            run(
                [
                    paths["keytool"],
                    "-genkeypair",
                    "-keystore",
                    str(key),
                    "-storetype",
                    "PKCS12",
                    "-storepass:file",
                    str(password),
                    "-alias",
                    "a50-manager",
                    "-keyalg",
                    "RSA",
                    "-keysize",
                    "2048",
                    "-validity",
                    "3650",
                    "-dname",
                    "CN=A50 Server Management",
                ],
                "keytool [dedicated signing key outside repository]",
            )
        if not password.is_file():
            raise RuntimeError("Signing password file is missing; no key was replaced.")
        apk = packaging / "a50-manager.apk"
        run(
            [
                paths["java"],
                "-jar",
                paths["apksigner_jar"],
                "sign",
                "--ks",
                str(key),
                "--ks-key-alias",
                "a50-manager",
                "--ks-pass",
                f"file:{password}",
                "--out",
                str(apk),
                str(aligned),
            ],
            "apksigner [sign with dedicated private key]",
        )
        run(
            [paths["java"], "-jar", paths["apksigner_jar"], "verify", "--verbose", str(apk)],
            "apksigner verify --verbose [built APK]",
        )
        run([paths["aapt"], "dump", "permissions", str(apk)], "aapt dump permissions [built APK]")
        shutil.copyfile(apk, output / "a50-manager.apk")
        digest = hashlib.sha256(apk.read_bytes()).hexdigest()
        (output / "build.json").write_text(
            json.dumps(
                {
                    "apk_sha256": digest,
                    "classes_path": str(classes),
                    "apk_path": str(output / "a50-manager.apk"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        records.append(f"APK_BYTES={apk.stat().st_size}\nAPK_SHA256={digest}\n")
        print(f"SIGNED_APK_READY BYTES={apk.stat().st_size}", flush=True)
        return 0
    finally:
        directory = Path("docs/assets/terminal")
        number = max(int(path.name.split("-")[0]) for path in directory.glob("*.txt")) + 1
        (directory / f"{number:02d}-a50-manager-apk-build.txt").write_text(
            "# Actual A50 recovery helper build and signature verification\n"
            "# Dedicated signing key and password stored outside repository\n\n"
            + "\n".join(records),
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
