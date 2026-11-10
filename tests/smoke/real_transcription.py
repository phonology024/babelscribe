"""One real transcription, end to end: ffmpeg, whisper-cli, the model, the writers, and the MCP server over stdio.

Not collected by pytest (no test_ prefix): it downloads a binary and a model and takes about a minute.
The unit tests mock subprocess and ffmpeg everywhere, so this is the only check that a release can transcribe.

  python tests/smoke/real_transcription.py jfk.wav                 # prebuilt CPU binary for this OS, tiny model
  python tests/smoke/real_transcription.py jfk.wav --bin ./whisper-cli --no-mcp   # a binary that was just built

jfk.wav is whisper.cpp's samples/jfk.wav (11 s, "ask not what your country can do for you ...").
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PHRASE = "ask not what your country can do for you"
FORMATS = ["srt", "vtt", "txt", "json", "ass"]
MODEL = "tiny"


def words(text: str) -> str:
    return " ".join(re.findall(r"[a-z']+", text.lower()))


def check(ok: bool, what: str) -> None:
    print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
    if not ok:
        raise SystemExit(f"smoke test failed: {what}")


def srt_times(text: str) -> list[float]:
    out = []
    for h, m, s, ms in re.findall(r"^(\d\d):(\d\d):(\d\d),(\d\d\d) -->", text, re.MULTILINE):
        out.append(int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000)
    return out


def cli_run(audio: Path, work: Path, bin: str | None, flavor: str | None) -> None:
    print("CLI: one file, every format", flush=True)
    src = work / "cli" / audio.name
    src.parent.mkdir(parents=True)
    shutil.copy(audio, src)
    cmd = [sys.executable, "-m", "babelscribe.cli", str(src), "-m", MODEL, "-l", "en", "-f", ",".join(FORMATS)]
    if bin:
        cmd += ["--bin", bin]
    elif flavor:
        cmd += ["--flavor", flavor]
    p = subprocess.run(cmd)
    check(p.returncode == 0, f"exit code 0 (got {p.returncode})")
    for f in FORMATS:
        out = src.with_suffix("." + f)
        check(out.is_file() and out.stat().st_size > 0, f"{out.name} written")
    check(PHRASE in words(src.with_suffix(".txt").read_text(encoding="utf-8")), f'txt contains "{PHRASE}"')
    times = srt_times(src.with_suffix(".srt").read_text(encoding="utf-8"))
    check(bool(times) and times == sorted(times), f"srt timestamps increase ({len(times)} cues)")
    data = json.loads(src.with_suffix(".json").read_text(encoding="utf-8"))
    check({"meta", "segments"} <= set(data) and len(data["segments"]) > 0, "json has meta and segments")
    check("Dialogue:" in src.with_suffix(".ass").read_text(encoding="utf-8"), "ass has dialogue lines")
    check("WEBVTT" in src.with_suffix(".vtt").read_text(encoding="utf-8"), "vtt has its header")


def payload(result) -> dict:
    """The tool's returned dict, whichever way this SDK version hands it over."""
    for attr in ("structured_content", "structuredContent"):
        data = getattr(result, attr, None)
        if isinstance(data, dict):
            return data.get("result", data) if set(data) == {"result"} else data
    return json.loads(result.content[0].text)


async def mcp_run(audio: Path, work: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    print("MCP: transcribe and transcribe_folder through a real stdio client", flush=True)
    one = work / "mcp" / audio.name
    folder = work / "mcp" / "folder"
    folder.mkdir(parents=True)
    shutil.copy(audio, one)
    shutil.copy(audio, folder / "a.wav")
    shutil.copy(audio, folder / "b.wav")
    env = {**os.environ, "BABELSCRIBE_MODEL": MODEL, "PYTHONUNBUFFERED": "1"}
    server = StdioServerParameters(command=sys.executable, args=["-m", "babelscribe.cli", "mcp"], env=env)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            check({"transcribe", "transcribe_folder", "list_devices"} <= tools, f"server lists its tools ({len(tools)})")

            seen: list[tuple] = []

            async def on_progress(progress, total=None, message=None):
                seen.append((progress, total, message))

            r = await session.call_tool("transcribe", {"file_path": str(one), "language": "en", "formats": "srt,txt"},
                                        progress_callback=on_progress)
            check(not getattr(r, "is_error", getattr(r, "isError", False)), "transcribe returned without an error")
            out = payload(r)
            check(PHRASE in words(out["text"]), "transcribe returns the transcript text")
            check(out["model"] == MODEL, f"BABELSCRIBE_MODEL picked the model ({out['model']})")
            check(one.with_suffix(".srt").is_file(), "transcribe wrote the srt next to the file")
            print(f"        ({len(seen)} progress notification(s) during one short file; they come every 5 s)")

            seen.clear()
            r = await session.call_tool("transcribe_folder", {"folder": str(folder), "language": "en", "formats": "srt"},
                                        progress_callback=on_progress)
            out = payload(r)
            check((out["total"], out["succeeded"], out["failed"]) == (2, 2, 0), "transcribe_folder: 2 of 2 succeeded")
            check((folder / "a.srt").is_file() and (folder / "b.srt").is_file(), "transcribe_folder wrote both srt files")
            check(len(seen) >= 1, f"progress notifications arrived ({len(seen)})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", help="whisper.cpp's samples/jfk.wav")
    ap.add_argument("--bin", help="a whisper-cli that was just built, instead of the prebuilt download")
    ap.add_argument("--flavor", help="prebuilt flavour to download (default: cpu; the Metal build on macOS)")
    ap.add_argument("--no-mcp", action="store_true", help="CLI only")
    a = ap.parse_args()
    audio = Path(a.audio).resolve()
    flavor = a.flavor or (None if platform.system() == "Darwin" else "cpu")
    with tempfile.TemporaryDirectory() as d:
        cli_run(audio, Path(d), a.bin, flavor)
        if not a.no_mcp:
            import anyio
            anyio.run(mcp_run, audio, Path(d))
    print("smoke test passed")


if __name__ == "__main__":
    main()
