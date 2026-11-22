"""Smoke test of the standalone build: does the folder work on a machine that has no Python?

    python packaging/standalone/smoke_test.py dist/babelscribe sample.wav

The two programs are started with an environment that has no Python in it (no PATH entry, no PYTHON* variables)
and a fresh, empty babelscribe home, so everything they need must come out of the folder itself or be downloaded
by them. This script only needs the standard library; the Python that runs it is not visible to the programs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def clean_env(home: Path) -> dict:
    keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
            "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE", "HOME", "LANG")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    system = os.environ.get("SYSTEMROOT", r"C:\Windows")
    env["PATH"] = os.pathsep.join([str(Path(system) / "System32"), system]) if os.name == "nt" else "/usr/bin:/bin"
    env["BABELSCRIBE_HOME"] = str(home)
    return env


def rpc(proc: subprocess.Popen, message: dict) -> dict | None:
    proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    proc.stdin.flush()
    if "id" not in message:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("the MCP server closed its output: " + proc.stderr.read().decode("utf-8", "replace")[-800:])
        reply = json.loads(line)
        if reply.get("id") == message["id"]:
            return reply


def main() -> None:
    folder, sample = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    ext = ".exe" if os.name == "nt" else ""
    cli, server = folder / f"babelscribe{ext}", folder / f"babelscribe-mcp{ext}"
    with tempfile.TemporaryDirectory() as tmp:
        env = clean_env(Path(tmp) / "home")
        work = Path(tmp) / "my files"                      # a space in the path, as on a real desktop
        work.mkdir()
        audio = work / sample.name
        audio.write_bytes(sample.read_bytes())

        t0 = time.time()
        text = dict(capture_output=True, text=True, encoding="utf-8", errors="replace")   # piped output is in the ANSI code page
        p = subprocess.run([str(cli), "--version"], env=env, **text)
        took = time.time() - t0
        assert p.returncode == 0 and p.stdout.strip()[:1].isdigit(), p
        print(f"--version: {p.stdout.strip()} in {took:.2f} s")

        p = subprocess.run([str(cli), "models"], env=env, **text)
        assert p.returncode == 0 and "tiny" in p.stdout, p

        # the whole first run: download whisper-cli (CPU build: CI machines have no GPU) and the tiny model, transcribe
        t0 = time.time()
        p = subprocess.run([str(cli), str(audio), "-m", "tiny", "-l", "en", "--flavor", "cpu", "-f", "srt,json"],
                           env=env, **text)
        print(p.stdout[-600:], p.stderr[-600:])
        assert p.returncode == 0, "transcription failed"
        srt = audio.with_suffix(".srt").read_text(encoding="utf-8")
        assert "-->" in srt and "country" in srt.lower(), srt
        print(f"first run (downloads + transcription): {time.time() - t0:.0f} s\n{srt.strip()[:200]}")

        # the MCP server: handshake and the tool list, over stdio, the way an AI app starts it
        proc = subprocess.Popen([str(server)], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        try:
            hello = rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "0"}}})
            assert hello["result"]["serverInfo"]["name"] == "babelscribe", hello
            rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = {t["name"] for t in rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
            assert {"transcribe", "find_media", "list_devices"} <= tools, tools
            print("MCP server:", hello["result"]["serverInfo"], sorted(tools))
        finally:
            proc.kill()
    print("standalone build: OK")


if __name__ == "__main__":
    main()
