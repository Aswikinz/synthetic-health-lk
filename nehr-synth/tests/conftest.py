import pytest

from nehr_synth.config import load
from nehr_synth.pipeline import generate
from nehr_synth.runtime import write_json
from nehr_synth.validate import application_checks


@pytest.fixture
def config(tmp_path):
    return load(patients=3, output=str(tmp_path / "runs"), tools=str(tmp_path / "tools"))


@pytest.fixture
def fake_validator(monkeypatch):
    """Only unit tests use this; integration tests require the real Java validator."""

    def validate(resources, assignments, config, directory, control):
        control.check()
        issues = application_checks(resources, config, assignments)
        for resource in resources:
            if resource["resourceType"] == "Patient":
                address = resource["address"][0]
                if "district" not in address:
                    issues.append(
                        {
                            "layer": "ig",
                            "severity": "error",
                            "resource": resource["id"],
                            "path": "address[0].district",
                            "message": "Required",
                        }
                    )
                if any("valueString" in e for e in address.get("extension", [])):
                    issues.append(
                        {
                            "layer": "ig",
                            "severity": "error",
                            "resource": resource["id"],
                            "path": "address[0].extension[0].value[x]",
                            "message": "Wrong type",
                        }
                    )
        result = {
            "status": "failed" if issues else "passed",
            "ig": "failed" if issues else "passed",
            "issues": issues,
        }
        write_json(directory / "validation.json", result)
        return result

    monkeypatch.setattr("nehr_synth.pipeline.validate_graph", validate)
    monkeypatch.setattr("nehr_synth.mutate.validate_graph", validate)
    return validate


@pytest.fixture
def positive(config, fake_validator):
    return generate(config)
