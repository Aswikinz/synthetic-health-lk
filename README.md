# Sri Lankan synthetic FHIR terminal

Generate, validate and inspect local synthetic Sri Lankan FHIR R4 data in a terminal.
The application targets the [NEHR Implementation Guide hosted at ig.hiu.lk](https://ig.hiu.lk/fhir/nehr/index.html)
and its registry guides. `fhir.lk.nehr` is the published **package ID**, not the
website address. The pinned target is NEHR IG 0.1.0 / FHIR R4 4.0.1.

## Windows setup and launch

Install Git, [Python 3.12 or newer](https://www.python.org/downloads/windows/),
and [Java 21](https://adoptium.net/temurin/releases/?version=21). Make sure `git`,
`python` and `java` are available in a new PowerShell window.

For a fresh checkout:

```powershell
git clone https://github.com/Aswikinz/synthetic-health-lk.git
cd synthetic-health-lk/nehr-synth
```

If you already have the repository, open PowerShell in its `nehr-synth` folder.
Then install the dependencies and download the pinned validator, Synthea and IG packages:

```powershell
python -m pip install uv
python -m uv sync --frozen --python 3.12.14
python -m uv run nehr-synth setup
python -m uv run nehr-synth doctor
python -m uv run nehr-synth
```

Initial setup requires internet access. Once setup is complete, only the final
launch command is needed. `doctor` reports missing tools or definitions.

## Generate your first dataset

In the terminal app, set **Patients** to `10`, choose **Demographics** and **Offline**
terminology, then select **Generate patients**. Select **Inspect result** when it
finishes. Use Tab to navigate, Escape to cancel a run, and Ctrl+Q to quit.

To generate directly from PowerShell instead:

```powershell
python -m uv run nehr-synth generate --patients 10 --terminology offline
```

Successful native runs are saved in `nehr-synth/runs/completed/<run-id>/`.
The `fhir/` subfolder contains the resources; `validation.txt` contains the results.
Outpatient datasets use Synthea and need online terminology checks for full validation.
All identities are synthetic; NICs are structural fixtures and receiver compatibility
remains unconfirmed. Codecov setup does not affect local application use.

## Docker or Podman

Containers include Python, Java and the pinned tools. With a running Linux container
engine, open PowerShell in `nehr-synth` and run:

```powershell
docker build -t localhost/nehr-synth:local .
New-Item -ItemType Directory -Force 'synthetic output' | Out-Null
$outDir = (Resolve-Path 'synthetic output').Path
docker run --rm -it --mount "type=bind,source=$outDir,target=/data" localhost/nehr-synth:local
```

Output persists under `synthetic output/runs/`. See the
[application README](nehr-synth/README.md#start-with-a-container) for Podman,
Linux/macOS shell commands, configuration, profile coverage and validation evidence.
