# 用户端与模块整合

## 当前可运行范围

用户端不另建服务：启动 README 中的 FastAPI 服务，打开 `/app/`。

1. 选择领域、难度、讲解语言，随机得到一个概念。中英名称属于同一个条目，避免两套词库逐渐失配。
2. 开始准备计时，可暂停、加时、提前进入上传；笔记留在浏览器会话里，不上传、不评价。
3. 用手机或电脑录好讲解视频，再选择或拖入页面。页面支持本地预览，当前没有网页内录制功能。
4. 上传后轮询练习任务。上传百分比来自浏览器真实进度；提取和转写只显示阶段，不虚构模型进度。
5. 完成后查看完整文本和时间片段，下载包含题目、语言和转写的 JSON，或开始下一题。

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

状态流：`queued → extracting → transcribing → completed`，任一处理阶段可转为 `failed`。`completed` 仅代表当前已接入的转写流程完成。

完成后 `result` 直接复用音频模块的 `TranscriptionResult`，包含 `text`、`language`、`language_probability`、`duration` 和 `segments`（`id`、`start`、`end`、`text`，时间单位为秒）。现有 `/audio/transcriptions/{task_id}` 返回的 `result` 对象可直接复用；练习任务在外层追加题目与模块状态，不改旧接口。

当前模块状态：

```json
{
  "transcription": {"status": "completed", "message": "音轨提取与语音转写已完成"},
  "text_evaluation": {"status": "pending", "message": "文本评价模块待接入，尚未生成评分或建议"},
  "video_evaluation": {"status": "pending", "message": "视频评价模块待接入，尚未分析画面或表现"}
}
```

非法术语或语言返回 422，非法文件格式或空文件返回 415，超大小返回 413，不存在的任务返回 404。扩展名允许并不代表内容有效；没有画面、没有音轨、音轨为空、超过时长、容器损坏、模型失败都会成为可查询的失败任务。已完成但没有识别到文字也按失败处理。

## 后续整合位置（尚未实现）

`src/practice/service.py` 负责流程汇总，`src/audio/` 继续只负责转写。整合时不要把评分逻辑塞进音频路由。

| 模块 | 可提供给模块的输入 | 需要团队确认的输出 |
| --- | --- | --- |
| 文本评价 | 术语快照、讲解语言、`TranscriptionResult` | 评价维度、量表、引用原句／时间段、改进建议 |
| 视频评价 | 原视频路径、术语、语言、带时间片段的转写 | 可观察行为、时间点、证据与建议；哪些维度确实能测量 |
| 产品端 | 上述模块的独立结果与状态 | 分模块展示成功、失败和未接入状态 |

目前 `modules` 只存接入状态，不含评价结果。整合时需另定义各评价模块的数据模型和失败语义，更新前端展示及测试。一个模块失败不应覆盖已取得的转写结果。

**原视频当前会在转写任务结束后删除。** 视频评价必须在清理前完成，或先明确新的临时文件生命周期；不能在现有任务完成后再尝试读取已删除的视频。当前没有长期保存视频、录制授权管理、账户系统或跨服务编排。

## 验证与边界

```bash
uv run pytest -q
node --check web/app.js  # 可选的 JavaScript 语法检查；运行网页本身不需要 Node
```

- 单元／接口测试使用真实 PyAV 媒体容器、假转写引擎：验证筛选、双语、避免连续重复、音轨提取、排队提交与查询、失败状态、上传限制、文件清理、已有路由兼容。
- 2026-11-15 本地验证：20 passed、1 skipped。另使用 macOS 合成语音制作中英 MP4，以真实 `base` 模型通过浏览器跑通上传到结果的流程，并验证英文结果下载。合成语音短样本只能验证流程，不能代表真人讲解的识别准确率或评价质量。
- 浏览器人工验证覆盖中英切换、筛选、准备暂停与刷新恢复、视频预览与提交、损坏视频失败后重新选择并成功重试、结果与时间片段切换、结果下载、390px 手机宽度布局。验证产物位于未追踪的 `data/qa/`，不作为产品样本发布。
- 无新增 Python 或前端依赖。媒体处理复用已有 `av`；无独立 ffmpeg 可执行文件要求。
- 当前服务仅用于小规模本地开发，使用单 worker。任务存在内存中，重启丢失；没有持久队列、跨进程共享状态、自动历史清理和远程部署。
