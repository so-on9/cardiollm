import {
  Activity,
  ChevronDown,
  Flame,
  LogOut,
  Moon,
  Play,
  RotateCcw,
  SlidersHorizontal,
  Sun,
  X,
} from "lucide-react";
import { displayModelName, QUANT_ORDER } from "../lib/models";

function ModelSelect({
  label,
  kind,
  catalog,
  groups,
  base,
  quant,
  onBaseChange,
  onQuantChange,
  disabled,
}) {
  const entry = catalog[base];
  return (
    <div className="control-block">
      <label className="field-label" htmlFor={`${kind}-model`}>
        {label}
      </label>
      <div className="select-wrap">
        <select
          id={`${kind}-model`}
          value={base}
          onChange={(event) => onBaseChange(event.target.value)}
          disabled={disabled}
        >
          {!!groups.current.length && (
            <optgroup label="目前模型">
              {groups.current.map((model) => (
                <option key={model} value={model}>
                  {displayModelName(model)}
                </option>
              ))}
            </optgroup>
          )}
          {!!groups.legacy.length && (
            <optgroup label="舊模型">
              {groups.legacy.map((model) => (
                <option key={model} value={model}>
                  {displayModelName(model)}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <ChevronDown size={15} aria-hidden="true" />
      </div>
      <div className="segmented quant-segmented" aria-label={`${label}量化選項`}>
        {QUANT_ORDER.map((option) => {
          const available = Boolean(entry?.quants?.[option]);
          return (
            <button
              key={option}
              type="button"
              className={quant === option ? "is-active" : ""}
              onClick={() => onQuantChange(option)}
              disabled={disabled || !available}
              title={available ? `使用 ${option.toUpperCase()}` : `${option.toUpperCase()} 版本不存在`}
            >
              {option.toUpperCase()}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function NumberField({ label, value, step = 1, min, max, onChange, disabled }) {
  return (
    <label className="number-field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

export default function ControlRail({
  open,
  onClose,
  theme,
  onToggleTheme,
  modelState,
  onModelStateChange,
  params,
  onParamsChange,
  busy,
  onWarmup,
  onAnalyze,
  onClear,
  onLogout,
}) {
  const changeModel = (kind, key, value) => {
    onModelStateChange({
      ...modelState,
      [kind]: { ...modelState[kind], [key]: value },
    });
  };
  const changeParam = (key, value) => onParamsChange({ ...params, [key]: value });

  return (
    <>
      <button
        type="button"
        className={`drawer-scrim ${open ? "is-visible" : ""}`}
        aria-label="關閉模型控制台"
        onClick={onClose}
      />
      <aside className={`control-rail ${open ? "is-open" : ""}`} aria-label="模型控制台">
        <div className="rail-heading">
          <div className="brand-mark" aria-hidden="true">
            <Activity size={20} strokeWidth={2.2} />
          </div>
          <div className="brand-copy">
            <strong>CardioLLM</strong>
            <span>Echo intelligence console</span>
          </div>
          <button type="button" className="icon-button mobile-only" onClick={onClose} title="關閉">
            <X size={18} />
          </button>
        </div>

        <div className="rail-status">
          <span className={`status-dot ${busy ? "is-busy" : ""}`} />
          <span>{busy ? "模型工作中" : "系統待命"}</span>
          <button
            type="button"
            className="icon-button theme-button"
            onClick={onToggleTheme}
            title={theme === "dark" ? "切換淺色模式" : "切換深色模式"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>

        <div className="rail-scroll">
          <section className="rail-section">
            <div className="section-kicker">Model routing</div>
            <ModelSelect
              label="翻譯模型"
              kind="translator"
              {...modelState.translator}
              onBaseChange={(value) => changeModel("translator", "base", value)}
              onQuantChange={(value) => changeModel("translator", "quant", value)}
              disabled={busy}
            />
            <ModelSelect
              label="摘要模型"
              kind="summarizer"
              {...modelState.summarizer}
              onBaseChange={(value) => changeModel("summarizer", "base", value)}
              onQuantChange={(value) => changeModel("summarizer", "quant", value)}
              disabled={busy}
            />
          </section>

          <details className="advanced-settings">
            <summary>
              <span>
                <SlidersHorizontal size={15} />
                推論參數
              </span>
              <ChevronDown size={15} />
            </summary>
            <div className="settings-grid">
              <NumberField
                label="翻譯 Tokens"
                value={params.maxT}
                min={1}
                max={4096}
                onChange={(value) => changeParam("maxT", value)}
                disabled={busy}
              />
              <NumberField
                label="翻譯 Temp"
                value={params.tempT}
                min={0}
                max={1.5}
                step={0.1}
                onChange={(value) => changeParam("tempT", value)}
                disabled={busy}
              />
              <NumberField
                label="摘要 Tokens"
                value={params.maxS}
                min={1}
                max={4096}
                onChange={(value) => changeParam("maxS", value)}
                disabled={busy}
              />
              <NumberField
                label="摘要 Temp"
                value={params.tempS}
                min={0}
                max={1.5}
                step={0.1}
                onChange={(value) => changeParam("tempS", value)}
                disabled={busy}
              />
              <NumberField
                label="Top P"
                value={params.topP}
                min={0.1}
                max={1}
                step={0.05}
                onChange={(value) => changeParam("topP", value)}
                disabled={busy}
              />
            </div>
          </details>
        </div>

        <div className="rail-actions">
          <button type="button" className="button secondary" onClick={onWarmup} disabled={busy}>
            <Flame size={17} />
            預熱模型
          </button>
          <button type="button" className="button primary" onClick={onAnalyze} disabled={busy}>
            <Play size={17} fill="currentColor" />
            {busy ? "分析進行中" : "開始分析"}
          </button>
          <div className="rail-action-row">
            <button type="button" className="button quiet" onClick={onClear} disabled={busy}>
              <RotateCcw size={16} />
              清除
            </button>
            <button type="button" className="button quiet danger" onClick={onLogout} disabled={busy}>
              <LogOut size={16} />
              登出
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
