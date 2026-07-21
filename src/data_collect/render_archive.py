"""Safe PNG archive extraction."""

from __future__ import annotations

import stat
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_ARCHIVE_MEMBERS = 128
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 100

def extract_png_archive(archive_bytes: bytes, output_dir: Path) -> int:
    root = output_dir.resolve()
    with zipfile.ZipFile(BytesIO(archive_bytes), "r") as archive:
        members = tuple(info for info in archive.infolist() if not info.is_dir())
        _validate_png_archive_members(members, root)
        rendered = [(root / member.filename, archive.read(member)) for member in members]
        for target, payload in rendered:
            _validate_png_bytes(payload, target.name)
    for target, payload in rendered:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return len(rendered)


_extract_png_archive = extract_png_archive

__all__ = ["_extract_png_archive"]


def _validate_png_archive_members(members: tuple[zipfile.ZipInfo, ...], root: Path) -> None:
    if not members or len(members) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("archive member count is outside the allowed bound")
    total_size = 0
    for member in members:
        target = (root / member.filename).resolve()
        ratio = member.file_size / max(member.compress_size, 1)
        if not member.filename.lower().endswith(".png") or member.file_size > MAX_ARCHIVE_MEMBER_BYTES or ratio > MAX_ARCHIVE_COMPRESSION_RATIO or stat.S_ISLNK(member.external_attr >> 16) or not target.is_relative_to(root):
            raise ValueError(f"unsafe archive member: {member.filename}")
        total_size += member.file_size
        if total_size > MAX_ARCHIVE_TOTAL_BYTES:
            raise ValueError("archive exceeds the allowed uncompressed size")


def _validate_png_bytes(payload: bytes, name: str) -> None:
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
        with Image.open(BytesIO(payload)) as image:
            if image.width <= 0 or image.height <= 0:
                raise ValueError(f"PNG has invalid dimensions: {name}")
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"archive member is not a decodable PNG: {name}") from error
