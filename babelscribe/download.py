"""Downloads that continue where they stopped.

A dropped connection is tried again at once, with an HTTP Range request for the bytes that are still missing, and what
was downloaded stays in a .part file, so running babelscribe again after giving up (or after Ctrl+C, a Cancel, a
shutdown) continues too. Bytes are only joined to older ones when there is a checksum to prove the result: the finished
file is hashed as a whole, and nothing is used unless it matches. Without a checksum every attempt starts from zero."""
from __future__ import annotations

import contextlib
import errno
import hashlib
import http.client
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

CHUNK = 1 << 16
TIMEOUT = 60                  # seconds without a single byte before a connection counts as dropped
ATTEMPTS = 6                  # attempts in a row that bring nothing new before giving up
SLEEP = time.sleep            # replaced by the tests
_BUSY = (errno.EACCES, errno.EAGAIN, errno.EDEADLK)


class ChecksumMismatch(Exception):
    """The finished file is not the expected one (it has been deleted). `got` is what it hashed to."""

    def __init__(self, got: str):
        super().__init__(got)
        self.got = got


class NotFound(Exception):
    """The server answered 404."""


class _Dropped(Exception):
    """This attempt failed in a way that another one may not."""


class _BadCertificate(_Dropped):
    """The server's certificate did not pass the check."""


