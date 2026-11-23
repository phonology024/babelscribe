"""babelscribe — transcribe any audio/video, in any language Whisper knows, on any GPU (AMD / NVIDIA / Intel via
Vulkan, NVIDIA via CUDA, Apple via Metal) or the CPU.

  babelscribe talk.mp4                         # auto language, turbo model, best GPU -> talk.srt + talk.json
  babelscribe a.mp4 b.mp3 ./recordings         # several files and folders in one run (-r for sub-folders)
  babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: Thai fine-tune text + turbo timing
  babelscribe talk.mp4 --accurate              # slower, fewest errors: large-v3 + beam search, or the best fine-tune
  babelscribe talk.mp4 --prompt "Pitakpong, babelscribe"   # bias spelling of names and terms
  babelscribe mcp                              # MCP server for AI apps (Claude, Codex, Gemini CLI, ...)
  babelscribe convert talk.json -f srt,ass --max-line-chars 20   # re-wrap / re-export from the JSON, no transcription
  babelscribe clip.mp4 --burn --style shorts   # also write clip.subbed.mp4: the video with the captions drawn on
  babelscribe burn clip.mp4 clip.ass           # draw an existing (edited) subtitle file onto the video
  babelscribe talk.mp4 --translate-to th       # also talk.th.srt, translated by a local LLM (Ollama, llama-server, ...)
  babelscribe translate talk.json --to ja      # translate a finished transcription (or an .srt), timing kept
  babelscribe connect add claude-desktop       # put babelscribe into an AI app's settings (status | show | add | remove)
  babelscribe devices                          # list GPUs whisper.cpp can use
  babelscribe models                           # list models and fine-tunes"""
from __future__ import annotations

import argparse
import json
import sys
import traceback

from . import __version__, api, backend, doctor, models, ram


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
    if argv[:1] == ["translate"]:
        from . import llm_translate
        return llm_translate.main(argv[1:])
    if argv[:1] == ["burn"]:
        from . import burn
        return burn.main(argv[1:])
    if argv[:1] == ["llms"]:                         # which local models can translate (for the desktop app)
        from . import llm_translate
        found = llm_translate.scan()
        if "--json" in argv[1:]:
            print(json.dumps(found, ensure_ascii=True))
        else:
            for f in found:
                print(f"  {f['kind']:14} {f['url']:32} " + (", ".join(f["models"][:3]) or "no model listed") if f["up"]
                      else f"  {f['kind']:14} {f['url']:32} not running")
        return
    if argv[:1] == ["connect"]:                      # put babelscribe into an AI app's settings (and take it out again)
        from . import connect
        return connect.main(argv[1:])
    if argv[:1] == ["models"]:
        # --exit-when-stdin-closes (which the desktop app adds to everything it runs) has nothing to stop here
        rest = [x for x in argv[1:] if x != "--exit-when-stdin-closes"]
        info = ram.detect()
        if rest == ["--json"]:                       # for programs: what fits this computer, and what to say if not
            print(json.dumps(ram.report(info), ensure_ascii=True))
            return
        print("general (99 languages), with the free memory a run needs:")
        [print(f"  {k:16} {v:>7}  needs ~{ram.need_mb(k) / 1024:.1f} GB") for k, v in models.GENERAL.items()]
        print("fine-tunes (text quality for one language, use with --text-model):")
        [print(f"  {k:18} [{v['lang']}] {v['note']}") for k, v in models.FINETUNES.items()]
        if info:
            print(f"this computer: {info['available_mb'] / 1024:.1f} GB free of {info['total_mb'] / 1024:.1f} GB; "
                  f"{ram.warning('turbo', info) or 'the default model (turbo) fits'}")
        return
    ap = argparse.ArgumentParser(prog="babelscribe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="+", help="audio/video files and/or folders, or 'devices'")
    ap.add_argument("-r", "--recursive", action="store_true", help="also take media from sub-folders of a folder")
    ap.add_argument("--skip-existing", action="store_true",
                    help="with several files or a folder: leave files whose outputs already exist")
    ap.add_argument("-l", "--lang", default="auto", help="language code (th, en, ja, ...) or auto")
    ap.add_argument("-m", "--model", help="timing/general model (default turbo = large-v3-turbo; with no -m on a computer "
                                          "with too little free memory for it, the largest model that fits is used instead)")
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
    ap.add_argument("--translate-to", metavar="LANG",
                    help="also write NAME.LANG.srt: the subtitles translated into any language (th, ja, es, ...) by a "
                         "local LLM; the timing is kept and the original files are not changed")
    from . import llm_translate
    llm_translate.add_llm_flags(ap)
    ap.add_argument("--burn", action="store_true",
                    help="also write NAME.subbed.mp4: the video with the subtitles drawn on it (the input is not changed)")
    ap.add_argument("--style", default="plain", choices=("plain", "karaoke", "shorts"),
                    help="look of --burn: plain | karaoke (each word lights up) | shorts (big, 2-3 words at a time, "
                         "for vertical video)")
    ap.add_argument("--burn-translated", action="store_true",
                    help="with --burn and --translate-to: draw the translated subtitles (NAME.LANG.subbed.mp4) instead of "
                         "the original ones")
    ap.add_argument("--font", help="font family for --burn (default: one that has the letters of the language)")
    ap.add_argument("-o", "--out", help="one file: output base path; several files or a folder: output folder "
                                        "(default: next to each input)")
    ap.add_argument("--device", default="auto", help="GPU id from `babelscribe devices`, or auto")
    ap.add_argument("--bin", help="path to a whisper-cli you built yourself")
    ap.add_argument("--flavor", help="prebuilt flavour to download: vulkan | cuda | metal | cpu")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--no-progress", action="store_true", help="never draw the progress bar")
    ap.add_argument("--progress-json", action="store_true",
                    help="for programs that run babelscribe (such as the desktop app): print one JSON object per "
                         "line on stdout (progress, log, done, error) and everything else on stderr")
    ap.add_argument("--exit-when-stdin-closes", action="store_true",
                    help="for a program that runs babelscribe and keeps its standard input open: when that program "
                         "ends, however it ends, stop whisper-cli and ffmpeg and exit instead of finishing the file")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)
    if a.exit_when_stdin_closes:
        from . import lifecycle
        lifecycle.start()
    if a.progress_json:
        return run_with_events(a)
    return _run(a)


