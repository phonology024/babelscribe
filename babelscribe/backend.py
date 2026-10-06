"""Find or fetch a whisper.cpp `whisper-cli` build for this machine and list its GPU devices.

Search order: --bin / BABELSCRIBE_WHISPER_BIN -> cached download -> `whisper-cli` on PATH -> download a prebuilt
release asset for this OS (Vulkan on Windows/Linux = AMD + NVIDIA + Intel, Metal on macOS, CPU fallback)."""
from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

CACHE = Path(os.environ.get("BABELSCRIBE_HOME", Path.home() / ".babelscribe"))
# Prebuilt binaries are produced by .github/workflows/build-binaries.yml and attached to a GitHub release.
RELEASES = os.environ.get("BABELSCRIBE_RELEASES", "https://github.com/phonology024/babelscribe/releases/latest/download")
EXE = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"


def asset_name(flavor: str | None = None) -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    flavor = flavor or ("metal" if system == "macos" else "vulkan")
    return f"whisper-cli-{system}-{arch}-{flavor}.zip"


def find_binary(explicit: str | None = None, flavor: str | None = None, download: bool = True) -> Path:
    for cand in (explicit, os.environ.get("BABELSCRIBE_WHISPER_BIN")):
        if cand and Path(cand).is_file():
            return Path(cand)
    cached = next(iter(sorted((CACHE / "bin").rglob(EXE))), None) if (CACHE / "bin").exists() else None
    if cached:
        return cached
    on_path = shutil.which("whisper-cli")
    if on_path:
        return Path(on_path)
    if not download:
        raise FileNotFoundError("whisper-cli not found; pass --bin or allow download")
    return fetch_binary(flavor)


def fetch_binary(flavor: str | None = None) -> Path:
    name = asset_name(flavor)
    dest = CACHE / "bin" / name[:-4]
    print(f"downloading {name} ...")
    data = urllib.request.urlopen(f"{RELEASES}/{name}").read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(dest)
    exe = next(dest.rglob(EXE))
    if os.name != "nt":
        exe.chmod(0o755)
    return exe


def probe_or_refetch(binary: Path, model: Path, flavor: str | None = None) -> tuple[Path, list[dict]]:
    """Probe devices; a cached binary that crashes with 'illegal instruction' is deleted and downloaded again once."""
    try:
        return binary, probe_devices(binary, model)
    except IllegalInstruction:
        cache = (CACHE / "bin").resolve()
        if cache not in binary.resolve().parents:
            raise SystemExit(f"{binary} crashed with 'illegal instruction': it was built for a newer CPU than this one.")
        shutil.rmtree(binary.parent)
        print("cached whisper-cli does not run on this CPU; downloading the current build ...")
        binary = fetch_binary(flavor)
        try:
            return binary, probe_devices(binary, model)
        except IllegalInstruction:
            raise SystemExit("the prebuilt whisper-cli does not run on this CPU; build whisper.cpp yourself and pass --bin.")


def devices(binary: Path) -> list[dict]:
    """Ask whisper.cpp which GPUs it can see (it prints them while loading a model)."""
    out = subprocess.run([str(binary), "--help"], capture_output=True, text=True, errors="replace")
    text = out.stdout + out.stderr
    found = []
    for m in re.finditer(r"ggml_(vulkan|cuda|metal): *(\d+) = ([^|\n]+)", text):
        found.append({"backend": m.group(1), "id": int(m.group(2)), "name": m.group(3).strip()})
    return found


class IllegalInstruction(RuntimeError):
    """The binary was compiled for CPU features this machine lacks (e.g. an old AVX-512 build)."""


def probe_devices(binary: Path, model: Path) -> list[dict]:
    """Load a model on an empty clip to see the GPU list and which device whisper.cpp picks."""
    import tempfile, wave
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "s.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0" * 16000)
        # no -np: static builds route the GPU list through the same logger -np silences
        out = subprocess.run([str(binary), "-m", str(model), "-f", str(wav)], capture_output=True, text=True, errors="replace")
    if out.returncode in (0xC000001D, -4, 132):   # Windows STATUS_ILLEGAL_INSTRUCTION / SIGILL
        raise IllegalInstruction(str(binary))
    text = out.stdout + out.stderr
    found = [{"backend": m.group(1), "id": int(m.group(2)), "name": m.group(3).strip(), "detail": m.group(4).strip()}
             for m in re.finditer(r"ggml_(vulkan|cuda|metal): *(\d+) = ([^|\n]+)\|?([^\n]*)", text)]
    if not found and "Metal" in text:
        found.append({"backend": "metal", "id": 0, "name": "Apple GPU", "detail": ""})
    return found or [{"backend": "cpu", "id": 0, "name": platform.processor() or "CPU", "detail": ""}]


def pick_device(found: list[dict]) -> int:
    """Prefer a discrete GPU: NVIDIA/AMD over integrated Intel/AMD APU (uma: 1)."""
    gpus = [d for d in found if d["backend"] != "cpu"]
    if not gpus:
        return 0
    discrete = [d for d in gpus if "uma: 0" in d.get("detail", "")] or gpus
    return discrete[0]["id"]


if __name__ == "__main__":
    print(json.dumps({"asset": asset_name(), "binary": str(find_binary(download=False))}, indent=1))
