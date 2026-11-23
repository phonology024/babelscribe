"""End with the program that started us: `--exit-when-stdin-closes`.

The desktop app starts babelscribe with a pipe on its standard input that it holds open and never writes to. While
the app lives the pipe stays open; when the app ends, in any way (closed, crashed, killed), the system closes its end
and the read below returns end-of-file. Then babelscribe ends whisper-cli and ffmpeg, which it started, and exits:
a transcription nobody is waiting for must not keep a GPU busy.

The same on Windows, macOS and Linux, and no job objects or parent-process polling needed. It is a flag of its own,
not part of --progress-json: a program that runs babelscribe with its stdin closed (or on /dev/null) would otherwise
find every run ended at once."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import Callable

NO_WINDOW = 0x08000000      # CREATE_NO_WINDOW


def start(fd: int = 0, on_close: Callable[[], None] | None = None) -> threading.Thread:
    """Watch `fd` (standard input) from a background thread; call `on_close` (default: end_everything) at its end.
    Whatever is written to it is ignored."""
    on_close = on_close or end_everything

    def watch() -> None:
        while True:
            try:
                if not os.read(fd, 4096):
                    break
            except InterruptedError:
                continue
            except OSError:               # closed under us, or never open: nobody is on the other end
                break
        on_close()

    thread = threading.Thread(target=watch, name="parent-watchdog", daemon=True)
    thread.start()
    return thread


def descendants(pid: int) -> list[int]:
    """The processes started by `pid`, and theirs ... (POSIX; `ps` lists pid and parent pid on Linux and macOS)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "ppid="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child)
    return found


def end_everything() -> None:
    """Kill whisper-cli, ffmpeg and anything else this process started, then end this process. Never returns."""
    try:
        if os.name == "nt":
            # the process and its whole tree (the same call the desktop app makes when the user presses Cancel)
            subprocess.run(["taskkill", "/PID", str(os.getpid()), "/T", "/F"], capture_output=True,
                           creationflags=NO_WINDOW, timeout=30)
        else:
            if os.getpgrp() == os.getpid():          # the desktop app starts us as the leader of our own group
                os.killpg(os.getpid(), signal.SIGKILL)   # all of it, this process included
            for _ in range(3):                       # a child started while we were looking is caught the next time
                pids = descendants(os.getpid())
                if not pids:
                    break
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
    finally:
        os._exit(1)
