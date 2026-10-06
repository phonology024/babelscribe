"""Hybrid pass done safely: language fine-tunes without timestamps drop words at whisper's 30 s window seams.
So we cut the audio into short chunks (<= max_len s) at the timing model's segment boundaries (natural pauses),
transcribe every chunk with the text model in ONE whisper-cli run (model loaded once), and align each chunk's
accurate text to the timing segments inside that chunk."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from . import align
from .transcribe import to_wav16k


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
        verbose: bool = False, pad: float = .25) -> list[dict]:
    parts = chunks(time_segs)
    with tempfile.TemporaryDirectory() as d:
        wavs = []
        for i, (a, b, _) in enumerate(parts):
            w = Path(d) / f"c{i:04d}.wav"; to_wav16k(media, w, max(0.0, a - pad), b + pad, tail_silence=1.5); wavs.append(w)
        cmd = [str(binary), "-m", str(text_model), "-l", lang, "-oj", "-mc", "0", "-dev", str(device), "-np"]
        if beam:
            cmd += ["-bs", str(beam)]
        for w in wavs:
            cmd += ["-f", str(w)]
        p = subprocess.run(cmd, capture_output=not verbose, text=True, errors="replace")
        if p.returncode:
            raise RuntimeError(f"whisper-cli failed ({p.returncode}):\n{(p.stderr or '')[-2000:]}")
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
