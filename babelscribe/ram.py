"""How much memory this computer has free, and which Whisper model fits it.

Detection uses only what the operating system offers (no new dependency): GlobalMemoryStatusEx on Windows,
/proc/meminfo (and the container limit, when there is one) on Linux, sysctl and vm_stat on macOS. When anything about
it fails, detect() returns None and every caller behaves as if this module did not exist.

The numbers a model needs are measured, not guessed: models.RAM_MB, with how they were measured in docs/memory.md."""
from __future__ import annotations

import ctypes
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import models

MB = 1024 * 1024
# Kept free on top of the model: the operating system, the audio, ffmpeg and the program itself.
MARGIN_MB = 512
# whisper-cli keeps the whole recording (and what it works out from it) in memory: measured about 10 to 11 MB for every
# minute of audio beyond the 2 minute clip the table was measured on (tiny on the CPU, turbo on Vulkan, 2 vs 30 minutes).
LENGTH_MB_PER_MIN = 11
MEASURED_MINUTES = 2
# What a smaller model than the default can be: best first. (medium needs more than turbo, so it only matters when the
# default was changed.)
SMALLER = ("medium", "small", "base", "tiny")


def gb(mb: float) -> str:
    return f"{mb / 1024:.1f} GB"


# ---------------------------------------------------------------------------------------------------- detection

