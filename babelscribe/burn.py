"""Burn subtitles into the video: clip.mp4 + subtitles -> clip.subbed.mp4, with the captions drawn on the picture.

Three looks, all drawn by ffmpeg's libass from an ASS file sized for the actual video:
  plain    white text at the bottom, two lines
  karaoke  the same, each word lights up as it is spoken
  shorts   big, bold, two or three words at a time, placed above the app buttons of a vertical video

The input video is never changed. Audio is copied."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from . import align, convert, transcribe, writers

STYLES = ("plain", "karaoke", "shorts")
WHITE, AMBER, YELLOW = "&H00FFFFFF", "&H0000D7FF", "&H0000FFFF"   # ASS colours are &HAABBGGRR

# Fonts that have the letters of each script, most common first: Windows, macOS, then Linux (Noto and friends).
FONTS = {
    "thai": ["Leelawadee UI", "Tahoma", "Thonburi", "Noto Sans Thai", "Sarabun", "Loma", "Garuda"],
    "japanese": ["Yu Gothic", "Meiryo", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP", "IPAGothic"],
    "chinese": ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei"],
    "korean": ["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "NanumGothic"],
    "arabic": ["Segoe UI", "Geeza Pro", "Noto Sans Arabic", "Noto Naskh Arabic", "DejaVu Sans"],
    "devanagari": ["Nirmala UI", "Kohinoor Devanagari", "Noto Sans Devanagari", "Lohit Devanagari"],
    "latin": ["Arial", "Helvetica Neue", "DejaVu Sans", "Liberation Sans", "Noto Sans"],
}
# how wide one character is, as a share of the font size (Thai counts its stacked vowels and tone marks as characters)
CHAR_WIDTH = {"thai": 0.50, "japanese": 1.0, "chinese": 1.0, "korean": 1.0, "arabic": 0.5, "devanagari": 0.6, "latin": 0.52}


def script_of(text: str, lang: str = "") -> str:
    """Which writing system the subtitles are in, from the text itself (the language code only settles ja / zh)."""
    counts = {"thai": 0, "kana": 0, "han": 0, "korean": 0, "arabic": 0, "devanagari": 0}
    for ch in text:
        o = ord(ch)
        if 0x0E00 <= o <= 0x0E7F:
            counts["thai"] += 1
        elif 0x3040 <= o <= 0x30FF:
            counts["kana"] += 1
        elif 0x4E00 <= o <= 0x9FFF:
            counts["han"] += 1
        elif 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
            counts["korean"] += 1
        elif 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F:
            counts["arabic"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["devanagari"] += 1
    best = max(counts, key=counts.get)
    if not counts[best]:
        return "latin"
    if best in ("kana", "han"):
        return "japanese" if counts["kana"] or lang.lower().startswith("ja") else "chinese"
    return best


def installed_fonts() -> set[str] | None:
    """Lower-case family names of the fonts on this computer, or None when there is no cheap way to list them."""
    if os.name == "nt":
        import winreg
        names: set[str] = set()
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        # "Leelawadee UI Bold (TrueType)", "Yu Gothic Regular & Yu Gothic UI Regular (TrueType)"
                        value = re.sub(r"\s*\(.*?\)\s*$", "", winreg.EnumValue(key, i)[0])
                        names.update(part.strip().lower() for part in value.split("&"))
            except OSError:
                pass
        return names or None
    fc = shutil.which("fc-list")
    if fc:
        try:
            out = subprocess.run([fc, ":", "family"], capture_output=True, text=True, errors="replace", timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        return {name.strip().lower() for line in out.splitlines() for name in line.split(",") if name.strip()} or None
    return None


def pick_font(script: str, have: set[str] | None = None, system: str | None = None) -> str:
    """A font that can draw this script. Refuses, naming what to install, instead of rendering empty boxes."""
    have = installed_fonts() if have is None else have
    wanted = FONTS[script]
    if have:
        for name in wanted:
            # the Windows list has "Leelawadee UI Bold", "Arial Italic", ...: a family counts when any face of it is there
            if any(h == name.lower() or h.startswith(name.lower() + " ") for h in have):
                return name
        if script == "latin":
            return wanted[0]                 # every system can draw Latin letters with its fallback font
        raise SystemExit(f"no font for {script} text was found on this computer. Install one of: "
                         f"{', '.join(wanted)} (or name the font you want with --font).")
    system = system or platform.system()     # the font list is unknown: take the one that ships with the system
    index = {"Windows": 0, "Darwin": 2 if script in ("thai", "japanese") else 1}.get(system)
    if script == "latin":
        index = {"Windows": 0, "Darwin": 1}.get(system, 2)
    return wanted[min(index, len(wanted) - 1)] if index is not None else wanted[-2 if script != "latin" else 2]


VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
_libass: dict[str, bool] = {}


def has_libass(ffmpeg: str) -> bool:
    """Can this ffmpeg draw subtitles (was it built with libass)?"""
    if ffmpeg not in _libass:
        try:
            out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True,
                                 errors="replace", timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        _libass[ffmpeg] = bool(re.search(r"^\s*\S+\s+ass\s", out, re.MULTILINE))
    return _libass[ffmpeg]


def burn_ffmpeg() -> str:
    """An ffmpeg that can draw subtitles: the one babelscribe already uses, else the other one on this computer
    (the system's, or the one that comes with imageio-ffmpeg)."""
    found = []
    try:
        found.append(transcribe.ffmpeg())
    except SystemExit:
        pass
    try:
        import imageio_ffmpeg
        found.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    for exe in found:
        if has_libass(exe):
            return exe
    if not found:
        raise SystemExit("ffmpeg not found: install it or `pip install imageio-ffmpeg`")
    raise SystemExit(f"this ffmpeg cannot draw subtitles (it was built without libass): {found[0]}\n"
                     "Install a full ffmpeg and put it on PATH (Windows: winget install Gyan.FFmpeg, "
                     "macOS: brew install ffmpeg, Linux: your package manager's ffmpeg), then run again.")


def probe(path: Path, ffmpeg: str | None = None) -> str:
    """What ffmpeg says about the file (its streams and length)."""
    return subprocess.run([ffmpeg or transcribe.ffmpeg(), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL).stderr


def video_size(path: Path, ffmpeg: str | None = None) -> tuple[int, int]:
    """Width and height as the video is shown (a phone video stored sideways counts as upright)."""
    return parse_size(probe(path, ffmpeg), path)


def parse_duration(info: str) -> float:
    """Length in seconds, 0 when ffmpeg does not know it."""
    m = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", info)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def parse_size(info: str, path: Path | str = "the file") -> tuple[int, int]:
    m = re.search(r"Stream #.*Video:.*?[ ,](\d{2,5})x(\d{2,5})[ ,\[\n]", info)
    if not m:
        raise SystemExit(f"{path} has no video to draw subtitles on. --burn needs a video file; "
                         f"for audio, the subtitle files are the result.")
    w, h = int(m.group(1)), int(m.group(2))
    turn = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", info)
    if turn and round(abs(float(turn.group(1)))) % 180 == 90:
        w, h = h, w
    return w, h


def layout(style: str, width: int, height: int, script: str, lang: str = "") -> dict:
    """Font size, margins and line length for this look on a picture of this size."""
    if style not in STYLES:
        raise SystemExit(f"unknown style '{style}'. Styles: {', '.join(STYLES)}")
    vertical = height > width
    base = min(width, height)
    size = round(base * (0.085 if style == "shorts" else 0.05))
    side = round(width * 0.05)
    fits = int((width - 2 * side) / (size * CHAR_WIDTH[script]))
    usual = writers._default_max_line_chars({"lang": lang}) if script == "latin" or lang else writers.CJK_THAI_MAX_LINE_CHARS
    if script != "latin":
        usual = min(usual, writers.CJK_THAI_MAX_LINE_CHARS)
    if style == "shorts":                      # above the caption and buttons an app draws over a vertical video
        bottom = round(height * (0.30 if vertical else 0.12))
    else:
        bottom = round(height * (0.14 if vertical else 0.06))
    return {"size": size, "side": side, "bottom": bottom, "chars": max(8, min(fits, usual)),
            "outline": max(2, round(size * (0.09 if style == "shorts" else 0.06))), "bold": style == "shorts"}


# Thai letters that cannot start a piece of text: marks written above or below the consonant before them, and
# vowels written after it. And the vowels written in front of their consonant, which cannot end one.
_THAI_JOINS_BACK = set("\u0e30\u0e31\u0e32\u0e33\u0e34\u0e35\u0e36\u0e37\u0e38\u0e39\u0e3a\u0e45\u0e46"
                       "\u0e47\u0e48\u0e49\u0e4a\u0e4b\u0e4c\u0e4d\u0e4e")
_THAI_JOINS_NEXT = set("\u0e40\u0e41\u0e42\u0e43\u0e44")
SHORT_CHARS = {"thai": 14, "japanese": 8, "chinese": 8, "korean": 10}   # letters on screen at once, 'shorts' look


def _units(tokens: list, script: str) -> list[list]:
    """The pieces a caption may be cut between, each a list of whisper tokens.

    Languages written with spaces: words (whisper's tokens are word pieces; a new word starts with a space).
    Thai: real words when pythainlp is installed (pip install "babelscribe[thai]"), each timed from the tokens
    it covers; without it, tokens joined so that no vowel or tone mark is cut from its consonant.
    Chinese and Japanese: the tokens as they are."""
    if script not in ("thai", "japanese", "chinese"):
        words: list[list] = []
        for tok in tokens:
            if words and not tok[0][:1].isspace():
                words[-1].append(tok)
            else:
                words.append([tok])
        return words
    if script == "thai":
        text = "".join(t[0] for t in tokens)
        times = [span for tok, t0, t1 in tokens for span in convert._spread(t0, t1, [1] * len(tok))]
        cuts = sorted(x for x in align._word_breaks(text) if 0 < x < len(text))
        if any(not text[x].isspace() and not text[x - 1].isspace() for x in cuts):   # pythainlp found the words
            edges = [0] + cuts + [len(text)]
            return [[[text[a:b], times[a][0], times[b - 1][1]]] for a, b in zip(edges, edges[1:]) if text[a:b].strip()]
    units: list[list] = []
    for tok in tokens:
        first, before = tok[0].lstrip()[:1], (units[-1][-1][0].rstrip()[-1:] if units else "")
        if units and not tok[0][:1].isspace() and (first in _THAI_JOINS_BACK or before in _THAI_JOINS_NEXT):
            units[-1].append(tok)
        else:
            units.append([tok])
    return units


def short_cues(segs: list[dict], max_chars: int, max_words: int = 3, script: str = "latin") -> list[dict]:
    """A few words at a time, for the 'shorts' look: at most max_words words, or max_chars letters in a language
    written without spaces. Needs word timings; a segment without them is shown whole. A cue ends at a sentence
    end or a pause, and otherwise stays up until the next one starts."""
    spaced = script not in ("thai", "japanese", "chinese")
    cues: list[dict] = []
    for seg in segs:
        tokens = seg.get("words") or []
        if not tokens:
            cues.append({"start": seg["start"], "end": seg["end"], "text": seg["text"].strip(), "lines": []})
            continue
        group: list[list] = []
        first = len(cues)
        for unit in _units(tokens, script):
            text = "".join(t[0] for u in group + [unit] for t in u).strip()
            if group and ((spaced and len(group) >= max_words) or len(text) > max_chars
                          or unit[0][1] - group[-1][-1][2] > 0.6
                          or re.search(r"[.!?。！？…]$", "".join(t[0] for t in group[-1]).strip())):
                cues.append(writers._cue_from_lines([[t for u in group for t in u]]))
                group = []
            group.append(unit)
        if group:
            cues.append(writers._cue_from_lines([[t for u in group for t in u]]))
        for a, b in zip(cues[first:], cues[first + 1:]):
            if 0 < b["start"] - a["end"] <= 0.6:   # no flicker between groups of one sentence
                a["end"] = b["start"]
    return cues


def ass_document(segs: list[dict], meta: dict, style: str, width: int, height: int, font: str | None = None) -> str:
    """A complete ASS file for this video size and look."""
    lang = str(meta.get("lang", ""))
    script = script_of(" ".join(s["text"] for s in segs), lang)
    look = layout(style, width, height, script, lang)
    font = font or pick_font(script)
    spoken = {"plain": WHITE, "karaoke": AMBER, "shorts": YELLOW}[style]
    head = (
        "[Script Info]\n; Written by babelscribe\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{look['size']},{spoken},{WHITE},&H00000000,&H80000000,{-1 if look['bold'] else 0},"
        f"0,0,0,100,100,0,0,1,{look['outline']},{0 if style == 'shorts' else 1},2,{look['side']},{look['side']},"
        f"{look['bottom']},1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    if style == "shorts":
        cues = short_cues(segs, min(look["chars"], SHORT_CHARS.get(script, look["chars"])), script=script)
    else:
        cues = writers._subtitle_cues(segs, look["chars"])
    lines = []
    for c in cues:
        if style == "plain":
            text = writers._ass_escape(c["text"]).replace("\n", "\\N")
        else:
            text = writers._ass_karaoke(c)
        lines.append(f"Dialogue: 0,{writers._ass_ts(c['start'])},{writers._ass_ts(c['end'])},Default,,0,0,0,,{text}\n")
    return head + "".join(lines)


def read_srt(path: Path) -> list[dict]:
    """Cues of an .srt or .vtt as segments (no word timings, so they can only be drawn plain)."""
    segs = []
    stamp = r"(?:(\d+):)?(\d\d):(\d\d)[.,](\d{3})"
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")):
        m = re.search(stamp + r"\s*-->\s*" + stamp + r"[^\n]*\n(.+)", block, re.DOTALL)
        if m:
            g = m.groups()
            t0 = int(g[0] or 0) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
            t1 = int(g[4] or 0) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
            text = re.sub(r"<[^>]+>", "", g[8]).strip()
            if text:
                segs.append({"start": t0, "end": t1, "text": " ".join(text.split("\n")), "words": []})
    return segs


def find_subtitles(video: Path) -> Path:
    for ext in (".json", ".ass", ".srt", ".vtt"):
        for cand in (video.with_suffix(ext), video.parent / (video.name + ext)):
            if cand.is_file():
                return cand
    raise SystemExit(f"no subtitles found next to {video.name} (looked for .json, .ass, .srt, .vtt). "
                     f"Transcribe first: babelscribe \"{video.name}\" --burn")


_ENCODERS = {   # hardware encoder -> the options that give about the quality of libx264 -crf 18
    "h264_nvenc": ["-rc", "vbr", "-cq", "20", "-b:v", "0"],
    "h264_amf": ["-rc", "cqp", "-qp_i", "20", "-qp_p", "22"],
    "h264_qsv": ["-global_quality", "20"],
    "h264_videotoolbox": ["-q:v", "62"],
}
_picked: dict[str, list[str]] = {}


def encoder_args(ffmpeg: str) -> list[str]:
    """The video encoder to use: the GPU's when one works on this machine (tried once, on a tiny clip), else x264."""
    if ffmpeg in _picked:
        return _picked[ffmpeg]
    order = ["h264_videotoolbox"] if platform.system() == "Darwin" else ["h264_nvenc", "h264_amf", "h264_qsv"]
    for name in order:
        try:
            ok = subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=size=640x360:rate=30:duration=0.2",
                                 "-c:v", name, *_ENCODERS[name], "-f", "null", "-"],
                                capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if ok:
            _picked[ffmpeg] = ["-c:v", name, *_ENCODERS[name]]
            return _picked[ffmpeg]
    _picked[ffmpeg] = SOFTWARE
    return SOFTWARE


SOFTWARE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]


def burn_command(ffmpeg: str, video: Path, out: Path, subs_name: str, video_args: list[str], audio: str = "copy") -> list[str]:
    """The ffmpeg command line. It is run inside the folder that holds the subtitle file under a fixed, plain
    name, so the filter never contains the user's path: no drive-letter colons, spaces or quotes to escape."""
    kind = "ass" if subs_name.endswith(".ass") else "subtitles"
    return [ffmpeg, "-v", "error", "-nostats", "-progress", "pipe:1", "-y", "-i", str(video),
            "-vf", f"{kind}={subs_name}", *video_args,
            "-pix_fmt", "yuv420p", "-c:a", audio, "-movflags", "+faststart", str(out)]


def _run_ffmpeg(cmd: list[str], cwd: str, seconds: float, progress: Callable[[float], None] | None) -> tuple[int, str]:
    """Run ffmpeg, turning its `-progress` lines into percent of the video's length. Returns (exit code, errors)."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errors:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL,
                             text=True, errors="replace")
        for line in p.stdout:
            m = re.match(r"out_time_(?:us|ms)=(\d+)", line)       # both are microseconds, whatever the name says
            if m and progress and seconds > 0:
                progress(min(99.0, int(m.group(1)) / 1e6 / seconds * 100))
        code = p.wait()
        errors.seek(0)
        return code, errors.read()


def burn_file(
    video: str | Path,
    subtitles: str | Path | None = None,
    style: str = "plain",
    out: str | Path | None = None,
    font: str | None = None,
    log: Callable[[str], None] = print,
    progress: Callable[[float], None] | None = None,
) -> dict:
    """Draw subtitles onto a copy of the video. Returns {"file", "style", "subtitles", "encoder", "size"}.
    progress, when given, is called with 0-100 as the video is written.

    subtitles: a babelscribe .json (drawn in the chosen style, any look), an .ass (drawn exactly as it is, so
    your edits and styling are kept), or an .srt / .vtt (drawn plain). Default: the file next to the video."""
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(f"no such file: {video}")
    if style not in STYLES:
        raise SystemExit(f"unknown style '{style}'. Styles: {', '.join(STYLES)}")
    subs = Path(subtitles).expanduser().resolve() if subtitles else find_subtitles(video)
    if not subs.is_file():
        raise FileNotFoundError(f"no such file: {subs}")
    dest = Path(out).expanduser().resolve() if out else video.with_name(video.stem + ".subbed.mp4")
    if dest == video:
        raise SystemExit("the output would overwrite the input video; pass another -o")
    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = burn_ffmpeg()
    info = probe(video, ffmpeg)
    width, height = parse_size(info, video)
    seconds = parse_duration(info)

    with tempfile.TemporaryDirectory() as d:
        if subs.suffix.lower() == ".ass":
            shutil.copy(subs, Path(d) / "subs.ass")
            used = "as written in the .ass"
        else:
            if subs.suffix.lower() == ".json":
                data = convert.load(subs)
                segs = [s for s in data["segments"] if str(s["text"]).strip()]
                [convert.retime_words(s) for s in segs]
                meta = data.get("meta") or {}
            else:
                segs, meta = read_srt(subs), {}
                if style != "plain":
                    log(f"{subs.name} has no word timings: drawing it plain. Use the .json for {style}.")
                    style = "plain"
            if not segs:
                raise SystemExit(f"{subs} has no subtitles in it")
            if style == "shorts" and script_of(" ".join(s["text"] for s in segs)) == "thai":
                try:
                    import pythainlp  # noqa: F401
                except ImportError:
                    log('tip: pip install "babelscribe[thai]" keeps Thai words whole in the shorts look')
            (Path(d) / "subs.ass").write_text(ass_document(segs, meta, style, width, height, font), encoding="utf-8")
            used = style
        log(f"burning subtitles ({used}) into {dest.name} ...")
        tries = [(encoder_args(ffmpeg), "copy")]
        if tries[0][0] != SOFTWARE:
            tries.append((SOFTWARE, "copy"))               # a GPU encoder can refuse a size or pixel format
        tries.append((SOFTWARE, "aac"))                    # audio that an .mp4 cannot hold as it is
        err = ""
        for video_args, audio in tries:
            code, err = _run_ffmpeg(burn_command(ffmpeg, video, dest, "subs.ass", video_args, audio), d, seconds, progress)
            if code == 0:
                if progress:
                    progress(100.0)
                log(f"-> {dest}")
                return {"file": str(dest), "style": used, "subtitles": str(subs), "encoder": video_args[1],
                        "size": f"{width}x{height}"}
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg could not write {dest.name}:\n{err[-1500:]}")


def main(argv: list[str]) -> None:
    """babelscribe burn clip.mp4 [clip.ass] --style shorts"""
    import argparse
    ap = argparse.ArgumentParser(
        prog="babelscribe burn",
        description="Draw subtitles onto a copy of the video (clip.subbed.mp4). The input is never changed.")
    ap.add_argument("video")
    ap.add_argument("subtitles", nargs="?", help=".json, .ass, .srt or .vtt (default: the one next to the video)")
    ap.add_argument("--style", default="plain", choices=STYLES, help="plain | karaoke (word highlight) | shorts "
                    "(big, 2-3 words at a time, for vertical video). An .ass file is drawn as it is.")
    ap.add_argument("--font", help="font family to use instead of the one picked for the language")
    ap.add_argument("-o", "--out", help="output video (default: NAME.subbed.mp4 next to the input)")
    ap.add_argument("--no-progress", action="store_true", help="never draw the progress bar")
    a = ap.parse_args(argv)
    bar = None
    if sys.stderr.isatty() and not a.no_progress:
        from .cli import progress_bar
        bar = progress_bar()
    try:
        burn_file(a.video, a.subtitles, a.style, a.out, a.font, progress=bar)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main(sys.argv[1:])
