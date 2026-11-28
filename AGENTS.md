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

- 配置在 `src/config.py`，全部来自环境变量：`WHISPER_MODEL`（默认 `small`）、`WHISPER_DEVICE`（默认 `cpu`）、`WHISPER_COMPUTE_TYPE`（默认 `int8`）、`UPLOAD_DIR`、`MAX_UPLOAD_MB`（默认 `200`）。模型从 huggingface_hub 下载，网络受限时可用 `HF_ENDPOINT` 指定镜像。

已知限制：任务状态存在进程内存里（单进程，服务重启丢任务）；上传的音频转写完成后即删除，不保留。

测试：`uv run pytest`（单元测试用假引擎，不下载模型）；真实模型集成测试用 `RUN_INTEGRATION=1 uv run pytest -m integration`。

## Text Evaluation Module

Implemented in `src/evaluation/`:

- `schemas.py` — 评测结果模型：`knowledge`（accuracy / completeness / logic / depth / examples）与 `speaking`（clarity / coherence / conciseness / organization）九个维度，每维是 `DimensionResult`（score 0–100、rationale、evidence 原文引用、suggestions），另含 `overall_score`、`knowledge_score`、`speaking_score`。`extra="forbid"`，字段不容增减。
- `prompts.py` — 系统提示词与 `build_user_prompt(...)`。评分权重写在提示词里（knowledge 70%、speaking 30%），模型必须按权重算总分。
- `evaluator.py` — `TextEvaluator.evaluate(topic=..., transcript=..., language=..., audience=..., key_points=..., reference_notes=...) -> EvaluationResult`。通过 OpenAI SDK 调用 DeepSeek（`https://api.deepseek.com`），用 Pydantic JSON Schema 约束返回结构，再做一次 `model_validate` 校验。
- `router.py` — 同步接口 `POST /evaluations`：请求体包含 `topic`、`transcript`（必填），可选 `language`（`zh` / `en`，默认 `zh`）、`audience`、`key_points`、`reference_notes`；直接返回完整评测结果。上游限流返回 429，连接/上游错误返回 502，缺少 API key 返回 503。

已知限制：只做文本评测，无法判断发音、语调、语速、表情等纯音频/视频信号；分数是 LLM 估计而非客观事实，`evidence` 暂未校验是否真的是转写原文子串；请求同步执行（超时 120 秒），不做排队；无鉴权与用量配额。

测试：`uv run pytest`；`tests/test_evaluation_schemas.py` 只测数据模型，不调用付费 API。

## Delivery Analysis Module

