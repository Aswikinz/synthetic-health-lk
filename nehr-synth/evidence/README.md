# Validation and platform evidence — 2026-09-17

These are observed results, not an assertion of deployment acceptance.
The implementation and package hashes are versioned in Git; the package closure
is recorded in every saved run. Receiver compatibility remains **unconfirmed**.

## Python and Java

* Windows x64, Python **3.12.14**: **57 unit/TUI tests passed**, with **90.96%**
  branch-inclusive coverage and an enforced 85% minimum. Ruff checks passed.
* Linux amd64, Python **3.12.14**: **57 unit/TUI tests passed** in 17.61 seconds,
  with the same **90.96%** branch-inclusive coverage.
* Linux arm64 under QEMU, Python **3.12.14**: **57 unit/TUI tests passed** in
  74.42 seconds, with the same **90.96%** branch-inclusive coverage.
* Windows x64, Temurin **21.0.12.1+1**, Validator **6.10.4**, Synthea **v4.0.0**:
  **four real integration tests passed in 216.34 seconds**. Those tests run nine
  validator invocations, including online and offline modes, actual Synthea,
  two equivalent outpatient generations and all four enabled negative variants.
  There were no mocks or skipped missing-service/tool checks in that selection.

Actual positive results:

| Scenario | Canonical resources | IG result |
| --- | --- | --- |
| Demographics, online | 10 Patients | Passed; zero errors |
| Demographics, offline | 10 Patients | Passed; zero errors |
| Outpatient, online | 1 Patient, 1 Practitioner, 1 Encounter, 1 Observation, 1 Composition | Passed; zero errors |
| Outpatient, offline | Same five resource types | Incomplete: UCUM could not be checked without terminology services |

The canonical content of two same-seed Synthea runs compared equal. Warnings
about missing narrative and unregistered identifier URI definitions remain in
the evidence. The default NIC check is explicitly structural-only; national NIC
format validity is incomplete even when IG validation passes.

[negative-results.json](negative-results.json) records the baseline hashes,
changed paths, expected layers and actual diagnostics for all four enabled
mutations. Every intended failure was observed. A separate unit test ensures
an expected application fault cannot hide an incomplete/crashed validator.

The terminal tests cover form errors, saved configuration, settings, generation,
responsive cancellation, inspecting partial/completed runs, searching, resizing,
and re-export. The cancellation test waits for an explicit event rather than
assuming a fast machine. An unread PTY initially blocked the emulated terminal
quit test; the harness now drains output during terminal restoration.

## Definition and terminology gate

[condition-gate.json](condition-gate.json) records the actual online validator
rejection of `Condition/icd10-binding-probe.code`, using ICD-10 `E11`.
It resolves the required binding to **ICD-10 Codes | 4.0.1**, whose seven example
codes do not include E11. The exact R4 definition hash is included. The R5
definition in [icd-10-definitions.json](icd-10-definitions.json) was an exploratory
comparison only; it is not in the locked target validation environment.

The observed loaded package set was:

```text
hl7.fhir.r4.core#4.0.1
hl7.fhir.xver-extensions#0.1.0
hl7.terminology.r4#6.2.0          (validator bootstrap)
hl7.terminology.r4#6.5.0          (target terminology)
hl7.fhir.uv.extensions.r4#5.2.0
fhir.lk.clientregistry#0.1.0
fhir.lk.facilityregistry#0.1.0
fhir.lk.providerregistry#0.1.0
fhir.lk.nehr#0.1.0
```

Online terminology reported **FHIRsmith 0.13.2** at `https://tx.fhir.org/r4` in
this session. Raw logs and cache hashes are retained with local runs. This remote
server and its terminology releases can change independently of the seed.
No patient dataset was sent to a remote full-resource validator.

## Synthetic sample

[examples/sample-run](../examples/sample-run) contains exactly ten synthetic
patients and real HL7 output from a successful offline run. The sample manifest
and all ten committed FHIR file hashes were checked directly from Git blobs.
The effective generation settings are unchanged; the sample TOML uses portable
paths. Large operational logs were omitted from this small sample. Full local
runs retain them. `export` successfully reopened and copied the saved sample
without generation. Git attributes preserve the sample's original bytes.

## Container/host coverage

Containers were built as Linux OCI images for amd64 and arm64. arm64 execution
uses QEMU on an amd64 Windows/WSL host; it is not a native-arm benchmark.

| Combination | Evidence |
| --- | --- |
| Rootless Podman 5.8.6, Linux amd64 in WSL | Passed generation, actual validation, mounted-output persistence, Java cancellation and terminal startup/quit |
| Docker Engine 28.5.1, Linux amd64 in WSL | Passed the same runtime checks |
| Rootless Podman, Linux arm64/QEMU | Passed generation, actual validation, mounted-output persistence, Java cancellation and terminal startup/quit |
| Docker Engine, Linux arm64/QEMU | Passed generation, actual validation, mounted-output persistence, Java cancellation and terminal startup/quit |
| Docker Desktop on Windows/macOS | Not tested here; release manual check required |
| Podman Machine native Windows/macOS CLI | Not tested here; local Windows client connection was stale; WSL Podman was tested directly |
| macOS native Python/Java | Not tested locally; Python CI matrix configured, native Java not claimed |
| GitHub CI / Codecov hosted upload / GHCR release | Configured, not executed or published in this session |

The temporary Docker test daemon used cgroupfs and a private data/socket directory;
online containers used host networking, while offline containers used
`--network=none`. It did not change the host firewall or mount a Docker socket
into the app. The CI smoke job uses its normal Docker bridge networking.
No app container required privileged mode or published ports.
An additional offline Podman run passed with read-only custom fixtures and
both input/output host paths containing spaces.
The temporary Docker daemon was stopped after verification.

The CI matrix is configuration until it runs on GitHub. Desktop host startup,
resize, cancellation and output persistence remain explicit release checks;
neither a Python matrix nor an emulated Linux test proves those combinations.

## Artifacts

The source distribution excludes local tools, virtual environments and generated
run directories. Local wheel/source builds succeeded at approximately 52/84 KB.
Release notes/checksum generation was exercised with matching `v0.1.0` metadata.
`NOTICES.md` and MIT licensing are included in package metadata. Definition/JAR
checksums are enforced before use, including checks for modified extracted JSON
definitions. All action revisions and the multi-architecture base-image manifest
are pinned. Codecov uses an 85% project/patch threshold and surfaces upload failure.

## Pre-merge review

The first hosted run passed the real Java suite and macOS tests. It exposed a
Windows UI-test timing assumption and a Codecov authentication failure. The search
test now waits for its observable result, and uploads use GitHub OIDC instead of
an absent upload token. The review also fixed `doctor` returning success with a
missing outpatient simulator and made output-folder errors visible in the TUI.
Regression checks brought the local Windows suite to **60 passed**, **90.91%**
branch-inclusive coverage. Package licensing now follows the MIT license on main.
Final hosted results are available in the repository's GitHub Actions history.
