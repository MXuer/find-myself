# macOS 与 Windows 客户端设计

## 产品定位

目标用户手里有一批多人照片，例如毕业照、团建照、会议照、活动照，希望上传或选择一张自己的清晰参考照，
然后在本地照片合集里找出包含自己的照片。

第一版客户端应保持三个原则：

- 本地优先：照片、索引、人脸向量默认只保存在用户设备上；
- 易解释：结果展示相似度、匹配人脸框和原图位置，用户需要人工确认；
- 可替换模型：先使用 InsightFace `buffalo_l` 原型验证，同时把模型层封装出来，便于未来替换为可商用模型。

## 推荐技术路线

建议采用同一套 Python 识别核心，加两个轻量客户端壳：

```text
apps/
  desktop/
    tauri-ui/              # Tauri + React/TypeScript 桌面 UI
  engine/
    face_finder/           # Python 核心：导入、建库、检索、导出
    cli.py                 # 本地引擎命令入口
```

客户端：

- macOS：Tauri `.app`，支持 Apple Silicon / Intel；
- Windows：Tauri `.msi` 或 `.exe` 安装包；
- UI：React + TypeScript；
- Python 引擎：PyInstaller 打包为随应用分发的本地二进制；
- 通信方式：前期用子进程 JSON-RPC/stdin-stdout，后期可升级为本地 HTTP 或 gRPC。

为什么不是直接把 Streamlit 打包成客户端：

- Streamlit 很适合 Demo，但原生文件选择、后台任务、进度恢复、系统托盘、自动更新和安装包体验较弱；
- Tauri 体积小，系统集成好，macOS/Windows 可共用大部分 UI；
- Python 引擎可以最大限度复用当前原型代码。

## 核心信息架构

### 首页 / 照片库

- 当前照片库概览：照片数、人脸数、索引大小、最近更新时间；
- 添加照片：
  - 选择文件夹；
  - 拖入照片；
  - 追加导入；
- 建库任务：
  - 显示扫描进度、已处理数量、跳过重复、未检测到脸、失败文件；
  - 支持暂停、继续和取消；
  - 建库完成后保留报告。

### 搜索

- 选择参考照；
- 自动裁剪参考人脸；
- 若参考照多人，展示所有检测到的人脸，让用户点选目标人；
- 阈值与返回数量；
- 结果网格：
  - 原图缩略图；
  - 匹配人脸框；
  - 相似度；
  - 原文件名和所在目录；
  - 标记“是我 / 不是我”。

### 导出

- 选择导出目录；
- 导出全部候选或只导出勾选结果；
- 保留原始格式和元数据；
- 生成 `匹配结果.json`；
- 一键打开导出目录。

### 设置

- 模型状态：未下载、已下载、版本、缓存位置；
- 数据位置：照片副本、缩略图、索引；
- 隐私操作：清空索引、清空照片副本、清空全部数据；
- 性能选项：检测尺寸、批处理大小、CPU 线程数；
- 许可说明：代码协议、模型权重协议、非商业研究用途提醒。

## 本地数据模型

建议从当前 `metadata.json + face_index.npz` 演进为 SQLite + 向量文件：

```text
Library
- id
- root_path
- created_at
- updated_at

Photo
- id
- content_hash
- original_path
- stored_path
- original_name
- width
- height
- imported_at

Face
- id
- photo_id
- bbox_x1
- bbox_y1
- bbox_x2
- bbox_y2
- embedding_offset
- thumb_path
- detector_name
- recognizer_name
- created_at

SearchRun
- id
- reference_hash
- threshold
- created_at

SearchResult
- search_run_id
- face_id
- score
- user_feedback
```

向量可继续使用 NumPy 矩阵；到十万级以上再接入 FAISS / hnswlib。

## 引擎 API 草案

客户端只调用稳定命令，不直接碰模型对象：

```json
{"method":"library.scan","params":{"folder":"/path/to/photos","recursive":true}}
{"method":"library.index","params":{"items":[...],"library_id":"default"}}
{"method":"search.reference_faces","params":{"image_path":"/path/to/me.jpg"}}
{"method":"search.run","params":{"face_id":"ref-1","threshold":0.38,"limit":60}}
{"method":"export.copy","params":{"result_ids":[...],"target_dir":"/path/to/export"}}
{"method":"library.reset","params":{"scope":"index_only"}}
```

所有长任务返回 `job_id`，客户端订阅进度事件：

```json
{"event":"job.progress","job_id":"...","done":120,"total":800,"message":"正在检测人脸"}
```

## 打包策略

### macOS

- 架构：`arm64` 和 `x64` 分别构建；
- 格式：`.dmg` 或 `.app.zip`；
- 签名：Developer ID Application；
- 公证：Apple notarization；
- 权限：
  - 访问用户选择的文件夹；
  - 不默认扫描全盘；
  - 模型缓存和索引放在 `~/Library/Application Support/FindMyself/`。

### Windows

- 架构：`x64` 起步；
- 格式：`.msi` 或 NSIS `.exe`；
- 签名：代码签名证书；
- 数据目录：`%APPDATA%/FindMyself/`；
- 注意事项：
  - Windows Defender 可能对新打包的 Python/ONNX 二进制更敏感，需要签名和稳定发布渠道；
  - 文件路径要完整支持中文、空格和长路径。

## 版本路线图

### v0.1：当前 Demo 开源化

- 保留 Streamlit；
- 补齐 LICENSE、模型许可、隐私提醒；
- GitHub 公共仓库；
- 明确“不分发模型权重”。

### v0.2：核心引擎拆分

- 从 `app.py` 拆出 `face_finder` Python 包；
- 增加 CLI；
- 增加最小单元测试；
- 保持 Streamlit 作为开发调试 UI。

### v0.3：桌面客户端 MVP

- Tauri 原生窗口；
- Python 运行环境由桌面端负责安装和启动；
- 当前 UI 仍复用现有 Streamlit 检索页面，直接在桌面窗口中打开；
- 数据目录迁移到用户级应用数据目录；
- 仍不默认随安装包分发 `buffalo_l` 模型权重。

### v0.4：体验与可靠性

- 任务暂停/恢复；
- 多参考照融合；
- “是我 / 不是我”反馈；
- SQLite 数据库；
- 自动更新。

### v1.0：可商用准备

- 替换或授权商用模型；
- 完整隐私政策；
- 数据删除与导出；
- 签名、公证、安装器；
- 性能压测和崩溃上报开关。
