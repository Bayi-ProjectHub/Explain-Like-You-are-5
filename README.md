# 讲解师 Explain Like You're 5

通过 *选术语、难度、语言 -> 用户自主研究 -> 用户录制讲解 -> AI分析并给出反馈建议*，在扩展用户知识面的同时，帮助用户在多语言的情境下，提升短时间内自主学习能力，以及表达和演讲能力。

Given a term in a field, the user is required to conduct research on their own, and explain the term in front of camera. This system would analyse the record and offer feedback based on thats.
In this process, while expanding and deepening users' knowledge, it would effectively improve user's ability on self learning, expressing and presenting under multiple languages.

## Devloping

### 初次 clone
1. 安装 uv 环境管理器 (ask GPT)，之后运行所有代码都通过 uv 环境
2. 在该项目的终端中运行 `uv sync` 拉取 dependencies
3. 开始开发吧!!

### 修改与提交
- 切换到你的工作分支，或新建一个分支
    ```bash 
    git switch video # 切换至已存在的分支
    git switch -c my-new-branch # 新建分支
    ```

- 更改后，在本地测试后，提交：
    ```bash
    git add .
    git commit -m "简短描述改动了什么"
    git push # 如果是新分支，git push -u origin my-new-branch
    ```

## 启动与使用

### 启动服务

```bash
cp .env.example .env # 仅第一次启动执行即可
uv run python scripts/download_models.py # 下载画面分析模型，已存在时跳过
uv run uvicorn src.serve:app --reload --env-file .env --port 8000
```
脚本默认只下载必需的 Holistic 模型

### 用户端练习页面

启动服务后打开 http://127.0.0.1:8000/app/

从中英词库抽题后，可以计时准备，再上传讲解视频。服务在本地完成转写并生成报告。画面和声音各有时间轴，动作旁会标出当时的转写。点击时间可以回看，也可以下载 Markdown 报告或证据 JSON。

- 词库包含 36 个中英配对概念、6 个领域、3 档难度。界面语言与讲解语言可分别选择。
- 支持 MP4、MOV、WebM、MKV、M4V；默认上限 200 MB、音轨 10 分钟。媒体处理复用已有 PyAV，不需要另外安装 ffmpeg 命令。
- 任务存在进程内存里，运行时使用单 worker；重启服务会丢失任务。当前浏览器会话保留题目、准备笔记及已取得的结果，刷新时可继续查询已提交的任务。

词库维护、产品接口与后续模块整合见 [docs/PRODUCT.md](docs/PRODUCT.md)。页面由现有 FastAPI 服务提供。

### 完整视频分析接口

上传讲解视频时使用 multipart 表单：`file`、`term_id`、`language` 必填。可选的 `presenter_ranges` 指定讲者出镜时段，只影响画面分析；声音和转写仍覆盖整段视频。

```bash
# 提交任务，立即返回 202 和 task_id
curl -F 'file=@explanation.mp4' -F 'term_id=goodharts-law' -F 'language=zh' \
  -F 'presenter_ranges=[{"start":5,"end":28},{"start":35,"end":70}]' \
  http://127.0.0.1:8000/practice/submissions

# 轮询任务，完成后读取 result、modules 和 delivery_report
curl http://127.0.0.1:8000/practice/submissions/<task_id>
```

完整的请求字段、错误码和词库维护见 [PRODUCT.md](docs/PRODUCT.md)；测量含义、实测数据与已知限制见 [AGENTS.md](AGENTS.md#delivery-analysis-module)。

### 单独分析视频画面

用 `POST /video/analyses` 可以直接测试画面分析。只需上传一个视频。无声视频也能用，请求会等到分析结束再返回 JSON。

先运行 `uv sync --locked --extra video` 安装 MediaPipe，并按上面的启动步骤下载模型。确认 `.env` 里的 `VIDEO_MODEL_PATH` 指向已下载的模型文件。

```bash
curl --fail-with-body -F 'file=@explanation.mp4' \
  http://127.0.0.1:8000/video/analyses
```

用 `-F 'presenter_ranges=[{"start":5,"end":28}]'` 可以指定讲者出镜时段。起止时间按播放器秒数填写，最多 100 段，时段不能重叠。省略该字段就从头分析。画面从首个有时间戳的视频帧算起，最多分析 `MAX_VIDEO_SECONDS` 秒。文件大小受 `MAX_UPLOAD_MB` 限制。

返回的 `sampled_frames` 是采样帧数，`coverage` 表示各类点位的覆盖率。`windows` 是分时段的测量值，`events` 记录检测到的动作。事件时间加上 `video_offset_seconds` 就是播放器时间。接口也可以在本地 [API 文档](http://127.0.0.1:8000/docs) 里试。

### 音频转写接口

第一次运行需要联网下载 Whisper 模型，之后使用本地缓存

音频模块位于 `src/audio/`，采用异步任务：上传后立即返回任务 id，之后轮询结果。

```bash
# 1. 上传音频进行处理。language 可选（zh、en 等），不传则自动识别
curl -s -F "file=@demo.wav" -F "language=zh" http://127.0.0.1:8000/audio/transcriptions
# {"task_id": "...", "status": "queued", "created_at": "...", "result": null}

# 2. 轮询任务
curl -s http://127.0.0.1:8000/audio/transcriptions/<task_id>
# status: queued | processing | completed | failed
# completed 时 result 包含 text、language、duration 和带起止时间的 segments
```

运行参数在 `src/config.py` 中，通过环境变量配置（`WHISPER_MODEL` 默认 `small`、`WHISPER_DEVICE`、`WHISPER_COMPUTE_TYPE` 等）。本地验证：`uv run pytest`。

### 文本评测接口

文本模块位于 `src/evaluation/`，调用 DeepSeek 对讲解转录进行评测。需先在 `.env` 配置 `DEEPSEEK_API_KEY`。

```bash
curl -s -X POST http://127.0.0.1:8000/evaluations \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "",
    "transcript": "这里放讲解的整段文本",
    "language": "",
    "audience": "初学者",
    "key_points": ["解释核心概念", "给一个例子", ...],
    "reference_notes": ""
  }'
```

返回 `knowledge`（准确、完整、逻辑、深度、例子）与 `speaking`（清晰、连贯、简洁、结构）九个维度的分数、理由、原文证据和改进建议，以及 `knowledge_score`、`speaking_score`、`overall_score`。只做文本分析，不评价发音、语速、表情等。

### 测试

```bash
uv run pytest -q                            # 单元与接口测试（假引擎，不下载模型）
RUN_INTEGRATION=1 uv run pytest -m integration  # 真实 Whisper 模型，需联网，首次下载权重
node --check web/app.js                     # 可选，仅检查前端语法，运行网页本身不需要 Node
```
