"""A computer without the Vulkan library (Linux: libvulkan1; Windows: vulkan-1.dll, as in a virtual machine or with the
basic display driver) gets the CPU build of whisper-cli and a plain sentence, not "error while loading shared libraries"
or a bare exit code."""
import json
import os
import subprocess

import pytest

from babelscribe import backend

LOADER_ERROR = ("whisper-cli: error while loading shared libraries: libvulkan.so.1: cannot open shared object file: "
                "No such file or directory\n")


# per system: what the build is called, what the probe sees when the loader is not there, and the advice given
SYSTEMS = {
    "Linux": {"os": "linux", "machine": "x86_64", "library": "libvulkan.so.1", "named": "libvulkan1",
              "advice": "sudo apt install libvulkan1",
              "exit": (127, "", LOADER_ERROR)},
    "Windows": {"os": "windows", "machine": "AMD64", "library": "vulkan-1.dll", "named": "vulkan-1.dll",
                "advice": "graphics driver",
                "exit": (3221225781, "", "")},          # seen with the real whisper-cli.exe: 0xC0000135, nothing printed
}


@pytest.fixture(params=sorted(SYSTEMS))
def computer(request, monkeypatch, tmp_path):
    s = SYSTEMS[request.param]
    monkeypatch.setattr(backend.platform, "system", lambda: request.param)
    monkeypatch.setattr(backend.platform, "machine", lambda: s["machine"])
    monkeypatch.setattr(backend, "CACHE", tmp_path / "home")
    monkeypatch.setattr(backend, "RELEASES", backend.DEFAULT_RELEASES)
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)
    monkeypatch.delenv("BABELSCRIBE_WHISPER_BIN", raising=False)
    return {**s, "system": request.param}


def cached(name: str) -> "backend.Path":
    exe = backend.CACHE / "bin" / name / backend.EXE
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    return exe


def test_without_the_vulkan_library_the_default_build_is_cpu_and_the_user_is_told_once(computer, monkeypatch, capsys):
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.asset_name() == f"whisper-cli-{computer['os']}-x64-cpu.zip"
    said = capsys.readouterr().err
    assert "no Vulkan library" in said and "CPU build" in said and computer["advice"] in said and computer["named"] in said
    assert said.count("babelscribe:") == 1, "one notice, not one per call"


def test_with_the_library_the_default_stays_vulkan_and_a_flavour_asked_for_is_kept(computer, monkeypatch, capsys):
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.asset_name() == f"whisper-cli-{computer['os']}-x64-vulkan.zip"
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.asset_name("vulkan") == f"whisper-cli-{computer['os']}-x64-vulkan.zip"      # asked for: no change
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("system", ["Linux", "Windows"])
@pytest.mark.parametrize("there", [True, False])
def test_the_library_of_this_system_is_the_one_looked_for(monkeypatch, system, there):
    import ctypes
    looked = []

    def load(name, *a, **k):
        looked.append(name)
        if not there:
            raise FileNotFoundError(name)                   # what Windows raises for a DLL that is not there
    monkeypatch.setattr(ctypes, "CDLL", load)
    monkeypatch.setattr(backend.platform, "system", lambda: system)
    assert backend.vulkan_loader_missing() is (not there) and looked == [SYSTEMS[system]["library"]]


def test_macos_never_looks_for_the_library(monkeypatch):
    import ctypes
    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **k: pytest.fail("looked"))
    monkeypatch.setattr(backend.platform, "system", lambda: "Darwin")
    assert backend.vulkan_loader_missing() is False


@pytest.mark.skipif(os.name != "nt", reason="the real check, on Windows")
def test_the_real_windows_check_loads_or_misses_without_an_error():
    assert backend.vulkan_loader_missing() in (True, False)


@pytest.mark.parametrize("code", [None, -1073741515], ids=["as-seen", "signed"])
def test_the_probe_names_the_missing_library(computer, monkeypatch, tmp_path, code):
    returncode, out, err = computer["exit"]
    if code is not None and computer["system"] == "Windows":
        returncode = code
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, returncode, out, err))
    with pytest.raises(backend.MissingLibrary) as e:
        backend.probe_devices(tmp_path / "whisper-cli", tmp_path / "m.bin")
    assert str(e.value) == computer["library"]


