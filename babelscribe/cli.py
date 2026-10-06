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

from . import __version__, api, backend, models


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

    if a.input == "devices":
        _, _, found = api.setup(a.model, a.bin, a.flavor)
        for d in found:
            print(f"  [{d['id']}] {d['backend']:6} {d['name']}  {d.get('detail', '')}")
        print(f"auto picks device {backend.pick_device(found)}"); return
    try:
        api.transcribe_file(a.input, a.lang, a.model, a.text_model, a.accurate,
                            [f.strip() for f in a.formats.split(",") if f.strip()], a.out, a.device, a.bin, a.flavor, a.verbose)
    except FileNotFoundError as e:
        raise SystemExit(str(e))

if __name__ == "__main__":
    main()
