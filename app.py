from __future__ import annotations

import hashlib
import json
import os
import shutil
from io import BytesIO
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import streamlit as st
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

for directory in (DATA_DIR, PHOTO_DIR, THUMB_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="照片里找自己",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1250px; padding-top: 1.5rem;}
      .status-card {
        border: 1px solid rgba(128,128,128,.30);
        border-radius: 14px;
        padding: 14px 16px;
        margin: 8px 0 16px 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state() -> None:
    defaults = {
        "pending_files": {},
        "gallery_uploader_version": 0,
        "last_index_report": None,
        "search_results": [],
        "search_reference_key": None,
        "last_export_dir": None,
        "folder_path_input": "",
        "last_scanned_folder": None,
        "last_scan_count": 0,
        "export_parent_dir": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


@st.cache_resource(show_spinner="正在加载本地人脸模型…")
def load_model() -> FaceAnalysis:
    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"],
    )
    app.prepare(ctx_id=-1, det_size=(1024, 1024))
    return app


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

    # OpenCV 通常不能直接读取 HEIC/HEIF；由 Pillow + pillow-heif 解码。
    try:
        with Image.open(BytesIO(content)) as pil_image:
            pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")
            rgb = np.asarray(pil_image)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        raise ValueError(f"无法读取图片：{exc}") from exc


def normalized_embedding(face) -> np.ndarray:
    vector = getattr(face, "normed_embedding", None)
    if vector is None:
        vector = np.asarray(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError("无效的人脸向量")
        vector = vector / norm
    return np.asarray(vector, dtype=np.float32)


def load_index() -> tuple[np.ndarray, list[dict]]:
    if not INDEX_FILE.exists() or not META_FILE.exists():
        return np.empty((0, 512), dtype=np.float32), []
    try:
        vectors = np.load(INDEX_FILE)["vectors"].astype(np.float32)
        metadata = json.loads(META_FILE.read_text(encoding="utf-8"))
        if len(vectors) != len(metadata):
            raise ValueError("索引与元数据数量不一致")
        return vectors, metadata
    except Exception as exc:
        st.error(f"索引读取失败：{exc}")
        return np.empty((0, 512), dtype=np.float32), []


def save_index(vectors: np.ndarray, metadata: list[dict]) -> None:
    np.savez_compressed(INDEX_FILE, vectors=vectors.astype(np.float32))
    META_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def existing_source_keys(metadata: list[dict]) -> set[str]:
    return {str(item["source_key"]) for item in metadata}


def make_face_thumb(image_bgr: np.ndarray, bbox: Iterable[float], target=220) -> Image.Image:
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    face_w, face_h = max(x2 - x1, 1), max(y2 - y1, 1)
    pad_x, pad_y = int(face_w * 0.35), int(face_h * 0.35)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
    crop = cv2.cvtColor(image_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(crop)
    return ImageOps.fit(pil, (target, target), Image.Resampling.LANCZOS)


def annotated_image(path: Path, bbox: list[float]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = bbox
    width = max(3, int(min(image.size) * 0.006))
    draw.rectangle((x1, y1, x2, y2), outline="red", width=width)
    return image


def add_uploads_to_pending(uploaded_files) -> tuple[int, int]:
    added = 0
    duplicates = 0
    for uploaded in uploaded_files:
        content = uploaded.getvalue()
        source_key = hashlib.sha1(content).hexdigest()
        pending_key = f"upload:{source_key}"
        if pending_key in st.session_state.pending_files:
            duplicates += 1
            continue
        st.session_state.pending_files[pending_key] = {
            "kind": "upload",
            "name": uploaded.name,
            "display_name": uploaded.name,
            "content": content,
            "size": len(content),
            "source_key": source_key,
        }
        added += 1
    return added, duplicates


def choose_folder_macos(prompt: str = "选择文件夹") -> Path | None:
    safe_prompt = prompt.replace('"', r'\\"')
    script = f'POSIX path of (choose folder with prompt "{safe_prompt}")'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    selected = result.stdout.strip()
    return Path(selected).expanduser() if selected else None


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
    return sorted(paths, key=lambda p: str(p).lower())


def add_paths_to_pending(folder: Path, paths: list[Path]) -> tuple[int, int, int]:
    added = 0
    duplicates = 0
    failed = 0
    folder = folder.expanduser().resolve()

    for path in paths:
        try:
            resolved = path.expanduser().resolve()
            stat = resolved.stat()
            pending_key = f"path:{resolved}"
            if pending_key in st.session_state.pending_files:
                duplicates += 1
                continue

            try:
                display_name = str(resolved.relative_to(folder))
            except ValueError:
                display_name = resolved.name

            st.session_state.pending_files[pending_key] = {
                "kind": "path",
                "name": resolved.name,
                "display_name": display_name,
                "path": str(resolved),
                "size": stat.st_size,
            }
            added += 1
        except OSError:
            failed += 1

    return added, duplicates, failed


def index_pending_files(pending_files: list[dict]) -> dict:
    model = load_model()
    old_vectors, metadata = load_index()
    known = existing_source_keys(metadata)
    new_vectors: list[np.ndarray] = []

    report = {
        "selected": len(pending_files),
        "added_photos": 0,
        "added_faces": 0,
        "duplicates": 0,
        "no_face": 0,
        "failed": 0,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    progress = st.progress(0)
    status = st.empty()
    total = max(len(pending_files), 1)

    for position, item in enumerate(pending_files, start=1):
        original_name = item["name"]
        display_name = item.get("display_name", original_name)
        status.write(f"正在处理 {position}/{len(pending_files)}：{display_name}")

        try:
            if item.get("kind") == "path":
                content = Path(item["path"]).read_bytes()
            else:
                content = item["content"]
            source_key = item.get("source_key") or hashlib.sha1(content).hexdigest()
        except Exception as exc:
            report["failed"] += 1
            st.warning(f"{display_name} 读取失败：{exc}")
            progress.progress(position / total)
            continue

        if source_key in known:
            report["duplicates"] += 1
            progress.progress(position / total)
            continue

        suffix = Path(original_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            report["failed"] += 1
            progress.progress(position / total)
            continue

        try:
            image = decode_image_bytes(content)
            faces = model.get(image)

            if not faces:
                report["no_face"] += 1
                progress.progress(position / total)
                continue

            filename = safe_filename(original_name, content)
            photo_path = PHOTO_DIR / filename
            photo_path.write_bytes(content)

            for face_number, face in enumerate(faces):
                vector = normalized_embedding(face)
                bbox = [float(v) for v in face.bbox.tolist()]
                thumb_name = f"{source_key[:12]}-{face_number}.jpg"
                thumb_path = THUMB_DIR / thumb_name
                make_face_thumb(image, bbox).save(thumb_path, quality=88)

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
                report["added_faces"] += 1

            known.add(source_key)
            report["added_photos"] += 1
        except Exception as exc:
            report["failed"] += 1
            st.warning(f"{display_name} 处理失败：{exc}")

        progress.progress(position / total)

    if new_vectors:
        batch = np.vstack(new_vectors).astype(np.float32)
        vectors = batch if len(old_vectors) == 0 else np.vstack([old_vectors, batch])
        save_index(vectors, metadata)
    elif not INDEX_FILE.exists():
        save_index(old_vectors, metadata)

    status.empty()
    progress.empty()

    _, updated_metadata = load_index()
    report["library_photos"] = len({m["source_key"] for m in updated_metadata})
    report["library_faces"] = len(updated_metadata)
    return report


def reference_embedding(uploaded_file) -> tuple[np.ndarray | None, Image.Image | None, str | None]:
    model = load_model()
    content = uploaded_file.getvalue()
    image = decode_image_bytes(content)
    faces = model.get(image)

    if not faces:
        return None, None, "参考照片中没有检测到人脸。请换一张更清晰、正脸更完整的照片。"

    face = max(
        faces,
        key=lambda f: max(0.0, float(f.bbox[2] - f.bbox[0]))
        * max(0.0, float(f.bbox[3] - f.bbox[1])),
    )
    preview = make_face_thumb(image, face.bbox, target=280)
    warning = None
    if len(faces) > 1:
        warning = f"参考照检测到 {len(faces)} 张脸，当前使用面积最大的一张。"
    return normalized_embedding(face), preview, warning


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


def export_matches(matches: list[dict], parent_directory: Path) -> tuple[Path, int]:
    parent_directory = parent_directory.expanduser().resolve()
    if not parent_directory.exists() or not parent_directory.is_dir():
        raise ValueError("导出目标不是可访问的文件夹")

    export_path = parent_directory / datetime.now().strftime("匹配照片_%Y%m%d_%H%M%S")
    export_path.mkdir(parents=True, exist_ok=False)

    copied = 0
    manifest = []
    seen = set()

    for item in matches:
        source_key = item["source_key"]
        if source_key in seen:
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
                "similarity": round(float(item["score"]), 6),
                "source_file": str(source_path),
            }
        )

    (export_path / "匹配结果.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return export_path, copied


def reveal_in_finder(path: Path) -> None:
    subprocess.Popen(["open", str(path)])


def reset_index() -> None:
    for path in (INDEX_FILE, META_FILE):
        if path.exists():
            path.unlink()
    for directory in (PHOTO_DIR, THUMB_DIR):
        for path in directory.glob("*"):
            if path.is_file():
                path.unlink()
    st.session_state.search_results = []
    st.session_state.last_index_report = None


st.title("🔎 照片里找自己")
st.caption("所有照片、人脸裁剪、向量和导出结果都保存在这台 Mac 上。")

with st.sidebar:
    st.header("检索设置")
    threshold = st.slider(
        "最低相似度",
        min_value=0.20,
        max_value=0.80,
        value=0.38,
        step=0.01,
        help="越高越严格。建议先用 0.35–0.45，再人工确认。",
    )
    limit = st.slider("最多返回照片", 10, 200, 60, 10)

    vectors, metadata = load_index()
    unique_photos = len({m["source_key"] for m in metadata})
    st.metric("已索引照片", unique_photos)
    st.metric("已索引人脸", len(metadata))

    st.divider()
    if st.button("清空本地索引", type="secondary", use_container_width=True):
        reset_index()
        st.success("本地索引已清空。")
        time.sleep(0.5)
        st.rerun()

tab_build, tab_search, tab_help = st.tabs(["① 建立照片库", "② 找到我的照片", "使用说明"])

with tab_build:
    st.subheader("导入照片合集")
    st.write("推荐直接指定本机文件夹，应用会自动查找其中的图片；也保留手动选择照片的方式。")

    report = st.session_state.last_index_report
    if report:
        st.success(f"最近一次索引更新已完成 · {report['finished_at']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("新增照片", report["added_photos"])
        c2.metric("新增人脸", report["added_faces"])
        c3.metric("重复跳过", report["duplicates"])
        c4.metric("未检测到脸/失败", report["no_face"] + report["failed"])
        st.caption(
            f"当前照片库共 {report['library_photos']} 张照片、"
            f"{report['library_faces']} 张人脸。"
        )

    import_mode = st.radio(
        "导入方式",
        ["选择本地文件夹（推荐）", "手动选择照片"],
        horizontal=True,
    )

    if import_mode == "选择本地文件夹（推荐）":
        recursive = st.checkbox("同时扫描所有子文件夹", value=True)

        choose_col, scan_col = st.columns([1, 1])
        with choose_col:
            if st.button("在 Finder 中选择文件夹", type="primary", use_container_width=True):
                selected = choose_folder_macos("选择要建立照片索引的文件夹")
                if selected:
                    st.session_state.folder_path_input = str(selected)
                    st.session_state.last_scanned_folder = None
                    st.rerun()

        folder_text = st.text_input(
            "文件夹路径",
            key="folder_path_input",
            placeholder="/Users/你的用户名/Pictures/活动照片",
            help="也可以从 Finder 把文件夹拖到终端取得路径，再粘贴到这里。",
        )

        with scan_col:
            scan_clicked = st.button(
                "扫描文件夹并加入待处理列表",
                use_container_width=True,
                disabled=not bool(folder_text.strip()),
            )

        if scan_clicked:
            folder = Path(folder_text.strip()).expanduser()
            if not folder.exists() or not folder.is_dir():
                st.error("这个路径不是可访问的文件夹。")
            else:
                with st.spinner("正在查找图片文件…"):
                    found_paths = scan_image_files(folder, recursive=recursive)
                    added, duplicates, failed = add_paths_to_pending(folder, found_paths)
                st.session_state.last_scanned_folder = str(folder.resolve())
                st.session_state.last_scan_count = len(found_paths)
                if found_paths:
                    st.success(
                        f"扫描到 {len(found_paths)} 张图片；加入 {added} 张，"
                        f"待处理列表中已存在 {duplicates} 张，读取失败 {failed} 张。"
                    )
                else:
                    st.warning(
                        "没有找到支持的图片。当前支持 JPG、JPEG、PNG、WEBP、BMP、TIF、TIFF、HEIC 和 HEIF。"
                    )

        if st.session_state.last_scanned_folder:
            st.caption(
                f"最近扫描：{st.session_state.last_scanned_folder} · "
                f"发现 {st.session_state.last_scan_count} 张图片"
            )
    else:
        st.write("照片可以分多次选择，每批加入待处理列表后可继续选择下一批。")
        uploader_key = f"gallery_{st.session_state.gallery_uploader_version}"
        uploaded_files = st.file_uploader(
            "选择一批照片",
            type=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "heic", "heif"],
            accept_multiple_files=True,
            key=uploader_key,
        )

        if uploaded_files:
            add_col, note_col = st.columns([1, 2])
            with add_col:
                if st.button("加入待处理列表并继续选", type="primary", use_container_width=True):
                    added, duplicates = add_uploads_to_pending(uploaded_files)
                    st.session_state.gallery_uploader_version += 1
                    if added:
                        st.toast(f"已加入 {added} 张照片")
                    if duplicates:
                        st.toast(f"忽略了 {duplicates} 张重复选择")
                    st.rerun()
            with note_col:
                st.info(f"当前选择器中有 {len(uploaded_files)} 张，尚未开始建立索引。")

    pending = st.session_state.pending_files
    st.markdown("#### 本次待处理列表")
    if pending:
        total_size_mb = sum(item["size"] for item in pending.values()) / 1024 / 1024
        st.info(f"已累计 {len(pending)} 张照片，共约 {total_size_mb:.1f} MB。可以继续追加其他批次。")

        names = [item.get("display_name", item["name"]) for item in pending.values()]
        with st.expander("查看待处理文件", expanded=False):
            for name in names[:200]:
                st.write(f"• {name}")
            if len(names) > 200:
                st.caption(f"其余 {len(names) - 200} 张未展开显示。")

        left, right = st.columns([2, 1])
        with left:
            if st.button(
                f"开始建立 / 更新索引（{len(pending)} 张）",
                type="primary",
                use_container_width=True,
            ):
                report = index_pending_files(list(pending.values()))
                st.session_state.last_index_report = report
                st.session_state.pending_files = {}
                st.session_state.gallery_uploader_version += 1
                st.rerun()
        with right:
            if st.button("清空待处理列表", use_container_width=True):
                st.session_state.pending_files = {}
                st.session_state.gallery_uploader_version += 1
                st.rerun()
    else:
        st.markdown(
            '<div class="status-card">当前没有待处理照片。可在上方选择一批照片并加入列表。</div>',
            unsafe_allow_html=True,
        )

with tab_search:
    st.subheader("上传参考照片")
    reference = st.file_uploader(
        "建议使用清晰、接近正脸、只有你自己的照片",
        type=["jpg", "jpeg", "png", "webp", "heic", "heif"],
        accept_multiple_files=False,
        key="reference",
    )

    if reference:
        reference_key = hashlib.sha1(reference.getvalue()).hexdigest()
        if st.session_state.search_reference_key != reference_key:
            st.session_state.search_reference_key = reference_key
            st.session_state.search_results = []

        try:
            query, preview, warning = reference_embedding(reference)
            if warning:
                st.warning(warning)
            if query is None:
                st.error(warning or "无法提取参考人脸。")
            else:
                left, right = st.columns([1, 3])
                with left:
                    st.image(preview, caption="用于检索的人脸", use_container_width=True)
                with right:
                    st.write("检索结果会保留在页面中，之后可一键复制到新的本地目录。")
                    if st.button("开始检索", type="primary", use_container_width=True):
                        st.session_state.search_results = search_matches(
                            query,
                            threshold=threshold,
                            limit=limit,
                        )

                matches = st.session_state.search_results
                if matches:
                    st.success(f"找到 {len(matches)} 张候选照片，请人工确认。")

                    st.markdown("#### 导出匹配原图")
                    choose_export_col, open_export_col = st.columns([1, 1])
                    with choose_export_col:
                        if st.button(
                            "选择导出目标文件夹",
                            type="secondary",
                            use_container_width=True,
                        ):
                            selected_export = choose_folder_macos("选择匹配照片的导出位置")
                            if selected_export:
                                st.session_state.export_parent_dir = str(selected_export)
                                st.rerun()

                    with open_export_col:
                        last_export = st.session_state.last_export_dir
                        if st.button(
                            "在 Finder 打开最近导出目录",
                            disabled=not bool(last_export),
                            use_container_width=True,
                        ):
                            reveal_in_finder(Path(last_export))

                    export_parent_text = st.text_input(
                        "导出到",
                        key="export_parent_dir",
                        placeholder="/Users/你的用户名/Desktop",
                        help="可以点击上方按钮选择，也可以直接输入或粘贴本地目录路径。",
                    )
                    export_parent = Path(export_parent_text.strip()).expanduser() if export_parent_text.strip() else None
                    export_parent_valid = bool(
                        export_parent
                        and export_parent.exists()
                        and export_parent.is_dir()
                    )

                    if export_parent_text.strip() and not export_parent_valid:
                        st.warning("当前导出路径不存在或不是文件夹。")

                    if st.button(
                        f"导出全部 {len(matches)} 张匹配原图",
                        type="primary",
                        use_container_width=True,
                        disabled=not export_parent_valid,
                    ):
                        try:
                            export_path, copied = export_matches(matches, export_parent)
                            st.session_state.last_export_dir = str(export_path)
                            reveal_in_finder(export_path)
                            st.success(f"已复制 {copied} 张原图到：{export_path}")
                        except Exception as exc:
                            st.error(f"导出失败：{exc}")

                    if export_parent_valid:
                        st.caption(
                            "本次会在所选目录下新建："
                            "`匹配照片_年月日_时分秒`"
                        )
                    if st.session_state.last_export_dir:
                        st.caption(f"最近导出：{st.session_state.last_export_dir}")

                    cols = st.columns(3)
                    for i, item in enumerate(matches):
                        with cols[i % 3]:
                            photo_path = Path(item["photo_path"])
                            thumb_path = Path(item["thumb_path"])
                            if photo_path.exists():
                                st.image(
                                    annotated_image(photo_path, item["bbox"]),
                                    use_container_width=True,
                                )
                            if thumb_path.exists():
                                st.image(
                                    Image.open(thumb_path),
                                    caption=f"匹配人脸 · 相似度 {item['score']:.3f}",
                                    width=120,
                                )
                            st.markdown(f"**{item['original_name']}**")
                            st.caption(f"本地文件：{photo_path.name}")
                            if photo_path.exists():
                                st.download_button(
                                    "单独下载原图副本",
                                    data=photo_path.read_bytes(),
                                    file_name=item["original_name"],
                                    mime="application/octet-stream",
                                    key=f"download-{item['source_key']}",
                                    use_container_width=True,
                                )
                elif st.session_state.search_reference_key == reference_key:
                    st.info("上传参考照后点击“开始检索”。没有结果时可降低相似度阈值。")
        except Exception as exc:
            st.error(f"参考照片处理失败：{exc}")

with tab_help:
    st.markdown(
        """
        ### 建库方式

        **文件夹模式（推荐）**

        1. 点击“在 Finder 中选择文件夹”。
        2. 选择是否扫描所有子文件夹。
        3. 点击“扫描文件夹并加入待处理列表”。
        4. 确认数量后点击“开始建立 / 更新索引”。

        文件夹模式会自动查找 JPG、JPEG、PNG、WEBP、BMP、TIF、TIFF、HEIC 和 HEIF。
        已经存在于索引中的相同图片会按内容哈希自动跳过。

        **手动选择模式**

        仍可一批一批选择照片并加入待处理列表，最后统一建立索引。

        ### 导出匹配照片

        检索成功后，先通过 Finder 选择导出目标文件夹，或直接输入文件夹路径，
        再点击“导出全部匹配原图”。

        应用会在用户指定的位置新建：

        `匹配照片_年月日_时分秒/`

        导出时保留原文件格式和原文件名，包括 HEIC；同名文件会自动加数字后缀，
        并生成一份 `匹配结果.json`。

        ### 本地数据位置

        - 原图副本：`data/photos/`
        - 人脸缩略图：`data/thumbs/`
        - 向量索引：`data/face_index.npz`
        - 元数据：`data/metadata.json`
        - 导出结果：由用户在每次导出前指定父目录
        - 模型缓存：`~/.insightface/models/`

        ### 原型限制

        - 文件夹选择通过 macOS 原生 Finder 对话框完成；首次访问“桌面”“文稿”或外置磁盘时，系统可能要求授权。
        - 浏览器上传仍受浏览器安全限制，因此只作为备用导入方式。
        - 当前参考照若包含多人，只使用面积最大的人脸。
        - 极小、模糊、遮挡严重或大角度侧脸可能漏检、误检。
        - 匹配结果只是候选，不能作为身份认证或重要决策依据。
        """
    )

st.divider()
st.caption(
    "隐私提示：只处理你有权使用的照片。InsightFace 官方预训练模型仅适用于非商业研究；"
    "商业化前需替换为具有明确商业授权的权重或取得许可。"
)
