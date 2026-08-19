import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Menu,
  Moon,
  Play,
  Settings2,
  Sun,
} from "lucide-react";
import ControlRail from "./components/ControlRail";
import HeartVisualizer from "./components/HeartVisualizer";
import ProgressPanel from "./components/ProgressPanel";
import ReportEditor from "./components/ReportEditor";
import ResultsWorkspace from "./components/ResultsWorkspace";
import { useProgress } from "./hooks/useProgress";
import { api, apiStream } from "./lib/api";
import {
  buildCatalog,
  chooseQuant,
  defaultSelection,
  groupModels,
  modelTag,
} from "./lib/models";

const EMPTY_MODEL = {
  catalog: {},
  groups: { current: [], legacy: [] },
  base: "",
  quant: "",
};

const PART_LABELS = {
  AO: "主動脈",
  PA: "肺動脈",
  LA: "左心房",
  RA: "右心房",
  LV: "左心室",
  RV: "右心室",
  MV: "二尖瓣",
  TV: "三尖瓣",
};

const CONDITION_LABELS = {
  dilatation: "擴大",
  hypertrophy: "肥厚",
  stenosis: "狹窄",
  regurgitation: "逆流",
  pressure_elevation: "壓力升高",
  dysfunction: "功能異常",
  hypokinesia: "運動減弱",
  aneurysm: "動脈瘤",
};

function initialTheme() {
  const saved = localStorage.getItem("theme");
  if (saved === "dark" || saved === "light") return saved;
  return "dark";
}

function initialVizMode() {
  return localStorage.getItem("cardiollm_viz_mode") === "ai" ? "ai" : "anatomy";
}

