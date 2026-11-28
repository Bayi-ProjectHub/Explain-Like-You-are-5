const byId = (id) => document.getElementById(id);
const fileInput = byId("file");
const choose = byId("choose");
const retry = byId("retry");
const video = byId("video");
const previewEmpty = byId("preview-empty");
const previewNote = byId("preview-note");
const status = byId("status");
const error = byId("error");
const result = byId("result");
const download = byId("download");
const coverageList = byId("coverage");
const eventList = byId("events");

const coverageLabels = {
  face: "人脸",
  face_actions: "面部动作",
  iris: "虹膜",
  upper_body: "上半身",
  hands: "手部",
  wrists: "手腕",
  torso_lean: "身体侧倾",
};
const eventLabels = {
  gaze: "头眼朝向",
  posture: "身体姿态",
  gesture: "手部动作",
  face: "面部动作",
};
const percentage = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("zh-CN");
let selectedFile;
let previewUrl;
let resultUrl;

function timeLabel(seconds) {
  const centiseconds = Math.round(seconds * 100);
  const minutes = Math.floor(centiseconds / 6000);
  const remainder = ((centiseconds % 6000) / 100).toFixed(2).padStart(5, "0");
  return `${minutes}:${remainder}`;
}

function setPreview(file) {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  video.hidden = true;
  previewEmpty.hidden = false;
  previewNote.textContent = "正在加载预览…";
  video.src = previewUrl;
}

function previewReady(canPlay) {
  video.hidden = !canPlay;
  previewEmpty.hidden = canPlay;
  if (!canPlay) previewNote.textContent = "浏览器无法预览这个文件。";
  for (const button of eventList.querySelectorAll("button")) button.disabled = !canPlay;
}

function showCoverage(data) {
  const rows = [];
  for (const [key, label] of Object.entries(coverageLabels)) {
    const value = data[key];
    if (typeof value !== "number") continue;
    const row = document.createElement("li");
    const name = document.createElement("span");
    const meter = document.createElement("meter");
    const text = document.createElement("span");
    name.textContent = label;
    meter.max = 1;
    meter.value = value;
    meter.setAttribute("aria-label", label);
    text.textContent = percentage.format(value);
    text.setAttribute("aria-hidden", "true");
    row.append(name, meter, text);
    rows.push(row);
  }
  coverageList.replaceChildren(...rows);
}

function showEvents(events, offset) {
  const sorted = [...events].sort((a, b) => a.start - b.start);
  const rows = sorted.map((event) => {
    const row = document.createElement("li");
    const label = document.createElement("span");
    const button = document.createElement("button");
    const start = Math.max(0, event.start + offset);
    const end = Math.max(start, event.end + offset);
    label.textContent = eventLabels[event.kind] ?? event.kind;
    button.type = "button";
    button.className = "event-time";
    button.textContent = `${timeLabel(start)}–${timeLabel(end)}`;
    button.setAttribute("aria-label", `跳到 ${timeLabel(start)} 的${label.textContent}`);
    button.disabled = video.hidden || video.readyState < 1;
    button.addEventListener("click", () => { video.currentTime = start; });
    row.append(label, button);
    return row;
  });
  eventList.replaceChildren(...rows);
  byId("event-empty").hidden = rows.length > 0;
}

function showResult(data) {
  byId("frames").textContent = integer.format(data.sampled_frames);
  byId("event-count").textContent = integer.format(data.events.length);
  byId("observations").hidden = data.sampled_frames === 0;
  showCoverage(data.coverage);
  showEvents(data.events, data.video_offset_seconds);
  resultUrl = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  download.href = resultUrl;
  download.hidden = false;
  result.hidden = false;
  status.textContent = data.sampled_frames ? "分析完成。" : "分析完成，没有采到可用的画面。";
}

async function analyze(file) {
  choose.disabled = true;
  retry.hidden = true;
  error.hidden = true;
  result.hidden = true;
  eventList.replaceChildren();
  download.hidden = true;
  download.removeAttribute("href");
  if (resultUrl) URL.revokeObjectURL(resultUrl);
  resultUrl = undefined;
  status.textContent = "正在上传并分析视频，请稍等…";
  result.setAttribute("aria-busy", "true");

  try {
    const form = new FormData();
    form.set("file", file);
    const response = await fetch("/video/analyses", { method: "POST", body: form });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      throw new Error(typeof data?.detail === "string" ? data.detail : "分析请求失败，请重试。");
    }
    showResult(data);
  } catch (failure) {
    status.textContent = "";
    error.hidden = false;
    error.textContent = failure instanceof TypeError ? "无法连接到分析服务，请检查服务是否已启动。" : failure.message;
    retry.hidden = false;
  } finally {
    choose.disabled = false;
    result.setAttribute("aria-busy", "false");
  }
}

choose.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (!fileInput.files.length) return;
  selectedFile = fileInput.files[0];
  fileInput.value = "";
  byId("file-name").textContent = selectedFile.name;
  setPreview(selectedFile);
  void analyze(selectedFile);
});
retry.addEventListener("click", () => { if (selectedFile) void analyze(selectedFile); });
video.addEventListener("loadedmetadata", () => previewReady(true));
video.addEventListener("error", () => previewReady(false));
