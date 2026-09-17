import copy
import sys
import threading
from dataclasses import replace

import pytest

from nehr_synth.__main__ import main
from nehr_synth.config import save
from nehr_synth.localize import demographics
from nehr_synth.mutate import mutate
from nehr_synth.pipeline import export_run, generate, open_run, revalidate
from nehr_synth.runtime import Cancelled, Control, digest, read_json, run_process, write_json
from nehr_synth.validate import outcome_issues, validate_graph


def test_export_and_saved_run(positive, tmp_path):
    manifest, resources, config = open_run(positive)
    assert manifest["counts"] == {"Patient": 3}
    assert manifest["identifier_counts"] == {"nic": 3, "phn": 3, "passport": 3}
    target = export_run(positive, tmp_path / "export")
    assert open_run(target)[:2] == (manifest, resources)
    with pytest.raises(ValueError, match="already exists"):
        export_run(positive, target)
    with pytest.raises(ValueError, match="outside"):
        export_run(positive, positive / "inside")
    assert revalidate(positive)["status"] == "passed"
    assert len(list((positive / "checks").iterdir())) == 1


@pytest.mark.parametrize("fault", ["bytes", "counts", "path", "id", "references"])
def test_tampered_export_rejected(positive, fault):
    manifest = read_json(positive / "manifest.json")
    entry = manifest["resources"][0]
    if fault == "bytes":
        (positive / entry["file"]).write_text("{}")
    elif fault == "counts":
        manifest["counts"]["Patient"] += 1
    elif fault == "path":
        entry["file"] = "../../outside.json"
    elif fault == "id":
        entry["id"] = "wrong"
    else:
        entry["dependencies"] = ["Patient/absent"]
    write_json(positive / "manifest.json", manifest)
    with pytest.raises(ValueError):
        open_run(positive)


def test_generation_without_java_is_incomplete(config):
    path = generate(config)
    manifest, resources, _ = open_run(path)
    assert len(resources) == 3
    assert manifest["status"] == "incomplete"
    assert manifest["validation"]["ig"] == "incomplete"
    assert "incomplete" in path.parts


def test_cancelled_generation_retains_diagnostics(config):
    control = Control()
    control.cancel()
    path = generate(config, control=control)
    manifest = read_json(path / "manifest.json")
    assert manifest["status"] == "incomplete"
    assert "Cancelled" in manifest["error"]
    assert not list(path.parent.parent.glob(".staging*"))


def test_bad_input_retains_error(config):
    path = generate(replace(config, names="missing-names.json"))
    assert read_json(path / "manifest.json")["execution_error"]


@pytest.mark.parametrize(
    "case", ["phn-bad-checksum", "gn-wrong-value-type", "address-missing-district"]
)
def test_single_mutation_preserves_baseline(positive, case):
    before = digest(positive / "manifest.json")
    path = mutate(positive, case)
    report = read_json(path / "mutation.json")
    assert report["result"] == "expected failure observed"
    assert report["baseline_sha256"] == before == digest(positive / "manifest.json")
    assert len(report["changed_paths"]) == 1
    assert open_run(positive)[0]["counts"]["Patient"] == 3
    with pytest.raises(FileExistsError):
        mutate(positive, case)


def test_mutation_requires_suitable_baseline(config, positive):
    with pytest.raises(ValueError, match="disabled"):
        mutate(positive, "nic-dob-mismatch")
    with pytest.raises(ValueError, match="clinical"):
        mutate(positive, "broken-patient-reference")
    m = read_json(positive / "manifest.json")
    m["status"] = "incomplete"
    write_json(positive / "manifest.json", m)
    with pytest.raises(ValueError, match="positive baseline"):
        mutate(positive, "phn-bad-checksum")


def test_real_subprocess_cancel_and_timeout(tmp_path):
    control = Control()
    timer = threading.Timer(0.2, control.cancel)
    timer.start()
    with pytest.raises(Cancelled):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path / "cancel.log", control
        )
    timer.join()
    with pytest.raises(TimeoutError):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "timeout.log",
            Control(),
            timeout=0.1,
        )
    assert run_process([sys.executable, "-c", "print('done')"], tmp_path / "ok.log", Control()) == 0
    assert (tmp_path / "ok.log").read_text().strip() == "done"


@pytest.mark.parametrize(
    ("issue", "exit_code", "expected"),
    [
        (None, 0, "passed"),
        ({"severity": "error", "code": "required", "diagnostics": "Missing field"}, 1, "failed"),
        (
            {
                "severity": "warning",
                "code": "not-supported",
                "diagnostics": "Unable to validate code; no terminology service",
            },
            0,
            "incomplete",
        ),
        (None, 1, "incomplete"),
    ],
)
def test_validator_result_policy(config, tmp_path, monkeypatch, issue, exit_code, expected):
    import nehr_synth.validate as module

    monkeypatch.setattr(module, "prepare_packages", lambda c: tmp_path)
    monkeypatch.setattr(module, "tool", lambda c, n: tmp_path / n)
    monkeypatch.setattr(module, "java", lambda c: "java")

    def execute(args, log, control, **kwargs):
        assert "-no-http-access" in args
        write_json(
            tmp_path / "validator-outcome.json",
            {"resourceType": "OperationOutcome", "issue": [issue] if issue else []},
        )
        return exit_code

    monkeypatch.setattr(module, "run_process", execute)
    config.terminology = "offline"
    r, a = demographics(config)
    assert validate_graph(r, a, config, tmp_path, Control())["status"] == expected


def test_outcome_parsing():
    result = outcome_issues(
        {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "warning",
                                "location": ["Patient.id"],
                                "details": {"text": "warning"},
                            }
                        ],
                    }
                }
            ],
        }
    )
    assert result[0]["path"] == "Patient.id"
    with pytest.raises(ValueError):
        outcome_issues({})


def test_cli(config, positive, tmp_path, capsys, monkeypatch):
    path = tmp_path / "run.toml"
    save(config, path)
    assert main([]) == 0
    assert "usage:" in capsys.readouterr().out
    assert main(["generate", "--patients", "0"]) == 3
    assert main(["generate", "--config", str(path)]) == 0
    assert main(["validate", "--run", str(positive)]) == 0
    assert main(["export", "--run", str(positive), "--output", str(tmp_path / "export")]) == 0
    assert main(["mutate", "--run", str(positive), "--case", "phn-bad-checksum"]) == 0
    assert main(["doctor", "--config", str(path)]) == 2
    monkeypatch.setattr("nehr_synth.__main__.setup", lambda c: None)
    assert main(["setup", "--config", str(path)]) == 0


def test_reference_check(config):
    from nehr_synth.validate import application_checks

    r, a = demographics(config)
    r.append(
        {
            "resourceType": "Encounter",
            "id": "enc",
            "subject": {"reference": "Patient/missing"},
            "period": {"start": "2026-01-02", "end": "2026-01-01"},
        }
    )
    issues = application_checks(r, config, a)
    assert any("Unresolved reference" in i["message"] for i in issues)
    assert any("Start is after" in i["message"] for i in issues)
    dup = copy.deepcopy(r[0])
    r.append(dup)
    assert any("Duplicate resource" in i["message"] for i in application_checks(r, config, a))
