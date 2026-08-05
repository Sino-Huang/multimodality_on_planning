from __future__ import annotations

import ctypes
import errno
import os

_AT_EMPTY_PATH = 0x1000


def renameat2(
    source_descriptor: int,
    source: bytes,
    destination_descriptor: int,
    destination: bytes,
    flags: int,
) -> None:
    try:
        operation = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as error:
        raise OSError(errno.ENOSYS, "renameat2 is unavailable") from error
    operation.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    operation.restype = ctypes.c_int
    if operation(source_descriptor, source, destination_descriptor, destination, flags) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def linkat(source_descriptor: int, source: bytes, destination_descriptor: int, destination: bytes) -> None:
    os.link(source, destination, src_dir_fd=source_descriptor, dst_dir_fd=destination_descriptor, follow_symlinks=False)


def linkat_empty(source_descriptor: int, destination_descriptor: int, destination: bytes) -> None:
    """Create a no-replace destination hard link from the inode pinned by source_descriptor."""
    operation = ctypes.CDLL(None, use_errno=True).linkat
    operation.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int)
    operation.restype = ctypes.c_int
    if operation(source_descriptor, b"", destination_descriptor, destination, _AT_EMPTY_PATH) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def linkat_proc_fd(source_descriptor: int, destination_descriptor: int, destination: bytes) -> None:
    """Link the inode addressed by a live descriptor through procfs with symlink following."""
    os.link(f"/proc/self/fd/{source_descriptor}", destination, dst_dir_fd=destination_descriptor, follow_symlinks=True)
