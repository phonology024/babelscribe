"""CI check of the engine as the installed app runs it: babelscribe-engine.exe with --progress-json.

    python desktop/scripts/check_engine.py "<install folder>/babelscribe-engine.exe" jfk.wav [FLAVOR]

Runs one real transcription (tiny model; FLAVOR of whisper-cli, default "cpu": CI machines have no GPU; "default" leaves
the choice to the engine, as on Apple Silicon, which has only a Metal build) the way the window does,
and checks what the window relies on: every stdout line is one JSON event, progress never goes back and reaches
100, the last event is "done" with files that exist. Standard library only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    engine, sample = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    flavor = sys.argv[3] if len(sys.argv) > 3 else "cpu"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "my files"                          # a space in the path, as on a real desktop
        work.mkdir()
        audio = work / sample.name
        shutil.copyfile(sample, audio)
        # BABELSCRIBE_HOME from the caller keeps the downloaded whisper-cli and model for a later step
        env = {**os.environ, "BABELSCRIBE_HOME": os.environ.get("BABELSCRIBE_HOME") or str(Path(tmp) / "home")}
        cmd = [str(engine), str(audio), "-m", "tiny", "-l", "en", "-f", "srt,txt", "--progress-json"]
        if flavor != "default":
            cmd += ["--flavor", flavor]
        p = subprocess.run(cmd, env=env, capture_output=True, timeout=1200)
        out = p.stdout.decode("ascii")                         # the events are ASCII-only JSON
        print(out[-1500:])
        print(p.stderr.decode("utf-8", "replace")[-1500:])
        assert p.returncode == 0, f"exit code {p.returncode}"
        events = [json.loads(line) for line in out.splitlines() if line.strip()]
        kinds = {e["event"] for e in events}
        assert kinds <= {"log", "progress", "done"}, kinds
        pct = [e["percent"] for e in events if e["event"] == "progress"]
        assert pct and pct == sorted(pct) and pct[-1] == 100, pct
        done = events[-1]
        assert done["event"] == "done" and done["lang"] == "en", done
        assert sorted(Path(f).suffix for f in done["files"]) == [".srt", ".txt"], done["files"]
        assert all(Path(f).is_file() for f in done["files"]), done["files"]
        srt = audio.with_suffix(".srt").read_text(encoding="utf-8")
        assert "-->" in srt and "country" in srt.lower(), srt
        print(f"engine OK: {len(pct)} progress events, {done['segments']} segments")


if __name__ == "__main__":
    main()
