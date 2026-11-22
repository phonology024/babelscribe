"""babelscribe as an MCP server: any MCP client (Claude Desktop / Code, Codex, Antigravity, Gemini CLI, Cursor,
VS Code, ...) can transcribe local audio/video on the user's own GPU.

  babelscribe mcp            # stdio server; AI apps launch it themselves (see README "Use it from an AI app")

Needs Python 3.10+ (the mcp SDK)."""

import io
import os
import sys
import time
from pathlib import Path

from .api import MEDIA   # one list of media extensions for the CLI and the server

HEARTBEAT = 5        # seconds between progress notifications while a file is being transcribed
TEXT_LIMIT = 30000   # characters of transcript returned to the model; the full text is always in the files


def _guard_stdout():
    """stdout is the JSON-RPC channel. Keep a private handle to it for the protocol and point everything else
    (print, logging, stray library output) at stderr so it can never corrupt a message."""
    proto = io.TextIOWrapper(os.fdopen(os.dup(sys.stdout.fileno()), "wb"), encoding="utf-8", newline="\n",
                             write_through=True)
    sys.stdout = sys.stderr
    return proto


async def _report_progress(ctx, progress, total, message) -> None:
    """Send an MCP progress notification when a client request is in flight.

    ctx.report_progress needs the request context; calling a tool directly (tests, scripts) has none and
    raises ValueError, which must not abort the transcription itself.
    No `float | None` annotations here: this is module level, and the module must still import on Python 3.9
    so that `babelscribe mcp` can reach its "needs Python 3.10+" message."""
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress, total, message)
    except ValueError:   # no request context: nothing to notify
        pass


def _tool_error(e: BaseException):
    """The CLI reports problems (no prebuilt binary for this platform, unknown model, bad format) by raising
    SystemExit. Inside the server that must come back as a tool error the client can read, never as the server
    process going away. ToolError because the SDK only forwards the text of a ToolError; any other exception
    reaches the client as a bare "Error executing tool", so "no such file" and "whisper-cli failed" must be
    wrapped as well or the assistant cannot tell the user what went wrong."""
    from mcp.server.mcpserver.exceptions import ToolError
    text = str(e) or "babelscribe stopped without a message"
    plain = isinstance(e, (SystemExit, FileNotFoundError, ValueError, RuntimeError))
    return ToolError(text if plain else f"{type(e).__name__}: {text}")


def _remote_llm_allowed() -> bool:
    """An assistant must not be able to send the user's transcript to another machine by passing a URL: only the
    person who configures the server can allow that, with BABELSCRIBE_LLM_ALLOW_REMOTE=1 in its environment."""
    return os.environ.get("BABELSCRIBE_LLM_ALLOW_REMOTE", "").strip().lower() in ("1", "true", "yes")


def _no_exit(fn):
    try:
        return fn()
    except (Exception, SystemExit) as e:
        raise _tool_error(e) from None


