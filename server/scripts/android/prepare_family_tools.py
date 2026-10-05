"""Download checksum-verified official Android/Gradle tools into a private local cache."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from a50_record import PhoneSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--java-home",
        type=Path,
        help="JDK 17 home; defaults to JAVA_HOME or the earlier management build configuration",
    )
    args = parser.parse_args()
    record = PhoneSession("family-build-tools")
    java_home = args.java_home
    if java_home is None and os.environ.get("JAVA_HOME"):
        java_home = Path(os.environ["JAVA_HOME"])
    if java_home is None:
        previous = Path("tmp/a50-build-tools/paths.json")
        if not previous.exists():
            raise RuntimeError("Install JDK 17 and pass --java-home or set JAVA_HOME")
        java_home = Path(json.loads(previous.read_text())["java"]).parent.parent
    java_home = java_home.resolve()
    version = subprocess.run(
        [str(java_home / "bin/java.exe"), "-version"], capture_output=True, text=True, check=True
    )
    if not re.search(r'version "17\.', version.stderr + version.stdout):
        raise RuntimeError("JDK 17 is required")
    record.log("JDK_17_VERSION_CHECK=PASS")
    root = Path.home() / ".codex/family-android-tools"
    root.mkdir(parents=True, exist_ok=True)
    sdk = root / "sdk"
    sdk.mkdir(exist_ok=True)
    xml = ET.fromstring(
        urllib.request.urlopen(
            "https://dl.google.com/android/repository/repository2-3.xml", timeout=30
        ).read()
    )
    for package, destination in [
        ("platforms;android-36", sdk / "platforms/android-36"),
        ("build-tools;36.0.0", sdk / "build-tools/36.0.0"),
        ("platform-tools", sdk / "platform-tools"),
    ]:
        if destination.exists():
            record.log("CACHED_OFFICIAL_PACKAGE=" + package)
            continue
        node = next(p for p in xml.iter("remotePackage") if p.attrib["path"] == package)
        archive = next(
            a for a in node.iter("archive") if a.findtext("host-os") in (None, "windows")
        )
        complete = archive.find("complete")
        url = "https://dl.google.com/android/repository/" + complete.findtext("url")
        data = urllib.request.urlopen(url, timeout=120).read()
        assert hashlib.sha1(data).hexdigest() == complete.findtext("checksum")
        path = root / (package.replace(";", "-") + ".zip")
        path.write_bytes(data)
        stage = root / (package.replace(";", "-") + "-extract")
        stage.mkdir(exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(stage)
        children = [p for p in stage.iterdir() if p.is_dir()]
        assert len(children) == 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        children[0].rename(destination)
        record.log("OFFICIAL_DOWNLOAD_AND_REPOSITORY_CHECKSUM=PASS PACKAGE=" + package)
    licenses = sdk / "licenses"
    licenses.mkdir(exist_ok=True)
    # Preserve Google's canonical license text hashes in the local SDK cache.
    for license_node in xml.iter("license"):
        value = hashlib.sha1((license_node.text or "").strip().encode()).hexdigest()
        (licenses / license_node.attrib["id"]).write_text(value + "\n")
    gradle = root / "gradle-8.13"
    if not gradle.exists():
        url = "https://services.gradle.org/distributions/gradle-8.13-bin.zip"
        expected = urllib.request.urlopen(url + ".sha256", timeout=30).read().decode().strip()
        data = urllib.request.urlopen(url, timeout=120).read()
        assert hashlib.sha256(data).hexdigest() == expected
        path = root / "gradle.zip"
        path.write_bytes(data)
        with zipfile.ZipFile(path) as z:
            z.extractall(root)
        record.log("OFFICIAL_GRADLE_8_13_SHA256=PASS")
    private = Path(".deploy/family-app")
    private.mkdir(parents=True, exist_ok=True)
    (private / "tools.json").write_text(
        json.dumps({"sdk": str(sdk), "gradle": str(gradle), "java_home": str(java_home)}, indent=2)
    )
    record.log("FAMILY_ANDROID_TOOLS_READY=PASS SDK=36 BUILD_TOOLS=36.0.0 GRADLE=8.13 JDK=17")


if __name__ == "__main__":
    main()
