# nehr-synth

A small Python/Textual terminal application that generates and inspects synthetic
Sri Lankan FHIR R4 datasets. Generation and full-resource validation run locally;
online terminology checking is the default. No NEHR sender or registry client is
included. FHIR JSON is the canonical output; spreadsheets are intentionally deferred.

**Target: FHIR R4 4.0.1 · fhir.lk.nehr 0.1.0 · Client Registry 0.1.0.**
The exact package closure and bootstrap resolutions are in [ig-lock.json](ig-lock.json).
These are development publications. **Receiver compatibility is unconfirmed**;
a receiver owner must confirm accepted versions, structures, terminology and test
identifier/GN conventions before a deployment compatibility claim can be made.
The separate older `lk-nehr-fhir-ips` contract is outside scope.

## Start with a container

One Linux OCI image supports Docker and Podman on Linux and their Linux VMs on
Windows/macOS. It includes Python 3.12.14, Java 21.0.12.1+1, unchanged Synthea
v4.0.0, HL7 Validator 6.10.4, and checksum-verified definition archives.
Build locally from this directory:

```sh
docker build -t localhost/nehr-synth:local .
# Or: podman build -t localhost/nehr-synth:local .
```

POSIX shell, including a path containing spaces:

```sh
mkdir -p "$PWD/synthetic output"
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$PWD/synthetic output:/data" localhost/nehr-synth:local
podman run --rm -it --userns=keep-id:uid=1000,gid=1000 --user=1000:1000 \
  -v "$PWD/synthetic output:/data:Z" localhost/nehr-synth:local
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force 'synthetic output' | Out-Null
$outDir = (Resolve-Path 'synthetic output').Path
docker run --rm -it --mount "type=bind,source=$outDir,target=/data" localhost/nehr-synth:local
podman run --rm -it --userns=keep-id:uid=1000,gid=1000 --user=1000:1000 -v "${outDir}:/data" localhost/nehr-synth:local
```

The no-argument entrypoint opens the terminal app. Tab/Shift+Tab navigate fields;
F1 shows help; Escape or Ctrl+C cancels a run; Ctrl+Q quits. The three tabs contain
generation, progress/results and saved-run inspection/export. Settings exposes
tool locations, the terminology endpoint, fixture paths and synthetic conventions.
The Generate button starts a worker so Java never blocks the UI. After a run,
inspect its findings or select a patient to inspect linked FHIR. Re-export copies
saved resources and evidence without regenerating them.

Headless examples:

```sh
docker run --rm -v "$PWD/synthetic output:/data" localhost/nehr-synth:local \
  generate --patients 10 --seed 42 --output /data/runs
podman run --rm --userns=keep-id:uid=1000,gid=1000 --user=1000:1000 -v "$PWD/synthetic output:/data:Z" localhost/nehr-synth:local \
  generate --patients 1 --preset outpatient --output /data/runs
docker run --rm --network=none -v "$PWD/synthetic output:/data" localhost/nehr-synth:local \
  generate --patients 10 --terminology offline --output /data/offline
```

Output survives container removal through `/data`. Default generated runs live
under `/data/runs`. Use a unique output destination when re-exporting. No ports,
privileged mode or Docker socket are needed. Rootless Podman uses `--userns=keep-id:uid=1000,gid=1000 --user=1000:1000`
to map the host owner to the image user and preserve file ownership; SELinux hosts may need the private `:Z` mount label
(or `:z` for intentionally shared mounts). Docker Linux users can pass their UID/GID.
Writable validator caches default to `/tmp/nehr-cache`, independently of HOME.
For reuse, mount a separate writable cache and set `NEHR_CACHE` to that mount.
Never run concurrent validators against the same writable cache.

To mount a saved configuration and fixtures read-only, place these three files
in a host directory `test inputs`: `run.toml`, `names.json`, `geography.csv`.
The minimal `run.toml` can contain:

```toml
patients = 10
reference_date = "2026-01-01"
names = "names.json"
geography = "geography.csv"
output = "/data/runs"
```

```sh
docker run --rm -v "$PWD/synthetic output:/data" \
  -v "$PWD/test inputs:/inputs:ro" localhost/nehr-synth:local generate --config /inputs/run.toml
```

```powershell
$inputDir = (Resolve-Path 'test inputs').Path
docker run --rm --mount "type=bind,source=$outDir,target=/data" `
  --mount "type=bind,source=$inputDir,target=/inputs,readonly" `
  localhost/nehr-synth:local generate --config /inputs/run.toml
```

Use the corresponding bundled fixture files from `src/nehr_synth/data/`. Real
reference geography may be supplied using the same CSV columns, with its source
and precise code scheme recorded. Do not substitute GN numbers and census codes.
The shipped `examples/run.toml` is for a source checkout; its relative paths
deliberately reference the source fixtures and developer tool cache.

## Native developer workflow

Containers are the supported distribution. Native execution is a tested developer
convenience on the combinations documented below. Install `uv` and Java 21, then:

