"""Unchanged Synthea engine, a tiny local module, explicit supported graph selection."""

import copy
import shutil
from pathlib import Path

from .config import DATA, Config
from .localize import NEHR, PR, demographics, stable_id
from .runtime import Control, digest, java, read_json, run_process, tool, write_json


def simulation_config(directory: Path) -> Path:
    settings = {
        "generate.demographics.default_file": "demographics.csv",
        "generate.geography.zipcodes.default_file": "zipcodes.csv",
        "generate.geography.timezones.default_file": "timezones.csv",
        "generate.geography.sdoh.default_file": "sdoh.csv",
        "generate.providers.hospitals.default_file": "hospitals.csv",
        "generate.payers.insurance_companies.default_file": "insurance_companies.csv",
        "generate.payers.insurance_plans.default_file": "insurance_plans.csv",
        "generate.payers.insurance_plans.eligibilities_file": "insurance_eligibilities.csv",
    }
    for kind in (
        "longterm",
        "nursing",
        "rehab",
        "hospice",
        "dialysis",
        "homehealth",
        "veterans",
        "urgentcare",
        "primarycare",
        "ihs.hospitals",
        "ihs.primarycare",
    ):
        settings[f"generate.providers.{kind}.default_file"] = "empty-providers.csv"
    lines = [f"{key} = {(directory / value).as_posix()}" for key, value in settings.items()]
    lines += [
        "generate.geography.country_code = LK",
        "generate.thread_pool_size = 1",
        "generate.only_alive_patients = true",
        "generate.max_attempts_to_keep_patient = 20",
        "exporter.years_of_history = 0",
        "exporter.fhir.use_us_core_ig = false",
        "exporter.fhir.transaction_bundle = false",
        "exporter.use_uuid_filenames = true",
        "exporter.hospital.fhir.export = false",
        "exporter.practitioner.fhir.export = false",
        "exporter.metadata.export = false",
        "exporter.enable_custom_exporters = false",
    ]
    path = directory / "synthea.properties"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def select_graph(bundle: dict) -> tuple | None:
    resources = [e["resource"] for e in bundle.get("entry", [])]
    patient = next((r for r in resources if r["resourceType"] == "Patient"), None)
    if patient is None:
        return None
    encounters = {
        r["id"]: r
        for r in resources
        if r["resourceType"] == "Encounter" and r.get("class", {}).get("code") == "AMB"
    }
    observations = sorted(
        (
            r
            for r in resources
            if r["resourceType"] == "Observation"
            and any(
                c.get("system") == "http://loinc.org" and c.get("code") == "2345-7"
                for c in r.get("code", {}).get("coding", [])
            )
        ),
        key=lambda r: (r.get("effectiveDateTime", ""), r["id"]),
        reverse=True,
    )
    for observation in observations:
        reference = observation.get("encounter", {}).get("reference", "")
        encounter = encounters.get(reference.removeprefix("urn:uuid:").split("/")[-1])
        if encounter and not encounter.get("diagnosis"):
            return patient, encounter, observation
    return None


def map_graph(config: Config, patient: dict, source: tuple, index: int) -> list:
    _, encounter, observation = source
    quantity = observation.get("valueQuantity", {})
    if quantity.get("system") != "http://unitsofmeasure.org" or quantity.get("code") != "mg/dL":
        raise ValueError("Unmapped required glucose quantity/unit; expected UCUM mg/dL")
    if not isinstance(quantity.get("value"), (int, float)):
        raise ValueError("Glucose value must be numeric")
    eid, oid, cid = [
        stable_id(config.seed, kind, index) for kind in ("Encounter", "Observation", "Composition")
    ]
    practitioner_id = stable_id(config.seed, "Practitioner", "screening")
    subject = {"reference": "Patient/" + patient["id"]}
    localized = {
        "resourceType": "Encounter",
        "id": eid,
        "meta": {"profile": [NEHR + "LKEncounter"]},
        "status": encounter["status"],
        "class": copy.deepcopy(encounter["class"]),
        "subject": subject,
        "period": copy.deepcopy(encounter["period"]),
        "participant": [{"individual": {"reference": "Practitioner/" + practitioner_id}}],
    }
    obs = {
        "resourceType": "Observation",
        "id": oid,
        "meta": {"profile": [NEHR + "LKBloodGlucose"]},
        "status": observation["status"],
        "code": {"coding": [{"system": "http://loinc.org", "code": "2345-7"}]},
        "subject": subject,
        "encounter": {"reference": "Encounter/" + eid},
        "effectiveDateTime": observation["effectiveDateTime"],
        "valueQuantity": quantity,
    }
    composition = {
        "resourceType": "Composition",
        "id": cid,
        "meta": {"profile": [NEHR + "LKEncounterSummary"]},
        "identifier": {"system": "https://synthetic.invalid/summary", "value": cid},
        "status": "final",
        "type": {"text": "Synthetic outpatient screening summary"},
        "subject": subject,
        "encounter": {"reference": "Encounter/" + eid},
        "date": encounter["period"].get("end", encounter["period"]["start"]),
        "author": [{"reference": "Practitioner/" + practitioner_id}],
        "title": "Synthetic outpatient screening — observation only",
        "section": [{"title": "Encounter Output", "entry": [{"reference": "Encounter/" + eid}]}],
    }
    return [localized, obs, composition]


