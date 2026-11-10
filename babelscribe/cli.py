"""babelscribe — transcribe any audio/video, in any language Whisper knows, on any GPU (AMD / NVIDIA / Intel via
Vulkan, NVIDIA via CUDA, Apple via Metal) or the CPU.

  babelscribe talk.mp4                         # auto language, turbo model, best GPU -> talk.srt + talk.json
  babelscribe a.mp4 b.mp3 ./recordings         # several files and folders in one run (-r for sub-folders)
  babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: Thai fine-tune text + turbo timing
  babelscribe talk.mp4 --accurate              # slower, fewest errors: large-v3 + beam search, or the best fine-tune
  babelscribe talk.mp4 --prompt "Pitakpong, babelscribe"   # bias spelling of names and terms
  babelscribe mcp                              # MCP server for AI apps (Claude, Codex, Gemini CLI, ...)
  babelscribe convert talk.json -f srt,ass --max-line-chars 20   # re-wrap / re-export from the JSON, no transcription
  babelscribe devices                          # list GPUs whisper.cpp can use
  babelscribe models                           # list models and fine-tunes"""
from __future__ import annotations

import argparse
import sys

from . import __version__, api, backend, doctor, models


def progress_bar(stream=None, width: int = 30):
    """A callback for transcribe_file(progress=...) that draws one self-updating line: [#####-----]  42%.

    It is drawn on stderr, so stdout stays clean for pipes, and wiped when the file reaches 100."""
    stream = stream or sys.stderr
    last = [-1]

    def draw(pct: float) -> None:
        n = int(pct)
        if n == last[0]:
            return
        last[0] = n
        if n >= 100:
            stream.write("\r" + " " * (width + 9) + "\r")
            last[0] = -1          # the next file of a batch starts a fresh bar
        else:
            done = width * n // 100
            stream.write(f"\r  [{'#' * done}{'-' * (width - done)}] {n:3d}%")
        stream.flush()
    return draw