```sh
uv sync --frozen --python 3.12.14
uv run nehr-synth setup                  # explicit public artifact downloads
uv run nehr-synth doctor
uv run nehr-synth                        # terminal UI
uv run nehr-synth generate --config examples/run.toml
uv run nehr-synth generate --patients 37 --terminology offline
```

`setup` checks every archive/JAR hash and fails on changes. It never fetches
moving IG builds during generation. Java can be selected with `NEHR_JAVA`;
`NEHR_TOOLS` selects the artifact directory. Linux developers/CI can install the
exact locked JRE with `uv run python scripts/install_java.py .tools/java-runtime`
and set `NEHR_JAVA` to its `bin/java`. On Windows, a JRE extracted beneath
`.tools/java/` is detected automatically; otherwise use Java on PATH.
Synthea is never invoked or required to construct demographics. Java and the
validator are required for a run to receive an IG passed result.

All commands work without a terminal. With no arguments and no TTY, help is
printed instead of opening an interactive app. Exit codes: **0** passed/success,
**1** invalid data or unexpected negative outcome, **2** incomplete validation or
cancellation, **3** configuration/execution failure. `doctor` returns 2 if required
dependencies are unavailable. Negative cases return 0 only when the intended
failure is observed, which is not a data-valid result.

## Configurations and saved runs

The CLI and TUI use one flat, versioned TOML model. CLI flags override file values,
which override defaults. Unknown keys and invalid combinations fail. Relative
paths resolve against the configuration file. The reference date defaults to
**2026-01-01**, never today's date. The default is 100 adults, seed 42; any positive
count within configured identifier capacities is accepted. Inspect
[examples/run.toml](examples/run.toml) for a ten-patient example.

The manifest reconciles requested patients, generated candidates, selected/exported
patients, resource/identifier counts, GN assignments, references, input hashes,
and validation. Patient groups are conservative: shared or unattributed graph
failures affect every patient. Counts refer to distinct resources, not repeated
Bundle entries. Positive generation never drops invalid patients to report success.

Each completed run contains:

```text
run.toml                 effective configuration
inputs/                  exact fixture and lock snapshots
fhir/                    individual canonical FHIR R4 JSON resources
manifest.json            counts, IDs, dependencies, hashes and provenance
validation-input.json    collection Bundle providing full graph validation context
validator-outcome.json   raw HL7 OperationOutcome
validation.json/.txt     structured and readable checks/findings
validator.log            actual Java validator diagnostics and loaded packages
terminology.log          online terminology requests/responses, when used
```

Completed positives are promoted atomically from staging into `completed/<run-id>`.
Failed/incomplete runs remain under clearly named directories with partial
resources and diagnostics. Cancel stops the owned Java process. Existing runs
are never implicitly overwritten. The collection Bundle is local validation
packaging, not a submission contract or a discharge document.

```sh
uv run nehr-synth validate --run runs/completed/RUN_ID --terminology online
uv run nehr-synth export --run runs/completed/RUN_ID --output exported-copy
uv run nehr-synth mutate --run runs/completed/RUN_ID --case address-missing-district
```

Revalidation appends evidence under `checks/`; it preserves the original evidence.
Re-export verifies canonical file hashes, IDs, counts and references. Input
snapshots allow a copied run to be revalidated after specifying the local
`--tools` directory. Operational run IDs, timestamps, paths, log timings, and
remote terminology responses are not deterministic. Canonical resource JSON is
repeatable for identical seeds, versions, fixtures and configuration. Different
seeds need not produce disjoint identities.

## Supported profile coverage

| Resource/profile | Generates and validates | Scope |
| --- | --- | --- |
| `LKPatient` | Yes | Demographics and outpatient |
| `LKAddress`, `lk-gn-extension` | Yes, through Patient | Exact GN `valueCode`, required address fields |
| `LKEncounter` | Yes | One selected screening encounter per patient |
| `LKBloodGlucose` | Yes | Synthea LOINC 2345-7, UCUM mg/dL; no relabeling/conversion |
| `LKPractitioner` | Yes | Shared synthetic screening author |
| `LKEncounterSummary` | Yes | Standalone Composition; `Encounter Output` section |
| `LKCondition` | Disabled | R4 ICD-10 example ValueSet rejects realistic codes |
| `LKVitalSignsHemoglobin` | No | HbA1c profile reviewed, not emitted |
| Discharge/facility/other profiles | No | Dependencies are locked, but generation is not implemented |

The outpatient scenario is deliberately artificial adult glucose screening with
no diagnosis required. Synthea performs clinical simulation using a small module
and coherent local input CSVs. Source birth dates, visit chronology and measured
values/units survive localization. At most three deterministic batches replenish
unsuitable candidates; a shortfall fails visibly. This is not calibrated Sri
Lankan epidemiology. Full source simulation is retained in its run for inspection;
the manifest names omitted resource categories. Flexporter was evaluated; Python
owns mappings to keep a single transformation layer.

## Identity and validation limits

