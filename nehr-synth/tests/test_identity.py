from dataclasses import replace

import pytest

from nehr_synth.config import Config, load, save
from nehr_synth.localize import SYSTEMS, checksum, demographics, valid_phn
from nehr_synth.validate import application_checks


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a", "3"),
        ("123456", "6"),
        ("ab32kcdak3", "9"),
        ("chaseisreallycoolyay", "7"),
        ("1", "8"),
        ("moose", "7"),
        ("MOOSE", "7"),
        ("MooSE", "7"),
        ("adD3Eddf429daD999", "1"),
    ],
)
def test_independent_openmrs_vectors(value, expected):
    assert checksum(value) == expected


def test_repeatable_ten_patients():
    config = Config(patients=10)
    resources, assignments = demographics(config)
    assert (resources, assignments) == demographics(config)
    assert len(resources) == len({p["id"] for p in resources}) == 10
    assert not application_checks(resources, config, assignments)
    assert any(any(ord(c) > 127 for c in p["name"][0]["text"]) for p in resources)
    for p in resources:
        value = next(i["value"] for i in p["identifier"] if i["system"] == SYSTEMS["phn"])
        assert valid_phn(value, config.phn_prefix)
        assert not valid_phn(value[:-1] + str((int(value[-1]) + 1) % 10), config.phn_prefix)


def test_pediatric_no_nic():
    config = Config(patients=30, age_min=0, age_max=17, nic=False)
    resources, assignments = demographics(config)
    assert not application_checks(resources, config, assignments)
    assert all(i["system"] != SYSTEMS["nic"] for p in resources for i in p["identifier"])


@pytest.mark.parametrize(
    "changes",
    [
        {"patients": 0},
        {"patients": True},
        {"patients": 1_000_001},
        {"phn_issued": 999_999},
        {"nic": False, "phn": False, "passport": False},
        {"age_min": 12},
        {"nic_mode": "realistic"},
        {"passport_width": 1},
        {"phn_prefix": "!!!!"},
        {"reference_date": "2026-02-29"},
    ],
)
def test_invalid_config(changes):
    with pytest.raises(ValueError):
        replace(Config(), **changes).check()


def test_config_roundtrip_paths_and_overrides(tmp_path):
    config = load(patients=7)
    path = tmp_path / "run.toml"
    save(config, path)
    assert load(path) == config
    assert load(path, patients=9).patients == 9
    path.write_text('output = "relative path"\npatients = 10\n')
    assert load(path).output == str(tmp_path / "relative path")
    path.write_text("typo = 12\n")
    with pytest.raises(ValueError, match="Unknown"):
        load(path)


def test_duplicate_and_missing_identifiers():
    config = Config(patients=2)
    resources, assignments = demographics(config)
    resources[1]["identifier"] = resources[0]["identifier"]
    assert any(
        "Duplicate patient" in i["message"]
        for i in application_checks(resources, config, assignments)
    )
    resources[0]["identifier"] = []
    assert any(
        "At least one" in i["message"] for i in application_checks(resources, config, assignments)
    )
