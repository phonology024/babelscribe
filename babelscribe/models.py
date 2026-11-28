"""Model registry + download.

General models are the official whisper.cpp ggml files (99 languages). Language fine-tunes are listed by their
Hugging Face repo and converted on the user's machine (we never redistribute converted weights — each fine-tune
keeps its own licence). Fine-tunes often lose timestamp prediction, so they are used for TEXT and a general model
gives the TIMING (see align.py)."""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

from . import download
from .backend import CACHE

# The files of one fixed revision, so that a download can be checked and a half-done one safely continued.
GGML_REVISION = "5359861c739e955e79d9a303bcbc70fb988958b1"
GGML = "https://huggingface.co/ggerganov/whisper.cpp/resolve/{revision}/ggml-{name}.bin"
SHA256 = {    # of each file at GGML_REVISION; tests/test_download.py compares them with Hugging Face when there is a network
    "tiny": "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
    "base": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
    "small": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
    "medium": "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
    "large-v3": "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
    "large-v3-turbo": "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
}
GENERAL = {   # name -> size (approx) ; 'turbo' is the best speed/quality default
    "tiny": "75 MB", "base": "142 MB", "small": "466 MB", "medium": "1.5 GB",
    "large-v3": "3.1 GB", "large-v3-turbo": "1.6 GB",
}
ALIASES = {"turbo": "large-v3-turbo", "large": "large-v3"}
# Community fine-tunes: add a line to support a new language better. 'beam' = needs beam search (greedy loops).
# 'revision' is the one commit of the repository that is downloaded: some weights are pickle files, which can run code
# when loaded, so a later change to a repository must not reach anyone by itself.
FINETUNES = {
    "thai-thonburian": {
        "repo": "biodatlab/whisper-th-large-v3-combined", "revision": "ba7197f618400e41b4826c18b2f48e0bc45ed3ca",
        "lang": "th", "beam": 5, "timestamps": False,
        "note": "Thonburian Whisper (Thai) — strong Thai spelling; pair with turbo for timing"},
    "thai-pathumma": {
        "repo": "nectec/Pathumma-whisper-th-large-v3", "revision": "6d5e4f2fc7fc2c05447b3626dd346b1793682eb9",
        "lang": "th", "beam": 5, "timestamps": False,
        "note": "Pathumma Whisper by NECTEC (Thai) — lowest Thai CER on FLEURS"},
    "hindi-vasista": {
        "repo": "vasista22/whisper-hindi-large-v2", "revision": "f98540cee2b8cba5b3f7d1b123608dda0a5f5a95",
        "lang": "hi", "beam": 5, "timestamps": False,
        "note": "Hindi fine-tune of large-v2 (Speech Lab, IIT Madras) — halves Hindi WER on FLEURS"},
    "vietnamese-toantam": {
        "repo": "toantam1290/whisper-large-v3-vietnamese", "revision": "3d446d9dc7c7292a98262a825b6f25065a015e0c",
        "lang": "vi", "beam": 5, "timestamps": False,
        "note": "Vietnamese fine-tune of large-v3 by toantam1290 (Apache-2.0)"},
}
# --accurate: per language, the model that scored best on FLEURS (bench/fleurs.py). Languages not listed use large-v3
# with beam search, which beat every public fine-tune we tried for vi / ar.
ACCURATE = {"th": "thai-pathumma", "hi": "hindi-vasista"}
MODELS = Path(os.environ.get("BABELSCRIBE_MODELS", CACHE / "models"))
# Peak RAM in MB of one whisper-cli run on a 2 minute recording, measured (docs/memory.md says how): "cpu" = the CPU
# build, "gpu" = the Vulkan build, whose weights live in the card's own memory. A fine-tune is a large-v3-sized model
# stored as q8_0 (measured as large-v3 quantized to q8_0). Longer recordings need more: ram.LENGTH_MB_PER_MIN.
RAM_MB = {
    "tiny": {"cpu": 309, "gpu": 420}, "base": {"cpu": 418, "gpu": 534}, "small": {"cpu": 887, "gpu": 635},
    "medium": {"cpu": 2191, "gpu": 683}, "large-v3-turbo": {"cpu": 1939, "gpu": 670}, "large-v3": {"cpu": 4046, "gpu": 871},
    **{name: {"cpu": 2665, "gpu": 835} for name in FINETUNES},
}


# The converter is a script that is run, so it is one fixed file: whisper.cpp v1.9.4 (what whisper-cli is built from).
CONVERTER = ("https://raw.githubusercontent.com/ggml-org/whisper.cpp/927cfce34f31707e17f2bff35c349632fb9e2c3a/"
             "models/convert-h5-to-ggml.py")
