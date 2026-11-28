"""Find or fetch a whisper.cpp `whisper-cli` build for this machine and list its GPU devices.

Search order: --bin / BABELSCRIBE_WHISPER_BIN -> cached download -> `whisper-cli` on PATH -> download a prebuilt
release asset for this OS (Vulkan on Windows/Linux = AMD + NVIDIA + Intel, Metal on macOS, CPU fallback)."""
from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from . import download

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
# A build published after BINARY_TAG was pinned stays on the release that first carried it: moving BINARY_TAG
# would change the whisper-cli every other platform runs. name -> (release tag, sha256 from that release's SHA256SUMS)
LATER = {
    "whisper-cli-macos-x64-cpu.zip": ("v0.5.0", "ee42b85c95f8fa31899f0b3db1c87eb313e03765d05bd452ad781d845f4a9da1"),
}


def release_url(tag: str) -> str:
    return f"https://github.com/phonology024/babelscribe/releases/download/{tag}"


DEFAULT_RELEASES = release_url(BINARY_TAG)
RELEASES = os.environ.get("BABELSCRIBE_RELEASES", DEFAULT_RELEASES)
EXE = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"
RECEIPT = "babelscribe-download.json"   # written next to a downloaded binary: where it came from, what it hashed to


# Exactly the assets .github/workflows/build-binaries.yml produces and attaches to a release. asset_name used to
# compose a name from the host OS/arch alone, so Linux arm64 (Docker on Apple Silicon, Raspberry Pi, ARM servers)
# and Intel macOS asked for a file that was never built and got a bare "HTTP Error 404" with no explanation.
ASSETS = {
    ("windows", "x64", "vulkan"), ("windows", "x64", "cpu"),
    ("linux", "x64", "vulkan"), ("linux", "x64", "cuda"), ("linux", "x64", "cpu"),
    ("macos", "arm64", "metal"), ("macos", "x64", "cpu"),
}


VULKAN_LOADER = {"Linux": "libvulkan.so.1", "Windows": "vulkan-1.dll"}


def vulkan_loader_missing() -> bool:
    """Is the Vulkan loader not there? The Vulkan build of whisper-cli cannot even start without it, GPU or no GPU.
    Linux: package libvulkan1. Windows: it comes with graphics drivers, so a virtual machine, the basic display driver
    and some server installs have none. macOS uses Metal."""
    library = VULKAN_LOADER.get(platform.system())
    if not library:
        return False
    import ctypes
    try:
        ctypes.CDLL(library)                      # loading it starts no driver: a few milliseconds
    except OSError:
        return True
    return False


_NO_VULKAN = ("babelscribe: this computer has no Vulkan library ({}), which the GPU build of whisper-cli needs, "
              "so the CPU build is used (slower). For the GPU: {}, then run babelscribe again.")
_GET_VULKAN = {"Linux": "install libvulkan1 (sudo apt install libvulkan1)", "Windows": "install or update the graphics driver"}


def no_vulkan_notice() -> str:
    system = platform.system()
    name = "libvulkan1" if system == "Linux" else VULKAN_LOADER.get(system, "Vulkan")
    return _NO_VULKAN.format(name, _GET_VULKAN.get(system, "install Vulkan"))


def asset_name(flavor: str | None = None) -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    # Apple Silicon: Metal. Intel Macs: CPU only (Accelerate), the only build for them. Windows and Linux: Vulkan,
    # except without the Vulkan library, where only the CPU build can run. A flavour asked for is kept.
    if flavor is None and system in ("linux", "windows") and vulkan_loader_missing():
        flavor = "cpu"
        print(no_vulkan_notice(), file=sys.stderr)
    flavor = flavor or (("metal" if arch == "arm64" else "cpu") if system == "macos" else "vulkan")
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


