from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image, ImageDraw, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FIND_MYSELF_DATA_DIR", APP_DIR / "data")).expanduser().resolve()
PHOTO_DIR = DATA_DIR / "photos"
THUMB_DIR = DATA_DIR / "thumbs"
EXPORT_DIR = DATA_DIR / "exports"
INDEX_FILE = DATA_DIR / "face_index.npz"
META_FILE = DATA_DIR / "metadata.json"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}


def ensure_dirs() -> None:
    for directory in (DATA_DIR, PHOTO_DIR, THUMB_DIR, EXPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def load_model() -> FaceAnalysis:
    model = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    model.prepare(ctx_id=-1, det_size=(1024, 1024))
    return model


def safe_filename(name: str, content: bytes) -> str:
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem[:80] or "photo"
    digest = hashlib.sha1(content).hexdigest()[:10]
    return f"{stem}-{digest}{suffix}"


def decode_image_bytes(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is not None:
        return image

    with Image.open(BytesIO(content)) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")
        rgb = np.asarray(pil_image)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def normalized_embedding(face) -> np.ndarray:
    vector = getattr(face, "normed_embedding", None)
    if vector is None:
        vector = np.asarray(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError("invalid face embedding")
        vector = vector / norm
    return np.asarray(vector, dtype=np.float32)


def load_index() -> tuple[np.ndarray, list[dict]]:
    if not INDEX_FILE.exists() or not META_FILE.exists():
        return np.empty((0, 512), dtype=np.float32), []

    vectors = np.load(INDEX_FILE)["vectors"].astype(np.float32)
    metadata = json.loads(META_FILE.read_text(encoding="utf-8"))
    if len(vectors) != len(metadata):
        raise ValueError("index and metadata length mismatch")
    return vectors, metadata


def save_index(vectors: np.ndarray, metadata: list[dict]) -> None:
    np.savez_compressed(INDEX_FILE, vectors=vectors.astype(np.float32))
    META_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def existing_source_keys(metadata: list[dict]) -> set[str]:
    return {str(item["source_key"]) for item in metadata}


def make_face_thumb(image_bgr: np.ndarray, bbox: Iterable[float], target: int = 220) -> Image.Image:
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    face_w, face_h = max(x2 - x1, 1), max(y2 - y1, 1)
    pad_x, pad_y = int(face_w * 0.35), int(face_h * 0.35)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
    crop = cv2.cvtColor(image_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
    return ImageOps.fit(Image.fromarray(crop), (target, target), Image.Resampling.LANCZOS)


def annotated_image(path: Path, bbox: list[float]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = bbox
    width = max(3, int(min(image.size) * 0.006))
    draw.rounded_rectangle((x1, y1, x2, y2), radius=12, outline="#33a0ff", width=width)
    return image


def image_to_data_url(image: Image.Image, max_width: int, quality: int = 82) -> str:
    working = image.copy()
    if working.width > max_width:
        ratio = max_width / working.width
        working = working.resize((max_width, max(1, int(working.height * ratio))), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    working.save(buffer, format="JPEG", quality=quality, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def scan_image_files(folder: Path, recursive: bool) -> list[Path]:
    folder = folder.expanduser().resolve()
    iterator = folder.rglob("*") if recursive else folder.glob("*")
    paths = []
    for path in iterator:
        try:
            if (
                path.is_file()
                and path.suffix.lower() in SUPPORTED_EXTENSIONS
                and not any(part.startswith(".") for part in path.relative_to(folder).parts)
            ):
                paths.append(path)
        except (OSError, ValueError):
            continue
    return sorted(paths, key=lambda item: str(item).lower())


def unique_export_path(directory: Path, filename: str) -> Path:
    clean_name = Path(filename).name
    candidate = directory / clean_name
    if not candidate.exists():
        return candidate

    stem = Path(clean_name).stem
    suffix = Path(clean_name).suffix
    number = 2
    while True:
        candidate = directory / f"{stem}_{number}{suffix}"
        if not candidate.exists():
            return candidate
        number += 1


def stats_payload() -> dict:
    vectors, metadata = load_index()
    unique_photos = len({item["source_key"] for item in metadata})
    return {
        "dataDir": str(DATA_DIR),
        "photoDir": str(PHOTO_DIR),
        "thumbDir": str(THUMB_DIR),
        "exportDir": str(EXPORT_DIR),
        "indexReady": INDEX_FILE.exists() and META_FILE.exists(),
        "photoCount": unique_photos,
        "faceCount": len(metadata),
        "vectorCount": int(len(vectors)),
    }


def index_folder(folder: Path, recursive: bool) -> dict:
    model = load_model()
    old_vectors, metadata = load_index()
    known = existing_source_keys(metadata)
    new_vectors: list[np.ndarray] = []
    file_paths = scan_image_files(folder, recursive)

    report = {
        "selected": len(file_paths),
        "addedPhotos": 0,
        "addedFaces": 0,
        "duplicates": 0,
        "noFace": 0,
        "failed": 0,
        "folder": str(folder),
        "finishedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    for path in file_paths:
        original_name = path.name
        try:
            content = path.read_bytes()
            source_key = hashlib.sha1(content).hexdigest()
        except Exception:
            report["failed"] += 1
            continue

        if source_key in known:
            report["duplicates"] += 1
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            report["failed"] += 1
            continue

        try:
            image = decode_image_bytes(content)
            faces = model.get(image)
            if not faces:
                report["noFace"] += 1
                continue

            filename = safe_filename(original_name, content)
            photo_path = PHOTO_DIR / filename
            photo_path.write_bytes(content)

            for face_number, face in enumerate(faces):
                vector = normalized_embedding(face)
                bbox = [float(v) for v in face.bbox.tolist()]
                thumb_name = f"{source_key[:12]}-{face_number}.jpg"
                thumb_path = THUMB_DIR / thumb_name
                make_face_thumb(image, bbox).save(thumb_path, quality=86)

                new_vectors.append(vector)
                metadata.append(
                    {
                        "source_key": source_key,
                        "original_name": original_name,
                        "stored_name": filename,
                        "photo_path": str(photo_path),
                        "thumb_path": str(thumb_path),
                        "face_number": face_number,
                        "bbox": bbox,
                    }
                )
                report["addedFaces"] += 1

            known.add(source_key)
            report["addedPhotos"] += 1
        except Exception:
            report["failed"] += 1

    if new_vectors:
        batch = np.vstack(new_vectors).astype(np.float32)
        vectors = batch if len(old_vectors) == 0 else np.vstack([old_vectors, batch])
        save_index(vectors, metadata)
    elif not INDEX_FILE.exists():
        save_index(old_vectors, metadata)

    final_stats = stats_payload()
    report["libraryPhotos"] = final_stats["photoCount"]
    report["libraryFaces"] = final_stats["faceCount"]
    return report


def reference_embedding(image_path: Path) -> tuple[np.ndarray, str | None, Image.Image]:
    model = load_model()
    content = image_path.read_bytes()
    image = decode_image_bytes(content)
    faces = model.get(image)
    if not faces:
        raise ValueError("参考照片中没有检测到人脸。请换一张更清晰的照片。")

    face = max(
        faces,
        key=lambda item: max(0.0, float(item.bbox[2] - item.bbox[0])) * max(0.0, float(item.bbox[3] - item.bbox[1])),
    )
    preview = make_face_thumb(image, face.bbox, target=320)
    warning = None
    if len(faces) > 1:
        warning = f"参考照检测到 {len(faces)} 张脸，当前使用面积最大的一张。"
    return normalized_embedding(face), warning, preview


def search_matches(query: np.ndarray, threshold: float, limit: int) -> list[dict]:
    vectors, metadata = load_index()
    if len(vectors) == 0:
        return []

    scores = vectors @ query
    order = np.argsort(scores)[::-1]

    best_per_photo: dict[str, dict] = {}
    for idx in order:
        score = float(scores[idx])
        if score < threshold:
            break
        item = dict(metadata[int(idx)])
        item["score"] = score
        key = item["source_key"]
        if key not in best_per_photo:
            best_per_photo[key] = item
        if len(best_per_photo) >= limit:
            break
    return list(best_per_photo.values())


def search_image(image_path: Path, threshold: float, limit: int) -> dict:
    query, warning, preview = reference_embedding(image_path)
    matches = search_matches(query, threshold=threshold, limit=limit)
    results = []

    for item in matches:
        photo_path = Path(item["photo_path"])
        thumb_path = Path(item["thumb_path"])
        if not photo_path.exists():
            continue

        annotated = annotated_image(photo_path, item["bbox"])
        thumb = Image.open(thumb_path).convert("RGB") if thumb_path.exists() else None
        results.append(
            {
                "sourceKey": item["source_key"],
                "originalName": item["original_name"],
                "photoPath": str(photo_path),
                "thumbPath": str(thumb_path),
                "score": round(float(item["score"]), 4),
                "bbox": item["bbox"],
                "annotatedImage": image_to_data_url(annotated, 920),
                "faceThumb": image_to_data_url(thumb, 220) if thumb else None,
            }
        )

    return {
        "warning": warning,
        "referencePreview": image_to_data_url(preview, 320, quality=88),
        "results": results,
        "resultCount": len(results),
    }


def export_matches(parent_directory: Path, source_keys: list[str]) -> dict:
    parent_directory = parent_directory.expanduser().resolve()
    if not parent_directory.exists() or not parent_directory.is_dir():
        raise ValueError("导出目标不是可访问的文件夹")

    _, metadata = load_index()
    export_path = parent_directory / datetime.now().strftime("匹配照片_%Y%m%d_%H%M%S")
    export_path.mkdir(parents=True, exist_ok=False)

    copied = 0
    manifest = []
    selected = set(source_keys)
    seen = set()

    for item in metadata:
        source_key = item["source_key"]
        if source_key not in selected or source_key in seen:
            continue
        seen.add(source_key)

        source_path = Path(item["photo_path"])
        if not source_path.exists():
            continue

        destination = unique_export_path(export_path, item["original_name"])
        shutil.copy2(source_path, destination)
        copied += 1
        manifest.append(
            {
                "filename": destination.name,
                "original_name": item["original_name"],
                "source_file": str(source_path),
            }
        )

    (export_path / "匹配结果.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"exportPath": str(export_path), "copied": copied}


def reveal_in_finder(path: Path) -> None:
    subprocess.Popen(["open", str(path)])


def reset_index() -> dict:
    for path in (INDEX_FILE, META_FILE):
        if path.exists():
            path.unlink()
    for directory in (PHOTO_DIR, THUMB_DIR):
        for path in directory.glob("*"):
            if path.is_file():
                path.unlink()
    return stats_payload()


def print_json(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    ensure_dirs()

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("stats")

    index_parser = subparsers.add_parser("index-folder")
    index_parser.add_argument("--folder", required=True)
    index_parser.add_argument("--recursive", choices=["true", "false"], default="true")

    search_parser = subparsers.add_parser("search-image")
    search_parser.add_argument("--image", required=True)
    search_parser.add_argument("--threshold", required=True, type=float)
    search_parser.add_argument("--limit", required=True, type=int)

    export_parser = subparsers.add_parser("export-matches")
    export_parser.add_argument("--parent-dir", required=True)
    export_parser.add_argument("--source-keys-json", required=True)

    subparsers.add_parser("reset-index")

    args = parser.parse_args()

    if args.command == "stats":
        return print_json(stats_payload())
    if args.command == "index-folder":
        return print_json(index_folder(Path(args.folder), args.recursive == "true"))
    if args.command == "search-image":
        return print_json(search_image(Path(args.image), args.threshold, args.limit))
    if args.command == "export-matches":
        source_keys = json.loads(args.source_keys_json)
        return print_json(export_matches(Path(args.parent_dir), source_keys))
    if args.command == "reset-index":
        return print_json(reset_index())

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
