# 双轨视频证据交接

## 当前分支和目标

分支 `feature/multimodal-delivery-feedback`。本次改动从 `fd8e2c3` 开始，把本地报告拆成独立的画面、音频和转写数据。应用不在练习流程调用云端模型。Markdown 用于人工复核，导出的证据 JSON 可交给后续模块或模型，原始检测值、单位、关联和可见性均保留。样片、模型权重、本地结果和用户视频均在环境本地或 Git 忽略目录。

## 启动

在仓库根目录进行。可沿用已有 `.env`。

```powershell
uv sync --locked --extra video
New-Item -ItemType Directory -Force data/models | Out-Null
$models = @{
  'holistic_landmarker.task' = 'holistic_landmarker/holistic_landmarker'
  'face_landmarker.task' = 'face_landmarker/face_landmarker'
  'pose_landmarker_heavy.task' = 'pose_landmarker/pose_landmarker_heavy'
  'hand_landmarker.task' = 'hand_landmarker/hand_landmarker'
}
foreach ($name in $models.Keys) {
  curl.exe --fail --location "https://storage.googleapis.com/mediapipe-models/$($models[$name])/float16/1/$name" --output "data/models/$name"
  if ($LASTEXITCODE -ne 0) { throw "Could not fetch $name" }
}
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

在 `.env` 中设置 `VIDEO_MODEL_PATH=data/models/holistic_landmarker.task`，运行 `uv run --locked --extra video uvicorn src.serve:app --env-file .env --port 8000`。访问 <http://127.0.0.1:8000/app/>。三个专用模型同目录且可选，缺少时使用 Holistic 对应输出。面部推理由 VIDEO_FACE_MODE 控制。转写、文本评测和原 WAV 提取和 main 的 fe69921 一致。使用原有 faster-whisper 模型和参数，默认配置照旧。只在视频模块中读取媒体时间轴和音频结果。首次配置某个 Whisper 模型可能需要下载权重。手机可编码的 MP4 和 WebM 通常可以回看，具体取决于浏览器。

选题、上传后可选择性填写讲者出镜时间，例如 `00:05–00:28, 00:35–01:10`。提交 API 是 `POST /practice/submissions`，额外表单字段 `presenter_ranges` 可传 `[{"start":5,"end":28},{"start":35,"end":70}]`。时间使用原播放器秒数，采用左闭右开区间。禁止重叠。未传时分析整片。若输入超出片长，只有交集会分析。剪去观众切镜只作用于画面，音频和转写仍保留整段。当前由用户确认讲者出镜时段，镜头切换检测用来切开运动事件。

## 报告接口

轮询 `GET /practice/submissions/{task_id}`。旧 `result` 转写字段仍保留。当前 `delivery_report.schema_version=2`，旧版混合 `timeline` 已改为独立轨道。浏览器可读上一个版本的缓存报告。

| 字段 | 时间零点和内容 |
| --- | --- |
| `delivery_report.video` | 首个定时解码视频帧为零点。每条用 `E…` ID，包含动作、起止、测量、重叠音频 ID 和重叠原话。 |
| `delivery_report.audio` | 解码后的 WAV 首样本为零点。保留 `A…` 的低能量段与可算语速区间。 |
| `delivery_report.audio_levels` | 同一 WAV 时间轴。每个连续 2 秒窗口（末段可能更短）记录 RMS dBFS 和 `L…` ID。音量表示数字音轨电平，无法估算实际分贝声压。 |
| `delivery_report.transcript` | 同一 WAV 时间轴。完整文本及原版的分句起止。多个独立动作可链接同一分句，报告不会把整句当成精确词位。 |
| `delivery_report.sync` | 两个独立的本轨到播放器偏移。播放时间 = 轨内时间 + 本轨偏移。匹配语音时，先把视频区间换算成音频轨坐标。关联分句保留音频轨时间。当前按首样本的固定偏移对齐；源音轨中途若有时间戳跳变，而 main 的 WAV 提取把间隙压紧，后续片段可能产生偏差。处理此类素材需独立的分段时钟映射。 |
| `delivery_evidence.visual` | 覆盖率、样本数、启用的检测分支命中、选择范围和粗略统计窗口。导出 JSON 同样带覆盖率及检测范围。 |

例如 JSON 中 `target=right_wrist, axis=y, unit=shoulder_width, delta=-0.32, direction=up` 表示右腕相对右肩沿画面竖轴上移 0.32 个肩宽。画面横轴正数朝画面右侧，竖轴正数朝下。躯干侧倾是肩部中心与臀部中心连线在画面平面的角度。肩部中心移动用肩宽归一，可能混入摄像机运动。眉心、眼睑、嘴角、下颌分别记录 blendshape 系数的起点、终点和差值，系数不等于表情意图或情绪。眼部朝向字段仍为画面相对代理量。手指构形、明确指向目标、身体纵深旋转、说话人身份仍未标注。

相邻帧超过方向/幅度阈值后组成区间。遇到方向反转、关键点丢失、跨镜头、跨选择范围或切换模型时打断。视频采用目标 15 Hz，低帧率视频不会重新造帧。目标覆盖率 85% 以分析范围内所有抽样帧为分母，逐项报告，包括人脸、面部系数、上半身、髋肩兼可见和手部。手腕可用姿态估计，手部关键点须通过手部检测质量条件，两者分开统计。

## 可选 RTMW 和显卡

CPU 默认走 MediaPipe，可使用专用面部模型和局部缺失时的 Pose Heavy、Hand Landmarker。普通机器可先走这条路径。单讲者视频可选择本地 RTMW，只有模型检测到一个人且躯干点质量不低于原模块时才接管身体点位；多人物不会用该模块自动选择身份。

1. 项目用过 `uv pip install --no-deps rtmlib==0.0.16`。项目的 `video` 组合已经提供 cv2 和 NumPy，原依赖提供 ONNX Runtime。用 `--no-deps` 避免同时安装两个提供 cv2 的包。执行项目环境同步后，可能需要重新将这项可选包安装到运行环境。
2. 从 OpenMMLab 下载 [YOLOX Tiny](https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_tiny_8xb8-300e_humanart-6f3252f9.zip)、[RTMW-m](https://download.openmmlab.com/mmpose/v1/projects/rtmw/onnx_sdk/rtmw-dw-l-m_simcc-cocktail14_270e-256x192_20231122.zip) 或更大的 [RTMW-l](https://download.openmmlab.com/mmpose/v1/projects/rtmw/onnx_sdk/rtmw-dw-x-l_simcc-cocktail14_270e-384x288_20231122.zip)。分别将压缩包内的 `end2end.onnx` 放到同一目录，命名为 `yolox-tiny.onnx`、`pose-m.onnx`、`pose-l.onnx`。无需两个 pose 权重同时存在。
3. 设置 `VIDEO_RTMW_DIR=data/models/rtmw`、`VIDEO_RTMW_PRESET=m` 或 `l`。数据库、云端密钥均不需要。启用失败时后端会记录异常，练习仍返回可用的声音和转写。
4. 默认 `VIDEO_RTMW_DEVICE=cpu`。Windows 可选 `dml` 和 `VIDEO_RTMW_DML_DEVICE_ID=0`；CUDA 可选 `cuda`。换对应 ONNX Runtime（`onnxruntime-directml` 或 `onnxruntime-gpu`），切勿让同一 Python 路径混用多个发行版。可用 `uv pip install --target data/ort-dml --no-deps onnxruntime-directml==1.24.4` 和 `$env:PYTHONPATH=(Resolve-Path data/ort-dml).Path` 单独给一次 Windows 运行提供 DirectML。CUDA 需本机安装匹配的 CUDA 与 cuDNN DLL。程序检查实际执行提供程序；运行日志及 `tracking_sources` 会标识模型。更大的预设及 GPU 并不保证提高某条视频的覆盖率。

来源 [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)、[RTMW 官方发布](https://github.com/open-mmlab/mmpose/releases)、[RTMLib](https://github.com/Tau-J/rtmlib)、[ONNX Runtime DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html) 与 [CUDA](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

## 本次实测

- Windows，Python 3.12、Ryzen 9 9955HX。33 项测试通过，含真实本地 Whisper 音频集成，另用了 `node --check web/app.js` 检查前端。
- 本地 1080p 单人讲解前 25 秒，15 Hz 共 375 个采样帧，CPU 路径约 17.5 秒。人脸、面部系数、虹膜可用性和上半身都是 100%。报告有 192 条独立面部系数变化、11 条朝向变化，手腕覆盖 0%，手势事件 0 条。系数条目可在时间上重叠，例如两眼各有一条，不能当作动作总次数。
- 同一本地视频的 445.66 秒全片通过上传与查询接口跑通，6684 个采样帧。人脸、面部系数和上半身覆盖率均为 98.9%，虹膜可用性 95.2%。音频轨有 223 个连续电平区间，视频相对音频晚 0.023 秒。首次报告有一个 0.042 秒的腕部误报。将少于 0.12 秒的单次腕部变化设为不可确认手势后，对该次检测结果重新生成报告，手势事件为 0 条。0.12 秒是保守滤波阈值，极短真实动作也会被过滤。此轮只复用了提取结果执行最终过滤，未重跑全片模型。
- NASA [Earthrise 访谈](https://images.nasa.gov/details/Earthrise%20-%20A%20Conversation%20with%20Apollo%208%20Astronaut%20Bill%20Anders%20%28Official%20NASA%20Video%29) 的 132–151 秒截取段含中间长切镜。不设筛选时人脸覆盖 49.8%；给接口传样片本地播放范围 `[0,4.3)` 与 `[14.5,19)` 后，132 帧里人脸、面部系数和上半身均为 100%。音轨电平仍完整到 19.072 秒。NASA 旧档案整片只有人脸 19.8%、上半身 13.4%，没达到 85%。本次没有把低清、切镜或不可见帧误算成成功。
- CPU 上 RTMW-m 已实际完成推理。Windows DirectML 上 RTMW-m 和 RTMW-l 都跑通。RTMW-l 以外部的手部可见性作约束后，在 18 帧近景中没有把画外手计入覆盖。未验证 CUDA 执行路径和普通电脑的耗时下限。CPU 足以运行基础路径，速度受素材和机器影响。

### 默认视频模型的选择

同一个 1080p 单人片段前 25 秒，旧版 Holistic（10 Hz）约 13.4 秒，改版的专用 Face Landmarker 路径（15 Hz）约 17.6 秒，RTMW-m + DirectML 路径（15 Hz）约 19.8 秒。三者的人脸覆盖都是 100%。旧版输出 44 个泛化面部变化区间，改版输出眉心、眼闭合、嘴角、下颌等独立动作系数和相应时间，输出粒度有差异。

再用同片段前 12 秒做四次轮换复测，两种改版 CPU 路径都是 180 帧、人脸和面部动作系数覆盖 100%。Holistic 优先的自适应模式中位 7.24 秒，专用 Face 每帧运行中位 7.80 秒。默认选择 `VIDEO_FACE_MODE=adaptive`，只有缺少可用脸部点位或动作系数才调用专用 Face。可以用 `VIDEO_FACE_MODE=dedicated` 对困难素材复测。RTMW/CUDA/DirectML 保留可选，未观察到它们为这段单人正面素材增加脸部覆盖。完整 445.66 秒的 98.9% 数据来自专用 Face 模式，自适应模式暂只完成短段比较。

## 接手顺序和已知问题

- 先运行 `uv run --locked --extra video pytest -q`、`node --check web/app.js`。测试覆盖音视频不同偏移、同期轨道共存、同句多个动作、剪掉指定视觉范围、视频切镜和腕部方向反转。
- 按独立的人为标记选讲者画面，验证脸部和手部真实入镜，再评估检测样本覆盖率与误报。讲者时段的 85% 与整条剪辑的 85% 必须分别报告。画外手、无人的配图、观众特写没有讲者关键点。
- 用稳定单人正面、侧面、手出画、背光、观众切镜五类视频分别验收。双人节目需要目标身份关联。现在可以手工排除镜头，但仍需多人跟踪和样本标注，才适合自动区分谁是讲者。
- 当前值是可复核的近似测量。镜头转动和低画质仍可能引起误报，待加入摄像机运动补偿并校准手势幅度。专业语义分析可以消费导出的 JSON，这条练习链不会自动上传它。
