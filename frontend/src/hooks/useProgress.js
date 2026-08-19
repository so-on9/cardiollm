import { useCallback, useEffect, useRef, useState } from "react";

const STATUS_COOLDOWN = 700;

function statusFor(value, mode) {
  if (mode === "warmup") {
    if (value < 16) return "檢查目前載入模型";
    if (value < 34) return "卸載舊模型";
    if (value < 92) return "載入目前選取模型";
    return "模型預熱完成";
  }
  if (value < 14) return "送出報告與模型設定";
  if (value < 42) return "翻譯模型推論中";
  if (value < 86) return "摘要模型推論中";
  if (value < 99) return "結構化 JSON 解析中";
  return "完成，正在顯示結果";
}

export function useProgress() {
  const [state, setState] = useState({
    visible: false,
    closing: false,
    error: false,
    value: 0,
    status: "準備推論",
    statusKey: 0,
    mode: "inference",
  });
  const stateRef = useRef(state);
  const tickTimer = useRef(null);
  const closeTimer = useRef(null);
  const statusTimer = useRef(null);
  const statusUpdatedAt = useRef(0);
  const pendingStatus = useRef("");

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const stopTick = useCallback(() => {
    if (tickTimer.current) window.clearInterval(tickTimer.current);
    tickTimer.current = null;
  }, []);

  const clearTimers = useCallback(() => {
    stopTick();
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    if (statusTimer.current) window.clearTimeout(statusTimer.current);
    closeTimer.current = null;
    statusTimer.current = null;
    pendingStatus.current = "";
  }, [stopTick]);

  useEffect(() => clearTimers, [clearTimers]);

  const commitStatus = useCallback((text) => {
    if (!text) return;
    statusUpdatedAt.current = Date.now();
    setState((current) =>
      current.status === text
        ? current
        : { ...current, status: text, statusKey: current.statusKey + 1 },
    );
  }, []);

  const setStatus = useCallback(
    (text, force = false) => {
      if (!text) return;
      const elapsed = Date.now() - statusUpdatedAt.current;
      if (force || elapsed >= STATUS_COOLDOWN) {
        if (statusTimer.current) window.clearTimeout(statusTimer.current);
        statusTimer.current = null;
        pendingStatus.current = "";
        commitStatus(text);
        return;
      }

      pendingStatus.current = text;
      if (statusTimer.current) return;
      statusTimer.current = window.setTimeout(() => {
        statusTimer.current = null;
        const pending = pendingStatus.current;
        pendingStatus.current = "";
        commitStatus(pending);
      }, STATUS_COOLDOWN - elapsed);
    },
    [commitStatus],
  );

  const update = useCallback(
    (value, label, forceStatus = false) => {
      const next = Math.max(0, Math.min(100, Math.round(value)));
      setState((current) => ({
        ...current,
        value: Math.max(current.value, next),
      }));
      setStatus(label || statusFor(next, stateRef.current.mode), forceStatus);
      if (next >= 92) stopTick();
    },
    [setStatus, stopTick],
  );

  const start = useCallback(
    (mode = "inference", initialStatus = "準備推論") => {
      clearTimers();
      statusUpdatedAt.current = Date.now();
      setState({
        visible: true,
        closing: false,
        error: false,
        value: 3,
        status: initialStatus,
        statusKey: Date.now(),
        mode,
      });

      tickTimer.current = window.setInterval(() => {
        const current = stateRef.current;
        if (!current.visible || current.value >= 92) return;
        const gap = 92 - current.value;
        const pace = current.value < 35 ? 3.2 : current.value < 70 ? 1.8 : 0.75;
        const next = current.value + Math.max(0.2, Math.min(pace, gap * 0.18));
        update(next);
      }, 520);
    },
    [clearTimers, update],
  );

  const tick = useCallback(
    (phase) => {
      const current = stateRef.current.value;
      const ceiling = phase === "translate" ? 46 : 86;
      const floor = phase === "translate" ? 8 : 54;
      const bump = phase === "translate" ? 0.45 : 0.32;
      update(Math.min(ceiling, Math.max(current, floor) + bump));
    },
    [update],
  );

  const finish = useCallback(
    (done) => {
      stopTick();
      update(100, "完成，正在顯示結果", true);
      closeTimer.current = window.setTimeout(() => {
        setState((current) => ({ ...current, closing: true }));
        closeTimer.current = window.setTimeout(() => {
          setState((current) => ({ ...current, visible: false, closing: false }));
          done?.();
        }, 420);
      }, 520);
    },
    [stopTick, update],
  );

  const fail = useCallback(
    (message) => {
      stopTick();
      setState((current) => ({ ...current, visible: true, closing: false, error: true }));
      update(100, message || "推論失敗", true);
    },
    [stopTick, update],
  );

  const reset = useCallback(() => {
    clearTimers();
    setState({
      visible: false,
      closing: false,
      error: false,
      value: 0,
      status: "準備推論",
      statusKey: Date.now(),
      mode: "inference",
    });
  }, [clearTimers]);

  return { ...state, start, update, tick, finish, fail, reset };
}
