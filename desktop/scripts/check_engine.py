"""CI check of the engine as the installed app runs it: babelscribe-engine.exe with --progress-json.

    python desktop/scripts/check_engine.py "<install folder>/babelscribe-engine.exe" jfk.wav

Runs one real transcription (tiny model, CPU build of whisper-cli: CI machines have no GPU) the way the window does,
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
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "my files"                          # a space in the path, as on a real desktop
        work.mkdir()
        audio = work / sample.name
        shutil.copyfile(sample, audio)
        env = {**os.environ, "BABELSCRIBE_HOME": str(Path(tmp) / "home")}
        p = subprocess.run([str(engine), str(audio), "-m", "tiny", "--flavor", "cpu", "-l", "en", "-f", "srt,txt",
                            "--progress-json"], env=env, capture_output=True, timeout=1200)
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
