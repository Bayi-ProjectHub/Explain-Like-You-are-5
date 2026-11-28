import { eventLabels, integer, metricRows, motionDetails, number, percentage } from "./metrics.js";

const byId = (id) => document.getElementById(id);
const coverageGroups = [
  ["coverage-face", { face: "人脸", face_actions: "面部动作", iris: "虹膜" }],
  ["coverage-body", { upper_body: "上半身", torso_lean: "躯干侧倾" }],
  ["coverage-hands", { hands: "手部", wrists: "手腕", left_wrist: "左腕", right_wrist: "右腕" }],
];
const sourceNames = { face_specialized: "专用人脸模型", pose_heavy: "专用姿态模型", hand: "专用手部模型" };
const pageSize = 6;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function definitionRows(rows) {
  return rows.map(([label, value]) => {
    const row = element("div", undefined, "measurement-row");
    row.append(element("dt", label), element("dd", value));
    return row;
  });
}

function timeLabel(seconds) {
  const centiseconds = Math.round(Math.max(0, seconds) * 100);
  const minutes = Math.floor(centiseconds / 6000);
  return `${minutes}:${((centiseconds % 6000) / 100).toFixed(2).padStart(5, "0")}`;
}

export function initResults(video) {
  const eventList = byId("events");
  const eventFilter = byId("event-filter");
  const windows = byId("window-select");
  const previous = byId("previous-events");
  const next = byId("next-events");
  const demoDetails = byId("analysis-details");
  const result = byId("result");
  let analysis;
  let page = 0;

  function jumpButton(start, end, label) {
    const playerTime = Math.max(0, start);
    const time = `${timeLabel(playerTime)}–${timeLabel(Math.max(playerTime, end))}`;
    const button = element("button", time, "event-time");
    button.type = "button";
    button.setAttribute("aria-label", `${time}，跳到${label}`);
    button.disabled = video.hidden || video.readyState < 1;
    button.addEventListener("click", () => {
      video.currentTime = playerTime;
      video.scrollIntoView({ block: "nearest" });
    });
    return button;
  }

  function showCoverage(data) {
    for (const [id, labels] of coverageGroups) {
      const rows = [];
      for (const [key, label] of Object.entries(labels)) {
        const value = data[key];
        if (typeof value !== "number") continue;
        const row = element("li");
        const meter = element("meter");
        meter.max = 1;
        meter.value = value;
        meter.setAttribute("aria-label", label);
        const text = element("span", percentage.format(value));
        text.setAttribute("aria-hidden", "true");
        row.append(element("span", label), meter, text);
        rows.push(row);
      }
      byId(id).replaceChildren(...rows);
    }
  }

  function eventItem(event) {
    const kind = eventLabels[event.kind] ?? event.kind;
    const row = element("li", undefined, "event-entry");
    const title = element("div", undefined, "event-heading");
    const offset = analysis.video_offset_seconds;
    title.append(element("strong", kind), jumpButton(event.start + offset, event.end + offset, kind));
    row.append(title);

    for (const measurement of event.measurements ?? []) {
      const { label, direction, rows } = motionDetails(measurement);
      const heading = [label, direction].filter(Boolean).join(" · ");
      const list = element("dl", undefined, "measurement-list");
      list.append(...definitionRows(rows));
      row.append(element("p", heading, "event-target"), list);
    }
    const measured = metricRows(event.metrics ?? {});
    if (measured.length) {
      const list = element("dl", undefined, "measurement-list");
      list.append(...definitionRows(measured));
      row.append(list);
    }
    return row;
  }

  function showEvents() {
    const kind = eventFilter.value;
    const events = kind === "all" ? analysis.events : analysis.events.filter((event) => event.kind === kind);
    const count = events.length;
    byId("event-empty").hidden = count > 0;
    byId("event-empty").textContent = kind === "all"
      ? "已分析的画面里没有检测到动作。"
      : "这个分类里没有动作记录。";
    byId("event-pages").hidden = count <= pageSize;
    const start = page * pageSize;
    eventList.replaceChildren(...events.slice(start, start + pageSize).map(eventItem));
    previous.disabled = page === 0;
    next.disabled = start + pageSize >= count;
    const first = start + 1;
    const last = Math.min(start + pageSize, count);
    const range = first === last ? first : `${first}–${last}`;
    byId("event-page-label").textContent = count ? `第 ${range} 条，共 ${count} 条` : "";
  }

  function showWindow() {
    const item = analysis.windows[Number(windows.value)];
    byId("window-time").replaceChildren();
    byId("window-metrics").replaceChildren();
    if (!item) return;
    const offset = analysis.video_offset_seconds;
    byId("window-time").append(jumpButton(item.start + offset, item.end + offset, "测量时段"));
    byId("window-metrics").append(...definitionRows(metricRows(item.metrics)));
  }

  function showTechnical() {
    const data = analysis;
    const rows = [
      ["模型", data.model === "mediapipe_holistic" ? "MediaPipe Holistic" : data.model],
      ["采样目标", `${number.format(data.sample_hz)} 帧/秒`],
      ["播放器时间偏移", `${data.video_offset_seconds} 秒`],
      ["结果格式版本", integer.format(data.schema_version)],
    ];
    for (const [source, count] of Object.entries(data.tracking_sources ?? {})) {
      rows.push([sourceNames[source] ?? source, `补充检测 ${integer.format(count)} 帧`]);
    }
    const ranges = data.selected_playback_ranges ?? [];
    if (ranges.length) {
      rows.push(["讲者出镜时段", ranges.map(({ start, end }) => `${timeLabel(start)}–${timeLabel(end)}`).join("，")]);
    }
    byId("technical-metrics").replaceChildren(...definitionRows(rows));
  }

  function render(data) {
    analysis = { ...data, events: [...data.events].sort((a, b) => a.start - b.start) };
    page = 0;
    eventFilter.value = "all";
    byId("frames").textContent = integer.format(data.sampled_frames);
    byId("event-count").textContent = integer.format(data.events.length);
    byId("window-count").textContent = integer.format(data.windows.length);
    byId("coverage").hidden = data.sampled_frames === 0;
    showCoverage(data.coverage);
    showEvents();

    const offset = data.video_offset_seconds;
    const options = data.windows.map(({ start, end }, index) => {
      const time = `${timeLabel(start + offset)}–${timeLabel(end + offset)}`;
      const option = element("option", time);
      option.value = index;
      return option;
    });
    windows.replaceChildren(...options);
    byId("window-control").hidden = options.length === 0;
    byId("window-empty").hidden = options.length > 0;
    showWindow();
    showTechnical();
    result.hidden = false;
    demoDetails.hidden = false;
  }

  eventFilter.addEventListener("change", () => { page = 0; showEvents(); });
  previous.addEventListener("click", () => { page--; showEvents(); });
  next.addEventListener("click", () => { page++; showEvents(); });
  windows.addEventListener("change", showWindow);

  return {
    render,
    clear() {
      result.hidden = true;
      demoDetails.hidden = true;
    },
    setPreview(canPlay) {
      for (const button of demoDetails.querySelectorAll(".event-time")) button.disabled = !canPlay;
    },
  };
}
