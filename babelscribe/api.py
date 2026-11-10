"""One function the CLI and the MCP server share: media file in -> subtitle/transcript files out."""
from __future__ import annotations

import contextlib
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import __version__, backend, hybrid, models, transcribe, writers


MEDIA = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def collect_media(inputs: list[str | Path], recursive: bool = False) -> list[tuple[Path, Path]]:
    """Expand files and folders into [(media file, root)], sorted and without duplicates.

    A folder contributes every audio/video file in it (and in its sub-folders when recursive); root is that
    folder, so its sub-folders can be kept under an output folder. A file named directly is taken as is,
    whatever its extension, with its own folder as root."""
    seen: dict[Path, Path] = {}
    for item in inputs:
        p = Path(item).expanduser()
        if p.is_dir():
            found = p.rglob("*") if recursive else p.glob("*")
            for f in sorted(f for f in found if f.is_file() and f.suffix.lower() in MEDIA):
                seen.setdefault(f, p)
        elif p.is_file():
            seen.setdefault(p, p.parent)
        else:
            raise FileNotFoundError(f"no such file or folder: {p}")
    return list(seen.items())


def output_bases(media: list[tuple[Path, Path]], out_root: str | Path | None = None) -> dict[Path, Path]:
    """Where each file's subtitles go, as {media path: output path without extension}. Never two files on one path.

    Next to the media by default; under out_root with the same sub-folders when given, so b/talk.mp4 does not
    land on a/talk.mp4. talk.mp4 and talk.mp3 in one folder would both write talk.srt, so files whose base
    collides keep their full name instead: talk.mp4.srt and talk.mp3.srt."""
    out_root = Path(out_root).expanduser() if out_root else None

    def base(p: Path, root: Path, stem: str) -> Path:
        return (out_root / p.relative_to(root).parent if out_root else p.parent) / stem
    groups: dict[str, list[tuple[Path, Path]]] = {}
    for p, root in media:
        groups.setdefault(str(base(p, root, p.stem)).lower(), []).append((p, root))   # lower(): Windows and macOS ignore case
    return {p: base(p, root, p.stem if len(group) == 1 else p.name) for group in groups.values() for p, root in group}


def transcribe_many(
    inputs: list[str | Path],
    recursive: bool = False,
    out_dir: str | Path | None = None,
    skip_existing: bool = False,
    formats: list[str] | None = None,
    log: Callable[[str], None] = print,
    **options,
) -> dict:
    """Transcribe several files and/or folders, one file at a time. A file that fails is recorded and the rest
    still run. Returns {"total", "succeeded", "skipped", "failed", "files": [one entry per file]}.

    options are passed to transcribe_file (lang, model, accurate, prompt, device, ...)."""
    formats = formats or ["srt", "json"]
    media = collect_media(inputs, recursive)
    bases = output_bases(media, out_dir)
    results: list[dict] = []
    with shared_setup():
        for i, (src, _) in enumerate(media, 1):
            base = bases[src]
            if skip_existing and all((base.parent / f"{base.name}.{f}").exists() for f in formats):
                log(f"[{i}/{len(media)}] {src.name}: already done, skipped")
                results.append({"path": str(src), "ok": True, "skipped": True, "files": []})
                continue
            log(f"[{i}/{len(media)}] {src.name}")
            try:
                r = transcribe_file(src, formats=formats, out=base, log=log, **options)
            except (Exception, SystemExit) as e:   # SystemExit: how the CLI paths report a bad model or format
                why = f"{type(e).__name__}: {e}"
                if isinstance(e, subprocess.CalledProcessError):   # its str() is the whole command line
                    why = f"{Path(str(e.cmd[0])).stem} could not process this file (exit code {e.returncode})"
                log(f"  failed: {why}")
                results.append({"path": str(src), "ok": False, "error": why})
                continue
            results.append({"path": str(src), "ok": True, "skipped": False, "files": r["files"],
                            "language": r["lang"], "segments": r["segments"], "seconds": r["seconds"]})
    failed = sum(not r["ok"] for r in results)
    skipped = sum(bool(r.get("skipped")) for r in results)
    return {"total": len(media), "succeeded": len(results) - failed - skipped, "skipped": skipped,
            "failed": failed, "files": results}


def _quantizer(binary: Path) -> Path:
    return binary.parent / ("whisper-quantize.exe" if binary.suffix == ".exe" else "whisper-quantize")


