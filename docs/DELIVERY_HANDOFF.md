# 演讲视频分析交接

## 工作状态

分支 `feature/multimodal-delivery-feedback` 从 `main` 的 `fe69921` 开始。架构依据是用户提供的图，视频和时间戳进入 MediaPipe Holistic，分别提取眼神、姿态、手势和面部动作，再生成 Visual Evidence JSON，和音频及转写合并生成七维报告。

第一版已经接入练习上传、后台处理、任务查询、结果页面和 JSON 下载。视觉模型和云端报告可在 `.env` 分别启用。视觉或云端失败时仍返回转写和已取得的其他证据。视频分析结果是测量记录，综合报告提供带证据的定性建议。图中未给出七维名称，当前暂定为镜头朝向与视线变化、姿态、手势、面部动作、声音节奏、讲解结构、动作与内容配合。团队如果已有正式量表，从 `src/delivery/schemas.py` 的 `DIMENSIONS` 和 `src/delivery/report.py` 的提示词、证据校验开始调整。

## 启动和配置

以下为仓库根目录下的 PowerShell 示例。先安装 `uv`。在已有 `.env` 时继续使用它。

```powershell
uv sync --locked --extra video
New-Item -ItemType Directory -Force data/models | Out-Null
curl.exe --fail --location 'https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/1/holistic_landmarker.task' --output data/models/holistic_landmarker.task
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

在 `.env` 中设置 `VIDEO_MODEL_PATH=data/models/holistic_landmarker.task`。模型文件在忽略目录 `data/` 下，下载地址固定为上游版本 `1`。本次下载的 SHA-256 为 `e2dab61191e2dcd0a15f943d8e3ed1dce13c82dfa597b9dd39f562975a50c3f8`。如果只测试视觉和音频，保留 `DELIVERY_REPORT_ENABLED=false`。确需生成报告时填写自己的 `DEEPSEEK_API_KEY` 并设 `DELIVERY_REPORT_ENABLED=true`。报告使用与独立文本评测相同的 `EVALUATION_MODEL`，默认 `deepseek-flash`。切换配置后重启服务。

```powershell
uv run --locked --extra video uvicorn src.serve:app --env-file .env --port 8000
```

打开 `http://127.0.0.1:8000/app/`，抽题后选择一段带人声的视频提交。Whisper 首次可能需要联网下载，可把 `WHISPER_MODEL` 指向本地 CTranslate2 模型目录。仅用转写和声音时，可省略 `--extra video` 和 `VIDEO_MODEL_PATH`。

## 从哪里继续读代码

| 位置 | 职责 |
| --- | --- |
| `src/serve.py`、`src/config.py` | 启动 FastAPI，配置视觉模型文件和报告生成器。 |
| `src/practice/media.py` | 生成 16 kHz 单声道 WAV。按源时间戳补齐音轨里的间隙，并返回首个 WAV 样本在原视频中的秒数。 |
| `src/practice/service.py` | 复用已有转写服务，随后读取原视频和 WAV 提取证据，再选用 DeepSeek 生成报告。模型推理和网络请求在线程中运行。原视频与工作 WAV 在任务退出时清理。 |
| `src/delivery/video.py` | PyAV 按播放时间抽帧，长边最多 640 像素。Holistic 的 `VIDEO` 模式同时返回 478 个脸部点、33 个身体点、左右手各 21 个点（检出时），另可返回面部动作系数。用 6 Hz 抽样和 2 秒时间窗口转换成局部统计。 |
| `src/delivery/audio.py` | 对同一条 WAV 计算声音相对能量，并从转写分段估算节奏。英语保留拉丁词/分钟，中文保留汉字/分钟，混合段分开计数。 |
| `src/delivery/schemas.py`、`src/delivery/report.py` | 定义 API 模型、选择要发给云端的窗口、将时序证据与转写关联、请求和验证七维报告。 |
| `web/app.js` | 更新处理和结果状态。报告用证据 ID 查找原始时间戳。上传后只要页面仍持有本地视频，可点击时间段播放。刷新后保留结果和时间标签，浏览器不再持有文件。 |

