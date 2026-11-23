import pytest

from babelscribe import ram


@pytest.fixture(autouse=True)
def _same_on_every_computer(request, monkeypatch):
    """No test depends on how much memory the computer running it has free (test_ram.py sets its own values)."""
    if not request.module.__name__.endswith("test_ram"):
        monkeypatch.setattr(ram, "detect", lambda: None)
