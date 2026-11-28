export const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 });
export const integer = new Intl.NumberFormat("zh-CN");
export const percentage = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 1 });

export const eventLabels = {
  gaze: "头眼朝向",
  posture: "身体姿态",
  gesture: "手部动作",
  face: "面部动作",
};

const metrics = {
  face_turn_offset: ["头部朝向偏移", ""],
  torso_lean_degrees: ["躯干侧倾", "°"],
  gesture_bursts: ["手腕快速移动次数", " 次"],
  wrist_range_shoulder_widths: ["手腕移动范围", " 个肩宽"],
  wrist_speed_shoulder_widths_per_second: ["手腕平均移动速度", " 个肩宽/秒"],
  iris_change_per_second: ["虹膜位置变化速率", " /秒"],
  shoulder_motion_widths_per_second: ["肩部平均移动速度", " 个肩宽/秒"],
  face_coefficient_change_per_second: ["面部动作系数变化速率", " /秒"],
  head_turn_change_per_second: ["头部朝向变化速率", " /秒"],
};

const targets = {
  left_wrist: "左腕相对左肩",
  right_wrist: "右腕相对右肩",
  shoulder_center: "肩部中心",
  torso_lean: "躯干侧倾",
  jawOpen: "下颌开合系数",
  browInnerUp: "眉心抬升系数",
  eyeBlinkLeft: "左眼闭合系数",
  eyeBlinkRight: "右眼闭合系数",
  mouthSmileLeft: "左嘴角上扬系数",
  mouthSmileRight: "右嘴角上扬系数",
};

const directions = {
  up: "向上",
  down: "向下",
  frame_left: "向画面左侧",
  frame_right: "向画面右侧",
  increase: "增大",
  decrease: "减小",
};

const units = {
  shoulder_width: " 个肩宽",
  degree: "°",
  blendshape_coefficient: "",
};

export function metricRows(values) {
  return Object.entries(values).map(([key, value]) => {
    const [label, unit] = metrics[key] ?? [key, ""];
    return [label, number.format(value) + unit];
  });
}

export function motionDetails(motion) {
  const unit = units[motion.unit] ?? "";
  return {
    label: targets[motion.target] ?? motion.target,
    direction: directions[motion.direction] ?? "",
    rows: [
      ["起止值", `${number.format(motion.start_value)} → ${number.format(motion.end_value)}${unit}`],
      ["幅度", number.format(motion.span) + unit],
      ["峰值速度", number.format(motion.peak_speed) + unit + "/秒"],
    ],
  };
}
