# Windows Release

本文档描述当前 Tauri Windows 客户端的发布方式。

## 当前产物

Windows 发布由 GitHub Actions 在 `windows-latest` runner 上构建，产物为 NSIS `.exe` 安装器。

当前测试版限制：

- 目标架构为 Windows x64；
- 安装器未做代码签名；
- 普通用户首次安装可能看到 SmartScreen 提示；
- 首次真正执行识别时，仍可能需要联网下载 InsightFace 模型权重；
- 模型权重不随安装器再分发，仍遵循 [MODEL_LICENSE.md](../MODEL_LICENSE.md)。

## 本地构建

本地构建需要：

- Node.js / npm
- Rust 工具链
- Python 3.11
- NSIS

构建命令：

```bash
npm install
npm run tauri:build:windows
```

构建完成后，安装器位于：

```text
desktop/tauri/src-tauri/target/release/bundle/nsis/
```

## 发布流程

推送 `v*` 标签会触发 `.github/workflows/release-desktop.yml`，同时生成 macOS 和 Windows 安装包，并上传到同一个 GitHub Release。

示例：

```bash
git tag v0.2.3
git push origin v0.2.3
```

## 正式分发前需要补齐

面向普通用户公开分发前，Windows 版建议补齐：

- 购买或申请代码签名证书；
- 在 GitHub Actions 中配置签名证书密钥；
- 对 NSIS 安装器签名；
- 在 Windows 10 / Windows 11 上做安装、启动、索引、检索、导出回归测试。