def test_a_missing_dll_with_the_vulkan_loader_there_is_not_blamed_on_vulkan_and_nothing_is_removed(monkeypatch, tmp_path):
    monkeypatch.setattr(backend.platform, "system", lambda: "Windows")
    monkeypatch.setattr(backend, "CACHE", tmp_path / "home")
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 3221225781, "", ""))
    monkeypatch.setattr(backend, "fetch_binary", lambda *a, **k: pytest.fail("must not download"))
    exe = cached("whisper-cli-windows-x64-vulkan")
    with pytest.raises(SystemExit) as e:
        backend.probe_or_refetch(exe, tmp_path / "m.bin", None)
    assert "a DLL it needs" in str(e.value) and "--flavor cpu" in str(e.value) and str(exe.parent) in str(e.value)
    assert "no Vulkan" not in str(e.value) and exe.exists()


def run_that_fails_for(computer, exe):
    """subprocess.run as the real probe sees it: `exe` cannot load its Vulkan library, any other build runs."""
    def run(cmd, **kw):
        if cmd[0] == str(exe):
            return subprocess.CompletedProcess(cmd, *computer["exit"])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


def test_a_cached_vulkan_build_that_cannot_start_is_replaced_by_the_cpu_build(computer, monkeypatch, capsys, tmp_path):
    vulkan = cached(f"whisper-cli-{computer['os']}-x64-vulkan")
    fetched = []
    cpu_exe = tmp_path / "cpu" / backend.EXE
    cpu_exe.parent.mkdir()
    cpu_exe.write_bytes(b"x")

    def fetch(flavor=None):
        assert vulkan.exists(), "removed only once there is something to put in its place"
        fetched.append(flavor)
        return cpu_exe
    monkeypatch.setattr(backend, "fetch_binary", fetch)
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    monkeypatch.setattr(backend.subprocess, "run", run_that_fails_for(computer, vulkan))
    assert backend.find_binary() == vulkan                       # the only build there is: from before, or copied over
    binary, found = backend.probe_or_refetch(vulkan, tmp_path / "m.bin", None)
    assert binary == cpu_exe and fetched == ["cpu"] and found[0]["backend"] == "cpu"
    assert not vulkan.exists(), "the build that cannot run is not kept to fail again"
    said = capsys.readouterr().err
    assert said.count("no Vulkan library") == 1 and computer["advice"] in said


def test_when_the_cpu_build_cannot_be_fetched_the_other_one_is_kept(computer, monkeypatch, tmp_path):
    vulkan = cached(f"whisper-cli-{computer['os']}-x64-vulkan")
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    monkeypatch.setattr(backend.subprocess, "run", run_that_fails_for(computer, vulkan))

    def offline(flavor=None):
        raise SystemExit("the download stopped")
    monkeypatch.setattr(backend, "fetch_binary", offline)
    with pytest.raises(SystemExit, match="download stopped"):
        backend.probe_or_refetch(vulkan, tmp_path / "m.bin", None)
    assert vulkan.exists()


@pytest.mark.parametrize("flavor,own_build", [("vulkan", False), (None, True)])
def test_a_flavour_you_asked_for_and_your_own_build_are_not_swapped_behind_your_back(computer, monkeypatch, tmp_path,
                                                                                    flavor, own_build):
    exe = tmp_path / "mine" / backend.EXE if own_build else cached(f"whisper-cli-{computer['os']}-x64-vulkan")
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"x")
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    monkeypatch.setattr(backend.subprocess, "run", run_that_fails_for(computer, exe))
    monkeypatch.setattr(backend, "fetch_binary", lambda flavor=None: pytest.fail("must not download"))
    with pytest.raises(SystemExit) as e:
        backend.probe_or_refetch(exe, tmp_path / "m.bin", flavor)
    assert f"{computer['library']} is not installed" in str(e.value) and "--flavor cpu" in str(e.value)
    assert computer["advice"] in str(e.value) and exe.exists()


def test_another_missing_library_is_reported_as_it_is(computer, monkeypatch, tmp_path):
    exe = cached(f"whisper-cli-{computer['os']}-x64-cpu")
    monkeypatch.setattr(backend, "probe_devices", lambda b, m: (_ for _ in ()).throw(backend.MissingLibrary("libgomp.so.1")))
    with pytest.raises(SystemExit) as e:
        backend.probe_or_refetch(exe, tmp_path / "m.bin", None)
    assert "libgomp.so.1 is not installed" in str(e.value) and "vulkan" not in str(e.value).lower()


