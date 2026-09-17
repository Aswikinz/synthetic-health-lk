"""Explicitly selected real-tool tests: missing tools or online service failures fail."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from nehr_synth.config import load
from nehr_synth.mutate import mutate
from nehr_synth.pipeline import generate, open_run
from nehr_synth.runtime import read_json

pytestmark = pytest.mark.integration


@pytest.fixture
def real_config(tmp_path):
    tools = Path(os.environ.get("NEHR_TEST_TOOLS", ".tools")).resolve()
    assert (tools / "validator.jar").exists(), (
        "Run setup; integration tests never skip missing tools"
    )
    return load(patients=10, output=str(tmp_path), tools=str(tools))


def test_real_demographics_offline_and_negative_variants(real_config):
    config = replace(real_config, terminology="offline")
    path = generate(config)
    manifest, resources, _ = open_run(path)
    assert manifest["status"] == "passed", str(path / "validation.txt")
    assert manifest["counts"] == {"Patient": 10}
    assert manifest["validation"]["identifier_format"]["nic"] == "incomplete"
    for case in ("phn-bad-checksum", "gn-wrong-value-type", "address-missing-district"):
        variant = mutate(path, case)
        assert read_json(variant / "mutation.json")["result"] == "expected failure observed"
    assert open_run(path)[1] == resources


def test_real_demographics_online(real_config):
    path = generate(real_config)
    assert open_run(path)[0]["status"] == "passed", str(path / "validation.txt")


def test_real_synthea_online_reproducibility(real_config):
    config = replace(real_config, patients=1, preset="outpatient")
    first = generate(config)
    manifest, resources, _ = open_run(first)
    assert manifest["status"] == "passed", str(first / "validation.txt")
    assert manifest["counts"] == {
        "Patient": 1,
        "Encounter": 1,
        "Observation": 1,
        "Composition": 1,
        "Practitioner": 1,
    }
    second = generate(config)
    assert open_run(second)[0]["status"] == "passed"
    assert open_run(second)[1] == resources
    variant = mutate(first, "broken-patient-reference")
    assert read_json(variant / "mutation.json")["result"] == "expected failure observed"


def test_real_outpatient_offline_is_incomplete(real_config):
    path = generate(replace(real_config, patients=1, preset="outpatient", terminology="offline"))
    manifest, _, _ = open_run(path)
    assert manifest["status"] == "incomplete"
    assert any(
        "without terminology services" in i["message"] for i in manifest["validation"]["issues"]
    )
