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
uv run uvicorn src.serve:app --reload --env-file .env --port 8000
```

### 用户端练习页面

启动服务后打开 http://127.0.0.1:8000/app/

当前用户端流程：**中英抽题、计时准备、上传讲解视频、转写、提取表达证据、查看和下载结果**。报告提供独立的画面和声音时间轴、词级转写关联、回看、Markdown 和证据 JSON。练习报告在本地生成。

- 词库包含 36 个中英配对概念、6 个领域、3 档难度。界面语言与讲解语言可分别选择。
- 支持 MP4、MOV、WebM、MKV、M4V；默认上限 200 MB、音轨 10 分钟。媒体处理复用已有 PyAV，不需要另外安装 ffmpeg 命令。
- 任务存在进程内存里，运行时使用单 worker；重启服务会丢失任务。当前浏览器会话保留题目、准备笔记及已取得的结果，刷新时可继续查询已提交的任务。

词库维护、产品接口与后续模块整合见 [docs/PRODUCT.md](docs/PRODUCT.md)。页面由现有 FastAPI 服务提供。

### 启用画面分析

运行 `uv sync --locked --extra video`，下载 [MediaPipe Holistic 模型](https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/1/holistic_landmarker.task)，在 `.env` 中配置 `VIDEO_MODEL_PATH`。安装命令、报告字段和验证方法见 [交接文档](docs/DELIVERY_HANDOFF.md)。

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
# completed 时 result 包含 text、language、duration 和带起止时间的 segments 和词级 words
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
