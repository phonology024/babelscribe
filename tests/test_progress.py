"""Real progress (#6): whisper-cli's own percentage reaches transcribe_file(progress=...), the CLI bar and MCP."""
import io
import json
import sys
from pathlib import Path

import pytest

from babelscribe import api, backend, cli, hybrid, models, transcribe


def test_run_cli_hands_over_lines_as_they_come_and_keeps_the_tail_on_failure():
    lines = []
    script = "import sys; print('progress =  50%', file=sys.stderr); print('text')"
    transcribe.run_cli([sys.executable, "-c", script], on_line=lines.append)
    assert [x.strip() for x in lines if x.strip()] and any("50%" in x for x in lines)
    with pytest.raises(RuntimeError) as e:
        transcribe.run_cli([sys.executable, "-c", "import sys; print('model is broken'); sys.exit(3)"],
                           on_line=lambda line: None)
    assert "(3)" in str(e.value) and "model is broken" in str(e.value)


def test_run_cli_ticks_while_the_process_runs():
    ticks = []
    transcribe.run_cli([sys.executable, "-c", "import time; time.sleep(1.2)"], tick=lambda: ticks.append(1))
    assert len(ticks) >= 2      # at least once during the run and once at the end


def _fake_whisper(monkeypatch, said):
    """transcribe.run with ffmpeg skipped and run_cli replaced by one that 'prints' the given lines."""
    seen = {}

    def fake_cli(cmd, verbose=False, on_line=None, tick=None):
        seen["cmd"] = list(cmd)
        for line in said:
            if on_line:
                on_line(line)
        out = cmd[cmd.index("-of") + 1]
        Path(out + ".json").write_text(json.dumps({"transcription": []}), encoding="utf-8")
    monkeypatch.setattr(transcribe, "run_cli", fake_cli)
    monkeypatch.setattr(transcribe, "to_wav16k", lambda *a, **k: None)
    return seen


def test_transcribe_run_reads_whisper_cli_progress_lines(monkeypatch, tmp_path):
    said = ["whisper_print_progress_callback: progress =  11%\n", "[00:00:00.000 --> 00:00:02.000]  hi\n",
            "whisper_print_progress_callback: progress = 100%\n"]
    seen = _fake_whisper(monkeypatch, said)
    got = []
    transcribe.run(Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", "en", 0, progress=got.append)
    assert got == [11.0, 100.0] and "-pp" in seen["cmd"]
    transcribe.run(Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", "en", 0)
    assert "-pp" not in seen["cmd"], "without a listener the command line is the one it always was"


def _api_run(monkeypatch, tmp_path, timing, text=None, **kw):
    seg = [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}]
    monkeypatch.setattr(api, "setup", lambda *a, **k: (tmp_path / "whisper-cli", tmp_path / "m.bin",
                                                       [{"id": 0, "backend": "cpu", "name": "CPU"}]))
    monkeypatch.setattr(models, "ensure", lambda *a, **k: tmp_path / "ft.bin")
    monkeypatch.setattr(models, "resolve", lambda name: (name, None))

    def fake_timing(*a, progress=None, **k):
        [progress(x) for x in timing if progress]
        return seg

    def fake_text(*a, progress=None, **k):
        [progress(x) for x in (text or []) if progress]
        return seg
    monkeypatch.setattr(transcribe, "run", fake_timing)
    monkeypatch.setattr(hybrid, "run", fake_text)
    (tmp_path / "a.wav").write_bytes(b"x")
    got = []
    api.transcribe_file(tmp_path / "a.wav", lang="en", formats=["srt"], log=lambda m: None, progress=got.append, **kw)
    return got


def test_transcribe_file_progress_never_goes_back_and_ends_at_100(monkeypatch, tmp_path):
    got = _api_run(monkeypatch, tmp_path, [10, 50, 30, 90])     # 30 after 50 is dropped
    assert got == [10.0, 50.0, 90.0, 100.0]


def test_transcribe_file_progress_splits_timing_and_text_pass(monkeypatch, tmp_path):
    got = _api_run(monkeypatch, tmp_path, [50, 100], text=[50, 100], text_model="thai-thonburian")
    assert got == [20.0, 40.0, 70.0, 100.0]


def test_transcribe_file_without_progress_passes_nothing_new(monkeypatch, tmp_path):
    """Stand-ins and older callers of transcribe.run have no progress argument; they must keep working."""
    monkeypatch.setattr(api, "setup", lambda *a, **k: (tmp_path / "whisper-cli", tmp_path / "m.bin",
                                                       [{"id": 0, "backend": "cpu", "name": "CPU"}]))
    monkeypatch.setattr(transcribe, "run", lambda binary, model, media, lang, dev, beam=None, verbose=False,
                        prompt=None, translate=False: [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}])
    (tmp_path / "a.wav").write_bytes(b"x")
    assert api.transcribe_file(tmp_path / "a.wav", lang="en", formats=["srt"], log=lambda m: None)["segments"] == 1


def test_progress_bar_draws_one_line_and_wipes_it_at_100():
    out = io.StringIO()
    bar = cli.progress_bar(out, width=10)
    bar(0); bar(42.4); bar(42.9); bar(100)
    text = out.getvalue()
    assert "[----------]   0%" in text and "[####------]  42%" in text
    assert text.count("42%") == 1, "the same whole percent is not redrawn"
    assert "\n" not in text and text.endswith("\r")
    bar(5)                                   # next file of a batch
    assert out.getvalue().endswith("  5%")


def test_cli_draws_no_bar_when_nobody_is_watching(monkeypatch):
    got = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: got.update(k))
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False, raising=False)
    cli.main(["talk.mp4"])
    assert "progress" not in got
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)
    cli.main(["talk.mp4"])
    assert callable(got["progress"])
    got.clear()
    cli.main(["talk.mp4", "--no-progress"])
    assert "progress" not in got


def test_mcp_transcribe_reports_a_real_percentage(tmp_path, monkeypatch):
    pytest.importorskip("mcp.server.mcpserver")
    import time
    import anyio
    from babelscribe import mcp_server
    monkeypatch.setattr(mcp_server, "HEARTBEAT", 0.05)
    sent = []

    async def record(ctx, progress, total, message):
        sent.append((progress, total, message))
    monkeypatch.setattr(mcp_server, "_report_progress", record)

    def slow(src, *a, log=print, progress=None, **k):
        log("transcribing with turbo ...")
        progress(37.0)
        time.sleep(0.4)
        return {"files": [], "lang": "en", "segments": 1, "seconds": 0.4, "text": ""}
    monkeypatch.setattr(api, "transcribe_file", slow)
    (tmp_path / "a.wav").write_bytes(b"x")
    srv = mcp_server.build()
    anyio.run(lambda: srv.call_tool("transcribe", {"file_path": str(tmp_path / "a.wav")}))
    during = [(p, t) for p, t, m in sent if "37%" in m]
    assert during and all(p == 37.0 and t == 100 for p, t in during), sent
    assert sent[-1][:2] == (100, 100)

    sent.clear()
    (tmp_path / "in").mkdir()
    for n in ("a.wav", "b.wav"):
        (tmp_path / "in" / n).write_bytes(b"x")
    anyio.run(lambda: srv.call_tool("transcribe_folder", {"folder": str(tmp_path / "in")}))
    second = [p for p, t, m in sent if m.startswith("b.wav (2/2): ") and t == 2]
    assert second and all(abs(p - 1.37) < 1e-9 for p in second), sent   # one file done + 37% of the second
