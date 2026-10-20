"""Atomic, owner-only writes for credential-bearing application files."""

import logging
import os
from pathlib import Path
import stat
import tempfile


def restrict_mode(path: Path, mode: int) -> bool:
    """Apply an owner-only mode; return False if another user owns ``path``.

    Only the owner may chmod. Bind mounts (e.g. Synology shares granted via
    ACLs) are often owned by a host user, so a foreign owner is reported
    loudly but tolerated. Failures on paths we own still raise.
    """
    try:
        os.chmod(path, mode)
    except PermissionError:
        owner = Path(path).stat().st_uid
        if owner == os.geteuid():
            raise
        logging.getLogger(__name__).warning(
            "Cannot restrict permissions on %s: owned by uid %s, but PowerNight "
            "runs as uid %s. Change its owner to uid %s to protect stored "
            "credentials.", path, owner, os.geteuid(), os.geteuid(),
        )
        return False
    if stat.S_IMODE(Path(path).stat().st_mode) != mode:
        raise PermissionError(f"Cannot secure credential path: {path}")
    return True


def protect_directory(path: Path) -> None:
    """Require owner-only access on directories this process owns."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    restrict_mode(path, 0o700)


def write_private_file(path: Path, content: str, *, exclusive: bool = False) -> bool:
    """Publish complete UTF-8 contents atomically, with mode 0600 from creation.

    Exclusive publication leaves an existing file unchanged, including when
    another process wins first-run initialization. No credentials enter logs.
    """
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != 0o600:
                raise PermissionError(f"Cannot secure credential file: {path}")
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            try:
                os.link(temporary, path)
            except FileExistsError:
                return False
        else:
            os.replace(temporary, path)
        # Persist the published directory entry as well as the file contents.
        Path(temporary).unlink(missing_ok=True)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)