def build():
    import anyio
    from mcp.server.mcpserver import Context, MCPServer
    from mcp.types import ToolAnnotations

    from . import __version__, api, backend, models

    srv = MCPServer("babelscribe", version=__version__, instructions=(
        "Local speech-to-text on the user's own GPU (AMD/NVIDIA/Intel/Apple) for 99 languages. Needs a file path on "
        "this computer: if the user only names or describes a file, call find_media first. Subtitles (.srt) and text "
        "(.txt) are written next to the media file unless output_dir is given, plus a .json with the word timings: "
        "to fix names or change the line width afterwards, edit the text in that .json and call convert_subtitles "
        "instead of transcribing again. burn_subtitles draws the subtitles onto a copy of a video (for TikTok, Reels, "
        "Shorts). Use accurate=true when the user wants "
        "the fewest mistakes (slower); it is much better for Thai and Hindi. The first run downloads the model "
        "(~1.6 GB), so it can take a few minutes. After transcribing you can proofread names, translate, or "
        "summarise from the returned text."))

    async def _run(ctx, job, progress=None, total=None, prefix=""):
        """Run job(log, pct) in a worker thread, sending a progress notification every 5 s so clients do not time
        out on a long file. job passes pct to transcribe_file(progress=...), so each notification carries how
        far the file really is: 0-100 of 100 for one file, or files done + the fraction of the current one out
        of total for a folder. Returns the job's result. A failure (including SystemExit, see _tool_error) is
        returned as a value, not raised: raised inside the task group it would arrive wrapped in an
        ExceptionGroup and the caller would see "unhandled errors in a TaskGroup" instead of the message."""
        lines: list[str] = []
        done = anyio.Event()
        t0 = time.time()
        at = [0.0]   # percent of the current file, written by the worker thread

        def work():
            try:
                return job(lambda m: (lines.append(m), print(m)), lambda pct: at.__setitem__(0, pct))
            except (Exception, SystemExit) as e:
                return e

        async def heartbeat():
            while not done.is_set():
                with anyio.move_on_after(HEARTBEAT):
                    await done.wait()
                if not done.is_set():
                    note = f"{at[0]:.0f}% after {time.time() - t0:.0f} s"
                    await _report_progress(ctx, at[0] if progress is None else progress + at[0] / 100,
                                           100 if progress is None else total,
                                           f"{prefix}{note} · " + (lines[-1] if lines else "starting ..."))

        async with anyio.create_task_group() as tg:
            tg.start_soon(heartbeat)
            try:
                return await anyio.to_thread.run_sync(work)
            finally:
                done.set()

    # transcribe writes new .srt/.txt files (re-running rewrites its own output); first use downloads whisper-cli and the model
    @srv.tool(title="Transcribe audio/video to subtitles", annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
    async def transcribe(file_path: str, language: str = "auto", accurate: bool = False, formats: str = "srt,txt,json",
                         output_dir: str = "", vocabulary: str = "",
                         translate: bool = False, translate_to: str = "", ctx: Context | None = None) -> dict:
        """Transcribe a local audio or video file into subtitles / text.

        file_path: absolute path to the media file (mp4, mkv, mov, mp3, wav, m4a, ...).
        language: ISO code such as en, th, ja, es, hi — or "auto" to detect.
        accurate: slower, fewest errors (large-v3 with beam search, or the best fine-tune for Thai / Hindi).
        formats: comma list from srt, vtt, txt, json, ass (ass = karaoke word highlight). Keep json: it is what
            convert_subtitles reads to re-wrap or re-export later without transcribing again.
        output_dir: folder for the output files; empty = next to the media file.
        vocabulary: names and terms to spell correctly, e.g. "Pitakpong, babelscribe" (whisper initial prompt); empty = none.
        translate: true = write the transcript translated to English (uses large-v3; slower than turbo).
        translate_to: a language code (th, ja, es, ...) = also write NAME.<code>.srt, translated by the LLM running
            on the user's computer (Ollama, LM Studio, llama-server). Empty = no translation. Without a local LLM
            the transcription is still returned, with a note; you can then translate the text yourself.
        Returns the files written, detected language, device used, and the transcript text."""
        src = Path(file_path).expanduser()
        out = Path(output_dir).expanduser() / src.stem if output_dir else None
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
        fmts = [f.strip() for f in formats.split(",") if f.strip()]
        if translate_to and "json" not in fmts:
            fmts.append("json")
        result = await _run(ctx, lambda log, pct: api.transcribe_file(
            src, language, accurate=accurate, formats=fmts, out=out, log=log, prompt=vocabulary, translate=translate,
            progress=pct))
        if translate_to and not isinstance(result, BaseException):
            from . import llm_translate
            saved = next(f for f in result["files"] if f.endswith(".json"))
            more = await _run(ctx, lambda log, pct: llm_translate.translate_file(
                saved, translate_to, formats=[f for f in fmts if f != "json"] or ["srt"],
                allow_remote=_remote_llm_allowed(), log=log, progress=pct))
            if isinstance(more, BaseException):
                result["translation_note"] = f"not translated: {more}"
            else:
                result["files"] += more["files"]
                result["translated"] = {"lang": more["lang"], "model": more["model"], "files": more["files"]}
        if not isinstance(result, BaseException):
            await _report_progress(ctx, 100, 100, "done")
        if isinstance(result, BaseException):
            raise _tool_error(result) from None
        text = result.pop("text", "")
        result["text"] = text[:TEXT_LIMIT]
        if len(text) > TEXT_LIMIT:
            result["note"] = f"transcript truncated to {TEXT_LIMIT} characters; the full text is in the files listed"
        return result

    # Whole-folder batch: "subtitle everything in this folder" in one request. One file failing must not
    # abort the rest, so failures are collected per file and reported alongside the successes.
    @srv.tool(title="Transcribe every audio/video in a folder", annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
    async def transcribe_folder(folder: str, language: str = "auto", accurate: bool = False,
                                formats: str = "srt,txt,json", output_dir: str = "", vocabulary: str = "",
                                translate: bool = False, recursive: bool = False,
                                ctx: Context | None = None) -> dict:
        """Transcribe every audio and video file in a folder, one at a time.

        folder: absolute path to the folder holding the media files.
        language: ISO code such as en, th, ja, es, hi — or "auto" to detect each file separately.
        accurate: slower, fewest errors (large-v3 with beam search, or the best fine-tune for Thai / Hindi).
        formats: comma list from srt, vtt, txt, json, ass (ass = karaoke word highlight).
        output_dir: folder for the output files (sub-folders are kept); empty = next to each media file.
        vocabulary: names and terms to spell correctly, e.g. "Pitakpong, babelscribe"; empty = none.
        translate: true = write every transcript translated to English (uses large-v3; much slower).
        recursive: true = also transcribe media in sub-folders.
        Returns the counts plus one entry per file (path, files written, language, seconds) — a failure is
        reported in its own entry and the batch continues with the next file. Two files that would write the
        same subtitle name (talk.mp4 and talk.mp3) keep their full name: talk.mp4.srt, talk.mp3.srt."""
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise _tool_error(ValueError(f"not a folder: {root}"))
        pairs = api.collect_media([root], recursive)
        media = [p for p, _ in pairs]
        bases = api.output_bases(pairs, output_dir or None)
        fmts = [f.strip() for f in formats.split(",") if f.strip()]

        results: list[dict] = []
        with api.shared_setup():   # find the binary, model and devices once for the whole folder
            for i, src in enumerate(media, 1):
                tag = f"{src.name} ({i}/{len(media)})"
                await _report_progress(ctx, i - 1, len(media), f"transcribing {tag}")
                r = await _run(ctx, lambda log, pct: api.transcribe_file(
                    src, language, accurate=accurate, formats=fmts, out=bases[src], log=log, prompt=vocabulary,
                    translate=translate, progress=pct), progress=i - 1, total=len(media), prefix=f"{tag}: ")
                if isinstance(r, BaseException):   # keep going: one bad file must not lose the rest of the batch.
                    # SystemExit counts too: a bad format or unknown model is how the CLI paths report a problem.
                    results.append({"path": str(src), "ok": False, "error": f"{type(r).__name__}: {r}"})
                    continue
                results.append({"path": str(src), "ok": True, "files": r["files"], "language": r["lang"],
                                "segments": r["segments"], "seconds": r["seconds"]})
        await _report_progress(ctx, len(media), len(media), f"{len(media)} file(s) done")

        ok = [r for r in results if r["ok"]]
        return {"folder": str(root), "total": len(media), "succeeded": len(ok),
                "failed": len(results) - len(ok), "files": results}

    @srv.tool(title="Re-export subtitles from a transcript JSON", annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def convert_subtitles(json_path: str, formats: str = "srt", max_line_chars: int = 0, output_dir: str = "") -> dict:
        """Write subtitle files again from a babelscribe .json, without transcribing again (instant, no GPU).

        Use it to change the line width or add a format, or after correcting names and words: edit the "text"
        of the segments in the JSON, then call this, and every format gets the corrected text with its timing.
        json_path: absolute path to the .json written by transcribe (formats must have included json).
        formats: comma list from srt, vtt, txt, json, ass.
        max_line_chars: maximum characters per subtitle line; 0 = the default for the language.
        output_dir: folder for the output files; empty = next to the JSON.
        Returns the files written, the number of segments, and how many had edited text."""
        from . import convert
        src = Path(json_path).expanduser()
        out = Path(output_dir).expanduser() / src.with_suffix("").name if output_dir else None
        return _no_exit(lambda: convert.convert_file(
            src, [f.strip() for f in formats.split(",") if f.strip()], out=out, max_line_chars=max_line_chars or None))

    # translate_subtitles writes new NAME.<lang>.* files; the text goes to an LLM on this computer only (see below)
    @srv.tool(title="Translate subtitles with a local LLM", annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
    async def translate_subtitles(path: str, target: str, formats: str = "srt", llm_url: str = "", model: str = "",
                                  ctx: Context | None = None) -> dict:
        """Translate finished subtitles into another language with the LLM running on the user's own computer
        (Ollama, LM Studio, llama-server, ...). Timing is kept; the original file is not changed.

        path: absolute path to the .json written by transcribe (best), or an .srt / .vtt.
        target: language code or name: th, ja, es, de, "Thai", ...
        formats: comma list from srt, vtt, txt, json, ass for the translated files (NAME.<code>.srt, ...).
        llm_url: OpenAI-compatible endpoint, e.g. http://127.0.0.1:11434/v1; empty = the usual local ports.
        model: model name to ask for; empty = the first one the endpoint lists.
        Returns the files written, the number of subtitles, the language code, and the model used. If no local
        LLM is running, the error says how to start one; you can also translate the text yourself instead."""
        from . import llm_translate
        result = await _run(ctx, lambda log, pct: llm_translate.translate_file(
            path, target, llm_url or None, model or None, [f.strip() for f in formats.split(",") if f.strip()],
            allow_remote=_remote_llm_allowed(), log=log, progress=pct))
        if isinstance(result, BaseException):
            raise _tool_error(result) from None
        await _report_progress(ctx, 100, 100, "done")
        return result

    # burn_subtitles writes one new video file next to the input (or at output_path); the input is only read
    @srv.tool(title="Burn subtitles into a video", annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    async def burn_subtitles(video_path: str, subtitle_path: str = "", style: str = "plain", output_path: str = "",
                             ctx: Context | None = None) -> dict:
        """Draw subtitles onto a copy of a video (NAME.subbed.mp4), for posting where a separate subtitle file
        is not possible (TikTok, Reels, Shorts). The input video is never changed; audio is copied.

        video_path: absolute path to the video.
        subtitle_path: the .json written by transcribe (best: any style works, and text edited in it is used),
            or an .ass (drawn exactly as written), or an .srt / .vtt (plain only). Empty = the subtitle file
            next to the video; transcribe the video first if there is none.
        style: plain (white text at the bottom) | karaoke (each word lights up as it is spoken) | shorts (big,
            two or three words at a time, placed for vertical video).
        output_path: the video to write; empty = NAME.subbed.mp4 next to the input.
        Returns the file written, the style, the subtitle file used, the encoder and the picture size."""
        from . import burn
        result = await _run(ctx, lambda log, pct: burn.burn_file(
            video_path, subtitle_path or None, style, output_path or None, log=log, progress=pct))
        if isinstance(result, BaseException):
            raise _tool_error(result) from None
        await _report_progress(ctx, 100, 100, "done")
        return result

    @srv.tool(title="Find audio/video files", annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def find_media(name_contains: str = "", folder: str = "", limit: int = 15) -> list[dict]:
        """Find audio/video files on this computer, newest first. Searches Downloads, Videos, Desktop, Music and
        Documents (two levels deep) unless folder is given. Use it when the user names a file without a full path."""
        home = Path.home()
        roots = [Path(folder).expanduser()] if folder else [home / d for d in ("Downloads", "Videos", "Desktop", "Music", "Documents", "Movies")]
        hits = []
        for r in roots:
            if not r.is_dir():
                continue
            for p in [*r.glob("*"), *r.glob("*/*"), *(r.glob("*/*/*") if folder else [])]:
                if p.suffix.lower() in MEDIA and name_contains.lower() in p.name.lower():
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    hits.append((st.st_mtime, p, st.st_size))
        hits.sort(reverse=True)
        return [{"path": str(p), "size_mb": round(sz / 1e6, 1), "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(t))}
                for t, p, sz in hits[:limit]]

    @srv.tool(title="List GPUs", annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
    def list_devices() -> dict:
        """GPUs whisper.cpp can use on this computer and which one babelscribe picks automatically."""
        _, _, found = _no_exit(api.setup)
        return {"devices": found, "auto_pick": backend.pick_device(found)}

    @srv.tool(title="List languages and models", annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def list_languages_and_models() -> dict:
        """Models available, and which model --accurate uses per language."""
        return {"general": models.GENERAL, "fine_tunes": {k: v["note"] for k, v in models.FINETUNES.items()},
                "accurate_per_language": {**models.ACCURATE, "*": "large-v3 beam 5"}}

    return srv


def main() -> None:
    try:
        import anyio
        from mcp.server.stdio import stdio_server
    except ImportError:
        raise SystemExit('the MCP server needs Python 3.10+ (the mcp SDK)')
    proto = _guard_stdout()
    srv = build()

    async def run():
        async with stdio_server(stdout=anyio.wrap_file(proto)) as (r, w):
            low = srv._lowlevel_server
            await low.run(r, w, low.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()
