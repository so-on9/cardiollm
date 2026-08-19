import { Activity, CheckCircle2, Flame } from "lucide-react";

export default function ProgressPanel({ progress, panelRef }) {
  if (!progress.visible) return null;
  const Icon = progress.error
    ? Activity
    : progress.value >= 100
      ? CheckCircle2
      : progress.mode === "warmup"
        ? Flame
        : Activity;

  return (
    <section
      ref={panelRef}
      className={`progress-panel ${progress.closing ? "is-closing" : ""} ${progress.error ? "is-error" : ""}`}
      aria-live="polite"
    >
      <div className="progress-orbit" aria-hidden="true">
        <Icon size={18} />
      </div>
      <div className="progress-copy">
        <div className="progress-eyebrow">
          {progress.mode === "warmup" ? "Model warmup" : "Inference sequence"}
        </div>
        <div className="progress-status-window">
          <span key={progress.statusKey}>{progress.status}</span>
        </div>
      </div>
      <div className="progress-meter">
        <div className="progress-value">{progress.value}%</div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progress.value}%` }} />
        </div>
      </div>
    </section>
  );
}
