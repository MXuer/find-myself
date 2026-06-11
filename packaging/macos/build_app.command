#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_NAME="Find Myself"
BUNDLE_ID="com.mxuer.findmyself"
DIST_DIR="$PROJECT_ROOT/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
BUNDLED_APP_DIR="$RESOURCES_DIR/app"

if [ -e "$APP_DIR" ]; then
  echo "已存在：$APP_DIR"
  echo "如需重新构建，请先删除旧的 app bundle。"
  exit 1
fi

mkdir -p "$MACOS_DIR" "$BUNDLED_APP_DIR"

rsync -a \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "dist" \
  --exclude ".DS_Store" \
  --exclude "data/photos/*" \
  --exclude "data/thumbs/*" \
  --exclude "data/exports/*" \
  --exclude "data/face_index.npz" \
  --exclude "data/metadata.json" \
  "$PROJECT_ROOT/" "$BUNDLED_APP_DIR/"

mkdir -p \
  "$BUNDLED_APP_DIR/data/photos" \
  "$BUNDLED_APP_DIR/data/thumbs" \
  "$BUNDLED_APP_DIR/data/exports"
touch \
  "$BUNDLED_APP_DIR/data/photos/.gitkeep" \
  "$BUNDLED_APP_DIR/data/thumbs/.gitkeep" \
  "$BUNDLED_APP_DIR/data/exports/.gitkeep"

cat > "$CONTENTS_DIR/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh_CN</string>
  <key>CFBundleDisplayName</key>
  <string>照片里找自己</string>
  <key>CFBundleExecutable</key>
  <string>find-myself</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>LSUIElement</key>
  <false/>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSHumanReadableCopyright</key>
  <string>Copyright © 2026 MXuer. Code licensed under MIT. Model weights follow their own licenses.</string>
</dict>
</plist>
PLIST

cat > "$CONTENTS_DIR/PkgInfo" <<PKGINFO
APPL????
PKGINFO

ICONSET_DIR="$RESOURCES_DIR/AppIcon.iconset"
ICON_SOURCE="$RESOURCES_DIR/AppIconSource.png"
if [ "${FIND_MYSELF_BUILD_ICON:-0}" = "1" ]; then
  mkdir -p "$ICONSET_DIR"

  python3 - "$ICON_SOURCE" <<'PY'
import sys

from PIL import Image, ImageDraw, ImageFilter

target = sys.argv[1]

base = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
draw = ImageDraw.Draw(base)

shadow = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
shadow_draw = ImageDraw.Draw(shadow)
shadow_draw.rounded_rectangle((116, 132, 908, 924), radius=196, fill=(0, 0, 0, 72))
shadow = shadow.filter(ImageFilter.GaussianBlur(28))
base.alpha_composite(shadow)

draw.rounded_rectangle((104, 104, 920, 920), radius=190, fill=(31, 132, 108, 255))
draw.rounded_rectangle((104, 104, 920, 920), radius=190, outline=(255, 255, 255, 90), width=8)

draw.rounded_rectangle((242, 236, 728, 646), radius=42, fill=(246, 248, 250, 255))
draw.rounded_rectangle((278, 276, 692, 500), radius=28, fill=(183, 216, 235, 255))
draw.polygon([(278, 500), (418, 382), (532, 500)], fill=(92, 159, 130, 255))
draw.polygon([(430, 500), (574, 356), (692, 500)], fill=(55, 124, 111, 255))
draw.ellipse((568, 304, 632, 368), fill=(255, 196, 86, 255))

draw.ellipse((356, 340, 554, 538), outline=(34, 42, 53, 255), width=32)
draw.arc((316, 458, 594, 748), start=205, end=335, fill=(34, 42, 53, 255), width=32)

draw.ellipse((526, 526, 804, 804), outline=(255, 255, 255, 255), width=54)
draw.line((732, 732, 846, 846), fill=(255, 255, 255, 255), width=66)
draw.ellipse((526, 526, 804, 804), outline=(34, 42, 53, 255), width=20)

base.save(target)
PY

  /usr/bin/sips -z 16 16 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
  /usr/bin/sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
  /usr/bin/sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
  /usr/bin/sips -z 64 64 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
  /usr/bin/sips -z 128 128 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
  /usr/bin/sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
  /usr/bin/sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
  /usr/bin/sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
  /usr/bin/sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
  /usr/bin/sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null

  if iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/AppIcon.icns"; then
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$CONTENTS_DIR/Info.plist" >/dev/null
    echo "已生成应用图标。"
  else
    echo "图标生成失败，将使用 macOS 默认应用图标。"
  fi
