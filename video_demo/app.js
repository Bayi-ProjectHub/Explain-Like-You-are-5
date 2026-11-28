import { initResults } from "./results.js";

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
const results = initResults(video);
let selectedFile;
let previewUrl;
let resultUrl;

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
  results.setPreview(canPlay);
}

function showResult(data) {
  results.render(data);
  resultUrl = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  download.href = resultUrl;
  download.hidden = false;
  status.textContent = data.sampled_frames ? "分析完成。" : "分析完成，没有采到可用的画面。";
}

async function analyze(file) {
  choose.disabled = true;
  retry.hidden = true;
  error.hidden = true;
  results.clear();
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