def test_which_cached_build_runs_depends_on_the_library_being_there(computer, monkeypatch):
    cpu, vulkan = (cached(f"whisper-cli-{computer['os']}-x64-{f}") for f in ("cpu", "vulkan"))
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.find_binary() == vulkan
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.find_binary() == cpu                          # one run with --flavor cpu was enough, and still is
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.find_binary(flavor="cpu") == cpu                                  # the flavour asked for first


def stand_in(computer, mark=True):
    exe = cached(f"whisper-cli-{computer['os']}-x64-cpu")
    receipt = {"asset": exe.parent.name + ".zip"}
    if mark is not None:
        receipt["stand_in"] = mark
    (exe.parent / backend.RECEIPT).write_text(json.dumps(receipt), encoding="utf-8")
    return exe


def test_the_gpu_build_comes_once_the_library_is_there(computer, monkeypatch, tmp_path):
    """"Install the library and run babelscribe again" has to work, with only the CPU build cached."""
    cpu = stand_in(computer)
    fetched = []
    monkeypatch.setattr(backend, "fetch_binary", lambda flavor=None: (fetched.append(flavor), tmp_path / "gpu")[1])
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.find_binary() == cpu and fetched == []
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.find_binary(flavor="cpu") == cpu and backend.find_binary(download=False) == cpu and fetched == []
    assert backend.find_binary() == tmp_path / "gpu" and fetched == [None]


@pytest.mark.parametrize("mark", [None, False], ids=["from-an-older-babelscribe", "not-a-stand-in"])
def test_other_cached_builds_are_left_alone(computer, monkeypatch, mark):
    cpu = stand_in(computer, mark)
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    monkeypatch.setattr(backend, "fetch_binary", lambda flavor=None: pytest.fail("must not download"))
    assert backend.find_binary() == cpu


@pytest.mark.parametrize("failure", [SystemExit("the download stopped"), OSError("disk")], ids=["offline", "disk"])
def test_when_the_gpu_build_cannot_be_had_the_cpu_build_still_works(computer, monkeypatch, capsys, failure):
    cpu = stand_in(computer)
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)

    def cannot(flavor=None):
        raise failure
    monkeypatch.setattr(backend, "fetch_binary", cannot)
    assert backend.find_binary() == cpu
    assert "CPU build is used this time" in capsys.readouterr().err


def test_a_flavour_asked_for_is_never_answered_with_another_cached_one(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "CACHE", tmp_path)
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)
    monkeypatch.delenv("BABELSCRIBE_WHISPER_BIN", raising=False)
    vulkan = tmp_path / "bin" / "whisper-cli-windows-x64-vulkan" / backend.EXE
    vulkan.parent.mkdir(parents=True)
    vulkan.write_bytes(b"x")
    fetched = []
    monkeypatch.setattr(backend, "fetch_binary", lambda flavor=None: (fetched.append(flavor), tmp_path / "cpu")[1])
    assert backend.find_binary(flavor="cpu") == tmp_path / "cpu" and fetched == ["cpu"]
    with pytest.raises(FileNotFoundError):
        backend.find_binary(flavor="cpu", download=False)
    assert backend.find_binary(flavor="vulkan") == vulkan and backend.find_binary() == vulkan


@pytest.mark.parametrize("system,cached,chosen", [
    ("Windows", ["windows-x64-cpu", "windows-x64-vulkan"], "windows-x64-vulkan"),      # after one --flavor cpu run
    ("Windows", ["windows-x64-cpu"], "windows-x64-cpu"),
    ("Darwin", ["macos-arm64-cpu", "macos-arm64-metal"], "macos-arm64-metal"),
    ("Linux", ["linux-x64-cpu", "linux-x64-cuda"], "linux-x64-cuda"),
    ("Linux", ["linux-x64-cpu", "linux-x64-cuda", "linux-x64-vulkan"], "linux-x64-vulkan"),
], ids=["windows", "windows-cpu-only", "mac", "linux-cuda", "linux-all"])
def test_without_a_flavour_a_cached_gpu_build_comes_before_a_cpu_one(monkeypatch, tmp_path, system, cached, chosen):
    monkeypatch.setattr(backend, "CACHE", tmp_path)
    monkeypatch.setattr(backend.platform, "system", lambda: system)
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    monkeypatch.delenv("BABELSCRIBE_WHISPER_BIN", raising=False)
    for name in cached:
        folder = tmp_path / "bin" / f"whisper-cli-{name}"
        folder.mkdir(parents=True)
        (folder / backend.EXE).write_bytes(b"x")
    assert backend.find_binary(download=False).parent.name == f"whisper-cli-{chosen}"
