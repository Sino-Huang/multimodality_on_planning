from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypeAlias

from .output_layout_inventory_types import OutputLayoutInventoryError

RENAME_NOREPLACE: Final = 1
RENAME_EXCHANGE: Final = 2
_READ_CHUNK_BYTES: Final = 1024 * 1024
_MAX_RECEIPT_BYTES: Final = 16 * 1024 * 1024
MAX_RECEIPT_BYTES: Final = _MAX_RECEIPT_BYTES

ExchangeOperation: TypeAlias = Callable[[int, str, str], None]


def max_receipt_bytes() -> int:
    return _MAX_RECEIPT_BYTES


@dataclass(frozen=True, slots=True)
class ReceiptContentToken:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int
    digest: bytes


def atomic_exchange(parent_descriptor: int, source_name: str, destination_name: str) -> None:
    atomic_rename(parent_descriptor, source_name, destination_name, RENAME_EXCHANGE)


def atomic_rename(parent_descriptor: int, source_name: str, destination_name: str, flags: int) -> None:
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as error:
        if flags == RENAME_EXCHANGE:
            raise OutputLayoutInventoryError("atomic receipt exchange is unavailable") from error
        raise OSError("atomic rename is unavailable") from error
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    result: int = renameat2(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(destination_name),
        flags,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if flags == RENAME_EXCHANGE and error_number in (errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP):
            raise OutputLayoutInventoryError("atomic receipt exchange is unavailable")
        raise OSError(error_number, os.strerror(error_number))


def read_content_token(descriptor: int) -> tuple[ReceiptContentToken, bytes]:
    initial_stat = os.fstat(descriptor)
    if initial_stat.st_size > _MAX_RECEIPT_BYTES:
        raise OutputLayoutInventoryError("receipt exceeds size limit")
    contents = _read_descriptor_bytes(descriptor)
    final_stat = os.fstat(descriptor)
    if _metadata(final_stat) != _metadata(initial_stat):
        raise OutputLayoutInventoryError("receipt changed while its content token was read")
    return _metadata(initial_stat, hashlib.sha256(contents).digest()), contents


def _read_descriptor_bytes(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while chunk := os.pread(descriptor, _READ_CHUNK_BYTES, offset):
        if offset + len(chunk) > _MAX_RECEIPT_BYTES:
            raise OutputLayoutInventoryError("receipt exceeds size limit")
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _metadata(receipt_stat: os.stat_result, digest: bytes = b"") -> ReceiptContentToken:
    return ReceiptContentToken(
        receipt_stat.st_dev,
        receipt_stat.st_ino,
        stat.S_IFMT(receipt_stat.st_mode),
        receipt_stat.st_size,
        receipt_stat.st_mtime_ns,
        receipt_stat.st_ctime_ns,
        digest,
    )
