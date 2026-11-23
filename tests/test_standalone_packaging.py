"""The standalone Windows build (#59). The build itself is tested by CI (build-standalone.yml runs
packaging/standalone/smoke_test.py on the real executables); these checks keep its recipe in step with the package."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "packaging" / "standalone"


def test_each_console_script_has_an_entry_that_calls_the_same_function():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = {name: (module, func)
               for name, module, func in re.findall(r'^(babelscribe[\w-]*) = "([\w.]+):(\w+)"$', pyproject, re.MULTILINE)}
    spec = (HERE / "babelscribe.spec").read_text(encoding="utf-8")
    built = dict((name, script) for script, name in re.findall(r'program\("([\w.]+)", "([\w-]+)"\)', spec))
    assert set(built) == set(scripts) == {"babelscribe", "babelscribe-mcp"}
    for name, (module, func) in scripts.items():
        entry = (HERE / built[name]).read_text(encoding="utf-8")
        assert f"from {module} import {func}" in entry, name


def test_the_workflow_builds_from_this_spec_and_runs_the_smoke_test():
    wf = (ROOT / ".github" / "workflows" / "build-standalone.yml").read_text(encoding="utf-8")
    assert "packaging/standalone/babelscribe.spec" in wf and "packaging/standalone/smoke_test.py" in wf
    assert "packaging/standalone/THIRD-PARTY.txt" in wf and (HERE / "THIRD-PARTY.txt").is_file()
    assert "windows-x64" in wf and "sha256sum" in wf


def test_the_smoke_test_hides_python_from_the_programs(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("smoke_test", HERE / "smoke_test.py")
    smoke = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoke)
    monkeypatch.setenv("PYTHONPATH", "x"); monkeypatch.setenv("PYTHONHOME", "y"); monkeypatch.setenv("VIRTUAL_ENV", "z")
    env = smoke.clean_env(tmp_path)
    assert not [k for k in env if k.upper().startswith("PYTHON") or k.upper() == "VIRTUAL_ENV"]
    assert "python" not in env["PATH"].lower() and env["BABELSCRIBE_HOME"] == str(tmp_path)


def _frozen_env():
    import importlib.util
    spec = importlib.util.spec_from_file_location("frozen_env", HERE / "frozen_env.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_programs_the_linux_engine_starts_get_the_library_path_it_was_started_with(monkeypatch):
    """PyInstaller puts its own folder first in LD_LIBRARY_PATH; whisper-cli and the GPU driver it loads must not see it."""
    import subprocess
    import sys
    fe = _frozen_env()
    seen = []
    monkeypatch.setattr(subprocess.Popen, "__init__", lambda self, *a, **k: seen.append((a, k)))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/app/_internal:/orig")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/orig")
    assert fe.install() is True

    subprocess.Popen(["whisper-cli"])                                           # no env: the engine's own, restored
    assert seen[-1][1]["env"]["LD_LIBRARY_PATH"] == "/orig"
    subprocess.Popen(["ffmpeg"], env={"LD_LIBRARY_PATH": "/app/_internal", "LD_LIBRARY_PATH_ORIG": "/x", "A": "1"})
    assert seen[-1][1]["env"]["LD_LIBRARY_PATH"] == "/x" and seen[-1][1]["env"]["A"] == "1"
    subprocess.Popen(["ffmpeg"], -1, None, None, None, None, None, True, False, None, {"LD_LIBRARY_PATH": "/b",
                                                                                      "LD_LIBRARY_PATH_ORIG": "/y"})
    assert seen[-1][0][10]["LD_LIBRARY_PATH"] == "/y" and "env" not in seen[-1][1]
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")                                  # the engine was started with none set
    subprocess.Popen(["whisper-cli"])
    assert "LD_LIBRARY_PATH" not in seen[-1][1]["env"]


def test_the_library_path_is_left_alone_outside_a_frozen_linux_build(monkeypatch):
    import subprocess
    import sys
    fe = _frozen_env()
    real = subprocess.Popen.__init__
    assert fe.install() is False                                                # not frozen (this test run)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    for platform in ("win32", "darwin"):
        monkeypatch.setattr(sys, "platform", platform)
        assert fe.install() is False
    assert subprocess.Popen.__init__ is real
    assert fe.child_env({"A": "1"}) == {"A": "1"}
