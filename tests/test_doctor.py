from pathlib import Path

from babelscribe import cli, doctor


def test_directory_size_and_format_bytes(tmp_path: Path):
    (tmp_path / "a.bin").write_bytes(b"1234")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.bin").write_bytes(b"567890")

    assert doctor.directory_size(tmp_path) == 10
    assert doctor.format_bytes(1024) == "1.0 KB"


def test_report_does_not_download_missing_binary(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    models_dir = tmp_path / "models"

    monkeypatch.setattr(doctor.backend, "CACHE", cache)
    monkeypatch.setattr(doctor.models, "MODELS", models_dir)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    def missing_binary(*args, **kwargs):
        raise FileNotFoundError("not installed")

    monkeypatch.setattr(doctor.backend, "find_binary", missing_binary)

    checks, report = doctor.collect_report()
    results = dict(checks)

    assert "Python" in results
    assert "Operating system" in results
    assert "whisper-cli" in results
    assert "not found" in results["whisper-cli"].lower()
    assert "Babelscribe doctor report" in report


def test_cli_routes_doctor_command(monkeypatch):
    called = []
    monkeypatch.setattr(doctor, "main", lambda: called.append(True))

    cli.main(["doctor"])

    assert called == [True]
