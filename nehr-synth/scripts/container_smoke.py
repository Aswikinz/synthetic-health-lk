"""Linux Docker/Podman runtime and PTY smoke checks (also under QEMU)."""

import json
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time
from pathlib import Path
from uuid import uuid4

engine, image, architecture = sys.argv[1:]
output = Path("container-output") / engine / architecture / uuid4().hex[:8]
output.mkdir(parents=True, exist_ok=True)
command = [engine, "run", "--rm", "--platform", f"linux/{architecture}"]
if engine == "podman":
    command += ["--userns=keep-id:uid=1000,gid=1000", "--user=1000:1000"]
else:
    command += ["--user", f"{os.getuid()}:{os.getgid()}"]
mount = ["-v", f"{output.resolve()}:/data"]

# No arguments must open the application, accept a keyboard quit and restore the PTY.
master, slave = pty.openpty()
termios.tcsetwinsize(slave, (40, 100))
process = subprocess.Popen(
    command + ["-it"] + mount + [image],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    env={**os.environ, "TERM": "xterm-256color"},
)
os.close(slave)
captured = b""
deadline = time.monotonic() + 30
try:
    while time.monotonic() < deadline and b"Receiver" not in captured:
        if select.select([master], [], [], 1)[0]:
            captured += os.read(master, 65536)
        if process.poll() is not None:
            break
    assert b"Receiver" in captured, (
        f"TUI failed to start: {captured[-5000:].decode(errors='replace')}"
    )
    os.write(master, b"\x11")  # Ctrl+Q
    deadline = time.monotonic() + 45
    while process.poll() is None and time.monotonic() < deadline:
        # Drain terminal output while quitting; an unread PTY can block terminal restoration.
        if select.select([master], [], [], 0.2)[0]:
            try:
                os.read(master, 65536)
            except OSError:
                break
    assert process.wait(timeout=5) == 0
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    os.close(master)

subprocess.run(
    command
    + mount
    + [
        "--network=none",
        image,
        "generate",
        "--patients",
        "10",
        "--terminology",
        "offline",
        "--output",
        "/data/demographics",
    ],
    check=True,
)
subprocess.run(
    command
    + mount
    + [
        image,
        "generate",
        "--patients",
        "1",
        "--preset",
        "outpatient",
        "--output",
        "/data/outpatient",
    ],
    check=True,
)
for preset, count in [("demographics", 10), ("outpatient", 1)]:
    manifests = list((output / preset / "completed").glob("*/manifest.json"))
    assert len(manifests) == 1, f"Expected one successful {preset} run"
    manifest = json.loads(manifests[0].read_text())
    assert manifest["counts"]["Patient"] == count
    assert manifest["validation"]["ig"] == "passed"
    for entry in manifest["resources"]:
        resource = json.loads((manifests[0].parent / entry["file"]).read_text())
        assert resource["id"] == entry["id"]

# Cancellation must stop an owned Java process and retain incomplete output.
process = subprocess.Popen(
    command
    + mount
    + [
        "--network=none",
        image,
        "generate",
        "--patients",
        "10",
        "--terminology",
        "offline",
        "--output",
        "/data/cancel",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
deadline = time.monotonic() + 180
try:
    while time.monotonic() < deadline:
        if any(p.stat().st_size for p in (output / "cancel").glob(".staging-*/validator.log")):
            break
        if process.poll() is not None:
            raise AssertionError("Cancellation run exited before Java started")
        time.sleep(0.1)
    else:
        raise AssertionError("Validator did not start before cancellation deadline")
    process.send_signal(signal.SIGINT)
    stdout, _ = process.communicate(timeout=30)
    assert process.returncode == 2, stdout
    incomplete = list((output / "cancel" / "incomplete").glob("*/manifest.json"))
    assert len(incomplete) == 1
    assert json.loads(incomplete[0].read_text())["status"] == "incomplete"
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)


print(
    f"{engine} linux/{architecture}: generation, validation, cancellation, "
    "persistence and TUI passed"
)
