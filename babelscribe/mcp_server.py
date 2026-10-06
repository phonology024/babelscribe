"""babelscribe as an MCP server: any MCP client (Claude Desktop / Code, Codex, Antigravity, Gemini CLI, Cursor,
VS Code, ...) can transcribe local audio/video on the user's own GPU.

  babelscribe-mcp            # stdio server; clients launch it themselves (see README "Use from an AI app")

Needs: pip install "babelscribe[mcp]" (Python 3.10+)."""

import io
import os
import sys
import time
from pathlib import Path

MEDIA = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
TEXT_LIMIT = 30000   # characters of transcript returned to the model; the full text is always in the files


def _guard_stdout():
    """stdout is the JSON-RPC channel. Keep a private handle to it for the protocol and point everything else
    (print, logging, stray library output) at stderr so it can never corrupt a message."""
    proto = io.TextIOWrapper(os.fdopen(os.dup(sys.stdout.fileno()), "wb"), encoding="utf-8", newline="\n",
                             write_through=True)
    sys.stdout = sys.stderr
    return proto


def build():
    import anyio
    from mcp.server.mcpserver import Context, MCPServer

    from . import __version__, api, backend, models

    srv = MCPServer("babelscribe", version=__version__, instructions=(
        "Local speech-to-text on the user's own GPU (AMD/NVIDIA/Intel/Apple) for 99 languages. Needs a file path on "
        "this computer: if the user only names or describes a file, call find_media first. Subtitles (.srt) and text "
        "(.txt) are written next to the media file unless output_dir is given. Use accurate=true when the user wants "
        "the fewest mistakes (slower); it is much better for Thai and Hindi. The first run downloads the model "
        "(~1.6 GB), so it can take a few minutes. After transcribing you can proofread names, translate, or "
        "summarise from the returned text."))

    @srv.tool()
    async def transcribe(file_path: str, language: str = "auto", accurate: bool = False, formats: str = "srt,txt",
                         output_dir: str = "", ctx: Context | None = None) -> dict:
        """Transcribe a local audio or video file into subtitles / text.

        file_path: absolute path to the media file (mp4, mkv, mov, mp3, wav, m4a, ...).
        language: ISO code such as en, th, ja, es, hi — or "auto" to detect.
        accurate: slower, fewest errors (large-v3 with beam search, or the best fine-tune for Thai / Hindi).
        formats: comma list from srt, vtt, txt, json.
        output_dir: folder for the output files; empty = next to the media file.
        Returns the files written, detected language, device used, and the transcript text."""
        src = Path(file_path).expanduser()
        out = Path(output_dir).expanduser() / src.stem if output_dir else None
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
        fmts = [f.strip() for f in formats.split(",") if f.strip()]
        lines: list[str] = []
        done = anyio.Event()

        async def heartbeat():   # progress keeps clients from timing out on long files
            t0 = time.time()
            while not done.is_set():
                with anyio.move_on_after(5):
                    await done.wait()
                if ctx and not done.is_set():
                    await ctx.report_progress(time.time() - t0, None, lines[-1] if lines else "starting ...")

        result: dict = {}
        async with anyio.create_task_group() as tg:
            tg.start_soon(heartbeat)
            try:
                result = await anyio.to_thread.run_sync(lambda: api.transcribe_file(
                    src, language, accurate=accurate, formats=fmts, out=out, log=lambda m: (lines.append(m), print(m))))
            finally:
                done.set()
        text = result.pop("text", "")
        result["text"] = text[:TEXT_LIMIT]
        if len(text) > TEXT_LIMIT:
            result["note"] = f"transcript truncated to {TEXT_LIMIT} characters; the full text is in the files listed"
        return result

    @srv.tool()
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

    @srv.tool()
    def list_devices() -> dict:
        """GPUs whisper.cpp can use on this computer and which one babelscribe picks automatically."""
        _, _, found = api.setup()
        return {"devices": found, "auto_pick": backend.pick_device(found)}

    @srv.tool()
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
        raise SystemExit('the MCP server needs: pip install "babelscribe[mcp]"  (Python 3.10+)')
    proto = _guard_stdout()
    srv = build()

    async def run():
        async with stdio_server(stdout=anyio.wrap_file(proto)) as (r, w):
            low = srv._lowlevel_server
            await low.run(r, w, low.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()