CONVERTER_SHA256 = "9cc282dfcd9a24da03ffa1b4123b5508ee935e19e369c33520b1a73f89440094"
# The one file it reads from openai/whisper (tag v20250625).
MEL_FILTERS = ("https://raw.githubusercontent.com/openai/whisper/31243bad24cc746f07d4c8bfdd2d974872cb1803/"
               "whisper/assets/mel_filters.npz")
MEL_FILTERS_SHA256 = "7450ae70723a5ef9d341e3cee628c7cb0177f36ce42c44b7ed2bf3325f0f6d4c"
LOADS = "WhisperForConditionalGeneration.from_pretrained(dir_model)\n"      # the converter's line that is patched


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
    with download.lock(MODELS / (p.name + ".lock"), f"model {name}"):
        if p.exists():                       # another babelscribe finished it while we waited
            return p
        if not ft:
            return _download_model(name, p)
        return convert_finetune(name, ft, p, quantizer)


def _download_model(name: str, p: Path) -> Path:
    print(f"downloading model {name} ({GENERAL[name]}) ...")
    part = p.with_name(f"{p.stem}.{SHA256[name][:12]}.part")      # never continued with another version's bytes
    for old in (p.with_name(f"{p.stem}.part"), *p.parent.glob(f"{p.stem}.{'?' * 12}.part")):    # left by an older one
        if old != part:
            old.unlink(missing_ok=True)
    for revision in (GGML_REVISION, "main"):      # "main" only if the repository's history was rewritten: same checksum
        try:
            download.fetch(GGML.format(revision=revision, name=name), part, SHA256[name], f"model {name}")
        except download.NotFound:
            continue
        except download.ChecksumMismatch as e:
            raise SystemExit(f"model {name}: checksum mismatch, nothing was installed.\n"
                             f"  expected sha256 {SHA256[name]}\n  downloaded      {e.got}\n"
                             f"Run it again; if it keeps happening, something between this computer and "
                             f"huggingface.co is changing the file (a proxy or a sign-in page).") from None
        part.replace(p)
        return p
    raise SystemExit(f"model {name} was not found on huggingface.co (HTTP 404). Update babelscribe and run it again.")


def _pinned(url: str, dest: Path, sha256: str, what: str) -> None:
    """`dest` holds exactly the file with this sha256 afterwards; whatever else was there is replaced."""
    if dest.is_file() and download.sha256_of(dest) == sha256:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(f"{dest.name}.{sha256[:12]}.part")
    try:
        download.fetch(url, part, sha256, what)
    except download.NotFound:
        raise SystemExit(f"{what} was not found at {url} (HTTP 404). Update babelscribe and run it again.") from None
    except download.ChecksumMismatch as e:
        raise SystemExit(f"{what}: checksum mismatch, nothing was run.\n  expected sha256 {sha256}\n"
                         f"  downloaded      {e.got}\nRun it again; if it keeps happening, something between this "
                         f"computer and github.com is changing the file.") from None
    part.replace(dest)


def convert_finetune(name: str, ft: dict, out: Path, quantizer: Path | None) -> Path:
    """HF transformers checkpoint -> ggml (whisper.cpp convert-h5-to-ggml.py) -> q8_0. Needs: pip install babelscribe[finetune]."""
    try:
        import torch, transformers  # noqa: F401
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit("fine-tune conversion needs extras: pip install \"babelscribe[finetune]\"")
    work = MODELS / f"_{name}"
    work.mkdir(parents=True, exist_ok=True)
    hf = snapshot_download(ft["repo"], revision=ft["revision"], local_dir=work / "hf")
    oa = work / "openai-whisper"
    _pinned(MEL_FILTERS, oa / "whisper" / "assets" / "mel_filters.npz", MEL_FILTERS_SHA256, "the converter's filter table")
    original = work / "convert-h5-to-ggml.orig.py"
    _pinned(CONVERTER, original, CONVERTER_SHA256, "the model converter")
    # some fine-tunes ship bf16 weights, which the converter cannot export -> load them as float32
    script = work / "convert-h5-to-ggml.py"           # written again every time, from the checked file only
    script.write_bytes(original.read_bytes().replace(LOADS.encode(), LOADS.replace("\n", ".float()\n").encode()))
    subprocess.run([sys.executable, str(script), hf, str(oa), str(work)], check=True, stdout=sys.stderr)
    f32 = work / "ggml-model.bin"
    if quantizer and quantizer.exists():
        if os.name != "nt":      # a cache unpacked by an older babelscribe has it without the executable bit
            with contextlib.suppress(OSError):
                quantizer.chmod(quantizer.stat().st_mode | 0o111)
        # not straight into `out`: a model that exists under that name is taken to be complete
        unfinished = out.with_name(out.name + ".part")
        subprocess.run([str(quantizer), str(f32), str(unfinished), "q8_0"], check=True, stdout=sys.stderr)
        unfinished.replace(out)
        f32.unlink()
    else:
        f32.replace(out)
    return out
