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
  reconnect: "Continue checking results",
  newPractice: "Start a new practice",
  resultKicker: "A RECORD OF WHAT YOU LEARNED",
  resultHeading: "Your explanation.<br><em>Worth another listen.</em>",
  transcriptionDone: "Speech transcription complete",
  fullText: "Full explanation",
  segments: "By segment",
  transcriptCaution:
    "Speech and movement timings are local estimates. You can check them against the original video.",
  downloadResult: "↓ Download video report",
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
  };
  const [heading, description] = descriptions[status] || descriptions.queued;
  $("processing-heading").textContent = heading;
  $("processing-description").textContent = description;
  $("elapsed").textContent = processingStarted
    ? formatTime((Date.now() - processingStarted) / 1000)
    : "";
  const active =
    { uploading: 0, queued: 1, extracting: 1, transcribing: 2, analyzing_delivery: 3 }[status] ?? 1;
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
    time.textContent = `${preciseTime(segment.start + audioOffset)}–${preciseTime(segment.end + audioOffset)}`;
    const text = document.createElement("p");
    if (videoUrl && segment.words?.length) {
      for (const word of segment.words) {
        const start = word.start + audioOffset;
        const token = word.text.trim();
        if (word.text.startsWith(" ")) text.append(" ");
        text.append(reviewAt(start, `${token} · ${preciseTime(start)}`, token));
      }
    } else {
      text.textContent = segment.text;
    }
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

function preciseTime(seconds) {
  const ticks = Math.max(0, Math.round(seconds * 100));
  const minutes = String(Math.floor(ticks / 6000)).padStart(2, "0");
  const whole = String(Math.floor(ticks / 100) % 60).padStart(2, "0");
  return `${minutes}:${whole}.${String(ticks % 100).padStart(2, "0")}`;
}

function reviewAt(time, label, visibleText) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "text-button review-time";
  button.textContent = visibleText || label;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", () => {
    const player = $("result-video");
    player.currentTime = time;
    player.focus();
    player.play().catch(() => {});
  });
  return button;
}

function describeMoment(entry) {
  const metrics = entry.metrics;
  if (entry.kind === "quiet") {
    return words(`声音能量较低，持续 ${metrics.quiet_seconds} 秒`,
      `Low audio energy for ${metrics.quiet_seconds} s`);
  }
  if (entry.kind === "pace") {
    const rates = [];
    if ("han_characters_per_minute" in metrics) {
      const count = metrics.han_characters_per_minute;
      rates.push(words(`约 ${count} 汉字/分钟`, `about ${count} Han characters/min`));
    }
    if ("latin_words_per_minute" in metrics) {
      const count = metrics.latin_words_per_minute;
      rates.push(words(`约 ${count} 拉丁字母词/分钟`, `about ${count} Latin-script words/min`));
    }
    return rates.join(words("、", ", "));
  }
  if (entry.kind === "gaze") {
    const head = "head_turn_change_per_second" in metrics;
    const iris = "iris_change_per_second" in metrics;
    if (head && iris) return words("头部朝向和眼部位置有变化", "Head direction and eye position changed");
    return head ? words("头部朝向有变化", "Head direction changed")
      : words("眼部位置有变化", "Eye position changed");
  }
  return {
    posture: words("上半身姿态有变化", "Upper-body posture changed"),
    gesture: words("检测到手腕移动", "Wrist movement detected"),
    face: words("检测到面部动作变化", "Facial movement detected"),
  }[entry.kind];
}

function visualAvailability(task) {
  const status = task.modules?.video_evaluation?.status;
  if (status === "completed") return "";
  if (status === "pending") return words("本次未启用画面分析。", "Visual analysis was not enabled.");
  if (status === "failed") return words("本次画面分析未完成。", "Visual analysis could not finish.");
  return words("画面中没有足够清晰的可追踪特征。", "There were too few visible features to track.");
}

function visualCoverage(task) {
  const coverage = task.delivery_evidence?.visual?.coverage;
  if (!coverage) return "";
  const parts = [
    ["upper_body", words("上半身", "upper body")],
    ["hands", words("手部", "hands")],
    ["face", words("人脸", "face")],
  ];
  const values = parts.map(([key, label]) => `${label} ${Math.round((coverage[key] || 0) * 100)}%`);
  return `${words("抽样检测覆盖率", "Detection coverage in sampled frames")} · ${values.join(" / ")}`;
}

