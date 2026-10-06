"""Reproducible benchmark: real talks with HUMAN captions in the spoken language as the reference.
usage: python bench/bench.py <dir with *.m4a + *.<lang>.vtt> [--hybrid-th] [--accurate]
Prints a markdown table: speed (x real time) and error rate — WER for space-separated languages, CER for ja/zh/th.
Reference captions are edited for reading (fillers removed, light rewording), so error rates are an upper bound."""
import json, os, re, subprocess, sys, time, unicodedata
from pathlib import Path
import jiwer

D = Path(sys.argv[1]); HYB = "--hybrid-th" in sys.argv; ACC = "--accurate" in sys.argv
CER_LANGS = {"ja", "zh", "th", "lo", "km", "my"}

def vtt_text(p: Path) -> str:
    out, last = [], None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "-->" in line or not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or line.strip().isdigit():
            continue
        t = re.sub(r"<[^>]+>", "", line).strip()
        if t and t != last:
            out.append(t); last = t
    return " ".join(out)

def norm(s: str, cer: bool) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)          # (laughter) [applause]
    s = "".join(c if (c.isalnum() or c.isspace()) else " " for c in s)
    s = re.sub(r"\s+", " " if not cer else "", s).strip()
    return s

def run(media: Path, lang: str, extra: list[str]) -> tuple[str, float]:
    out = media.with_name(media.stem + ("_" + "".join(e.strip("-")[:3] for e in extra) if extra else "") + "_out")
    t0 = time.time()
    subprocess.run([sys.executable, "-m", "babelscribe", str(media), "-l", lang, "-f", "json", "-o", str(out)] + extra, check=True,
                   stdout=subprocess.DEVNULL)
    dt = time.time() - t0
    segs = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["segments"]
    return " ".join(s["text"] for s in segs), dt

def dur(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))

rows = []
for media in sorted(D.glob("*.m4a")):
    lang = media.stem.split("_")[0]; ref_p = next(D.glob(media.stem + f".{lang}*.vtt"))
    cer = lang in CER_LANGS; ref = norm(vtt_text(ref_p), cer); L = dur(media)
    modes = [("turbo", [])] + ([("hybrid thai-thonburian", ["--text-model", "thai-thonburian"])] if HYB and lang == "th" else [])         + ([("accurate", ["--accurate"])] if ACC else [])
    for name, extra in modes:
        hyp, dt = run(media, lang, extra); h = norm(hyp, cer)
        err = jiwer.cer(ref, h) if cer else jiwer.wer(ref, h)
        rows.append((lang, media.stem.split("_", 1)[1], L, name, dt, L / dt, ("CER" if cer else "WER"), err))
        print(f"{lang} {name}: {L / 60:.1f} min audio in {dt:.1f}s ({L / dt:.0f}x) {'CER' if cer else 'WER'} {err * 100:.1f}%", flush=True)
print("\n| Language | Talk | Length | Mode | Time | Speed | Error |\n|---|---|---|---|---|---|---|")
for lang, vid, L, name, dt, x, kind, err in rows:
    print(f"| {lang} | youtu.be/{vid} | {L / 60:.1f} min | {name} | {dt:.0f} s | {x:.0f}x real time | {kind} {err * 100:.1f}% |")
