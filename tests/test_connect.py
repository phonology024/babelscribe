"""Connect to AI apps: merge, backup, remove and refuse, for each app's file format, on fake home folders."""
import json
import os
import sys
from pathlib import Path

import pytest

from babelscribe import cli, connect
from babelscribe.connect import APPS, ConnectError, Env

SERVER = ("C:/Program Files/babelscribe/babelscribe-mcp.exe", [])
OURS = {"command": SERVER[0], "args": [], "timeout": 3_600_000}
JSON_APPS = ["claude-desktop", "cursor", "gemini"]
toml_only = pytest.mark.skipif(connect.tomllib is None, reason="needs tomllib (Python 3.11+)")


def make_env(tmp_path, platform="win32", found=(), run=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    ran = []

    def fake_run(cmd):
        ran.append(cmd)
        return run(cmd) if run else (0, "")
    env = Env(home=home, platform=platform,
              environ={"APPDATA": str(tmp_path / "AppData" / "Roaming"), "LOCALAPPDATA": str(tmp_path / "AppData" / "Local")},
              which=lambda name: f"/bin/{name}" if name in found else None, run=fake_run, command=SERVER)
    env.ran = ran                                                                    # type: ignore[attr-defined]
    return env


def put(path: Path, text: str, raw: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return path


def only_files(folder: Path):
    return sorted(p.name for p in folder.iterdir())


# ------------------------------------------------------------------------------------------------- where things live

@pytest.mark.parametrize("platform,tail", [
    ("win32", ("AppData", "Roaming", "Claude", "claude_desktop_config.json")),
    ("darwin", ("home", "Library", "Application Support", "Claude", "claude_desktop_config.json")),
    ("linux", ("home", ".config", "Claude", "claude_desktop_config.json"))])
def test_claude_desktop_file_is_where_the_app_keeps_it(tmp_path, platform, tail):
    assert connect.config_path("claude-desktop", make_env(tmp_path, platform)) == tmp_path.joinpath(*tail)


def test_other_apps_files(tmp_path):
    env = make_env(tmp_path)
    assert connect.config_path("cursor", env) == env.home / ".cursor" / "mcp.json"
    assert connect.config_path("gemini", env) == env.home / ".gemini" / "settings.json"
    assert connect.config_path("codex", env) == env.home / ".codex" / "config.toml"
    assert connect.config_path("claude-code", env) is None
    env.environ["CODEX_HOME"] = str(tmp_path / "elsewhere")
    assert connect.config_path("codex", env) == tmp_path / "elsewhere" / "config.toml"


def test_apps_are_found_by_their_program_or_their_folder(tmp_path):
    env = make_env(tmp_path, found=("claude",))
    assert [connect.installed(k, env) for k in APPS] == [False, True, False, False, False]
    (env.home / ".cursor").mkdir()
    (env.home / ".gemini").mkdir()
    (env.home / ".codex").mkdir()
    (tmp_path / "AppData" / "Roaming" / "Claude").mkdir(parents=True)
    assert all(connect.installed(k, env) for k in APPS)


def test_the_server_is_the_one_next_to_the_engine_in_the_installed_app(tmp_path, monkeypatch):
    exe = tmp_path / ("babelscribe-mcp.exe" if os.name == "nt" else "babelscribe-mcp")
    exe.write_bytes(b"x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "babelscribe-engine"))
    assert connect.server_command() == (str(exe.resolve()), [])


def test_the_server_of_a_pip_install_is_the_babelscribe_command(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(connect.shutil, "which", lambda name: "/usr/bin/babelscribe")
    assert connect.server_command() == ("/usr/bin/babelscribe", ["mcp"])
    monkeypatch.setattr(connect.shutil, "which", lambda name: None)
    assert connect.server_command() == (sys.executable, ["-m", "babelscribe", "mcp"])


# ------------------------------------------------------------------------------------------------- JSON apps: add

@pytest.mark.parametrize("app", JSON_APPS)
def test_add_creates_the_file_when_there_is_none(tmp_path, app):
    env = make_env(tmp_path)
    r = connect.add(app, env)
    path = connect.config_path(app, env)
    assert r["changed"] and r["backup"] is None
    assert json.loads(path.read_text(encoding="utf-8")) == {"mcpServers": {"babelscribe": OURS}}
    assert only_files(path.parent) == [path.name]                       # no stray temporary file


@pytest.mark.parametrize("app", JSON_APPS)
def test_add_keeps_everything_else_and_the_look_of_the_file(tmp_path, app):
    env = make_env(tmp_path)
    path = connect.config_path(app, env)
    original = ('{\r\n    "theme": "dark",\r\n    "mcpServers": {\r\n        "other": {"command": "x", "args": ["a", "b"]}\r\n    },'
                '\r\n    "ünï": [1, 2.50, null, true]\r\n}\r\n')
    put(path, original)
    r = connect.add(app, env)
    new = path.read_bytes().decode("utf-8")
    data = json.loads(new)
    assert data["theme"] == "dark" and data["ünï"] == [1, 2.5, None, True]
    assert data["mcpServers"]["other"] == {"command": "x", "args": ["a", "b"]}
    assert data["mcpServers"]["babelscribe"] == OURS
    assert list(data) == ["theme", "mcpServers", "ünï"]                 # same order
    assert new.count("\r\n") == new.count("\n") and new.endswith("\r\n")  # still Windows line endings
    assert '\n        "other"' in new.replace("\r\n", "\n")                # the four-space indentation is kept
    assert r["backup"] and Path(r["backup"]).read_bytes() == original.encode("utf-8")    # the old file, byte for byte


def test_add_keeps_a_byte_order_mark_and_tab_indentation(tmp_path):
    env = make_env(tmp_path)
    path = connect.config_path("cursor", env)
    put(path, "", raw=b'\xef\xbb\xbf{\n\t"mcpServers": {}\n}\n')
    connect.add("cursor", env)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b'\n\t"mcpServers"' in raw
    assert json.loads(raw.decode("utf-8-sig"))["mcpServers"]["babelscribe"] == OURS


@pytest.mark.parametrize("text", ["", "  \n"])
def test_an_empty_file_is_treated_as_an_empty_object(tmp_path, text):
    env = make_env(tmp_path)
    path = put(connect.config_path("gemini", env), text)
    connect.add("gemini", env)
    assert json.loads(path.read_text(encoding="utf-8")) == {"mcpServers": {"babelscribe": OURS}}


def test_adding_twice_changes_nothing_the_second_time(tmp_path):
    env = make_env(tmp_path)
    connect.add("cursor", env)
    path = connect.config_path("cursor", env)
    before = path.read_bytes()
    r = connect.add("cursor", env)
    assert r["changed"] is False and path.read_bytes() == before and only_files(path.parent) == ["mcp.json"]


def test_an_older_babelscribe_entry_is_replaced_and_nothing_else(tmp_path):
    env = make_env(tmp_path)
    path = connect.config_path("claude-desktop", env)
    put(path, json.dumps({"mcpServers": {"babelscribe": {"command": "uvx", "args": ["babelscribe", "mcp"]},
                                          "keep": {"command": "k"}}}))
    assert connect.plan("claude-desktop", env)["state"] == "other"
    connect.add("claude-desktop", env)
    got = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    assert got == {"babelscribe": OURS, "keep": {"command": "k"}}
    assert connect.plan("claude-desktop", env)["state"] == "connected"


def test_a_second_backup_never_overwrites_the_first(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("cursor", env), '{"a": 1}')
    first = connect.add("cursor", env)["backup"]
    connect.remove("cursor", env)
    second = connect.add("cursor", env)
    assert Path(first).name == "mcp.json.bak" and Path(first).read_text(encoding="utf-8") == '{"a": 1}'
    assert second["backup"] and Path(second["backup"]).name == "mcp.json.bak3"       # .bak (add), .bak2 (remove), .bak3
    assert only_files(path.parent) == ["mcp.json", "mcp.json.bak", "mcp.json.bak2", "mcp.json.bak3"]


def test_no_backup_when_the_person_says_so(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("cursor", env), '{"a": 1}')
    assert connect.add("cursor", env, make_backup=False)["backup"] is None
    assert only_files(path.parent) == ["mcp.json"]


# ------------------------------------------------------------------------------------------------- JSON apps: refuse

@pytest.mark.parametrize("text", ['{"mcpServers": {', '{"a": 1,}', "not json at all", '{"a": 1} trailing', "\x00\x01"])
@pytest.mark.parametrize("action", ["add", "remove"])
def test_a_file_with_a_syntax_error_is_never_touched(tmp_path, text, action):
    env = make_env(tmp_path)
    path = put(connect.config_path("claude-desktop", env), text)
    with pytest.raises(ConnectError) as e:
        getattr(connect, action)("claude-desktop", env)
    assert "left it exactly as it is" in str(e.value) and "line" in str(e.value)
    assert path.read_bytes() == text.encode("utf-8")
    assert only_files(path.parent) == [path.name]                       # not even a backup
    p = connect.plan("claude-desktop", env)
    assert p["state"] == "unknown" and "left it exactly as it is" in p["problem"]


@pytest.mark.parametrize("text,why", [('["a"]', "JSON object"), ('{"mcpServers": []}', "mcpServers"), ('{"mcpServers": 3}', "mcpServers")])
def test_a_file_of_the_wrong_shape_is_never_touched(tmp_path, text, why):
    env = make_env(tmp_path)
    path = put(connect.config_path("cursor", env), text)
    with pytest.raises(ConnectError) as e:
        connect.add("cursor", env)
    assert why in str(e.value) and path.read_text(encoding="utf-8") == text and only_files(path.parent) == ["mcp.json"]


def test_a_file_that_is_not_text_is_never_touched(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("cursor", env), "", raw=b"\xff\xfe{\x00")
    with pytest.raises(ConnectError, match="UTF-8"):
        connect.add("cursor", env)
    assert path.read_bytes() == b"\xff\xfe{\x00"


def test_when_the_write_fails_the_old_file_is_still_there_and_no_temporary_file_is_left(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    original = '{"a": 1}'
    path = put(connect.config_path("cursor", env), original)

    def refuse(src, dst):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(connect.os, "replace", refuse)
    with pytest.raises(ConnectError, match="close it and try again"):
        connect.add("cursor", env)
    assert path.read_text(encoding="utf-8") == original
    assert [n for n in only_files(path.parent) if not n.endswith(".bak")] == ["mcp.json"]


def test_a_link_to_the_real_file_stays_a_link(tmp_path):
    env = make_env(tmp_path)
    real = put(tmp_path / "dotfiles" / "mcp.json", '{"a": 1}')
    link = connect.config_path("cursor", env)
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("cannot make symbolic links here")
    connect.add("cursor", env)
    assert link.is_symlink() and json.loads(real.read_text(encoding="utf-8"))["mcpServers"]["babelscribe"] == OURS


# ------------------------------------------------------------------------------------------------- JSON apps: remove

@pytest.mark.parametrize("app", JSON_APPS)
def test_remove_takes_out_only_babelscribe(tmp_path, app):
    env = make_env(tmp_path)
    path = put(connect.config_path(app, env), json.dumps({"x": 1, "mcpServers": {"a": {"command": "a"}, "babelscribe": OURS}}, indent=2))
    r = connect.remove(app, env)
    assert r["changed"] and json.loads(path.read_text(encoding="utf-8")) == {"x": 1, "mcpServers": {"a": {"command": "a"}}}
    assert Path(r["backup"]).exists()
    assert connect.plan(app, env)["state"] == "not-connected"


def test_remove_when_it_is_not_there_changes_nothing(tmp_path):
    env = make_env(tmp_path)
    assert connect.remove("cursor", env)["changed"] is False                     # no file at all
    path = put(connect.config_path("cursor", env), '{"mcpServers": {"a": {}}}')
    r = connect.remove("cursor", env)
    assert r["changed"] is False and only_files(path.parent) == ["mcp.json"]


def test_add_then_remove_gives_the_same_servers_back(tmp_path):
    env = make_env(tmp_path)
    original = {"mcpServers": {"a": {"command": "a", "env": {"K": "v"}}}, "n": 1}
    path = put(connect.config_path("gemini", env), json.dumps(original, indent=2) + "\n")
    connect.add("gemini", env)
    connect.remove("gemini", env)
    assert json.loads(path.read_text(encoding="utf-8")) == original


# ------------------------------------------------------------------------------------------------- Codex (TOML)

CODEX = '''# my settings
model = "gpt-5"

[mcp_servers.other]
command = "other"   # keep this comment
args = ["x"]

[projects."C:\\\\work"]
trust = "trusted"
'''


@toml_only
def test_codex_add_appends_a_table_with_the_long_timeouts(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("codex", env), CODEX)
    r = connect.add("codex", env)
    new = path.read_text(encoding="utf-8")
    assert new.startswith(CODEX.rstrip("\n")) and "# keep this comment" in new
    got = connect.tomllib.loads(new)
    assert got["mcp_servers"]["babelscribe"] == {"command": SERVER[0], "args": [], "tool_timeout_sec": 3600, "startup_timeout_sec": 120}
    assert got["mcp_servers"]["other"] == {"command": "other", "args": ["x"]} and got["projects"]["C:\\work"] == {"trust": "trusted"}
    assert Path(r["backup"]).read_text(encoding="utf-8") == CODEX


@toml_only
def test_codex_add_creates_the_file(tmp_path):
    env = make_env(tmp_path)
    connect.add("codex", env)
    path = connect.config_path("codex", env)
    assert connect.tomllib.loads(path.read_text(encoding="utf-8"))["mcp_servers"]["babelscribe"]["tool_timeout_sec"] == 3600


@toml_only
def test_codex_add_twice_changes_nothing_and_a_stale_table_is_replaced_with_its_sub_tables(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("codex", env), CODEX + '\n[mcp_servers.babelscribe]\ncommand = "uvx"\nargs = ["babelscribe", "mcp"]\n'
               '[mcp_servers.babelscribe.env]\nOLD = "1"\n\n[after]\nkept = true\n')
    assert connect.plan("codex", env)["state"] == "other"
    connect.add("codex", env)
    got = connect.tomllib.loads(path.read_text(encoding="utf-8"))
    assert got["mcp_servers"]["babelscribe"]["command"] == SERVER[0] and "env" not in got["mcp_servers"]["babelscribe"]
    assert got["after"] == {"kept": True} and got["mcp_servers"]["other"]["command"] == "other"
    before = path.read_bytes()
    assert connect.add("codex", env)["changed"] is False and path.read_bytes() == before


@toml_only
def test_codex_quoted_table_name_is_ours_too(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("codex", env), '[mcp_servers."babelscribe"]\ncommand = "old"\n')
    connect.add("codex", env)
    assert connect.tomllib.loads(path.read_text(encoding="utf-8"))["mcp_servers"]["babelscribe"]["command"] == SERVER[0]


@toml_only
def test_codex_remove_takes_out_only_ours(tmp_path):
    env = make_env(tmp_path)
    path = put(connect.config_path("codex", env), CODEX)
    connect.add("codex", env)
    r = connect.remove("codex", env)
    assert r["changed"] and path.read_text(encoding="utf-8").rstrip("\n") == CODEX.rstrip("\n")
    assert connect.remove("codex", env)["changed"] is False


@toml_only
@pytest.mark.parametrize("text", ['model = "gpt-5', "[mcp_servers", "a = = 1", "[a]\nb = 1\n[a]\nc = 2\n"])
@pytest.mark.parametrize("action", ["add", "remove"])
def test_codex_file_with_a_syntax_error_is_never_touched(tmp_path, text, action):
    env = make_env(tmp_path)
    path = put(connect.config_path("codex", env), text)
    with pytest.raises(ConnectError, match="left it exactly as it is"):
        getattr(connect, action)("codex", env)
    assert path.read_text(encoding="utf-8") == text and only_files(path.parent) == ["config.toml"]


@toml_only
def test_codex_entry_that_cannot_be_edited_safely_is_left_alone(tmp_path):
    env = make_env(tmp_path)
    text = 'mcp_servers = { babelscribe = { command = "old" } }\n'
    path = put(connect.config_path("codex", env), text)
    for action in ("add", "remove"):
        with pytest.raises(ConnectError):
            getattr(connect, action)("codex", env)
    assert path.read_text(encoding="utf-8") == text and only_files(path.parent) == ["config.toml"]


def test_codex_without_tomllib_refuses_to_edit_and_says_how_to_do_it_by_hand(tmp_path, monkeypatch):
    monkeypatch.setattr(connect, "tomllib", None)
    env = make_env(tmp_path)
    path = put(connect.config_path("codex", env), CODEX)
    for action in ("add", "remove"):
        with pytest.raises(ConnectError, match="Python 3.11"):
            getattr(connect, action)("codex", env)
    assert path.read_text(encoding="utf-8") == CODEX and "Python 3.11" in connect.plan("codex", env)["problem"]


# ------------------------------------------------------------------------------------------------- Claude Code (its own command)

def test_claude_code_runs_its_own_command_for_the_user_scope(tmp_path):
    env = make_env(tmp_path, found=("claude",))
    r = connect.add("claude-code", env)
    assert r["changed"] and env.ran == [["claude", "mcp", "add", "--scope", "user", "babelscribe", "--", SERVER[0]]]


def test_claude_code_already_connected_runs_nothing(tmp_path):
    env = make_env(tmp_path, found=("claude",))
    put(env.home / ".claude.json", json.dumps({"mcpServers": {"babelscribe": OURS}, "projects": {}}))
    assert connect.plan("claude-code", env)["state"] == "connected"
    assert connect.add("claude-code", env)["changed"] is False and env.ran == []


def test_claude_code_replaces_an_older_entry_by_removing_it_first(tmp_path):
    env = make_env(tmp_path, found=("claude",))
    put(env.home / ".claude.json", json.dumps({"mcpServers": {"babelscribe": {"command": "uvx"}}}))
    connect.add("claude-code", env)
    assert env.ran[0][:5] == ["claude", "mcp", "remove", "--scope", "user"] and env.ran[1][:3] == ["claude", "mcp", "add"]


def test_claude_code_that_fails_says_what_it_said(tmp_path):
    env = make_env(tmp_path, found=("claude",), run=lambda cmd: (1, "Error: something happened"))
    with pytest.raises(ConnectError, match="Error: something happened"):
        connect.add("claude-code", env)


def test_claude_code_not_installed_is_explained(tmp_path):
    env = make_env(tmp_path)
    with pytest.raises(ConnectError, match="Claude Code was not found"):
        connect.add("claude-code", env)
    assert "Claude Code was not found" in connect.plan("claude-code", env)["problem"] and env.ran == []


def test_claude_code_remove(tmp_path):
    env = make_env(tmp_path, found=("claude",))
    assert connect.remove("claude-code", env)["changed"] is False and env.ran == []
    put(env.home / ".claude.json", json.dumps({"mcpServers": {"babelscribe": OURS}}))
    assert connect.remove("claude-code", env)["changed"] and env.ran == [["claude", "mcp", "remove", "--scope", "user", "babelscribe"]]


def test_claude_codes_own_file_is_only_ever_read(tmp_path):
    env = make_env(tmp_path, found=("claude",))
    path = put(env.home / ".claude.json", '{"broken": ')
    st = connect.status(env)
    assert next(s for s in st if s["app"] == "claude-code")["state"] == "unknown" and path.read_text(encoding="utf-8") == '{"broken": '


# ------------------------------------------------------------------------------------------------- plan, status, command line

def test_plan_shows_exactly_what_will_be_added(tmp_path):
    env = make_env(tmp_path)
    put(connect.config_path("cursor", env), "{}")
    p = connect.plan("cursor", env)
    assert json.loads(p["text"]) == {"mcpServers": {"babelscribe": OURS}} and p["backup"].endswith("mcp.json.bak")
    assert p["path"] == str(connect.config_path("cursor", env)) and p["problem"] is None and p["state"] == "not-connected"
    assert "babelscribe-mcp.exe" in connect.plan("claude-code", make_env(tmp_path, found=("claude",)))["text"]
    if connect.tomllib:
        assert "tool_timeout_sec = 3600" in connect.plan("codex", env)["text"]


def test_status_lists_every_app_and_never_raises_on_a_broken_file(tmp_path):
    env = make_env(tmp_path)
    put(connect.config_path("gemini", env), "{")
    rows = connect.status(env)
    assert [r["app"] for r in rows] == list(APPS)
    assert next(r for r in rows if r["app"] == "gemini")["state"] == "unknown"
    assert all(r["state"] in ("not-connected", "unknown") for r in rows)


def test_unknown_app_is_refused(tmp_path):
    for fn in (connect.plan, connect.add, connect.remove):
        with pytest.raises(ConnectError, match="unknown app"):
            fn("notepad", make_env(tmp_path))


def test_command_line_prints_json_for_the_desktop_app(tmp_path, monkeypatch, capsys):
    env = make_env(tmp_path)
    monkeypatch.setattr(connect, "Env", lambda: env)
    cli.main(["connect", "add", "cursor", "--json", "--exit-when-stdin-closes"])
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["changed"] and out["path"].endswith("mcp.json")
    cli.main(["connect", "status", "--json"])
    assert {r["app"]: r["state"] for r in json.loads(capsys.readouterr().out)}["cursor"] == "connected"
    cli.main(["connect", "remove", "cursor", "--json", "--no-backup"])
    assert json.loads(capsys.readouterr().out)["changed"] is True


def test_command_line_reports_a_refusal_as_json_and_exit_code_1(tmp_path, monkeypatch, capsys):
    env = make_env(tmp_path)
    monkeypatch.setattr(connect, "Env", lambda: env)
    put(connect.config_path("cursor", env), "{")
    with pytest.raises(SystemExit) as e:
        cli.main(["connect", "add", "cursor", "--json"])
    assert e.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "left it exactly as it is" in out["error"]
    with pytest.raises(SystemExit) as e:
        cli.main(["connect", "add", "nope"])
    assert "unknown app" in str(e.value.code)
    with pytest.raises(SystemExit) as e:
        cli.main(["connect", "add"])
    assert "usage" in str(e.value.code)
