"""Find or fetch a whisper.cpp `whisper-cli` build for this machine and list its GPU devices.

Search order: --bin / BABELSCRIBE_WHISPER_BIN -> cached download -> `whisper-cli` on PATH -> download a prebuilt
release asset for this OS (Vulkan on Windows/Linux = AMD + NVIDIA + Intel, Metal on macOS, CPU fallback)."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

CACHE = Path(os.environ.get("BABELSCRIBE_HOME", Path.home() / ".babelscribe"))
# Prebuilt binaries are produced by .github/workflows/build-binaries.yml and attached to a GitHub release.
# This version of babelscribe was tested with the binaries of exactly one release and downloads only those:
# "latest" would let the same babelscribe run a different whisper.cpp build next month, and a bad binary release
# would break every installed version at once.
BINARY_TAG = "v0.4.0"
# sha256 of each zip of BINARY_TAG. The download is checked against it before anything is unpacked or run.
# To move to newer binaries: change BINARY_TAG and copy the digests from that release's SHA256SUMS file;
# tests/test_binary_verify.py compares the two when there is a network.
SHA256 = {
    "whisper-cli-linux-x64-cpu.zip": "b060b82b996c879b8289012abd25cf1e6d124252bf4cd9c6779f3166f37aa6e2",
    "whisper-cli-linux-x64-cuda.zip": "cb54539a9b18aa0210fd6bcd2e58cf2b79872c1cc73fe98b0d9c3e40da2b83f0",
    "whisper-cli-linux-x64-vulkan.zip": "fa25c971837cc1c41c51a069862676a113f7f34857b5f4ab041294ce90cb3a18",
    "whisper-cli-macos-arm64-metal.zip": "a5ee85f644af0ebf8868d9fe9689cb12d7e91f0a5c01428a5363b4cdbf57b9a3",
    "whisper-cli-windows-x64-cpu.zip": "34743845679c1bc0cd30b87efcc95b3393fdd936a2252e0bfd466e7e02438121",
    "whisper-cli-windows-x64-vulkan.zip": "dba378fc25326203b57b41476ecc81c2ab5881bcd46b4b1b2a2e4a184eeeea25",
}
DEFAULT_RELEASES = f"https://github.com/phonology024/babelscribe/releases/download/{BINARY_TAG}"
RELEASES = os.environ.get("BABELSCRIBE_RELEASES", DEFAULT_RELEASES)
EXE = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"
RECEIPT = "babelscribe-download.json"   # written next to a downloaded binary: where it came from, what it hashed to


# Exactly the assets .github/workflows/build-binaries.yml produces and attaches to a release. asset_name used to
# compose a name from the host OS/arch alone, so Linux arm64 (Docker on Apple Silicon, Raspberry Pi, ARM servers)
# and Intel macOS asked for a file that was never built and got a bare "HTTP Error 404" with no explanation.
ASSETS = {
    ("windows", "x64", "vulkan"), ("windows", "x64", "cpu"),
    ("linux", "x64", "vulkan"), ("linux", "x64", "cuda"), ("linux", "x64", "cpu"),
    ("macos", "arm64", "metal"),
}


def asset_name(flavor: str | None = None) -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    flavor = flavor or ("metal" if system == "macos" else "vulkan")
    # A self-hosted mirror (BABELSCRIBE_RELEASES) may carry builds this project does not publish, so only the
    # default URL is checked against the table; a mirror is asked for the composed name as before.
    if RELEASES == DEFAULT_RELEASES and (system, arch, flavor) not in ASSETS:
        have = ", ".join(f"{s}-{a}-{f}" for s, a, f in sorted(ASSETS))
        raise SystemExit(
            f"no prebuilt whisper-cli for {system}-{arch}-{flavor}; available: {have}.\n"
            f"Build whisper.cpp for this machine and point babelscribe at it:\n"
            f"  git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp\n"
            f"  cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release -j\n"
            f"  babelscribe FILE --bin whisper.cpp/build/bin/whisper-cli")
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


def _skip_verify() -> bool:
    return os.environ.get("BABELSCRIBE_SKIP_VERIFY", "").strip().lower() in ("1", "true", "yes")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_binary(flavor: str | None = None) -> Path:
    """Download the prebuilt whisper-cli for this machine, check its sha256, then unpack it into the cache.

    Nothing is unpacked, and nothing stays in the cache, unless the zip is the one this version was tested with.
    A mirror (BABELSCRIBE_RELEASES) is held to the same digests; BABELSCRIBE_SKIP_VERIFY=1 turns the check off
    for a mirror that carries its own builds."""
    name = asset_name(flavor)
    dest = CACHE / "bin" / name[:-4]
    want = None if _skip_verify() else SHA256.get(name)
    if want is None and not _skip_verify():
        raise SystemExit(
            f"{name} is not one of the builds babelscribe publishes, so there is no checksum to verify it against.\n"
            f"If {RELEASES} is your own mirror with your own builds, set BABELSCRIBE_SKIP_VERIFY=1.")
    print(f"downloading {name} ...")
    try:
        resp = urllib.request.urlopen(f"{RELEASES}/{name}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        raise SystemExit(f"{RELEASES}/{name} was not found (HTTP 404). Publish that file on the mirror, or build "
                         f"whisper.cpp for this machine and pass --bin PATH/whisper-cli.")
    (CACHE / "bin").mkdir(parents=True, exist_ok=True)
    part = CACHE / "bin" / (name + ".part")
    digest = hashlib.sha256()
    try:
        with resp, open(part, "wb") as f:      # to disk, not memory: the CUDA build is 800 MB
            for block in iter(lambda: resp.read(1 << 20), b""):
                digest.update(block)
                f.write(block)
        got = digest.hexdigest()
        if want and got != want:
            raise SystemExit(
                f"{name}: checksum mismatch, nothing was installed.\n"
                f"  expected sha256 {want}\n  downloaded      {got}\n"
                f"The download from {RELEASES} was cut short or is not the {BINARY_TAG} build. Try again; "
                f"if it keeps happening, build whisper.cpp yourself and pass --bin PATH/whisper-cli."
                + ("" if RELEASES == DEFAULT_RELEASES else
                   "\nA mirror with its own builds needs BABELSCRIBE_SKIP_VERIFY=1."))
        if dest.exists():
            shutil.rmtree(dest)
        with zipfile.ZipFile(part) as z:
            z.extractall(dest)
    finally:
        part.unlink(missing_ok=True)
    exe = next(dest.rglob(EXE))
    if os.name != "nt":
        exe.chmod(0o755)
    files = {f.relative_to(dest).as_posix(): _sha256(f) for f in sorted(dest.rglob("*")) if f.is_file()}
    (dest / RECEIPT).write_text(json.dumps({
        "asset": name, "source": RELEASES, "tag": BINARY_TAG if RELEASES == DEFAULT_RELEASES else None,
        "sha256": got, "verified": bool(want), "files": files}, indent=1), encoding="utf-8")
    return exe


def binary_origin(binary: Path) -> str:
    """One line for `babelscribe doctor`: which release a whisper-cli came from and whether it is still intact."""
    cache = (CACHE / "bin").resolve()
    binary = binary.resolve()
    if cache not in binary.parents:
        return "your own build (not downloaded by babelscribe)"
    root = next(p for p in [binary.parent, *binary.parents] if p.parent == cache)
    try:
        receipt = json.loads((root / RECEIPT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (f"downloaded by an older babelscribe, release unknown; delete {root} to get the {BINARY_TAG} "
                f"build with a checksum")
    changed = [n for n, h in receipt.get("files", {}).items()
               if not (root / n).is_file() or _sha256(root / n) != h]
    where = receipt.get("tag") or f"mirror {receipt.get('source')}"
    if changed:
        return (f"{receipt.get('asset')} from {where}: CHANGED since download ({', '.join(changed)}); "
                f"delete {root} and run babelscribe again")
    checked = "checksum verified at download" if receipt.get("verified") else "checksum NOT verified (skip flag)"
    return f"{receipt.get('asset')} from {where}; {checked}; files unchanged since"


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
