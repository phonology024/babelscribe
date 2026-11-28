"""A Linux without the Vulkan library (libvulkan1) gets the CPU build of whisper-cli and a plain sentence, not
"error while loading shared libraries"."""
import subprocess

import pytest

from babelscribe import backend

LOADER_ERROR = ("whisper-cli: error while loading shared libraries: libvulkan.so.1: cannot open shared object file: "
                "No such file or directory\n")


@pytest.fixture
def linux(monkeypatch, tmp_path):
    monkeypatch.setattr(backend.platform, "system", lambda: "Linux")
    monkeypatch.setattr(backend.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(backend, "CACHE", tmp_path / "home")
    monkeypatch.setattr(backend, "RELEASES", backend.DEFAULT_RELEASES)


def cached(name: str) -> "backend.Path":
    exe = backend.CACHE / "bin" / name / backend.EXE
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    return exe


def test_without_the_vulkan_library_the_default_build_is_cpu_and_the_user_is_told_once(linux, monkeypatch, capsys):
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.asset_name() == "whisper-cli-linux-x64-cpu.zip"
    said = capsys.readouterr().err
    assert "no Vulkan library" in said and "CPU build" in said and "sudo apt install libvulkan1" in said
    assert said.count("babelscribe:") == 1, "one notice, not one per call"


def test_with_the_library_the_default_stays_vulkan_and_a_flavour_asked_for_is_kept(linux, monkeypatch, capsys):
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.asset_name() == "whisper-cli-linux-x64-vulkan.zip"
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.asset_name("vulkan") == "whisper-cli-linux-x64-vulkan.zip"      # asked for: no silent change
    assert capsys.readouterr().err == ""


def test_other_systems_never_look_for_the_library(monkeypatch):
    for system in ("Windows", "Darwin"):
        monkeypatch.setattr(backend.platform, "system", lambda s=system: s)
        assert backend.vulkan_loader_missing() is False


def test_the_probe_names_the_missing_library(monkeypatch, tmp_path):
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 127, "", LOADER_ERROR))
    with pytest.raises(backend.MissingLibrary) as e:
        backend.probe_devices(tmp_path / "whisper-cli", tmp_path / "m.bin")
    assert str(e.value) == "libvulkan.so.1"


def test_a_cached_vulkan_build_that_cannot_start_is_replaced_by_the_cpu_build(linux, monkeypatch, capsys, tmp_path):
    vulkan = cached("whisper-cli-linux-x64-vulkan")
    fetched = []
    cpu_exe = tmp_path / "cpu" / backend.EXE
    cpu_exe.parent.mkdir()
    cpu_exe.write_bytes(b"x")
    monkeypatch.setattr(backend, "fetch_binary", lambda flavor=None: (fetched.append(flavor), cpu_exe)[1])

    def probe(binary, model):
        if binary == vulkan:
            raise backend.MissingLibrary("libvulkan.so.1")
        return [{"backend": "cpu", "id": 0, "name": "CPU", "detail": ""}]
    monkeypatch.setattr(backend, "probe_devices", probe)
    binary, found = backend.probe_or_refetch(vulkan, tmp_path / "m.bin", None)
    assert binary == cpu_exe and fetched == ["cpu"] and found[0]["backend"] == "cpu"
    assert not vulkan.exists(), "the build that cannot run is not kept to fail again"
    assert "CPU build" in capsys.readouterr().err


@pytest.mark.parametrize("flavor,own_build", [("vulkan", False), (None, True)])
def test_a_flavour_you_asked_for_and_your_own_build_are_not_swapped_behind_your_back(linux, monkeypatch, tmp_path,
                                                                                    flavor, own_build):
    exe = tmp_path / "mine" / backend.EXE if own_build else cached("whisper-cli-linux-x64-vulkan")
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"x")
    monkeypatch.setattr(backend, "probe_devices", lambda b, m: (_ for _ in ()).throw(backend.MissingLibrary("libvulkan.so.1")))
    monkeypatch.setattr(backend, "fetch_binary", lambda flavor=None: pytest.fail("must not download"))
    with pytest.raises(SystemExit) as e:
        backend.probe_or_refetch(exe, tmp_path / "m.bin", flavor)
    assert "libvulkan.so.1 is not installed" in str(e.value) and "--flavor cpu" in str(e.value)
    assert exe.exists()


def test_another_missing_library_is_reported_as_it_is(linux, monkeypatch, tmp_path):
    exe = cached("whisper-cli-linux-x64-cpu")
    monkeypatch.setattr(backend, "probe_devices", lambda b, m: (_ for _ in ()).throw(backend.MissingLibrary("libgomp.so.1")))
    with pytest.raises(SystemExit) as e:
        backend.probe_or_refetch(exe, tmp_path / "m.bin", None)
    assert "libgomp.so.1 is not installed" in str(e.value) and "vulkan" not in str(e.value).lower()


def test_a_cached_cpu_build_does_not_outrank_vulkan_once_the_library_is_there(linux, monkeypatch):
    cpu, vulkan = cached("whisper-cli-linux-x64-cpu"), cached("whisper-cli-linux-x64-vulkan")
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.find_binary() == vulkan
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: True)
    assert backend.find_binary() == cpu
    monkeypatch.setattr(backend, "vulkan_loader_missing", lambda: False)
    assert backend.find_binary(flavor="cpu") == cpu                                  # the flavour asked for first


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
