"""One talk with human captions as a test set for bench/hybrid_bench.py: DIR/talk.wav and DIR/refs.json.
usage: python bench/ted_clip.py DIR LANG VIDEO_URL     (needs yt-dlp and ffmpeg; the DIR name must start with LANG_)
The audio and captions are only read to measure accuracy, and are not redistributed (TED content is CC BY-NC-ND)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def vtt_text(path: Path) -> str:
    """The caption text without times and tags, a line that repeats the one before it counted once (as bench.py does)."""
    import re
    out, last = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "-->" in line or not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or line.strip().isdigit():
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if text and text != last:
            out.append(text)
            last = text
    return " ".join(out)


def main() -> None:
    folder, lang, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["yt-dlp", "--no-progress", "-x", "--audio-format", "wav",
                    "--postprocessor-args", "ExtractAudio:-ac 1 -ar 16000",
                    "--write-subs", "--sub-langs", lang, "--sub-format", "vtt", "-o", str(folder / "talk.%(ext)s"), url],
                   check=True)
    captions = folder / f"talk.{lang}.vtt"
    (folder / "refs.json").write_text(json.dumps({"talk": vtt_text(captions)}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
