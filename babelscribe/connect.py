"""Connect babelscribe to AI apps (Claude Desktop, Claude Code, Codex CLI, Cursor, Gemini CLI) as an MCP server.

The desktop app shows this to a person who is not at a terminal, so the rules are strict:

- An app's settings file is MERGED, never replaced: everything that is not babelscribe's own entry stays as it was
  (other servers, other settings, the indentation and line endings).
- The old file is copied to NAME.bak first (NAME.bak2, ... when that exists), unless the caller says not to.
- A file that cannot be read as JSON / TOML, or whose shape is not what the app writes, is left exactly as it is, and the
  error says why in plain words.
- The new content is checked after it is built and before it replaces anything; the write goes to a temporary file in the
  same folder and is moved over the old one in one step.
- `remove` takes out only the "babelscribe" entry.

The server that is registered is the one this program ships: `babelscribe-mcp` next to the engine in the installed app, else
the `babelscribe` command of a pip install."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

NAME = "babelscribe"
TOOL_TIMEOUT_MS = 3_600_000        # a long video: the apps' default (60 s) is far too short
TOOL_TIMEOUT_S = 3600
STARTUP_TIMEOUT_S = 120            # the first start can download a model

try:
    import tomllib
except ImportError:                # Python 3.9 and 3.10
    tomllib = None                 # type: ignore[assignment]


class ConnectError(Exception):
    """Something to tell the person, in plain words. Nothing was changed."""


# ---------------------------------------------------------------------------------------------------- environment

def server_command() -> tuple[str, list[str]]:
    """The program and arguments an AI app should start to get the babelscribe MCP server."""
    if getattr(sys, "frozen", False):                       # the installed app: babelscribe-mcp sits next to the engine
        sibling = Path(sys.executable).resolve().parent / ("babelscribe-mcp.exe" if os.name == "nt" else "babelscribe-mcp")
        if sibling.is_file():
            return str(sibling), []
    exe = shutil.which("babelscribe")
    if exe:
        return exe, ["mcp"]
    return sys.executable, ["-m", "babelscribe", "mcp"]


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=90, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


@dataclass
class Env:
    """Everything that depends on the computer, so a test can hand in a fake one."""
    home: Path = field(default_factory=Path.home)
    platform: str = sys.platform
    environ: dict = field(default_factory=lambda: dict(os.environ))
    which: Callable[[str], str | None] = shutil.which
    run: Callable[[list[str]], tuple[int, str]] = _run
    command: tuple[str, list[str]] | None = None
    exists: Callable[[Path], bool] = lambda p: p.exists()

    def server(self) -> tuple[str, list[str]]:
        return self.command or server_command()

    def appdata(self) -> Path:
        return Path(self.environ.get("APPDATA") or self.home / "AppData" / "Roaming")

    def localappdata(self) -> Path:
        return Path(self.environ.get("LOCALAPPDATA") or self.home / "AppData" / "Local")


# ---------------------------------------------------------------------------------------------------- the apps

@dataclass(frozen=True)
class App:
    key: str
    name: str
    kind: str                       # "json" | "toml" | "command"
    extra: str
    after: str


APPS = {a.key: a for a in (
    App("claude-desktop", "Claude Desktop", "json",
        "Other servers already in the file are kept.",
        "Quit Claude Desktop completely and open it again, then look for babelscribe under the tools icon."),
    App("claude-code", "Claude Code", "command",
        "Claude Code keeps this in its own user settings (`--scope user`), so it works in every project.",
        "Start a new Claude Code session; /mcp lists babelscribe."),
    App("codex", "Codex CLI", "toml",
        "The long timeouts are needed: Codex stops a tool after 60 seconds and a start after 10 seconds by default.",
        "Start Codex again; /mcp lists babelscribe."),
    App("cursor", "Cursor", "json",
        "Other servers already in the file are kept. Cursor may ask you to switch the server on under Settings, MCP.",
        "Open Cursor Settings, MCP, and check that babelscribe is on."),
    App("gemini", "Gemini CLI", "json",
        "Other servers and settings already in the file are kept.",
        "Start Gemini CLI again; /mcp lists babelscribe."),
)}


CLAUDE_CONFIG = "claude_desktop_config.json"


def _newest(paths: list[Path]) -> Path | None:
    def when(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    return max(paths, key=when) if paths else None


def _glob(folder: Path, pattern: str) -> list[Path]:
    try:
        return [p for p in folder.glob(pattern)]
    except OSError:
        return []


def claude_desktop_windows(env: Env) -> Path:
    """Claude Desktop's settings file on Windows. The Store (MSIX) install keeps it in %LOCALAPPDATA%\\Claude-Data\\claude_*\\,
    the same app's package folder has a LocalCache\\Roaming\\Claude copy, and the plain installer uses %APPDATA%\\Claude. A file
    that exists wins, in that order (the most recently changed one when there are several); with none, the folder of the first
    layout that is on this computer; else the plain installer's."""
    local = env.localappdata()
    store = _glob(local / "Claude-Data", "claude_*")
    package = _glob(local / "Packages", "Claude_*")
    layouts = [                          # (the app's own folder, the file inside it)
        [(d, d / CLAUDE_CONFIG) for d in store],
        [(d, d / "LocalCache" / "Roaming" / "Claude" / CLAUDE_CONFIG) for d in package],
        [(env.appdata() / "Claude", env.appdata() / "Claude" / CLAUDE_CONFIG)],
    ]
    for group in layouts:
        found = _newest([f for _, f in group if f.is_file()])
        if found:
            return found
    for group in layouts[:2]:
        folder = _newest([d for d, _ in group if d.is_dir()])
        if folder:
            return next(f for d, f in group if d == folder)
    return layouts[2][0][1]


