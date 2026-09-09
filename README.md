# slbb-chatcut-oneshot

> One-click editing for 9:16 vertical talking-head videos.
> 一键剪辑 9:16 竖屏口播短视频（单条 / 批量自适应）。

## What it does / 它能做什么

Drop in a talking-head clip (or a folder of them), and it auto-edits to a publish-ready 9:16 short with a fixed recipe:

- Trim pauses / filler / mistakes / dead air; **cut the opening silence so the first frame already speaks**
- Speed up the whole timeline at 1.1×
- Cover with full-screen B-Roll + a real-person PiP in the top-right corner (landscape sources fit via `cover`)
- Single-line black-on-white Simplified Chinese subtitles (overflow → split by semantics, never wrap)
- Lay a pre-mixed BGM bed (BGM + opening SFX) with duck `-6 dB` and gain `+6 dB`
- Export 1080P H.264 to your Desktop

中文流程同上：删废话停顿、1.1× 提速、全屏 B-Roll + 真人画中画、单行黑底白字字幕、铺背景音频、1080P H.264 导出。

## Modes / 模式

**Single / 单条** — feed one video → one project → one finished file.

**Batch / 批量** — feed a parent folder → numbered subfolders queue up → one project per video (to prevent cross-contamination) → a final manifest with per-clip status.

Batch folder layout / 批量文件夹结构：

```
口播批量-<主题>/
├── 背景音频.mp3          # 全批共用（可选，缺则问用户要）
├── broll/                # B-Roll 池 3~5 个（可选）
├── 01_<主题>/
│   ├── 主视频.mp4        # 必填，每文件夹唯一
│   └── 文案.txt          # 可选，有则字幕/删废话更准
├── 02_<主题>/
└── ...
```

B-Roll picking rule / B-Roll 数量挑选：

| 成片时长 | B-Roll 数量 |
|---|---|
| ≤ 15 秒 | 1 |
| 15 ~ 40 秒 | 2 |
| > 40 秒 | 3（封顶） |

## How to use / 怎么用

1. Open **ChatCut Desktop** (this skill drives its MCP tools; the desktop window must be running)
2. Drop your video (or batch parent folder) into ChatCut
3. Invoke this skill — the prompt seed is in `agents/openai.yaml`, the full rules in `SKILL.md`
4. Finished files land on your Desktop; ffprobe verifies codec / resolution / duration after each export

## File structure / 文件结构

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 主入口：模式识别、共享固定参数、单条 / 批量流程、字幕硬规则 |
| `agents/openai.yaml` | OpenAI Agents 协议声明（`display_name` / `default_prompt`） |
| `references/technical-guardrails.md` | 执行层技术护栏：转写、改速、B-Roll / 画中画、字幕、音频、像素验证、导出 |

## Prerequisites / 前置依赖

- **ChatCut Desktop** running with the window open
- ChatCut official skills loaded per stage: `chatcut:transcription`, `chatcut:talking-head-guide`, `chatcut:visual-analysis`, optionally `chatcut:music`
- **FFmpeg / ffprobe** for post-export validation only (not used to render)

## Things you should NOT change without re-validating / 不要乱改这些固定值

这些值是反复踩坑才定下来的"够用值"。改了不验证整套管线很容易翻车。

| 参数 | 固定值 | 踩过的坑 |
|---|---|---|
| 画幅 / fps | 9:16 / 1080×1920 / 30fps | 改了字幕框 / 画中画位置 / B-Roll 适配全要重算 |
| 改速 | 1.1× | 太快会变声，太慢省不下来 |
| 字幕同时存在 | 屏幕上一行 | 一屏两行会被字幕框压扁 |
| 字幕超屏处理 | 不断行，按语义断句 | 换行会丢语义边界 |
| 画中画 | 右上角 360×640 静音 | 挡字幕 / 手势 / 表情 |
| BGM `duckDepthDb` | `-6`（**必须显式传**） | 不传会被自动 duck 到约 `-13 dB`，BGM 全程听不见 |
| BGM `decibelAdjustment` | `+6` | 之前 `+3` 还不够响 |
| 导出 | 1080P / H.264 / 30fps | 其他格式 / 编码容易出兼容问题 |

## See also / 延伸阅读

- [`SKILL.md`](./SKILL.md) — full rules, fixed parameters, single / batch flows
- [`agents/openai.yaml`](./agents/openai.yaml) — agent manifest
- [`references/technical-guardrails.md`](./references/technical-guardrails.md) — AI executor guardrails