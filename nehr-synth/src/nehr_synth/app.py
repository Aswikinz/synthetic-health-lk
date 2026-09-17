"""Compact Textual UI over the same saved configuration and pipeline."""

import json
import time
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from .config import Config, load, save
from .mutate import CASES, mutate
from .pipeline import export_run, generate, open_run
from .runtime import Control, read_json

FORM_FIELDS = (
    "patients",
    "age_min",
    "age_max",
    "seed",
    "reference_date",
    "phn_prefix",
    "geography",
    "output",
)
SETTINGS_FIELDS = (
    "terminology_url",
    "tools",
    "ig_lock",
    "names",
    "phn_prefix_provenance",
    "phn_issued",
    "passport_prefix",
    "passport_width",
)
INTEGERS = {"patients", "age_min", "age_max", "seed", "phn_issued", "passport_width"}


class Settings(ModalScreen):
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="settings-panel"):
            yield Label("Settings · synthetic conventions")
            for name in SETTINGS_FIELDS:
                yield Label(name.replace("_", " ").capitalize())
                yield Input(str(getattr(self.app.config, name)), id="setting-" + name)
            yield Button("Apply", id="apply-settings")
            yield Button("Close", id="close-settings")
            yield Static("", id="settings-error")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-settings":
            self.dismiss()
        elif event.button.id == "apply-settings":
            try:
                values = {
                    name: self.query_one("#setting-" + name, Input).value
                    for name in SETTINGS_FIELDS
                }
                values = {k: int(v) if k in INTEGERS else v for k, v in values.items()}
                from dataclasses import replace

                self.app.config = replace(self.app.config, **values).check()
                self.dismiss()
            except ValueError as error:
                self.query_one("#settings-error", Static).update(str(error))