## API 和时间轴

仍从 `POST /practice/submissions` 上传。上传字段为 `file`、`term_id`、`language`。用 `GET /practice/submissions/{task_id}` 轮询。状态依次为 `queued`、`extracting`、`transcribing`、`analyzing_delivery`，启用报告时再经过 `generating_report`。`completed` 表示任务结束且转写成功。查看 `modules.video_evaluation`、`modules.audio_evidence`、`modules.delivery_report` 判断各模块是否成功、未启用或证据不足。`result` 仍是原有音频转写结构，独立的 `POST /evaluations` 九维文本评分保留。七维报告在单次云端请求内直接读取转写做结构点评，不重复发起九维评分请求。

结果新增 `delivery_evidence` 和 `delivery_report`。视觉和音频证据的 `start`、`end` 都是原视频播放秒数。旧 `result.segments` 仍以 WAV 开头为零点，加 `audio_offset_seconds` 后才能和原视频比对。证据的 `transcript_ids` 是与当前窗口相交或在其边界 0.4 秒内的转写片段编号。云端请求包含题目、练习目标、完整有序转写（无分段时使用全文）、视觉可见率、最多 19 个代表性视觉窗口，以及最多 20 条声音证据。窗口选择保留开头、中间、结尾和各指标高低值，详细窗口仍可从任务 JSON 下载。

视觉 JSON 示例，数值仅为示意：

```json
{
  "schema_version": 1,
  "model": "mediapipe_holistic",
  "sample_hz": 6,
  "coverage": {"face": 0.91, "iris": 0.69, "upper_body": 0.94, "hands": 0.85},
  "windows": [
    {"id": "V4", "start": 6.0, "end": 8.0, "metrics": {"gesture_bursts": 1}, "transcript_ids": [2]}
  ]
}
```

| 评测维度 | 证据与计算口径 |
| --- | --- |
| 镜头朝向与视线变化 | `face_turn_offset` 用鼻尖在脸部横轴上的相对位置近似头部朝向。`iris_change_per_second` 仅在近正脸时计算虹膜相对眼角位置变化。这两个指标不表示真实眼神交流。 |
| 姿态 | `torso_lean_degrees` 是肩中心至髋中心连线在画面里的侧倾角。`shoulder_motion_widths_per_second` 用肩宽归一化画面中的肩中心移动。镜头移动也会影响读数。 |
| 手势 | 手部与手腕均检出后，测量相对于肩部的手腕速度和窗口内活动范围。`gesture_bursts` 是窗口内速度跨过经验阈值的次数。目前发给云端的是 2 秒窗口的起止时间，逐个动作的精确起止需要另做连续事件检测。 |
| 面部动作 | `face_coefficient_change_per_second` 汇总选定的眉、眼睑、下巴和嘴角动作系数变化。说话本身会影响数值。 |
| 声音节奏 | `quiet_seconds` 是夹在较高能量区间之间、持续至少 0.6 秒的相对低能量段。语速来自至少 2 秒的 ASR 片段，容易受转写错误影响。 |
| 讲解结构 | 根据整段转写看主旨、衔接和收束，引用 `T` 开头的转写 ID。 |
| 动作与内容配合 | 引用时间重叠的 `V` 与 `A` 或 `T` 证据，说明动作与所讲内容可能如何配合。 |

无可用点位时，窗口 JSON 里缺省对应指标。报告的每个维度都必须出现一次。`observed` 必须给实际存在且与维度匹配的证据 ID、观察和建议。`insufficient_evidence` 对应的三个内容字段留空。配合项额外校验时间交集，前端由 ID 解析时间，云端输出只负责解释。引用通过结构校验不代表解释本身已经验证。报告失败时看服务端日志中的异常类型。日志刻意省略模型回复和转写内容。

## 方案评估与修改

