"""
The on-disk game data cache, safe for several threads and processes loading at once.

A file is written to a temporary name beside it and renamed into place, so a reader sees
the old file or the new one, never half of one. :func:`locked` lets one process download
while the others wait and then read what it wrote. None of this is client behaviour; the
browser client keeps its items in memory.
"""

import errno
import logging
import os
import secrets
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import msvcrt

    _STILL_HELD = {errno.EDEADLK, getattr(errno, "EDEADLOCK", errno.EDEADLK)}

    def _acquire(fd: int) -> None:
        # LK_LOCK gives up with EDEADLOCK after ten one-second tries while another process holds the lock.
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                return
            except OSError as e:
                if e.errno not in _STILL_HELD:
                    raise

    def _release(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _acquire(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _release(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """
    Hold an exclusive lock on ``path`` across processes, creating it if missing.

    A lock that cannot be had (a read-only cache directory, a filesystem without
    locks) gives no lock rather than an error: the rename in :func:`write_atomic`
    still keeps readers safe.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
    except OSError as e:
        logger.debug(f"Loading without the cache lock {path}: {e}")
        yield
        return
    with handle:
        handle.seek(0)
        try:
            _acquire(handle.fileno())
        except OSError as e:
            logger.debug(f"Loading without the cache lock {path}: {e}")
            yield
            return
        try:
            yield
        finally:
            _release(handle.fileno())


def write_atomic(path: Path, text: str) -> None:
    """
    Replace ``path`` with ``text`` in one rename. Raises OSError when it cannot.

    The file gets the permissions :meth:`Path.write_text` would give it (the umask applies).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    out = temp.open("x", encoding="utf-8")
    try:
        with out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


__all__ = ["locked", "write_atomic"]
