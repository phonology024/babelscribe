"""babelscribe — transcribe any audio/video, in any language Whisper knows, on any GPU (AMD / NVIDIA / Intel via
Vulkan, NVIDIA via CUDA, Apple via Metal) or the CPU.

  babelscribe talk.mp4                         # auto language, turbo model, best GPU -> talk.srt + talk.json
  babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: Thai fine-tune text + turbo timing
  babelscribe talk.mp4 --accurate              # slower, fewest errors: large-v3 + beam search, or the best fine-tune
  babelscribe devices                          # list GPUs whisper.cpp can use
  babelscribe models                           # list models and fine-tunes"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__, backend, hybrid, models, transcribe, writers


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["models"]:
        print("general (99 languages):"); [print(f"  {k:16} {v}") for k, v in models.GENERAL.items()]
        print("fine-tunes (text quality for one language, use with --text-model):")
        [print(f"  {k:16} [{v['lang']}] {v['note']}") for k, v in models.FINETUNES.items()]
        return
    ap = argparse.ArgumentParser(prog="babelscribe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="audio or video file, or 'devices'")
    ap.add_argument("-l", "--lang", default="auto", help="language code (th, en, ja, ...) or auto")
    ap.add_argument("-m", "--model", default="turbo", help="timing/general model (default turbo = large-v3-turbo)")
    ap.add_argument("--text-model", help="language fine-tune for the text (hybrid mode), e.g. thai-thonburian")
    ap.add_argument("--accurate", action="store_true",
                    help="slower but fewest errors: large-v3 with beam search, or the language's best fine-tune (hybrid)")
    ap.add_argument("-f", "--formats", default="srt,json", help="comma list: srt,vtt,txt,json")
    ap.add_argument("-o", "--out", help="output base path (default: next to the input)")
    ap.add_argument("--device", default="auto", help="GPU id from `babelscribe devices`, or auto")
    ap.add_argument("--bin", help="path to a whisper-cli you built yourself")
    ap.add_argument("--flavor", help="prebuilt flavour to download: vulkan | cuda | metal | cpu")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)

    binary = backend.find_binary(a.bin, a.flavor)
    timing = models.ensure(a.model, binary.parent / ("whisper-quantize.exe" if binary.suffix == ".exe" else "whisper-quantize"))
    binary, found = backend.probe_or_refetch(binary, timing, a.flavor)
    if a.input == "devices":
        for d in found:
            print(f"  [{d['id']}] {d['backend']:6} {d['name']}  {d.get('detail', '')}")
        print(f"auto picks device {backend.pick_device(found)}"); return
    dev = backend.pick_device(found) if a.device == "auto" else int(a.device)
    gpu = next((d for d in found if d["id"] == dev), found[0])
    src = Path(a.input)
    if not src.exists():
        raise SystemExit(f"no such file: {src}")
    lang = a.lang
    if lang == "auto":
        lang = transcribe.detected_language(binary, timing, src, dev); print(f"language: {lang}")
    beam = None
    if a.accurate:
        if not a.text_model and lang in models.ACCURATE:
            a.text_model = models.ACCURATE[lang]          # fine-tune text + turbo timing
        elif not a.text_model and a.model == "turbo":
            a.model, beam = "large-v3", 5
            timing = models.ensure(a.model)
    t0 = time.time()
    print(f"transcribing with {a.model} on {gpu['backend']} {gpu['name']} ...")
    segs = transcribe.run(binary, timing, src, lang, dev, beam=beam, verbose=a.verbose)
    meta = {"tool": f"babelscribe {__version__}", "model": a.model, "lang": lang, "device": f"{gpu['backend']} {gpu['name']}"}
    if a.text_model:
        _, ft = models.resolve(a.text_model)
        tm = models.ensure(a.text_model, binary.parent / ("whisper-quantize.exe" if binary.suffix == ".exe" else "whisper-quantize"))
        print(f"text pass with {a.text_model} ...")
        segs = hybrid.run(binary, tm, src, segs, ft["lang"] if ft else lang, dev, (ft or {}).get("beam"), a.verbose)
        meta["text_model"] = a.text_model
    base = Path(a.out) if a.out else src.with_suffix("")
    files = writers.write(segs, base, [f.strip() for f in a.formats.split(",") if f.strip()], meta)
    print(f"{len(segs)} segments in {time.time() - t0:.1f}s -> " + ", ".join(str(f) for f in files))


if __name__ == "__main__":
    main()
