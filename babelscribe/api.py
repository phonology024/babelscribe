"""One function the CLI and the MCP server share: media file in -> subtitle/transcript files out."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from . import __version__, backend, hybrid, models, transcribe, writers


def _quantizer(binary: Path) -> Path:
    return binary.parent / ("whisper-quantize.exe" if binary.suffix == ".exe" else "whisper-quantize")


def setup(model: str = "turbo", bin: str | None = None, flavor: str | None = None) -> tuple[Path, Path, list[dict]]:
    """Find (or download) whisper-cli and the model, and list the devices it can use."""
    binary = backend.find_binary(bin, flavor)
    timing = models.ensure(model, _quantizer(binary))
    binary, found = backend.probe_or_refetch(binary, timing, flavor)
    return binary, timing, found


def transcribe_file(
    src: str | Path,
    lang: str = "auto",
    model: str = "turbo",
    text_model: str | None = None,
    accurate: bool = False,
    formats: list[str] | None = None,
    out: str | Path | None = None,
    device: str | int = "auto",
    bin: str | None = None,
    flavor: str | None = None,
    verbose: bool = False,
    log: Callable[[str], None] = print,
    max_line_chars: int | None = None,
    prompt: str | None = None,
    translate: bool = False,
) -> dict:
    """Transcribe one audio/video file. Returns a summary dict (files written, language, device, segments, text)."""
    src = Path(src).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"no such file: {src}")
    if translate:
        if text_model:
            raise ValueError("translate cannot be combined with a text model (fine-tunes write the source language)")
        if models.ALIASES.get(model, model) == "large-v3-turbo":   # turbo was not trained for translation
            model = "large-v3"
            log("translate: using large-v3 (turbo does not translate)")
    binary, timing, found = setup(model, bin, flavor)
    dev = backend.pick_device(found) if device == "auto" else int(device)
    gpu = next((d for d in found if d["id"] == dev), found[0])
    if lang == "auto":
        lang = transcribe.detected_language(binary, timing, src, dev)
        log(f"language: {lang}")
    beam = 5 if translate and accurate else None
    if accurate and not text_model and not translate:
        if lang in models.ACCURATE:
            text_model = models.ACCURATE[lang]          # fine-tune text + turbo timing
        elif model == "turbo":
            model, beam = "large-v3", 5
            timing = models.ensure(model, _quantizer(binary))
    t0 = time.time()
    log(f"transcribing with {model} on {gpu['backend']} {gpu['name']} ...")
    segs = transcribe.run(binary, timing, src, lang, dev, beam=beam, verbose=verbose, prompt=prompt, translate=translate)
    meta = {"tool": f"babelscribe {__version__}", "model": model, "lang": lang, "device": f"{gpu['backend']} {gpu['name']}"}
    if translate:
        meta["translate"] = "en"
    if text_model:
        _, ft = models.resolve(text_model)
        tm = models.ensure(text_model, _quantizer(binary))
        log(f"text pass with {text_model} ...")
        segs = hybrid.run(binary, tm, src, segs, ft["lang"] if ft else lang, dev, (ft or {}).get("beam"), verbose, prompt=prompt)
        meta["text_model"] = text_model
    base = Path(out).expanduser() if out else src.with_suffix("")
    files = writers.write(
        segs,
        base,
        formats or ["srt", "json"],
        meta,
        max_line_chars=max_line_chars,
    )
    took = time.time() - t0
    log(f"{len(segs)} segments in {took:.1f}s -> " + ", ".join(str(f) for f in files))
    return {**meta, "files": [str(f) for f in files], "segments": len(segs), "seconds": round(took, 1),
            "text": "\n".join(s["text"].strip() for s in segs)}
