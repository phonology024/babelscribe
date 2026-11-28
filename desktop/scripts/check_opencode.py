"""CI check of "Connect to OpenCode" against the real OpenCode, version 2 and version 1, in a fake home folder.

    python desktop/scripts/check_opencode.py <npm prefix with @opencode/cli> <npm prefix with opencode-ai (version 1)>

Version 2: babelscribe adds itself with OpenCode's own `mcp add --global`, finds the entry where OpenCode wrote it
(default folder and OPENCODE_CONFIG_DIR), and takes it out again leaving the person's settings and comments.
Version 1: Connect changes nothing and says to update; the command offered by Copy works, and Remove takes it out.
Standard library only; babelscribe must be installed for this Python."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FAILED: list[str] = []
SEED = '{\n  // my own note\n  "mcp": {"servers": {"other": {"type": "local", "command": ["x"]}}}\n}\n'


def check(ok: bool, what: str, why: object = "") -> None:
    print(("ok    " if ok else "FAIL  ") + what + ("" if ok else f"   [{str(why)[:900]}]"), flush=True)
    if not ok:
        FAILED.append(what)


def fake_env(home: Path, programs: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("OPENCODE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")}
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "AppData" / "Roaming"),
               LOCALAPPDATA=str(home / "AppData" / "Local"))
    env["PATH"] = os.pathsep.join([str(programs / "node_modules" / ".bin")]
                                  + [p for p in env.get("PATH", "").split(os.pathsep) if "opencode" not in p.lower()])
    return env


def connect(env: dict, *args: str) -> tuple[int, dict]:
    p = subprocess.run([sys.executable, "-m", "babelscribe", "connect", *args, "--json"], env=env,
                       capture_output=True, text=True, timeout=240)
    lines = [l for l in p.stdout.splitlines() if l.startswith(("{", "["))]
    return p.returncode, (json.loads(lines[-1]) if lines else {"raw": p.stdout, "err": p.stderr[-900:]})


def files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def version_2(prefix: Path, tmp: Path, override: bool) -> None:
    label = "v2 with OPENCODE_CONFIG_DIR" if override else "v2"
    home = tmp / ("home two" if override else "home dir")        # a space in the path
    home.mkdir()
    env = fake_env(home, prefix)
    folder = home / ".config" / "opencode"
    if override:
        folder = tmp / "own settings"
        env["OPENCODE_CONFIG_DIR"] = str(folder)
    folder.mkdir(parents=True)
    config = folder / "opencode.jsonc"
    config.write_text(SEED, encoding="utf-8", newline="")

    code, plan = connect(env, "show", "opencode")
    check(code == 0 and plan.get("problem") is None and "--global" in plan.get("text", ""),
          f"{label}: --help is recognised as version 2", plan)
    code, r = connect(env, "add", "opencode")
    check(code == 0 and r.get("ok") and r.get("changed") and Path(r.get("path") or "") == config,
          f"{label}: add, and the entry is where babelscribe looks", r)
    text = config.read_text(encoding="utf-8")
    check("// my own note" in text and '"other"' in text, f"{label}: the other settings are still there", text)
    check(config.with_name("opencode.jsonc.bak").read_text(encoding="utf-8") == SEED, f"{label}: the old file is kept")
    code, rows = connect(env, "status")
    state = next((x["state"] for x in rows if x["app"] == "opencode"), None) if isinstance(rows, list) else rows
    check(state == "connected", f"{label}: status says connected", state)
    code, again = connect(env, "add", "opencode")
    check(code == 0 and again.get("changed") is False, f"{label}: adding again changes nothing", again)
    code, r = connect(env, "remove", "opencode")
    text = config.read_text(encoding="utf-8")
    check(code == 0 and r.get("changed") and "babelscribe" not in text and "// my own note" in text and '"other"' in text,
          f"{label}: remove takes out only babelscribe", (r, text))
    p = subprocess.run([shutil.which("opencode", path=env["PATH"]), "mcp", "add", "later", "--global", "--", "x"], env=env,
                       capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    check(p.returncode == 0 and '"later"' in config.read_text(encoding="utf-8"),
          f"{label}: OpenCode still reads and edits the file babelscribe cut", p.stdout + p.stderr)


def version_1(prefix: Path, tmp: Path) -> None:
    home = tmp / "home one"
    home.mkdir()
    env = fake_env(home, prefix)
    folder = home / ".config" / "opencode"
    code, plan = connect(env, "show", "opencode")
    check(code == 0 and "version 2" in (plan.get("problem") or "") and "--global" not in plan.get("text", "")
          and plan.get("kind") == "command", "v1: recognised, and Copy offers a command without --global", plan)
    before = files(folder)
    code, r = connect(env, "add", "opencode")
    check(code == 1 and "Update OpenCode to version 2" in r.get("error", ""), "v1: Connect says to update", r)
    check(files(folder) == before and not any("babelscribe" in (folder / f).read_text(encoding="utf-8", errors="replace")
                                              for f in files(folder)), "v1: and changes nothing", files(folder))
    shown = plan.get("text", "")
    server = shown.split(" -- ", 1)[1] if " -- " in shown else ""
    parts = [json.loads(p) if p.startswith('"') else p for p in __import__("re").findall(r'"(?:[^"\\]|\\.)*"|\S+', server)]
    p = subprocess.run([shutil.which("opencode", path=env["PATH"]), "mcp", "add", "babelscribe", "--", *parts], env=env,
                       cwd=home, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    check(p.returncode == 0, "v1: the command Copy gives runs", p.stdout + p.stderr)
    code, rows = connect(env, "status")
    state = next((x["state"] for x in rows if x["app"] == "opencode"), None) if isinstance(rows, list) else rows
    check(state == "connected", "v1: what it wrote is found", (state, files(folder)))
    code, r = connect(env, "remove", "opencode")
    check(code == 0 and r.get("changed") and not any(
        '"babelscribe"' in (folder / f).read_text(encoding="utf-8", errors="replace")
        for f in files(folder) if f.endswith((".json", ".jsonc"))), "v1: Remove takes it out", r)


def main() -> None:
    two, one = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        version_2(two, Path(tmp), override=False)
        version_2(two, Path(tmp), override=True)
        version_1(one, Path(tmp))
    if FAILED:
        raise SystemExit(f"{len(FAILED)} check(s) failed:\n  " + "\n  ".join(FAILED))
    print("every OpenCode check passed")


if __name__ == "__main__":
    main()
