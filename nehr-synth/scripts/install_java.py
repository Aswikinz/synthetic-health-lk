"""Image-build only: install the checksum-pinned JRE for this architecture."""

import json
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from nehr_synth.runtime import checked

root = Path(__file__).resolve().parents[1]
architecture = {"x86_64": "x64", "aarch64": "aarch64"}[platform.machine()]
artifact = next(
    a
    for a in json.loads((root / "tool-lock.json").read_text())["artifacts"]
    if a["name"] == f"java-{architecture}.tar.gz"
)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "java.tar.gz"
    with urllib.request.urlopen(artifact["url"], timeout=180) as response:
        with path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    checked(path, artifact["sha256"])
    with tarfile.open(path) as archive:
        archive.extractall(Path(directory) / "extracted", filter="data")
    shutil.copytree(next((Path(directory) / "extracted").iterdir()), sys.argv[1])
