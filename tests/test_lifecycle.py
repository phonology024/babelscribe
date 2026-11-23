"""--exit-when-stdin-closes: babelscribe ends with the program that started it, and takes whisper-cli and ffmpeg along."""
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from babelscribe import cli, lifecycle

ROOT = Path(__file__).resolve().parent.parent


def alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def gone(*pids: int, within: float = 15.0) -> bool:
    until = time.time() + within
    while time.time() < until:
        if not any(alive(p) for p in pids):
            return True
        time.sleep(0.1)
    return False


def test_the_watchdog_waits_for_the_end_of_the_pipe_and_ignores_what_is_written():
    read, write = os.pipe()
    closed = threading.Event()
    thread = lifecycle.start(read, closed.set)
    os.write(write, b"anything")
    assert not closed.wait(0.5), "data is not a reason to end"
    os.close(write)
    assert closed.wait(5), "end of file is"
    thread.join(5)
    os.close(read)


def test_a_descriptor_that_is_not_open_counts_as_closed():
    closed = threading.Event()
    lifecycle.start(987654, closed.set)
    assert closed.wait(5)


def test_the_flag_is_off_unless_given_so_a_closed_stdin_ends_nothing(monkeypatch):
    started = []
    monkeypatch.setattr(lifecycle, "start", lambda *a, **k: started.append(1))
    with pytest.raises(SystemExit):
        cli.main(["--version"])                           # exits in argparse, before anything runs
    assert started == []
    ap = []
    monkeypatch.setattr(cli, "_run", lambda a, emit=None: ap.append(a))
    cli.main(["x.wav", "--progress-json"])
    assert started == [] and ap[0].exit_when_stdin_closes is False
    cli.main(["x.wav", "--progress-json", "--exit-when-stdin-closes"])
    assert started == [1] and ap[1].exit_when_stdin_closes is True


@pytest.mark.skipif(os.name == "nt", reason="needs ps")
def test_descendants_lists_children_and_grandchildren():
    child = subprocess.Popen([sys.executable, "-c", textwrap.dedent("""
        import subprocess, sys, time
        g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        print(g.pid, flush=True)
        time.sleep(60)""")], stdout=subprocess.PIPE, text=True)
    try:
        grandchild = int(child.stdout.readline())
        assert {child.pid, grandchild} <= set(lifecycle.descendants(os.getpid()))
        assert lifecycle.descendants(grandchild) == []
    finally:
        child.kill()
        child.wait()
        if alive(grandchild):
            os.kill(grandchild, 9)


CHILD = """
import subprocess, sys, time
sys.path.insert(0, {root!r})
from babelscribe import lifecycle
helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])   # stands for whisper-cli
print(helper.pid, flush=True)
lifecycle.start()
time.sleep(120)
"""


@pytest.mark.parametrize("leader", [False, True])
def test_ending_the_program_that_holds_stdin_ends_babelscribe_and_what_it_started(tmp_path, leader):
    """The real thing, in a process of its own: it starts a helper, watches its stdin; the 'app' (this test) closes
    the pipe, as the system does when the app is killed. Both must be gone within seconds. leader: started as the
    leader of its own process group, as the desktop app does on macOS and Linux."""
    if leader and os.name == "nt":
        pytest.skip("process groups are POSIX")
    script = tmp_path / "engine.py"
    script.write_text(CHILD.format(root=str(ROOT)), encoding="utf-8")
    engine = subprocess.Popen([sys.executable, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                              **({"start_new_session": True} if leader else {}))
    helper = int(engine.stdout.readline())
    try:
        time.sleep(1)
        assert engine.poll() is None and alive(helper), "nothing ends while the pipe is open"
        engine.stdin.close()
        assert engine.wait(15) != 0, "babelscribe did not end"
        assert gone(helper), "what babelscribe started is still running"
    finally:
        if engine.poll() is None:
            engine.kill()
            engine.wait()
        if alive(helper):
            os.kill(helper, 9)
        engine.stdout.close()
