"""Environment diagnostics for babelscribe doctor."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import backend, models


def directory_size(path: Path) -> int:
    """Return the total size of files below a directory, without following symlinks."""
    if not path.exists():
        return 0

    total = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def format_bytes(size: int) -> str:
    """Format bytes in a human-readable unit."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def collect_report() -> tuple[list[tuple[str, str]], str]:
    """Collect diagnostics without downloading binaries or models."""
    checks: list[tuple[str, str]] = []

    checks.append(("Python", f"{platform.python_version()} ({sys.executable})"))
    checks.append(("Operating system", f"{platform.system()} {platform.release()} ({platform.machine()})"))

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            result = subprocess.run(
                [ffmpeg, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            first_line = (result.stdout or result.stderr).splitlines()
            checks.append((
                "FFmpeg",
                f"OK: {first_line[0]}" if result.returncode == 0 and first_line else
                f"Found at {ffmpeg}, but version check failed (exit {result.returncode})",
            ))
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append(("FFmpeg", f"Found at {ffmpeg}, but could not run: {exc}"))
    else:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            checks.append(("FFmpeg", f"Bundled executable available: {ffmpeg}"))
        except (ImportError, OSError, RuntimeError) as exc:
            checks.append(("FFmpeg", f"Not found on PATH or through imageio-ffmpeg ({exc})"))

    binary = None
    try:
        binary = backend.find_binary(download=False)
        result = subprocess.run(
            [str(binary), "--help"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode == 0 or result.stdout or result.stderr:
            checks.append(("whisper-cli", f"Found and launched: {binary}"))
            try:
                devices = backend.devices(binary)
                if devices:
                    summary = "; ".join(
                        f"{d['backend']} device {d['id']}: {d['name']}"
                        for d in devices
                    )
                    checks.append(("GPU backends", summary))
                else:
                    checks.append(("GPU backends", "No Vulkan/CUDA/Metal devices reported; CPU may still work"))
            except (OSError, subprocess.SubprocessError) as exc:
                checks.append(("GPU backends", f"Could not inspect devices: {exc}"))
        else:
            checks.append(("whisper-cli", f"Found at {binary}, but --help exited with {result.returncode}"))
    except FileNotFoundError:
        checks.append(("whisper-cli", "Not found; no download was attempted"))
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(("whisper-cli", f"Could not run: {exc}"))

    cache_path = backend.CACHE.resolve()
    models_path = models.MODELS.resolve()

    try:
        models_path.relative_to(cache_path)
        overlapping = True
    except ValueError:
        try:
            cache_path.relative_to(models_path)
            overlapping = True
        except ValueError:
            overlapping = False

    cache_dirs = [backend.CACHE] if overlapping else [backend.CACHE, models.MODELS]
    cache_size = sum(directory_size(path) for path in cache_dirs)
    checks.append((
        "Model/binary cache",
        f"{format_bytes(cache_size)} across {', '.join(map(str, cache_dirs))}",
    ))

    try:
        disk_path = backend.CACHE if backend.CACHE.exists() else Path.home()
        disk = shutil.disk_usage(disk_path)
        checks.append(("Free disk space", f"{format_bytes(disk.free)} free on {disk_path}"))
    except OSError as exc:
        checks.append(("Free disk space", f"Could not determine: {exc}"))

    report = [
        "Babelscribe doctor report",
        f"Version: {__import__('babelscribe').__version__}",
        *[f"{name}: {value}" for name, value in checks],
    ]
    return checks, "\n".join(report)


def main() -> None:
    checks, report = collect_report()
    print("Babelscribe diagnostics")
    for name, value in checks:
        print(f"{name}: {value}")

    print("\n--- Copy/paste bug report ---")
    print(report)
    print("--- End report ---")
