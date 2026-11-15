# AGENTS.md
This file provides instructions and information for coding agent when working on this project. 

## Project Context
*Explain Like You're 5 (讲解师)* is a student-led project for fun, not a serious commercial software where thousands of users request in the meantime.
The project aims to help users improve their autonomous learning, explanation, and presentation skills through short learning and presentation tasks.

## Architecture and Pipeline
This project is in its very early developing stage for now. The roadmap isn't fixed.

The initial idea is: pick a term -> user do research under given time -> record and upload a video of user explaining the term ->  evaluate and give advice based on the video. 

The current goal is building 3 main modules: audio processing and transcribing, text processing and evaluating, video processing and evaluating.

## Audio Module

Implemented in `src/audio/`:

- `schemas.py` — 数据模型（`TranscriptionResult`、`Segment`、`TaskResponse`）
- `engine.py` — 转写引擎抽象 `Transcriber`（`transcribe(audio_path, language) -> TranscriptionResult`）与本地 `FasterWhisperTranscriber`。要换云端服务时实现同一接口即可，其余代码不动。
- `service.py` — 任务生命周期管理（上传落盘、排队、转写、清理、错误记录）。核心逻辑不依赖 HTTP，其他模块可以直接复用。
- `router.py` — 异步 HTTP 接口：

  - `POST /audio/transcriptions`：multipart 上传，字段 `file`、可选 `language`；立即返回 `202` 和 `task_id`。
  - `GET /audio/transcriptions/{task_id}`：轮询状态 `queued | processing | completed | failed`；完成后 `result` 为整段文本加带秒级起止时间的分句。

- 配置在 `src/config.py`，全部来自环境变量：`ELY5_WHISPER_MODEL`（默认 `small`）、`ELY5_WHISPER_DEVICE`（默认 `cpu`）、`ELY5_WHISPER_COMPUTE_TYPE`（默认 `int8`）、`ELY5_UPLOAD_DIR`、`ELY5_MAX_UPLOAD_MB`（默认 `200`）。模型从 huggingface_hub 下载，网络受限时可用 `HF_ENDPOINT` 指定镜像。

已知限制：任务状态存在进程内存里（单进程，服务重启丢任务）；上传的音频转写完成后即删除，不保留。

测试：`uv run pytest`（单元测试用假引擎，不下载模型）；真实模型集成测试用 `ELY5_RUN_INTEGRATION=1 uv run pytest -m integration`。

## User-facing Product Module

- `web/` — 同源静态用户端，入口 `/app/`，使用原生 HTML/CSS/JS，无额外构建依赖。原来的 `/` JSON 健康响应及 `/audio/*` 接口保持兼容。
- `src/practice/vocabulary.json` — 36 个中英配对概念，6 类领域、3 档难度；`vocabulary.py` 负责加载校验与随机抽题。
- `src/practice/media.py` — 用已有 PyAV 从视频中提取单声道 16 kHz WAV；不分析画面，不更改音频模块支持的格式。
- `src/practice/service.py` — 独立练习编排，调用已有 `TranscriptionService`；视频任务逐个处理，状态为 `queued | extracting | transcribing | completed | failed`。`completed` 仅表示当前音轨提取与转写已完成，不表示评价已完成。
- `src/practice/router.py` — `GET /practice/vocabulary`、`GET /practice/terms/random`、`POST /practice/submissions`、`GET /practice/submissions/{task_id}`。
- 追加配置 `ELY5_MAX_VIDEO_SECONDS`（默认 600，限制解码音轨长度），复用 `ELY5_MAX_UPLOAD_MB`。正常完成和失败均删除视频及生成的临时音轨。
- 文本评价与视频评价均为 `pending`，尚无评分、建议或画面分析。后续整合入口和接口约定见 `docs/PRODUCT.md`。
- 任务记录仍为进程内存，仅支持单 worker；服务重启丢任务。页面使用 `sessionStorage` 保存当前练习，文件需重新选择，不保存原视频。
- 测试：`tests/test_practice.py` 使用 PyAV 生成真实容器验证媒体提取，用假引擎测试转写编排；这不等于真实模型准确率验证。真实模型验证需另外记录使用的模型和视频来源。

## Engineering
1. Keep It Simple — Prefer straightforward implementations over unnecessary abstractions or complex architectures.
2. Be pragmatic
3. Modular Design — Keep audio, text, and video processing modules logically independent.

## Development Guidelines

### Before Making Changes
1. Read relevant documentation
2. Inspect the existing implementation and understand the current module boundaries.

### Implementation Principles
1. Prioritize readability for humans. Avoid overly concise or abstract expressions that make code difficult to understand.
2. Add type hints where appropriate.
3. Write comments for non-obvious logic, design decisions, or variables. Use Chinese or English as appropriate.
4. Keep configuration separate from source code.
5. Never hardcode API keys, tokens, or other credentials.
6. Handle expected errors explicitly
7. Stay within the requested scope, reuse existing code where appropriate, and avoid unrelated refactoring.
8. Design Consistency: Follow existing project conventions and architecture. Explain significant design decisions when necessary.

### After Making Changes
1. Run relevant tests or checks to verify the implementation.
2. Report what was changed and any known limitations.
3. Identify any changes to shared interfaces, dependencies, or architecture.
4. Update relevant documentation (including this file AGENTS.md) to reflect the actual implementation and any changed interfaces or decisions.
