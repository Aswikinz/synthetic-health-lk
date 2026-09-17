# Contract review — 2026-09-17

The application targets **FHIR R4 4.0.1, fhir.lk.nehr 0.1.0**, using
Client Registry/Provider Registry/Facility Registry 0.1.0. Receiver compatibility
is **unconfirmed**. No receiver or registry was contacted. The older IPS guide is
outside scope. These development packages declare publication limitations.

`ig-lock.json` is the reviewed dependency closure. All four national archive
hashes match the supplied research brief. `dev` dependencies resolve to exact,
byte-identical 0.1.0 archives in a private validator cache. Published canonicals,
snapshots and differentials remain unchanged. Update changed checksums only after
reviewing the upstream contract. Routine setup only consumes the reviewed lock.

The validator additionally bootstraps `hl7.fhir.xver-extensions#0.1.0` and
`hl7.terminology.r4#6.2.0`; these are locked too. Its unversioned automatic
`hl7.terminology` / `hl7.fhir.uv.extensions` loads otherwise request moving
packages online. The pinned validator's `IgLoader` supports local package files
under these names. A private working directory supplies byte-identical R4
6.5.0 / 5.2.0 archives for those lookups, with the resolution recorded in the
lock. The validation report records and checks the actual loaded package set.
No R5 core or later ICD-10 ValueSet is loaded into the target validator.

Sources: [NEHR specification](https://ig.hiu.lk/fhir/nehr/specification.html),
[Client Registry](https://ig.hiu.lk/fhir/clientregistry/artifacts.html), and
the source URLs in the lock. Snapshots and differentials were inspected for the
profiles listed in README; base cardinalities apply too.

## Identity decisions

PHN uses the national guideline's four-character POI, six-character random body,
and one decimal check digit. Body alphabet: `2346789BCDFGHJKMPQRTVWXY`.
The POI has a **one-million issuance ceiling**, even though its body space is larger.
`phn_issued` reserves previously used capacity, but is not an allocation registry.
`TEST` is a configured synthetic prefix, **not an officially reserved prefix**.

[NDHGS v2, section 7.1, printed pp. 21–22](https://www.health.gov.lk/wp-content/uploads/2022/10/NDHGS-v2.pdf)
specifies Regenstrief's modified Luhn. The independently implemented checksum
was checked against [OpenMRS 2.7.0 source](https://github.com/openmrs/openmrs-core/blob/2.7.0/api/src/main/java/org/openmrs/patient/impl/LuhnIdentifierValidator.java)
and its [numeric/alphabetic test vectors](https://github.com/openmrs/openmrs-core/blob/2.7.0/api/src/test/java/org/openmrs/patient/impl/LuhnIdentifierValidatorTest.java).
The check digit covers POI plus body, without OpenMRS's presentation hyphen.
The character weighting is ASCII-minus-48, with alternating doubled/reduced
weights, not decimal Luhn on letters or Luhn mod N.

NIC is deliberately **structural-only**: twelve numeric characters. The
[DRP history](https://drp.gov.lk/en/history.php) confirms twelve-digit NICs;
[DRP FAQ](https://drp.gov.lk/en/faq.php) describes old/new conversion but does
not supply a complete allocation/checksum contract or independent leap-day
vectors. No national date/sex/checksum validity is claimed. The model records
no encoded attribute. Realistic mode and `nic-dob-mismatch` remain disabled until
those semantics can be independently verified. Pediatric cases omit NICs.

Passport `TEST-P` plus a padded serial is a named synthetic string convention.
It does not assert national format validity. Dataset uniqueness is guaranteed;
different seeds are not guaranteed disjoint and no identifiers are proven unissued.

Names are authored synthetic fixtures with explicit family/given/full text;
the mapping is not inferred from word order, script, gender or ethnicity.
GN fixtures are explicitly fabricated administrative rows; `scheme` and
`provenance` accompany the complete hierarchy in the manifest. Sourced CSVs
must use the same columns. Local GN numbers and census composite codes are
not interchangeable; the IG chooses neither and its GN extension has no binding.

## Upstream issues retained

* Optional NIC/PHN type coding systems differ from the bundled CodeSystem URL.
  The generator emits minimal system/value identifiers.
* Calculated birth date's published context has `birthdate` capitalization;
  the generator uses known birth dates and omits this extension.
* LKCondition binds to the R4 ICD-10 example ValueSet; diagnosis export is gated.
  No WHO/ICD-10-CM relabeling, SNOMED map or placeholder diagnosis is distributed.
* LKEncounterSummary is a standalone Composition, not a document. Its optional
  obstetric targets and broad Observation section slicing need caution.
* LKVitalSignsHemoglobin actually requires HbA1c LOINC 4548-4.

An actual online validator probe on 2026-09-17 rejected ICD-10 `E11` at
`Bundle.entry[1].resource/*Condition/icd10-binding-probe*/.code`: the code is not
in `http://hl7.org/fhir/ValueSet/icd-10|4.0.1` and a member is required.
See `evidence/condition-gate.json` for the exact diagnostic and definition hash.
`evidence/icd-10-definitions.json` also retains the R5 definition inspected during
bootstrap investigation; its presence there is explicitly not target resolution.

The synthetic Synthea locality uses the upstream v4.0.0 CSV schemas. Population
size, equal age bins, 50/50 sex weights, socioeconomic weights and screening
glucose range are artificial settings, not census data or a treatment guideline.
The schema's US race labels are engine input categories, not claims about Sri
Lankan ethnicity. They are not exported. The payer files have headers only;
the scenario does not model insurance. Provider coordinates describe the test
locality and provider identities are synthetic. Source DOB, observation values,
units and visit dates are retained. All clinical categories outside the selected
screening graph are recorded as omitted; no diagnosis is needed by this module.

## Bounded Flexporter evaluation

The [documented extension](https://github.com/synthetichealth/synthea/wiki/Flexporter)
supports `profiles` and `set_values`; `apply_profiles` is not a documented key.
It could attach meta.profile, but cannot remove the need for coherent identity
allocation, complete-graph selection and the summary mapping here. Python owns
mapping to avoid maintaining two transformation layers. Synthea is unmodified.
