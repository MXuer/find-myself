# 模型与第三方许可说明

本项目代码采用 MIT License 开源，详见 [LICENSE](LICENSE)。

重要：代码协议不等于模型权重协议。本项目默认通过 `insightface` Python 包加载
`buffalo_l` 模型包，该模型包会在首次使用时由 InsightFace 自动下载到本机缓存目录：

```text
~/.insightface/models/
```

## InsightFace / buffalo_l

根据 InsightFace 官方仓库 README 的 License 说明：

- InsightFace 代码采用 MIT License；
- 训练数据及由这些数据训练得到的模型仅限非商业研究用途；
- 手动下载的模型和通过 Python 包自动下载的模型都遵循同一模型许可政策；
- 对 `buffalo_l` 等开源人脸识别模型的额外授权，应联系 InsightFace 官方许可邮箱。

官方来源：

- https://github.com/deepinsight/insightface#license
- https://github.com/deepinsight/insightface/tree/master/model_zoo

因此，本仓库不会提交、镜像或再分发 `buffalo_l` 模型权重。用户首次运行时如果选择使用
InsightFace 默认模型，需要自行确认其使用场景符合 InsightFace 的模型许可。

## 使用边界

本项目适合：

- 本地原型验证；
- 毕业照、活动照、团建照等个人或研究性质的照片检索；
- 非商业研究和技术评估。

商业化、收费服务、企业内部生产部署或面向第三方交付前，请先完成以下至少一项：

- 获得 InsightFace / `buffalo_l` 对应模型权重的明确商业授权；
- 替换为自训练、采购或明确允许商业使用的人脸检测与识别模型；
- 更新本文档和 README，准确说明替换后的模型、训练数据来源和授权条款。

## 隐私与合规提醒

本项目处理人脸特征向量和照片副本。即使默认只在本机运行，也应获得照片相关人员的知情同意，
并遵守所在地关于生物识别信息、个人信息保护、数据保留和删除的法律法规。

本说明不是法律意见。如需商业发布或大规模使用，请咨询专业法律顾问。
