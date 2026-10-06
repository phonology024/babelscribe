"""Multilingual accuracy benchmark on Google FLEURS (verbatim, human-checked transcripts, 102 languages).
usage:
  python bench/fleurs.py fetch DIR [--n 50] [--langs en_us,th_th,...]     # download N test utterances per language
  python bench/fleurs.py run DIR --bin whisper-cli --model ggml.bin --tag NAME [--beam 5] [--langs ...] [--extra "..."]
  python bench/fleurs.py table DIR [--tags a,b]                             # markdown table of the runs so far
  python bench/fleurs.py rescore DIR --tag NAME                             # re-score saved output after a normaliser change
Scores: WER for space-separated languages, CER for ja / zh / th / ko / lo / km / my (Whisper paper convention).
Each run also stores '<tag>~trim': the same score after dropping hypothesis words that come BEFORE the first or AFTER the
last reference word. Some FLEURS clips contain more speech than their reference transcript (the model hears a clause the
reference leaves out); ~trim removes that artefact. Hypotheses are saved in DIR/hyps/<tag>/ so scores can be recomputed."""
from __future__ import annotations
import argparse, json, re, subprocess, sys, unicodedata, urllib.request
from pathlib import Path

LANGS = "en_us,es_419,fr_fr,de_de,pt_br,it_it,ru_ru,ar_eg,hi_in,id_id,vi_vn,tr_tr,ja_jp,cmn_hans_cn,ko_kr,th_th".split(",")
CER = {"ja", "cmn", "zh", "th", "ko", "lo", "km", "my", "yue"}
WHISPER = {"cmn": "zh", "yue": "yue"}   # FLEURS code prefix -> whisper language code


def wlang(cfg: str) -> str:
    p = cfg.split("_")[0]
    return WHISPER.get(p, p)


