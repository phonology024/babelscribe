"""CI check (Windows): uninstalling the app takes babelscribe out of the AI apps it was connected to.

    python desktop/scripts/check_connect_uninstall.py prepare "<installed engine>"    # before the silent uninstall
    python desktop/scripts/check_connect_uninstall.py verify                          # after it

The runner is a throw-away machine, so this uses the runner's own user folders (the uninstaller runs as that user and
looks there). `prepare` connects Cursor, Gemini CLI, Claude Desktop and Codex with the installed engine to settings that
already hold another server and another setting. `verify` requires, once the uninstaller has run, that babelscribe is gone from
all four, that the other server and setting are still there, and that a .bak copy was kept. Standard library only (Python 3.11+)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.gettempdir()) / "babelscribe-connect-uninstall.json"
HOME = Path(os.environ["USERPROFILE"])
FILES = {
    "cursor": HOME / ".cursor" / "mcp.json",
    "gemini": HOME / ".gemini" / "settings.json",
    "claude-desktop": Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json",
}
TOML = HOME / ".codex" / "config.toml"
FAILED: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what, flush=True)
    if not ok:
        FAILED.append(what)


def prepare(engine: str) -> None:
    other = {"keep-me": {"command": "keep", "args": ["x"]}}
    for app, path in FILES.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"theme": "dark", "mcpServers": other}, indent=2), encoding="utf-8")
    TOML.parent.mkdir(parents=True, exist_ok=True)
    TOML.write_text('# mine\nmodel = "gpt-5"\n\n[mcp_servers.keep-me]\ncommand = "keep"\n', encoding="utf-8")
    for app in (*FILES, "codex"):
        p = subprocess.run([engine, "connect", "add", app, "--json"], capture_output=True, text=True, timeout=120)
        check(p.returncode == 0 and '"changed": true' in p.stdout, f"{app}: connected before the uninstall")
        print(p.stdout.strip()[:300])
    STATE.write_text(json.dumps({"engine": engine}), encoding="utf-8")
    if FAILED:
        raise SystemExit("could not set up: " + "; ".join(FAILED))


def verify() -> None:
    import tomllib
    for app, path in FILES.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        check("babelscribe" not in data["mcpServers"], f"{app}: babelscribe is gone from {path}")
        check(data["mcpServers"].get("keep-me") == {"command": "keep", "args": ["x"]} and data.get("theme") == "dark",
              f"{app}: the other server and setting are still there")
        check(path.with_name(path.name + ".bak").is_file(), f"{app}: a .bak copy was kept")
    data = tomllib.loads(TOML.read_text(encoding="utf-8"))
    check("babelscribe" not in data.get("mcp_servers", {}), "codex: babelscribe is gone from config.toml")
    check(data["mcp_servers"].get("keep-me") == {"command": "keep"} and data.get("model") == "gpt-5", "codex: the other server and setting are still there")
    engine = json.loads(STATE.read_text(encoding="utf-8"))["engine"]
    check(not Path(engine).exists(), "the app is uninstalled (the engine is gone)")
    if FAILED:
        raise SystemExit(f"{len(FAILED)} check(s) failed:\n  " + "\n  ".join(FAILED))
    print("uninstalling took babelscribe out of every app it was connected to")


if __name__ == "__main__":
    prepare(sys.argv[2]) if sys.argv[1] == "prepare" else verify()