def _roots_only() -> ssl.SSLContext | None:
    """Windows: the same full certificate check, building the chain from the system's trusted ROOT certificates only.

    Python also hands OpenSSL every certificate in Windows' intermediate ("CA") store. That store can hold an old
    cross-signed copy of a root whose own issuer is missing; OpenSSL then follows the copy and fails with "unable to
    get issuer certificate" on a good server (seen with github.com). None on other systems."""
    if not hasattr(ssl, "enum_certificates"):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)           # certificate and host name are required
    for cert, encoding, trust in ssl.enum_certificates("ROOT"):
        if encoding == "x509_asn" and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
            with contextlib.suppress(ssl.SSLError):          # one unreadable entry must not lose the others
                ctx.load_verify_locations(cadata=cert)
    return ctx


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _try_lock(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def lock(path: Path, what: str, log: Callable[[str], None] = print):
    """One babelscribe at a time per download (the app, a terminal and an AI app's server can all want the same file;
    two of them writing one .part would spoil it). Yields True when it had to wait for another one, which may have
    done the work by now. The system drops the lock when a process ends, however it ends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    waited = held = False
    with open(path, "a+b") as f:
        while True:
            try:
                _try_lock(f)
                held = True
                break
            except OSError as e:
                if e.errno not in _BUSY:      # a disk that cannot lock (some network shares): go on without
                    break
                if not waited:
                    log(f"another babelscribe is downloading {what}; waiting for it ...")
                    waited = True
                SLEEP(1)
        try:
            yield waited
        finally:
            if held:
                with contextlib.suppress(OSError):
                    _unlock(f)


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _cannot_write(path: Path, e: OSError) -> SystemExit:
    return SystemExit(f"could not write {path} ({e.strerror or e}). What was downloaded so far is kept: free some disk "
                      f"space (or fix the folder's permissions) and run babelscribe again.")


def _attempt(url: str, part: Path, resume: bool, tls: dict) -> None:
    """One connection: add to the part file (or start it over). Returns when the server sent everything it announced."""
    have = _size(part) if resume else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT, **tls)
    except urllib.error.HTTPError as e:
        with contextlib.suppress(Exception):
            e.close()
        if e.code == 404:
            raise NotFound(url) from None
        if e.code == 416 and have:            # nothing left at that offset, yet the file is not the right one
            part.unlink()
            raise _Dropped("the server could not continue the file") from None
        if e.code in (408, 429) or e.code >= 500:
            raise _Dropped(f"HTTP {e.code}") from None
        raise SystemExit(f"could not download {url}: HTTP {e.code} {e.reason}") from None
    except (OSError, http.client.HTTPException) as e:
        reason = getattr(e, "reason", e)
        if url.startswith("file:") and isinstance(reason, FileNotFoundError):     # a mirror in a folder
            raise NotFound(url) from None
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise _BadCertificate(f"the server's certificate could not be checked ({reason})") from None
        raise _Dropped(str(reason) or type(e).__name__) from None
    with resp:
        status = getattr(resp, "status", None) or 200
        length = resp.headers.get("Content-Length") if getattr(resp, "headers", None) else None
        total = int(length) if length and length.isdigit() else None
        if status == 206:
            m = re.match(r"bytes (\d+)-(\d+)/(\d+|\*)", resp.headers.get("Content-Range", ""))
            if not have or not m or int(m.group(1)) != have:
                if part.exists():
                    part.unlink()
                raise _Dropped("the server continued at the wrong place")
            total = int(m.group(3)) if m.group(3) != "*" else int(m.group(2)) + 1
        else:
            have = 0                          # the whole file again: the server does not do ranges
        try:
            f = open(part, "ab" if have else "wb")
        except OSError as e:
            raise _cannot_write(part, e) from None
        with f:
            while True:
                try:
                    block = resp.read(CHUNK)
                except (OSError, http.client.HTTPException) as e:
                    raise _Dropped(str(e) or type(e).__name__) from None
                if not block:
                    break
                try:
                    f.write(block)
                    f.flush()
                except OSError as e:
                    raise _cannot_write(part, e) from None
    if total is not None and _size(part) < total:    # read(n) returns b"" on a cut connection, without an error
        raise _Dropped("the connection closed before the end")


def fetch(url: str, part: Path, sha256: str | None, what: str, log: Callable[[str], None] = print) -> str:
    """Download url into the file `part` and return its sha256. The caller moves or unpacks `part`.

    With sha256 the download continues whatever `part` already holds, and `part` is deleted if the result does not
    match (ChecksumMismatch). Without it, `part` starts from zero and does not survive a failure."""
    resume = sha256 is not None
    part.parent.mkdir(parents=True, exist_ok=True)
    if not resume:
        part.unlink(missing_ok=True)
    elif _size(part):
        if sha256_of(part) == sha256:                # finished, but stopped before it could be used
            return sha256
        log(f"continuing the download of {what} at {_size(part) / 1e6:.0f} MB ...")
    joined = resume and _size(part) > 0              # the file holds bytes from more than one connection
    best, stalls, done = _size(part), 0, False
    tls: dict = {}                                   # how the server's certificate is checked; it is always checked
    try:
        while True:
            try:
                _attempt(url, part, resume, tls)
            except _Dropped as e:
                if isinstance(e, _BadCertificate):    # the next attempt builds the chain the other way (see _roots_only)
                    other = None if tls else _roots_only()
                    tls = {"context": other} if other else {}
                now = _size(part)
                if resume and now > best:
                    best, stalls = now, 0
                else:
                    stalls += 1
                if stalls >= ATTEMPTS:
                    kept = (f" The {now / 1e6:.0f} MB already downloaded are kept; run babelscribe again to continue."
                            if resume and now else " Run babelscribe again to retry.")
                    check = ("Check the computer's date and time, and any proxy or antivirus that opens HTTPS."
                             if "certificate" in str(e) else "Check the internet connection.")
                    raise SystemExit(f"the download of {what} stopped: {e}. {check}{kept}") from None
                joined = joined or (resume and now > 0)
                log(f"the download of {what} was interrupted ({e}); trying again ...")
                SLEEP(min(2 ** stalls, 15))
                continue
            got = sha256_of(part)
            if sha256 is None or got == sha256:
                done = True
                return got
            part.unlink()
            if not joined:
                raise ChecksumMismatch(got)
            log(f"the continued download of {what} does not match its checksum; starting it again from the beginning ...")
            joined, best, stalls = False, 0, 0
    finally:
        if not done and not resume:
            with contextlib.suppress(OSError):
                part.unlink(missing_ok=True)
