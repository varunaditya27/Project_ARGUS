"""Safe ZIP reading, shared by roster import and batch recognition.

Uploaded archives are untrusted input, so the whole index is validated before a
single byte is decompressed:

* directory traversal ("zip slip") - absolute paths and ``..`` segments are refused,
* decompression bombs - the declared uncompressed total is checked against a cap,
  and every read is capped again because ``file_size`` is only a claim the archive
  makes about itself,
* resource exhaustion - entry count and per-entry size are capped too.

The archive is read from the caller's file object rather than from a ``bytes``
blob, so a large upload stays in Starlette's spool file instead of being held in
memory in full.
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
    #: Entry name as written in the archive (never absolute, never traversing).
    name: str
    #: Base name without directories, which is what a CSV row refers to.
    filename: str
    payload: bytes


def _is_unsafe(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return path.is_absolute() or path.drive != "" or ".." in path.parts


def _normalise(name: str) -> str:
    return name.strip().replace("\\", "/").removeprefix("./").lower()


class SafeZipArchive:
    """A validated, read-only view over an uploaded ZIP.

    Supports both access shapes the application needs: iterate every entry (batch
    recognition, which wants all the images) and look one up by the name a CSV row
    quotes (roster import).
    """

    def __init__(
        self, zip_file: zipfile.ZipFile, entries: Sequence[zipfile.ZipInfo], *, max_entry_bytes: int
    ) -> None:
        self._zip = zip_file
        self._entries = tuple(entries)
        self._max_entry_bytes = max_entry_bytes

        self._by_path: dict[str, zipfile.ZipInfo] = {}
        by_name: dict[str, zipfile.ZipInfo | None] = {}
        for info in self._entries:
            path = _normalise(info.filename)
            self._by_path[path] = info
            name = path.rsplit("/", 1)[-1]
            # A bare filename occurring in two folders is ambiguous; the caller must
            # then use the full path rather than have us guess which was meant.
            by_name[name] = None if name in by_name else info
        self._by_name = by_name

    # -------------------------------------------------------------------- open
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
        """Validate the archive index and return a reader over it.

        ``max_total_bytes`` caps both the uploaded archive and the uncompressed
        size its index declares; ``suffixes`` restricts the view to the extensions
        the caller can actually handle.
        """
        stream = io.BytesIO(source) if isinstance(source, bytes) else source
        stream.seek(0, os.SEEK_END)
        uploaded_bytes = stream.tell()
        stream.seek(0)
        if uploaded_bytes > max_total_bytes:
            raise PayloadTooLargeError(
                "The uploaded archive is too large.",
                details={"max_bytes": max_total_bytes, "received_bytes": uploaded_bytes},
            )

        try:
            zip_file = zipfile.ZipFile(stream)
            members = [info for info in zip_file.infolist() if not info.is_dir()]
        except (zipfile.BadZipFile, OSError) as exc:
            raise InvalidRequestError(
                "The upload could not be read as a ZIP archive.",
                details={"driver_error": str(exc)},
            ) from exc

        try:
            cls._validate(
                members,
                max_total_bytes=max_total_bytes,
                max_entry_bytes=max_entry_bytes,
                max_files=max_files,
            )
            if suffixes is not None:
                members = [
                    info
                    for info in members
                    if PurePosixPath(info.filename).suffix.lower() in suffixes
                ]
        except Exception:
            zip_file.close()
            raise
        return cls(zip_file, members, max_entry_bytes=max_entry_bytes)

    @staticmethod
    def _validate(
        members: Sequence[zipfile.ZipInfo],
        *,
        max_total_bytes: int,
        max_entry_bytes: int,
        max_files: int | None,
    ) -> None:
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

    # ------------------------------------------------------------------ access
    @property
    def entries(self) -> tuple[zipfile.ZipInfo, ...]:
        return self._entries

    def resolve(self, name: str) -> zipfile.ZipInfo | None:
        """Entry for a quoted filename: full path first, then the bare name."""
        key = _normalise(name)
        info = self._by_path.get(key)
        if info is not None:
            return info
        return self._by_name.get(key.rsplit("/", 1)[-1])

    def is_ambiguous(self, name: str) -> bool:
        key = _normalise(name)
        return key not in self._by_path and key.rsplit("/", 1)[-1] in self._by_name

    def read(self, entry: zipfile.ZipInfo) -> bytes:
        # One byte past the cap: a longer read means the index lied about
        # ``file_size`` and the bomb check on it was worthless.
        with self._zip.open(entry) as stream:
            data = stream.read(self._max_entry_bytes + 1)
        if len(data) > self._max_entry_bytes:
            raise PayloadTooLargeError(
                f"Archive entry '{entry.filename}' decompresses to more than the accepted size.",
                details={"max_bytes": self._max_entry_bytes},
            )
        return data

    def iter_entries(self) -> Iterator[ArchiveEntry]:
        """Every entry in the view, decompressed one at a time."""
        for info in self._entries:
            yield ArchiveEntry(
                name=info.filename,
                filename=PurePosixPath(info.filename.replace("\\", "/")).name,
                payload=self.read(info),
            )

    # ------------------------------------------------------------------- close
    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> SafeZipArchive:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
