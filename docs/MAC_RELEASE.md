# macOS 发布说明

本文档描述当前 Tauri macOS 客户端的发布流程，以及把测试版 `.dmg` 变成普通用户可直接安装版本所需的签名与公证步骤。

## 当前产物

本仓库当前可生成：

- `dist/Find Myself_0.2.0_arm64.dmg`
- `desktop/tauri/src-tauri/target/release/bundle/macos/Find Myself.app`

当前构建特性：

- 面向 Apple Silicon (`arm64`)
- 安装包内置 Python 后端与依赖
- 目标机器不需要预装 `python3`
- 首次真正执行识别时仍会本地下载 InsightFace 模型
- 当前默认只有 ad-hoc 签名，不适合直接面向普通用户分发

## 为什么还不算最终公开版

普通 Mac 用户从互联网下载应用时，macOS 主要看两件事：

1. `Developer ID Application` 签名
2. Apple notarization 公证

没有这两项时，应用通常会被 Gatekeeper 拦截，需要用户手动绕过“无法验证开发者”提示。这不符合“普通用户可安装”的目标。

## 本机发布前提

要出正式对外分发包，构建机器必须具备：

- Apple Developer Program 账号
- 已安装的 `Developer ID Application` 证书
- `xcrun notarytool` 可用
- 已配置的 notarytool keychain profile

检查本机证书：

```bash
security find-identity -v -p codesigning
```

如果输出里没有 `Developer ID Application:`，当前机器只能生成测试版，不能生成正式公众分发版。

## 生成测试版 DMG

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY npm run tauri:build:dmg
```

输出：

```text
dist/Find Myself_0.2.0_arm64.dmg
```

这个产物适合开发测试和受控分发，不适合直接公开下载。

## 正式签名与公证

仓库提供脚本：

```text
packaging/macos/sign_and_notarize.command
```

使用前设置环境变量：

```bash
export FIND_MYSELF_APPLE_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export FIND_MYSELF_NOTARY_PROFILE="find-myself-notary"
```

然后执行：

```bash
./packaging/macos/sign_and_notarize.command
```

脚本会执行：

1. 对 `.app` deep sign
2. 对 `.app` 做 `codesign --verify`
3. 对 `.app` 做 `spctl` 评估
4. 重新生成用于发布的 `.dmg`
5. 提交 `.dmg` 到 Apple notarization
6. 将 notarization ticket staple 到 `.app` 和 `.dmg`
7. 再次做 `spctl` 校验

## notarytool profile 示例

先在本机配置一次：

```bash
xcrun notarytool store-credentials "find-myself-notary" \
  --apple-id "you@example.com" \
  --team-id "TEAMID" \
  --password "app-specific-password"
```

之后脚本即可通过 `FIND_MYSELF_NOTARY_PROFILE` 读取该配置。

## 最终交付检查

正式发布前至少应验证：

```bash
codesign -dv --verbose=2 "dist/Find Myself.app"
codesign --verify --deep --strict --verbose=2 "dist/Find Myself.app"
spctl --assess --type open --verbose=4 "dist/Find Myself.app"
spctl --assess --type open --verbose=4 "dist/Find Myself_0.2.0_arm64.dmg"
```

此外还应在一台未装开发环境、未信任本机构建产物的干净 Apple Silicon Mac 上下载并打开一次。
