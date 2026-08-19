import { useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Crosshair,
  ImagePlus,
  RefreshCw,
  ScanLine,
  Sparkles,
} from "lucide-react";
import {
  ANCHOR_STORAGE_KEY,
  DEFAULT_ANCHORS,
  HEART_PARTS,
  heartFindings,
  loadAnchors,
} from "../lib/heart";

const AI_PARTS = [
  ["AO", "AO 主動脈"],
  ["PA", "PA 肺動脈"],
  ["LA", "LA 左心房"],
  ["RA", "RA 右心房"],
  ["LV", "LV 左心室"],
  ["RV", "RV 右心室"],
  ["MV", "MV 二尖瓣"],
  ["TV", "TV 三尖瓣"],
];

const AI_CONDITIONS = [
  ["dilatation", "擴大"],
  ["hypertrophy", "肥厚"],
  ["stenosis", "狹窄"],
  ["regurgitation", "逆流"],
  ["pressure_elevation", "壓力升高"],
  ["dysfunction", "功能異常"],
  ["hypokinesia", "運動減弱"],
  ["aneurysm", "動脈瘤"],
];

const AI_SEVERITIES = [
  ["mild", "輕度"],
  ["moderate", "中度"],
  ["severe", "重度"],
];

function AnatomyView({ theme, structured }) {
  const [anchors, setAnchors] = useState(loadAnchors);
  const [calibration, setCalibration] = useState(false);
  const [target, setTarget] = useState("ao");
  const [hint, setHint] = useState("點擊圖面即可重新定位標記");
  const stageRef = useRef(null);
  const findings = useMemo(() => heartFindings(structured), [structured]);

  const imagePath =
    theme === "dark"
      ? "/static/Heart_diagram_nobg_dark.png"
      : "/static/Heart_diagram_nobg.png";

  const setAnchor = (event) => {
    if (!calibration || !stageRef.current) return;
    const rect = stageRef.current.getBoundingClientRect();
    const next = {
      x: Number((((event.clientX - rect.left) / rect.width) * 1000).toFixed(2)),
      y: Number((((event.clientY - rect.top) / rect.height) * 651.302).toFixed(2)),
    };
    const updated = { ...anchors, [target]: next };
    setAnchors(updated);
    localStorage.setItem(ANCHOR_STORAGE_KEY, JSON.stringify(updated));
    setHint(`${target.toUpperCase()} 已定位至 ${next.x}, ${next.y}`);
  };

  const resetAnchors = () => {
    const next = structuredClone(DEFAULT_ANCHORS);
    setAnchors(next);
    localStorage.setItem(ANCHOR_STORAGE_KEY, JSON.stringify(next));
    setHint("已恢復預設座標");
  };

  return (
    <>
      <div className="viz-tool-row">
        <div className="select-wrap compact">
          <select
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            disabled={!calibration}
            aria-label="校準部位"
          >
            {HEART_PARTS.map((part) => (
              <option key={part.id} value={part.id}>
                {part.code} {part.label}
              </option>
            ))}
          </select>
          <ChevronDown size={14} />
        </div>
        <button
          type="button"
          className={`tool-button ${calibration ? "is-active" : ""}`}
          onClick={() => setCalibration((value) => !value)}
        >
          <Crosshair size={15} />
          校準 {calibration ? "開" : "關"}
        </button>
        <button type="button" className="icon-button" onClick={resetAnchors} title="重置座標">
          <RefreshCw size={16} />
        </button>
        <span className="calibration-hint">{calibration ? hint : "標記依結構化結果顯示"}</span>
      </div>

      <div
        ref={stageRef}
        className={`heart-stage ${calibration ? "is-calibrating" : ""}`}
        onClick={setAnchor}
      >
        <div className="stage-coordinate top-left">ANTERIOR / CUTAWAY</div>
        <div className="stage-coordinate bottom-right">ECHOCARDIOGRAPHY MAP</div>
        <div className="scan-line" aria-hidden="true" />
        <img
          src={imagePath}
          className="heart-image"
          alt="心臟解剖示意圖"
          onError={(event) => {
            event.currentTarget.src = "/static/Heart_diagram_nobg.png";
          }}
        />
        <svg
          className="heart-overlay"
          viewBox="0 0 1000 651.302"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {HEART_PARTS.map((part) => {
            const labels = findings[part.id] || [];
            const active = labels.length > 0;
            const anchor = anchors[part.id] || DEFAULT_ANCHORS[part.id];
            return (
              <g
                key={part.id}
                className={`heart-callout ${active ? "is-active" : ""}`}
                transform={`translate(${anchor.x},${anchor.y})`}
              >
                <line x1="-56" y1="14" x2="56" y2="14" />
                <text x="0" y="43" textAnchor="middle">
                  {labels.slice(0, 2).join("、")}
                </text>
              </g>
            );
          })}
        </svg>
        <div className={`stage-signal ${Object.keys(findings).length ? "is-active" : ""}`}>
          <span />
          {Object.keys(findings).length ? `${Object.keys(findings).length} 處標記` : "等待結構化資料"}
        </div>
      </div>
    </>
  );
}

