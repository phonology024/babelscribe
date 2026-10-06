"""Run whisper.cpp on any audio/video file and return segments [{start, end, text, words: [[text, t0, t1], ...]}]."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("ffmpeg not found: install it or `pip install imageio-ffmpeg`")


def to_wav16k(src: Path, dst: Path, start: float | None = None, end: float | None = None, tail_silence: float = 0) -> None:
    cmd = [ffmpeg(), "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000"]
    if tail_silence:   # whisper tends to drop the last words when audio stops abruptly
        cmd += ["-af", f"apad=pad_dur={tail_silence}"]
    cmd += ["-c:a", "pcm_s16le", str(dst)]
    subprocess.run(cmd, check=True, stdout=sys.stderr)   # never stdout: it is the MCP channel


def run(binary: Path, model: Path, media: Path, lang: str = "auto", device: int = 0, beam: int | None = None,
        threads: int | None = None, extra: list[str] | None = None, verbose: bool = False) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "in.wav"
        to_wav16k(media, wav)
        out = Path(d) / "out"
        # -mc 0: never feed previous text back as a prompt — stops the repeat-loop hallucination on long files
        cmd = [str(binary), "-m", str(model), "-f", str(wav), "-l", lang, "-ojf", "-of", str(out), "-mc", "0", "-dev", str(device)]
        if beam:
            cmd += ["-bs", str(beam)]
        if threads:
            cmd += ["-t", str(threads)]
        cmd += extra or []
        p = subprocess.run(cmd, capture_output=not verbose, text=True, errors="replace")
        if p.returncode:
            raise RuntimeError(f"whisper-cli failed ({p.returncode}):\n{(p.stderr or '')[-2000:]}")
        data = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8", errors="replace"))
    segs = []
    for s in data.get("transcription", []):
        words = [[t["text"], t["offsets"]["from"] / 1000, t["offsets"]["to"] / 1000] for t in s.get("tokens", [])
                 if not t["text"].startswith("[_") and t["text"].strip()]
        segs.append({"start": s["offsets"]["from"] / 1000, "end": s["offsets"]["to"] / 1000, "text": s["text"].strip(), "words": words})
    return [s for s in segs if s["text"]]


def detected_language(binary: Path, model: Path, media: Path, device: int = 0) -> str:
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "in.wav"
        to_wav16k(media, wav, 0, 30)
        p = subprocess.run([str(binary), "-m", str(model), "-f", str(wav), "-l", "auto", "-dl", "-dev", str(device)],
                           capture_output=True, text=True, errors="replace")
    import re
    m = re.search(r"auto-detected language: (\w+)", p.stdout + p.stderr)
    return m.group(1) if m else "auto"