def _cached_order(flavor: str | None) -> list[Path]:
    """The whisper-cli builds in the cache, best first. With a flavour asked for, only builds of that flavour (another
    one is no answer to it: "--flavor cpu" must not run the cached Vulkan build). Else a GPU build before a CPU build:
    one run with --flavor cpu, or a CPU build kept from a time the GPU one could not start, must not make the CPU the
    choice from then on. Only where the Vulkan build cannot start (no Vulkan library) do the names decide: CPU first."""
    found = sorted((CACHE / "bin").rglob(EXE)) if (CACHE / "bin").exists() else []
    if flavor:
        return [p for p in found if p.relative_to(CACHE / "bin").parts[0].endswith("-" + flavor)]
    if len(found) > 1 and vulkan_loader_missing():                 # one build: nothing to choose, nothing to look up
        return found
    rank = {"vulkan": 0, "metal": 0, "cuda": 1, "cpu": 3}           # a folder of another name: after the GPU builds
    return sorted(found, key=lambda p: rank.get(p.relative_to(CACHE / "bin").parts[0].rsplit("-", 1)[-1], 2))   # stable


def find_binary(explicit: str | None = None, flavor: str | None = None, download: bool = True) -> Path:
    for cand in (explicit, os.environ.get("BABELSCRIBE_WHISPER_BIN")):
        if cand and Path(cand).is_file():
            return Path(cand)
    cached = next(iter(_cached_order(flavor)), None)
    if cached:
        if flavor is None and download and _stands_in_for_the_gpu_build(cached):
            try:
                return fetch_binary()                     # the Vulkan build, which can run here (now)
            except (SystemExit, OSError) as e:
                print(f"babelscribe: the GPU build of whisper-cli could not be installed, so the CPU build is used this "
                      f"time ({e}). --flavor cpu uses it without trying.", file=sys.stderr)
        return cached
    on_path = shutil.which("whisper-cli")
    if on_path:
        return Path(on_path)
    if not download:
        raise FileNotFoundError("whisper-cli not found; pass --bin or allow download")
    return fetch_binary(flavor)


