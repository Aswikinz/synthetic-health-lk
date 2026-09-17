# Contract review — 2026-09-17

The application targets **FHIR R4 4.0.1, fhir.lk.nehr 0.1.0**, using
Client Registry/Provider Registry/Facility Registry 0.1.0. Receiver compatibility
is **unconfirmed**. No receiver or registry was contacted. The older IPS guide is
outside scope. These development packages declare publication limitations.

`ig-lock.json` is the reviewed dependency closure. All four national archive
hashes match the supplied research brief. `dev` dependencies resolve to exact,
byte-identical 0.1.0 archives in a private validator cache. Published canonicals,
snapshots and differentials remain unchanged. Update changed checksums only after
reviewing the upstream contract. Do not run `scripts/research.py` as routine setup.

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

## Bounded Flexporter evaluation

The [documented extension](https://github.com/synthetichealth/synthea/wiki/Flexporter)
supports `profiles` and `set_values`; `apply_profiles` is not a documented key.
It could attach meta.profile, but cannot remove the need for coherent identity
allocation, complete-graph selection and the summary mapping here. Python owns
mapping to avoid maintaining two transformation layers. Synthea is unmodified.