- **姿态分类。** 先按各部位可观测性决定哪些指标能产出，避免半身或侧身录像被错误路由。坐站、PPT 识别和观众定位仍待支持。
- **依赖。** VERA 的旧 NumPy 固定版本与本仓库冲突。实际采用 MediaPipe Tasks 和 PyAV。`video` 是可选依赖，锁定的 Windows 实测版本为 MediaPipe 1.2.3、PyAV 18.1.0、Python 3.12.16。
- **时间偏移。** 先前 WAV 在转写前就被删除，且音轨开头不一定与视频相同。现在保留工作 WAV 到分析结束，提取时保留音轨间隙并记录偏移。无 PTS 的老文件采用顺序 PCM 写入。
- **云端故障。** 独立可开关，默认关闭。生成器超时 60 秒，不自动重试，云端故障降级为已有本地结果。任务仍用原有单进程内存状态，报告等待期间该练习占用一个工作槽。

## 验证与下一步

```powershell
uv run --locked --extra video pytest -q
node --check web/app.js
```

- `tests/test_visual_evidence.py` 用合成信号断言四路视觉指标及遮挡退化。`tests/test_practice.py` 使用真实 PyAV 容器，覆盖偏移、声音事件、视觉模块故障、有效和无效证据引用，以及原文件清理。
- 真实 DeepSeek 调用需要可用密钥。自动接口测试会替换云端客户端，检查实际发出的结构和服务是否接收符合约束的回复。环境中的真实模型与浏览器实测见下方验证记录。
- 下一位先用几段获得授权的中英真人短讲回看正常、半身、侧身、竖屏旋转和手出画等条件。逐段对比事件时间和真实行为，再调抽帧率、手势阈值和可见性门槛。对照同一句话附近的动作，核验报告的解释是否由证据支持。
- PPT 分析可在第七维增加独立幻灯片证据和画面覆盖字段。建议用同一原视频时间轴关联幻灯片、转写和身体朝向，补完样本后才评估指向或观众互动。短片云端复核、准确率标注、报告重试和持久化均尚未实现。

### 实测记录

- 全量 `pytest` 为 **28 passed**。额外用了 `RUN_INTEGRATION=1` 和本地 `WHISPER_MODEL` 路径来启用已有的真实音频转写测试。`node --check web/app.js` 通过。
- Windows 上用真实 MediaPipe Holistic 和 faster-whisper `tiny.en`，通过上传和轮询接口跑通两个 11 秒 MP4。素材由 [MediaPipe 全身图](https://storage.googleapis.com/mediapipe-assets/pose.jpg)、[MediaPipe 正脸图](https://storage.googleapis.com/mediapipe-assets/portrait.jpg) 与 [Whisper JFK 样例音频](https://github.com/openai/whisper/blob/main/tests/jfk.flac) 合成。首次约 4.00 秒，第二段约 2.24 秒。全身样片输出姿态和手势，近景样片覆盖四路视觉指标，两者均输出声音证据与转写关联，结束后临时文件已清理。这是用来验证数据流的合成样片，不能用于验证动作识别准确率、正常使用延迟或报告质量。
- 浏览器用 Edge 跑通上传、云端发送说明、七维报告、中英切换、按证据跳转播放、刷新恢复结果。在宽度 320、390、768、1024 和 1440 像素下检查了结果页无横向溢出。视觉和语音使用真实模型，DeepSeek 使用模拟响应。当前环境没有 DeepSeek 密钥，真实云端报告等待联调。运行时样片和模型均在 Git 忽略的 `data/` 下。

量表依据采用本地改写，参考 [Elizabeth Johnston / Lumen Learning 口头演讲量表（CC BY 4.0）](https://courses.lumenlearning.com/atd-monroecc-collegecomp/chapter/oral-presentation-assignment/) 的结构、表达和多媒体维度，以及 [Toastmasters 肢体语言量表](https://ccdn.toastmasters.org/medias/files/department-documents/education-documents/evaluation-resources/english/8203e-evaluation-resource-ffe.pdf) 的手势观察思路。具体首版字段和证据规则是本项目的实现决策。模型 API 见 [MediaPipe Holistic](https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker?tab=Python) 和 [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。
