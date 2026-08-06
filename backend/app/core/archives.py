"""Safe ZIP reading, shared by roster import and batch recognition.

Uploaded archives are untrusted, so the index is validated before a byte is
decompressed: zip-slip paths are refused, and entry count, per-entry size and
declared uncompressed total are all capped.
"""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

from app.core.errors import InvalidRequestError, PayloadTooLargeError


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    name: str
    filename: str
    payload: bytes


def _normalise(name: str) -> str:
    # Comparable key for an entry path.
    return name.strip().replace("\\", "/").removeprefix("./").lower()


def _is_unsafe(name: str) -> bool:
    # Absolute paths and '..' segments would let an entry escape the archive.
    path = PurePosixPath(name.replace("\\", "/"))
    return path.is_absolute() or path.drive != "" or ".." in path.parts


class SafeZipArchive:
    """A validated, read-only view over an uploaded ZIP."""

    def __init__(
        self, zip_file: zipfile.ZipFile, entries: Sequence[zipfile.ZipInfo], max_entry_bytes: int
    ) -> None:
        # Index by full path and by bare name; a duplicated bare name is ambiguous.
        self._zip = zip_file
        self._entries = tuple(entries)
        self._max_entry_bytes = max_entry_bytes
        self._by_path = {_normalise(info.filename): info for info in self._entries}
        by_name: dict[str, zipfile.ZipInfo | None] = {}
        for path, info in self._by_path.items():
            name = path.rsplit("/", 1)[-1]
            by_name[name] = None if name in by_name else info
        self._by_name = by_name

    @classmethod
    def open(
        cls,
        source: BinaryIO | bytes,
        *,
        max_total_bytes: int,
        max_entry_bytes: int,
        max_files: int | None = None,
        suffixes: frozenset[str] | None = None,
    ) -> SafeZipArchive:
        # Validate the whole index up front, then expose only usable entries.
        stream = io.BytesIO(source) if isinstance(source, bytes) else source
        stream.seek(0, os.SEEK_END)
        uploaded = stream.tell()
        stream.seek(0)
        if uploaded > max_total_bytes:
            raise PayloadTooLargeError(
                "The uploaded archive is too large.",
                details={"max_bytes": max_total_bytes, "received_bytes": uploaded},
            )
        try:
            zip_file = zipfile.ZipFile(stream)
            members = [info for info in zip_file.infolist() if not info.is_dir()]
        except (zipfile.BadZipFile, OSError) as exc:
            raise InvalidRequestError("The upload could not be read as a ZIP archive.") from exc
        try:
            _validate(members, max_total_bytes, max_entry_bytes, max_files)
        except Exception:
            zip_file.close()
            raise
        if suffixes is not None:
            members = [
                info for info in members if PurePosixPath(info.filename).suffix.lower() in suffixes
            ]
        return cls(zip_file, members, max_entry_bytes)

    def resolve(self, name: str) -> zipfile.ZipInfo | None:
        # Look a quoted filename up by full path first, then by bare name.
        key = _normalise(name)
        return self._by_path.get(key) or self._by_name.get(key.rsplit("/", 1)[-1])

    def is_ambiguous(self, name: str) -> bool:
        # True when only the bare name matches and it occurs in several folders.
        key = _normalise(name)
        return key not in self._by_path and key.rsplit("/", 1)[-1] in self._by_name

    def read(self, entry: zipfile.ZipInfo) -> bytes:
        # Read one byte past the cap: a longer read means the index lied.
        with self._zip.open(entry) as stream:
            data = stream.read(self._max_entry_bytes + 1)
        if len(data) > self._max_entry_bytes:
            raise PayloadTooLargeError(
                f"Archive entry '{entry.filename}' decompresses beyond the accepted size.",
                details={"max_bytes": self._max_entry_bytes},
            )
        return data

    def iter_entries(self) -> Iterator[ArchiveEntry]:
        # Every entry in the view, decompressed one at a time.
        for info in self._entries:
            yield ArchiveEntry(
                name=info.filename,
                filename=PurePosixPath(info.filename.replace("\\", "/")).name,
                payload=self.read(info),
            )

    def close(self) -> None:
        # Release the underlying file handle.
        self._zip.close()


def _validate(
    members: Sequence[zipfile.ZipInfo],
    max_total_bytes: int,
    max_entry_bytes: int,
    max_files: int | None,
) -> None:
    # Reject traversal, too many files and declared decompression bombs.
    unsafe = [info.filename for info in members if _is_unsafe(info.filename)]
    if unsafe:
        raise InvalidRequestError(
            "The archive contains entries with absolute paths or '..' segments.",
            details={"entries": unsafe[:10]},
        )
    if max_files is not None and len(members) > max_files:
        raise PayloadTooLargeError(
            "The archive holds too many files.",
            details={"max_files": max_files, "received_files": len(members)},
        )
    declared = sum(info.file_size for info in members)
    if declared > max_total_bytes:
        raise PayloadTooLargeError(
            "The archive declares more uncompressed data than is accepted.",
            details={"max_bytes": max_total_bytes, "declared_bytes": declared},
        )
    oversize = [info.filename for info in members if info.file_size > max_entry_bytes]
    if oversize:
        raise PayloadTooLargeError(
            "The archive contains entries that are too large.",
            details={"max_bytes": max_entry_bytes, "entries": oversize[:10]},
        )
