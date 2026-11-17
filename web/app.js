const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "ely5.practice.v1";
const panels = ["topic", "prepare", "upload", "result"];
const zh = {};
document.querySelectorAll("[data-i18n]").forEach((el) => {
  zh[el.dataset.i18n] = el.innerHTML;
});
const en = {
  edition: "A little curiosity. A new explanation.",
  yourPractice: "YOUR PRACTICE",
  stepTopic: "Meet a new concept",
  stepTopicSub: "Start with curiosity",
  stepPrepare: "Make sense of it",
  stepPrepareSub: "Explore, understand, organize",
  stepUpload: "Put it in your words",
  stepUploadSub: "Upload your explanation",
  stepResult: "Look back and learn",
  stepResultSub: "Reflect on your explanation",
  sidebarQuote:
    "Make a concept<br>a little simpler.<br>Understand it a little better.",
  sidebarNote: "Start with one explanation.",
  localPractice: "A moment of focused learning",
  topicKicker: "START WITH A QUESTION",
  topicHeading: "New knowledge.<br><em>Your own words.</em>",
  topicLead:
    "Draw a concept and take some time to explore. Then explain it to someone who is hearing about it for the first time.",
  field: "Explore a field",
  allFields: "All fields",
  difficulty: "Choose a challenge",
  allLevels: "Open exploration",
  starter: "Starter · Everyday ideas",
  intermediate: "Intermediate · Go deeper",
  advanced: "Advanced · Complex ideas",
  speakingLanguage: "Explain in",
  yourConcept: "THIS TIME, TRY EXPLAINING",
  redraw: "Draw another concept",
  startPreparing: "Let’s explore this one",
  principle:
    "You don’t need to recite a definition. One good example can do more than a string of unfamiliar words.",
  prepareKicker: "MAKE ROOM FOR UNDERSTANDING",
  prepareHeading: "Make sense of it.<br><em>Then make it simple.</em>",
  thisConcept: "Your concept: ",
  prepRemaining: "PREPARATION TIME",
  timerHelp:
    "Look things up, find an example, and give your ideas a little structure.",
  pause: "Pause timer",
  thinkAbout: "Explore with three questions",
  question1: "What does it actually mean?",
  question2: "What is a good everyday example?",
  question3: "What might someone misunderstand?",
  notesLabel: "A few keywords to organize your thoughts",
  notesHint: "Notes stay in this browser session and are not evaluated.",
  backTopic: "← Choose a different concept",
  readyUpload: "I’m ready to upload",
  uploadKicker: "TURN UNDERSTANDING INTO EXPRESSION",
  uploadHeading: "Take the camera.<br><em>Explain it your way.</em>",
  chooseVideo: "Choose or drop your explanation video",
  removeVideo: "Remove and choose again",
  uploadTip:
    "Find a quiet spot and make sure your voice is clear. The server deletes your video after processing.",
  backPrepare: "← Back to preparation",
  submitVideo: "Submit my explanation",
  uploadStage: "Upload video",
  extractStage: "Read audio",
  transcribeStage: "Transcribe speech",
  deliveryStage: "Analyze delivery",
  cloudReportNotice: "The delivery report sends the topic, transcript, and audio and visual summaries to DeepSeek.",
  reconnect: "Continue checking results",
  newPractice: "Start a new practice",
  resultKicker: "A RECORD OF WHAT YOU LEARNED",
  resultHeading: "Your explanation.<br><em>Worth another listen.</em>",
  transcriptionDone: "Speech transcription complete",
  fullText: "Full explanation",
  segments: "By segment",
  transcriptCaution:
    "The transcript may contain recognition errors. You can check the report against the original video.",
  downloadResult: "↓ Save this result",
  practiceAgain: "Explore another concept",
  footer: "Every explanation is a chance to learn.",
};
let state = {
  ui: "zh",
  stage: "topic",
  language: "zh",
  term: null,
  taskId: null,
  result: null,
  notes: "",
  remaining: 0,
  deadline: null,
  category: "",
  difficulty: "",
};
try {
  const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
  if (saved) state = { ...state, ...saved };
} catch {
  /* Session storage may be unavailable. */
}
if (!["zh", "en"].includes(state.ui)) state.ui = "zh";
if (!panels.includes(state.stage)) state.stage = "topic";
let catalog = null;
let selectedFile = null;
let videoUrl = null;
let busy = false;
let drawSequence = 0;
let pollSequence = 0;
let processingStarted = 0;
let processingStatus = "uploading";
let currentResult = null;
const words = (cn, english) => (state.ui === "en" ? english : cn);
const persist = () => {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* The flow also works without storage. */
  }
};
const showNotice = (message) => {
  $("notice").textContent = message;
  $("notice").hidden = !message;
};
const formatTime = (seconds) => {
  const value = Math.max(0, Math.ceil(seconds));
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
};
const levelName = (level) =>
  ({
    starter: words("入门", "Starter"),
    intermediate: words("进阶", "Intermediate"),
    advanced: words("挑战", "Advanced"),
  })[level] || level;
