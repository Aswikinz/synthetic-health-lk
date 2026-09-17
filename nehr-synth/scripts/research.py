"""One-off artifact inspection; setup uses the reviewed lock instead."""

import concurrent.futures
import hashlib
import json
import pathlib
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / ".tools"
CACHE.mkdir(exist_ok=True)
PACKAGES = {
    "fhir.lk.clientregistry": ("0.1.0", "https://ig.hiu.lk/fhir/clientregistry/package.tgz"),
    "fhir.lk.nehr": ("0.1.0", "https://ig.hiu.lk/fhir/nehr/package.tgz"),
    "fhir.lk.providerregistry": ("0.1.0", "https://ig.hiu.lk/fhir/providerregistry/package.tgz"),
    "fhir.lk.facilityregistry": ("0.1.0", "https://ig.hiu.lk/fhir/facilityregistry/package.tgz"),
    "hl7.fhir.r4.core": ("4.0.1", "https://packages.fhir.org/hl7.fhir.r4.core/4.0.1"),
    "hl7.terminology.r4": ("6.5.0", "https://packages.fhir.org/hl7.terminology.r4/6.5.0"),
    "hl7.fhir.uv.extensions.r4": (
        "5.2.0",
        "https://packages.fhir.org/hl7.fhir.uv.extensions.r4/5.2.0",
    ),
}


def fetch(item):
    name, (version, url) = item
    path = CACHE / f"{name}-{version}.tgz"
    if not path.exists():
        with urllib.request.urlopen(url, timeout=180) as response:
            path.write_bytes(response.read())
    with tarfile.open(path) as archive:
        metadata = json.load(archive.extractfile("package/package.json"))
    return {
        "id": name,
        "version": version,
        "url": url,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dependencies": metadata.get("dependencies", {}),
    }


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        packages = list(pool.map(fetch, PACKAGES.items()))
    lock = {
        "schema_version": 1,
        "reviewed": "2026-09-17",
        "fhir": "4.0.1",
        "receiver_compatibility": "unconfirmed",
        "packages": packages,
        "dev_resolution": {k: "0.1.0" for k in PACKAGES if k.startswith("fhir.lk.")},
    }
    (ROOT / "ig-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    print(json.dumps(lock, indent=2))
