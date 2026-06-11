#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== 照片里找自己：Mac 安装程序 v2 ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python 3.10–3.12，推荐 3.11。"
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "检测到 Python $PY_VERSION"

python3 - <<'PY'
import sys
if not ((3, 10) <= sys.version_info[:2] <= (3, 12)):
    raise SystemExit(
        "请使用 Python 3.10–3.12，推荐 Python 3.11。"
        f" 当前为 {sys.version_info.major}.{sys.version_info.minor}。"
    )
PY

if [ -d ".venv" ]; then
  echo "发现旧的 .venv，正在删除并重新创建……"
  rm -rf .venv
fi

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel

# 强制使用通用 wheel，不允许 pip 回退到本地 C++ 源码编译。
python -m pip install --only-binary=insightface "insightface==1.0.1"
python -m pip install -r requirements.txt

echo "正在执行安装自检……"
python - <<'PY'
import platform
import insightface
import onnxruntime
import cv2
import streamlit
import pillow_heif

print("Python:", platform.python_version())
print("Machine:", platform.machine())
print("InsightFace:", getattr(insightface, "__version__", "unknown"))
print("ONNX Runtime:", onnxruntime.__version__)
print("OpenCV:", cv2.__version__)
print("Streamlit:", streamlit.__version__)
print("pillow-heif:", pillow_heif.__version__)
print("安装自检通过。")
PY

echo
echo "安装完成。双击 start.command 启动。"
echo "首次处理照片时，模型会下载到 ~/.insightface/models/。"
