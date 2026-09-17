"""Application graph checks plus the actual HL7 validator; no FHIRPath reimplementation."""

from collections import Counter
from datetime import date
from pathlib import Path

from .config import Config
from .localize import GN, SYSTEMS, valid_phn
from .runtime import Control, java, prepare_packages, read_json, run_process, tool, write_json


def references(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "reference" and isinstance(child, str):
                yield path + ".reference", child
            else:
                yield from references(child, path + "." + key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from references(child, f"{path}[{i}]")


def application_checks(resources: list, config: Config, assignments: dict) -> list:
    issues = []

    def error(resource, path, message):
        issues.append({"layer": "application", "severity": "error", "resource": resource,
                       "path": path, "message": message})

    ids = [r["resourceType"] + "/" + r["id"] for r in resources]
    known = set(ids)
    if len(known) != len(ids):
        error("graph", "id", "Duplicate resource IDs")
    patients = [r for r in resources if r["resourceType"] == "Patient"]
    if len(patients) != config.patients:
        error("graph", "Patient", f"Expected {config.patients}, found {len(patients)} patients")
    identifiers = set()
    for resource in resources:
        rid = resource["resourceType"] + "/" + resource["id"]
        for path, reference in references(resource):
            if reference not in known:
                error(rid, path, f"Unresolved reference: {reference}")
        period = resource.get("period", {})
        if period.get("start", "") > period.get("end", "9999"):
            error(rid, "period", "Start is after end")
        subject = resource.get("subject", {}).get("reference")
        if subject in known:
            patient = next((p for p in patients if f"Patient/{p['id']}" == subject), None)
            instant = resource.get("effectiveDateTime") or period.get("start")
            if patient and instant and not patient["birthDate"] <= instant[:10] <= config.reference_date:
                error(rid, "period/effectiveDateTime", "Clinical date outside patient lifetime/reference date")
    for patient in patients:
        rid = "Patient/" + patient["id"]
        values = patient.get("identifier", [])
        if not values:
            error(rid, "identifier", "At least one identifier required")
        counts = Counter(i.get("system") for i in values)
        for kind, system in SYSTEMS.items():
            if getattr(config, kind) and counts[system] != 1:
                error(rid, "identifier", f"Expected one {kind} identifier")
            if counts[system] > 1:
                error(rid, "identifier", f"Duplicate {kind} identifier slice")
        for identifier in values:
            value, system = identifier.get("value"), identifier.get("system")
            if not isinstance(value, str) or not value or not system:
                error(rid, "identifier", "Identifier system and string value required")
                continue
            if (system, value) in identifiers:
                error(rid, "identifier", "Duplicate patient identifier")
            identifiers.add((system, value))
            if system == SYSTEMS["phn"] and not valid_phn(value, config.phn_prefix):
                error(rid, "identifier.phn", "PHN convention/checksum mismatch")
            if system == SYSTEMS["nic"] and (len(value) != 12 or not value.isascii() or not value.isdigit()):
                error(rid, "identifier.nic", "Structural NIC must have 12 ASCII digits")
        try:
            dob = date.fromisoformat(patient["birthDate"])
            reference = date.fromisoformat(config.reference_date)
            age = reference.year - dob.year - ((reference.month, reference.day) < (dob.month, dob.day))
            if not config.age_min <= age <= config.age_max:
                error(rid, "birthDate", "DOB outside configured age range")
        except (KeyError, ValueError):
            error(rid, "birthDate", "Invalid or missing birthDate")
        row = assignments.get(patient["id"], {}).get("geography")
        if not row:
            error(rid, "address", "Missing geography provenance")
        else:
            address = patient.get("address", [{}])[0]
            for key, source in [("city", "ds_division"), ("district", "district"), ("state", "province")]:
                if key in address and address[key] != row[source]:
                    error(rid, "address." + key, "Geography hierarchy mismatch")
            codes = [e.get("valueCode") for e in address.get("extension", []) if e.get("url") == GN]
            if config.gn and not codes:
                error(rid, "address.extension", "Missing configured GN extension")
            if codes and codes[0] is not None and codes != [row["gn_code"]]:
                error(rid, "address.extension", "GN code differs from assigned fixture")
    return issues


def outcome_issues(outcome: dict) -> list:
    if outcome.get("resourceType") == "Bundle":
        return [issue for entry in outcome.get("entry", [])
                for issue in outcome_issues(entry.get("resource", {}))]
    if outcome.get("resourceType") != "OperationOutcome":
        raise ValueError("Validator did not return an OperationOutcome")
    return [{"layer": "ig", "severity": item["severity"],
             "resource": "graph", "path": ", ".join(item.get("expression", item.get("location", []))),
             "message": item.get("diagnostics") or item.get("details", {}).get("text", ""),
             "code": item.get("code", "")}
            for item in outcome.get("issue", [])]


def validate_graph(resources: list, assignments: dict, config: Config, directory: Path,
                   control: Control) -> dict:
    issues = application_checks(resources, config, assignments)
    result = {"application": "failed" if issues else "passed", "ig": "not checked",
              "identifier_format": {"phn": "passed" if config.phn else "not checked",
                                    "nic": "incomplete" if config.nic else "not checked",
                                    "passport": "synthetic convention" if config.passport else "not checked"},
              "registry_validity": "not checked", "terminology_mode": config.terminology,
              "terminology_endpoint": config.terminology_url if config.terminology == "online" else None,
              "server_version": "not reported", "issues": issues}
    if any(i["path"] == "identifier.phn" for i in issues):
        result["identifier_format"]["phn"] = "failed"
    graph = {"resourceType": "Bundle", "type": "collection", "entry": [
        {"fullUrl": f"https://synthetic.invalid/fhir/{r['resourceType']}/{r['id']}", "resource": r}
        for r in resources]}
    write_json(directory / "validation-input.json", graph)
    try:
        home = prepare_packages(config)
        args = [java(config), "-Xmx2g", f"-Duser.home={home}", "-jar", str(tool(config, "validator.jar")),
                str(directory / "validation-input.json"), "-version", "4.0.1",
                "-ig", "fhir.lk.nehr#0.1.0", "-tx", config.terminology_url
                if config.terminology == "online" else "n/a",
                "-txCache", str(Path(config.tools) / "tx-cache"),
                "-txLog", str(directory / "terminology.log"),
                "-output", str(directory / "validator-outcome.json"),
                "-show-message-ids", "-check-references", "-disable-default-resource-fetcher"]
        if config.terminology == "offline":
            args.append("-no-http-access")
        write_json(directory / "validator-command.json", args)
        code = run_process(args, directory / "validator.log", control)
        parsed = outcome_issues(read_json(directory / "validator-outcome.json"))
        issues.extend(parsed)
        unavailable = ("unable to connect", "not supported", "could not be found", "not found",
                       "unable to resolve", "unable to provide", "no terminology", "not checked",
                       "not available", "error contacting", "unable to validate", "unknown code system")
        gaps = any(any(word in i["message"].lower() for word in unavailable) for i in parsed)
        errors = any(i["severity"] in {"error", "fatal"} for i in parsed)
        result["ig"] = "incomplete" if gaps else "failed" if errors else "passed"
        if code != 0 and not errors:
            result["ig"] = "incomplete"
            issues.append({"layer": "execution", "severity": "error", "resource": "graph",
                           "path": "validator", "message": f"Validator exit code {code}"})
    except (ValueError, OSError, TimeoutError) as error:
        result["ig"] = "incomplete"
        issues.append({"layer": "execution", "severity": "error", "resource": "graph",
                       "path": "validator", "message": str(error)})
    result["status"] = ("failed" if result["application"] == "failed" or result["ig"] == "failed"
                        else result["ig"])
    write_json(directory / "validation.json", result)
    (directory / "validation.txt").write_text(
        f"IG: {result['ig']}; application: {result['application']}; receiver: unconfirmed\n"
        + "\n".join(f"{i['severity']} {i['resource']} {i['path']}: {i['message']}" for i in issues),
        encoding="utf-8")
    return result
