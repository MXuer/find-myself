# 照片里找自己

一个面向毕业照、团建照和活动照片合集的本地人脸检索原型。

## 功能

- 批量导入照片
- 检测每张照片中的多张人脸
- 本地提取 512 维人脸向量
- 上传一张参考照，以人搜图
- 按相似度返回候选照片
- 在原图中画框显示匹配人脸
- 下载匹配原图副本
- 所有业务数据保存在本机

## macOS 桌面版

当前仓库已经可以生成一个 `Apple Silicon` Mac 用的桌面安装包：

```text
dist/Find Myself_0.2.1_arm64.dmg
```

当前桌面版状态：

- 安装包内置 Python 人脸检索引擎与依赖；
- 目标机器不需要预装 `python3`；
- 桌面窗口直接渲染原生 Tauri UI，不再依赖 Streamlit 页面；
- 首次真正执行识别时，仍会在本机下载 InsightFace 模型；
- 当前构建默认只有 ad-hoc 签名，还没有完成 Apple Developer ID 签名与 notarization。

这意味着它已经适合开发测试和受控分发，但还不能算“普通用户下载后无拦截直接安装”的最终公开版。

要构建桌面版：

```bash
npm install
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY npm run tauri:build:dmg
```

更多发布细节见 [docs/MAC_RELEASE.md](docs/MAC_RELEASE.md)。

## Windows 桌面版

当前也支持在 Windows x64 上生成 NSIS 安装器。Windows 构建必须在 Windows 环境中完成，推荐使用 GitHub Actions：

```bash
npm install
npm run tauri:build:windows
```

发布标签 `v*` 会触发 GitHub Actions，同时构建：

- macOS Apple Silicon `.dmg`
- Windows x64 `.exe` 安装器

当前 Windows 构建同样是未签名测试版，因此普通用户下载后可能看到 SmartScreen 提示。更多细节见 [docs/WINDOWS_RELEASE.md](docs/WINDOWS_RELEASE.md)。

## Python 原型最快启动方式

### 1. 安装 Python

推荐 Python 3.11。

在终端确认：

```bash
python3 --version
```

### 2. 安装依赖

在 Finder 中进入本项目文件夹，右键 `setup.command`，选择“打开”。

也可在终端执行：

```bash
cd mac-face-photo-finder-demo
chmod +x setup.command start.command
./setup.command
```

### 3. 启动

双击 `start.command`，或执行：

```bash
./start.command
```

浏览器会打开：

```text
http://localhost:8501
```

### 旧版 macOS App 壳

也可以生成一个可双击的 macOS app：

```bash
./packaging/macos/build_app.command
```

生成后双击：

```text
dist/Find Myself.app
```

首次启动会在以下位置创建运行环境和本地数据目录：

```text
~/Library/Application Support/FindMyself/
```

这个 app 当前是 macOS 客户端壳：负责安装/启动本地 Python 引擎，并打开本机页面。
它不上传照片，Streamlit 服务仍只监听 `127.0.0.1`。

### 原生 Tauri 客户端

仓库中也提供了原生 Tauri 客户端工程：

```text
desktop/tauri/
```

当前实现：

- 用 Tauri 原生窗口承载应用；
- 安装包内置 Python 人脸检索引擎与依赖；
- 前端直接通过 Tauri command 调用本地引擎，不再启动 Streamlit；
- 把运行时、日志和业务数据写到用户目录，而不是 app bundle；
- 当前界面为深色照片优先布局，包含建库、检索、结果网格和右侧检查面板。

常用命令：

```bash
npm install
npm run tauri:dev
npm run tauri:build
```

本机构建前提：

- Node.js / npm
- Rust 工具链
- macOS 上可用的 `python3`，仅构建机需要；最终用户不需要

目前默认不把 `InsightFace buffalo_l` 模型权重随安装包分发；首次真正使用识别时，模型仍按
InsightFace 现有方式在本机下载。这是为了避免与当前 [MODEL_LICENSE.md](MODEL_LICENSE.md)
中的“不再分发模型权重”策略冲突。

当前发布限制：

- 当前只产出 `arm64` 安装包；
- 当前机器没有 `Developer ID Application` 证书，因此产物未完成正式签名与公证；
- 没有签名/公证时，普通用户可能会遇到 Gatekeeper 拦截。

### 4. 使用

1. 打开“建立照片库”。
2. 选择一批照片并建立索引。
3. 打开“找到我的照片”。
4. 上传一张清晰参考照。
5. 调整相似度阈值并检索。

## macOS 安全提示

首次双击 `.command` 文件时，macOS 可能阻止运行。可在 Finder 中：

1. 右键脚本；
2. 选择“打开”；
3. 在弹窗中再次确认。

## 数据位置

```text
data/
├── photos/          # 导入照片的本地副本
├── thumbs/          # 检测到的人脸缩略图
├── face_index.npz   # 人脸向量
└── metadata.json    # 文件名和人脸位置
```

InsightFace 模型默认缓存在：

```text
~/.insightface/models/
```

