"""Connect to OpenCode: added with its own command, taken out by cutting only babelscribe's entry from its settings.

The stand-in answers `mcp add --help` the way each OpenCode line does, and its `add --global` writes mcp.servers.NAME
into the first global settings file that exists, as OpenCode 2.4.2's packages/cli/src/commands/handlers/mcp/add.ts
does. CI also runs the real OpenCode (desktop/scripts/check_opencode.py)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from babelscribe import connect, jsonc
from babelscribe.connect import ConnectError, Env

SERVER = ("C:/Program Files/babelscribe/babelscribe-mcp.exe", [])
OURS = {"type": "local", "command": [SERVER[0]]}
V2_HELP = "USAGE\n  opencode mcp add [flags] <name> [<command...>]\nFLAGS\n  --url string\n  --env key=value\n  --global  Write to the global config"
V1_HELP = "opencode mcp add [name]\n\nadd an MCP server\n\nOptions:\n  --url   URL for a remote MCP server\n  --env\n  --header"
OLD_HELP = "opencode mcp add\n\nadd an MCP server\n\nOptions:\n  -h, --help"


class Stand:
    def __init__(self, env: Env, help_text=V2_HELP, add=None):
        self.env, self.help, self.add, self.ran = env, help_text, add, []

    def __call__(self, cmd):
        self.ran.append(cmd)
        if cmd[1:] == ["mcp", "add", "--help"]:
            return 0, self.help
        if self.add:
            return self.add(cmd)
        assert cmd[1:3] == ["mcp", "add"] and cmd[4] == "--global" and cmd[5] == "--", cmd
        target = connect._opencode_target(self.env)
        data = jsonc.parse(target.read_text(encoding="utf-8-sig") if target.is_file() else "{}").value
        data.setdefault("mcp", {}).setdefault("servers", {})[cmd[3]] = {"type": "local", "command": cmd[6:]}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return 0, f'MCP server "{cmd[3]}" added to {target}'


def make(tmp_path, help_text=V2_HELP, add=None, found=("opencode",), platform="linux", environ=None, paths=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    paths = paths or {n: f"/bin/{n}" for n in found}
    env = Env(home=home, platform=platform, environ=dict(environ or {}), which=paths.get, command=SERVER)
    env.run = Stand(env, help_text, add)
    return env


def settings(env, name="opencode.json") -> Path:
    return connect.opencode_dir(env) / name


def put(path: Path, text: str, raw: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return path


def adds(env):
    return [c for c in env.run.ran if c[-1] != "--help"]


# ------------------------------------------------------------------------------------------------- where, and which one

def test_the_global_folder_is_found_the_way_opencode_2_finds_it(tmp_path):
    env = make(tmp_path)
    assert connect.opencode_dir(env) == env.home / ".config" / "opencode"
    env.environ["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    assert connect.opencode_dir(env) == tmp_path / "xdg" / "opencode"
    env.environ["OPENCODE_CONFIG_DIR"] = str(tmp_path / "own")
    assert connect.opencode_dir(env) == tmp_path / "own"


def test_the_file_opencode_writes_is_the_first_that_exists(tmp_path):
    env = make(tmp_path)
    assert connect.config_path("opencode", env) == settings(env)
    put(settings(env, ".opencode/opencode.jsonc"), "{}")
    assert connect.config_path("opencode", env) == settings(env, ".opencode/opencode.jsonc")
    put(settings(env, "opencode.jsonc"), "{}")
    assert connect.config_path("opencode", env) == settings(env, "opencode.jsonc")


def test_it_is_found_by_its_programs_or_its_folder(tmp_path):
    env = make(tmp_path, found=())
    assert not connect.installed("opencode", env)
    own = put(env.home / ".opencode" / "bin" / "opencode", "x")
    assert connect.installed("opencode", env) and connect._opencode_programs(env) == [str(own)]


def test_add_runs_its_own_command_globally_by_full_path(tmp_path):
    env = make(tmp_path)
    r = connect.add("opencode", env)
    assert adds(env) == [["/bin/opencode", "mcp", "add", "babelscribe", "--global", "--", SERVER[0]]]
    assert r["changed"] and r["path"] == str(settings(env)) and r["backup"] is None
    assert connect.state("opencode", env) == ("connected", None)
    again = connect.add("opencode", env)
    assert again["changed"] is False and len(adds(env)) == 1


def test_a_copy_of_the_old_file_is_kept_before_the_command_runs(tmp_path):
    env = make(tmp_path)
    path = put(settings(env), '{"theme": "x"}')
    r = connect.add("opencode", env)
    assert Path(r["backup"]).read_text(encoding="utf-8") == '{"theme": "x"}' and path.read_text(encoding="utf-8") != '{"theme": "x"}'


def test_version_2_installed_as_opencode2_next_to_version_1_is_used(tmp_path):
    env = make(tmp_path, found=("opencode", "opencode2"))
    stand = env.run
    env.run = lambda cmd: (0, V1_HELP) if cmd[0] == "/bin/opencode" and cmd[-1] == "--help" else stand(cmd)
    assert connect.add("opencode", env)["changed"]
    assert adds(type("E", (), {"run": stand})())[0][0] == "/bin/opencode2"
    assert connect.plan("opencode", env)["text"].startswith("opencode2 mcp add babelscribe --global --")


@pytest.mark.parametrize("help_text", [V1_HELP, OLD_HELP], ids=["v1", "older"])
def test_a_version_without_global_is_never_used_and_nothing_changes(tmp_path, help_text):
    env = make(tmp_path, help_text)
    path = put(settings(env), '{"theme": "x"}')
    with pytest.raises(ConnectError, match="Update OpenCode to version 2, or use Copy.*Nothing was changed"):
        connect.add("opencode", env)
    assert not adds(env) and path.read_text(encoding="utf-8") == '{"theme": "x"}'
    assert [p.name for p in path.parent.iterdir()] == ["opencode.json"]


def test_what_copy_gives_works_on_the_version_that_is_there(tmp_path):
    v1 = connect.plan("opencode", make(tmp_path, V1_HELP))
    assert v1["kind"] == "command" and v1["text"].startswith("opencode mcp add babelscribe -- ") and "--global" not in v1["text"]
    old = connect.plan("opencode", make(tmp_path, OLD_HELP))
    assert old["kind"] == "json" and json.loads(old["text"])["mcp"]["babelscribe"]["command"] == [SERVER[0]]
    assert "add the text to" in old["problem"]
    new = connect.plan("opencode", make(tmp_path))
    assert "--global" in new["text"] and new["problem"] is None


def test_missing_and_broken_programs_are_explained(tmp_path):
    with pytest.raises(ConnectError, match="not found"):
        connect.add("opencode", make(tmp_path, found=()))
    env = make(tmp_path)
    env.run = lambda cmd: (1, "node: not found")
    assert "did not run: node: not found" in connect.plan("opencode", env)["problem"]


def test_a_command_that_fails_or_writes_nothing_is_not_called_success(tmp_path):
    with pytest.raises(ConnectError, match="did not accept.*boom"):
        connect.add("opencode", make(tmp_path, add=lambda cmd: (1, "boom")))
    with pytest.raises(ConnectError, match="not in .* as expected"):
        connect.add("opencode", make(tmp_path, add=lambda cmd: (0, "done")))


def test_a_broken_settings_file_stops_add_before_opencode_touches_it(tmp_path):
    env = make(tmp_path)
    path = put(settings(env), '{"mcp": {')
    with pytest.raises(ConnectError, match="left it exactly as it is"):
        connect.add("opencode", env)
    assert not adds(env) and path.read_text(encoding="utf-8") == '{"mcp": {'
    assert connect.state("opencode", env)[0] == "unknown"


@pytest.mark.parametrize("server,refused", [("C:/R&D/babelscribe-mcp.exe", True), ("C:/100%/babelscribe-mcp.exe", True),
                                            ("C:/R & D/babelscribe-mcp.exe", False)])
def test_an_npm_cmd_file_is_not_handed_a_path_it_would_read_as_commands(tmp_path, server, refused):
    env = make(tmp_path, platform="win32", paths={"opencode": r"C:\npm\opencode.CMD"})
    env.command = (server, [])
    if refused:
        with pytest.raises(ConnectError, match="cannot pass on safely"):
            connect.add("opencode", env)
        assert not adds(env)
    else:
        assert connect.add("opencode", env)["changed"]


@pytest.mark.skipif(os.name != "nt", reason="a .cmd file")
def test_the_real_runner_gives_a_program_no_input_and_strips_colours(tmp_path):
    script = tmp_path / "ask.py"
    script.write_text("import sys\nprint('\\x1b[31mred\\x1b[0m', repr(sys.stdin.read()))\n", encoding="utf-8")
    code, out = connect._run([sys.executable, str(script)])
    assert code == 0 and out == "red ''"


# ------------------------------------------------------------------------------------------------- remove

def check_removed(env, text: str, expected: str, **kwargs):
    path = put(settings(env, "opencode.jsonc"), text)
    r = connect.remove("opencode", env, **kwargs)
    assert r["changed"], r
    assert path.read_bytes().decode("utf-8") == expected
    return path, r


E = '{"type": "local", "command": ["' + SERVER[0] + '"]}'      # our entry, written on one line


@pytest.mark.parametrize("text,expected", [
    # first, middle, last, only: one entry per line
    (f'{{\n  "mcp": {{\n    "servers": {{\n      "babelscribe": {E},\n      "b": 1,\n      "c": 2\n    }}\n  }}\n}}\n',
     '{\n  "mcp": {\n    "servers": {\n      "b": 1,\n      "c": 2\n    }\n  }\n}\n'),
    (f'{{\n  "mcp": {{\n    "servers": {{\n      "a": 1,\n      "babelscribe": {E},\n      "c": 2\n    }}\n  }}\n}}\n',
     '{\n  "mcp": {\n    "servers": {\n      "a": 1,\n      "c": 2\n    }\n  }\n}\n'),
    (f'{{\n  "mcp": {{\n    "servers": {{\n      "a": 1,\n      "b": 2,\n      "babelscribe": {E}\n    }}\n  }}\n}}\n',
     '{\n  "mcp": {\n    "servers": {\n      "a": 1,\n      "b": 2\n    }\n  }\n}\n'),
    (f'{{\n  "mcp": {{\n    "servers": {{\n      "babelscribe": {E}\n    }}\n  }}\n}}\n',
     '{\n  "mcp": {\n    "servers": {\n    }\n  }\n}\n'),
    # trailing commas
    (f'{{\n  "mcp": {{"servers": {{\n    "a": 1,\n    "babelscribe": {E},\n  }},}},\n}}\n',
     '{\n  "mcp": {"servers": {\n    "a": 1,\n  },},\n}\n'),
    (f'{{"mcp":{{"servers":{{"babelscribe":{E},}}}}}}', '{"mcp":{"servers":{}}}'),
    # all on one line
    (f'{{"mcp": {{"servers": {{"a": 1, "babelscribe": {E}, "c": 2}}}}}}', '{"mcp": {"servers": {"a": 1, "c": 2}}}'),
    (f'{{"mcp": {{"servers": {{"a": 1, "babelscribe": {E}}}}}}}', '{"mcp": {"servers": {"a": 1}}}'),
    (f'{{"mcp": {{"servers": {{"babelscribe": {E}, "c": 2}}}}}}', '{"mcp": {"servers": {"c": 2}}}'),
    # a version 1 file: directly under mcp
    (f'{{\n  "mcp": {{\n    "a": {{}},\n    "babelscribe": {E}\n  }}\n}}\n', '{\n  "mcp": {\n    "a": {}\n  }\n}\n'),
    # the name twice
    (f'{{"mcp": {{"servers": {{"babelscribe": {E}, "a": 1, "babelscribe": {E}}}}}}}', '{"mcp": {"servers": {"a": 1}}}'),
], ids=["first", "middle", "last", "only", "trailing", "only-trailing", "inline-middle", "inline-last", "inline-first",
        "version-1", "twice"])
def test_remove_cuts_out_only_our_entry(tmp_path, text, expected):
    check_removed(make(tmp_path), text, expected)


def test_comments_around_and_beside_the_entry_stay_and_comments_inside_it_go(tmp_path):
    text = ('// my settings\n{\n  /* servers */\n  "mcp": {\n    "servers": {\n      // before babelscribe\n'
            '      "babelscribe": { // inside\n        "type": "local", /* inside too */\n'
            f'        "command": ["{SERVER[0]}"]\n      }}, // beside\n      // after\n'
            '      "other": { "type": "local", "command": ["x"] } // keep\n    }\n  }\n}\n')
    expected = ('// my settings\n{\n  /* servers */\n  "mcp": {\n    "servers": {\n      // before babelscribe\n'
                '      // beside\n      // after\n      "other": { "type": "local", "command": ["x"] } // keep\n    }\n  }\n}\n')
    env = make(tmp_path)
    path = put(settings(env, "opencode.jsonc"), text)
    connect.remove("opencode", env)
    got = path.read_text(encoding="utf-8")
    assert got == expected
    assert jsonc.parse(got).value == {"mcp": {"servers": {"other": {"type": "local", "command": ["x"]}}}}
    for comment in ("// my settings", "/* servers */", "// before babelscribe", "// beside", "// after", "// keep"):
        assert comment in got
    assert "inside" not in got


@pytest.mark.parametrize("between", ["/* c */ ", " // c\n  ", "\n  /* c */\n  "])
@pytest.mark.parametrize("last", [True, False])
def test_a_comment_between_the_entry_and_its_comma_stays(tmp_path, between, last):
    env = make(tmp_path)
    if last:
        text = f'{{"mcp": {{"servers": {{"a": 1 {between}, "babelscribe": {E}}}}}}}'
    else:
        text = f'{{"mcp": {{"servers": {{"babelscribe": {E} {between}, "a": 1}}}}}}'
    path = put(settings(env), text)
    connect.remove("opencode", env)
    got = path.read_text(encoding="utf-8")
    assert jsonc.parse(got).value == {"mcp": {"servers": {"a": 1}}} and "c" in got.split('"mcp"')[1] and between.strip() in got


def test_crlf_a_byte_order_mark_and_the_backup(tmp_path):
    env = make(tmp_path)
    raw = ('\ufeff{\r\n  "mcp": {\r\n    "servers": {\r\n      "a": 1,\r\n'
           f'      "babelscribe": {E}\r\n    }}\r\n  }}\r\n}}\r\n').encode("utf-8")
    path = put(settings(env), "", raw=raw)
    r = connect.remove("opencode", env)
    assert path.read_bytes() == '\ufeff{\r\n  "mcp": {\r\n    "servers": {\r\n      "a": 1\r\n    }\r\n  }\r\n}\r\n'.encode("utf-8")
    assert Path(r["backup"]).read_bytes() == raw
    assert not adds(env), "no OpenCode command removes a server"


def test_no_backup_when_the_person_says_so(tmp_path):
    env = make(tmp_path)
    path, r = check_removed(env, f'{{"mcp": {{"servers": {{"babelscribe": {E}}}}}}}', '{"mcp": {"servers": {}}}',
                            make_backup=False)
    assert r["backup"] is None and [p.name for p in path.parent.iterdir()] == [path.name]


def test_strings_that_look_like_the_entry_braces_or_comments_are_left_alone(tmp_path):
    tricky = ('"note": "babelscribe\\": {}, // not a comment /* nor this */ }]",\n  "url": "https://x//y",\n'
              '  "agent": {"babelscribe": "mine"},\n  "list": ["babelscribe", "{", "\\\\"],\n  ')
    env = make(tmp_path)
    check_removed(env, f'{{\n  {tricky}"mcp": {{"servers": {{"babelscribe": {E}}}}}\n}}',
                  f'{{\n  {tricky}"mcp": {{"servers": {{}}}}\n}}')


@pytest.mark.parametrize("broken", ['{"mcp": {"servers": {"babelscribe": ', '{"mcp": /* babelscribe', '{"babelscribe" 1}',
                                    '{"a": NaN, "babelscribe": 1}', '["babelscribe"]', '{} {"babelscribe": 1}',
                                    "[" * 100_000 + '"babelscribe"'], ids=lambda s: s[:30])
def test_a_broken_file_is_refused_and_left_as_it_is(tmp_path, broken):
    env = make(tmp_path)
    path = put(settings(env), broken)
    with pytest.raises(ConnectError, match="left it"):
        connect.remove("opencode", env)
    assert path.read_text(encoding="utf-8") == broken and [p.name for p in path.parent.iterdir()] == ["opencode.json"]


def test_an_entry_that_starts_something_else_stays_next_to_ours_and_in_remove_all(tmp_path):
    env = make(tmp_path)
    foreign = '{"type": "local", "command": ["uvx", "babelscribe", "mcp"]}'
    mine = put(settings(env), f'{{"mcp": {{"servers": {{"babelscribe": {E}}}}}}}')
    other = put(settings(env, "opencode.jsonc"), f'{{"mcp": {{"babelscribe": {foreign}}}}}')
    connect.remove("opencode", env)
    assert mine.read_text(encoding="utf-8") == '{"mcp": {"servers": {}}}' and foreign in other.read_text(encoding="utf-8")
    assert connect.state("opencode", env)[0] == "other"
    assert connect.remove_all(env)["results"] == [] and foreign in other.read_text(encoding="utf-8")
    assert connect.remove("opencode", env)["changed"], "Remove on 'set up another way', as for the other apps"
    assert other.read_text(encoding="utf-8") == '{"mcp": {}}'


def test_remove_all_takes_ours_out_of_every_file_that_has_it(tmp_path):
    env = make(tmp_path, found=())                               # OpenCode may be gone already: no program is needed
    paths = [put(settings(env, n), f'{{"mcp": {{"servers": {{"babelscribe": {E}}}}}}}')
             for n in ("opencode.json", ".opencode/opencode.jsonc")]
    r = connect.remove_all(env)
    assert r["removed"] == ["opencode"]
    assert all(p.read_text(encoding="utf-8") == '{"mcp": {"servers": {}}}' for p in paths)
    assert connect.plan("opencode", env)["can_remove"] is False


def test_remove_can_be_pressed_when_connect_cannot(tmp_path):
    env = make(tmp_path, V1_HELP)
    put(settings(env), f'{{"mcp": {{"babelscribe": {E}}}}}')
    p = connect.plan("opencode", env)
    assert p["problem"] and p["can_remove"] and p["state"] == "connected"
    assert connect.remove("opencode", env)["changed"]


def test_a_second_broken_file_that_names_babelscribe_is_reported_after_the_removal(tmp_path):
    env = make(tmp_path)
    good = put(settings(env), f'{{"mcp": {{"servers": {{"babelscribe": {E}}}}}}}')
    bad = put(settings(env, "opencode.jsonc"), '{"babelscribe": ')
    r = connect.remove_all(env)
    assert "could not be checked" in r["results"][0]["error"]
    assert "babelscribe" not in good.read_text(encoding="utf-8") and bad.read_text(encoding="utf-8") == '{"babelscribe": '


def test_remove_when_it_is_not_there_changes_nothing(tmp_path):
    env = make(tmp_path)
    assert connect.remove("opencode", env)["changed"] is False
    put(settings(env), '{"mcp": {"servers": {"a": 1}}}')
    put(settings(env, "opencode.jsonc"), '{"broken": ')           # says nothing about babelscribe
    assert connect.remove("opencode", env)["changed"] is False


def test_a_failed_write_leaves_the_file_as_it_was(tmp_path, monkeypatch):
    env = make(tmp_path)
    text = f'{{"mcp": {{"servers": {{"babelscribe": {E}}}}}}}'
    path = put(settings(env), text)

    def refuse(*a):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(connect.os, "replace", refuse)
    with pytest.raises(ConnectError, match="Nothing was changed"):
        connect.remove("opencode", env, make_backup=False)
    assert path.read_text(encoding="utf-8") == text and [p.name for p in path.parent.iterdir()] == ["opencode.json"]


@pytest.mark.parametrize("restore_works", [True, False], ids=["restored", "stuck"])
def test_when_the_second_file_cannot_be_written_the_first_is_put_back_or_named(tmp_path, monkeypatch, restore_works):
    env = make(tmp_path)
    text = f'{{"mcp": {{"servers": {{"babelscribe": {E}}}}}}}'
    first, second = put(settings(env), text), put(settings(env, "opencode.jsonc"), text)
    real, calls = connect.os.replace, []

    def replace(a, b):
        calls.append(Path(b).name)
        if Path(b).name == "opencode.jsonc" or (not restore_works and len(calls) > 2):
            raise PermissionError(13, "Access is denied")
        real(a, b)
    monkeypatch.setattr(connect.os, "replace", replace)
    with pytest.raises(ConnectError) as e:
        connect.remove("opencode", env, make_backup=False)
    assert second.read_text(encoding="utf-8") == text
    if restore_works:
        assert first.read_text(encoding="utf-8") == text and "Nothing was changed" in str(e.value)
    else:
        assert "already out of" in str(e.value) and str(first) in str(e.value) and "Nothing was changed" not in str(e.value)
    assert sorted(p.name for p in first.parent.iterdir()) == ["opencode.json", "opencode.jsonc"]


@pytest.mark.parametrize("wrong", [
    lambda text, obj, i: [(obj.members[i].start, obj.members[i].end + 1)],                  # takes a brace too
    lambda text, obj, i: [(obj.members[0].start, obj.members[i].end)],                      # takes the neighbour too
    lambda text, obj, i: [(obj.members[0].start, obj.members[0].end)],                      # takes the wrong member
    lambda text, obj, i: [(obj.members[i].start + 1, obj.members[i].end)],                  # leaves half a quote
], ids=["brace", "neighbour", "wrong-member", "half"])
def test_an_edit_that_would_not_check_out_writes_nothing(tmp_path, monkeypatch, wrong):
    env = make(tmp_path)
    text = f'{{"mcp": {{"servers": {{"a": 1, "babelscribe": {E}}}}}}}'
    path = put(settings(env), text)
    monkeypatch.setattr(jsonc, "_cuts", wrong)
    with pytest.raises(ConnectError, match="could not edit.*nothing was changed"):
        connect.remove("opencode", env, make_backup=False)
    assert path.read_text(encoding="utf-8") == text and [p.name for p in path.parent.iterdir()] == ["opencode.json"]


def test_every_removal_from_generated_files_keeps_the_rest(tmp_path):
    """Our entry at every place, between members, comments, line breaks and trailing commas in every combination."""
    import itertools
    spaces = ["", " ", "\n  ", "\r\n\t", " // n\n  ", " /* n */ ", "\n  /* a\n b */\n"]
    for position, before, after, trailing in itertools.product(range(3), spaces, spaces, (False, True)):
        names = ["a", "b"]
        names.insert(position, "babelscribe")
        body = ""
        for k, name in enumerate(names):
            value = E if name == "babelscribe" else '{"x": [1, "}"]}'
            comma = "," if k < 2 or trailing else ""
            body += f'{before}"{name}": {value}{after}{comma}'
        text = '{"mcp": {"servers": {' + body + "\n}}}"
        new = jsonc.remove(text, ("mcp", "servers"), "babelscribe")
        assert list(jsonc.parse(new).value["mcp"]["servers"]) == ["a", "b"], (text, new)
        if not trailing and "/" not in before + after:
            json.loads(new)                              # a strict JSON file stays strict JSON
        assert new.count("n */") + new.count("// n") + new.count("b */") == \
            text.count("n */") + text.count("// n") + text.count("b */"), (text, new)
