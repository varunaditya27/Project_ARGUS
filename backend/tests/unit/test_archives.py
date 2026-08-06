"""SafeZipArchive: uploaded archives are untrusted, so the index is checked first."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.archives import SafeZipArchive
from app.core.errors import InvalidRequestError, PayloadTooLargeError
from tests.helpers import PNG, build_zip, open_archive


def test_entries_resolve_by_full_path_and_by_bare_name() -> None:
    archive = open_archive({"batch/ada.png": PNG})
    assert archive.resolve("batch/ada.png") is not None
    assert archive.resolve("ada.png") is not None
    assert archive.resolve("missing.png") is None


def test_lookup_ignores_case_and_backslashes() -> None:
    # Edge: archives built on Windows quote separators the other way round.
    archive = open_archive({"Batch/Ada.PNG": PNG})
    assert archive.resolve("batch\\ada.png") is not None


def test_a_bare_name_in_two_folders_is_ambiguous() -> None:
    archive = open_archive({"a/ada.png": PNG, "b/ada.png": PNG})
    assert archive.resolve("ada.png") is None
    assert archive.is_ambiguous("ada.png")
    # The full path stays unambiguous.
    assert archive.resolve("a/ada.png") is not None
    assert not archive.is_ambiguous("a/ada.png")


@pytest.mark.parametrize("name", ["../escape.png", "/etc/passwd", "a/../../escape.png"])
def test_traversal_entries_reject_the_whole_archive(name: str) -> None:
    with pytest.raises(InvalidRequestError):
        open_archive({name: PNG})


def test_an_upload_larger_than_the_cap_is_refused_before_reading() -> None:
    with pytest.raises(PayloadTooLargeError):
        open_archive({"ada.png": PNG}, max_total_bytes=8)


def test_too_many_files_is_refused() -> None:
    entries = {f"student_{index}.png": PNG for index in range(5)}
    with pytest.raises(PayloadTooLargeError):
        SafeZipArchive.open(
            build_zip(entries), max_total_bytes=1 << 20, max_entry_bytes=1 << 16, max_files=4
        )


def test_a_declared_decompression_bomb_is_refused() -> None:
    # One entry that claims more uncompressed data than the archive accepts.
    with pytest.raises(PayloadTooLargeError):
        open_archive({"big.png": PNG + b"\x00" * 4096}, max_entry_bytes=1024)


def test_reading_an_entry_that_lied_about_its_size_is_refused() -> None:
    # The index is trusted for validation, so the read is capped independently.
    archive = open_archive({"ada.png": PNG + b"\x00" * 512}, max_entry_bytes=1 << 16)
    entry = archive.resolve("ada.png")
    assert entry is not None
    object.__setattr__(archive, "_max_entry_bytes", 16)
    with pytest.raises(PayloadTooLargeError):
        archive.read(entry)


def test_bytes_that_are_not_a_zip_are_a_request_error() -> None:
    with pytest.raises(InvalidRequestError):
        SafeZipArchive.open(b"definitely not a zip", max_total_bytes=1 << 20, max_entry_bytes=1024)


def test_directories_are_not_entries() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("batch/", b"")
        zip_file.writestr("batch/ada.png", PNG)
    buffer.seek(0)
    archive = SafeZipArchive.open(buffer, max_total_bytes=1 << 20, max_entry_bytes=1 << 16)
    assert [entry.filename for entry in archive.iter_entries()] == ["ada.png"]


def test_a_suffix_filter_hides_everything_else() -> None:
    archive = SafeZipArchive.open(
        build_zip({"ada.png": PNG, "notes.txt": b"hello"}),
        max_total_bytes=1 << 20,
        max_entry_bytes=1 << 16,
        suffixes=frozenset({".png"}),
    )
    assert [entry.filename for entry in archive.iter_entries()] == ["ada.png"]


def test_an_empty_archive_yields_nothing() -> None:
    # Edge: valid ZIP, no members.
    archive = open_archive({})
    assert list(archive.iter_entries()) == []
    assert archive.resolve("anything.png") is None
