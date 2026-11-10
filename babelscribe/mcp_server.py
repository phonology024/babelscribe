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


def _tool_error(e: SystemExit):
    """The CLI reports problems (no prebuilt binary for this platform, unknown model, bad format) by raising
    SystemExit. Inside the server that must come back as a tool error the client can read, never as the server
    process going away. ToolError because the SDK only forwards the text of a ToolError; any other exception
    reaches the client as a bare "Error executing tool"."""
    from mcp.server.mcpserver.exceptions import ToolError
    return ToolError(str(e) or "babelscribe stopped without a message")


def _no_exit(fn):
    try:
        return fn()
    except SystemExit as e:
        raise _tool_error(e) from None


def build():
    import anyio
    from mcp.server.mcpserver import Context, MCPServer
    from mcp.types import ToolAnnotations

    from . import __version__, api, backend, models

    srv = MCPServer("babelscribe", version=__version__, instructions=(
        "Local speech-to-text on the user's own GPU (AMD/NVIDIA/Intel/Apple) for 99 languages. Needs a file path on "
        "this computer: if the user only names or describes a file, call find_media first. Subtitles (.srt) and text "
        "(.txt) are written next to the media file unless output_dir is given. Use accurate=true when the user wants "
        "the fewest mistakes (slower); it is much better for Thai and Hindi. The first run downloads the model "
        "(~1.6 GB), so it can take a few minutes. After transcribing you can proofread names, translate, or "
        "summarise from the returned text."))

    async def _run(ctx, job, progress=None, total=None, prefix=""):
        """Run job(log) in a worker thread, sending a progress notification every 5 s so clients do not time out
        on a long file. Returns the job's result. A failure (including SystemExit, see _tool_error) is returned
        as a value, not raised: raised inside the task group it would arrive wrapped in an ExceptionGroup and the
        caller would see "unhandled errors in a TaskGroup" instead of the message."""
        lines: list[str] = []
        done = anyio.Event()
        t0 = time.time()

        def work():
            try:
                return job(lambda m: (lines.append(m), print(m)))
            except (Exception, SystemExit) as e:
                return e

        async def heartbeat():
            while not done.is_set():
                with anyio.move_on_after(HEARTBEAT):
                    await done.wait()
                if not done.is_set():
                    await _report_progress(ctx, time.time() - t0 if progress is None else progress, total,
                                           prefix + (lines[-1] if lines else "starting ..."))

        async with anyio.create_task_group() as tg:
            tg.start_soon(heartbeat)
            try:
                return await anyio.to_thread.run_sync(work)
            finally:
                done.set()

    # transcribe writes new .srt/.txt files (re-running rewrites its own output); first use downloads whisper-cli and the model
    @srv.tool(title="Transcribe audio/video to subtitles", annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
    async def transcribe(file_path: str, language: str = "auto", accurate: bool = False, formats: str = "srt,txt",
                         output_dir: str = "", vocabulary: str = "",
                         translate: bool = False, ctx: Context | None = None) -> dict:
        """Transcribe a local audio or video file into subtitles / text.

        file_path: absolute path to the media file (mp4, mkv, mov, mp3, wav, m4a, ...).
        language: ISO code such as en, th, ja, es, hi — or "auto" to detect.
        accurate: slower, fewest errors (large-v3 with beam search, or the best fine-tune for Thai / Hindi).
        formats: comma list from srt, vtt, txt, json, ass (ass = karaoke word highlight).
        output_dir: folder for the output files; empty = next to the media file.
        vocabulary: names and terms to spell correctly, e.g. "Pitakpong, babelscribe" (whisper initial prompt); empty = none.
        translate: true = write the transcript translated to English (uses large-v3; slower than turbo).
        Returns the files written, detected language, device used, and the transcript text."""
        src = Path(file_path).expanduser()
        out = Path(output_dir).expanduser() / src.stem if output_dir else None
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
        fmts = [f.strip() for f in formats.split(",") if f.strip()]
        result = await _run(ctx, lambda log: api.transcribe_file(
            src, language, accurate=accurate, formats=fmts, out=out, log=log, prompt=vocabulary, translate=translate))
        if isinstance(result, BaseException):
            raise _tool_error(result) if isinstance(result, SystemExit) else result
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
                                formats: str = "srt,txt", output_dir: str = "", vocabulary: str = "",
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
            raise ValueError(f"not a folder: {root}")
        pairs = api.collect_media([root], recursive)
        media = [p for p, _ in pairs]
        bases = api.output_bases(pairs, output_dir or None)
        fmts = [f.strip() for f in formats.split(",") if f.strip()]

        results: list[dict] = []
        with api.shared_setup():   # find the binary, model and devices once for the whole folder
            for i, src in enumerate(media, 1):
                tag = f"{src.name} ({i}/{len(media)})"
                await _report_progress(ctx, i - 1, len(media), f"transcribing {tag}")
                r = await _run(ctx, lambda log: api.transcribe_file(
                    src, language, accurate=accurate, formats=fmts, out=bases[src], log=log, prompt=vocabulary,
                    translate=translate), progress=i - 1, total=len(media), prefix=f"{tag}: ")
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