def convert_main(argv: list[str]) -> None:
    """babelscribe convert talk.json -f srt,ass --max-line-chars 20"""
    from . import convert
    ap = argparse.ArgumentParser(
        prog="babelscribe convert",
        description="Write subtitles again from a saved babelscribe JSON (made with -f json): another format, "
                    "another line width, or after you corrected the text in the JSON. No model, no GPU; instant.")
    ap.add_argument("json", nargs="+", help="babelscribe .json file(s)")
    ap.add_argument("-f", "--formats", default="srt", help="comma list: srt,vtt,txt,json,ass (default: srt)")
    ap.add_argument("-o", "--out", help="output base path (default: next to the JSON; one input only)")
    ap.add_argument("--max-line-chars", type=int, help="maximum characters per subtitle line")
    ap.add_argument("--max-lines", type=int, default=2, help="lines per subtitle (default: 2)")
    ap.add_argument("--max-cps", type=float, help="reading speed: keep a fast subtitle up longer (e.g. 17)")
    ap.add_argument("--min-duration", type=float, help="seconds a subtitle stays up at least (e.g. 1.0)")
    ap.add_argument("--max-duration", type=float, help="seconds a subtitle stays up at most; longer ones are cut (e.g. 7)")
    a = ap.parse_args(argv)
    if a.out and len(a.json) > 1:
        raise SystemExit("-o names one output; convert one JSON at a time with it")
    for path in a.json:
        try:
            r = convert.convert_file(
                path, [f.strip() for f in a.formats.split(",") if f.strip()], out=a.out,
                max_line_chars=a.max_line_chars, max_lines=a.max_lines, max_cps=a.max_cps,
                min_duration=a.min_duration, max_duration=a.max_duration)
        except (FileNotFoundError, ValueError) as e:
            raise SystemExit(str(e))
        edited = f" ({r['retimed']} with edited text)" if r["retimed"] else ""
        print(f"{r['segments']} segments{edited} -> " + ", ".join(r["files"]))


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["doctor"]:
        doctor.main()
        return
    if argv[:1] == ["mcp"]:                          # MCP server for AI apps (stdio)
        from .mcp_server import main as serve
        return serve()
    if argv[:1] == ["convert"]:
        return convert_main(argv[1:])
    if argv[:1] == ["models"]:
        print("general (99 languages):"); [print(f"  {k:16} {v}") for k, v in models.GENERAL.items()]
        print("fine-tunes (text quality for one language, use with --text-model):")
        [print(f"  {k:16} [{v['lang']}] {v['note']}") for k, v in models.FINETUNES.items()]
        return
    ap = argparse.ArgumentParser(prog="babelscribe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="+", help="audio/video files and/or folders, or 'devices'")
    ap.add_argument("-r", "--recursive", action="store_true", help="also take media from sub-folders of a folder")
    ap.add_argument("--skip-existing", action="store_true",
                    help="with several files or a folder: leave files whose outputs already exist")
    ap.add_argument("-l", "--lang", default="auto", help="language code (th, en, ja, ...) or auto")
    ap.add_argument("-m", "--model", default="turbo", help="timing/general model (default turbo = large-v3-turbo)")
    ap.add_argument("--text-model", help="language fine-tune for the text (hybrid mode), e.g. thai-thonburian")
    ap.add_argument("--accurate", action="store_true",
                    help="slower but fewest errors: large-v3 with beam search, or the language's best fine-tune (hybrid)")
    ap.add_argument("--prompt", help='names and terms to spell correctly, e.g. --prompt "Pitakpong, babelscribe" (whisper initial prompt)')
    ap.add_argument("--translate", action="store_true", help="translate the speech to English (uses large-v3; not with --text-model)")
    ap.add_argument("-f", "--formats", default="srt,json", help="comma list: srt,vtt,txt,json,ass")
    ap.add_argument(
        "--max-line-chars",
        type=int,
        help="maximum characters per subtitle line (default: 42, smaller for CJK/Thai)",
    )
    ap.add_argument("-o", "--out", help="one file: output base path; several files or a folder: output folder "
                                        "(default: next to each input)")
    ap.add_argument("--device", default="auto", help="GPU id from `babelscribe devices`, or auto")
    ap.add_argument("--bin", help="path to a whisper-cli you built yourself")
    ap.add_argument("--flavor", help="prebuilt flavour to download: vulkan | cuda | metal | cpu")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--no-progress", action="store_true", help="never draw the progress bar")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)

    if a.input == ["devices"]:
        _, _, found = api.setup(a.model, a.bin, a.flavor)
        for d in found:
            print(f"  [{d['id']}] {d['backend']:6} {d['name']}  {d.get('detail', '')}")
        print(f"auto picks device {backend.pick_device(found)}"); return
    options = dict(
        lang=a.lang,
        model=a.model,
        text_model=a.text_model,
        accurate=a.accurate,
        device=a.device,
        bin=a.bin,
        flavor=a.flavor,
        verbose=a.verbose,
        max_line_chars=a.max_line_chars,
        prompt=a.prompt,
        translate=a.translate,
    )
    if sys.stderr.isatty() and not a.verbose and not a.no_progress:   # a bar only where a person is watching
        options["progress"] = progress_bar()
    formats = [f.strip() for f in a.formats.split(",") if f.strip()]
    from pathlib import Path
    try:
        if len(a.input) == 1 and not Path(a.input[0]).expanduser().is_dir():   # one file: -o is the output base path
            api.transcribe_file(src=a.input[0], formats=formats, out=a.out, **options)
            return
        done = api.transcribe_many(a.input, recursive=a.recursive, out_dir=a.out, skip_existing=a.skip_existing,
                                   formats=formats, **options)
    except FileNotFoundError as e:
        raise SystemExit(str(e))
    if not done["total"]:
        raise SystemExit("no audio or video files found" + ("" if a.recursive else " (use -r to look in sub-folders)"))
    print(f"{done['succeeded']} done, {done['skipped']} skipped, {done['failed']} failed")
    for r in done["files"]:
        if not r["ok"]:
            print(f"  failed: {r['path']}: {r['error']}")
    if done["failed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
