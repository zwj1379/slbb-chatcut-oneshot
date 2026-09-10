# 技术护栏（AI 执行层）

本文件保存剪辑过程中 AI 必须遵守的技术操作护栏。小白不需要读，AI 执行时按需查阅。

## 能力来源

执行时按阶段加载 ChatCut 官方 Skill，全流程至少使用 `chatcut:transcription`（转写）、`chatcut:talking-head-guide`（B-Roll/画中画）与 `chatcut:visual-analysis`（像素验证），按阶段补充 `chatcut:music`（BGM）。导出使用 MCP 工具 `local_export`，无独立 Skill。

## 1. 错误恢复（429 / 5xx / 超时 / 不确定回执）

1. 立即停止同类连续调用，记录错误。
2. 写入类或可能异步落盘的调用，先读回目标 item/track/job 是否已保存，不要盲目重试。
3. 做一次轻量健康探针（项目摘要或目标时间线）。
4. 探针成功且确认未落盘时，同参数最多重试一次；探针失败或重试仍失败，停下报告明确阻塞。
5. MCP 可能把 `tool call error`、HTTP 5xx 包在普通 `content[].text` 里，批处理必须展开业务正文，同时检查成功字段和错误文本，不能只靠 try/catch。

## 2. 项目发现与 ID

- 所有 ID 视为 opaque，只使用工具返回的完整 ID、前缀或当前 alias。
- 每轮按 `summary -> timelines/timeline -> track/item` 分阶段发现结构。
- Targeted item detail 只传 projectId + itemId，不与 timeline/track/frame filter 混用。
- 继续旧项目时刷新轨道别名、角色、隐藏/静音状态和目标 item，不复用旧标签对象。

## 3. 导入与转写

- 本地素材使用官方 import session/helper，超过单批上限时重新建 session。
- Helper 的 `transcription.status` 是局部字段，不代表最终 ASR 状态。
- 进入 Script/字幕前用 `track_progress(target="transcription")` 确认 terminal complete。
- 导出和云端帧验证前确认素材 upload ready / cloud-readable，不把已注册但未上传完成的素材视为可渲染。

## 4. A-Roll 与改速

- spoken-content 只通过 Script 路径处理（`read_script -> 编辑 timeline.md -> apply_script`），不用 `find_transcript + split/edit_item` 代替语义剪辑。
- 开头气口（开口前的吸气、停顿、空白）必须剪干净，成片第一帧就开始说话；结尾空白尾音一并删掉。
- 剪气口的正确姿势：`read_script({showSilence:true})` 才能在 timeline.md 里看到 `[silence=Ns]` 标记（默认隐藏）。开头第一个字之前的气口是 `[silence=0.98s]` 之类，strike 成 `~~[silence=0.98s]~~`，结尾同理，再 `apply_script`。气口长度可用 `inspect_asset` 的 `transcriptRangesMs` 拿逐字时间戳确认（第一个字的 startMs 即气口终点）。
- 改速前读取 `sourceStartFromInSeconds`、素材时长、fps 和目标倍率。片段预计消耗源时长为 `durationInFrames / fps * playbackRate`；源起点加预计消耗超过素材结尾时，先缩短 duration 或降低倍率，再 `validateOnly`，不直接提交越界范围。
- 多片段统一改速固定顺序：
  1. 批量 `playbackRate` 更新，`ripple=false`。
  2. 读回代表 item / 全批计数。
  3. `edit_track(action="tighten")`。
  4. 读回全轨起止帧、连续性和总时长。
- 不把多片段 playback-rate 更新与 `ripple:true` 组合。
- 1.1x 是固定值，直接执行；不自然时保留原速并报告。

## 5. B-Roll 与画中画

- 放置前明确模式：全屏切片、普通画中画，或「全屏 B-Roll + 同步真人小窗」。
- B-Roll 自带音频默认静音，不参与主混音，读回实际增益/静音状态。
- **B-Roll 的位置/时长调整用 `edit_item updates [{id, fromFrame, durationInFrames}]`，不是 apply_script**（B-Roll 是视觉层，非 transcript 语义剪辑）。起点/终点按 A-Roll 对应句子的源时间换帧：源秒 ×(1/playbackRate)×fps，或直接用 `preview_timeline` 读回 item 的 range。
- B-Roll 默认插在用户指定的句子之后，不是开头；开头必须是 A-Roll 真人。
- 「全屏 B-Roll + 同步真人小窗」低自由度顺序：
  1. B-Roll 覆盖目标语义范围并占满画布（V2 轨道，`fit:"cover"`）。
  2. **新建 V3 视频轨**（在 V2 之上），从 A-Roll 源素材添加画中画 item；**按 V1 的 item 边界拆分**，逐段保持与 V1 相同的 `sourceStartFromInSeconds` 和 `playbackRate`。
  3. 画中画参数（竖屏 1080×1920）：
     - 尺寸：`width:360, height:640`（9:16 比例，不裁切）
     - 位置：`left:684, top:120`（距右 36px、距上 120px，右上角）
     - 静音：`decibelAdjustment:-60`
  4. 画中画源时间计算：
     - timeline 帧 96（B-Roll 起点）→ 源 = V1 第一段 sourceStart + 96/30×1.1（若 V1 第一段从 frame 0 开始）
     - 更安全的做法：直接用 `preview_timeline` 读回 V1 item 的 `source` 范围，取对应帧的源起点；跨 V1 item 切割点时，逐段分别设置 sourceStartFromInSeconds。
  5. 真人副本音频不得与主口播重复混音；读回实际音量/分离状态。
  6. 切入、稳定段和退出帧都要 `preview_timeline` 截图打开像素，确认画中画不挡字幕、人脸、手势。