const remainingSeconds = () =>
  state.deadline
    ? Math.max(0, (state.deadline - Date.now()) / 1000)
    : state.remaining;

async function api(path, options = {}) {
  const response = await fetch(path, {
    signal: AbortSignal.timeout(20000),
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message =
      typeof data.detail === "string"
        ? data.detail
        : words(
            "请求没有完成，请稍后重试。",
            "The request failed. Please try again.",
          );
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function renderLanguage() {
  document.documentElement.lang = state.ui === "zh" ? "zh-CN" : "en";
  document.title = words(
    "讲解师 · 把新知识，讲成自己的话",
    "Explain Like You’re 5 · Your own words",
  );
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    el.innerHTML = state.ui === "zh" ? zh[key] : en[key] || zh[key];
  });
  $("ui-language").textContent = state.ui === "zh" ? "EN ↗" : "中文 ↗";
  $("notes").placeholder = words(
    "一个例子、一个关键区别、一句话结论……",
    "One example, one key distinction, one sentence to remember…",
  );
  if (catalog) {
    $("cloud-report-notice").hidden = !catalog.delivery_report_enabled;
    const category = $("category");
    category
      .querySelectorAll("option:not(:first-child)")
      .forEach((option) => option.remove());
    Object.entries(catalog.categories).forEach(([key, value]) => {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = value[state.ui];
      category.append(option);
    });
    category.value = state.category;
    $("catalog-count").textContent = words(
      `${catalog.terms.length} 个概念 · 中英双语探索`,
      `${catalog.terms.length} concepts · Two languages`,
    );
    $("file-limits").textContent = words(
      `MP4 / MOV / WebM / MKV / M4V · ≤ ${catalog.limits.max_upload_mb} MB · ≤ ${catalog.limits.max_video_seconds / 60} 分钟`,
      `MP4 / MOV / WebM / MKV / M4V · ≤ ${catalog.limits.max_upload_mb} MB · ≤ ${catalog.limits.max_video_seconds / 60} min`,
    );
  }
  renderTerm();
  renderTimer();
  if (busy || state.taskId) renderProcessing(processingStatus);
  if (currentResult) renderResult(currentResult);
}

function renderTerm() {
  const term = state.term;
  if (!term) return;
  $("term-title").textContent = term.title[state.language];
  $("term-translation").textContent =
    term.title[state.language === "zh" ? "en" : "zh"];
  $("term-title").lang = state.language;
  $("term-prompt").textContent = term.prompt[state.language];
  $("term-category").textContent =
    catalog?.categories[term.category]?.[state.ui] || term.category;
  $("term-level").textContent = levelName(term.difficulty);
  $("prep-time").textContent = words(
    `准备 ${term.preparation_seconds / 60} 分钟`,
    `${term.preparation_seconds / 60} min to explore`,
  );
  $("speak-time").textContent = words(
    `讲解约 ${term.speaking_seconds} 秒`,
    `About ${term.speaking_seconds}s to explain`,
  );
  $("prepare-term").textContent = term.title[state.language];
  $("prepare-prompt").textContent = term.prompt[state.language];
  $("upload-instruction").textContent = words(
    `用${state.language === "zh" ? "中文" : "英文"}讲清「${term.title[state.language]}」，建议 ${term.speaking_seconds} 秒左右。请用手机或电脑录好视频，再上传到这里。`,
    `Explain “${term.title[state.language]}” in ${state.language === "zh" ? "Chinese" : "English"}, in about ${term.speaking_seconds} seconds. Record on your phone or computer, then upload it here.`,
  );
}

function go(stage, focus = true) {
  state.stage = stage;
  panels.forEach((name) => {
    $(`${name}-panel`).hidden = name !== stage;
  });
  document.querySelectorAll("[data-step]").forEach((el) => {
    const index = panels.indexOf(el.dataset.step);
    el.classList.toggle("active", el.dataset.step === stage);
    el.classList.toggle("done", index < panels.indexOf(stage));
    if (el.dataset.step === stage) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  });
  persist();
  if (focus) {
    $("main").focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }
}

async function draw() {
  const sequence = ++drawSequence;
  $("redraw").disabled = true;
  $("start-prepare").disabled = true;
  showNotice("");
  state.category = $("category").value;
  state.difficulty = $("difficulty").value;
  const query = new URLSearchParams();
  if (state.category) query.set("category", state.category);
  if (state.difficulty) query.set("difficulty", state.difficulty);
  if (state.term) query.set("exclude_id", state.term.id);
  try {
    if (!catalog) {
      catalog = await api("/practice/vocabulary");
      renderLanguage();
    }
    const term = await api(`/practice/terms/random?${query}`);
    if (sequence !== drawSequence) return;
    state.term = term;
    state.notes = "";
    $("notes").value = "";
    state.remaining = term.preparation_seconds;
    state.deadline = null;
    renderTerm();
    persist();
    $("start-prepare").disabled = false;
  } catch (error) {
    if (sequence !== drawSequence) return;
    showNotice(
      error.message ||
        words(
          "词库暂时无法连接，请点击“换一个概念”重试。",
          "Cannot reach the vocabulary. Draw again to retry.",
        ),
    );
  } finally {
    if (sequence === drawSequence) $("redraw").disabled = false;
  }
}

function renderTimer() {
  const remaining = remainingSeconds();
  $("timer").textContent = formatTime(remaining);
  $("toggle-timer").textContent =
    remaining <= 0
      ? words("再给自己 1 分钟", "Add one more minute")
      : state.deadline
        ? words("暂停计时", "Pause timer")
        : words("继续计时", "Resume timer");
  if (remaining <= 0) {
    $("timer-message").textContent = words(
      "准备时间到了。可以继续想一想，也可以去录制了。",
      "Time is up. Take a little more time, or start recording.",
    );
    if (state.deadline) {
      state.deadline = null;
      state.remaining = 0;
      persist();
    }
  } else
    $("timer-message").textContent = words(
      "查资料、想例子，也留一点时间理清顺序。",
      "Look things up, find an example, and give your ideas a little structure.",
    );
}

function pauseTimer() {
  state.remaining = remainingSeconds();
  state.deadline = null;
  persist();
  renderTimer();
}
function clearFile() {
  selectedFile = null;
  for (const id of ["video-preview", "result-video"]) {
    const player = $(id);
    player.pause();
    if (player.hasAttribute("src")) {
      player.removeAttribute("src");
      player.load();
    }
  }
  if (videoUrl) URL.revokeObjectURL(videoUrl);
  videoUrl = null;
  $("video-file").value = "";
  $("file-preview").hidden = true;
  $("drop-zone").hidden = false;
  $("submit-video").disabled = true;
}
function selectFile(file) {
  if (!file || busy) return;
  clearFile();
  showNotice("");
  if (!/\.(mp4|mov|webm|mkv|m4v)$/i.test(file.name)) {
    showNotice(
      words(
        "请选择 MP4、MOV、WebM、MKV 或 M4V 视频。",
        "Please choose an MP4, MOV, WebM, MKV, or M4V video.",
      ),
    );
    return;
  }
  if (!file.size || file.size > catalog.limits.max_upload_mb * 1024 * 1024) {
    showNotice(
      words(
        `视频不能为空，且不能超过 ${catalog.limits.max_upload_mb} MB。`,
        `Choose a nonempty video under ${catalog.limits.max_upload_mb} MB.`,
      ),
    );
    return;
  }
  selectedFile = file;
  videoUrl = URL.createObjectURL(file);
  $("video-preview").src = videoUrl;
  $("file-name").textContent = file.name;
  $("file-size").textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  $("file-preview").hidden = false;
  $("drop-zone").hidden = true;
  $("submit-video").disabled = false;
}

function setProcessing(visible) {
  $("upload-controls").hidden = visible;
  $("upload-actions").hidden = visible;
  $("processing").hidden = !visible;
}
function renderProcessing(status) {
  processingStatus = status;
  const descriptions = {
    uploading: [
      words("正在上传视频", "Uploading your video"),
      words(
        "上传完成后，会开始读取视频中的音轨。",
        "Once the upload finishes, we’ll read the audio in your video.",
      ),
    ],
    queued: [
      words("上传完成，等待处理", "Uploaded and waiting"),
      words(
        "你的讲解已收到，正在等待前面的任务完成。",
        "Your explanation is received and waiting for the previous task to finish.",
      ),
    ],
    extracting: [
      words("正在读取视频音轨", "Reading your video’s audio"),
      words(
        "正在提取视频中的声音。",
        "Extracting the audio from your video.",
      ),
    ],
    transcribing: [
      words("正在把你的讲解写下来", "Transcribing your explanation"),
      words(
        "首次使用可能需要下载语音模型，耗时会较长。你可以留在这里等待。",
        "The first use may need to download a speech model and take longer. You can wait here.",
      ),
    ],
    analyzing_delivery: [
      words("正在提取表达证据", "Analyzing your delivery"),
      words("正在分析声音和可用的画面特征。", "Analyzing audio and available visual features."),
    ],
    generating_report: [
      words("正在生成综合报告", "Preparing your report"),
      words("正在结合转写和带时间段的证据。", "Combining your transcript with timestamped evidence."),
    ],
  };
  const [heading, description] = descriptions[status] || descriptions.queued;
  $("processing-heading").textContent = heading;
  $("processing-description").textContent = description;
  $("elapsed").textContent = processingStarted
    ? formatTime((Date.now() - processingStarted) / 1000)
    : "";
  const active =
    { uploading: 0, queued: 1, extracting: 1, transcribing: 2, analyzing_delivery: 3, generating_report: 3 }[status] ?? 1;
  document.querySelectorAll("[data-processing]").forEach((el, i) => {
    el.classList.toggle("current", i === active);
    el.classList.toggle("complete", i < active);
  });
  // 百分比只展示浏览器提供的上传进度。模型处理期间用不定进度，避免虚构百分比。
  if (status !== "uploading") $("upload-progress").removeAttribute("value");
}

function uploadVideo(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/practice/submissions");
    xhr.timeout = 600000;
    const body = new FormData();
    body.append("file", file);
    body.append("term_id", state.term.id);
    body.append("language", state.language);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        $("upload-progress").value = Math.round(
          (event.loaded / event.total) * 100,
        );
    };
    xhr.onload = () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        reject(
          new Error(
            words(
              "服务器未返回有效结果，请稍后重试。",
              "The server returned an invalid response. Please try again.",
            ),
          ),
        );
        return;
      }
      if (xhr.status === 202 && data.task_id) resolve(data);
      else
        reject(
          new Error(
            typeof data.detail === "string"
              ? data.detail
              : words("上传未完成，请重试。", "Upload failed. Please retry."),
          ),
        );
    };
    xhr.onerror = () =>
      reject(
        new Error(
          words(
            "上传连接中断，请检查网络后重试。",
            "The upload connection was lost. Check your network and retry.",
          ),
        ),
      );
    xhr.ontimeout = () =>
      reject(
        new Error(
          words(
            "上传等待超时，请检查网络后重试。",
            "The upload timed out. Check your network and retry.",
          ),
        ),
      );
    xhr.send(body);
  });
}

