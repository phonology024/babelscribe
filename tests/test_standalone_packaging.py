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