def json_events(stream):
    """emit(event, **fields) for --progress-json: one JSON object per line, flushed at once (stdout is a pipe).

    ASCII-only JSON, so a reader on Windows never meets the ANSI code page of a piped stream."""
    def emit(event: str, **fields) -> None:
        stream.write(json.dumps({"event": event, **fields}) + "\n")
        stream.flush()
    return emit


def run_with_events(a: argparse.Namespace) -> None:
    """Run with --progress-json. Events on stdout:

      {"event": "log", "message": "..."}                       what the CLI would print
      {"event": "progress", "stage": "transcribe", "percent": 42.0}   0-100 per stage, never going back
      {"event": "done", "files": [...], "lang": "en", ...}      the transcribe_file summary (one file) or the
                                                                transcribe_many summary (several files)
      {"event": "error", "message": "..."}                     then exit code 1

    Anything else that is printed (downloads, whisper-cli with -v) goes to stderr, so stdout stays parseable."""
    emit = json_events(sys.stdout)
    saved, sys.stdout = sys.stdout, sys.stderr
    try:
        _run(a, emit)
    except SystemExit as e:
        if isinstance(e.code, str):
            emit("error", message=e.code)
            raise SystemExit(1) from None
        raise
    except Exception as e:
        traceback.print_exc()
        emit("error", message=f"{type(e).__name__}: {e}")
        raise SystemExit(1) from None
    finally:
        sys.stdout = saved


