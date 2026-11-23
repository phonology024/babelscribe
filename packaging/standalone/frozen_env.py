"""Programs the standalone build starts (whisper-cli, ffmpeg) must not load the libraries bundled with it.

On Linux the PyInstaller bootloader puts the build's own folder (_internal) first in LD_LIBRARY_PATH and keeps the
value it found in LD_LIBRARY_PATH_ORIG. Every program the engine starts inherits that path: whisper-cli, and the GPU
driver it loads (Vulkan), would then run against libz, libexpat ... of the machine the engine was built on, which can
be older than what the driver on this machine was built against. install() makes each subprocess started by the
engine see the library path the engine itself was started with. The engine's own process keeps its path: it needs
it to load its modules.

Not needed on Windows (no such variable) or macOS (PyInstaller sets none)."""
from __future__ import annotations

import os
import subprocess
import sys

_ENV_POSITION = 10          # subprocess.Popen(args, bufsize, executable, stdin, stdout, stderr, preexec_fn,
                            #                  close_fds, shell, cwd, env, ...)


def child_env(env: dict | None) -> dict:
    """The environment for a program the engine starts: `env` (or the engine's own) with the library path restored."""
    out = dict(os.environ if env is None else env)
    original = out.get("LD_LIBRARY_PATH_ORIG")
    if original is None:
        out.pop("LD_LIBRARY_PATH", None)
    else:
        out["LD_LIBRARY_PATH"] = original
    return out


def install() -> bool:
    """Apply child_env to every subprocess.Popen (so also run, check_output ...). True when it did anything."""
    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return False
    real_init = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        if len(args) > _ENV_POSITION:
            args = (*args[:_ENV_POSITION], child_env(args[_ENV_POSITION]), *args[_ENV_POSITION + 1:])
        else:
            kwargs["env"] = child_env(kwargs.get("env"))
        real_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = init
    return True
