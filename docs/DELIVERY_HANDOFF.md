# 视频分析交接

## 当前分支和目标

分支是 `feature/multimodal-delivery-feedback`。练习报告在本地生成，画面和声音各用自己的时间轴，转写跟随音轨。想回看时可以打开 Markdown 报告。后续模块可以读取 JSON，里面有测量值和单位，也能查到每条记录对应的转写和画面覆盖率。样片、模型权重和实测结果都留在本机。

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

在 `.env` 里填上 `VIDEO_MODEL_PATH=data/models/holistic_landmarker.task`，运行 `uv run --locked --extra video uvicorn src.serve:app --env-file .env --port 8000`，再打开 <http://127.0.0.1:8000/app/>。三个专用模型可以放在同一目录，没有它们时也能用 Holistic。用 `VIDEO_FACE_MODE` 选择面部检测方式。练习复用 `main` 上已有的 WAV 提取和 faster-whisper 转写配置。首次使用某个 Whisper 模型可能需要下载权重。MP4 和 WebM 能否回看取决于浏览器是否支持视频编码。

上传时可以填写讲者出镜时间，比如 `00:05–00:28, 00:35–01:10`。调用 `POST /practice/submissions` 时，把 `[{"start":5,"end":28},{"start":35,"end":70}]` 作为表单字段 `presenter_ranges` 传入。区间按播放器秒数计算，包含开始时间，不含结束时间。区间不能重叠，超出片长的部分会忽略。留空就分析整片。排除观众镜头只影响画面分析，音频和转写仍保留整段。讲者出镜区间由用户填写，程序检测到切镜时会把前后的动作分开记。

## 报告接口

用 `GET /practice/submissions/{task_id}` 查询结果，转写仍可从 `result` 读取。新版报告的 `delivery_report.schema_version` 为 `2`，画面和声音各有时间轴。浏览器也能打开上一版带 `timeline` 的缓存报告。

| 字段 | 时间零点和内容 |
| --- | --- |
| `delivery_report.video` | 从首个有时间戳的视频帧算起。每条动作都有 `E…` ID 和起止时间。记录包含测量值，并引用同期音频和转写。 |
| `delivery_report.audio` | 解码后的 WAV 首样本为零点。保留 `A…` 的低能量段与可算语速区间。 |
| `delivery_report.audio_levels` | 同一 WAV 时间轴。每个连续 2 秒窗口（末段可能更短）记录 RMS dBFS 和 `L…` ID。音量表示数字音轨电平，无法估算实际分贝声压。 |
| `delivery_report.transcript` | 同一 WAV 时间轴。完整文本及原版的分句起止。多个独立动作可链接同一分句，报告不会把整句当成精确词位。 |
| `delivery_report.sync` | 给轨道时间加上对应偏移，就得到播放器时间。匹配语音时会把视频区间换算成音轨时间，转写分句仍用原来的时间。偏移按首样本计算。如果源音轨中间的时间戳有跳变，提取 WAV 时又压缩了间隙，后面的内容可能对不上。这类素材需要逐段换算。 |
| `delivery_evidence.visual` | 记录采样帧数和检测范围，以及各项覆盖率、补充模型命中次数和分段统计。导出的 JSON 也包含覆盖率和检测范围。 |

例如 JSON 中 `target=right_wrist, axis=y, unit=shoulder_width, delta=-0.32, direction=up` 表示右腕相对右肩上移了 0.32 个肩宽。画面横轴向右为正，竖轴向下为正。躯干侧倾取肩部中心与臀部中心连线在画面上的角度。肩部位移以肩宽为单位，摄像机移动也可能改变这个值。面部用 blendshape 系数描述眉心和眼睑的变化，嘴角和下颌也一样。每条记录都给出起始值、结束值和差值。眼部朝向按图像里的相对位置估算。情绪、手指形状、指向目标、身体纵深转动和说话人身份都需要进一步判断。

超过阈值的连续帧会合成一条动作。方向反转、关键点丢失、切镜、切换模型或离开选定范围时，当前动作结束。目标每秒抽 15 帧，帧率较低时按原片可用帧取样。每项覆盖率都用分析范围内的抽样帧数作分母，目标是 85%。手腕可以用姿态模型估算，手部关键点则要通过手部检测的质量检查。

## 可选 RTMW 和显卡

普通电脑可以先用默认的 CPU MediaPipe。需要补关键点时，可加装专用面部模型以及 Pose Heavy 和 Hand Landmarker。单讲者视频还可以选 RTMW。它只在检测到一人且躯干点质量达到原模型水平时替换身体关键点。多人素材需要事先选定讲者镜头。

