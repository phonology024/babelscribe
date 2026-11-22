"""Write subtitles again from a saved babelscribe JSON: another format, another line width, or after the text was
corrected by hand. No model, no GPU, no audio."""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from . import writers


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _word_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of every word, each with the whitespace in front of it, the way whisper tokens carry it."""
    return [(m.start(), m.end()) for m in re.finditer(r"\s*\S+", text)]


def _spread(t0: float, t1: float, sizes: list[int]) -> list[tuple[float, float]]:
    """Share the time from t0 to t1 among pieces in proportion to their length."""
    total = sum(sizes) or 1
    out, done = [], 0
    for n in sizes:
        out.append((t0 + (t1 - t0) * done / total, t0 + (t1 - t0) * (done + n) / total))
        done += n
    return out


def _one_word(old: str, times: list, starts: set, new: str) -> list:
    """One word replaced by one word (a spelling fix, or a whole line in a language written without spaces).
    Characters that did not change keep their time and their token boundaries; changed ones share the time of
    what they replaced and stay in one piece."""
    new_times: list = [None] * len(new)
    cuts = {0}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                new_times[j1 + k] = times[i1 + k]
                if i1 + k in starts:
                    cuts.add(j1 + k)
        elif j2 > j1:
            t0 = times[i1][0] if i1 < len(times) else times[-1][1]
            t1 = times[i2 - 1][1] if i2 > i1 else t0
            new_times[j1:j2] = _spread(t0, t1, [1] * (j2 - j1))
    edges = sorted(cuts) + [len(new)]
    return [[new[a:b], new_times[a][0], new_times[b - 1][1]] for a, b in zip(edges, edges[1:])]


def retime_words(seg: dict) -> bool:
    """If the segment's text was edited after transcription, rebuild its word timings to say the new text.

    The subtitle writers wrap and time long cues from `words`, so an edit that only touched `text` would not
    show up there. Words that did not change keep their time; new words share the time of the words they
    replaced. Returns True when the words were rebuilt. A segment without word timings is left alone."""
    words = seg.get("words") or []
    new = seg["text"].strip()
    old = "".join(w[0] for w in words)
    if not words or _squash(old) == _squash(new):
        return False
    lead = old[:len(old) - len(old.lstrip())]
    new = lead + new                                 # keep the leading space whisper puts on the first token

    times: list[tuple[float, float]] = []            # a time span for every character of the old text
    starts = set()                                   # where the old tokens start
    for tok, t0, t1 in words:
        starts.add(len(times))
        times += _spread(t0, t1, [1] * len(tok))

    ow, nw = _word_spans(old), _word_spans(new)
    rebuilt: list = []
    match = difflib.SequenceMatcher(None, [old[a:b].strip() for a, b in ow], [new[a:b].strip() for a, b in nw],
                                    autojunk=False)
    for tag, i1, i2, j1, j2 in match.get_opcodes():
        if tag == "equal":                           # unchanged words: the original tokens, exactly as they were
            for a, b in ow[i1:i2]:
                edges = [a] + sorted(x for x in starts if a < x < b) + [b]
                rebuilt += [[old[x:y], times[x][0], times[y - 1][1]] for x, y in zip(edges, edges[1:])]
        elif i2 - i1 == 1 and j2 - j1 == 1:
            (a, b), (c, d) = ow[i1], nw[j1]
            rebuilt += _one_word(old[a:b], times[a:b], {x - a for x in starts if a <= x < b}, new[c:d])
        elif j2 > j1:                                # words replaced or added: share the time of what they replaced
            if i2 > i1:
                t0, t1 = times[ow[i1][0]][0], times[ow[i2 - 1][1] - 1][1]
            else:                                    # nothing was replaced: only the pause before the next word
                t0 = rebuilt[-1][2] if rebuilt else seg["start"]
                t1 = times[ow[i1][0]][0] if i1 < len(ow) else seg["end"]
                t1 = max(t0, t1)
            spans = _spread(t0, t1, [d - c for c, d in nw[j1:j2]])
            rebuilt += [[new[c:d], t[0], t[1]] for (c, d), t in zip(nw[j1:j2], spans)]
    seg["words"] = [[tok, round(t0, 3), round(t1, 3)] for tok, t0, t1 in rebuilt if tok.strip()]
    return True


def load(json_path: str | Path) -> dict:
    p = Path(json_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"no such file: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise ValueError(f"{p} is not valid JSON ({e}). If you edited it by hand, check the quotes and commas.") from None
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise ValueError(f"{p} is not a babelscribe JSON (no 'segments' list). Make one with: babelscribe FILE -f json")
    for i, s in enumerate(data["segments"]):
        if not isinstance(s, dict) or not {"start", "end", "text"} <= set(s):
            raise ValueError(f"{p}: segment {i} needs 'start', 'end' and 'text'")
    return data


def convert_file(
    json_path: str | Path,
    formats: list[str] | None = None,
    out: str | Path | None = None,
    max_line_chars: int | None = None,
    max_lines: int = 2,
    max_cps: float | None = None,
    min_duration: float | None = None,
    max_duration: float | None = None,
) -> dict:
    """Write subtitle files from a babelscribe JSON. Returns {"files", "segments", "retimed"}.

    out is the output base path (default: next to the JSON, talk.json -> talk.srt). Text edited in the JSON is
    used as it is; `retimed` counts the segments whose word timings were rebuilt for it."""
    src = Path(json_path).expanduser()
    data = load(src)
    segs = [s for s in data["segments"] if str(s["text"]).strip()]
    retimed = sum(retime_words(s) for s in segs)
    base = Path(out).expanduser() if out else src.with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)
    files = writers.write(segs, base, formats or ["srt"], data.get("meta") or {}, max_line_chars=max_line_chars,
                          max_lines=max_lines, max_cps=max_cps, min_duration=min_duration, max_duration=max_duration)
    return {"files": [str(f) for f in files], "segments": len(segs), "retimed": retimed}
