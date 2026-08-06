"""Build a roster CSV and its photo archive for POST /students/import.

Two sources. Point --photos at a directory of photographs, one per student, and
each file becomes a row. Or point --manifest at datasets/processed/*.csv and
--root at the LFW download, and the first --count identities become rows, which
is the only way to get genuinely distinct faces into the import.

    python build_roster.py --photos ./my_photos --start-roll 101
    python build_roster.py --manifest ../../datasets/processed/enrollment_manifest.csv \
        --root ~/datasets/raw/LFW --count 200
"""

from __future__ import annotations

import argparse
import csv
import zipfile
from pathlib import Path

HEADER = ("student_name", "roll_no", "class_id", "image_filename", "image_url")
SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def from_photos(directory: Path) -> list[tuple[str, Path]]:
    # Each image is one student; the file stem becomes the name.
    files = sorted(path for path in directory.iterdir() if path.suffix.lower() in SUFFIXES)
    if not files:
        raise SystemExit(f"No images found in {directory}")
    return [(path.stem.replace("_", " ").title(), path) for path in files]


def from_manifest(manifest: Path, root: Path, count: int) -> list[tuple[str, Path]]:
    # The dataset manifests carry absolute paths from the machine that built
    # them, so only the identity and filename are reused.
    rows: list[tuple[str, Path]] = []
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            identity = row["identity"]
            image = root / identity / row["filename"]
            if not image.exists():
                image = next(root.rglob(row["filename"]), None)
            if image is None or not image.exists():
                continue
            rows.append((identity.replace("_", " "), image))
            if len(rows) >= count:
                break
    if not rows:
        raise SystemExit(f"No manifest image resolved under {root}; is the dataset downloaded?")
    return rows


def write(students: list[tuple[str, Path]], out: Path, start_roll: int, class_id: str) -> None:
    # One CSV row and one archive entry per student, named by roll number.
    out.mkdir(parents=True, exist_ok=True)
    csv_path, zip_path = out / "roster.csv", out / "photos.zip"
    with csv_path.open("w", newline="", encoding="utf-8") as handle, zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED
    ) as archive:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for offset, (name, image) in enumerate(students):
            roll = start_roll + offset
            entry = f"student_{roll}{image.suffix.lower()}"
            writer.writerow([name, roll, class_id, entry, ""])
            archive.write(image, entry)
    print(f"{len(students)} students -> {csv_path} and {zip_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--photos", type=Path, help="Directory of photographs, one per student.")
    source.add_argument("--manifest", type=Path, help="datasets/processed/*.csv to read.")
    parser.add_argument("--root", type=Path, help="Dataset image root, required with --manifest.")
    parser.add_argument("--count", type=int, default=100, help="Students to take from a manifest.")
    parser.add_argument("--start-roll", type=int, default=101)
    parser.add_argument("--class-id", default="", help="Leave empty to choose in the UI.")
    parser.add_argument("--out", type=Path, default=Path("."))
    args = parser.parse_args()

    if args.manifest and not args.root:
        raise SystemExit("--root is required with --manifest")
    students = (
        from_photos(args.photos)
        if args.photos
        else from_manifest(args.manifest, args.root, args.count)
    )
    write(students, args.out, args.start_roll, args.class_id)


if __name__ == "__main__":
    main()
