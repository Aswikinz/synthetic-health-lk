"""A finite set of single-fault variants from validated positive graphs."""

import copy
from pathlib import Path

from .localize import GN, SYSTEMS
from .pipeline import open_run, write_resources
from .runtime import Control, digest, write_json
from .validate import validate_graph

CASES = (
    "phn-bad-checksum",
    "gn-wrong-value-type",
    "address-missing-district",
    "broken-patient-reference",
)


def mutate(directory: Path, case: str, control: Control | None = None) -> Path:
    if case not in CASES:
        raise ValueError("Unknown/disabled mutation (NIC semantics are not verified)")
    manifest, baseline, config = open_run(directory)
    if manifest["status"] != "passed" or manifest.get("validation", {}).get("ig") != "passed":
        raise ValueError("Mutation requires a successfully validated positive baseline")
    resources = copy.deepcopy(baseline)
    patient = next(r for r in resources if r["resourceType"] == "Patient")
    target = patient
    layer = "ig"
    if case == "phn-bad-checksum":
        matches = [i for i in patient["identifier"] if i["system"] == SYSTEMS["phn"]]
        if not matches:
            raise ValueError("Baseline has no PHN")
        value = matches[0]["value"]
        matches[0]["value"] = value[:-1] + str((int(value[-1]) + 1) % 10)
        path, layer = "identifier.phn", "application"
    elif case == "gn-wrong-value-type":
        extension = next(
            (e for e in patient["address"][0].get("extension", []) if e["url"] == GN), None
        )
        if not extension:
            raise ValueError("Baseline has no GN extension")
        extension["valueString"] = extension.pop("valueCode")
        path = "address[0].extension[0].value[x]"
    elif case == "address-missing-district":
        patient["address"][0].pop("district")
        path = "address[0].district"
    else:
        target = next(
            (
                r
                for r in resources
                if r.get("subject", {}).get("reference") == f"Patient/{patient['id']}"
            ),
            None,
        )
        if target is None:
            raise ValueError("Baseline needs a clinical patient reference; use outpatient preset")
        target["subject"]["reference"] = "Patient/missing-synthetic-patient"
        path, layer = "subject.reference", "application"
    destination = directory / "negative" / case
    destination.mkdir(parents=True, exist_ok=False)
    entries = write_resources(resources, destination)
    observed = validate_graph(
        resources, manifest["assignments"], config, destination, control or Control()
    )
    errors = [i for i in observed["issues"] if i["severity"] in {"error", "fatal"}]
    expected = [
        i
        for i in errors
        if i["layer"] == layer
        and (
            path in i["path"]
            or (case.startswith("gn-") and "extension" in i["path"])
            or (case.startswith("address-") and "address" in i["path"])
        )
    ]
    status = (
        "expected failure observed"
        if expected
        else "unexpected pass"
        if observed["status"] == "passed"
        else "unexpected failure"
    )
    write_json(
        destination / "mutation.json",
        {
            "baseline_sha256": digest(directory / "manifest.json"),
            "case": case,
            "patient": patient["id"],
            "resource": target["resourceType"] + "/" + target["id"],
            "changed_paths": [path],
            "expected_layer": layer,
            "result": status,
            "resources": entries,
            "validation": observed,
        },
    )
    return destination
