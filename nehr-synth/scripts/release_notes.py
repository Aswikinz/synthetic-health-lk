"""Produce version-checked release notes and distribution checksums."""

import hashlib
import json
import sys
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
assert sys.argv[1] == "v" + version, "Tag must match the packaged version"
tools = json.loads((root / "tool-lock.json").read_text())
lock_hash = hashlib.sha256((root / "ig-lock.json").read_bytes()).hexdigest()
dist = root / "dist"
(dist / "RELEASE.md").write_text(
    f"nehr-synth {version}\n\n"
    f"Synthea {tools['synthea']}; HL7 Validator {tools['validator']}; Java {tools['java']}.\n"
    "FHIR R4 4.0.1, fhir.lk.nehr 0.1.0; receiver compatibility unconfirmed.\n"
    f"IG lock SHA-256: `{lock_hash}`.\n\n"
    "NICs are structural fixtures. Diagnosis export is disabled. "
    "See README and RESEARCH for profile coverage, limitations and platform evidence.\n",
    encoding="utf-8",
)
(dist / "SHA256SUMS").write_text(
    "\n".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
        for p in sorted(dist.iterdir())
        if p.is_file() and p.name != "SHA256SUMS"
    )
    + "\n"
)
