"""One scriptable pipeline shared by the terminal application and CLI."""

import shutil
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import __version__
from .config import Config, bundled, load, save
from .localize import GN, SYSTEMS, demographics
from .runtime import Cancelled, Control, digest, read_json, write_json
from .validate import references, validate_graph

EXIT_CODES = {"passed": 0, "failed": 1, "incomplete": 2, "not checked": 2}


def write_resources(resources: list, directory: Path) -> list:
    fhir = directory / "fhir"
    fhir.mkdir()
    entries = []
    for resource in resources:
        name = f"{resource['resourceType']}-{resource['id']}.json"
        path = fhir / name
        write_json(path, resource)
        entries.append(
            {
                "type": resource["resourceType"],
                "id": resource["id"],
                "file": "fhir/" + name,
                "sha256": digest(path),
                "dependencies": sorted({r for _, r in references(resource)}),
            }
        )
    return entries


def open_run(directory: Path) -> tuple[dict, list, Config]:
    directory = directory.resolve()
    manifest = read_json(directory / "manifest.json")
    resources = []
    for entry in manifest["resources"]:
        path = (directory / entry["file"]).resolve()
        if not path.is_relative_to(directory / "fhir"):
            raise ValueError("Canonical file path escapes the run's FHIR directory")
        if digest(path) != entry["sha256"]:
            raise ValueError(f"Canonical file changed: {entry['file']}")
        resource = read_json(path)
        if (resource["resourceType"], resource["id"]) != (entry["type"], entry["id"]):
            raise ValueError("Manifest/resource identity mismatch")
        if sorted({r for _, r in references(resource)}) != entry["dependencies"]:
            raise ValueError("Manifest/reference mismatch")
        resources.append(resource)
    if Counter(r["resourceType"] for r in resources) != manifest["counts"]:
        raise ValueError("Manifest/resource count mismatch")
    return (
        manifest,
        resources,
        load(
            directory / "run.toml",
            ig_lock=str(directory / "inputs" / "ig-lock.json"),
            names=str(directory / "inputs" / "names.json"),
            geography=str(directory / "inputs" / "geography.csv"),
        ),
    )


def generate(config: Config, progress=print, control: Control | None = None) -> Path:
    config.check()
    control = control or Control()
    root = Path(config.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    run_id = uuid4().hex[:12]
    manifest = {
        "schema_version": 1,
        "application": __version__,
        "mapping_version": 1,
        "run_id": run_id,
        "preset": config.preset,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "incomplete",
        "receiver_compatibility": "unconfirmed",
        "target": "fhir.lk.nehr#0.1.0 / R4 4.0.1",
        "requested_patients": config.patients,
        "generated_candidates": 0,
        "resources": [],
        "counts": {},
        "assignments": {},
    }
    save(config, stage / "run.toml")
    try:
        inputs = {
            "names": Path(config.names),
            "geography": Path(config.geography),
            "ig-lock": Path(config.ig_lock),
            "tool-lock": bundled("tool-lock.json"),
        }
        source_dir = stage / "inputs"
        source_dir.mkdir()
        manifest["input_hashes"] = {}
        for name, path in inputs.items():
            manifest["input_hashes"][name] = digest(path)
            shutil.copyfile(path, source_dir / path.name)
        control.check()
        if config.preset == "outpatient":
            from .synthea import outpatient

            progress(f"Simulation: requesting {config.patients} patient graphs")
            resources, assignments, simulation = outpatient(config, stage, control, progress)
            manifest.update(simulation)
        else:
            progress(f"Generation: {config.patients} patients; Synthea not needed")
            resources, assignments = demographics(config, cancel=control)
            manifest["generated_candidates"] = config.patients
        progress("Localization complete; writing canonical FHIR")
        control.check()
        manifest["assignments"] = assignments
        manifest["resources"] = write_resources(resources, stage)
        manifest["counts"] = dict(Counter(r["resourceType"] for r in resources))
        patients = [r for r in resources if r["resourceType"] == "Patient"]
        manifest["exported_patients"] = len(patients)
        manifest["identifier_counts"] = {
            kind: sum(i["system"] == system for p in patients for i in p["identifier"])
            for kind, system in SYSTEMS.items()
        }
        manifest["gn_populated_patients"] = sum(
            any(e.get("url") == GN for a in p.get("address", []) for e in a.get("extension", []))
            for p in patients
        )
        manifest["identity_convention"] = {
            "nic": config.nic_mode,
            "phn": config.phn_convention,
            "poi": config.phn_prefix,
            "poi_provenance": config.phn_prefix_provenance,
            "passport": "synthetic-prefix-serial",
            "uniqueness_scope": "this dataset only",
        }
        write_json(stage / "manifest.json", manifest)
        # Validate the bytes written for export, not a separate in-memory projection.
        _, exported, _ = open_run(stage)
        progress(f"Validation: all {len(exported)} resources (HL7 validator)")
        validation = validate_graph(exported, assignments, config, stage, control)
        manifest["status"] = validation["status"]
        manifest["validation"] = validation
        manifest["patient_groups"] = {
            state: len(patients) if state == validation["status"] else 0
            for state in ("passed", "failed", "incomplete")
        }
        manifest["patient_groups_note"] = (
            "Conservative whole-graph groups; shared/unknown failures affect all patients"
        )
    except Cancelled as error:
        manifest["error"] = str(error)
    except (ValueError, OSError, TimeoutError, KeyError) as error:
        manifest["error"] = str(error)
        manifest["execution_error"] = True
    finally:
        write_json(stage / "manifest.json", manifest)
        group = "completed" if manifest["status"] == "passed" else manifest["status"]
        target = root / group / run_id
        target.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(target)
    progress(f"{manifest['status'].upper()}: {target}")
    return target


def revalidate(directory: Path, control: Control | None = None, **overrides) -> dict:
    from dataclasses import asdict

    manifest, resources, saved = open_run(directory)
    values = asdict(saved)
    values.update({key: value for key, value in overrides.items() if value is not None})
    config = load(**values)
    # Append evidence; never overwrite a baseline's validator reports.
    report = directory / "checks" / uuid4().hex[:12]
    report.mkdir(parents=True)
    return validate_graph(resources, manifest["assignments"], config, report, control or Control())


def export_run(directory: Path, destination: Path) -> Path:
    open_run(directory)
    if destination.exists():
        raise ValueError("Export destination already exists; choose a new directory")
    if destination.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Export destination must be outside the source run")
    shutil.copytree(directory, destination, ignore=shutil.ignore_patterns("negative", "simulation"))
    open_run(destination)
    return destination