async function poll(taskId) {
  const sequence = ++pollSequence;
  const started = Date.now();
  let failures = 0;
  busy = true;
  setProcessing(true);
  $("reconnect-controls").hidden = true;
  showNotice("");
  while (sequence === pollSequence) {
    try {
      const task = await api(
        `/practice/submissions/${encodeURIComponent(taskId)}`,
      );
      if (sequence !== pollSequence) return;
      failures = 0;
      if (task.status === "completed") {
        busy = false;
        state.result = task;
        currentResult = task;
        renderResult(task);
        go("result");
        return;
      }
      if (task.status === "failed") {
        busy = false;
        state.taskId = null;
        persist();
        setProcessing(false);
        showNotice(
          task.error ||
            words(
              "处理失败，请重新上传视频。",
              "Processing failed. Please upload again.",
            ),
        );
        return;
      }
      renderProcessing(task.status);
    } catch (error) {
      if (sequence !== pollSequence) return;
      failures += 1;
      if (error.status === 404) {
        busy = false;
        state.taskId = null;
        persist();
        setProcessing(false);
        showNotice(
          words(
            "没有找到这次任务，服务可能已经重启。请选择视频重新提交。",
            "This task was not found. The server may have restarted; choose your video and submit again.",
          ),
        );
        return;
      }
      if (failures >= 3) {
        busy = false;
        showNotice(
          words(
            "暂时无法读取任务状态。已保留任务编号，恢复连接后可继续查看。",
            "Cannot read the task status. Its ID is saved; continue checking after reconnecting.",
          ),
        );
        $("reconnect-controls").hidden = false;
        return;
      }
    }
    if (Date.now() - started > 15 * 60 * 1000) {
      busy = false;
      showNotice(
        words(
          "处理时间较长，已暂停自动查询。任务可能仍在运行，可以继续查看。",
          "Processing is taking a while. Automatic checks are paused; the task may still be running.",
        ),
      );
      $("reconnect-controls").hidden = false;
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

function renderResult(task) {
  if (!task.result) return;
  $("result-summary").textContent =
    `${task.term.title[task.language]} · ${task.language === "zh" ? words("中文讲解", "Chinese explanation") : words("英文讲解", "English explanation")}`;
  $("result-duration").textContent =
    task.result.duration == null
      ? ""
      : words(
          `音轨时长 ${formatTime(task.result.duration)}`,
          `Audio duration ${formatTime(task.result.duration)}`,
        );
  $("full-text").textContent = task.result.text;
  $("full-text").lang = task.result.language || task.language;
  $("segments").replaceChildren();
  const audioOffset = task.delivery_evidence?.audio_offset_seconds || 0;
  for (const segment of task.result.segments || []) {
    const row = document.createElement("div");
    row.className = "segment-row";
    const time = document.createElement("span");
    time.className = "segment-time";
    time.textContent = `${formatTime(Math.floor(segment.start + audioOffset))}–${formatTime(segment.end + audioOffset)}`;
    const text = document.createElement("p");
    text.textContent = segment.text;
    row.append(time, text);
    $("segments").append(row);
  }
  if (!task.result.segments?.length)
    $("segments").textContent = words(
      "这次转写没有提供分段时间。",
      "This transcript has no segment timestamps.",
    );
  renderDelivery(task);
}

function renderDelivery(task) {
  const container = $("evaluation-modules");
  const player = $("result-video");
  container.replaceChildren();
  player.hidden = !videoUrl;
  if (videoUrl && player.getAttribute("src") !== videoUrl) player.src = videoUrl;
  if (!videoUrl) player.removeAttribute("src");

  const evidence = task.delivery_evidence;
  const visual = evidence?.visual?.windows || [];
  const audio = evidence?.audio || [];
  const offset = evidence?.audio_offset_seconds || 0;
  const transcript = (task.result.segments || []).map((segment) => ({
    id: `T${segment.id}`, start: segment.start + offset, end: segment.end + offset,
  }));
  const timeline = new Map([...visual, ...audio, ...transcript].map((entry) => [entry.id, entry]));
  const statusLabels = {
    completed: words("已完成", "Ready"),
    pending: words("未启用", "Not enabled"),
    insufficient_evidence: words("证据不足", "Insufficient evidence"),
    failed: words("生成失败", "Unavailable"),
  };

  function createCard(title, status, body) {
    const card = document.createElement("article");
    card.className = "module-card";
    const badge = document.createElement("span");
    badge.textContent = statusLabels[status] || statusLabels.pending;
    const heading = document.createElement("h3");
    heading.textContent = title;
    const copy = document.createElement("p");
    copy.textContent = body;
    card.append(badge, heading, copy);
    container.append(card);
    return card;
  }

  createCard(words("画面证据", "Visual evidence"), task.modules?.video_evaluation?.status,
    words(`${visual.length} 个有可用特征的时间段`, `${visual.length} time windows with visible features`));
  createCard(words("声音证据", "Audio evidence"), task.modules?.audio_evidence?.status,
    words(`${audio.length} 条语速或低音量记录`, `${audio.length} pace or quiet-interval observations`));

  const report = task.delivery_report;
  const card = createCard(words("综合表达反馈", "Delivery report"), task.modules?.delivery_report?.status,
    report?.summary || words("本次练习没有综合报告。可以下载已取得的证据。",
      "There is no report for this practice. You can download the available evidence."));
  card.classList.add("delivery-report-card");
  if (!report) return;
  card.querySelector("p").lang = task.language;
  const dimensions = {
    gaze: words("镜头朝向与视线变化", "Head direction and gaze changes"),
    posture: words("姿态", "Posture"),
    gesture: words("手势", "Gestures"),
    face: words("面部动作", "Facial movement"),
    voice: words("声音节奏", "Vocal pacing"),
    structure: words("讲解结构", "Explanation structure"),
    coordination: words("动作与内容配合", "Delivery and content"),
  };
  const list = document.createElement("ul");
  list.className = "delivery-feedback";
  for (const item of report.feedback) {
    const row = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = dimensions[item.dimension];
    const detail = document.createElement("p");
    if (item.status === "observed") {
      detail.lang = task.language;
      detail.textContent = `${item.observation} ${item.suggestion}`;
    } else {
      detail.textContent = statusLabels.insufficient_evidence;
    }
    row.append(label, detail);
    for (const id of item.evidence_ids) {
      const entry = timeline.get(id);
      if (!entry) continue;
      const time = `${formatTime(Math.floor(entry.start))}–${formatTime(entry.end)}`;
      const link = document.createElement(videoUrl ? "button" : "small");
      link.textContent = videoUrl ? words(`回看 ${time}`, `Review ${time}`) : `${time} `;
      if (videoUrl) {
        link.type = "button";
        link.className = "text-button";
        link.addEventListener("click", () => {
          player.currentTime = entry.start;
          player.focus();
          player.play().catch(() => {});
        });
      }
      row.append(link);
    }
    list.append(row);
  }
  card.append(list);
}

function resetPractice() {
  pollSequence++;
  busy = false;
  state.taskId = null;
  state.result = null;
  currentResult = null;
  state.notes = "";
  $("notes").value = "";
  state.deadline = null;
  state.remaining = 0;
  clearFile();
  setProcessing(false);
  showNotice("");
  go("topic");
  draw();
}

$("ui-language").addEventListener("click", () => {
  state.ui = state.ui === "zh" ? "en" : "zh";
  persist();
  renderLanguage();
});
$("category").addEventListener("change", draw);
$("difficulty").addEventListener("change", draw);
$("redraw").addEventListener("click", draw);
document.querySelectorAll('[name="speaking-language"]').forEach((el) =>
  el.addEventListener("change", () => {
    state.language = el.value;
    persist();
    renderTerm();
  }),
);
$("start-prepare").addEventListener("click", () => {
  if (!state.term) return;
  state.deadline = Date.now() + state.term.preparation_seconds * 1000;
  state.remaining = state.term.preparation_seconds;
  showNotice("");
  renderTimer();
  go("prepare");
});
$("toggle-timer").addEventListener("click", () => {
  if (state.deadline) pauseTimer();
  else {
    if (state.remaining <= 0) state.remaining = 60;
    state.deadline = Date.now() + state.remaining * 1000;
    persist();
    renderTimer();
  }
});
$("notes").addEventListener("input", () => {
  state.notes = $("notes").value;
  persist();
});
$("back-topic").addEventListener("click", () => {
  pauseTimer();
  go("topic");
});
$("ready-upload").addEventListener("click", () => {
  pauseTimer();
  go("upload");
});
$("back-prepare").addEventListener("click", () => go("prepare"));
$("video-file").addEventListener("change", (event) =>
  selectFile(event.target.files[0]),
);
$("remove-video").addEventListener("click", clearFile);
for (const type of ["dragover", "dragenter"])
  $("drop-zone").addEventListener(type, (event) => {
    event.preventDefault();
    $("drop-zone").classList.add("dragging");
  });
for (const type of ["dragleave", "drop"])
  $("drop-zone").addEventListener(type, (event) => {
    event.preventDefault();
    $("drop-zone").classList.remove("dragging");
    if (type === "drop") selectFile(event.dataTransfer.files[0]);
  });
$("video-preview").addEventListener("loadedmetadata", () => {
  if (
    Number.isFinite($("video-preview").duration) &&
    $("video-preview").duration > catalog.limits.max_video_seconds
  ) {
    clearFile();
    showNotice(
      words(
        `视频超过 ${catalog.limits.max_video_seconds / 60} 分钟，请剪短后重新选择。`,
        `The video exceeds ${catalog.limits.max_video_seconds / 60} minutes. Trim it and choose again.`,
      ),
    );
  }
});
$("submit-video").addEventListener("click", async () => {
  if (!selectedFile || busy || !state.term) return;
  busy = true;
  processingStarted = Date.now();
  setProcessing(true);
  renderProcessing("uploading");
  $("reconnect-controls").hidden = true;
  $("upload-progress").value = 0;
  showNotice("");
  try {
    const task = await uploadVideo(selectedFile);
    state.taskId = task.task_id;
    persist();
    renderProcessing(task.status);
    await poll(task.task_id);
  } catch (error) {
    busy = false;
    setProcessing(false);
    showNotice(error.message);
  }
});
$("reconnect").addEventListener("click", () => {
  if (state.taskId && !busy) {
    processingStarted = Date.now();
    poll(state.taskId);
  }
});
$("new-after-error").addEventListener("click", resetPractice);
$("practice-again").addEventListener("click", resetPractice);
$("download-result").addEventListener("click", () => {
  if (!currentResult) return;
  const blob = new Blob([JSON.stringify(currentResult, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ely5-${currentResult.term.id}-${currentResult.task_id.slice(0, 8)}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
function selectResultTab(segmented) {
  $("full-text").hidden = segmented;
  $("segments").hidden = !segmented;
  $("full-tab").classList.toggle("active", !segmented);
  $("segments-tab").classList.toggle("active", segmented);
  $("full-tab").setAttribute("aria-selected", String(!segmented));
  $("segments-tab").setAttribute("aria-selected", String(segmented));
  $("full-tab").tabIndex = segmented ? -1 : 0;
  $("segments-tab").tabIndex = segmented ? 0 : -1;
}
$("full-tab").addEventListener("click", () => selectResultTab(false));
$("segments-tab").addEventListener("click", () => selectResultTab(true));
document.querySelector(".result-tabs").addEventListener("keydown", (event) => {
  if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const segmented =
      event.key === "End" || (event.key !== "Home" && $("segments").hidden);
    selectResultTab(segmented);
    $(segmented ? "segments-tab" : "full-tab").focus();
  }
});
window.addEventListener("pagehide", (event) => {
  persist();
  if (!event.persisted && videoUrl) URL.revokeObjectURL(videoUrl);
});
setInterval(() => {
  if (state.stage === "prepare") renderTimer();
  if (busy)
    $("elapsed").textContent = formatTime(
      (Date.now() - processingStarted) / 1000,
    );
}, 500);

async function init() {
  renderLanguage();
  go("topic", false);
  try {
    catalog = await api("/practice/vocabulary");
    $("category").value = state.category;
    $("difficulty").value = state.difficulty;
    document.querySelectorAll('[name="speaking-language"]').forEach((el) => {
      el.checked = el.value === state.language;
    });
    $("notes").value = state.notes;
    renderLanguage();
    if (
      !state.term ||
      !catalog.terms.some((term) => term.id === state.term.id)
    ) {
      state.taskId = null;
      state.result = null;
      await draw();
      return;
    }
    state.term = catalog.terms.find((term) => term.id === state.term.id);
    renderTerm();
    $("start-prepare").disabled = false;
    if (state.result?.status === "completed" && state.result.result) {
      currentResult = state.result;
      renderResult(currentResult);
      go("result", false);
    } else if (state.taskId) {
      go("upload", false);
      processingStarted = Date.now();
      renderProcessing("queued");
      poll(state.taskId);
    } else if (restoredStage === "prepare") {
      go("prepare", false);
      renderTimer();
    } else if (restoredStage === "upload") {
      go("upload", false);
      showNotice(
        words(
          "视频文件需要重新选择；你的题目和笔记已保留。",
          "Please choose the video again. Your concept and notes have been kept.",
        ),
      );
    }
  } catch {
    showNotice(
      words(
        "暂时无法连接词库，请确认服务正常，再点击“换一个概念”重试。",
        "Cannot reach the vocabulary. Check the server, then draw again to retry.",
      ),
    );
  }
}
const restoredStage = state.stage;
init();
