"""Compare two versions of the hybrid alignment on exactly the same model outputs.

Running the models is the slow part and does not depend on the alignment, so it is done once and saved:
  python bench/hybrid_bench.py collect DIR/th_th thai-pathumma out.json [--shard 0/3] [--flavor cpu]
      DIR/th_th holds NAME.wav files and refs.json (bench/fleurs.py fetch writes that)
Then both versions merge the saved outputs and are scored with bench/fleurs.py's normaliser:
  python bench/hybrid_bench.py score OLD_align.py out1.json out2.json ...
`score` prints a table and every clip whose text differs, and exits with an error when any number got worse."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def collect(a) -> None:
    from babelscribe import api, backend, hybrid, models, transcribe
    folder = Path(a.dir)
    refs = json.loads((folder / "refs.json").read_text(encoding="utf-8"))
    index, count = (int(x) for x in a.shard.split("/"))
    ft = models.FINETUNES[a.model]
    binary = backend.find_binary(flavor=a.flavor)
    timing = models.ensure("turbo", api._quantizer(binary))
    text_model = models.ensure(a.model, api._quantizer(binary))
    found = backend.probe_devices(binary, timing)
    device = backend.pick_device(found)
    rows = []
    for key in sorted(refs)[index::count]:
        wav = folder / f"{key}.wav"
        time_segs = transcribe.run(binary, timing, wav, ft["lang"], device)
        parts = hybrid.chunks(time_segs)
        texts = hybrid.text_pass(binary, text_model, wav, parts, ft["lang"], device, ft.get("beam"))
        rows.append({"set": folder.name, "key": key, "ref": refs[key], "parts": parts, "texts": texts})
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"{folder.name} {key}: {len(parts)} chunk(s)", flush=True)


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score(a) -> None:
    from babelscribe import align, hybrid
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fleurs
    import jiwer
    old = load(a.old, "align_before")
    sets: dict[str, list[dict]] = {}
    for path in a.dumps:
        for row in json.loads(Path(path).read_text(encoding="utf-8")):
            sets.setdefault(row["set"], []).append(row)

    def errors(ref: str, hyp: str, cer: bool, lang: str) -> tuple[int, int, int]:
        r, h = fleurs.norm(ref, cer, lang), fleurs.norm(hyp, cer, lang)
        if not r:
            return 0, 0, 0
        o = (jiwer.process_characters if cer else jiwer.process_words)(r, h or "∅")
        e = o.substitutions + o.deletions + o.insertions
        al = o.alignments[0]
        edge = sum(c.hyp_end_idx - c.hyp_start_idx for c in (al[0], al[-1]) if c.type == "insert") if h else 0
        if len(al) == 1:
            edge = min(edge, e)
        return e, e - edge, o.substitutions + o.deletions + o.hits

    table, changed, worse = [], [], []
    for name, rows in sorted(sets.items()):
        lang, cer = fleurs.wlang(name), name.split("_")[0] in fleurs.CER
        total = {"before": [0, 0, 0], "after": [0, 0, 0]}
        for row in sorted(rows, key=lambda r: r["key"]):
            parts = [(p[0], p[1], p[2]) for p in row["parts"]]
            said = {}
            for label, module in (("before", old), ("after", align)):
                segs = hybrid.merge(json.loads(json.dumps(parts)), row["texts"], module.hybrid)
                said[label] = " ".join(s["text"] for s in segs)
                counted = errors(row["ref"], said[label], cer, lang)
                total[label] = [x + y for x, y in zip(total[label], counted)]
            if said["before"] != said["after"] and name.endswith("_ted"):
                changed.append(f"**{name} {row['key']}**: the text changed (a talk's transcript is not printed)")
            elif said["before"] != said["after"]:
                b, c = errors(row["ref"], said["before"], cer, lang), errors(row["ref"], said["after"], cer, lang)
                changed.append(f"**{name} {row['key']}**: errors {b[0]} -> {c[0]}\n- reference: {row['ref']}\n"
                               f"- before: {said['before']}\n- after: {said['after']}")
        metric = "CER" if cer else "WER"
        for i, label in ((0, metric), (1, f"{metric}, edge-trimmed")):
            b, c = (100 * total[v][i] / total[v][2] for v in ("before", "after"))
            table.append(f"| {name} | {len(rows)} | {label} | {b:.2f}% | {c:.2f}% | {total['before'][i]} | {total['after'][i]} |")
            if total["after"][i] > total["before"][i]:
                worse.append(f"{name} {label}")
    report = ("| set | clips | metric | before | after | errors before | errors after |\n|---|---|---|---|---|---|---|\n"
              + "\n".join(table) + f"\n\n{len(changed)} clip(s) changed.\n\n" + "\n\n".join(changed) + "\n")
    print(report)
    if a.report:
        with open(a.report, "a", encoding="utf-8") as f:
            f.write(report)
    if worse:
        raise SystemExit("worse than before: " + ", ".join(worse))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("dir"); c.add_argument("model"); c.add_argument("out")
    c.add_argument("--shard", default="0/1"); c.add_argument("--flavor")
    s = sub.add_parser("score")
    s.add_argument("old"); s.add_argument("dumps", nargs="+"); s.add_argument("--report")
    a = ap.parse_args()
    collect(a) if a.cmd == "collect" else score(a)


if __name__ == "__main__":
    main()