def outpatient(config: Config, stage: Path, control: Control, progress) -> tuple:
    if config.age_min < 18:
        raise ValueError("The initial outpatient screening module supports adults only")
    inputs = stage / "inputs" / "synthea"
    shutil.copytree(DATA / "synthea", inputs)
    settings = simulation_config(inputs)
    candidates, generated = [], 0
    batches = []
    for batch in range(3):
        control.check()
        output = stage / "simulation" / str(batch)
        count = config.patients - len(candidates)
        seed = (config.seed + batch) % (2**63)
        args = [
            java(config),
            "-Xmx2g",
            "-Duser.timezone=UTC",
            "-jar",
            str(tool(config, "synthea.jar")),
            "-p",
            str(count),
            "-s",
            str(seed),
            "-cs",
            str(config.seed),
            "-r",
            config.reference_date.replace("-", ""),
            "-e",
            config.reference_date.replace("-", ""),
            "-a",
            f"{config.age_min}-{config.age_max}",
            "-c",
            str(settings),
            "-d",
            str(inputs / "modules"),
            "-m",
            "nehr_screening",
            "--exporter.baseDirectory=" + str(output),
            "Western",
            "Colombo",
        ]
        write_json(stage / f"synthea-command-{batch}.json", args)
        code = run_process(args, stage / f"synthea-{batch}.log", control)
        if code:
            raise ValueError(f"Synthea exited {code}; inspect synthea-{batch}.log")
        for path in sorted((output / "fhir").glob("*.json")):
            bundle = read_json(path)
            generated += sum(
                e.get("resource", {}).get("resourceType") == "Patient"
                for e in bundle.get("entry", [])
            )
            graph = select_graph(bundle)
            if graph and len(candidates) < config.patients:
                candidates.append(graph)
        batches.append({"seed": seed, "requested": count})
        progress(
            f"Simulation: selected {len(candidates)}/{config.patients}; candidates {generated}"
        )
        if len(candidates) == config.patients:
            break
    if len(candidates) != config.patients:
        raise ValueError(
            f"Clinical count shortfall: selected {len(candidates)}/{config.patients} "
            "after 3 batches"
        )
    patients, assignments = demographics(config, [g[0] for g in candidates], control)
    resources = list(patients)
    practitioner_id = stable_id(config.seed, "Practitioner", "screening")
    resources.append(
        {
            "resourceType": "Practitioner",
            "id": practitioner_id,
            "meta": {"profile": [PR + "LKPractitioner"]},
            "identifier": [
                {"system": "https://synthetic.invalid/practitioner", "value": "TEST-CLINICIAN"}
            ],
            "name": [{"text": "Synthetic Screening Clinician"}],
        }
    )
    for i, (patient, graph) in enumerate(zip(patients, candidates, strict=True)):
        resources.extend(map_graph(config, patient, graph, i))
    return (
        resources,
        assignments,
        {
            "generated_candidates": generated,
            "simulation_batches": batches,
            "scenario": "Artificial adult glucose screening; no diagnosis required",
            "omitted_source_categories": [
                "other encounters/observations",
                "US identifiers/extensions",
                "claims",
                "coverage",
                "procedures",
                "medications",
                "careplans",
                "immunizations",
            ],
            "clinical_input_hashes": {
                str(p.relative_to(inputs)): digest(p) for p in inputs.rglob("*") if p.is_file()
            },
            "diagnosis_support": "disabled: unresolved ICD-10 ValueSet contract",
        },
    )