def config_path(app: str, env: Env) -> Path | None:
    """The settings file an app reads (None for Claude Code, which keeps its own)."""
    h = env.home
    if app == "claude-desktop":
        if env.platform == "win32":
            return claude_desktop_windows(env)
        if env.platform == "darwin":
            return h / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        return Path(env.environ.get("XDG_CONFIG_HOME") or h / ".config") / "Claude" / "claude_desktop_config.json"
    if app == "cursor":
        return h / ".cursor" / "mcp.json"
    if app == "gemini":
        return h / ".gemini" / "settings.json"
    if app == "codex":
        return Path(env.environ.get("CODEX_HOME") or h / ".codex") / "config.toml"
    return None


def installed(app: str, env: Env) -> bool:
    """Is the app on this computer? (A guess from its program or its settings folder; Connect works either way.)"""
    ex = env.exists
    if app == "claude-code":
        return bool(env.which("claude")) or ex(env.home / ".claude" / "local" / "claude")
    if app == "codex":
        return bool(env.which("codex")) or ex(config_path(app, env).parent)           # type: ignore[union-attr]
    if app == "gemini":
        return bool(env.which("gemini")) or ex(env.home / ".gemini")
    if app == "cursor":
        places = [env.home / ".cursor"]
        if env.platform == "win32":
            places.append(env.localappdata() / "Programs" / "cursor")
        elif env.platform == "darwin":
            places.append(Path("/Applications/Cursor.app"))
        return any(ex(p) for p in places)
    cfg = config_path(app, env)                                                       # Claude Desktop
    places = [cfg.parent]                                                              # type: ignore[union-attr]
    if env.platform == "win32":
        local = env.localappdata()
        places += [local / "AnthropicClaude", local / "Claude-Data", env.appdata() / "Claude"]
        places += _glob(local / "Packages", "Claude_*")
    elif env.platform == "darwin":
        places.append(Path("/Applications/Claude.app"))
    return any(ex(p) for p in places)


TIMEOUT_KEY = {"gemini"}     # the apps whose settings document a per-server "timeout" (milliseconds); the others get no extra key


def entry(env: Env, app: str) -> dict:
    cmd, args = env.server()
    out: dict = {"command": cmd, "args": list(args)}
    if app in TIMEOUT_KEY:
        out["timeout"] = TOOL_TIMEOUT_MS
    return out


def _quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)       # a JSON string is a valid TOML basic string


def toml_block(env: Env) -> str:
    cmd, args = env.server()
    return (f"[mcp_servers.{NAME}]\ncommand = {_quote(cmd)}\nargs = [{', '.join(_quote(a) for a in args)}]\n"
            f"tool_timeout_sec = {TOOL_TIMEOUT_S}\nstartup_timeout_sec = {STARTUP_TIMEOUT_S}\n")


def command_line(env: Env, exe: str = "claude") -> list[str]:
    cmd, args = env.server()
    return [exe, "mcp", "add", "--scope", "user", NAME, "--", cmd, *args]


def _shown(cmd: list[str]) -> str:
    return " ".join(c if re.fullmatch(r"[\w./:\\=@%+-]+", c) else json.dumps(c, ensure_ascii=False) for c in cmd)


