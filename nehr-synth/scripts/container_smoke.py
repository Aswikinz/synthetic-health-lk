"""Linux Docker/Podman runtime and PTY smoke checks (also under QEMU)."""

import json
import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

engine, image, architecture = sys.argv[1:]
output = Path("container-output") / engine / architecture
output.mkdir(parents=True, exist_ok=True)
output.chmod(0o777)
command = [engine, "run", "--rm", "--platform", f"linux/{architecture}"]
if engine == "podman":
    command += ["--userns=keep-id"]
mount = ["-v", f"{output.resolve()}:/data"]
subprocess.run(command + mount + ["--network=none", image, "generate", "--patients", "10",
                                 "--terminology", "offline", "--output", "/data/demographics"], check=True)
subprocess.run(command + mount + [image, "generate", "--patients", "1", "--preset", "outpatient",
                                 "--output", "/data/outpatient"], check=True)
for preset, count in [("demographics", 10), ("outpatient", 1)]:
    manifests = list((output / preset / "completed").glob("*/manifest.json"))
    assert len(manifests) == 1, f"Expected one successful {preset} run"
    manifest = json.loads(manifests[0].read_text())
    assert manifest["counts"]["Patient"] == count
    assert manifest["validation"]["ig"] == "passed"
    for entry in manifest["resources"]:
        resource = json.loads((manifests[0].parent / entry["file"]).read_text())
        assert resource["id"] == entry["id"]

# No arguments must open the application, accept a keyboard quit and restore the PTY.
master, slave = pty.openpty()
process = subprocess.Popen(command + ["-it"] + mount + [image], stdin=slave, stdout=slave,
                           stderr=slave, env={**os.environ, "TERM": "xterm-256color"})
os.close(slave)
captured = b""
deadline = time.monotonic() + 30
try:
    while time.monotonic() < deadline and b"Receiver" not in captured:
        if select.select([master], [], [], 1)[0]:
            captured += os.read(master, 65536)
    assert b"Receiver" in captured, "TUI failed to start"
    os.write(master, b"\x11")  # Ctrl+Q
    assert process.wait(timeout=15) == 0
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    os.close(master)
print(f"{engine} linux/{architecture}: generation, validation, persistence and TUI passed")
