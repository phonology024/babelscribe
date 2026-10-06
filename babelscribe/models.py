"""Model registry + download.

General models are the official whisper.cpp ggml files (99 languages). Language fine-tunes are listed by their
Hugging Face repo and converted on the user's machine (we never redistribute converted weights — each fine-tune
keeps its own licence). Fine-tunes often lose timestamp prediction, so they are used for TEXT and a general model
gives the TIMING (see align.py)."""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from .backend import CACHE

GGML = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
GENERAL = {   # name -> size (approx) ; 'turbo' is the best speed/quality default
    "tiny": "75 MB", "base": "142 MB", "small": "466 MB", "medium": "1.5 GB",
    "large-v3": "3.1 GB", "large-v3-turbo": "1.6 GB",
}
ALIASES = {"turbo": "large-v3-turbo", "large": "large-v3"}
# Community fine-tunes: add a line to support a new language better. 'beam' = needs beam search (greedy loops).
FINETUNES = {
    "thai-thonburian": {"repo": "biodatlab/whisper-th-large-v3-combined", "lang": "th", "beam": 5, "timestamps": False,
                        "note": "Thonburian Whisper (Thai) — strong Thai spelling; pair with turbo for timing"},
    "thai-pathumma": {"repo": "nectec/Pathumma-whisper-th-large-v3", "lang": "th", "beam": 5, "timestamps": False,
                      "note": "Pathumma Whisper by NECTEC (Thai) — lowest Thai CER on FLEURS"},
    "hindi-vasista": {"repo": "vasista22/whisper-hindi-large-v2", "lang": "hi", "beam": 5, "timestamps": False,
                      "note": "Hindi fine-tune of large-v2 (Speech Lab, IIT Madras) — halves Hindi WER on FLEURS"},
}
# --accurate: per language, the model that scored best on FLEURS (bench/fleurs.py). Languages not listed use large-v3
# with beam search, which beat every public fine-tune we tried for vi / ar.
ACCURATE = {"th": "thai-pathumma", "hi": "hindi-vasista"}
MODELS = Path(os.environ.get("BABELSCRIBE_MODELS", CACHE / "models"))


def resolve(name: str) -> tuple[str, dict | None]:
    name = ALIASES.get(name, name)
    if name in GENERAL:
        return name, None
    if name in FINETUNES:
        return name, FINETUNES[name]
    raise SystemExit(f"unknown model '{name}'. General: {', '.join(GENERAL)}; fine-tunes: {', '.join(FINETUNES)}")


def path_for(name: str) -> Path:
    name, ft = resolve(name)
    return MODELS / (f"ggml-{name}-q8_0.bin" if ft else f"ggml-{name}.bin")


def ensure(name: str, quantizer: Path | None = None) -> Path:
    name, ft = resolve(name)
    p = path_for(name)
    if p.exists():
        return p
    MODELS.mkdir(parents=True, exist_ok=True)
    if not ft:
        print(f"downloading model {name} ({GENERAL[name]}) ...")
        tmp = p.with_suffix(".part")
        urllib.request.urlretrieve(GGML.format(name=name), tmp)
        tmp.replace(p)
        return p
    return convert_finetune(name, ft, p, quantizer)


def convert_finetune(name: str, ft: dict, out: Path, quantizer: Path | None) -> Path:
    """HF transformers checkpoint -> ggml (whisper.cpp convert-h5-to-ggml.py) -> q8_0. Needs: pip install babelscribe[finetune]."""
    try:
        import torch, transformers  # noqa: F401
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit("fine-tune conversion needs extras: pip install \"babelscribe[finetune]\"")
    work = MODELS / f"_{name}"
    work.mkdir(parents=True, exist_ok=True)
    hf = snapshot_download(ft["repo"], local_dir=work / "hf")
    oa = work / "openai-whisper"
    if not oa.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", "https://github.com/openai/whisper.git", str(oa)], check=True, stdout=sys.stderr)
    script = work / "convert-h5-to-ggml.py"
    if not script.exists():
        urllib.request.urlretrieve("https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/models/convert-h5-to-ggml.py", script)
    # some fine-tunes ship bf16 weights, which the converter cannot export -> load them as float32
    src = script.read_text(encoding="utf-8").replace("WhisperForConditionalGeneration.from_pretrained(dir_model)\n",
                                                     "WhisperForConditionalGeneration.from_pretrained(dir_model).float()\n")
    script.write_text(src, encoding="utf-8")
    subprocess.run([sys.executable, str(script), hf, str(oa), str(work)], check=True, stdout=sys.stderr)
    f32 = work / "ggml-model.bin"
    if quantizer and quantizer.exists():
        subprocess.run([str(quantizer), str(f32), str(out), "q8_0"], check=True, stdout=sys.stderr)
        f32.unlink()
    else:
        f32.replace(out)
    return out
