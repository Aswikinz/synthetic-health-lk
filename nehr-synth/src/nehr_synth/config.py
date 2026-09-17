"""The shared, deliberately flat CLI/TUI configuration."""

import json
import os
import re
import tomllib
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path

DATA = Path(__file__).parent / "data"
ALPHABET = "2346789BCDFGHJKMPQRTVWXY"


def bundled(name: str) -> Path:
    path = DATA / name
    return path if path.exists() else Path(__file__).resolve().parents[2] / name


@dataclass
class Config:
    schema_version: int = 1
    patients: int = 100
    preset: str = "demographics"
    seed: int = 42
    reference_date: str = "2026-01-01"
    age_min: int = 18
    age_max: int = 80
    nic: bool = True
    phn: bool = True
    passport: bool = True
    gn: bool = True
    nic_mode: str = "structural-only"
    phn_convention: str = "ndhgs-v2-regenstrief"
    phn_prefix: str = "TEST"
    phn_prefix_provenance: str = "synthetic test configuration; not officially reserved"
    phn_issued: int = 0
    passport_prefix: str = "TEST-P"
    passport_width: int = 7
    geography: str = str(DATA / "geography.csv")
    names: str = str(DATA / "names.json")
    ig_lock: str = str(bundled("ig-lock.json"))
    tools: str = os.environ.get("NEHR_TOOLS", str(Path.cwd() / ".tools"))
    terminology: str = "online"
    terminology_url: str = "https://tx.fhir.org/r4"
    output: str = "runs"

    def check(self) -> "Config":
        defaults = Config()
        for field in fields(self):
            if type(getattr(self, field.name)) is not type(getattr(defaults, field.name)):
                raise ValueError(f"{field.name}: incorrect type")
        if self.schema_version != 1:
            raise ValueError("Unsupported configuration schema_version")
        if self.patients < 1 or not 0 <= self.seed < 2**63:
            raise ValueError("patients must be positive; seed must be in 0..2^63-1")
        if not 0 <= self.age_min <= self.age_max <= 110:
            raise ValueError("age range must be within 0..110")
        date.fromisoformat(self.reference_date)
        if self.preset not in {"demographics", "outpatient"}:
            raise ValueError("preset must be demographics or outpatient")
        if self.nic_mode != "structural-only":
            raise ValueError("Realistic NIC allocation/encoding is not verified")
        if self.nic and self.age_min < 18:
            raise ValueError("Disable NIC for pediatric presets")
        if not (self.nic or self.phn or self.passport):
            raise ValueError("At least one patient identifier must be enabled")
        if self.phn_convention != "ndhgs-v2-regenstrief":
            raise ValueError("Unknown PHN convention")
        if not re.fullmatch(r"[A-Z0-9]{4}", self.phn_prefix):
            raise ValueError("PHN test prefix must contain four uppercase ASCII letters/digits")
        if self.phn and not 0 <= self.phn_issued <= 1_000_000 - self.patients:
            raise ValueError("PHN POI issuance capacity exhausted (one million)")
        if not 1 <= self.passport_width <= 12:
            raise ValueError("passport_width must be in 1..12")
        if self.passport and self.patients >= 10**self.passport_width:
            raise ValueError("Passport serial capacity exhausted")
        if not re.fullmatch(r"[A-Za-z0-9-]{1,30}", self.passport_prefix):
            raise ValueError("Passport prefix must contain ASCII letters, digits or hyphens")
        if self.terminology not in {"online", "offline"}:
            raise ValueError("terminology must be online or offline")
        if not self.terminology_url.startswith("https://"):
            raise ValueError("Terminology endpoint must use HTTPS")
        return self


PATHS = {"geography", "names", "ig_lock", "tools", "output"}


def load(path: Path | None = None, **overrides) -> Config:
    values = {}
    if path:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
        for key in PATHS & values.keys():
            if not isinstance(values[key], str):
                raise ValueError(f"{key}: expected a path string")
            values[key] = str((path.resolve().parent / values[key]).resolve())
    unknown = (values.keys() | overrides.keys()) - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    values.update({key: value for key, value in overrides.items() if value is not None})
    config = Config(**values).check()
    for key in PATHS:
        setattr(config, key, str(Path(getattr(config, key)).resolve()))
    return config


def save(config: Config, path: Path) -> None:
    config.check()
    values = asdict(config)
    for key in PATHS:
        values[key] = str(Path(values[key]).resolve())
    # This flat schema needs only TOML strings, booleans and integers.
    path.write_text(
        "\n".join(f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in values.items()) + "\n",
        encoding="utf-8",
    )
