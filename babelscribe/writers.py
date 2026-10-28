"""Output formats: srt, vtt, txt, json."""
from __future__ import annotations

import json
from pathlib import Path


DEFAULT_MAX_LINE_CHARS = 42

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
    accurate start/end timestamps.
    """
    if max_line_chars <= 0:
        raise ValueError("max_line_chars must be greater than 0")

    cues = []

    for seg in segs:
        text = seg["text"].strip()
        words = seg.get("words") or []

        # Already short enough: preserve the original segment exactly.
        if len(text) <= max_line_chars:
            cues.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": text,
            })
            continue

        # Without word timings we cannot safely create new timed cues.
        # Preserve the original segment rather than invent timestamps.
        if not words:
            cues.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": text,
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
            })

    return cues


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

        else:
            raise SystemExit(f"unknown format {f}")

        out.append(p)

    return out