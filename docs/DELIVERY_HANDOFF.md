# 本地视频内容报告交接

## 当前实现

分支 `feature/multimodal-delivery-feedback` 从 `main` 的 `fe69921` 开始。当前版本在练习上传后，本地运行 faster-whisper 与 MediaPipe Holistic，将动作、声音测量和转写合到原视频播放时间，生成中英界面可浏览、可回看的报告。页面支持下载 Markdown。之前提交中的云端七维点评已从练习任务移除。独立的 `POST /evaluations` 仍可供文本评测模块单独使用，练习流程没有调用它。

## 在 Windows 上启动

在仓库根目录执行。已有 `.env` 时保留其内容。

```powershell
uv sync --locked --extra video
New-Item -ItemType Directory -Force data/models | Out-Null
curl.exe --fail --location 'https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/1/holistic_landmarker.task' --output data/models/holistic_landmarker.task
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

在 `.env` 中设置 `VIDEO_MODEL_PATH=data/models/holistic_landmarker.task`。官方模型 SHA-256 为 `e2dab61191e2dcd0a15f943d8e3ed1dce13c82dfa597b9dd39f562975a50c3f8`，模型文件保存在 Git 忽略目录。所有练习报告无需 API 密钥。首次运行可能从 Hugging Face 下载 Whisper 权重，也可以把 `WHISPER_MODEL` 指向本地 CTranslate2 模型目录。开发机可用多语种 `tiny`，项目默认 `small`。

```powershell
uv run --locked --extra video uvicorn src.serve:app --env-file .env --port 8000
```

访问 <http://127.0.0.1:8000/app/>。选题和讲解语言后上传带人声的视频。缺少视觉模型时，页面仍能显示转写和声音时间线，并标明画面分析未启用。若需从页面回看，使用浏览器支持播放的 MP4 或 WebM。当前浏览器会话保留本地视频引用，刷新后保留报告和时间戳。

## 处理链和文件边界

| 位置 | 职责 |
| --- | --- |
| `src/practice/media.py` | PyAV 输出 16 kHz 单声道 WAV，保留 PCM 时间戳间隙并返回音轨起点相对视频的偏移。 |
| `src/audio/engine.py` | 使用本地 faster-whisper。启用 VAD 和 `word_timestamps`，返回可用的词级估计。 |
| `src/delivery/video.py` | 在原视频时间轴以目标 10 Hz 采样，长边最多 640 像素。Holistic 提取身体、脸、手关键点和部分面部动作系数。保留 2 秒统计窗口，并独立生成相邻采样帧间的动作事件。 |
| `src/delivery/audio.py` | 在同一 WAV 测低声音能量区段，并根据转写分段估计中文汉字或拉丁字母词的语速。 |
| `src/delivery/report.py` | 以原视频秒数严格关联重叠的动作、声音与词；无词级数据的分段才退回分段级。用程序组装报告。 |
| `src/practice/service.py` | 编排媒体、转写和证据生成；保留成功的模块结果，临时视频与工作 WAV 在任务退出时清理。 |
| `web/app.js` | 用毫秒级数据格式化为百分秒显示。报告动作与同期原话各保留自己的起止时间，点击回看动作。按时间的转写视图可点击有时间的词。下载 Markdown 含时间线和完整转写。 |

视觉事件分别检测头部朝向/眼部位置、上半身姿态、手腕移动、面部动作。同类相邻活动会合并，间隔或遮挡将其断开。两次动作可同时挂在同一个分句 ID 上，各自引用所在时间内重叠的词。动作阈值仍是工程初值，短于采样间隔的动作可能漏检。眼部变化与真实眼神交流是两个不同概念，肩部移动也可能受到镜头移动影响。报告只描述可测信号。

## API 和时间

原任务接口仍为 `POST /practice/submissions` 与 `GET /practice/submissions/{task_id}`。状态为 `queued → extracting → transcribing → analyzing_delivery → completed`，媒体或转写问题会进入 `failed`。视觉模型失败时报告仍可返回其他模块数据。

- `result.segments[].start/end` 和 `result.segments[].words[].start/end` 均以音轨为零点，单位秒。旧客户端可继续使用分句。
- `delivery_evidence.audio_offset_seconds` 是 WAV 首样本在原视频时间轴上的时间。与视频比较时给音频时间加这个偏移。
- `delivery_evidence.visual.windows/events` 和 `delivery_evidence.audio` 已在原视频时间轴上。事件 ID 和显示顺序属于单次任务。
- `delivery_report.timeline[]` 含 `kind`、`start`、`end`、该项测量值与 `speech[]`。每段原话有 `segment_id`、独立的原视频起止时间和 `precision`。时间重叠为空时保持空数组。报告不把事件时间强行挪到某个词的开始。

## 验证和后续

```powershell
uv run --locked --extra video pytest -q
node --check web/app.js
```

`tests/test_practice.py` 包含音频晚起 0.25 秒、同一句中两次手势匹配不同词的回归测试。`tests/test_visual_evidence.py` 检查动作时间跨越旧统计窗口边界，以及遮挡和采样间隙。已有真实转写测试可用 `RUN_INTEGRATION=1` 和已下载的本地模型运行。试看片、报告和本地演示相关文件保存在 Git 忽略的 `data/` 下。

想提升准确率时，用不同机位的真人短讲逐个标注动作起止，再测事件误报、漏检和时间偏差。音频内容质量还受本地模型、语言选择与录音条件影响。后续要接其他模块时，请共用原视频时间轴，并选用已有 `delivery_report.timeline` 作为可核对的合并结果。

参考 [faster-whisper 词级时间戳](https://github.com/SYSTRAN/faster-whisper#word-level-timestamps) 和 [MediaPipe Holistic API](https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker?tab=Python)。
