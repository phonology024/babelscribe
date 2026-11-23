"""CI check: when the app is killed, the engine and whisper-cli do not keep running.

    python desktop/scripts/check_orphans.py "<installed engine>" long.wav [FLAVOR]     (needs psutil)

A stand-in for the app starts the installed engine the way the app does (standard input a pipe it holds open and never
writes to, --exit-when-stdin-closes; on macOS and Linux its own process group) on a long recording. Once whisper-cli
is running, this script kills the stand-in only (SIGKILL / TerminateProcess: it gets no chance to clean up, as with a
crashed or force-quit app) and checks that the engine and every program it started are gone within 20 seconds.
FLAVOR is the whisper-cli flavour (default cpu; "default" leaves it to the engine, as on Apple Silicon)."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import psutil

WATCHED = ("whisper-cli", "ffmpeg", "babelscribe-engine")


def stand_in_for_the_app(engine: str, wav: str, flavor: str) -> None:
    cmd = [engine, wav, "-m", "tiny", "-l", "en", "-f", "txt", "--progress-json", "--exit-when-stdin-closes"]
    if flavor != "default":
        cmd += ["--flavor", flavor]
    kw = {} if os.name == "nt" else {"process_group": 0}
    engine_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    print(engine_process.pid, flush=True)
    time.sleep(900)               # holds the pipe open until it is killed


def running() -> list[str]:
    found = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        label = (p.info["name"] or "") + " " + (p.info["exe"] or "")
        if p.pid != os.getpid() and any(w in label for w in WATCHED):
            found.append(f"{p.pid} {p.info['name']}")
    return found


def main() -> None:
    if sys.argv[1] == "--parent":
        return stand_in_for_the_app(*sys.argv[2:5])
    engine, wav = sys.argv[1], sys.argv[2]
    flavor = sys.argv[3] if len(sys.argv) > 3 else "cpu"
    assert not running(), f"processes of the engine are running before the test: {running()}"
    parent = subprocess.Popen([sys.executable, __file__, "--parent", engine, wav, flavor], stdout=subprocess.PIPE, text=True)
    try:
        engine_pid = int(parent.stdout.readline())
        until = time.time() + 240
        seen: list[str] = []
        while time.time() < until:
            seen = [p.name() for p in psutil.Process(engine_pid).children(recursive=True)]
            if any("whisper-cli" in n for n in seen):
                break
            time.sleep(0.2)
        assert any("whisper-cli" in n for n in seen), f"whisper-cli never ran under the engine: {seen}"
        print(f"engine {engine_pid} is transcribing with {seen}; killing the stand-in for the app (pid {parent.pid})")
        psutil.Process(parent.pid).kill()                      # only this process; nothing else is told to stop
        parent.wait(10)
        began = time.time()
        while time.time() < began + 20 and (psutil.pid_exists(engine_pid) or running()):
            time.sleep(0.2)
        left = running() + ([f"{engine_pid} (the engine)"] if psutil.pid_exists(engine_pid) else [])
        assert not left, f"still running {time.time() - began:.0f} s after the app was killed: {left}"
        print(f"orphan check OK: the engine and whisper-cli were gone {time.time() - began:.1f} s after the app was killed")
    finally:
        if parent.poll() is None:
            parent.kill()
        for p in psutil.process_iter(["pid", "name"]):          # never leave anything behind on a failed run
            if p.pid != os.getpid() and any(w in (p.info["name"] or "") for w in ("whisper-cli", "babelscribe-engine")):
                try:
                    p.kill()
                except psutil.Error:
                    pass


if __name__ == "__main__":
    main()
