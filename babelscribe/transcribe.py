"""Run whisper.cpp on any audio/video file and return segments [{start, end, text, words: [[text, t0, t1], ...]}]."""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable


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


def prompt_args(prompt: str | None) -> list[str]:
    """whisper-cli `--prompt` (initial prompt: names / jargon to spell right). Empty or blank = no flag. The text is one argv item."""
    prompt = (prompt or "").strip()
    return ["--prompt", prompt] if prompt else []


def run_cli(cmd: list[str], verbose: bool = False, on_line: Callable[[str], None] | None = None,
            tick: Callable[[], None] | None = None) -> None:
    """Run whisper-cli and raise RuntimeError with the end of its output when it fails.

    With on_line (called for every line it prints) or tick (called twice a second while it runs) the output is
    read as it comes, which is what progress reporting needs; without them it is one plain subprocess.run."""
    if on_line is None and tick is None:
        p = subprocess.run(cmd, capture_output=not verbose, text=True, errors="replace")
        if p.returncode:
            raise RuntimeError(f"whisper-cli failed ({p.returncode}):\n{(p.stderr or '')[-2000:]}")
        return
    tail: collections.deque = collections.deque(maxlen=80)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    stop = threading.Event()

    def ticker():
        while not stop.wait(0.5):
            tick()
    t = threading.Thread(target=ticker, daemon=True) if tick else None
    if t:
        t.start()
    try:
        for line in p.stdout:
            tail.append(line)
            if verbose:
                sys.stderr.write(line)   # never stdout: it is the MCP channel
            if on_line:
                on_line(line)
        code = p.wait()
    except BaseException:
        p.kill()
        raise
    finally:
        stop.set()
        if t:
            t.join()
    if tick:
        tick()
    if code:
        raise RuntimeError(f"whisper-cli failed ({code}):\n{''.join(tail)[-2000:]}")


def run(binary: Path, model: Path, media: Path, lang: str = "auto", device: int = 0, beam: int | None = None,
        threads: int | None = None, extra: list[str] | None = None, verbose: bool = False,
        prompt: str | None = None, translate: bool = False,
        progress: Callable[[float], None] | None = None) -> list[dict]:
    """progress, when given, is called with 0-100 as whisper-cli works through the file (its -pp output)."""
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "in.wav"
        to_wav16k(media, wav)
        out = Path(d) / "out"
        # -mc 0: never feed previous text back as a prompt — stops the repeat-loop hallucination on long files.
        # whisper.cpp ignores --prompt while -mc is 0, so with a prompt the context limit is left at its default.
        pa = prompt_args(prompt)
        cmd = [str(binary), "-m", str(model), "-f", str(wav), "-l", lang, "-ojf", "-of", str(out), *([] if pa else ["-mc", "0"]),
               "-dev", str(device), *pa]
        if translate:   # whisper's translate-to-English task
            cmd += ["-tr"]
        if beam:
            cmd += ["-bs", str(beam)]
        if threads:
            cmd += ["-t", str(threads)]
        cmd += extra or []
        if progress:
            cmd += ["-pp"]

            def on_line(line: str) -> None:
                m = re.search(r"progress = *(\d+)%", line)
                if m:
                    progress(float(m.group(1)))
            run_cli(cmd, verbose, on_line=on_line)
        else:
            run_cli(cmd, verbose)
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
    m = re.search(r"auto-detected language: (\w+)", p.stdout + p.stderr)
    return m.group(1) if m else "auto"