`src/delivery/` 负责画面和声音分析。练习流程在转写后调用这个模块来生成报告。只想测试画面时，用 [README 中的独立接口](README.md#单独分析视频画面)。

- `router.py` — `POST /video/analyses` 接收视频和可选的 `presenter_ranges`。请求等待分析结束，直接返回 `VisualEvidence`。无声视频也能用。接口复用 `VIDEO_MODEL_PATH`、`MAX_UPLOAD_MB` 和 `MAX_VIDEO_SECONDS`，处理结束后删除上传的临时文件。
- `schemas.py` — `DeliveryEvidence`（画面统计、声音记录和音轨偏移）与 `DeliveryReport`（`schema_version=2`）。`Evidence` 带 `id`、`start`、`end`、`metrics`；`VisualEvent` 追加 `kind`（`gaze | posture | gesture | face`）、`measurements` 和关联的 `transcript_ids`；`MotionMeasurement` 描述单个目标在一条轴上的起止值、差值、幅度与峰值速度；`PlaybackRange` 校验讲者出镜时段。
- `video.py` — `analyze_video(path, model_path, max_seconds, presenter_ranges)`。用 MediaPipe Holistic（含面部 blendshape）按 15 Hz 抽样，帧长边缩放到 960（最多放大 2 倍），低帧率时按可用帧取样；按 2 秒窗口生成 `V…` 汇总，按持续动作生成 `E…` 事件。方向反转、关键点丢失、切镜、切换模型或离开选定范围时结束当前动作。手势阈值为 0.6 肩宽/秒、最短 0.12 秒；显著动作的最小幅度为 2°、0.08 肩宽或 0.16 blendshape 系数；16×16 缩略图平均绝对差超过 43 视为切镜。
- `landmarks.py` — 可选补充检测器，从 `model_path` 同目录加载 `face_landmarker.task`、`pose_landmarker_heavy.task`、`hand_landmarker.task`。`VIDEO_FACE_MODE=adaptive`（默认，Holistic 缺面部数据时才调用专用模型）或 `dedicated`（每帧调用）。
- `scripts/download_models.py` — 下载模型到 `data/models/`；默认只取必需的 Holistic，`--all` 才下载专用 Face、Pose Heavy、Hand 回退模型，已存在时跳过。
- `wholebody.py` — 可选 RTMW 单人身体模型，只在检测到一人且身体关键点质量不低于 Holistic 时替换。配置为 `VIDEO_RTMW_DIR`（内含 `yolox-tiny.onnx` 及 `pose-m.onnx` 或 `pose-l.onnx`）、`VIDEO_RTMW_PRESET=m|l`、`VIDEO_RTMW_DEVICE=cpu|cuda|dml`、`VIDEO_RTMW_DML_DEVICE_ID`（仅 Windows DirectML）。
- `audio.py` — 在已提取的 16 kHz WAV 上算 50 ms RMS：记录低能量段 `A…`（`quiet_seconds`）、按转写分句估算语速（`han_characters_per_minute` / `latin_words_per_minute`），并按 2 秒窗口输出 `L…` 的 `rms_dbfs`。这是数字音轨电平，不等于实际声压分贝。
- `clock.py` — 只读取容器起点到首条音轨样本的偏移，不改动音频流程。
- `report.py` — `build_delivery_report(evidence, transcript)` 保留两条时间轴，按时间重叠把画面事件连到转写（分句精度）和声音记录。

报告字段：

| 字段 | 时间零点与内容 |
| --- | --- |
| `delivery_report.video` | 首个有时间戳的视频帧。每条 `E…` 带起止时间、测量值和同期转写引用，并引用重叠的 `A…` / `L…` 记录。 |
| `delivery_report.audio` | 解码后 WAV 的首样本。保留 `A…` 低能量段与可算语速区间。 |
| `delivery_report.audio_levels` | 同一 WAV 时间轴；每个连续 2 秒窗口（末段可能更短）的 `rms_dbfs`。 |
| `delivery_report.transcript` | 同一 WAV 时间轴；完整文本与分句起止。 |
| `delivery_report.sync` | 给轨道时间加 `audio_to_playback_seconds` / `video_to_playback_seconds` 得到播放器时间。 |
| `delivery_evidence.visual` | 抽样帧数、检测范围、各项覆盖率（目标 85%，分母是抽样帧）、补充模型命中次数（`tracking_sources`）和分段统计。 |

画面记录里的 `speech` 仍是转写（音轨）时间：匹配时先把画面区间换算到音轨时间，再把重叠分句附在事件上，不会把整句当成精确词位。两个偏移都按首样本计算。

测量是 2D 画面估算：横轴向右为正、竖轴向下为正；手腕和肩部位移以肩宽为单位，躯干侧倾取肩部中心与臀部中心连线的角度，面部使用 blendshape 系数。无法判断情绪、手指形状、指向目标、身体纵深转动或说话人身份；镜头移动、低画质和多人素材会降低可信度。多人素材需要用户用 `presenter_ranges` 手工排除观众镜头，待办见本节末尾的“接手与已知问题”。

`tests/test_visual_evidence.py` 用合成关键点验证动作汇总、切镜和模型切换。`tests/test_practice.py` 用无声视频验证独立接口，也覆盖错误响应和文件清理。评估真实模型的准确率时需另行记录模型和视频来源。

### 可选 RTMW 与 GPU

普通电脑默认用 CPU MediaPipe 即可。单讲者视频可用 RTMW 进一步补身体关键点，它只在检测到一人、且躯干点质量不低于原模型时替换。多人素材需要先用 `presenter_ranges` 选定讲者镜头。

1. 安装 RTMLib。项目依赖已提供 cv2 和 NumPy，原依赖提供 ONNX Runtime；用 `--no-deps` 避免同时装两个提供 cv2 的包。同步项目环境后可能需要重装这项可选项：

   ```bash
   uv pip install --no-deps rtmlib==0.0.16
   ```

2. 从 OpenMMLab 下载 [YOLOX Tiny](https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_tiny_8xb8-300e_humanart-6f3252f9.zip)、[RTMW-m](https://download.openmmlab.com/mmpose/v1/projects/rtmw/onnx_sdk/rtmw-dw-l-m_simcc-cocktail14_270e-256x192_20231122.zip) 或更大的 [RTMW-l](https://download.openmmlab.com/mmpose/v1/projects/rtmw/onnx_sdk/rtmw-dw-x-l_simcc-cocktail14_270e-384x288_20231122.zip)。把各压缩包内的 `end2end.onnx` 放到同一目录，分别命名为 `yolox-tiny.onnx`、`pose-m.onnx`、`pose-l.onnx`；两个 pose 权重不必同时存在。

3. 设置 `VIDEO_RTMW_DIR=data/models/rtmw`、`VIDEO_RTMW_PRESET=m` 或 `l`。数据库和云端密钥都不需要。启用失败时后端会记录异常，练习仍返回可用的声音和转写。

4. 执行设备默认 `VIDEO_RTMW_DEVICE=cpu`。GPU 需要替换 ONNX Runtime，且同一 Python 路径不要混用多个发行版：

   - **Windows DirectML**（仅 Windows，使用 `onnxruntime-directml`）：

     ```powershell
     uv pip install --target data/ort-dml --no-deps onnxruntime-directml==1.24.4
     $env:PYTHONPATH=(Resolve-Path data/ort-dml).Path
     $env:VIDEO_RTMW_DEVICE="dml"
     $env:VIDEO_RTMW_DML_DEVICE_ID="0"
     ```

   - **Linux CUDA**（使用 `onnxruntime-gpu`，需本机匹配的 CUDA 与 cuDNN）：

     ```bash
     uv pip install --target data/ort-cuda --no-deps onnxruntime-gpu
     export PYTHONPATH="$(pwd)/data/ort-cuda"
     export VIDEO_RTMW_DEVICE=cuda
     ```

   - **macOS**：使用默认 CPU；没有 CUDA 或 DirectML 路径。

   程序会检查实际执行提供程序，运行日志和 `tracking_sources` 会标明模型。更大的预设或 GPU 并不保证提高某条视频的覆盖率。

来源：[MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)、[RTMW 官方发布](https://github.com/open-mmlab/mmpose/releases)、[RTMLib](https://github.com/Tau-J/rtmlib)、[ONNX Runtime DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html) 与 [CUDA](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

### 实测记录

实测环境为 Windows、Python 3.12、Ryzen 9 9955HX；运行命令见 README，在 macOS/Linux 上相同。

- 开启 `RUN_INTEGRATION=1` 时 33 项测试全部通过（含真实本地 Whisper 音频集成）；默认运行会跳过集成测试，得到 32 passed、1 skipped。另用 `node --check web/app.js` 检查前端。
- 25 秒 1080p 单人片段，15 Hz 采样 375 帧，CPU 约 17.5 秒。人脸、面部系数、虹膜可用性、上半身均 100%；192 条面部系数变化、11 条朝向变化，手腕覆盖 0%，手势事件 0 条。系数条目可在时间上重叠（例如两眼各一条），不能当作动作总次数。
- 同一片段前 12 秒轮换四次：两种 CPU 路径均采样 180 帧，人脸和面部系数覆盖率 100%；Holistic 优先中位 7.24 秒，每帧跑专用 Face 7.80 秒，因此默认 `VIDEO_FACE_MODE=adaptive`。25 秒片段的旧版 Holistic（10 Hz）约 13.4 秒，专用 Face（15 Hz）约 17.6 秒，RTMW-m + DirectML（15 Hz）约 19.8 秒，三者人脸覆盖均 100%。
- 445.66 秒单人视频全片，每轮采样 6,684 帧。CPU 自适应模式 242.2 秒（含本地 Whisper Small 英文转写），人脸／面部系数／上半身 98.9%，虹膜 94.4%，共 223 个电平窗口；画面时间加 0.023 秒对齐播放器。手部覆盖 0.4%，回看确认三条腕部记录来自同一次动作；三条肩部位移都与景别切换同时出现，髋部一直在画面外。较早的专用 Face 模式虹膜覆盖 95.2%，曾出现 0.042 秒腕部误报，按后来采用的 0.12 秒阈值复筛后消失；该阈值也可能滤掉极短的真实动作。
- NASA [Earthrise 访谈](https://images.nasa.gov/details/Earthrise%20-%20A%20Conversation%20with%20Apollo%208%20Astronaut%20Bill%20Anders%20%28Official%20NASA%20Video%29) 的 132–151 秒截取段含中间长切镜。不设筛选时人脸覆盖 49.8%；传样片本地播放范围 `[0,4.3)` 与 `[14.5,19)` 后，132 帧的人脸、面部系数和上半身均为 100%，音轨电平完整到 19.072 秒。NASA 旧档案整片人脸 19.8%、上半身 13.4%，未达 85%；低清、切镜或不可见帧没有被算作成功。
- RTMW-m 已在 CPU 完成推理；Windows DirectML 上 RTMW-m / RTMW-l 均跑通。RTMW-l 以外部手部可见性作约束后，18 帧近景中没有把画外手计入覆盖。CUDA 路径和普通电脑的耗时下限尚未验证。

### 接手与已知问题

- 先运行 `uv run pytest -q` 和 `node --check web/app.js`。测试覆盖音视频不同偏移、同期轨道共存、同句多个动作、剪掉指定视觉范围、视频切镜和腕部方向反转。
- 先人工标出讲者镜头，确认脸和手是否入镜，再查覆盖率和误报。讲者出镜时段和整条剪辑分别计算覆盖率；画外的手无法跟踪，配图和观众特写也可能看不到讲者。
- 用五类视频分别验收：稳定单人正面、侧面、手出画、背光、观众切镜。双人节目需要目标身份关联；目前只能手工排除镜头，仍需多人跟踪和样本标注，才适合自动区分讲者。
- 镜头运动和低画质会让测量失准。后续可先做摄像机运动补偿，再校准手势幅度；表达分析可以把本地导出的 JSON 交给后续模块。
- 如果源音轨中间的时间戳有跳变，提取 WAV 时又压缩了间隙，后面的时间换算可能对不上，需要逐段换算。

## User-facing Product Module

- `web/` — 同源静态用户端，入口 `/app/`，使用原生 HTML/CSS/JS，无额外构建依赖。原来的 `/` JSON 健康响应及 `/audio/*` 接口保持兼容。
- `src/practice/vocabulary.json` — 36 个中英配对概念，6 类领域、3 档难度；`vocabulary.py` 负责加载校验与随机抽题。
- `src/practice/media.py` 用 PyAV 提取单声道 16 kHz WAV。`src/delivery/clock.py` 单独读取音轨起点，供报告换算时间。
- `src/practice/service.py` 先调用 `TranscriptionService` 转写，再把画面动作和声音记录写进本地报告。任务逐个处理，状态为 `queued | extracting | transcribing | analyzing_delivery | completed | failed`。看到 `completed` 就可以读取转写。画面分析等步骤的结果在 `modules` 里。
- `src/practice/router.py` — `GET /practice/vocabulary`、`GET /practice/terms/random`、`POST /practice/submissions`、`GET /practice/submissions/{task_id}`。
- 追加配置 `MAX_VIDEO_SECONDS`（默认 600，限制解码音轨长度），复用 `MAX_UPLOAD_MB`。正常完成和失败均删除视频及生成的临时音轨。
- 配好 `VIDEO_MODEL_PATH` 后，练习任务会调用 `src/delivery/` 分析画面和声音；模块细节、实测与待办见上节 Delivery Analysis Module。文本评分可单独调用 `POST /evaluations`。
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