def fetch(d: Path, n: int, langs: list[str]) -> None:
    """Stream FLEURS test audio straight from the dataset repo and stop after n files (no full tarball download)."""
    import csv, io, tarfile
    base = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/{cfg}/{f}"
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "babelscribe-bench"}))
    for cfg in langs:
        out = d / cfg; out.mkdir(parents=True, exist_ok=True)
        if (out / "refs.json").exists():
            continue
        tsv = get(base.format(cfg=cfg, f="test.tsv")).read().decode("utf-8")
        meta = {r[1]: r[2] for r in csv.reader(io.StringIO(tsv), delimiter="	", quoting=csv.QUOTE_NONE) if len(r) > 2}   # file -> raw transcription
        refs = {}
        with tarfile.open(fileobj=get(base.format(cfg=cfg, f="audio/test.tar.gz")), mode="r|gz") as tar:
            for m in tar:
                name = Path(m.name).name
                if not m.isfile() or name not in meta:
                    continue
                k = f"{len(refs):04d}"; raw = out / (k + ".src")
                raw.write_bytes(tar.extractfile(m).read())
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-ac", "1", "-ar", "16000", str(out / f"{k}.wav")], check=True); raw.unlink()
                refs[k] = meta[name]
                if len(refs) >= n:
                    break
        (out / "refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=0), encoding="utf-8")
        print(cfg, len(refs), "utterances", flush=True)


def spell_numbers(s: str, lang: str) -> str:
    """'100' and 'cent' must count as the same word: spell digits out in the utterance's language (scoring only)."""
    try:
        from num2words import num2words
    except ImportError:
        return s
    def rep(m):
        try:
            return " " + num2words(int(m.group(0).replace(",", "")), lang=lang) + " "
        except Exception:
            return m.group(0)
    return re.sub(r"\d[\d,]*", rep, s)


def norm(s: str, cer: bool, lang: str = "") -> str:
    """Whisper's BasicTextNormalizer rule: drop non-spacing marks (Mn) without splitting words, keep letters, digits and
    spacing vowel signs (Mc), turn punctuation/symbols into spaces. Same rule for every language and for both sides."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]|<[^>]*>", " ", s)
    if lang and not cer:
        s = spell_numbers(s, lang)
    out = []
    for c in s:
        cat = unicodedata.category(c)
        if cat == "Mn":
            continue                                   # non-spacing marks (diacritics, nukta, harakat): dropped, as Whisper's normaliser does
        if cat[0] in "LNM" or c.isspace():
            out.append(c)
        elif c in "'’":
            continue                                   # don't -> dont, city's -> citys
        else:
            out.append(" ")
    return re.sub(r"\s+", "" if cer else " ", "".join(out)).strip()


def score(d: Path, cfg: str, hyps: dict[str, str]) -> tuple[float, float]:
    """(raw, edge-trimmed) error rate for one language."""
    import jiwer
    refs = json.loads((d / cfg / "refs.json").read_text(encoding="utf-8")); cer = cfg.split("_")[0] in CER; L = wlang(cfg)
    E = Et = N = 0
    for k in refs:
        r, h = norm(refs[k], cer, L), norm(hyps.get(k, ""), cer, L)
        if not r:
            continue
        o = (jiwer.process_characters if cer else jiwer.process_words)(r, h or "∅")
        e = o.substitutions + o.deletions + o.insertions; al = o.alignments[0]
        edge = sum(c.hyp_end_idx - c.hyp_start_idx for c in (al[0], al[-1]) if c.type == "insert") if h else 0
        if len(al) == 1:
            edge = min(edge, e)
        E += e; Et += e - edge; N += o.substitutions + o.deletions + o.hits
    return round(100 * E / N, 2), round(100 * Et / N, 2)


def save(d: Path, tag: str, cfg: str, hyps: dict[str, str]) -> None:
    res = json.loads((d / "results.json").read_text(encoding="utf-8")) if (d / "results.json").exists() else {}
    raw, trim = score(d, cfg, hyps)
    res.setdefault(tag, {})[cfg] = raw; res.setdefault(tag + "~trim", {})[cfg] = trim
    (d / "results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    h = d / "hyps" / tag.replace(":", "_"); h.mkdir(parents=True, exist_ok=True)
    (h / f"{cfg}.json").write_text(json.dumps(hyps, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{tag} {cfg}: {'CER' if cfg.split('_')[0] in CER else 'WER'} {raw:.2f}% (edge-trimmed {trim:.2f}%)", flush=True)


def run(d: Path, a) -> None:
    for cfg in a.langs:
        out = d / cfg; refs = json.loads((out / "refs.json").read_text(encoding="utf-8")); wavs = [out / f"{k}.wav" for k in refs]
        for w in wavs:
            Path(str(w) + ".json").unlink(missing_ok=True)
        cmd = [a.bin, "-m", a.model, "-l", wlang(cfg), "-oj", "-mc", "0", "-np"] + (["-bs", str(a.beam)] if a.beam else []) + (a.extra.split() if a.extra else [])
        for w in wavs:
            cmd += ["-f", str(w)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        save(d, a.tag, cfg, disk_hyps(d, cfg))


def disk_hyps(d: Path, cfg: str) -> dict[str, str]:
    refs = json.loads((d / cfg / "refs.json").read_text(encoding="utf-8")); out = {}
    for k in refs:
        j = json.loads(Path(str(d / cfg / f"{k}.wav") + ".json").read_text(encoding="utf-8", errors="replace"))
        out[k] = " ".join(s["text"] for s in j["transcription"])
    return out


def table(d: Path, only: str | None = None) -> None:
    res = json.loads((d / "results.json").read_text(encoding="utf-8")); tags = only.split(",") if only else list(res)
    langs = [c for c in LANGS if any(c in res[t] for t in tags)] + sorted({c for t in tags for c in res[t]} - set(LANGS))
    print("| Language | metric | " + " | ".join(tags) + " |\n|---|---|" + "---|" * len(tags))
    for c in langs:
        print(f"| {c} | {'CER' if c.split('_')[0] in CER else 'WER'} | " + " | ".join(f"{res[t][c]:.1f}%" if c in res[t] else "–" for t in tags) + " |")


def rescore(d: Path, a) -> None:
    """Recompute scores after a normaliser change: from saved hypotheses of --tag, or (no saved copy) the outputs on disk."""
    for cfg in a.langs:
        h = d / "hyps" / a.tag.replace(":", "_") / f"{cfg}.json"
        save(d, a.tag, cfg, json.loads(h.read_text(encoding="utf-8")) if h.exists() else disk_hyps(d, cfg))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("dir"); ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--langs", default=",".join(LANGS)); ap.add_argument("--bin"); ap.add_argument("--model"); ap.add_argument("--tag")
    ap.add_argument("--beam", type=int); ap.add_argument("--extra"); ap.add_argument("--tags", help="table: comma list of tags to show")
    a = ap.parse_args(); a.langs = a.langs.split(","); D = Path(a.dir); D.mkdir(parents=True, exist_ok=True)
    {"fetch": lambda: fetch(D, a.n, a.langs), "run": lambda: run(D, a), "table": lambda: table(D, a.tags), "rescore": lambda: rescore(D, a)}[a.cmd]()