# ---------------------------------------------------------------------------------------------------- files

@dataclass
class Loaded:
    path: Path
    exists: bool
    text: str = ""
    bom: bool = False
    eol: str = "\n"
    indent: str = "  "
    data: dict = field(default_factory=dict)


def _read_text(path: Path) -> tuple[str, bool]:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ConnectError(f"{path} cannot be read ({e.strerror or e}). Nothing was changed.") from None
    try:
        return raw.decode("utf-8-sig"), raw.startswith(b"\xef\xbb\xbf")
    except UnicodeDecodeError:
        raise ConnectError(f"{path} is not a UTF-8 text file, so babelscribe left it as it is.") from None


def load_json(path: Path) -> Loaded:
    if not path.exists():
        return Loaded(path, False)
    text, bom = _read_text(path)
    m = re.search(r'^([ \t]+)"', text, re.M)
    out = Loaded(path, True, text, bom, "\r\n" if "\r\n" in text else "\n", m.group(1) if m else "  ")
    if not text.strip():
        return out
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConnectError(f"{path} has a mistake in it ({e.msg}, line {e.lineno}, column {e.colno}), so babelscribe left it "
                           f"exactly as it is. Fix that line, or use Copy and add babelscribe yourself.") from None
    if not isinstance(data, dict):
        raise ConnectError(f"{path} does not hold a JSON object ({{ ... }}), so babelscribe left it as it is.")
    out.data = data
    return out


def dump_json(f: Loaded, data: dict) -> str:
    text = json.dumps(data, indent=f.indent, ensure_ascii=False)
    if f.eol != "\n":
        text = text.replace("\n", f.eol)
    return text + f.eol


def _servers(f: Loaded, create: bool) -> dict | None:
    s = f.data.get("mcpServers")
    if s is None:
        return {} if create else None
    if not isinstance(s, dict):
        raise ConnectError(f"In {f.path} the \"mcpServers\" part is not a list of servers ({{ ... }}), so babelscribe left "
                           f"the file as it is.")
    return s


def backup(path: Path) -> Path | None:
    """Copy the file next to itself as NAME.bak (NAME.bak2, ... if that exists). None when there is no file."""
    if not path.exists():
        return None
    for n in range(1, 1000):
        to = path.with_name(path.name + (".bak" if n == 1 else f".bak{n}"))
        if not to.exists():
            try:
                shutil.copy2(path, to)
            except OSError as e:
                raise ConnectError(f"A copy of {path.name} could not be made ({e.strerror or e}), so nothing was changed.") from None
            return to
    raise ConnectError(f"There are already 999 copies of {path.name}; nothing was changed.")


def write_atomic(path: Path, text: str, bom: bool = False) -> None:
    target = path.resolve() if path.is_symlink() else path           # a link to the real file stays a link
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".babelscribe-new")
        tmp.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
        if target.exists():
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    except OSError as e:
        try:
            tmp.unlink()
        except (OSError, UnboundLocalError):
            pass
        raise ConnectError(f"{path} could not be written ({e.strerror or e}). If the app is open, close it and try again. "
                           f"Nothing was changed.") from None


# ---------------------------------------------------------------------------------------------------- TOML (Codex)

def _need_tomllib(path: Path) -> None:
    if tomllib is None:
        raise ConnectError(f"{path} can only be checked safely with Python 3.11 or newer (the desktop app has it). "
                           f"Use Copy and add babelscribe to it yourself.")


def load_toml(path: Path) -> Loaded:
    if not path.exists():
        return Loaded(path, False)
    text, bom = _read_text(path)
    out = Loaded(path, True, text, bom, "\r\n" if "\r\n" in text else "\n")
    if tomllib is not None:
        try:
            out.data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ConnectError(f"{path} has a mistake in it ({e}), so babelscribe left it exactly as it is. Fix that line, or "
                               f"use Copy and add babelscribe yourself.") from None
    return out


_OURS = re.compile(r"^\s*\[\[?\s*mcp_servers\s*\.\s*(?:babelscribe|\"babelscribe\"|'babelscribe')\s*(?:\.[^\]]*)?\]\]?\s*(?:#.*)?$")
_ANY_HEADER = re.compile(r"^\s*\[")


