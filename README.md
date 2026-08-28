# YROLL AI

> 泛来源素材与工程的人机共创视频生产平台——让一个人成为一支视频生产团队。

## 文档

- **`YROLL-产品蓝图-整理终稿.md`** — 产品最终蓝图（所有设计决策以此为准，含被否定内容附录）
- **`YROLL-开发规划.md`** — 开发阶段与任务拆解
- **`docs/manifest-v0.1.md`** — 内部统一对象模型规范

## 当前状态：Phase 0 技术验证 Spike

素材 → AI 理解 → Project Memory 管线（纯 Python，无 GUI）：

```
Stage 0   媒体扫描（ffprobe，成本 0）
Stage 1   镜头切分（PySceneDetect）
Stage 2   关键帧抽取（每 Shot 首/中/尾）
Stage 2.5 ASR 转写（faster-whisper 本地，词级时间戳）
Stage 3.5 关键帧视觉描述（可选，需 YROLL_VISION_MODEL）
Stage 4   故事线建议（可选，需 YROLL_TEXT_MODEL）
```

## 使用

```bash
uv venv && uv pip install -e . && uv pip install opencv-python-headless pytest

# 扫描并理解素材目录
python -m yroll.cli.main ingest <素材目录> --name <项目名> --goal "视频目标"

# 选项
  --no-asr          跳过语音转写
  --no-story        跳过 LLM 故事线
  --whisper-model   whisper 模型规格（默认 small，本地 models/ 目录优先）
```

LLM 配置（BYOK，OpenAI 兼容 API）：

```bash
export YROLL_API_KEY=...
export YROLL_BASE_URL=https://...     # 可选
export YROLL_TEXT_MODEL=gpt-4o-mini   # Stage 4
export YROLL_VISION_MODEL=...         # Stage 3.5（不配则跳过）
```

输出：`<素材目录>/.yroll/<项目名>/memory.json`（Project Memory）+ `cache/keyframes/`。

## 测试

```bash
python -m pytest tests/
```