删除 `data/` 中内容即可清除照片索引；页面侧栏也提供“清空本地索引”。

## 技术说明

- Python 原型 UI：Streamlit
- 桌面 UI：Tauri + 原生前端页面
- 人脸检测与向量：InsightFace `buffalo_l`
- 推理：ONNX Runtime CPU
- 相似度：归一化向量的点积，即余弦相似度
- 索引：NumPy 压缩矩阵

当前方案没有远程后端。Python 原型通过本地 Streamlit 服务运行；桌面版通过 Tauri 子进程直接调用内置引擎。

## 开源协议与模型许可

本项目代码采用 MIT License 开源，详见 [LICENSE](LICENSE)。

请注意：代码开源协议不等于模型权重协议。本项目默认使用 InsightFace Python 包自动下载的
`buffalo_l` 模型包。根据 InsightFace 官方说明，InsightFace 代码采用 MIT License，
但训练数据及由这些数据训练得到的模型仅限非商业研究用途，手动下载和自动下载的模型都遵循该模型许可政策。

本仓库不会提交或再分发 `buffalo_l` 模型权重。商业化、收费服务、企业内部生产部署或向第三方交付前，
请先获得对应模型商业授权，或替换为明确允许商用的模型。详见 [MODEL_LICENSE.md](MODEL_LICENSE.md)。

## 桌面客户端规划

当前已实现 Tauri macOS 客户端第一版，并已去掉桌面版对 Streamlit 的依赖。后续 macOS 与 Windows 的共同方向仍建议采用：

- Tauri + 前端 UI 作为跨平台桌面界面；
- Python 引擎封装当前人脸检测、索引、检索和导出逻辑；
- PyInstaller 分别打包 macOS / Windows 本地引擎；
- 客户端与引擎通过本地子进程 JSON/stdout 通信。

详细方案见 [docs/CLIENT_DESIGN.md](docs/CLIENT_DESIGN.md)。

## 已知限制

- 第一次使用需要联网下载模型。
- 模型下载后可以离线使用。
- 大型合照的小脸可能漏检。
- 微信等渠道压缩后的照片会降低效果。
- 参考照中多人时，默认选择面积最大的人脸。
- 数万级人脸尚可；几十万级建议使用 FAISS。
- 匹配结果必须人工确认，不能用于身份认证或高风险决策。

## 模型许可

InsightFace Python 代码采用 MIT 许可，但其官方提供、自动下载的预训练模型仅限非商业研究用途。

此 Demo 适合原型验证。正式收费或商业部署前，应：

- 获取明确的模型商业许可；或
- 替换为自训练、采购或明确允许商用的 ONNX 权重。

## 后续改进建议

- 支持多张参考照并融合向量
- 增加“是我 / 不是我”反馈
- 采用分块和多尺度检测改善毕业照小脸
- 使用 FAISS 做大规模向量检索
- 直接读取本地文件夹，避免复制原图
- 打包为原生 `.app`


## v2 安装修复

v1 使用 `insightface==0.7.3`，Apple Silicon 上可能触发本地 C++ 编译并报：

```text
fatal error: 'cmath' file not found
ERROR: Failed building wheel for insightface
```

v2 使用 `insightface==1.0.1` 的通用 Python wheel，并禁止回退到源码编译。
解压后直接双击 `setup.command`；脚本会删除失败残留的 `.venv` 并重新安装。


## v3 交互优化

- 检索结果支持“一键导出全部匹配原图”。
- 每次导出创建独立目录，并自动在 Finder 中打开。
- 导出目录包含 `匹配结果.json`，记录文件名和相似度。
- 建库完成后保留更新结果卡片，不再立即恢复成未更新状态。
- 文件选择改为“待处理列表”：
  - 一批一批追加照片；
  - 不需要删除前一批再重新选择；
  - 最后统一建立或更新索引。


## v4 文件夹扫描

建立照片库页面新增“选择本地文件夹（推荐）”：

- 调用 macOS 原生 Finder 文件夹选择框；
- 可递归扫描全部子目录；
- 自动查找 JPG、JPEG、PNG、WEBP、BMP、TIF、TIFF；
- 只把路径加入待处理列表，不会一次性把整个文件夹读入内存；
- 建索引时按图片内容哈希跳过已有照片；
- 保留原有的手动多批次上传模式。

现有 `data/` 索引可直接沿用。


## v5：HEIC 与自定义导出目录

### HEIC / HEIF

- 文件夹扫描、手动导入和参考照片均支持 `.heic`、`.heif`。
- 使用 `pillow-heif` 在本机解码。
- 建库时保存原始 HEIC 文件，不转换为 JPEG。
- 导出时复制原始文件，保留 HEIC 格式和元数据。
- 图片方向会根据 EXIF 自动纠正后再进行人脸检测。

### 导出目录

- 检索后必须先选择或输入导出目标文件夹。
- 应用会在目标文件夹下创建独立的时间戳目录。
- 未指定有效目录时，导出按钮保持禁用。
- 导出完成后自动在 Finder 中打开新目录。