def _stands_in_for_the_gpu_build(binary: Path) -> bool:
    """Is this a CPU build that was only fetched for the moment (asked for with --flavor cpu, or because the Vulkan
    library was missing), on a computer whose own build is the Vulkan one and can start now? Without this, a computer
    that only ever got the CPU build would keep it after its driver was installed. A build of an older babelscribe does
    not say, and stays."""
    if platform.system() not in VULKAN_LOADER:
        return False
    root = CACHE / "bin"
    if root not in binary.parents:
        return False
    try:
        receipt = json.loads((root / binary.relative_to(root).parts[0] / RECEIPT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(receipt.get("stand_in")) and not vulkan_loader_missing()


def _skip_verify() -> bool:
    return os.environ.get("BABELSCRIBE_SKIP_VERIFY", "").strip().lower() in ("1", "true", "yes")


def _rmtree(path: Path) -> None:
    """Delete a folder, read-only files in it included (git marks its own so, and Windows then refuses)."""
    def writable(fn, name, _):
        os.chmod(name, os.stat(name).st_mode | stat.S_IWRITE)
        fn(name)
    if path.exists():
        shutil.rmtree(path, **{"onexc" if sys.version_info >= (3, 12) else "onerror": writable})


def _move_into_place(src: Path, dest: Path) -> None:
    """Rename a finished folder to its real name. Windows refuses while a virus scanner still reads a new file in it,
    which passes in a moment."""
    for attempt in range(20):
        try:
            os.replace(src, dest)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.5)


def _installed_by(dest: Path, want: str | None) -> Path | None:
    """The whisper-cli in `dest` when it is a complete install of the zip with sha256 `want`."""
    try:
        receipt = json.loads((dest / RECEIPT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return next(dest.rglob(EXE), None) if want and receipt.get("sha256") == want else None


def fetch_binary(flavor: str | None = None) -> Path:
    """Download the prebuilt whisper-cli for this machine, check its sha256, then unpack it into the cache.

    A dropped download continues where it stopped (download.py). Nothing is unpacked unless the zip is the one this
    version was tested with, and the cache only ever gets a complete install: it is unpacked next to the cache and
    renamed into it in one step, so a run that is killed half way leaves nothing that looks installed.
    A mirror (BABELSCRIBE_RELEASES) is held to the same digests; BABELSCRIBE_SKIP_VERIFY=1 turns the check off
    for a mirror that carries its own builds."""
    name = asset_name(flavor)
    dest = CACHE / "bin" / name[:-4]
    tag, later = (LATER[name][0], LATER[name][1]) if name in LATER else (BINARY_TAG, None)
    base = release_url(tag) if RELEASES == DEFAULT_RELEASES else RELEASES
    want = None if _skip_verify() else (later or SHA256.get(name))
    if want is None and not _skip_verify():
        raise SystemExit(
            f"{name} is not one of the builds babelscribe publishes, so there is no checksum to verify it against.\n"
            f"If {RELEASES} is your own mirror with your own builds, set BABELSCRIBE_SKIP_VERIFY=1.")
    with download.lock(CACHE / "locks" / (name + ".lock"), name) as waited:
        ready = _installed_by(dest, want) if waited else None
        if ready:                                                  # the one we waited for installed it
            return ready
        # the digest is part of the name, so a part file is only ever continued with the very same build
        part = CACHE / "bin" / (f"{name}.{want[:12]}.part" if want else f"{name}.part")
        for old in (CACHE / "bin").glob(name + "*.part"):    # of another version: never continued, only in the way
            if old != part:
                with contextlib.suppress(OSError):
                    old.unlink()
        print(f"downloading {name} ...")
        try:
            got = download.fetch(f"{base}/{name}", part, want, name)
        except download.NotFound:
            raise SystemExit(f"{base}/{name} was not found (HTTP 404). Publish that file on the mirror, or build "
                             f"whisper.cpp for this machine and pass --bin PATH/whisper-cli.") from None
        except download.ChecksumMismatch as e:
            raise SystemExit(
                f"{name}: checksum mismatch, nothing was installed.\n"
                f"  expected sha256 {want}\n  downloaded      {e.got}\n"
                f"The download from {base} is damaged or is not the {tag} build. Try again; "
                f"if it keeps happening, build whisper.cpp yourself and pass --bin PATH/whisper-cli."
                + ("" if RELEASES == DEFAULT_RELEASES else
                   "\nA mirror with its own builds needs BABELSCRIBE_SKIP_VERIFY=1.")) from None
        return _unpack(part, dest, {"asset": name, "source": base,
                                    "tag": tag if RELEASES == DEFAULT_RELEASES else None,
                                    "sha256": got, "verified": bool(want),
                                    # a CPU build where Vulkan is this system's own: see _stands_in_for_the_gpu_build
                                    "stand_in": name.endswith("-cpu.zip") and platform.system() in VULKAN_LOADER})


def _unpack(part: Path, dest: Path, receipt: dict) -> Path:
    staging = CACHE / "unpacking" / dest.name             # not under bin/: nothing in here may be found and run
    try:
        _rmtree(staging)
        with zipfile.ZipFile(part) as z:
            z.extractall(staging)
        exe = next(staging.rglob(EXE), None)
        if exe is None:
            part.unlink()
            raise SystemExit(f"{receipt['asset']} from {receipt['source']} holds no {EXE}; nothing was installed.")
        if os.name != "nt":             # unzipping does not keep "executable": both programs of the build need it
            for program in (exe, exe.with_name("whisper-quantize")):
                if program.is_file():
                    program.chmod(0o755)
        files = {f.relative_to(staging).as_posix(): download.sha256_of(f)
                 for f in sorted(staging.rglob("*")) if f.is_file()}
        (staging / RECEIPT).write_text(json.dumps({**receipt, "files": files}, indent=1), encoding="utf-8")
        _rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _move_into_place(staging, dest)
    except zipfile.BadZipFile as e:
        part.unlink()
        raise SystemExit(f"{receipt['asset']} from {receipt['source']} is not a zip file ({e}); nothing was installed.") \
            from None
    except OSError as e:                                  # the checked zip is kept: the next run only unpacks it
        with contextlib.suppress(OSError):
            _rmtree(staging)
        raise SystemExit(f"could not install {receipt['asset']} into {dest} ({e.strerror or e}). The download is kept: "
                         f"free some disk space, or close a running babelscribe, and run it again.") from None
    with contextlib.suppress(OSError):                    # installed: a zip that cannot be deleted yet is no failure
        part.unlink()
    return next(dest.rglob(EXE))


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
               if not (root / n).is_file() or download.sha256_of(root / n) != h]
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
    except MissingLibrary as e:
        in_cache = (CACHE / "bin").resolve() in binary.resolve().parents
        vulkan = str(e).startswith(("libvulkan", "vulkan-1"))
        if not (vulkan and in_cache and flavor is None):          # your own build, or a flavour you asked for
            if str(e) == UNNAMED_DLL:
                raise SystemExit(f"{binary} cannot start: Windows could not find a DLL it needs (an antivirus may have "
                                 f"removed a file). Delete {binary.parent} to download it again, or use --flavor cpu.")
            how = _GET_VULKAN.get(platform.system(), "install Vulkan")
            raise SystemExit(f"{binary} cannot start: {e} is not installed on this computer"
                             + (f" ({how}, or use --flavor cpu)." if vulkan else "."))
        print(no_vulkan_notice(), file=sys.stderr)
        cpu = fetch_binary("cpu")                                 # first: if it fails, nothing has been removed
        _rmtree(binary.parent)                                    # the Vulkan build we cannot run
        try:
            return cpu, probe_devices(cpu, model)
        except MissingLibrary as again:
            raise SystemExit(f"{cpu} cannot start either: {again} is missing on this computer.") from None
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


# Windows' exit code for a program one of whose DLLs is not there (STATUS_DLL_NOT_FOUND); it prints nothing.
DLL_NOT_FOUND = (0xC0000135, 0xC0000135 - (1 << 32))
UNNAMED_DLL = "a DLL it needs"


@contextlib.contextmanager
def _no_error_boxes():
    """Windows: a program that cannot load a DLL may stop at a message box, which nobody sees behind the app or an AI
    app's server. With this it just ends with its exit code (a started program inherits the setting)."""
    if os.name != "nt":
        yield
        return
    import ctypes
    kernel32 = ctypes.windll.kernel32
    before = kernel32.SetErrorMode(0x0001)                 # SEM_FAILCRITICALERRORS
    kernel32.SetErrorMode(before | 0x0001)
    try:
        yield
    finally:
        kernel32.SetErrorMode(before)


def devices(binary: Path) -> list[dict]:
    """Ask whisper.cpp which GPUs it can see (it prints them while loading a model)."""
    with _no_error_boxes():
        out = subprocess.run([str(binary), "--help"], capture_output=True, text=True, errors="replace")
    text = out.stdout + out.stderr
    found = []
    for m in re.finditer(r"ggml_(vulkan|cuda|metal): *(\d+) = ([^|\n]+)\|?([^\n]*)", text):
        found.append({"backend": m.group(1), "id": int(m.group(2)), "name": m.group(3).strip(),
                      "detail": (m.group(4) or "").strip()})
    return found


class MissingLibrary(RuntimeError):
    """whisper-cli could not start because a shared library is not installed (the message names it)."""


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
        with _no_error_boxes():
            out = subprocess.run([str(binary), "-m", str(model), "-f", str(wav)], capture_output=True, text=True,
                                 errors="replace")
    if platform.system() == "Windows" and out.returncode in DLL_NOT_FOUND:
        raise MissingLibrary(VULKAN_LOADER["Windows"] if vulkan_loader_missing() else UNNAMED_DLL)
    if out.returncode in (0xC000001D, -4, 132):   # Windows STATUS_ILLEGAL_INSTRUCTION / SIGILL
        raise IllegalInstruction(str(binary))
    text = out.stdout + out.stderr
    gone = re.search(r"error while loading shared libraries: (\S+): cannot open shared object file", text)
    if gone:
        raise MissingLibrary(gone.group(1))
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
