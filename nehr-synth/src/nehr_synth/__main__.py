"""Small argparse dispatch; the TUI and CLI call the same pipeline."""

import argparse
import json
import signal
import sys
from pathlib import Path

from .config import load
from .mutate import CASES, mutate
from .pipeline import EXIT_CODES, export_run, generate, revalidate
from .runtime import Cancelled, Control, doctor, read_json, setup


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="nehr-synth", description="Synthetic Sri Lankan FHIR R4 datasets"
    )
    commands = root.add_subparsers(dest="command")
    for command in ("generate", "doctor", "setup"):
        child = commands.add_parser(command)
        child.add_argument("--config", type=Path)
        child.add_argument("--patients", type=int)
        child.add_argument("--preset", choices=("demographics", "outpatient"))
        child.add_argument("--seed", type=int)
        child.add_argument("--reference-date")
        child.add_argument("--output")
        child.add_argument("--tools")
        child.add_argument("--terminology", choices=("online", "offline"))
        child.add_argument("--terminology-url")
        for field in ("nic", "phn", "passport", "gn"):
            child.add_argument(f"--{field}", action=argparse.BooleanOptionalAction, default=None)
    validate = commands.add_parser("validate")
    validate.add_argument("--run", type=Path, required=True)
    validate.add_argument("--terminology", choices=("online", "offline"))
    validate.add_argument("--tools")
    export = commands.add_parser("export")
    export.add_argument("--run", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    negative = commands.add_parser("mutate")
    negative.add_argument("--run", type=Path, required=True)
    negative.add_argument("--case", choices=CASES, required=True)
    return root


def main(argv=None) -> int:
    root = parser()
    args = root.parse_args(argv)
    if args.command is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            root.print_help()
            return 0
        from .app import SynthApp

        SynthApp().run()
        return 0
    control = Control()
    previous = signal.signal(signal.SIGINT, lambda *_: control.cancel())
    previous_term = signal.signal(signal.SIGTERM, lambda *_: control.cancel())
    try:
        values = vars(args).copy()
        command = values.pop("command")
        if command in {"generate", "doctor", "setup"}:
            config = load(values.pop("config"), **values)
            if command == "setup":
                setup(config)
                return 0
            if command == "doctor":
                findings = doctor(config)
                print(json.dumps(findings, indent=2))
                return (
                    0
                    if all(
                        findings[k] == "available"
                        for k in ("fixtures", "java", "validator", "definitions", "synthea")
                        if k in findings
                    )
                    else 2
                )
            directory = generate(config, control=control)
            manifest = read_json(directory / "manifest.json")
            return 3 if manifest.get("execution_error") else EXIT_CODES[manifest["status"]]
        if command == "validate":
            result = revalidate(
                args.run.resolve(), control, terminology=args.terminology, tools=args.tools
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_CODES[result["status"]]
        if command == "export":
            print(export_run(args.run, args.output))
            return 0
        directory = mutate(args.run.resolve(), args.case, control)
        result = read_json(directory / "mutation.json")
        print(f"{result['result']}: {directory}")
        if control.event.is_set():
            return 2
        return 0 if result["result"] == "expected failure observed" else 1
    except Cancelled as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 3
    finally:
        signal.signal(signal.SIGINT, previous)
        signal.signal(signal.SIGTERM, previous_term)


if __name__ == "__main__":
    raise SystemExit(main())