1. 项目用过 `uv pip install --no-deps rtmlib==0.0.16`。项目的 `video` 组合已经提供 cv2 和 NumPy，原依赖提供 ONNX Runtime。用 `--no-deps` 避免同时安装两个提供 cv2 的包。执行项目环境同步后，可能需要重新将这项可选包安装到运行环境。
2. 从 OpenMMLab 下载 [YOLOX Tiny](https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_tiny_8xb8-300e_humanart-6f3252f9.zip)、[RTMW-m](https://download.openmmlab.com/mmpose/v1/projects/rtmw/onnx_sdk/rtmw-dw-l-m_simcc-cocktail14_270e-256x192_20231122.zip) 或更大的 [RTMW-l](https://download.openmmlab.com/mmpose/v1/projects/rtmw/onnx_sdk/rtmw-dw-x-l_simcc-cocktail14_270e-384x288_20231122.zip)。分别将压缩包内的 `end2end.onnx` 放到同一目录，命名为 `yolox-tiny.onnx`、`pose-m.onnx`、`pose-l.onnx`。无需两个 pose 权重同时存在。
3. 设置 `VIDEO_RTMW_DIR=data/models/rtmw`、`VIDEO_RTMW_PRESET=m` 或 `l`。数据库、云端密钥均不需要。启用失败时后端会记录异常，练习仍返回可用的声音和转写。
4. 默认 `VIDEO_RTMW_DEVICE=cpu`。Windows 可选 `dml` 和 `VIDEO_RTMW_DML_DEVICE_ID=0`；CUDA 可选 `cuda`。换对应 ONNX Runtime（`onnxruntime-directml` 或 `onnxruntime-gpu`），切勿让同一 Python 路径混用多个发行版。可用 `uv pip install --target data/ort-dml --no-deps onnxruntime-directml==1.24.4` 和 `$env:PYTHONPATH=(Resolve-Path data/ort-dml).Path` 单独给一次 Windows 运行提供 DirectML。CUDA 需本机安装匹配的 CUDA 与 cuDNN DLL。程序检查实际执行提供程序；运行日志及 `tracking_sources` 会标识模型。更大的预设及 GPU 并不保证提高某条视频的覆盖率。

来源 [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)、[RTMW 官方发布](https://github.com/open-mmlab/mmpose/releases)、[RTMLib](https://github.com/Tau-J/rtmlib)、[ONNX Runtime DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html) 与 [CUDA](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

## 本次实测

- Windows，Python 3.12、Ryzen 9 9955HX。33 项测试通过，含真实本地 Whisper 音频集成，另用了 `node --check web/app.js` 检查前端。
- 本地 1080p 单人讲解前 25 秒，15 Hz 共 375 个采样帧，CPU 路径约 17.5 秒。人脸、面部系数、虹膜可用性和上半身都是 100%。报告有 192 条独立面部系数变化、11 条朝向变化，手腕覆盖 0%，手势事件 0 条。系数条目可在时间上重叠，例如两眼各有一条，不能当作动作总次数。
- 同一段 445.66 秒单人视频用上传和查询接口跑过全片，每轮采样 6,684 帧。默认自适应模式用 CPU 跑完用时 242.2 秒，含本地 Whisper Small 英文转写。人脸、面部系数和上半身覆盖率均为 98.9%，虹膜是 94.4%。音轨有 223 个连续电平窗口，画面时间加 0.023 秒即可对到播放器。手部覆盖率为 0.4%，回看确认三条腕部记录来自同一次动作。三条肩部位移都与景别切换同时出现，髋部也一直在画面外，无法评价躯干侧倾。较早用专用 Face 模式跑全片时，虹膜覆盖率为 95.2%。该轮出现过一条 0.042 秒的腕部误报。按后来采用的 0.12 秒阈值对这轮已有结果重新过滤，误报消失。这个阈值也可能滤掉极短的真实动作。
- NASA [Earthrise 访谈](https://images.nasa.gov/details/Earthrise%20-%20A%20Conversation%20with%20Apollo%208%20Astronaut%20Bill%20Anders%20%28Official%20NASA%20Video%29) 的 132–151 秒截取段含中间长切镜。不设筛选时人脸覆盖 49.8%；给接口传样片本地播放范围 `[0,4.3)` 与 `[14.5,19)` 后，132 帧里人脸、面部系数和上半身均为 100%。音轨电平仍完整到 19.072 秒。NASA 旧档案整片只有人脸 19.8%、上半身 13.4%，没达到 85%。本次没有把低清、切镜或不可见帧误算成成功。
- CPU 上 RTMW-m 已实际完成推理。Windows DirectML 上 RTMW-m 和 RTMW-l 都跑通。RTMW-l 以外部的手部可见性作约束后，在 18 帧近景中没有把画外手计入覆盖。未验证 CUDA 执行路径和普通电脑的耗时下限。CPU 足以运行基础路径，速度受素材和机器影响。

### 默认视频模型的选择

同一个 1080p 单人片段前 25 秒，旧版 Holistic（10 Hz）约 13.4 秒，改版的专用 Face Landmarker 路径（15 Hz）约 17.6 秒，RTMW-m + DirectML 路径（15 Hz）约 19.8 秒。三者的人脸覆盖都是 100%。旧版输出 44 个泛化面部变化区间，改版输出眉心、眼闭合、嘴角、下颌等独立动作系数和相应时间，输出粒度有差异。

在同一视频的前 12 秒轮换跑了四次。两种 CPU 路径都采样 180 帧，人脸和面部系数覆盖率都是 100%。Holistic 优先的模式中位耗时 7.24 秒，每帧跑专用 Face 的模式用了 7.80 秒。默认用 `VIDEO_FACE_MODE=adaptive`，Holistic 缺少可用脸部点位或动作系数时才调用专用 Face。遇到难跟踪的素材，可以用 `VIDEO_FACE_MODE=dedicated` 复测。这段单人正面素材的短片测试已经达到 100% 人脸覆盖率，RTMW 仍可按需启用。

## 接手顺序和已知问题

- 先运行 `uv run --locked --extra video pytest -q`、`node --check web/app.js`。测试覆盖音视频不同偏移、同期轨道共存、同句多个动作、剪掉指定视觉范围、视频切镜和腕部方向反转。
- 先人工标出讲者镜头，并确认脸和手是否入镜，再查覆盖率和误报。讲者出镜时段和整条剪辑分别计算覆盖率。画外的手无法跟踪，配图和观众特写也可能看不到讲者。
- 用稳定单人正面、侧面、手出画、背光、观众切镜五类视频分别验收。双人节目需要目标身份关联。现在可以手工排除镜头，但仍需多人跟踪和样本标注，才适合自动区分谁是讲者。
- 镜头运动和低画质都可能让测量失准。后续可先补摄像机运动补偿，再校准手势幅度。需要做表达分析时，可以把本地导出的 JSON 交给后续模块。