function createModelEntry(names, defaults, kind) {
  const filtered = names.filter((name) => name.toLowerCase().includes(kind));
  const catalog = buildCatalog(filtered.length ? filtered : names);
  const bases = Object.keys(catalog).sort();
  const selection = defaultSelection(defaults, catalog);
  return {
    catalog,
    groups: groupModels(bases, kind === "translator" ? "translator" : "summarizer"),
    ...selection,
  };
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const [railOpen, setRailOpen] = useState(false);
  const [vizMode, setVizMode] = useState(initialVizMode);
  const [source, setSource] = useState("");
  const [translation, setTranslation] = useState("");
  const [summary, setSummary] = useState("");
  const [structured, setStructured] = useState(null);
  const [structuredStatus, setStructuredStatus] = useState("等待解析");
  const [warningTranslation, setWarningTranslation] = useState("");
  const [warningSummary, setWarningSummary] = useState("");
  const [activeResultTab, setActiveResultTab] = useState("translation");
  const [waitingForResults, setWaitingForResults] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [warming, setWarming] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [modelLoadError, setModelLoadError] = useState("");
  const [modelState, setModelState] = useState({
    translator: EMPTY_MODEL,
    summarizer: EMPTY_MODEL,
  });
  const [params, setParams] = useState({
    maxT: 2048,
    tempT: 0.1,
    maxS: 2048,
    tempS: 0,
    topP: 0.95,
  });
  const [imageState, setImageState] = useState({
    url: "",
    status: "等待分析結果",
    prompt: "",
  });
  const progress = useProgress();
  const progressPanelRef = useRef(null);

  const modelBusy = analyzing || warming;
  const selectedTranslator = useMemo(
    () =>
      modelTag(
        modelState.translator.catalog,
        modelState.translator.base,
        modelState.translator.quant,
      ),
    [modelState.translator],
  );
  const selectedSummarizer = useMemo(
    () =>
      modelTag(
        modelState.summarizer.catalog,
        modelState.summarizer.base,
        modelState.summarizer.quant,
      ),
    [modelState.summarizer],
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("cardiollm_viz_mode", vizMode);
  }, [vizMode]);

  useEffect(() => {
    let active = true;
    api("/models")
      .then((data) => {
        if (!active) return;
        const names = [...(data.names || [])].sort();
        setModelState({
          translator: createModelEntry(
            names,
            data.defaults?.translator,
            "translator",
          ),
          summarizer: createModelEntry(
            names,
            data.defaults?.summarizer,
            "summarizer",
          ),
        });
      })
      .catch((error) => {
        if (active) setModelLoadError(error.message || "無法取得模型清單");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!progress.visible || !progressPanelRef.current) return;
    const mobile = window.matchMedia("(max-width: 760px)").matches;
    if (!mobile) return;
    const timer = window.setTimeout(() => {
      progressPanelRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 180);
    return () => window.clearTimeout(timer);
  }, [progress.visible]);

  const updateModelState = (next) => {
    const normalized = { ...next };
    ["translator", "summarizer"].forEach((kind) => {
      const entry = normalized[kind].catalog[normalized[kind].base];
      normalized[kind] = {
        ...normalized[kind],
        quant: chooseQuant(entry, normalized[kind].quant || "q8"),
      };
    });
    setModelState(normalized);
  };

  const clearOutputs = () => {
    progress.reset();
    setTranslation("");
    setSummary("");
    setStructured(null);
    setStructuredStatus("等待解析");
    setWarningTranslation("");
    setWarningSummary("");
    setWaitingForResults(false);
    setImageState({ url: "", status: "等待分析結果", prompt: "" });
  };

  const clearAll = () => {
    setSource("");
    clearOutputs();
  };

  const warmupModels = async () => {
    if (!selectedTranslator || !selectedSummarizer) {
      window.alert("模型清單尚未載入完成");
      return;
    }
    setRailOpen(false);
    setWarming(true);
    progress.start("warmup", "準備預熱模型");
    progress.update(6, "準備預熱模型", true);
    try {
      await apiStream(
        "/models/warmup_stream",
        {
          translator_model: selectedTranslator,
          summarizer_model: selectedSummarizer,
        },
        (event) => {
          if (["phase_start", "status", "done"].includes(event.event)) {
            progress.update(
              event.progress || 0,
              event.label || "模型預熱中",
              event.event !== "status",
            );
          }
        },
      );
      progress.finish(() => setWarming(false));
    } catch (error) {
      progress.fail(error.message || "模型預熱失敗");
      setWarming(false);
    }
  };

  const analyze = async () => {
    const report = source.trim();
    if (!report) {
      window.alert("請先輸入報告內容");
      return;
    }
    if (!selectedTranslator || !selectedSummarizer) {
      window.alert("模型清單尚未載入完成");
      return;
    }

    setRailOpen(false);
    setAnalyzing(true);
    setTranslation("");
    setSummary("");
    setStructured(null);
    setStructuredStatus("等待解析");
    setWarningTranslation("");
    setWarningSummary("");
    setWaitingForResults(true);
    setImageState({ url: "", status: "等待分析結果", prompt: "" });
    setActiveResultTab("translation");
    progress.start("inference", "準備推論");

    let streamedTranslation = "";
    let streamedSummary = "";
    let finalStructured = null;

    try {
      await apiStream(
        "/pipeline_stream",
        {
          source: report,
          translator_model: selectedTranslator,
          summarizer_model: selectedSummarizer,
          style: "Clinical",
          max_new_tokens_translate: params.maxT,
          temperature_translate: params.tempT,
          max_new_tokens_summary: params.maxS,
          temperature_summary: params.tempS,
          top_p: params.topP,
          glossary: [],
        },
        (event) => {
          if (event.event === "phase_start") {
            progress.update(event.progress || 0, event.label, true);
            if (event.phase === "translate") {
              streamedTranslation = "";
              setTranslation("");
            }
            if (event.phase === "summary") {
              streamedSummary = "";
              setSummary("");
            }
            if (event.phase === "extract_json") setStructuredStatus("解析中");
            return;
          }

          if (event.event === "token") {
            setWaitingForResults(false);
            progress.tick(event.phase);
            if (event.phase === "translate") {
              streamedTranslation += event.delta || "";
              setTranslation(streamedTranslation);
            }
            if (event.phase === "summary") {
              streamedSummary += event.delta || "";
              setSummary(streamedSummary);
            }
            return;
          }

          if (event.event === "status") {
            progress.update(event.progress || 0, event.label, false);
            return;
          }

          if (event.event === "phase_done") {
            setWaitingForResults(false);
            progress.update(event.progress || 0, event.label, true);
            if (event.phase === "translate") {
              streamedTranslation = event.text || streamedTranslation;
              setTranslation(streamedTranslation);
              if (event.warn_missing?.length) {
                setWarningTranslation(`缺漏：${event.warn_missing.join("、")}`);
              }
            }
            if (event.phase === "summary") {
              streamedSummary = event.text || streamedSummary;
              setSummary(streamedSummary);
              if (event.warn_missing?.length) {
                setWarningSummary(`缺漏：${event.warn_missing.join("、")}`);
              }
            }
            if (event.phase === "extract_json") {
              finalStructured = event.structured || null;
              setStructured(finalStructured);
              setStructuredStatus(event.warning ? "備援解析" : "解析完成");
              setImageState((current) => ({
                ...current,
                status: finalStructured ? "可產生示意圖" : "無可產生部位",
              }));
            }
            return;
          }

          if (event.event === "done") {
            if (event.structured && !finalStructured) {
              finalStructured = event.structured;
              setStructured(finalStructured);
              setStructuredStatus("解析完成");
              setImageState((current) => ({ ...current, status: "可產生示意圖" }));
            }
            if (event.warn_translation_missing?.length) {
              setWarningTranslation(
                `缺漏：${event.warn_translation_missing.join("、")}`,
              );
            }
            if (event.warn_summary_missing?.length) {
              setWarningSummary(`缺漏：${event.warn_summary_missing.join("、")}`);
            }
          }
        },
      );

      progress.finish(() => {
        setAnalyzing(false);
        setWaitingForResults(false);
      });
    } catch (error) {
      progress.fail("串流推論失敗，請檢查模型服務");
      setTranslation(`錯誤：${error.message}`);
      setSummary("");
      setStructuredStatus("解析失敗");
      setWaitingForResults(false);
      setAnalyzing(false);
    }
  };

  const requestImage = async (payload) => {
    setVizMode("ai");
    setGenerating(true);
    setImageState((current) => ({ ...current, status: "產生中", prompt: "" }));
    try {
      const result = await api("/image/generate", payload);
      setImageState({
        url: result.image_url ? `${result.image_url}?t=${Date.now()}` : "",
        status: result.image_url
          ? result.region_label
            ? `${result.region_label}完成`
            : "生成完成"
          : "無可產生部位",
        prompt: result.prompt || result.error || "",
      });
    } catch (error) {
      setImageState({
        url: "",
        status: "生成失敗",
        prompt: error.message || String(error),
      });
    } finally {
      setGenerating(false);
    }
  };

  const generateImage = () => {
    if (!structured) return;
    requestImage({ structured, summary, source });
  };

  const generateTestImage = (part, condition, severity) => {
    const partName = PART_LABELS[part] || part;
    const conditionName = CONDITION_LABELS[condition] || condition;
    const testSummary = `測試：${partName}${conditionName}`;
    const testStructured = {
      version: "1.0",
      findings: [
        {
          part,
          part_name: partName,
          condition,
          severity,
          status: "present",
          evidence: testSummary,
          confidence: 1,
          visual_action: "highlight",
        },
      ],
      measurements: [],
      overall: { summary: testSummary, has_abnormality: true },
    };
    requestImage({
      structured: testStructured,
      summary: testSummary,
      source: testSummary,
    });
  };

  const logout = async () => {
    await api("/logout", {});
    try {
      sessionStorage.setItem("cardiollm_force_login_top", "1");
      if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    } catch {
      // Storage may be unavailable in strict privacy mode.
    }
    window.scrollTo(0, 0);
    window.location.replace("/");
  };

  return (
    <div className="app-shell">
      <ControlRail
        open={railOpen}
        onClose={() => setRailOpen(false)}
        theme={theme}
        onToggleTheme={() => setTheme((value) => (value === "dark" ? "light" : "dark"))}
        modelState={modelState}
        onModelStateChange={updateModelState}
        params={params}
        onParamsChange={setParams}
        busy={modelBusy}
        onWarmup={warmupModels}
        onAnalyze={analyze}
        onClear={clearAll}
        onLogout={logout}
      />

      <main className="workspace">
        <header className="workspace-topbar">
          <button
            type="button"
            className="icon-button mobile-only"
            onClick={() => setRailOpen(true)}
            title="開啟模型控制台"
          >
            <Menu size={19} />
          </button>
          <div className="mobile-brand mobile-only">
            <Activity size={18} />
            <strong>CardioLLM</strong>
          </div>
          <div className="topbar-context">
            <span>Taichung Veterans General Hospital</span>
            <strong>心臟超音波報告分析工作台</strong>
          </div>
          <div className="topbar-actions">
            <span className="session-status">
              <span className={modelBusy ? "is-busy" : ""} />
              {modelBusy ? "處理中" : "連線正常"}
            </span>
            <button
              type="button"
              className="icon-button mobile-only"
              onClick={() => setTheme((value) => (value === "dark" ? "light" : "dark"))}
              title="切換主題"
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </header>

        {!!modelLoadError && (
          <div className="system-alert">
            <Settings2 size={16} />
            {modelLoadError}
          </div>
        )}

        <section className="primary-grid">
          <ReportEditor
            source={source}
            onSourceChange={setSource}
            onClear={() => setSource("")}
            disabled={analyzing}
          />
          <HeartVisualizer
            theme={theme}
            mode={vizMode}
            onModeChange={setVizMode}
            structured={structured}
            imageState={imageState}
            generating={generating}
            onGenerate={generateImage}
            onGenerateTest={generateTestImage}
          />
        </section>

        <ProgressPanel progress={progress} panelRef={progressPanelRef} />

        <ResultsWorkspace
          translation={translation}
          summary={summary}
          structured={structured}
          structuredStatus={structuredStatus}
          warningTranslation={warningTranslation}
          warningSummary={warningSummary}
          activeTab={activeResultTab}
          onTabChange={setActiveResultTab}
          waiting={waitingForResults}
        />
      </main>

      <div className="mobile-action-bar mobile-only">
        <button
          type="button"
          className="icon-button"
          onClick={() => setRailOpen(true)}
          disabled={modelBusy}
          title="模型與參數"
        >
          <Settings2 size={18} />
        </button>
        <button type="button" className="button primary" onClick={analyze} disabled={modelBusy}>
          <Play size={17} fill="currentColor" />
          {analyzing ? "分析中" : warming ? "預熱中" : "開始分析"}
        </button>
      </div>
    </div>
  );
}