- `fromItemId` 复制会继承裁切和视觉字段；若 `fit` 与继承 crop 冲突，停止同参数重试，选择「明确矩形、不传 fit」或「先清除冲突 crop 再设 fit」，并先预检。

## 6. 背景音频

- **音源优先级**：用户上传了背景音频就用用户的；没上传就用技能内置默认 `assets/bgm.mp3`（45.6 秒，开头已含开场音效）——**不要为此回头追问用户**。两条路都只认「BGM + 开场音效合成一条」的单一音轨，不拆成两条。
- 导入后 `uploadState=ready` 才能上时间线。
- 内置默认轨时长 45.6 秒：成片比它长就循环补齐，比它短就裁切，两种处理都必须在 V1 结束帧收尾。
- 把承载真实人声的轨道设为 `anchor`，背景音频轨设为 `follower`。
- **BGM 音量约束（固定值，别让 BGM 太小）**：
  1. 设 `follower` 时**必须同时显式传 `audioRouting.duckDepthDb:-6`**。若不传，`edit_track` 会按时间线响度自动初始化成约 -13dB（甚至更深）的 duck——口播几乎全程在说话，BGM 全程被压得很低，这是「BGM 太小」的根因。
  2. 给 BGM item 设 `decibelAdjustment:6`（+6dB 基础增益；素材本身偏轻，之前仅 +3dB 仍不够）。
  3. 导出后用试听/响度核验：仍偏小则增益 +3dB 递增；盖过人声则 duck 向 -8/-10 加深 2dB，或增益 -3dB。
  4. **削顶预警（内置默认轨）**：`assets/bgm.mp3` 实测真峰值 **+1.2 dBFS**（素材本身已顶到 0dB），再叠 +6dB 有破音风险。导出后若听到爆音/失真，把 `decibelAdjustment` 从 `6` 降到 `0` 或 `-2` 再试——**不要靠继续加增益去救音量**。
- 从开头铺到结尾，必要时循环或裁切，**与 V1 视频内容结束帧对齐**。时间线总长度会被最长轨道撑长；如果背景音频比 V1 长，必须缩短其 `durationInFrames` 到 V1 结束帧，避免结尾黑屏/空画面。
- 设短淡入淡出，避免尾部残留。
- 背景音频替换顺序：fresh 读取旧 item/asset/角色/范围/源偏移/音量/淡入淡出 → 导入新素材 → `integratedLufs` 差值作 A/B 起始补偿 → atomic `edit_item(validateOnly=true)` 预检「删旧 + 加新」→ 原参数提交 → 读回新 item。
- 结构读回不能替代听感；背景音频的响度、气质最终以用户反馈为准。

## 7. 字幕

- 有文案时，以文案作为专名、数字、关键词和语义顺序的对照真相源，不把 ASR 自动视为更权威。
- 无文案时，ASR 转写 + 校对专名/数字/同音词。
- ASR 真相修正用 `manage_transcript fix`（先 preview 真实 token）；显示修正用 `edit_captions display_text`，不混淆二者。
- 固定顺序：template/style/pagination -> display overrides -> layout -> item readback -> pixels。Style 可能自动改写字幕框高度，layout 必须最后执行。
- 存在静音 B-Roll、复制真人轨或其它可转录视频轨时，启用字幕后立即读取 `sourceScope`，显式限定到主口播轨。
- 字幕样式为黑底白字。
- 字幕同一时间只显示一行；一句超屏**不换行**，而是断句拆成多个短字幕，按时间轴分时出现。
- 按语义短句分卡，产品名、金额、英文短语、中文复合词不拆到两张卡。
- 已知有语音却返回 0 页：同窗最多重读一次，再用重叠窗和像素确认，不得解释为「无字幕」。

## 8. 像素验证

- Hosted frame URI 是临时签名资源；TLS 失败时重新取新 URI，不无限重试旧链接。
- 下载可用 HTTP/1.1、`--retry 1 --retry-all-errors` 和连接超时。
- 成功渲染/下载不等于看过像素，必须打开图片确认。

## 9. 导出

- 本地导出用 `local_export`，需要 ChatCut 桌面窗口打开；窗口关闭会报 "window is not open"，此时提示用户打开窗口后再导。
- 提交前查询活动导出，避免重复 render job。
- `submit_export` 后记录 renderId；只按 `track_export` 返回间隔检查，非终态不重复提交、不声称完成。
- 终态后下载到用户 Downloads，用不覆盖同名文件的安全命名，核对本地大小与任务输出大小。
- 用 `ffprobe` 验证编码（H.264）、分辨率（1080×1920）、fps（30）、音频和容器时长；用 `ffmpeg` 对音视频做只读全片解码。这里 ffmpeg 仅用于验证，不替代 ChatCut 导出。