else
  echo "跳过应用图标生成。需要尝试生成图标时可设置 FIND_MYSELF_BUILD_ICON=1。"
fi

cat > "$MACOS_DIR/find-myself" <<'LAUNCHER'
#!/bin/bash
set -euo pipefail

CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
BUNDLED_APP_DIR="$RESOURCES_DIR/app"
APP_SUPPORT_DIR="$HOME/Library/Application Support/FindMyself"
VENV_DIR="$APP_SUPPORT_DIR/.venv"
DATA_DIR="$APP_SUPPORT_DIR/data"
LOG_FILE="$APP_SUPPORT_DIR/streamlit.log"
PID_FILE="$APP_SUPPORT_DIR/server.pid"
URL_FILE="$APP_SUPPORT_DIR/server.url"

mkdir -p "$APP_SUPPORT_DIR" "$DATA_DIR"

show_dialog() {
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"好\"} default button \"好\" with icon note" >/dev/null
}

show_error() {
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"好\"} default button \"好\" with icon caution" >/dev/null
}

shell_quote() {
  printf "%q" "$1"
}

if ! command -v python3 >/dev/null 2>&1; then
  show_error "未找到 Python 3。请先安装 Python 3.10–3.12，推荐 Python 3.11。"
  exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  INSTALL_SCRIPT="$APP_SUPPORT_DIR/install_find_myself.command"
  VENV_Q="$(shell_quote "$VENV_DIR")"
  BUNDLED_APP_Q="$(shell_quote "$BUNDLED_APP_DIR")"

  cat > "$INSTALL_SCRIPT" <<INSTALL
#!/bin/bash
set -e

echo "=== 照片里找自己：首次安装运行环境 ==="
echo
echo "这一步会在用户目录中创建虚拟环境："
echo "$VENV_DIR"
echo

python3 -m venv $VENV_Q
$VENV_Q/bin/python -m pip install --upgrade pip setuptools wheel
$VENV_Q/bin/python -m pip install --only-binary=insightface "insightface==1.0.1"
$VENV_Q/bin/python -m pip install -r $BUNDLED_APP_Q/requirements.txt

echo
echo "安装完成。请关闭这个窗口，然后重新打开“照片里找自己”。"
read -n 1 -s -r -p "按任意键关闭"
INSTALL

  chmod +x "$INSTALL_SCRIPT"
  /usr/bin/osascript -e 'display dialog "首次启动需要安装本地运行环境，可能需要几分钟。安装窗口打开后请等待完成，再重新打开应用。" buttons {"取消", "开始安装"} default button "开始安装" with icon note' >/dev/null
  /usr/bin/open -a Terminal "$INSTALL_SCRIPT"
  exit 0
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  EXISTING_URL="$(cat "$URL_FILE" 2>/dev/null || true)"
  if [ -n "$EXISTING_URL" ]; then
    /usr/bin/open "$EXISTING_URL"
    exit 0
  fi
fi

PORT="$("$VENV_DIR/bin/python" - <<'PY'
import socket

for port in range(8501, 8600):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("没有找到可用端口")
PY
)"

URL="http://127.0.0.1:$PORT"
echo "$URL" > "$URL_FILE"

export FIND_MYSELF_DATA_DIR="$DATA_DIR"
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

cd "$BUNDLED_APP_DIR"
nohup "$VENV_DIR/bin/python" -m streamlit run "$BUNDLED_APP_DIR/app.py" \
  --server.address 127.0.0.1 \
  --server.port "$PORT" \
  --server.headless true \
  --browser.gatherUsageStats false \
  > "$LOG_FILE" 2>&1 &

SERVER_PID="$!"
echo "$SERVER_PID" > "$PID_FILE"

for _ in $(seq 1 45); do
  if /usr/bin/curl -fsS "$URL" >/dev/null 2>&1; then
    /usr/bin/open "$URL"
    exit 0
  fi
  sleep 1
done

show_error "应用启动失败。日志位置：$LOG_FILE"
exit 1
LAUNCHER

chmod +x "$MACOS_DIR/find-myself"

echo "已生成：$APP_DIR"
echo
echo "双击打开：dist/$APP_NAME.app"
echo "首次启动会在 ~/Library/Application Support/FindMyself/ 创建运行环境和本地数据目录。"