class SynthApp(App):
    TITLE = "nehr-synth"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+c", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel run"),
        ("f1", "help", "Help"),
    ]
    CSS = """
    Screen { background: $surface; }
    #contract { height: auto; padding: 0 1; color: $accent; }
    #form, #inspection { padding: 1 2; }
    Label { margin-top: 1; }
    .buttons { height: auto; margin: 1 0; }
    .buttons Button { margin-right: 1; }
    #form-error { color: $error; height: auto; }
    #status { height: auto; padding: 1; }
    #progress-log { height: 1fr; }
    #patients-table { height: 10; }
    #json { min-height: 12; }
    #settings-panel {
        width: 80%; height: 90%; background: $panel; padding: 1 2; border: solid $accent;
    }
    Settings { align: center middle; }
    """

    def __init__(self, config: Config | None = None):
        super().__init__()
        self.config = config or load()
        self.control = Control()
        self.busy = False
        self.current_run: Path | None = None
        self.resources = []
        self.started = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "FHIR R4 · fhir.lk.nehr 0.1.0 · Client Registry 0.1.0 | Receiver: unconfirmed",
            id="contract",
        )
        with TabbedContent(id="tabs"):
            with TabPane("Generate", id="generate-tab"):
                with VerticalScroll(id="form"):
                    yield Static(
                        "Coverage-oriented synthetic identities. NIC: structural-only.\n"
                        "FHIR JSON always exported. Clinical totals depend on the preset."
                    )
                    for name in FORM_FIELDS:
                        yield Label(name.replace("_", " ").capitalize())
                        yield Input(str(getattr(self.config, name)), id=name)
                    yield Label("Dataset preset")
                    yield Select(
                        [
                            ("Demographics · Python only", "demographics"),
                            ("Outpatient · glucose screening only", "outpatient"),
                        ],
                        value=self.config.preset,
                        allow_blank=False,
                        id="preset",
                    )
                    for name in ("nic", "phn", "passport", "gn"):
                        yield Checkbox(name.upper(), value=getattr(self.config, name), id=name)
                    yield Label("Terminology validation")
                    yield Select(
                        [
                            ("Online (local validation, remote terminology)", "online"),
                            ("Offline (no HTTP; missing checks → incomplete)", "offline"),
                        ],
                        value=self.config.terminology,
                        allow_blank=False,
                        id="terminology",
                    )
                    yield Label("Saved configuration path")
                    yield Input("run.toml", id="config-path")
                    with Horizontal(classes="buttons"):
                        yield Button("Load", id="load")
                        yield Button("Save", id="save")
                        yield Button("Settings", id="settings")
                    yield Static("", id="form-error")
                    yield Button("Generate patients", variant="primary", id="generate")
            with TabPane("Progress / results", id="progress-tab"):
                yield Static("No run started. Validation: not checked.", id="status")
                yield RichLog(max_lines=200, wrap=True, id="progress-log")
                with Horizontal(classes="buttons"):
                    yield Button("Cancel", id="cancel", disabled=True)
                    yield Button("Inspect result", id="inspect-result", disabled=True)
            with TabPane("Inspect / export", id="inspect-tab"):
                with VerticalScroll(id="inspection"):
                    yield Label("Saved run directory")
                    yield Input("", id="run-path")
                    with Horizontal(classes="buttons"):
                        yield Button("Open run", id="open-run")
                        yield Button("Browse output", id="browse")
                    yield Select([], prompt="Saved runs", id="saved-runs")
                    yield Input("", placeholder="Search patient name or ID", id="search")
                    yield DataTable(id="patients-table", cursor_type="row")
                    yield TextArea("", read_only=True, id="json")
                    yield Label("Export destination (must not exist)")
                    yield Input("", id="export-path")
                    yield Button("Re-export saved FHIR", id="export")
                    yield Select(
                        [(c, c) for c in CASES], value=CASES[0], allow_blank=False, id="mutation"
                    )
                    yield Button("Create negative variant", id="mutate")
        yield Footer()

    def on_mount(self):
        self.query_one("#patients-table", DataTable).add_columns("Patient ID", "Name", "DOB")
        self.set_interval(1, self.tick)

    def form_config(self) -> Config:
        from dataclasses import asdict

        values = asdict(self.config)
        for name in FORM_FIELDS:
            value = self.query_one("#" + name, Input).value
            values[name] = int(value) if name in INTEGERS else value
        for name in ("preset", "terminology"):
            values[name] = self.query_one("#" + name, Select).value
        for name in ("nic", "phn", "passport", "gn"):
            values[name] = self.query_one("#" + name, Checkbox).value
        return load(**values)

    def show_config(self):
        for name in FORM_FIELDS:
            self.query_one("#" + name, Input).value = str(getattr(self.config, name))
        for name in ("preset", "terminology"):
            self.query_one("#" + name, Select).value = getattr(self.config, name)
        for name in ("nic", "phn", "passport", "gn"):
            self.query_one("#" + name, Checkbox).value = getattr(self.config, name)

    def on_button_pressed(self, event: Button.Pressed):
        action = event.button.id
        try:
            if action == "generate" and not self.busy:
                self.config = self.form_config()
                self.query_one("#form-error", Static).update("")
                self.control = Control()
                self.started = time.monotonic()
                self.set_busy(True)
                self.query_one("#tabs", TabbedContent).active = "progress-tab"
                self.call_after_refresh(self.show_progress)
                self.generate_worker()
            elif action == "cancel":
                self.action_cancel()
            elif action == "load":
                self.config = load(Path(self.query_one("#config-path", Input).value))
                self.show_config()
            elif action == "save":
                self.config = self.form_config()
                save(self.config, Path(self.query_one("#config-path", Input).value))
                self.notify("Configuration saved")
            elif action == "settings":
                self.push_screen(Settings())
            elif action in {"open-run", "inspect-result"}:
                path = (
                    self.current_run
                    if action == "inspect-result"
                    else Path(self.query_one("#run-path", Input).value)
                )
                if path:
                    self.inspect(path)
            elif action == "browse":
                paths = sorted(Path(self.config.output).glob("*/*/manifest.json"))
                self.query_one("#saved-runs", Select).set_options(
                    [(str(p.parent), str(p.parent)) for p in paths]
                )
            elif action == "export" and self.current_run:
                export_run(self.current_run, Path(self.query_one("#export-path", Input).value))
                self.notify("Saved FHIR exported; no regeneration")
            elif action == "mutate" and self.current_run and not self.busy:
                self.control = Control()
                self.set_busy(True)
                self.mutate_worker(self.current_run, str(self.query_one("#mutation", Select).value))
        except (ValueError, OSError, KeyError) as error:
            self.query_one("#form-error", Static).update(str(error))
            self.notify(str(error), severity="error", timeout=10)

    def set_busy(self, value: bool):
        self.busy = value
        self.query_one("#generate", Button).disabled = value
        self.query_one("#mutate", Button).disabled = value
        self.query_one("#cancel", Button).disabled = not value

    def show_progress(self):
        self.query_one("#tabs", TabbedContent).active = "progress-tab"
        self.query_one("#cancel" if self.busy else "#inspect-result", Button).focus()

    def report_progress(self, text: str):
        self.query_one("#progress-log", RichLog).write(text)
        self.query_one("#status", Static).update(text)

    @work(thread=True, exit_on_error=False)
    def generate_worker(self):
        try:
            path = generate(
                self.config,
                lambda text: self.call_from_thread(self.report_progress, text),
                self.control,
            )
            self.current_run = path
            self.call_from_thread(self.result_ready)
        finally:
            self.call_from_thread(self.set_busy, False)

    def result_ready(self):
        self.query_one("#inspect-result", Button).disabled = False
        manifest = read_json(self.current_run / "manifest.json")
        self.query_one("#status", Static).update(
            f"{manifest['status'].upper()} · Requested {manifest['requested_patients']} · "
            f"Candidates {manifest['generated_candidates']} · "
            f"Exported {manifest.get('exported_patients', 0)}\n"
            f"Resources: {manifest['counts']}\n"
            f"Identifiers: {manifest.get('identifier_counts', {})} · "
            f"GN patients: {manifest.get('gn_populated_patients', 0)}\n"
            "NIC: structural-only · Registry: not checked · Receiver: unconfirmed"
        )

    @work(thread=True, exit_on_error=False)
    def mutate_worker(self, path: Path, case: str):
        try:
            destination = mutate(path, case, self.control)
            result = read_json(destination / "mutation.json")
            self.call_from_thread(self.notify, result["result"])
        except (ValueError, OSError) as error:
            self.call_from_thread(self.notify, str(error), severity="error")
        finally:
            self.call_from_thread(self.set_busy, False)

    def tick(self):
        if self.busy:
            self.sub_title = f"Working · {int(time.monotonic() - self.started)}s"
        else:
            self.sub_title = "Local synthetic data"

    def action_cancel(self):
        if self.busy:
            self.control.cancel()
            self.report_progress("Cancelling owned process; partial output will remain incomplete")

    def action_quit(self):
        self.control.cancel()
        if self.busy:
            self.notify("Cancelling; quit again once the run stops")
        else:
            self.exit()

    def action_help(self):
        self.notify(
            "Tab / Shift+Tab: navigate. Escape: cancel. "
            "Open a saved run to inspect FHIR and findings.",
            timeout=12,
        )

    def inspect(self, path: Path):
        try:
            manifest, resources, _ = open_run(path)
        except (OSError, ValueError, KeyError) as error:
            manifest, resources = read_json(path / "manifest.json"), []
            manifest = {**manifest, "inspection_issue": str(error)}
        self.current_run, self.resources = path, resources
        self.query_one("#run-path", Input).value = str(path)
        self.query_one("#json", TextArea).load_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        self.filter_patients("")
        self.query_one("#tabs", TabbedContent).active = "inspect-tab"

    def filter_patients(self, query: str):
        table = self.query_one("#patients-table", DataTable)
        table.clear()
        for resource in self.resources:
            if resource["resourceType"] == "Patient":
                name = resource["name"][0]["text"]
                if query.lower() in (name + resource["id"]).lower():
                    table.add_row(resource["id"], name, resource["birthDate"], key=resource["id"])

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search" and self.is_mounted:
            self.filter_patients(event.value)

    def on_select_changed(self, event: Select.Changed):
        if event.select.id == "saved-runs" and event.value is not Select.BLANK:
            self.query_one("#run-path", Input).value = str(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        from .validate import references

        pid = event.row_key.value
        graph = [
            r
            for r in self.resources
            if r["id"] == pid or r.get("subject", {}).get("reference") == f"Patient/{pid}"
        ]
        linked = {ref for resource in graph for _, ref in references(resource)}
        graph += [
            resource
            for resource in self.resources
            if resource not in graph and f"{resource['resourceType']}/{resource['id']}" in linked
        ]
        self.query_one("#json", TextArea).load_text(json.dumps(graph, ensure_ascii=False, indent=2))
