# 用户端与模块整合

## 当前可运行范围

用户端不另建服务：启动 README 中的 FastAPI 服务，打开 `/app/`。

1. 选择领域、难度、讲解语言，随机得到一个概念。中英名称属于同一个条目，避免两套词库逐渐失配。
2. 开始准备计时，可暂停、加时、提前进入上传；笔记留在浏览器会话里，不上传、不评价。
3. 用手机或电脑录好讲解视频，再选择或拖入页面。页面支持本地预览，当前没有网页内录制功能。
4. 上传后轮询练习任务。上传百分比来自浏览器真实进度；提取和转写只显示阶段，不虚构模型进度。
5. 完成后查看转写、配有时间戳的声音和画面证据、云端综合报告（如已启用）并下载 JSON。当前会话可以用本地视频回看报告引用的时间段。

界面语言和讲解语言相互独立。页面在桌面与手机宽度下使用不同布局。刷新后会从 `sessionStorage` 恢复题目、笔记、倒计时以及任务编号；尚未提交的本地视频必须重新选择。网络查询连续失败或超过 15 分钟后暂停自动查询，用户可以继续查看原任务。

## 词库维护

数据源：`src/practice/vocabulary.json`。六个领域为自然科学、技术与 AI、思维与学习、经济与社会、生活与设计、数学与数据。每个领域的每档难度有两题，共 36 题；这是一份可扩充的初始词库，并非经用户研究校准的难度标准。

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定英文标识，记录练习时使用；不要随翻译改动 |
| `category` | 引用顶层 `categories` 中的分类 |
| `difficulty` | `starter`、`intermediate` 或 `advanced` |
| `title.zh` / `title.en` | 同一概念的中文和英文名称 |
| `prompt.zh` / `prompt.en` | 研究方向／讲解问题，不是参考答案 |
| `preparation_seconds` | 建议研究时间：初始为 180／300／480 秒 |
| `speaking_seconds` | 建议讲解长度：初始为 60／90／120 秒 |

启动时通过 Pydantic 检查双语内容非空、ID 唯一、领域存在、时间为正。修改后重启服务即可。增加题目时为它同时补齐两种语言，保持同一语义；分领域、难度筛选，不按语言拆成两份概念池。

抽题使用符合筛选条件的均匀随机选择；传入 `exclude_id` 时，若有其他候选则避免与上一题重复。当前不是自适应推荐系统，也不记录长期抽题历史。

## 当前 API

### 查询和抽题

```text
GET /practice/vocabulary
GET /practice/vocabulary?category=society&difficulty=advanced
GET /practice/terms/random?category=society&difficulty=advanced&exclude_id=goodharts-law
```

词库查询返回 `version`、`categories`、筛选后的 `terms`、`limits`；随机接口直接返回一个完整术语对象。领域和难度可省略；无候选时随机接口返回 404，非法难度返回 422。

### 上传与查询

```bash
curl -F 'file=@explanation.mp4' -F 'term_id=goodharts-law' -F 'language=zh' \
  http://127.0.0.1:8000/practice/submissions
curl http://127.0.0.1:8000/practice/submissions/TASK_ID
```

上传为 multipart，必填 `file`、`term_id`、`language`（`zh` 或 `en`）。成功返回 HTTP 202 和任务快照：

```json
{
  "task_id": "...",
  "status": "queued",
  "created_at": "...",
  "finished_at": null,
  "term": {"id": "goodharts-law", "...": "完整术语快照"},
  "language": "zh",
  "filename": "explanation.mp4",
  "result": null,
  "modules": {},
  "error": null
}
```

状态流为 `queued → extracting → transcribing → analyzing_delivery → [generating_report →] completed`。媒体或转写失败时任务进入 `failed`。后续任一附加模块失败时，任务仍可返回转写和已取得的证据。

完成后 `result` 直接复用音频模块的 `TranscriptionResult`，包含 `text`、`language`、`language_probability`、`duration` 和 `segments`（`id`、`start`、`end`、`text`，时间单位为秒）。现有 `/audio/transcriptions/{task_id}` 返回的 `result` 对象可直接复用；练习任务在外层追加题目与模块状态，不改旧接口。

成功任务可能包含下列模块状态：

```json
{
  "transcription": {"status": "completed", "message": "音轨提取与语音转写已完成"},
  "text_evaluation": {"status": "pending", "message": "文本评价模块待接入，尚未生成评分或建议"},
  "video_evaluation": {"status": "completed", "message": "视觉证据已提取"},
  "audio_evidence": {"status": "completed", "message": "声音证据已提取"},
  "delivery_report": {"status": "completed", "message": "综合报告已生成"}
}
```

非法术语或语言返回 422，非法文件格式或空文件返回 415，超大小返回 413，不存在的任务返回 404。扩展名允许并不代表内容有效；没有画面、没有音轨、音轨为空、超过时长、容器损坏、模型失败都会成为可查询的失败任务。已完成但没有识别到文字也按失败处理。

## 表达证据与综合报告

`delivery_evidence` 包含视觉窗口、声音事件和音轨时间偏移。证据使用原视频播放时间，`result.segments` 继续使用音轨时间。`delivery_report` 可为空，生成成功时包含七维反馈和证据 ID。原视频和 WAV 在任务退出时清理。具体字段、运行条件与后续校准任务见 [交接文档](DELIVERY_HANDOFF.md)。独立的文本评分接口仍可使用。

## 验证与边界

```bash
uv run pytest -q
node --check web/app.js  # 可选的 JavaScript 语法检查；运行网页本身不需要 Node
```

- 单元／接口测试使用真实 PyAV 媒体容器、假转写引擎：验证筛选、双语、避免连续重复、音轨提取、排队提交与查询、失败状态、上传限制、文件清理、已有路由兼容。
- 2026-11-15 本地验证：20 passed、1 skipped。另使用 macOS 合成语音制作中英 MP4，以真实 `base` 模型通过浏览器跑通上传到结果的流程，并验证英文结果下载。合成语音短样本只能验证流程，不能代表真人讲解的识别准确率或评价质量。
- 浏览器人工验证覆盖中英切换、筛选、准备暂停与刷新恢复、视频预览与提交、损坏视频失败后重新选择并成功重试、结果与时间片段切换、结果下载、390px 手机宽度布局。验证产物位于未追踪的 `data/qa/`，不作为产品样本发布。
- 视觉模块使用可选 `video` 依赖组。媒体处理复用已有 `av`，无需安装独立的 ffmpeg。前端仍使用原生 HTML/CSS/JS。
- 当前服务仅用于小规模本地开发，使用单 worker。任务存在内存中，重启丢失；没有持久队列、跨进程共享状态、自动历史清理和远程部署。
