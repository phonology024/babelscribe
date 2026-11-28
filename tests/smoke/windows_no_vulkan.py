"""Windows without vulkan-1.dll (a virtual machine, the basic display driver, some server installs), for real: the real
whisper-cli builds, the real "DLL not found" exit, real transcriptions. CI's Windows machines are such computers.

  python tests/smoke/windows_no_vulkan.py jfk.wav

On a computer that has the library there is nothing to test, and the script fails: it must not pass without testing."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from babelscribe import backend

PHRASE = "ask not what your country can do for you"


def check(ok: bool, what: str, why: str = "") -> None:
    print(("ok    " if ok else "FAIL  ") + what + ("" if ok else f"\n{why[-2000:]}"), flush=True)
    if not ok:
        raise SystemExit(f"failed: {what}")


def run(home: Path, audio: Path, out: Path, *args: str) -> tuple[int, str]:
    env = {**os.environ, "BABELSCRIBE_HOME": str(home), "PYTHONUTF8": "1"}
    env.pop("BABELSCRIBE_WHISPER_BIN", None)
    env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if not (Path(p) / backend.EXE).is_file())
    # the time limit also catches a message box that waits for a click nobody can give
    p = subprocess.run([sys.executable, "-m", "babelscribe", str(audio), "-m", "tiny", "-l", "en", "-f", "txt", "-o",
                        str(out), *args], env=env, capture_output=True, text=True, errors="replace", timeout=600)
    return p.returncode, p.stdout + p.stderr


def builds(home: Path) -> list[str]:
    folder = home / "bin"
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.exists() else []


def said_it(out: Path) -> bool:
    text = Path(f"{out}.txt")
    return text.is_file() and PHRASE in " ".join(text.read_text(encoding="utf-8").lower().replace(",", " ").split())


def main() -> None:
    audio = Path(sys.argv[1]).resolve()
    check(sys.platform == "win32" and backend.vulkan_loader_missing(), "this is a Windows computer without vulkan-1.dll")
    cpu, vulkan = "whisper-cli-windows-x64-cpu", "whisper-cli-windows-x64-vulkan"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)

        home = tmp / "first run"
        code, said = run(home, audio, tmp / "one")
        check(code == 0 and said_it(tmp / "one"), "a first run transcribes", said)
        check(builds(home) == [cpu] and said.count("no Vulkan library (vulkan-1.dll)") == 1,
              "with the CPU build, and says so once", f"{builds(home)}\n{said}")

        home = tmp / "had the gpu build"
        code, said = run(home, audio, tmp / "two", "--flavor", "vulkan")
        check(code != 0 and "vulkan-1.dll is not installed" in said and "--flavor cpu" in said and "Traceback" not in said,
              "--flavor vulkan ends with a plain message", f"exit {code}\n{said}")
        check(builds(home) == [vulkan], "and the build asked for is kept", str(builds(home)))

        code, said = run(home, audio, tmp / "three")                       # only the Vulkan build is cached now
        check(code == 0 and said_it(tmp / "three"), "a plain run then still transcribes", said)
        check(builds(home) == [cpu] and said.count("no Vulkan library (vulkan-1.dll)") == 1,
              "it replaced the build that cannot start with the CPU build", f"{builds(home)}\n{said}")

        code, said = run(home, audio, tmp / "four")
        check(code == 0 and said_it(tmp / "four") and "no Vulkan library" not in said and "downloading" not in said,
              "the next run just works, with nothing to say or fetch", said)
    print("Windows without Vulkan: every check passed")


if __name__ == "__main__":
    main()