function AiView({
  imageState,
  canGenerate,
  onGenerate,
  onGenerateTest,
  generating,
}) {
  const [testPart, setTestPart] = useState("RA");
  const [testCondition, setTestCondition] = useState("dilatation");
  const [testSeverity, setTestSeverity] = useState("moderate");

  return (
    <div className="ai-workspace">
      <div className="ai-stage">
        <div className="stage-coordinate top-left">AI INPAINT PREVIEW</div>
        <div className="ai-status">
          <span className={generating ? "is-busy" : ""} />
          {imageState.status}
        </div>
        <img
          src={imageState.url || "/static/assets/heart_base.png"}
          className={imageState.url ? "is-generated" : ""}
          alt="AI 心臟示意圖"
        />
        {generating && (
          <div className="ai-generating" aria-live="polite">
            <Sparkles size={22} />
            <span>生成示意圖中</span>
          </div>
        )}
      </div>

      <div className="ai-actions">
        <button
          type="button"
          className="button primary compact-button"
          disabled={!canGenerate || generating}
          onClick={onGenerate}
        >
          <ImagePlus size={16} />
          產生示意圖
        </button>
      </div>

      <details className="ai-test-tools">
        <summary>
          <span>
            <ScanLine size={15} />
            繪圖測試工具
          </span>
          <ChevronDown size={15} />
        </summary>
        <div className="ai-test-grid">
          <div className="select-wrap compact">
            <select value={testPart} onChange={(event) => setTestPart(event.target.value)}>
              {AI_PARTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          <div className="select-wrap compact">
            <select
              value={testCondition}
              onChange={(event) => setTestCondition(event.target.value)}
            >
              {AI_CONDITIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          <div className="select-wrap compact">
            <select
              value={testSeverity}
              onChange={(event) => setTestSeverity(event.target.value)}
            >
              {AI_SEVERITIES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          <button
            type="button"
            className="button secondary compact-button"
            disabled={generating}
            onClick={() => onGenerateTest(testPart, testCondition, testSeverity)}
          >
            <Sparkles size={16} />
            產生測試圖
          </button>
        </div>
      </details>

      {!!imageState.prompt && <pre className="prompt-preview">{imageState.prompt}</pre>}
    </div>
  );
}

export default function HeartVisualizer({
  theme,
  mode,
  onModeChange,
  structured,
  imageState,
  generating,
  onGenerate,
  onGenerateTest,
}) {
  return (
    <section className="visualizer-panel">
      <header className="visualizer-heading">
        <div>
          <span className="section-kicker">Anatomical signal</span>
          <h1>心臟示意圖</h1>
        </div>
        <div className="segmented viz-mode" role="tablist" aria-label="圖像模式">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "anatomy"}
            className={mode === "anatomy" ? "is-active" : ""}
            onClick={() => onModeChange("anatomy")}
          >
            心臟圖
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "ai"}
            className={mode === "ai" ? "is-active" : ""}
            onClick={() => onModeChange("ai")}
          >
            AI 繪圖
          </button>
        </div>
      </header>

      {mode === "anatomy" ? (
        <AnatomyView theme={theme} structured={structured} />
      ) : (
        <AiView
          imageState={imageState}
          canGenerate={Boolean(structured)}
          generating={generating}
          onGenerate={onGenerate}
          onGenerateTest={onGenerateTest}
        />
      )}
    </section>
  );
}