def _device_id(device: str | int, found: list[dict]) -> int:
    """Turn a user-supplied device into an id whisper.cpp actually reported.

    `--device foo` used to escape as a bare ValueError from int(), and an id that is not in the list (5, -1)
    was passed straight to whisper-cli. Both now fail here, before the run, with the ids that do exist."""
    try:
        dev = int(device)
    except (TypeError, ValueError):
        raise ValueError(f"device must be 'auto' or a GPU id, not {device!r}") from None
    ids = [d["id"] for d in found]
    if dev not in ids:
        listed = ", ".join(f"{i} ({d['backend']} {d['name']})" for i, d in zip(ids, found)) or "none"
        raise ValueError(f"no device {dev}; available: {listed}")
    return dev


_shared: dict | None = None   # setup() results kept for the length of one batch, see shared_setup()


@contextlib.contextmanager
def shared_setup():
    """Inside this block setup() runs once per (model, bin, flavor) instead of once per file.

    Listing the devices loads the model, which costs seconds; a folder of 200 short clips should pay that once.
    Nothing is kept after the block, so a later call sees a binary or GPU that changed in between."""
    global _shared
    outer, _shared = _shared, ({} if _shared is None else _shared)
    try:
        yield
    finally:
        _shared = outer


def setup(model: str = "turbo", bin: str | None = None, flavor: str | None = None) -> tuple[Path, Path, list[dict]]:
    """Find (or download) whisper-cli and the model, and list the devices it can use."""
    key = (model, bin, flavor)
    if _shared is not None and key in _shared:
        return _shared[key]
    binary = backend.find_binary(bin, flavor)
    timing = models.ensure(model, _quantizer(binary))
    binary, found = backend.probe_or_refetch(binary, timing, flavor)
    if _shared is not None:
        _shared[key] = (binary, timing, found)
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
    progress: Callable[[float], None] | None = None,
) -> dict:
    """Transcribe one audio/video file. Returns a summary dict (files written, language, device, segments, text).

    progress, when given, is called with how far the file is, 0 to 100 (never going back), from whisper-cli's
    own progress output. With a text model the timing pass is the first 40 and the text pass the rest."""
    src = Path(src).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"no such file: {src}")
    base = Path(out).expanduser() if out else src.with_suffix("")
    # Before any download or inference: -o into a folder that does not exist used to fail at the very end with a
    # bare "[Errno 2] ... .srt", throwing away a transcription that may have taken minutes.
    base.parent.mkdir(parents=True, exist_ok=True)
    if translate:
        if text_model:
            raise ValueError("translate cannot be combined with a text model (fine-tunes write the source language)")
        if models.ALIASES.get(model, model) == "large-v3-turbo":   # turbo was not trained for translation
            model = "large-v3"
            log("translate: using large-v3 (turbo does not translate)")
    binary, timing, found = setup(model, bin, flavor)
    dev = backend.pick_device(found) if device in ("auto", None) else _device_id(device, found)
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
    more: dict = {}   # only passed when asked for, so callers and stand-ins that predate progress keep working
    reached = [0.0]

    def span(lo: float, hi: float) -> Callable[[float], None]:
        def report(pct: float) -> None:
            now = lo + (hi - lo) * min(max(pct, 0.0), 100.0) / 100
            if now > reached[0]:
                reached[0] = now
                progress(now)
        return report
    first = 40.0 if text_model else 100.0
    if progress:
        more["progress"] = span(0.0, first)
    segs = transcribe.run(binary, timing, src, lang, dev, beam=beam, verbose=verbose, prompt=prompt,
                          translate=translate, **more)
    meta = {"tool": f"babelscribe {__version__}", "model": model, "lang": lang, "device": f"{gpu['backend']} {gpu['name']}"}
    if translate:
        meta["translate"] = "en"
    if text_model:
        _, ft = models.resolve(text_model)
        tm = models.ensure(text_model, _quantizer(binary))
        log(f"text pass with {text_model} ...")
        if progress:
            more["progress"] = span(first, 100.0)
        segs = hybrid.run(binary, tm, src, segs, ft["lang"] if ft else lang, dev, (ft or {}).get("beam"), verbose,
                          prompt=prompt, **more)
        meta["text_model"] = text_model
    files = writers.write(
        segs,
        base,
        formats or ["srt", "json"],
        meta,
        max_line_chars=max_line_chars,
    )
    if progress:
        span(100.0, 100.0)(100.0)
    took = time.time() - t0
    log(f"{len(segs)} segments in {took:.1f}s -> " + ", ".join(str(f) for f in files))
    return {**meta, "files": [str(f) for f in files], "segments": len(segs), "seconds": round(took, 1),
            "text": "\n".join(s["text"].strip() for s in segs)}
