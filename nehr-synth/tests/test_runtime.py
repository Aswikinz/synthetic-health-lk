import io
import json
import tarfile
from pathlib import Path

import pytest

from nehr_synth.runtime import checked, digest, doctor, java, prepare_packages, setup, tool


def test_package_setup_integrity_and_dev_alias(config, monkeypatch, tmp_path):
    import nehr_synth.runtime as module

    destination = Path(config.tools)
    destination.mkdir()
    archive = destination / "fixture-0.1.0.tgz"
    content = json.dumps({"name": "fixture", "version": "0.1.0"}).encode()
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(content)
        stream.addfile(info, io.BytesIO(content))
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "id": "fixture",
                        "version": "0.1.0",
                        "url": "https://example.invalid/pkg",
                        "sha256": digest(archive),
                    }
                ],
                "dev_resolution": {"fixture": "0.1.0"},
                "bootstrap_resolution": {"fixture-alias": "fixture-0.1.0"},
            }
        )
    )
    config.ig_lock = str(lock)
    tools_lock = tmp_path / "tools.json"
    tools_lock.write_text('{"artifacts": []}')
    monkeypatch.setattr(module, "bundled", lambda _: tools_lock)
    setup(config)
    home = prepare_packages(config)
    assert (home / ".fhir/packages/fixture#dev/package/package.json").read_bytes() == content
    assert (destination / "bootstrap/fixture-alias").read_bytes() == archive.read_bytes()
    cached = home / ".fhir/packages/fixture#dev/package/package.json"
    cached.write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        prepare_packages(config)
    cached.write_bytes(content)
    archive.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="changed"):
        prepare_packages(config)
    with pytest.raises(ValueError):
        checked(tmp_path / "absent", "0" * 64)


def test_setup_download_checksum_gate(config, tmp_path, monkeypatch):
    import nehr_synth.runtime as module

    lock = tmp_path / "lock.json"
    lock.write_text(
        '{"packages": [{"id":"fixture","version":"1","url":"https://example.invalid", '
        '"sha256":"wrong"}], "dev_resolution": {}, "bootstrap_resolution": {}}'
    )
    tool_lock = tmp_path / "tool.json"
    tool_lock.write_text('{"artifacts": []}')
    config.ig_lock = str(lock)
    monkeypatch.setattr(module, "bundled", lambda _: tool_lock)
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"not trusted")
    )
    with pytest.raises(ValueError, match="changed"):
        setup(config)
    assert not (Path(config.tools) / "fixture-1.tgz").exists()


def test_java_and_selected_workflow(config, monkeypatch):
    import nehr_synth.runtime as module

    monkeypatch.setenv("NEHR_JAVA", "pinned-java")
    assert java(config) == "pinned-java"
    monkeypatch.delenv("NEHR_JAVA")
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="Java 21"):
        java(config)
    executable = Path(config.tools) / "java/runtime/bin/java.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert java(config) == str(executable)
    findings = doctor(config)
    assert "synthea" not in findings
    config.preset = "outpatient"
    assert "synthea" in doctor(config)
    with pytest.raises(ValueError, match="artifact"):
        tool(config, "synthea.jar")