def parse_meminfo(text: str) -> dict | None:
    """/proc/meminfo -> {"total_mb", "available_mb"}. MemAvailable exists since Linux 3.14; older kernels get an estimate."""
    kb = {m.group(1): int(m.group(2)) for m in re.finditer(r"^(\w+):\s+(\d+)\s*kB", text, re.M)}
    if "MemTotal" not in kb:
        return None
    avail = kb.get("MemAvailable")
    if avail is None:
        avail = kb.get("MemFree", 0) + kb.get("Buffers", 0) + kb.get("Cached", 0)
    return {"total_mb": kb["MemTotal"] // 1024, "available_mb": min(avail, kb["MemTotal"]) // 1024}


def parse_vm_stat(text: str, total_bytes: int) -> dict | None:
    """macOS `vm_stat` + hw.memsize -> {"total_mb", "available_mb"}: free, inactive and speculative pages can be reused."""
    size = re.search(r"page size of (\d+) bytes", text)
    if not size or total_bytes <= 0:
        return None
    pages = {m.group(1).lower(): int(m.group(2)) for m in re.finditer(r"^Pages ([\w -]+?):\s+(\d+)\.", text, re.M)}
    if "free" not in pages:
        return None
    reusable = pages["free"] + pages.get("inactive", 0) + pages.get("speculative", 0)
    return {"total_mb": total_bytes // MB, "available_mb": min(reusable * int(size.group(1)), total_bytes) // MB}


def container_limit_mb(read: Callable[[str], str | None]) -> int | None:
    """Room left under a Docker/cgroup memory limit, or None when there is no limit (or it cannot be read)."""
    def number(path: str) -> int | None:
        text = read(path)
        return int(text.strip()) if text and text.strip().isdigit() else None   # cgroup v2 says "max" for no limit
    pairs = (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),                  # cgroup v2
             ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"))  # v1
    for limit_path, used_path in pairs:
        limit, used = number(limit_path), number(used_path)
        if limit is not None and used is not None and limit < 2**60:     # v1 reports ~2**63 for "no limit"
            return max(0, (limit - used) // MB)
    return None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _windows() -> dict | None:
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended", ctypes.c_ulonglong)]
    s = Status()
    s.length = ctypes.sizeof(s)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):      # type: ignore[attr-defined]
        return None
    return {"total_mb": s.total // MB, "available_mb": s.avail // MB}


def _linux(read: Callable[[str], str | None] = _read) -> dict | None:
    text = read("/proc/meminfo")
    info = parse_meminfo(text) if text else None
    if info is None:
        return None
    room = container_limit_mb(read)
    if room is not None:
        info = {"total_mb": info["total_mb"], "available_mb": min(info["available_mb"], room)}
    return info


def _macos() -> dict | None:
    def out(*cmd: str) -> str:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout
    return parse_vm_stat(out("vm_stat"), int(out("sysctl", "-n", "hw.memsize").strip()))


def detect() -> dict | None:
    """{"total_mb": ..., "available_mb": ...} for this computer, or None when it cannot be found out."""
    try:
        if sys.platform == "win32":
            info = _windows()
        elif sys.platform == "darwin":
            info = _macos()
        elif sys.platform.startswith("linux"):
            info = _linux()
        else:
            return None
    except Exception:         # a missing tool, a locked-down machine, a changed output: carry on as if unknown
        return None
    if not info or info["total_mb"] <= 0 or info["available_mb"] < 0:
        return None
    return info


# ---------------------------------------------------------------------------------------------------- the rule

def extra_mb(minutes: float | None) -> int:
    """What a recording longer than the measured 2 minutes adds."""
    return int(max(0.0, (minutes or 0.0) - MEASURED_MINUTES) * LENGTH_MB_PER_MIN + 0.999)


def need_mb(*names: str, minutes: float | None = None) -> int:
    """Peak RAM (CPU build) for a run that uses these models one after the other, a recording of this many minutes
    (None: not known, taken as short), plus the margin."""
    return max(models.RAM_MB[models.resolve(n)[0]]["cpu"] for n in names) + MARGIN_MB + extra_mb(minutes)


def fits(name: str, ram: dict, minutes: float | None = None) -> bool:
    return need_mb(name, minutes=minutes) <= ram["available_mb"]


def best_fit(ram: dict, candidates=SMALLER, minutes: float | None = None) -> str | None:
    return next((n for n in candidates if fits(n, ram, minutes)), None)


def media_minutes(path) -> float | None:
    """How long a recording is, from ffmpeg's own header line; None when that cannot be read (then nothing is added)."""
    try:
        from . import transcribe
        out = subprocess.run([transcribe.ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                             errors="replace", timeout=15, check=False).stderr
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
        return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) / 60 if m else None
    except (Exception, SystemExit):
        return None


def _for(minutes: float | None) -> str:
    return f" for a {minutes:.0f} minute recording" if minutes and minutes > 30 else ""


def warning(name: str, ram: dict | None, minutes: float | None = None) -> str | None:
    """One plain line when `name` is too big for the free memory, else None. Never changes anything."""
    if not ram:
        return None
    name = models.resolve(name)[0]
    if fits(name, ram, minutes):
        return None
    alt = best_fit(ram, [n for n in SMALLER if models.RAM_MB[n]["cpu"] < models.RAM_MB[name]["cpu"]], minutes)
    gpu = models.RAM_MB[name]["gpu"] + MARGIN_MB + extra_mb(minutes)
    return (f"{name} needs about {gb(need_mb(name, minutes=minutes))} of free memory{_for(minutes)} and this computer has "
            f"{gb(ram['available_mb'])} free "
            f"({gb(ram['total_mb'])} in all): it may run very slowly or stop"
            + (f" (on a graphics card with its own memory, about {gb(gpu)})" if gpu <= ram["available_mb"] else "")
            + (f". A smaller model that fits: -m {alt}." if alt else ". Close other programs and try again."))


def choose_default(default: str, ram: dict | None, minutes: float | None = None) -> tuple[str, str | None]:
    """The model to use when nobody named one, and the one line to say when it is not the default."""
    if not ram or fits(default, ram, minutes):
        return default, None
    pick = best_fit(ram, [n for n in SMALLER if models.RAM_MB[n]["cpu"] < models.RAM_MB[models.resolve(default)[0]]["cpu"]],
                    minutes)
    if pick is None:
        pick = "tiny"
        tail = f"even tiny needs about {gb(need_mb('tiny', minutes=minutes))}; close other programs"
    else:
        tail = "it is less accurate, most of all for Thai and other languages than English"
    return pick, (f"low memory: {gb(ram['available_mb'])} free, {default} needs about {gb(need_mb(default, minutes=minutes))}"
                  f"{_for(minutes)}; using {pick} "
                  f"instead ({tail}). -m {default} keeps it.")


def report(ram: dict | None) -> dict:
    """What `babelscribe models --json` prints for the desktop app: every model, whether it fits, and the warning."""
    default = "turbo"
    pick, say = choose_default(default, ram)
    rows = []
    for name in list(models.GENERAL) + list(models.FINETUNES):
        r = models.RAM_MB[name]
        rows.append({"name": name, "kind": "general" if name in models.GENERAL else "finetune",
                     "ram_mb": need_mb(name), "gpu_ram_mb": r["gpu"] + MARGIN_MB,
                     "fits": None if not ram else fits(name, ram), "warning": warning(name, ram)})
    return {"ram": ram, "margin_mb": MARGIN_MB, "default": default, "default_used": pick, "default_note": say,
            "accurate": {**models.ACCURATE, "*": "large-v3"}, "models": rows}
