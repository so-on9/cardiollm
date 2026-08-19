import { Braces, ClipboardCheck, Languages, TriangleAlert } from "lucide-react";

const TABS = [
  { id: "translation", label: "翻譯", icon: Languages },
  { id: "summary", label: "摘要", icon: ClipboardCheck },
  { id: "json", label: "JSON", icon: Braces },
];

function ResultPanel({ title, eyebrow, text, warning, icon: Icon, className = "" }) {
  return (
    <article className={`result-panel ${className}`}>
      <header className="result-header">
        <div>
          <span>{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        <Icon size={19} aria-hidden="true" />
      </header>
      <div className={`result-content ${text ? "" : "is-empty"}`}>
        {text || "分析完成後，內容會顯示在這裡。"}
      </div>
      {!!warning && (
        <div className="result-warning">
          <TriangleAlert size={15} />
          <span>{warning}</span>
        </div>
      )}
    </article>
  );
}

export default function ResultsWorkspace({
  translation,
  summary,
  structured,
  structuredStatus,
  warningTranslation,
  warningSummary,
  activeTab,
  onTabChange,
  waiting,
}) {
  return (
    <section className={`results-workspace ${waiting ? "is-waiting" : ""}`}>
      <div className="results-heading">
        <div>
          <span className="section-kicker">Clinical output</span>
          <h1>分析結果</h1>
        </div>
        <div className="result-state">
          <span className={translation || summary ? "is-ready" : ""} />
          {translation || summary ? "已有分析內容" : "等待報告"}
        </div>
      </div>

      <div className="result-tabs" role="tablist" aria-label="分析結果">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            className={activeTab === id ? "is-active" : ""}
            onClick={() => onTabChange(id)}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      <div className="result-grid">
        <ResultPanel
          title="翻譯結果"
          eyebrow="Translation"
          text={translation}
          warning={warningTranslation}
          icon={Languages}
          className={activeTab === "translation" ? "mobile-active" : ""}
        />
        <ResultPanel
          title="臨床摘要"
          eyebrow="Clinical summary"
          text={summary}
          warning={warningSummary}
          icon={ClipboardCheck}
          className={activeTab === "summary" ? "mobile-active" : ""}
        />
        <details
          className={`structured-panel ${activeTab === "json" ? "mobile-active" : ""}`}
          open={activeTab === "json" || undefined}
        >
          <summary>
            <div>
              <span>Structured findings</span>
              <strong>結構化 JSON</strong>
            </div>
            <span className="json-status">{structuredStatus}</span>
          </summary>
          <pre>{structured ? JSON.stringify(structured, null, 2) : "等待解析"}</pre>
        </details>
      </div>
    </section>
  );
}