def _run(a: argparse.Namespace, emit=None) -> None:
    """The main command after its arguments are parsed. emit: see run_with_events."""
    from pathlib import Path

    from . import llm_translate

    def stage_progress(stage: str):
        last = [-1.0]

        def report(pct: float) -> None:
            pct = round(min(max(float(pct), 0.0), 100.0), 1)
            if pct > last[0]:
                last[0] = pct
                emit("progress", stage=stage, percent=pct)
        return report

    if a.input == ["devices"]:
        _, _, found = api.setup(a.model or "turbo", a.bin, a.flavor)
        for d in found:
            print(f"  [{d['id']}] {d['backend']:6} {d['name']}  {d.get('detail', '')}")
        print(f"auto picks device {backend.pick_device(found)}"); return
    options = dict(
        lang=a.lang,
        model=a.model or api.UNCHOSEN,
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
    if emit:
        options["log"] = lambda message: emit("log", message=str(message))
        options["progress"] = stage_progress("transcribe")
    elif sys.stderr.isatty() and not a.verbose and not a.no_progress:   # a bar only where a person is watching
        options["progress"] = progress_bar()
    formats = [f.strip() for f in a.formats.split(",") if f.strip()]
    if a.burn_translated and not (a.burn and a.translate_to):
        raise SystemExit("--burn-translated needs --burn and --translate-to (it draws the translated subtitles)")
    if a.burn:
        from . import burn
        if "json" not in formats:
            formats.append("json")       # the word timings: what the karaoke and shorts looks are drawn from

    if a.translate_to:
        if "json" not in formats:
            formats.append("json")       # the translation is made from the saved segments
        try:                             # no LLM, or one on another machine: say so before transcribing anything
            llm_translate.language(a.translate_to)
            llm_translate.find_endpoint(a.llm, a.allow_remote)
        except ValueError as e:
            raise SystemExit(str(e))

    def translate_one(files: list[str]) -> dict:
        saved = next(f for f in files if f.endswith(".json"))
        written = [f for f in formats if f != "json"] or ["srt"]
        if a.burn_translated and "srt" not in written:
            written.append("srt")        # what is drawn is the translated .srt
        return llm_translate.translate_file(
            saved, a.translate_to, a.llm, a.llm_model, written,
            allow_remote=a.allow_remote, max_line_chars=a.max_line_chars,
            progress=stage_progress("translate") if emit else None)

    def burn_one(src, files: list[str], translated: list[str] | None = None) -> dict:
        saved = next(f for f in files if f.endswith(".json"))
        what, name = saved, ".subbed.mp4"
        if a.burn_translated:            # the translated subtitles, in a video of their own: NAME.LANG.subbed.mp4
            what = next(f for f in translated or [] if f.endswith(".srt"))
            name = what[:-len(".srt")][len(saved) - len(".json"):] + ".subbed.mp4"
        return burn.burn_file(src, what, a.style, saved[:-len(".json")] + name, a.font,
                              progress=stage_progress("burn") if emit else options.get("progress"))

    try:
        if len(a.input) == 1 and not Path(a.input[0]).expanduser().is_dir():   # one file: -o is the output base path
            src = Path(a.input[0]).expanduser()
            if a.burn and src.is_file():
                burn.video_size(src, burn.burn_ffmpeg())   # an audio file has no picture: say so before transcribing it
            r = api.transcribe_file(src=a.input[0], formats=formats, out=a.out, **options)
            translated = translate_one(r["files"]) if a.translate_to else None
            burned = burn_one(src, r["files"], translated["files"] if translated else None) if a.burn else None
            if emit:
                more = (translated["files"] if translated else []) + ([burned["file"]] if burned else [])
                emit("done", **{**r, "files": r["files"] + more})
            return
        if a.burn:
            burn.burn_ffmpeg()
        done = api.transcribe_many(a.input, recursive=a.recursive, out_dir=a.out, skip_existing=a.skip_existing,
                                   formats=formats, **options)
        translated_of: dict[str, list[str]] = {}
        if a.translate_to:
            for r in done["files"]:
                if r["ok"] and not r.get("skipped"):
                    try:
                        translated_of[r["path"]] = translate_one(r["files"])["files"]
                        r["files"] += translated_of[r["path"]]
                    except (Exception, SystemExit) as e:
                        r.update(ok=False, error=f"subtitles written, but the translation failed: {e}")
                        done["succeeded"] -= 1
                        done["failed"] += 1
        if a.burn:                       # videos transcribed in this run; audio files have nothing to draw on
            for r in done["files"]:
                if r["ok"] and not r.get("skipped") and Path(r["path"]).suffix.lower() in burn.VIDEO:
                    try:
                        burn_one(r["path"], r["files"], translated_of.get(r["path"]))
                    except (Exception, SystemExit) as e:
                        r.update(ok=False, error=f"subtitles written, but burning them in failed: {e}")
                        done["succeeded"] -= 1
                        done["failed"] += 1
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        raise SystemExit(str(e))
    if not done["total"]:
        raise SystemExit("no audio or video files found" + ("" if a.recursive else " (use -r to look in sub-folders)"))
    if emit:
        emit("done", **done)
    print(f"{done['succeeded']} done, {done['skipped']} skipped, {done['failed']} failed")
    for r in done["files"]:
        if not r["ok"]:
            print(f"  failed: {r['path']}: {r['error']}")
    if done["failed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
