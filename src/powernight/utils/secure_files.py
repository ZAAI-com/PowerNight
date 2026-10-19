"""Atomic, owner-only writes for credential-bearing application files."""

import os
from pathlib import Path
import stat
import tempfile


def protect_directory(path: Path) -> None:
    """Require owner-only directory access; never silently weaken protection."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise PermissionError(f"Cannot secure credential directory: {path}")


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
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)
