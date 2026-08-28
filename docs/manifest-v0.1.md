# YROLL Manifest v0.1 — 内部统一对象模型

> 地位：**YROLL 的地基，第一天就要做对。** 所有系统（GUI / Harness / Adapter / 导出）都围绕它。
> 原则：Core 统一、extensions 自由扩展；"永远不要为了导入一个旧工程而污染 YROLL Core"。
> 本文档是规范说明；机器可读 schema 见 `yroll/core/manifest.schema.json`（Phase 1 实现）。

## 顶层结构

```
Project
├── id / name / created_at / intent { goal, audience, style }
├── assets[]          Asset        一切来源统一为 Asset（来源只是 Origin 属性）
├── timeline          Timeline     只记录最终作品结构（X 轴）
├── clips[]           Clip         时间轴上的使用实例
├── relationships[]   Relationship 语义关系图（与 Timeline 并列，不放 Timeline 里）
├── operations[]      Operation    一切有意义修改（不可变日志）
├── versions[]        Version      Git 式版本树（只存 diff）
├── problems[]        Problem      一级数据对象
├── solutions[]       Solution     一级数据对象（带 route/tool/cost）
├── generations[]     Generation   生成谱系（provider/model/prompt/references/cost）
├── ai_context        AIContext    Y 轴所需，与 Clip 绑定
├── publishing        Publishing   上传前成品包
└── extensions        {}           jianying/premiere/comfyui/... 来源特定数据隔离
```

## Asset（素材）

```json
{
  "asset_id": "a1b2c3...",
  "type": "video | image | audio | subtitle | document | reference",
  "origin": "camera | generated | screen_record | unknown",
  "path": "当前已知路径（可失效）",
  "identity": {
    "md5": "...", "size_bytes": 0, "duration_sec": 0,
    "width": 0, "height": 0, "created_at": "..."
  },
  "history_paths": ["曾经的位置（素材找回用）"],
  "understanding": { "caption": "", "tags": [], "embedding_ref": "" }
}
```

## Clip（时间轴上的使用实例）

```json
{
  "clip_id": "c001",
  "asset_id": "a1b2c3...",
  "source_range":   { "start": 12.4, "end": 16.8 },
  "timeline_range": { "start": 0.0,  "end": 4.4 },
  "track_id": "v1",
  "current_state": { "version_id": "v5", "transform": {}, "adjustments": [] },
  "context": { "story_role": "", "scene_id": "", "emotion": "", "intent": "", "importance": 0 },
  "relationships": ["r1", "r2"],
  "versions": ["v1", "v2", "..."],
  "capabilities": ["trim", "color", "mask", "regenerate", "...（按资产类型动态生成）"]
}
```

## Timeline（X 轴，只记录最终作品结构）

```json
{
  "timeline_id": "main",
  "tracks": [
    { "track_id": "v1", "kind": "video", "clip_ids": ["c001"] },
    { "track_id": "a1", "kind": "audio", "clip_ids": [] },
    { "track_id": "t1", "kind": "text",  "clip_ids": [] }
  ],
  "duration": 30.0
}
```

## Relationship（语义关系图，独立于 Timeline）

```json
{
  "relation_id": "r1",
  "source": "c001", "target": "c007",
  "relation": "strong | medium | weak | independent",
  "kind": "voice_of | caption_of | bgm_of | sfx_of | ...",
  "confidence": 0.98,
  "scope": { "source_range": [0, 4.4], "target_range": [0, 4.4] },
  "reason": "字幕内容与该 clip 人声逐字匹配"
}
```

## Operation（一切有意义修改，不可变）

```json
{
  "operation_id": "op1001",
  "who": "human | ai | agent:<name>",
  "at": "2026-08-23T...",
  "type": "trim | split | move | transform | adjust | generate | inpaint | ...",
  "target": "c001",
  "time_range": [2.1, 4.3],
  "region": { "x": 120, "y": 80, "w": 300, "h": 200, "feather": 20 },
  "parameters": {},
  "before": {}, "after": {},
  "why": "用户：这个壶太大",
  "tool": "video.transform", "model": null, "cost": 0.0,
  "approved_by": "human | auto"
}
```

## Version（Git 式，不复制素材）

```json
{
  "version_id": "v5",
  "parent": "v4",
  "operations": ["op0998", "op1001"],
  "note": "缩小茶壶 30%",
  "created_at": "..."
}
```

## Problem / Solution（一级数据对象）

```json
{
  "problem_id": "p001",
  "target_clip": "c001",
  "time_range": [2.1, 4.3],
  "region": null,
  "category": "spatial_object | temporal | audio | text | visual | semantic | consistency",
  "description": "茶壶太大挡住字幕",
  "source": "human | ai_review | data_feedback",
  "severity": 2, "confidence": 0.95
}
```
```json
{
  "solution_id": "s01",
  "problem_id": "p001",
  "route": "L0_transform | L1_local_ai | L2_cloud_ai | L3_regenerate",
  "tool": "object.transform",
  "params": { "scale": 0.7 },
  "cost": 0.0, "duration_ms": 200,
  "risk": "low", "reversible": true,
  "selected": true
}
```

## Generation（生成谱系）

```json
{
  "generation_id": "g01",
  "clip_id": "c003",
  "provider": "comfyui | kling | local",
  "model": "...", "prompt": "...",
  "references": ["asset_id..."],
  "workflow": {}, "cost": 0.18, "duration_ms": 40000,
  "review": { "status": "accepted | rejected | pending", "by": "human" }
}
```

## Publishing（成品包，不是只导出 MP4）

```json
{
  "video_versions": [{ "platform": "douyin", "profile": "9:16-30s", "output": "..." }],
  "cover": { "asset_id": "...", "generated": false },
  "title": "", "description": "", "tags": [],
  "platform_copy": { "xiaohongshu": "...", "douyin": "..." },
  "cost_report": { "total": 3.82, "per_minute": 1.52, "human_hours_saved": 2.5 }
}
```

## 工程目录布局

```
MyProject/
├── current.json          # 当前状态（本 Manifest 的序列化）
├── operations/           # op0001.json ... 不可变操作日志
├── versions/             # v1.json ... 版本树
├── memory.db             # SQLite：理解索引/向量/检索
├── media/                # 素材（或外链 + Asset Identity 指纹）
├── cache/                # proxy / keyframes / 临时（可清理）
└── generated/            # 确认使用的生成结果
```

## 版本策略

- Manifest 版本字段 `manifest_version: "0.1"`；向后兼容靠 migration 函数链。
- extensions 内的数据不参与 Core 校验。
