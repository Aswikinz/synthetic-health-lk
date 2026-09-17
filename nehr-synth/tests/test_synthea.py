import copy
from dataclasses import replace

import pytest

from nehr_synth.localize import demographics
from nehr_synth.pipeline import generate, open_run
from nehr_synth.runtime import Control, write_json
from nehr_synth.synthea import map_graph, outpatient, select_graph


@pytest.fixture
def source(config):
    patient = demographics(config)[0][0]
    encounter = {
        "resourceType": "Encounter",
        "id": "enc1",
        "class": {"code": "AMB", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
        "status": "finished",
        "period": {"start": "2025-02-01T09:00:00Z", "end": "2025-02-01T09:15:00Z"},
    }
    observation = {
        "resourceType": "Observation",
        "id": "obs1",
        "status": "final",
        "encounter": {"reference": "urn:uuid:enc1"},
        "code": {"coding": [{"system": "http://loinc.org", "code": "2345-7"}]},
        "valueQuantity": {"system": "http://unitsofmeasure.org", "code": "mg/dL", "value": 92},
        "effectiveDateTime": "2025-02-01T09:00:00Z",
    }
    return patient, encounter, observation


def test_selection_mapping_and_required_code_gate(config, source):
    bundle = {"entry": [{"resource": r} for r in source]}
    assert select_graph(bundle) == source
    mapped = map_graph(config, source[0], source, 0)
    assert [r["resourceType"] for r in mapped] == ["Encounter", "Observation", "Composition"]
    assert mapped[1]["valueQuantity"] == source[2]["valueQuantity"]
    assert mapped[2]["section"][0]["title"] == "Encounter Output"
    source[2]["valueQuantity"]["code"] = "mmol/L"
    with pytest.raises(ValueError, match="Unmapped"):
        map_graph(config, source[0], source, 0)
    source[2]["valueQuantity"]["code"] = "mg/dL"
    source[2]["valueQuantity"]["value"] = "text"
    with pytest.raises(ValueError, match="numeric"):
        map_graph(config, source[0], source, 0)
    source[1]["diagnosis"] = [{"condition": {"reference": "Condition/a"}}]
    assert select_graph(bundle) is None
    assert select_graph({}) is None


def test_outpatient_batch_pipeline(config, source, monkeypatch, fake_validator):
    import nehr_synth.synthea as module

    config.preset = "outpatient"
    monkeypatch.setattr(module, "java", lambda c: "java")
    monkeypatch.setattr(module, "tool", lambda c, n: n)

    def execute(args, log, control):
        from pathlib import Path

        path = (
            Path(
                next(a.split("=", 1)[1] for a in args if a.startswith("--exporter.baseDirectory="))
            )
            / "fhir"
        )
        path.mkdir(parents=True)
        for i in range(config.patients):
            write_json(
                path / f"{i}.json", {"entry": [{"resource": r} for r in copy.deepcopy(source)]}
            )
        return 0

    monkeypatch.setattr(module, "run_process", execute)
    manifest, resources, _ = open_run(generate(config))
    assert manifest["counts"] == {
        "Patient": 3,
        "Practitioner": 1,
        "Encounter": 3,
        "Observation": 3,
        "Composition": 3,
    }
    assert manifest["generated_candidates"] == 3
    assert manifest["status"] == "passed"
    assert len(manifest["simulation_batches"]) == 1


def test_bounded_shortfall_and_tool_failure(config, tmp_path, monkeypatch):
    import nehr_synth.synthea as module

    monkeypatch.setattr(module, "java", lambda c: "java")
    monkeypatch.setattr(module, "tool", lambda c, n: n)
    for code in [0, 1]:
        monkeypatch.setattr(module, "run_process", lambda *args, code=code: code)
        stage = tmp_path / str(code)
        stage.mkdir()
        with pytest.raises(ValueError, match="shortfall" if code == 0 else "exited"):
            outpatient(config, stage, Control(), lambda _: None)
    with pytest.raises(ValueError, match="adults"):
        outpatient(replace(config, nic=False, age_min=1), tmp_path, Control(), print)
