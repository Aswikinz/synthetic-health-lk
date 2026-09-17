"""Pinned local tools, explicit setup downloads and cancellable child processes."""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
from pathlib import Path

from .config import Config, bundled


class Cancelled(Exception):
    pass


class Control:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise Cancelled("Cancelled; partial output retained as incomplete")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checked(path: Path, expected: str) -> Path:
    if not path.is_file() or digest(path) != expected:
        raise ValueError(f"Missing or changed pinned artifact: {path}; run setup")
    return path


def java(config: Config) -> str:
    installed = os.environ.get("NEHR_JAVA") or shutil.which("java")
    if installed:
        return installed
    candidates = sorted((Path(config.tools) / "java").glob("**/bin/java.exe"))
    if candidates:
        return str(candidates[0])
    raise ValueError("Java 21 required for validation/simulation; run doctor after installation")


def tool(config: Config, name: str) -> Path:
    lock = read_json(bundled("tool-lock.json"))
    artifact = next(a for a in lock["artifacts"] if a["name"] == name)
    return checked(Path(config.tools) / name, artifact["sha256"])


def run_process(args: list[str], log: Path, control: Control, *, cwd=None, timeout=900) -> int:
    control.check()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT, cwd=cwd,
                                   start_new_session=os.name != "nt")
        started = time.monotonic()
        try:
            while process.poll() is None:
                control.check()
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Tool timed out after {timeout}s; see {log}")
                control.event.wait(0.1)
            return process.returncode
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def setup(config: Config, progress=print):
    destination = Path(config.tools)
    destination.mkdir(parents=True, exist_ok=True)
    lock = read_json(Path(config.ig_lock))
    artifacts = [dict(p, name=f"{p['id']}-{p['version']}.tgz") for p in lock["packages"]]
    artifacts += [a for a in read_json(bundled("tool-lock.json"))["artifacts"]
                  if a["name"].endswith(".jar")]
    for artifact in artifacts:
        path = destination / artifact["name"]
        if not path.exists():
            progress(f"Downloading {artifact['name']}")
            temporary = path.with_suffix(path.suffix + ".part")
            with urllib.request.urlopen(artifact["url"], timeout=180) as response:
                with temporary.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
            checked(temporary, artifact["sha256"])
            temporary.replace(path)
        checked(path, artifact["sha256"])
    prepare_packages(config)


def prepare_packages(config: Config) -> Path:
    """Alias dev to byte-identical reviewed packages without editing definitions."""
    tools = Path(config.tools)
    home = tools / "home"
    cache = home / ".fhir" / "packages"
    cache.mkdir(parents=True, exist_ok=True)
    lock = read_json(Path(config.ig_lock))
    for package in lock["packages"]:
        archive = checked(tools / f"{package['id']}-{package['version']}.tgz", package["sha256"])
        versions = [package["version"]]
        if package["id"] in lock["dev_resolution"]:
            versions.append("dev")
        for version in versions:
            target = cache / f"{package['id']}#{version}"
            marker = target / ".archive-sha256"
            if marker.exists() and marker.read_text() == package["sha256"]:
                continue
            target.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive) as stream:
                stream.extractall(target, filter="data")
            marker.write_text(package["sha256"])
    return home


def doctor(config: Config) -> dict:
    from .localize import fixtures

    findings = {}
    checks = {"fixtures": lambda: fixtures(config), "java": lambda: java(config),
              "validator": lambda: tool(config, "validator.jar"),
              "definitions": lambda: prepare_packages(config)}
    if config.preset == "outpatient":
        checks["synthea"] = lambda: tool(config, "synthea.jar")
    for name, check in checks.items():
        try:
            check()
            findings[name] = "available"
        except (OSError, ValueError) as error:
            findings[name] = str(error)
    output = Path(config.output)
    output.mkdir(parents=True, exist_ok=True)
    import tempfile

    with tempfile.TemporaryFile(dir=output):
        findings["output"] = "writable"
    findings["terminal"] = "interactive" if os.isatty(0) else "headless"
    findings["receiver_compatibility"] = "unconfirmed"
    return findings