The default identity-testing preset enables NIC, PHN, passport and GN; this is
coverage-oriented and does not model real identifier prevalence. Switch fields
off individually, while retaining at least one identifier. Pediatric demographic
configurations must disable NIC. Names preserve authored family/given/full text,
including Sinhala/Tamil, with no inference of attributes from names.

* **NIC:** unique twelve-digit structural fixtures. National DOB/sex/allocation
  semantics are not verified; realistic mode is disabled. No invented checksum.
* **PHN:** configured four-character test POI, six-character recommended alphabet,
  Regenstrief checksum verified against OpenMRS numeric/alphabetic vectors. Capacity
  is capped at one million per POI; `phn_issued` accounts for configured prior usage.
  `TEST` is not an officially reserved prefix. Dataset uniqueness is guaranteed,
  but there is no shared allocation registry or proof of issuance/global uniqueness.
* **Passport:** configurable prefix and padded serial, default `TEST-P0000001`.
  This is a synthetic convention, not nationally verified passport formatting.
* **GN:** synthetic fixture rows by default; a sourced reference CSV is supported.
  The published extension has no ValueSet binding, so IG validation cannot certify
  official GN membership. DS/GN names and provenance remain in the manifest.

IG conformance, identifier-format checks and registry validity are separate
results. An IG pass does not imply national NIC validity or receiver acceptance.
All exported resources receive actual HL7 validation in a complete collection
graph; Python checks do not replace profile, slicing or terminology validation.
Warnings stay visible. Missing packages, crashes and unavailable terminology are
incomplete rather than passed. Online checking sends terminology operations to
the configured endpoint (default `https://tx.fhir.org/r4`); it does not upload
whole patient datasets to a remote validator. Server version, lookup time, loaded
package set and cache hashes are recorded. External responses can change.

Offline uses the verified validator options `-tx n/a -no-http-access`; container
`--network=none` additionally enforces network isolation. Actual tests show the
demographic graph passes offline. Outpatient offline validation is **incomplete**
because the validator reports it cannot validate UCUM units without terminology
services, even with a previously populated online cache. This limitation is not
converted to success. Patient narrative and unregistered synthetic URI warnings
are retained in the reports.

Enabled negative mutations are `phn-bad-checksum`, `gn-wrong-value-type`,
`address-missing-district`, and `broken-patient-reference` (clinical baseline).
Each creates one traceable fault under `negative/`, preserves the positive graph,
records changed paths/baseline hash/expected layer/observed outcome, and is excluded
from positive counts. PHN failures are application-level; the IG does not encode
the checksum. `nic-dob-mismatch` stays disabled with the unverified realistic NIC mode.

See [RESEARCH.md](RESEARCH.md) for identifier sources, upstream inconsistencies,
the exact ICD-10 blocker, and configuration provenance.

## Tests, CI and releases

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -m 'not integration' --cov --cov-report=xml
uv run pytest -m integration --basetemp=integration-output
```

The integration selection requires installed pinned tools; it fails when tools
or the online terminology service are unavailable. It never silently skips those
checks. Unit tests include deterministic identities, independent checksum vectors,
capacity, graph tampering, chronology, saved exports, real subprocess cancellation,
and Textual headless form/progress/cancel/inspect/export workflows. Coverage
includes branches and is enforced at **85%**, with no application modules excluded.

CI runs lightweight tests on Windows/macOS/Ubuntu, lint once, real Java tests on
Linux, and Docker/rootless Podman smoke tests. Pull requests exercise amd64;
main/tag runs exercise amd64 and arm64 via QEMU. Image builds and runtime tests
are distinct steps. Small failure reports are retained as artifacts.

Codecov upload uses a pinned action and GitHub OIDC authentication, with
project/patch thresholds and upload failures visible in CI. No stored upload
token is required. Repository owners must connect the Codecov GitHub app.
See the [Codecov OIDC instructions](https://github.com/codecov/codecov-action#using-oidc).
Local tests alone do not establish a successful hosted upload.

Version tags matching `pyproject.toml` invoke the same CI checks before publishing
wheel/sdist/checksums/notes to GitHub Releases and amd64/arm64 images to GHCR.
Only the release job has contents/packages write permission; it uses GITHUB_TOKEN.
No PyPI credentials or NEHR credentials are used. Published images will use
`ghcr.io/aswikinz/synthetic-health-lk:v0.1.0` and a commit tag when a tested tag is
pushed; a release has not been published by this build session.

## Recorded evidence and platform coverage

[evidence/README.md](evidence/README.md) records actual checks, and
[examples/sample-run](examples/sample-run) contains a ten-patient synthetic sample
with real validator output. Compatibility statements are limited to that evidence.

Before release, manually check Docker Desktop and Podman Machine on Windows and
macOS: terminal launch/resize, generation, cancellation while Java is running,
clean exit, and persistence through a mounted path containing spaces. The Python
OS matrix is not evidence that those host/container combinations were tested.
No native installers, Compose services, database or background queue are needed.
