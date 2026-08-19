export const HEART_PARTS = [
  { id: "ao", code: "AO", label: "主動脈" },
  { id: "pa", code: "PA", label: "肺動脈" },
  { id: "la", code: "LA", label: "左心房" },
  { id: "ra", code: "RA", label: "右心房" },
  { id: "lv", code: "LV", label: "左心室" },
  { id: "rv", code: "RV", label: "右心室" },
];

export const DEFAULT_ANCHORS = {
  ao: { x: 628.16, y: 70.45 },
  pa: { x: 686.42, y: 155 },
  la: { x: 709.97, y: 228.58 },
  ra: { x: 257.55, y: 320.95 },
  lv: { x: 745.92, y: 385.14 },
  rv: { x: 429.84, y: 583.98 },
};

export const ANCHOR_STORAGE_KEY = "heart_anchors_v3";

const CONDITION_LABELS = {
  dilatation: "擴大",
  hypertrophy: "肥厚",
  stenosis: "狹窄",
  regurgitation: "逆流",
  dysfunction: "功能異常",
  pressure_elevation: "壓力升高",
  aneurysm: "動脈瘤",
  hypokinesia: "運動減弱",
  normal: "正常",
  other: "其他",
};

const SEVERITY_LABELS = {
  trace: "極輕度",
  mild: "輕度",
  moderate: "中度",
  severe: "重度",
  unknown: "",
};

export function heartFindings(structured) {
  const findings = Array.isArray(structured?.findings) ? structured.findings : [];
  return findings.reduce((result, finding) => {
    if (!finding || finding.status === "absent") return result;
    const code = String(finding.part || "").toUpperCase();
    const part = HEART_PARTS.find((item) => item.code === code);
    if (!part) return result;
    const severity = SEVERITY_LABELS[finding.severity] || "";
    const condition = CONDITION_LABELS[finding.condition] || finding.condition || "有提及";
    const label = [severity, condition].filter(Boolean).join(" ");
    if (!result[part.id]) result[part.id] = [];
    if (label && !result[part.id].includes(label)) result[part.id].push(label);
    return result;
  }, {});
}

export function loadAnchors() {
  try {
    const value = JSON.parse(localStorage.getItem(ANCHOR_STORAGE_KEY));
    return { ...structuredClone(DEFAULT_ANCHORS), ...(value || {}) };
  } catch {
    return structuredClone(DEFAULT_ANCHORS);
  }
}
