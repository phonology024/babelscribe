"""CI check of "Connect to an AI app" as the installed app runs it: the engine's `connect` command against a fake home.

    python desktop/scripts/check_connect.py "<installed engine>" "<installed babelscribe-mcp>"

For each app that keeps a settings file (Claude Desktop, Cursor, Gemini CLI, Codex CLI) the installed engine adds babelscribe to
a config that already has other things in it, and the check requires: the other things are still there, the old file is
kept as .bak byte for byte, the command that was written is the program shipped in the app and it really starts and
answers an MCP handshake, "remove" takes out only babelscribe, and a config with a syntax error is refused and left
exactly as it was. Every program runs with HOME and the app folders pointed at a temporary folder: nothing of the
runner's own settings is read or written. Standard library only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

FAILED: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what, flush=True)
    if not ok:
        FAILED.append(what)


def fake_env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_CONFIG_HOME")}
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "AppData" / "Roaming"),
               LOCALAPPDATA=str(home / "AppData" / "Local"), XDG_CONFIG_HOME=str(home / ".config"))
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "claude" not in p.lower())
    return env


def connect(engine: Path, env: dict, *args: str) -> tuple[int, dict]:
    p = subprocess.run([str(engine), "connect", *args, "--json", "--exit-when-stdin-closes"], env=env, stdin=subprocess.PIPE,
                       capture_output=True, text=True, timeout=120)
    lines = [l for l in p.stdout.splitlines() if l.startswith(("{", "["))]
    return p.returncode, (json.loads(lines[-1]) if lines else {"raw": p.stdout, "err": p.stderr[-600:]})


def handshake(command: str, args: list[str], env: dict) -> bool:
    """Start the server the way an AI app does and ask it for its tools."""
    p = subprocess.Popen([command, *args], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        def rpc(msg: dict) -> dict | None:
            p.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
            p.stdin.flush()
            while "id" in msg:
                line = p.stdout.readline()
                if not line:
                    return None
                reply = json.loads(line)
                if reply.get("id") == msg["id"]:
                    return reply
            return None
        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "ci", "version": "0"}}})
        rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in (tools or {}).get("result", {}).get("tools", [])]
        return bool(init and "transcribe" in names)
    finally:
        p.kill()
        p.wait()


def main() -> None:
    engine, mcp = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    check(mcp.is_file(), f"the app ships {mcp.name} next to the engine")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home dir"                              # a space in the path, as on a real desktop
        home.mkdir()
        env = fake_env(home)

        code, rows = connect(engine, env, "status")
        check(code == 0 and [r["app"] for r in rows] == ["claude-desktop", "claude-code", "codex", "cursor", "gemini"],
              "status lists the five apps")
        check(all(r["state"] == "not-connected" for r in rows if r["app"] != "claude-code"), "none is connected in a fresh home")

        code, plan = connect(engine, env, "show", "cursor")
        shown = json.loads(plan["text"])["mcpServers"]["babelscribe"]["command"] if code == 0 else ""   # a Windows path has doubled backslashes in JSON
        check(code == 0 and Path(shown).resolve() == mcp and plan.get("problem") is None, "show names the program shipped in the app")

        files = {r["app"]: Path(r["path"]) for r in rows if r["path"]}
        old = {"claude-desktop": '{\n  "globalShortcut": "Ctrl+Space",\n  "mcpServers": {"other": {"command": "x"}}\n}\n',
               "cursor": '{"mcpServers": {"other": {"command": "x", "args": ["a"]}}}',
               "gemini": '{\n    "theme": "Default",\n    "mcpServers": {"other": {"command": "y"}}\n}\n'}
        for app, text in old.items():
            files[app].parent.mkdir(parents=True, exist_ok=True)
            files[app].write_text(text, encoding="utf-8", newline="")
            code, r = connect(engine, env, "add", app)
            check(code == 0 and r.get("ok") and r.get("changed"), f"{app}: add")
            data = json.loads(files[app].read_text(encoding="utf-8"))
            check(data["mcpServers"]["other"] == json.loads(text)["mcpServers"]["other"], f"{app}: the other server is still there")
            check({k: v for k, v in data.items() if k != "mcpServers"} == {k: v for k, v in json.loads(text).items() if k != "mcpServers"},
                  f"{app}: the other settings are still there")
            written = data["mcpServers"]["babelscribe"]
            check(Path(written["command"]).resolve() == mcp, f"{app}: the command written is the program shipped in the app")
            bak = files[app].with_name(files[app].name + ".bak")
            check(bak.is_file() and bak.read_bytes() == text.encode("utf-8"), f"{app}: the old file is kept as .bak, byte for byte")
            code, again = connect(engine, env, "add", app)
            check(code == 0 and again.get("changed") is False, f"{app}: adding again changes nothing")
            code, r = connect(engine, env, "remove", app)
            data = json.loads(files[app].read_text(encoding="utf-8"))
            check(code == 0 and r.get("changed") and list(data["mcpServers"]) == ["other"], f"{app}: remove takes out only babelscribe")
            connect(engine, env, "add", app, "--no-backup")

        entry = json.loads(files["cursor"].read_text(encoding="utf-8"))["mcpServers"]["babelscribe"]
        check(handshake(entry["command"], entry["args"], env), "the command written into the config starts and lists the transcribe tool")

        codex = files["codex"]
        codex.parent.mkdir(parents=True, exist_ok=True)
        codex.write_text('# my settings\nmodel = "gpt-5"\n\n[mcp_servers.other]\ncommand = "o"  # keep\n', encoding="utf-8", newline="")
        code, r = connect(engine, env, "add", "codex")
        text = codex.read_text(encoding="utf-8")
        check(code == 0 and r.get("changed") and "# keep" in text and "[mcp_servers.other]" in text, "codex: add keeps the rest of config.toml")
        check("tool_timeout_sec = 3600" in text and "startup_timeout_sec = 120" in text, "codex: the long timeouts are set")
        code, r = connect(engine, env, "remove", "codex")
        check(code == 0 and "babelscribe" not in codex.read_text(encoding="utf-8") and "[mcp_servers.other]" in codex.read_text(encoding="utf-8"),
              "codex: remove takes out only babelscribe")

        for app, broken in (("claude-desktop", '{"mcpServers": {'), ("codex", 'model = "gpt-5')):
            files[app].write_text(broken, encoding="utf-8", newline="")
            before = {p.name for p in files[app].parent.iterdir()}
            code, r = connect(engine, env, "add", app)
            check(code == 1 and r.get("ok") is False and "left it exactly as it is" in r.get("error", ""), f"{app}: a syntax error is refused, with the reason")
            check(files[app].read_text(encoding="utf-8") == broken and {p.name for p in files[app].parent.iterdir()} == before,
                  f"{app}: the broken file was not touched and no copy was made")

        code, r = connect(engine, env, "show", "claude-code")
        check(code == 0 and r.get("kind") == "command" and "claude mcp add --scope user babelscribe" in r.get("text", ""),
              "claude code: the command it would run is shown")
    if FAILED:
        raise SystemExit(f"{len(FAILED)} check(s) failed:\n  " + "\n  ".join(FAILED))
    print("every connect check passed")


if __name__ == "__main__":
    main()
