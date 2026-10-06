"""Hybrid mode: accurate TEXT from a language fine-tune (often without usable timestamps) + accurate TIMING from a
general model. Both transcripts are aligned character by character (spaces/punctuation ignored, works for languages
without spaces such as Thai, Chinese, Japanese); every character of the accurate text gets a time, and the text is
re-segmented on the timing model's segment boundaries."""
from __future__ import annotations

import difflib
import re
import unicodedata

_SKIP = re.compile(r"[\s\W_]", re.UNICODE)


def _chars_with_times(segs: list[dict]) -> tuple[str, list[float]]:
    chars, times = [], []
    for s in segs:
        toks = s.get("words") or [[s["text"], s["start"], s["end"]]]
        for text, t0, t1 in toks:
            clean = [c for c in unicodedata.normalize("NFC", text) if not _SKIP.match(c)]
            for i, c in enumerate(clean):
                chars.append(c)
                times.append(t0 + (t1 - t0) * (i + .5) / max(1, len(clean)))
    return "".join(chars), times


def _word_breaks(text: str) -> set[int]:
    """Positions where a new word starts. Spaces everywhere; for Thai/Lao/Khmer/Burmese use pythainlp if installed."""
    br = {i for i, c in enumerate(text) if i and (text[i - 1].isspace() or c.isspace())}
    if any('฀' <= c <= '๿' for c in text):
        try:
            from pythainlp.tokenize import word_tokenize
            pos = 0
            for w in word_tokenize(text, keep_whitespace=True):
                br.add(pos); pos += len(w)
        except ImportError:
            pass
    return br


def hybrid(text_segs: list[dict], time_segs: list[dict]) -> list[dict]:
    full = " ".join(s["text"] for s in text_segs)
    full = unicodedata.normalize("NFC", full)
    ref, ref_t = _chars_with_times(time_segs)
    keep = [(i, c) for i, c in enumerate(full) if not _SKIP.match(c)]
    hyp = "".join(c for _, c in keep)
    sm = difflib.SequenceMatcher(None, hyp, ref, autojunk=False)
    t_of = [None] * len(hyp)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            t_of[a + k] = ref_t[b + k]
    # fill gaps by linear interpolation between matched neighbours
    known = [i for i, t in enumerate(t_of) if t is not None]
    if not known:
        return time_segs
    for i in range(len(t_of)):
        if t_of[i] is None:
            lo = max((k for k in known if k < i), default=None)
            hi = min((k for k in known if k > i), default=None)
            if lo is None:
                t_of[i] = t_of[hi]
            elif hi is None:
                t_of[i] = t_of[lo]
            else:
                t_of[i] = t_of[lo] + (t_of[hi] - t_of[lo]) * (i - lo) / (hi - lo)
    char_time = {}
    for (pos, _), t in zip(keep, t_of):
        char_time[pos] = t
    # cut the accurate text at the timing model's segment ends
    bounds = [s["end"] for s in time_segs]
    out, cur, cur_t0, bi = [], [], None, 0
    last_t = 0.0
    breaks = _word_breaks(full)
    hold = False
    for pos, ch in enumerate(full):
        t = char_time.get(pos, last_t)
        last_t = t
        # never cut inside a word: if we are mid-word, keep filling the current segment until the next word break
        hold = bool(cur) and pos not in breaks and pos - (max((b for b in breaks if b <= pos), default=0)) < 14
        while not hold and bi < len(bounds) - 1 and t > bounds[bi]:
            if cur and "".join(cur).strip():
                out.append({"start": cur_t0, "end": bounds[bi], "text": "".join(cur).strip(), "words": []})
            cur, cur_t0 = [], None
            bi += 1
        if cur_t0 is None and not ch.isspace():
            cur_t0 = t
        cur.append(ch)
    if cur and "".join(cur).strip():
        out.append({"start": cur_t0, "end": time_segs[-1]["end"], "text": "".join(cur).strip(), "words": []})
    return _fill_uncovered(out, time_segs, sm, ref, ref_t)


def _fill_uncovered(out: list[dict], time_segs: list[dict], sm: difflib.SequenceMatcher, ref: str, ref_t: list[float]) -> list[dict]:
    """Text models often skip the first/last words of a clip. Where the timing transcript has speech that the
    accurate text never matched (head or tail), keep the timing model's words there instead of losing them."""
    blocks = [b for b in sm.get_matching_blocks() if b.size >= 3]   # ignore stray 1–2 char matches
    if not blocks or not ref:
        return out
    first_ref, last_ref = blocks[0].b, blocks[-1].b + blocks[-1].size - 1
    def words_between(t0: float, t1: float) -> str:
        ws = [w for s in time_segs for w in (s.get("words") or [[s["text"], s["start"], s["end"]]]) if t0 < (w[1] + w[2]) / 2 <= t1]
        return "".join(w[0] for w in ws).strip()
    if len(ref) - 1 - last_ref > 2:
        tail = words_between(ref_t[last_ref], time_segs[-1]["end"] + 1)
        tail = tail.lstrip("".join(chr(c) for c in range(0x0e31, 0x0e4f) if unicodedata.category(chr(c)) == "Mn"))   # no orphan vowel/tone marks
        if tail and out:
            out[-1]["text"] = (out[-1]["text"] + " " + tail).strip(); out[-1]["end"] = time_segs[-1]["end"]
    if first_ref > 2:
        head = words_between(time_segs[0]["start"] - 1, ref_t[first_ref] - .01)
        if head and out:
            out[0]["text"] = (head + " " + out[0]["text"]).strip(); out[0]["start"] = time_segs[0]["start"]
    return out