def toml_without_ours(text: str) -> str:
    """The text with babelscribe's own [mcp_servers.babelscribe] tables (and its sub-tables) taken out."""
    keep, skipping = [], False
    for line in text.splitlines(keepends=True):
        if _OURS.match(line.rstrip("\r\n")):
            skipping = True
            continue
        if skipping and _ANY_HEADER.match(line):
            skipping = False
        if not skipping:
            keep.append(line)
    out = "".join(keep)
    return re.sub(r"(\r?\n){3,}", lambda m: m.group(0)[: 2 * len(m.group(1))], out) if out != text else out


def _toml_ours(data: dict) -> dict | None:
    s = data.get("mcp_servers")
    return s.get(NAME) if isinstance(s, dict) and isinstance(s.get(NAME), dict) else None


def _toml_check(path: Path, text: str, want_present: bool, env: Env) -> None:
    """The rebuilt file must parse, and say what we meant; otherwise nothing is written."""
    try:
        data = tomllib.loads(text)                                                       # type: ignore[union-attr]
    except tomllib.TOMLDecodeError as e:                                                 # type: ignore[union-attr]
        raise ConnectError(f"babelscribe could not edit {path} safely ({e}); nothing was changed. Use Copy and add it "
                           f"yourself.") from None
    ours = _toml_ours(data)
    cmd, args = env.server()
    if want_present and not (ours and ours.get("command") == cmd and list(ours.get("args", [])) == list(args)
                             and ours.get("tool_timeout_sec") == TOOL_TIMEOUT_S):
        raise ConnectError(f"babelscribe could not edit {path} safely; nothing was changed. Use Copy and add it yourself.")
    if not want_present and ours is not None:
        raise ConnectError(f"babelscribe is set up in {path} in a way that cannot be taken out safely (for example inside an "
                           f"inline table), so the file was not changed. Remove the [mcp_servers.{NAME}] part by hand.")


# ---------------------------------------------------------------------------------------------------- state

def _same(found: dict | None, env: Env) -> bool:
    cmd, args = env.server()
    return bool(found) and found.get("command") == cmd and list(found.get("args") or []) == list(args)


def _state_json(app: str, env: Env) -> tuple[str, str | None]:
    """('not-connected' | 'connected' | 'other' | 'unknown', why unknown)"""
    path = config_path(app, env)
    try:
        f = load_json(path)                                                              # type: ignore[arg-type]
        found = (_servers(f, False) or {}).get(NAME)
    except ConnectError as e:
        return "unknown", str(e)
    return ("not-connected" if found is None else "connected" if _same(found, env) else "other"), None


def _state_toml(env: Env) -> tuple[str, str | None]:
    path = config_path("codex", env)
    try:
        f = load_toml(path)                                                              # type: ignore[arg-type]
    except ConnectError as e:
        return "unknown", str(e)
    if tomllib is None:                                  # Python 3.9 / 3.10: cannot read TOML, so do not claim to know
        return ("not-connected", None) if not f.exists else ("unknown", None)
    found = _toml_ours(f.data)
    return ("not-connected" if found is None else "connected" if _same(found, env) else "other"), None


def _state_code(env: Env) -> tuple[str, str | None]:
    path = env.home / ".claude.json"
    if not path.exists():
        return "not-connected", None
    try:
        data = json.loads(_read_text(path)[0] or "{}")
    except (ConnectError, json.JSONDecodeError):
        return "unknown", None                    # Claude Code's own file: we only look, never change it
    found = (data.get("mcpServers") or {}).get(NAME) if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) else None
    return ("not-connected" if found is None else "connected" if _same(found, env) else "other"), None


def state(app: str, env: Env) -> tuple[str, str | None]:
    return _state_code(env) if app == "claude-code" else _state_toml(env) if app == "codex" else _state_json(app, env)


def status(env: Env | None = None) -> list[dict]:
    env = env or Env()
    out = []
    for key, a in APPS.items():
        st, why = state(key, env)
        path = config_path(key, env)
        out.append({"app": key, "name": a.name, "installed": installed(key, env), "state": st,
                    "path": str(path) if path else None, "problem": why})
    return out


