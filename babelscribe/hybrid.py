"""Hybrid pass done safely: language fine-tunes without timestamps drop words at whisper's 30 s window seams.
So we cut the audio into short chunks (<= max_len s) at the timing model's segment boundaries (natural pauses),
transcribe every chunk with the text model in ONE whisper-cli run (model loaded once), and align each chunk's
accurate text to the timing segments inside that chunk."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Callable

from . import align, transcribe
from .transcribe import prompt_args, to_wav16k


def chunks(time_segs: list[dict], max_len: float = 24.0) -> list[tuple[float, float, list[dict]]]:
    out, cur = [], []
    for s in time_segs:
        if cur and s["end"] - cur[0]["start"] > max_len:
            out.append(cur); cur = []
        cur.append(s)
    if cur:
        out.append(cur)
    return [(c[0]["start"], c[-1]["end"], c) for c in out]


def run(binary: Path, text_model: Path, media: Path, time_segs: list[dict], lang: str, device: int, beam: int | None,
        verbose: bool = False, pad: float = .25, prompt: str | None = None,
        progress: Callable[[float], None] | None = None) -> list[dict]:
    """progress, when given, is called with 0-100: the share of chunks whisper-cli has finished."""
    parts = chunks(time_segs)
    with tempfile.TemporaryDirectory() as d:
        wavs = []
        for i, (a, b, _) in enumerate(parts):
            w = Path(d) / f"c{i:04d}.wav"; to_wav16k(media, w, max(0.0, a - pad), b + pad, tail_silence=1.5); wavs.append(w)
        pa = prompt_args(prompt)   # whisper.cpp ignores --prompt while -mc is 0 (chunks are single windows, so no context loop)
        cmd = [str(binary), "-m", str(text_model), "-l", lang, "-oj", *([] if pa else ["-mc", "0"]), "-dev", str(device), "-np", *pa]
        if beam:
            cmd += ["-bs", str(beam)]
        for w in wavs:
            cmd += ["-f", str(w)]
        if progress and wavs:   # -np silences whisper-cli here, so count the per-chunk JSON files it has written
            transcribe.run_cli(cmd, verbose, tick=lambda: progress(
                100.0 * sum(Path(str(w) + ".json").exists() for w in wavs) / len(wavs)))
        else:
            transcribe.run_cli(cmd, verbose)
        texts = []
        for w in wavs:
            j = json.loads(Path(str(w) + ".json").read_text(encoding="utf-8", errors="replace"))
            texts.append(" ".join(s["text"].strip() for s in j.get("transcription", [])))
    out = []
    for (a, b, segs), text in zip(parts, texts):
        if not text.strip():
            out.extend(segs); continue
        out.extend(align.hybrid([{"start": a, "end": b, "text": text, "words": []}], segs))
    return out
