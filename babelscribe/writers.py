"""Output formats: srt, vtt, txt, json."""
from __future__ import annotations

import json
from pathlib import Path


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write(segs: list[dict], base: Path, formats: list[str], meta: dict) -> list[Path]:
    out = []
    for f in formats:
        p = base.with_suffix("." + f)
        if f == "srt":
            p.write_text("".join(f"{i}\n{_ts(s['start'], ',')} --> {_ts(s['end'], ',')}\n{s['text']}\n\n" for i, s in enumerate(segs, 1)), encoding="utf-8")
        elif f == "vtt":
            p.write_text("WEBVTT\n\n" + "".join(f"{_ts(s['start'], '.')} --> {_ts(s['end'], '.')}\n{s['text']}\n\n" for s in segs), encoding="utf-8")
        elif f == "txt":
            p.write_text("\n".join(s["text"] for s in segs) + "\n", encoding="utf-8")
        elif f == "json":
            p.write_text(json.dumps({"meta": meta, "segments": segs}, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            raise SystemExit(f"unknown format {f}")
        out.append(p)
    return out
