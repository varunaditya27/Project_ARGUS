"""Bulk face registration + masked identification, scored on accuracy.

Written for the evaluation protocol in the brief:

    registration/<Identity Name>/*.jpg   -> folder name IS the identity
    recognition/<anything>.jpg           -> identify the person
    results.csv                          -> Original Face Name, Model Predicted Face Name

WHY THIS DIFFERS FROM THE LIVE ATTENDANCE PATH
----------------------------------------------
Attendance is open-set: an unknown face must NOT be marked present, so the API
abstains (HUMAN_REVIEW / UNKNOWN) below threshold and writes nothing.

This benchmark is closed-set and scored purely on how many predictions are
correct. Every test image belongs to someone in the gallery, so abstaining is a
guaranteed wrong answer. This tool therefore always emits its best guess -
argmax over the gallery, no threshold - and spends its effort on making that
argmax right.

ACCURACY MEASURES USED (each one measured, not assumed - see --ablate)
  1. no abstention              always emit top-1
  2. detector fallback ladder   retry progressively lower score gates, then
                                treat the whole image as a pre-cropped face
  3. horizontal-flip TTA        average the embedding with its mirror
  4. synthetic-mask gallery     enroll bare photo + 6 masked variants, so a
                                masked probe is compared against masked templates
  5. max-over-templates         an identity scores as its single best template

Usage
-----
    python identify_folder.py --registration DIR --recognition DIR --out results.csv
    python identify_folder.py ... --ground-truth gt.csv       # prints accuracy
    python identify_folder.py ... --ablate                    # per-measure gains
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings                             # noqa: E402
from app.recognition.adapters.arcface import ArcFaceEmbedder         # noqa: E402
from app.recognition.adapters.masks import GeometricMaskSynthesizer  # noqa: E402
from app.recognition.adapters.scrfd import ScrfdFaceDetector         # noqa: E402
from app.recognition.alignment import align_face                     # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
#: Tried in order until a face is found. Masked faces score far below bare ones,
#: so a single fixed gate silently drops real students.
DETECT_LADDER = (0.50, 0.30, 0.20, 0.10, 0.05)


@dataclass(frozen=True, slots=True)
class Options:
    flip_tta: bool = True
    masked_gallery: bool = True
    ladder: bool = True
    whole_image_fallback: bool = True


class Recognizer:
    def __init__(self, model_root: Path, options: Options) -> None:
        settings = get_settings()
        self.options = options
        self.embedder = ArcFaceEmbedder(
            model_root / "w600k_r50.onnx", providers=("CPUExecutionProvider",),
            intra_op_threads=0, embedding_dim=settings.embedding_dim,
        )
        self.synth = GeometricMaskSynthesizer(settings.mask_variants)
        self.detectors = {
            score: ScrfdFaceDetector(
                model_root / "det_10g.onnx", providers=("CPUExecutionProvider",),
                intra_op_threads=0, input_size=settings.detection_input_size,
                score_threshold=score, nms_iou=settings.detection_nms_iou, max_faces=100,
            )
            for score in (DETECT_LADDER if options.ladder else (0.50,))
        }

    # ---- perception -----------------------------------------------------
    def crop(self, image: np.ndarray) -> np.ndarray | None:
        """Aligned 112x112 face, trying progressively weaker detection gates."""
        for score in (DETECT_LADDER if self.options.ladder else (0.50,)):
            faces = self.detectors[score].detect(image)
            if faces:
                best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                return align_face(image, best.landmarks)
        if self.options.whole_image_fallback:
            # Already-cropped portrait: no box to find, so use the frame itself.
            return cv2.resize(image, (112, 112), interpolation=cv2.INTER_AREA)
        return None

    def embed(self, crops: list[np.ndarray]) -> np.ndarray:
        """L2-normalised embeddings, optionally averaged with their mirror."""
        vectors = np.asarray(self.embedder.embed(crops), dtype=np.float32)
        if self.options.flip_tta:
            mirrored = np.asarray(
                self.embedder.embed([cv2.flip(c, 1) for c in crops]), dtype=np.float32
            )
            vectors = vectors + mirrored
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.clip(norms, 1e-9, None)

    def templates_for(self, image: np.ndarray) -> np.ndarray | None:
        """Gallery templates for one enrollment photo: bare + masked variants."""
        face = self.crop(image)
        if face is None:
            return None
        variants = [face]
        if self.options.masked_gallery:
            variants += list(self.synth.synthesize(face).values())
        return self.embed(variants)


def load_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)


def register(recognizer: Recognizer, root: Path) -> tuple[np.ndarray, list[str]]:
    """Bulk-enroll every identity folder. Folder name is the identity."""
    vectors: list[np.ndarray] = []
    owners: list[str] = []
    people = sorted(d for d in root.iterdir() if d.is_dir())
    if not people:
        raise SystemExit(f"No identity folders found under {root}")

    started = time.time()
    for index, person in enumerate(people, 1):
        for photo in load_images(person):
            image = cv2.imread(str(photo))
            if image is None:
                continue
            templates = recognizer.templates_for(image)
            if templates is None:
                print(f"  ! no face in {photo.name} ({person.name})")
                continue
            vectors.extend(templates)
            owners.extend([person.name] * len(templates))
        if index % 25 == 0 or index == len(people):
            print(f"  registered {index}/{len(people)} identities "
                  f"({len(vectors)} templates, {time.time()-started:.0f}s)", flush=True)
    return np.asarray(vectors, dtype=np.float32), owners


def identify(recognizer: Recognizer, gallery: np.ndarray, owners: list[str],
             root: Path) -> list[tuple[str, str]]:
    """Predict an identity for every test image. Never abstains."""
    owner_array = np.asarray(owners)
    results: list[tuple[str, str]] = []
    images = load_images(root)
    started = time.time()

    for index, path in enumerate(images, 1):
        image = cv2.imread(str(path))
        prediction = "UNKNOWN"
        if image is not None:
            face = recognizer.crop(image)
            if face is not None:
                query = recognizer.embed([face])[0]
                # An identity scores as its single best template (max, not mean),
                # so one good masked variant is enough to carry the match.
                similarity = gallery @ query
                prediction = str(owner_array[int(np.argmax(similarity))])
        results.append((path.stem, prediction))
        if index % 25 == 0 or index == len(images):
            print(f"  identified {index}/{len(images)} ({time.time()-started:.0f}s)", flush=True)
    return results


def score(results: list[tuple[str, str]], ground_truth: Path) -> float:
    with open(ground_truth, newline="", encoding="utf-8") as fh:
        truth = {r["Original Face Name"]: r["True Identity"] for r in csv.DictReader(fh)}
    hits = sum(1 for name, predicted in results if truth.get(name) == predicted)
    return hits / max(len(results), 1)


def write_csv(results: list[tuple[str, str]], out: Path) -> None:
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Original Face Name", "Model Predicted Face Name"])
        writer.writerows(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("results.csv"))
    parser.add_argument("--ground-truth", type=Path)
    parser.add_argument("--model-root", type=Path, default=BACKEND.parent / "models" / "buffalo_l")
    parser.add_argument("--ablate", action="store_true",
                        help="measure each accuracy technique by turning it off")
    args = parser.parse_args()

    configurations = {"all measures on": Options()}
    if args.ablate:
        configurations |= {
            "no flip-TTA": Options(flip_tta=False),
            "no masked gallery": Options(masked_gallery=False),
            "no detector ladder": Options(ladder=False, whole_image_fallback=False),
        }

    for label, options in configurations.items():
        print(f"\n=== {label} ===", flush=True)
        recognizer = Recognizer(args.model_root, options)
        gallery, owners = register(recognizer, args.registration)
        print(f"  gallery: {gallery.shape[0]} templates / {len(set(owners))} identities")
        results = identify(recognizer, gallery, owners, args.recognition)
        if label == "all measures on":
            write_csv(results, args.out)
            print(f"  wrote {args.out}")
        if args.ground_truth:
            print(f"  ACCURACY: {score(results, args.ground_truth)*100:.2f}%")


if __name__ == "__main__":
    main()