def plan(app: str, env: Env | None = None) -> dict:
    """What Connect would do for one app, in the words and text to show before anything is changed."""
    env = env or Env()
    a = APPS.get(app)
    if a is None:
        raise ConnectError(f"unknown app '{app}'; choose one of: {', '.join(APPS)}")
    st, why = state(app, env)
    path = config_path(app, env)
    shown = (_shown(command_line(env)) if a.kind == "command" else toml_block(env) if a.kind == "toml"
             else json.dumps({"mcpServers": {NAME: entry(env, app)}}, indent=2, ensure_ascii=False))
    problem = why
    if a.kind == "command" and not env.which("claude"):
        problem = problem or ("Claude Code was not found on this computer (the `claude` command). Install it, or use Copy "
                              "and run the command yourself.")
    if a.kind == "toml" and tomllib is None:
        problem = problem or f"{path} can only be checked safely with Python 3.11 or newer. Use Copy and add it yourself."
    bak = None
    if path is not None and path.exists():
        bak = str(path.with_name(path.name + ".bak"))
    return {"app": app, "name": a.name, "kind": a.kind, "installed": installed(app, env), "state": st,
            "path": str(path) if path else None, "text": shown, "backup": bak, "problem": problem,
            "extra": a.extra, "after": a.after, "server": " ".join([env.server()[0], *env.server()[1]])}


# ---------------------------------------------------------------------------------------------------- change

def add(app: str, env: Env | None = None, make_backup: bool = True) -> dict:
    env = env or Env()
    a = APPS.get(app)
    if a is None:
        raise ConnectError(f"unknown app '{app}'; choose one of: {', '.join(APPS)}")
    if a.kind == "command":
        return _code_add(env)
    path = config_path(app, env)
    if a.kind == "toml":
        _need_tomllib(path)                                                              # type: ignore[arg-type]
        f = load_toml(path)                                                              # type: ignore[arg-type]
        base = toml_without_ours(f.text) if f.exists else ""
        block = toml_block(env).replace("\n", f.eol)
        text = (base.rstrip("\r\n") + f.eol + f.eol + block) if base.strip() else block
        _toml_check(path, text, True, env)                                               # type: ignore[arg-type]
        same = f.exists and text == f.text
        if same:
            return {"ok": True, "changed": False, "path": str(path), "backup": None, "message": f"{a.name} was already connected."}
        bak = backup(path) if make_backup else None                                      # type: ignore[arg-type]
        write_atomic(path, text, f.bom)                                                  # type: ignore[arg-type]
        return {"ok": True, "changed": True, "path": str(path), "backup": str(bak) if bak else None,
                "message": f"{a.name} is connected. {a.after}"}
    f = load_json(path)                                                                  # type: ignore[arg-type]
    servers = _servers(f, True)
    if servers.get(NAME) == entry(env, app):
        return {"ok": True, "changed": False, "path": str(path), "backup": None, "message": f"{a.name} was already connected."}
    data = dict(f.data)
    data["mcpServers"] = {**servers, NAME: entry(env, app)}
    text = dump_json(f, data)
    _json_check(path, text, True, env, app)                                              # type: ignore[arg-type]
    bak = backup(path) if make_backup else None                                          # type: ignore[arg-type]
    write_atomic(path, text, f.bom)                                                      # type: ignore[arg-type]
    return {"ok": True, "changed": True, "path": str(path), "backup": str(bak) if bak else None,
            "message": f"{a.name} is connected. {a.after}"}


def _json_check(path: Path, text: str, want_present: bool, env: Env, app: str) -> None:
    try:
        got = (json.loads(text).get("mcpServers") or {}).get(NAME)
    except (json.JSONDecodeError, AttributeError):
        got = "broken"
    if want_present and got != entry(env, app) or not want_present and got is not None:
        raise ConnectError(f"babelscribe could not edit {path} safely; nothing was changed. Use Copy and add it yourself.")


