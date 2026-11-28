"""One real fine-tune conversion, end to end, with the pinned files. Heavy (several GB, CPU torch): run by the
finetune-conversion workflow, not by the unit tests.

    python bench/fleurs.py fetch clips --n 3 --langs th_th
    BABELSCRIBE_HOME=empty-folder python tests/smoke/finetune_conversion.py clips/th_th thai-pathumma

1. The command a person types downloads the pinned fine-tune, converter and filter table, converts, quantizes and
   transcribes. 2. The pins are checked on disk. 3. The converted model alone transcribes each clip and must come close
   to the reference text (a conversion with wrong weights, tokens or filters writes nonsense or nothing)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

from babelscribe import api, backend, download, models, transcribe

MAX_CER = 0.35        # mean character error rate; the model scores 0.089 on FLEURS Thai (docs/benchmarks.md)


def plain(text: str) -> str:
    """Letters, marks and digits only: Thai writes vowels and tones as marks, so they must stay."""
    return "".join(c for c in unicodedata.normalize("NFC", text).lower() if unicodedata.category(c)[0] in "LMN")


def cer(ref: str, hyp: str) -> float:
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1] / max(1, len(ref))


def has_thai(text: str) -> bool:
    return any("฀" <= c <= "๿" for c in text)


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what, flush=True)
    if not ok:
        raise SystemExit(f"failed: {what}")


def main() -> None:
    clips, name = Path(sys.argv[1]), sys.argv[2]
    refs = json.loads((clips / "refs.json").read_text(encoding="utf-8"))
    ft = models.FINETUNES[name]
    model = models.path_for(name)
    check(not model.exists(), "the model is not there yet: this run converts it")

    first = sorted(refs)[0]
    out = clips / "hybrid"
    subprocess.run([sys.executable, "-m", "babelscribe", str(clips / f"{first}.wav"), "-l", "th", "-m", "tiny",
                    "--text-model", name, "--flavor", "cpu", "-f", "txt,json", "-o", str(out)], check=True)
    text = Path(f"{out}.txt").read_text(encoding="utf-8")
    meta = json.loads(Path(f"{out}.json").read_text(encoding="utf-8"))["meta"]
    print("reference:", refs[first], "\nhybrid:   ", text.strip())
    check(meta.get("text_model") == name and has_thai(text), "the command converted the fine-tune and wrote Thai text")

    work = models.MODELS / f"_{name}"
    check(download.sha256_of(work / "convert-h5-to-ggml.orig.py") == models.CONVERTER_SHA256, "the pinned converter ran")
    check(".float()" in (work / "convert-h5-to-ggml.py").read_text(encoding="utf-8"), "with the float32 line patched in")
    mel = work / "openai-whisper" / "whisper" / "assets" / "mel_filters.npz"
    check(download.sha256_of(mel) == models.MEL_FILTERS_SHA256, "with the pinned filter table")
    check(not (work / "openai-whisper" / ".git").exists(), "nothing was cloned")
    records = list((work / "hf" / ".cache").rglob("*.metadata"))       # huggingface_hub: line 1 is the commit
    commits = {r.read_text(encoding="utf-8").splitlines()[0] for r in records}
    check(bool(records) and commits == {ft["revision"]}, f"the weights are of commit {ft['revision']} (found {commits})")
    size = model.stat().st_size / 1e9
    check(0.8 < size < 2.2, f"the model was quantized to q8_0 ({size:.2f} GB; unquantized would be about 3 GB)")
    check(not list(models.MODELS.glob("*.part")), "no unfinished file is left")

    binary = backend.find_binary(flavor="cpu")
    check(api._quantizer(binary).is_file(), "whisper-quantize ships next to whisper-cli")
    scores = []
    for key in sorted(refs):
        segs = transcribe.run(binary, model, clips / f"{key}.wav", ft["lang"], 0, ft.get("beam"))
        said = " ".join(s["text"] for s in segs)
        scores.append(cer(plain(refs[key]), plain(said)))
        print(f"clip {key}: CER {scores[-1]:.3f}\n  reference: {refs[key]}\n  converted: {said}", flush=True)
        check(has_thai(said), f"clip {key}: the converted model writes Thai")
    mean = sum(scores) / len(scores)
    check(mean < MAX_CER, f"mean CER {mean:.3f} over {len(scores)} clips is below {MAX_CER}")

    summary = (f"### {name} converted and transcribing\n- commit `{ft['revision']}`, {size:.2f} GB q8_0\n"
               f"- CER on {len(scores)} FLEURS Thai clips: {', '.join(f'{s:.3f}' for s in scores)} (mean {mean:.3f})\n")
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024 ** 2          # Linux: kB
        summary += f"- largest child process: {peak:.1f} GB of memory\n"
    except ImportError:
        pass
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary)


if __name__ == "__main__":
    main()
