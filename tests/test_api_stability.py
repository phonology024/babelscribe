"""Pins the public surface listed in API_STABILITY.md. Additions are fine; removing or renaming fails."""
import inspect
import json

import pytest

from babelscribe import api, cli

CLI_FLAGS = {"-l", "--lang", "-m", "--model", "--text-model", "--accurate", "--prompt", "-f", "--formats",
             "-o", "--out", "--device", "--bin", "--flavor", "-v", "--verbose", "--version"}
TRANSCRIBE_FILE_ARGS = {"src", "lang", "model", "text_model", "accurate", "formats", "out", "device", "bin",
                        "flavor", "verbose", "log", "prompt"}
MCP_TRANSCRIBE_ARGS = {"file_path", "language", "accurate", "formats", "output_dir", "vocabulary"}
MCP_TOOLS = {"transcribe", "find_media", "list_devices", "list_languages_and_models"}


def test_transcribe_file_keeps_public_arguments():
    params = inspect.signature(api.transcribe_file).parameters
    assert TRANSCRIBE_FILE_ARGS <= set(params)
    assert all(p.default is not inspect.Parameter.empty for n, p in params.items() if n not in ("src",))


def test_cli_keeps_public_flags(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for flag in CLI_FLAGS:
        assert flag in out, flag


def test_mcp_tools_and_transcribe_schema():
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import mcp_server
    srv = mcp_server.build()
    tools = {t.name: t for t in anyio.run(srv.list_tools)}
    assert MCP_TOOLS <= set(tools)
    t = tools["transcribe"]
    schema = getattr(t, "input_schema", None) or t.inputSchema   # attribute name differs between mcp versions
    props = schema["properties"]
    assert MCP_TRANSCRIBE_ARGS <= set(props)
    assert schema.get("required") == ["file_path"]


def test_json_output_keys(tmp_path):
    from babelscribe import writers
    segs = [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}]
    (p,) = writers.write(segs, tmp_path / "x", ["json"], {"lang": "en"})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert {"meta", "segments"} <= set(data)


def test_output_formats_are_the_pinned_ones(tmp_path):
    from babelscribe import writers
    segs = [{"start": 0.0, "end": 1.0, "text": "hi", "words": [["hi", 0.0, 1.0]]}]
    for fmt in ("srt", "vtt", "txt", "json", "ass"):
        (p,) = writers.write(segs, tmp_path / fmt, [fmt], {"lang": "en"})
        assert p.exists() and p.read_text(encoding="utf-8").strip(), fmt
