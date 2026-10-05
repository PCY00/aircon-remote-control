"""Connect the recovery helper build to the already downloaded official Android tools."""

import argparse
import json
from pathlib import Path


def prepare(source: Path, output: Path) -> None:
    tools = json.loads(source.read_text(encoding="utf-8-sig"))
    java = Path(tools["java_home"]) / "bin"
    sdk = Path(tools["sdk"])
    build = sdk / "build-tools/36.0.0"
    paths = {
        "java": java / "java.exe",
        "javac": java / "javac.exe",
        "keytool": java / "keytool.exe",
        "aapt": build / "aapt.exe",
        "zipalign": build / "zipalign.exe",
        "d8_jar": build / "lib/d8.jar",
        "apksigner_jar": build / "lib/apksigner.jar",
        "android_jar": sdk / "platforms/android-36/android.jar",
    }
    if not all(path.is_file() for path in paths.values()):
        raise RuntimeError("Official SDK/JDK files missing; run prepare_family_tools.py first")
    desired = {name: str(path.resolve()) for name, path in paths.items()}
    if output.exists():
        if json.loads(output.read_text(encoding="utf-8-sig")) != desired:
            raise RuntimeError(
                "Existing tool settings differ; preserve them and use --output for a new file"
            )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(desired, stream, indent=2)
            stream.write("\n")
    print("MANAGER_TOOLS_READY=TRUE FILES_PRESENT=8 PHONE_ACTION=NONE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(".deploy/family-app/tools.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("tmp/a50-build-tools/reader-paths.json")
    )
    args = parser.parse_args()
    prepare(args.source, args.output)


if __name__ == "__main__":
    main()