function renderDelivery(task) {
  const container = $("evaluation-modules");
  const player = $("result-video");
  container.replaceChildren();
  player.hidden = !videoUrl;
  if (videoUrl && player.getAttribute("src") !== videoUrl) player.src = videoUrl;
  if (!videoUrl) player.removeAttribute("src");

  const timeline = task.delivery_report?.timeline || [];
  const card = document.createElement("article");
  card.className = "module-card delivery-report-card";
  const heading = document.createElement("h3");
  heading.textContent = words("视频内容报告", "Video report");
  const description = document.createElement("p");
  description.textContent = visualAvailability(task) || (timeline.length
    ? words("按原视频时间排列，动作旁标出当时说到的词句。",
      "Observations are in playback order, with the words spoken at each moment.")
    : words("本次没有检出可列出的动作或声音变化。", "There were no detectable changes to list."));
  card.append(heading, description);
  const coverage = visualCoverage(task);
  if (coverage) {
    const note = document.createElement("p");
    note.textContent = coverage;
    card.append(note);
  }
  if (!videoUrl && timeline.length) {
    const hint = document.createElement("p");
    hint.textContent = words("原视频未保存在此页面，可按下列时间在原片中回看。",
      "The original video is unavailable here. Use the times below to find each moment in your recording.");
    card.append(hint);
  }
  const list = document.createElement("ol");
  list.className = "delivery-feedback";
  for (const entry of timeline) {
    const row = document.createElement("li");
    const range = `${preciseTime(entry.start)}–${preciseTime(entry.end)}`;
    const title = document.createElement("strong");
    title.textContent = describeMoment(entry);
    const time = videoUrl ? reviewAt(entry.start, words(`回看 ${range}`, `Review ${range}`), range)
      : document.createElement("time");
    if (!videoUrl) time.textContent = range;
    row.append(time, title);
    for (const excerpt of entry.speech) {
      const quote = document.createElement("p");
      quote.lang = task.result.language || task.language;
      const speechTime = `${preciseTime(excerpt.start)}–${preciseTime(excerpt.end)}`;
      const source = excerpt.precision === "segment"
        ? words("相关分段", "Overlapping segment") : words("同期原话", "Spoken at this time");
      quote.textContent = `${source} ${speechTime} · ${excerpt.text}`;
      row.append(quote);
    }
    list.append(row);
  }
  if (timeline.length) card.append(list);
  container.append(card);
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
function reportMarkdown(task) {
  const title = task.term.title[task.language];
  const duration = task.result.duration;
  const lines = [
    `# ${words("视频内容报告", "Video report")} · ${title}`,
    "",
    duration == null ? "" : `${words("音轨时长", "Audio duration")} ${preciseTime(duration)}`,
    visualAvailability(task),
    visualCoverage(task),
    words("下列时间以原视频开头为零点。转写和动作时间为估算。",
      "Times are relative to the start of the video. Speech and movement timings are estimates."),
    "",
    `## ${words("时间线", "Timeline")}`,
    "",
  ];
  for (const entry of task.delivery_report?.timeline || []) {
    lines.push(`- **${preciseTime(entry.start)}–${preciseTime(entry.end)}** ${describeMoment(entry)}`);
    for (const excerpt of entry.speech) {
      const source = excerpt.precision === "segment" ? words("相关分段", "Overlapping segment") : words("同期原话", "Speech");
      lines.push(`  - ${source} ${preciseTime(excerpt.start)}–${preciseTime(excerpt.end)} · ${excerpt.text}`);
    }
  }
  lines.push("", `## ${words("完整转写", "Transcript")}`, "", task.result.text, "");
  return lines.join("\n");
}

$("download-result").addEventListener("click", () => {
  const task = currentResult;
  if (!task) return;
  const blob = new Blob([reportMarkdown(task)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ely5-${task.term.id}-${task.task_id.slice(0, 8)}.md`;
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
