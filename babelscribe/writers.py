"""Output formats: srt, vtt, txt, json, ass."""
from __future__ import annotations

import json
from pathlib import Path


DEFAULT_MAX_LINE_CHARS = 42
# Karaoke cues are read a word at a time, so they are kept shorter than ordinary subtitles.
ASS_MAX_LINE_CHARS = 32

# PrimaryColour is what a word turns into once it has been spoken, SecondaryColour what it is before.
# Colours are &HAABBGGRR: white &H00FFFFFF, amber &H0000D7FF. Change these two values to restyle.
ASS_UNSPOKEN_COLOUR = "&H00FFFFFF"

ASS_HEADER = """[Script Info]
; Written by babelscribe
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H0000D7FF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# The maintainer requested a smaller default for CJK/Thai.
# 24 is our proposed starting point and can easily be adjusted
# based on maintainer feedback.
CJK_THAI_MAX_LINE_CHARS = 24
CJK_THAI_LANGS = {"zh", "ja", "ko", "th"}


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _ass_ts(t: float) -> str:
    """ASS timestamps: H:MM:SS.cc — centiseconds, and the hour is not zero-padded."""
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    """Make a plain string safe inside an ASS event line: braces start an override block, so a literal brace
    would swallow the rest of the line. The full-width forms look the same and mean nothing to libass."""
    return text.replace("{", "｛").replace("}", "｝")


def _default_max_line_chars(meta: dict) -> int:
    """Choose a subtitle line length based on the detected language."""
    lang = str(meta.get("lang", "")).lower().split("-")[0]

    if lang in CJK_THAI_LANGS:
        return CJK_THAI_MAX_LINE_CHARS

    return DEFAULT_MAX_LINE_CHARS


def _subtitle_cues(
    segs: list[dict],
    max_line_chars: int,
) -> list[dict]:
    """Split transcription segments into readable subtitle cues.

    Each subtitle cue contains at most two lines. Long segments are
    divided using Whisper word timings so that each new cue keeps
    accurate start/end timestamps. A cue also keeps its words grouped
    per line, which the karaoke writer needs and the others ignore.
    """
    if max_line_chars <= 0:
        raise ValueError("max_line_chars must be greater than 0")

    cues = []

    for seg in segs:
        text = seg["text"].strip()
        words = seg.get("words") or []

        # Already short enough: preserve the original segment exactly. The words are kept in one line group
        # anyway — the plain formats ignore them, but the karaoke writer needs them even for short cues.
        if len(text) <= max_line_chars:
            cues.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": text,
                "lines": [words] if words else [],
            })
            continue

        # Without word timings we cannot safely create new timed cues.
        # Preserve the original segment rather than invent timestamps.
        if not words:
            cues.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": text,
                "lines": [],
            })
            continue

        lines: list[list] = []
        current_line: list = []

        for word in words:
            token = word[0]

            candidate = (
                "".join(w[0] for w in current_line) + token
            ).strip()

            if current_line and len(candidate) > max_line_chars:
                lines.append(current_line)
                current_line = [word]
            else:
                current_line.append(word)

        if current_line:
            lines.append(current_line)

        # Combine at most two lines into each subtitle cue.
        for i in range(0, len(lines), 2):
            cue_lines = lines[i:i + 2]

            first_word = cue_lines[0][0]
            last_word = cue_lines[-1][-1]

            cue_text = "\n".join(
                "".join(word[0] for word in line).strip()
                for line in cue_lines
            )

            cues.append({
                "start": first_word[1],
                "end": last_word[2],
                "text": cue_text,
                "lines": cue_lines,
            })

    return cues


def _ass_karaoke(cue: dict) -> str:
    """One ASS event text with a \\k tag per word.

    Each word lasts until the next one starts (the last one until the cue ends), so the highlight never runs
    ahead of the audio when whisper leaves a gap between words. Cues with no word timings fall back to plain
    text: the line still shows, it just does not animate.
    """
    lines = cue.get("lines") or []
    if not lines:
        # No word timings: do not invent them (the same rule _subtitle_cues follows). A line with no \k tag is
        # drawn in PrimaryColour, which is the *spoken* colour, so pin it to the unspoken one instead.
        return "{\\c" + ASS_UNSPOKEN_COLOUR + "}" + _ass_escape(cue["text"]).replace("\n", "\\N")

    flat = [w for line in lines for w in line]
    out, k = [], 0
    for line in lines:
        parts = []
        for j, (tok, t0, _t1) in enumerate(line):
            nxt = flat[k + j + 1][1] if k + j + 1 < len(flat) else cue["end"]
            cs = int(round(max(0.0, max(nxt, t0) - t0) * 100))
            parts.append(f"{{\\k{cs}}}{_ass_escape(tok.replace(chr(10), ' '))}")
        out.append("".join(parts).strip())
        k += len(line)
    return "\\N".join(out)


def write(
    segs: list[dict],
    base: Path,
    formats: list[str],
    meta: dict,
    max_line_chars: int | None = None,
) -> list[Path]:
    out = []

    line_limit = (
        max_line_chars
        if max_line_chars is not None
        else _default_max_line_chars(meta)
    )

    subtitle_segs = _subtitle_cues(segs, line_limit)

    for f in formats:
        p = base.with_suffix("." + f)

        if f == "srt":
            p.write_text(
                "".join(
                    f"{i}\n"
                    f"{_ts(s['start'], ',')} --> {_ts(s['end'], ',')}\n"
                    f"{s['text']}\n\n"
                    for i, s in enumerate(subtitle_segs, 1)
                ),
                encoding="utf-8",
            )

        elif f == "vtt":
            p.write_text(
                "WEBVTT\n\n"
                + "".join(
                    f"{_ts(s['start'], '.')} --> {_ts(s['end'], '.')}\n"
                    f"{s['text']}\n\n"
                    for s in subtitle_segs
                ),
                encoding="utf-8",
            )

        elif f == "txt":
            p.write_text(
                "\n".join(s["text"] for s in segs) + "\n",
                encoding="utf-8",
            )

        elif f == "json":
            p.write_text(
                json.dumps(
                    {"meta": meta, "segments": segs},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )

        elif f == "ass":
            karaoke = _subtitle_cues(segs, min(line_limit, ASS_MAX_LINE_CHARS))
            p.write_text(
                ASS_HEADER
                + "".join(
                    f"Dialogue: 0,{_ass_ts(s['start'])},{_ass_ts(s['end'])},Default,,0,0,0,,{_ass_karaoke(s)}\n"
                    for s in karaoke
                ),
                encoding="utf-8",
            )

        else:
            raise SystemExit(f"unknown format {f}")

        out.append(p)

    return out