def remove(app: str, env: Env | None = None, make_backup: bool = True) -> dict:
    env = env or Env()
    a = APPS.get(app)
    if a is None:
        raise ConnectError(f"unknown app '{app}'; choose one of: {', '.join(APPS)}")
    if a.kind == "command":
        return _code_remove(env)
    path = config_path(app, env)
    if a.kind == "toml":
        _need_tomllib(path)                                                              # type: ignore[arg-type]
        f = load_toml(path)                                                              # type: ignore[arg-type]
        if not f.exists or _toml_ours(f.data) is None:
            return {"ok": True, "changed": False, "path": str(path), "backup": None, "message": f"babelscribe was not in {a.name}'s settings."}
        text = toml_without_ours(f.text)
        _toml_check(path, text, False, env)                                              # type: ignore[arg-type]
        bak = backup(path) if make_backup else None                                      # type: ignore[arg-type]
        write_atomic(path, text, f.bom)                                                  # type: ignore[arg-type]
        return {"ok": True, "changed": True, "path": str(path), "backup": str(bak) if bak else None,
                "message": f"babelscribe was taken out of {a.name}'s settings."}
    f = load_json(path)                                                                  # type: ignore[arg-type]
    servers = _servers(f, False)
    if not servers or NAME not in servers:
        return {"ok": True, "changed": False, "path": str(path), "backup": None, "message": f"babelscribe was not in {a.name}'s settings."}
    data = dict(f.data)
    data["mcpServers"] = {k: v for k, v in servers.items() if k != NAME}
    text = dump_json(f, data)
    _json_check(path, text, False, env, app)                                             # type: ignore[arg-type]
    bak = backup(path) if make_backup else None                                          # type: ignore[arg-type]
    write_atomic(path, text, f.bom)                                                      # type: ignore[arg-type]
    return {"ok": True, "changed": True, "path": str(path), "backup": str(bak) if bak else None,
            "message": f"babelscribe was taken out of {a.name}'s settings."}


def _code_add(env: Env) -> dict:
    exe = env.which("claude")        # the full path: Windows does not apply PATHEXT to a bare "claude" that is a claude.cmd
    if not exe:
        raise ConnectError("Claude Code was not found on this computer (the `claude` command). Install it, or use Copy and run "
                           "the command yourself.")
    st, _ = _state_code(env)
    if st == "connected":
        return {"ok": True, "changed": False, "path": None, "backup": None, "message": "Claude Code was already connected."}
    if st == "other":                                        # an older babelscribe entry: replace it, nothing else
        code, out = env.run([exe, "mcp", "remove", "--scope", "user", NAME])
        if code != 0:
            raise ConnectError(f"Claude Code did not take the old babelscribe entry out: {out or 'no message'}")
    code, out = env.run(command_line(env, exe))
    if code != 0:
        raise ConnectError(f"Claude Code did not accept the command: {out or 'no message'}")
    return {"ok": True, "changed": True, "path": None, "backup": None,
            "message": f"Claude Code is connected. {APPS['claude-code'].after}"}


def _code_remove(env: Env) -> dict:
    st, _ = _state_code(env)
    if st == "not-connected":
        return {"ok": True, "changed": False, "path": None, "backup": None, "message": "babelscribe was not in Claude Code's settings."}
    exe = env.which("claude")
    if not exe:
        raise ConnectError("Claude Code was not found on this computer (the `claude` command), so babelscribe could not be taken out.")
    code, out = env.run([exe, "mcp", "remove", "--scope", "user", NAME])
    if code != 0:
        raise ConnectError(f"Claude Code did not take babelscribe out: {out or 'no message'}")
    return {"ok": True, "changed": True, "path": None, "backup": None, "message": "babelscribe was taken out of Claude Code's settings."}


# ---------------------------------------------------------------------------------------------------- command line

def main(argv: list[str]) -> None:
    """babelscribe connect [status | show APP | add APP | remove APP] [--json] [--no-backup]"""
    argv = [x for x in argv if x != "--exit-when-stdin-closes"]       # added by the desktop app to everything it runs
    as_json = "--json" in argv
    backup_on = "--no-backup" not in argv
    words = [x for x in argv if not x.startswith("--")]
    action = words[0] if words else "status"
    app = words[1] if len(words) > 1 else ""
    try:
        if action == "status":
            result: object = status()
        elif action in ("show", "add", "remove") and app:
            result = {"show": lambda: plan(app), "add": lambda: add(app, make_backup=backup_on),
                      "remove": lambda: remove(app, make_backup=backup_on)}[action]()
        else:
            raise ConnectError("usage: babelscribe connect [status | show APP | add APP | remove APP] [--json] [--no-backup]\n"
                               f"APP is one of: {', '.join(APPS)}")
    except ConnectError as e:
        if as_json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=True))
            raise SystemExit(1) from None
        raise SystemExit(str(e)) from None
    if as_json:
        print(json.dumps(result, ensure_ascii=True))
        return
    if action == "status":
        for r in result:                                          # type: ignore[union-attr]
            print(f"  {r['name']:16} {'found' if r['installed'] else 'not found':10} {r['state']}")
    elif action == "show":
        print(f"{result['name']}: {result['text']}")              # type: ignore[index]
    else:
        print(result["message"] + (f" (old file kept as {result['backup']})" if result.get("backup") else ""))   # type: ignore[index,union-attr]
