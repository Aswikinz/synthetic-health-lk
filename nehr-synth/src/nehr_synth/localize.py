"""Direct demographics and explicitly synthetic identities."""

import csv
import hashlib
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .config import ALPHABET, Config

CR = "http://ig.hiu.lk/fhir/clientregistry/StructureDefinition/"
NEHR = "http://ig.hiu.lk/fhir/nehr/StructureDefinition/"
PR = "http://ig.hiu.lk/fhir/providerregistry/StructureDefinition/"
GN = CR + "lk-gn-extension"
SYSTEMS = {
    "nic": "http://fhir.health.gov.lk/ips/identifier/nic",
    "phn": "http://fhir.health.gov.lk/ips/identifier/phn",
    "passport": "http://fhir.health.gov.lk/identifier/passport",
}


def checksum(value: str) -> str:
    """Regenstrief variant, verified against OpenMRS 2.7.0 independent vectors.

    ASCII-minus-48 weights; not decimal Luhn or Luhn mod N. See RESEARCH.md.
    """
    if not re.fullmatch(r"[A-Za-z0-9]+", value):
        raise ValueError("Checksum input must be nonempty ASCII alphanumeric")
    digits = [ord(char) - 48 for char in reversed(value.upper())]
    total = sum(2 * digit - (digit // 5) * 9 if i % 2 == 0 else digit
                for i, digit in enumerate(digits))
    return str((-abs(total)) % 10)


def valid_phn(value: str, prefix: str) -> bool:
    return (len(value) == 11 and value[:4] == prefix
            and all(c in ALPHABET for c in value[4:10])
            and value[-1] == checksum(value[:-1]))


def stable_id(seed: int, kind: str, key: str | int) -> str:
    return str(uuid5(NAMESPACE_URL, f"nehr-synth/1/{seed}/{kind}/{key}"))


def rng_for(seed: int, key: str) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{seed}/{key}".encode()).hexdigest(), 16))


def fixtures(config: Config) -> tuple[list, list]:
    names = json.loads(Path(config.names).read_text(encoding="utf-8"))
    if not names or any(not n.get("family") or not n.get("given")
                        or not isinstance(n["given"], list) or not n.get("text") for n in names):
        raise ValueError("Names require explicit family, given array and full text")
    with Path(config.geography).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"province", "district", "ds_division", "gn_code", "gn_name",
                "scheme", "provenance"}
    if not rows or any(any(not row.get(k) for k in required) for row in rows):
        raise ValueError("Geography CSV requires complete hierarchy, scheme and provenance")
    divisions = {}
    for row in rows:
        key = (row["scheme"], row["gn_code"])
        if key in divisions and divisions[key] != row:
            raise ValueError("Conflicting geography rows for the same scheme/code")
        divisions[key] = row
    return names, rows


def demographics(config: Config, sources: list | None = None, cancel=None) -> tuple[list, dict]:
    config.check()
    names, geography = fixtures(config)
    reference = date.fromisoformat(config.reference_date)
    resources, assignments = [], {}
    phn_rng = rng_for(config.seed, "phn")
    # Sample without replacement; bounded and detects space exhaustion before allocating.
    bodies = phn_rng.sample(range(len(ALPHABET)**6), config.patients) if config.phn else []
    nic_rng = rng_for(config.seed, "nic")
    nics = nic_rng.sample(range(10**11, 10**12), config.patients) if config.nic else []
    for index in range(config.patients):
        if cancel:
            cancel.check()
        rng = rng_for(config.seed, f"patient/{index}")
        if sources is None:
            # Rejection at February 29 handles exact age boundaries without invalid dates.
            first = date(reference.year - config.age_max - 1, reference.month, 1)
            last = date(reference.year - config.age_min, reference.month, reference.day)
            while True:
                dob = first + timedelta(days=rng.randrange((last - first).days + 1))
                age = reference.year - dob.year - ((reference.month, reference.day)
                                                   < (dob.month, dob.day))
                if config.age_min <= age <= config.age_max:
                    break
            gender = rng.choice(["male", "female"])
        else:
            dob = date.fromisoformat(sources[index]["birthDate"])
            gender = sources[index]["gender"]
        identifiers = []
        if config.nic:
            identifiers.append({"system": SYSTEMS["nic"], "value": str(nics[index])})
        if config.phn:
            number, body = bodies[index], ""
            for _ in range(6):
                number, digit = divmod(number, len(ALPHABET))
                body = ALPHABET[digit] + body
            value = config.phn_prefix + body
            identifiers.append({"system": SYSTEMS["phn"], "value": value + checksum(value)})
        if config.passport:
            identifiers.append({"system": SYSTEMS["passport"],
                                "value": f"{config.passport_prefix}{index + 1:0{config.passport_width}}"})
        row = rng.choice(geography)
        address = {"line": [f"{index + 1} Synthetic Test Lane"], "city": row["ds_division"],
                   "district": row["district"], "state": row["province"], "country": "LK"}
        if config.gn:
            address["extension"] = [{"url": GN, "valueCode": row["gn_code"]}]
        patient = {"resourceType": "Patient", "id": stable_id(config.seed, "Patient", index),
                   "meta": {"profile": [CR + "LKPatient"]}, "identifier": identifiers,
                   "name": [rng.choice(names)], "gender": gender, "birthDate": dob.isoformat(),
                   "address": [address]}
        resources.append(patient)
        assignments[patient["id"]] = {"geography": row, "nic_encoded_attribute": None,
                                       "nic_mode": config.nic_mode}
    return resources, assignments
