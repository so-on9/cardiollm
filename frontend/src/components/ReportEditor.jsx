import { FileText, Trash2 } from "lucide-react";

export default function ReportEditor({ source, onSourceChange, onClear, disabled }) {
  const lineCount = source ? source.split(/\r?\n/).length : 0;
  const charCount = source.length;

  return (
    <section className="report-panel">
      <header className="report-heading">
        <div>
          <span className="section-kicker">Source report</span>
          <h1>原始報告輸入</h1>
        </div>
        <FileText size={19} aria-hidden="true" />
      </header>
      <textarea
        value={source}
        onChange={(event) => onSourceChange(event.target.value)}
        placeholder="請貼上心臟超音波報告全文..."
        spellCheck="false"
        disabled={disabled}
      />
      <footer className="report-footer">
        <span>{lineCount || 0} 行</span>
        <span>{charCount} 字元</span>
        <button
          type="button"
          className="icon-button"
          onClick={onClear}
          disabled={disabled || !source}
          title="清除報告"
        >
          <Trash2 size={16} />
        </button>
      </footer>
    </section>
  );
}
