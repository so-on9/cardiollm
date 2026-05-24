const KEY = "supersecret";
const HEART_IMG_LIGHT = "/static/Heart_diagram_nobg.png";
const HEART_IMG_DARK_CANDIDATES = [
    "/static/Heart_diagram_nobg_dark.png",
    "/static/Heart_diagram_nobg_dark.webp",
    "/static/Heart_diagram_nobg_dark.jpg",
    "/static/Heart_diagram_nobg_dark.jpeg",
    HEART_IMG_LIGHT,
];

/* ==============================
 * 0) 圖片/座標：固定 viewBox 比例 (1000 x 533.854)
 *    + 校準模式 (點一下就記住位置)
 * ============================== */
const VB_W = 1000;
const VB_H_BASE = 533.854;

// 20260119跟 CSS 的 --pad-ratio 一樣
const PAD_RATIO = 0.22;

// 20260119變成「圖片高度 + 留白高度」
const VB_H = +(VB_H_BASE * (1 + PAD_RATIO)).toFixed(3);

const ANCHOR_KEY = "heart_anchors_v2";

/** 預設座標（只是初值，之後你用校準模式點黑字會覆蓋） */
const DEFAULT_ANCHORS = {
    ao: { x: 637.16, y: 27.06 },
    pa: { x: 702.56, y: 105.53 },
    la: { x: 739.93, y: 178.41 },
    ra: { x: 203.68, y: 269.96 },
    lv: { x: 781.03, y: 327.89 },
    rv: { x: 418.55, y: 514.74 },
};

function loadAnchors() {
    try {
        const raw = localStorage.getItem(ANCHOR_KEY);
        if (!raw) return structuredClone(DEFAULT_ANCHORS);
        const obj = JSON.parse(raw);
        // 補缺項
        return { ...structuredClone(DEFAULT_ANCHORS), ...(obj || {}) };
    } catch (e) {
        return structuredClone(DEFAULT_ANCHORS);
    }
}
function saveAnchors(a) {
    localStorage.setItem(ANCHOR_KEY, JSON.stringify(a));
}

let anchors = loadAnchors();

function applyAnchor(id) {
    const g = document.getElementById("label-" + id);
    if (!g || !anchors[id]) return;
    g.setAttribute("transform", `translate(${anchors[id].x},${anchors[id].y})`);
}
function applyAllAnchors() {
    ["ao", "pa", "la", "ra", "lv", "rv"].forEach(applyAnchor);
}

/* 校準模式：點圖設定座標 */
let calibOn = false;

function setCalibUI() {
    const stack = document.getElementById("heartStack");
    const btn = document.getElementById("btnCalib");
    stack.classList.toggle("calib-on", calibOn);
    btn.textContent = calibOn ? "校準模式：開" : "校準模式：關";
}

document.addEventListener("DOMContentLoaded", () => {
    applyAllAnchors();

    document.getElementById("btnCalib").onclick = () => {
        calibOn = !calibOn;
        setCalibUI();
    };

    document.getElementById("btnResetAnchors").onclick = () => {
        anchors = structuredClone(DEFAULT_ANCHORS);
        saveAnchors(anchors);
        applyAllAnchors();
        alert("已重置為預設座標（你可再開啟校準模式重新點選）");
    };

    document.getElementById("heartStack").addEventListener("click", (ev) => {
        if (!calibOn) return;

        const stack = document.getElementById("heartStack");
        const rect = stack.getBoundingClientRect();  // ✅ 用整個 stack（含留白）

        const x = (ev.clientX - rect.left) / rect.width * VB_W;
        const y = (ev.clientY - rect.top) / rect.height * VB_H;

        const id = document.getElementById("calibTarget").value;
        anchors[id] = { x: +x.toFixed(2), y: +y.toFixed(2) };
        saveAnchors(anchors);
        applyAnchor(id);

        document.getElementById("calibHint").textContent =
            `已設定 ${id.toUpperCase()} 座標：(${anchors[id].x}, ${anchors[id].y})`;
    });



    setCalibUI();
});

/* ---------------------------------------------------
 * 1. 關鍵字 → 心臟區域 map
 *   - 同時支援英文縮寫、英文全名、中文名稱
 *   - 把常見寫法像 "LA("、"LA:" 也加進來
 * --------------------------------------------------*/
const MAP = {
    ao: {
        k: [
            "aorta", "aortic", "root", "av ", "ar ",
            " ao ", " ao(", "ao(", "ao:", "主動脈"
        ],
        name: "AO"
    },
    la: {
        k: [
            "left atrium", "left atrial",
            " la ", " la(", "la(", "la:",
            "左心房"
        ],
        name: "LA"
    },
    lv: {
        k: [
            "left ventricle", "left ventricular",
            " lv ", " lv(", "lv(", "lv:",
            "lvef", "lvh", "concentric lvh",
            "左心室"
        ],
        name: "LV"
    },
    ra: {
        k: [
            "right atrium", "right atrial",
            " ra ", " ra(", "ra(", "ra:",
            "右心房"
        ],
        name: "RA"
    },
    rv: {
        k: [
            "right ventricle", "right ventricular",
            " rv ", " rv(", "rv(", "rv:",
            "右心室"
        ],
        name: "RV"
    },
    pa: {
        k: [
            "pulmonary artery", "pulmonary trunk",
            " pa ", " pa(", "pa(", "pa:",
            "肺動脈"
        ],
        name: "PA"
    }
};

/* ---------------------------------------------------
 * 2. 病變關鍵字 (中英混搭)
 * --------------------------------------------------*/
const CONDS = [
    { k: "dilat", label: "擴大 (Dilatation)" },
    { k: "enlarg", label: "擴大 (Enlarged)" },
    { k: "hypertroph", label: "肥厚 (Hypertrophy)" },
    { k: "thick", label: "壁厚增加 (Thickened)" },
    { k: "stenosis", label: "狹窄 (Stenosis)" },
    { k: "regurgitation", label: "逆流 (Regurgitation)" },
    { k: "regurgitant", label: "逆流 (Regurgitation)" },
    { k: "abnormal", label: "異常 (Abnormal)" },
    { k: "dysfunction", label: "功能異常 (Dysfunction)" },
    { k: "hypokine", label: "運動減弱 (Hypokinesia)" },
    { k: "akine", label: "運動缺失 (Akinesia)" },
    { k: "aneurysm", label: "動脈瘤 (Aneurysm)" },
    { k: "severe", label: "重度 (Severe)" },
    { k: "moderate", label: "中度 (Moderate)" },
    { k: "mild", label: "輕度 (Mild)" },
    { k: "pressure", label: "壓力升高" },
    { k: "elevat", label: "壓力升高" },       // elevated / elevation
    { k: "hypertension", label: "壓力升高" },
    { k: "pulmonary hypertension", label: "壓力升高" },


    // 中文關鍵字
    { k: "擴大", label: "擴大" },
    { k: "肥厚", label: "肥厚" },
    { k: "壁厚增加", label: "壁厚增加" },
    { k: "狹窄", label: "狹窄" },
    { k: "逆流", label: "逆流" },
    { k: "功能異常", label: "功能異常" },
    { k: "收縮功能不全", label: "收縮功能不全" },
    { k: "舒張功能不全", label: "舒張功能不全" },
    { k: "高壓", label: "壓力升高" }
];

/* ---------------------------------------------------
 * 3. 依翻譯 + 摘要文字啟動標註
 * --------------------------------------------------*/
function highlight(text) {
    if (!text) return;

    const low = text.toLowerCase();
    const sentences = low.split(/[。！？\.\n]/);

    // 先清掉之前的 active & 說明文字
    document.querySelectorAll('.callout-group').forEach(g => {
        g.classList.remove('active');
    });
    ["ao", "la", "lv", "ra", "rv", "pa"].forEach(id => {
        const desc = document.getElementById("desc-" + id);
        if (desc) {
            desc.textContent = "--";
            desc.style.fill = "#000";
        }
    });

    // 改：每個區域可以累積多個狀況
    const status = {}; // id -> { hit: true, descs: Set() }

    sentences.forEach(sent => {
        const s = sent.trim();
        if (!s) return;

        for (let id in MAP) {
            const keys = MAP[id].k;

            if (keys.some(k => s.includes(k))) {
                if (!status[id]) status[id] = { hit: true, descs: new Set() };

                // 改：不要 break，全部掃完把符合的都加進去
                for (let c of CONDS) {
                    if (s.includes(c.k)) {
                        status[id].descs.add(c.label);
                    }
                }
            }
        }
    });

    for (let id in status) {
        if (!status[id].hit) continue;

        const g = document.getElementById("label-" + id);
        if (g) g.classList.add("active");

        const d = document.getElementById("desc-" + id);
        if (!d) continue;

        const arr = Array.from(status[id].descs).filter(Boolean);

        if (arr.length) {
            d.textContent = arr.slice(0, 2).join("、");
            d.style.fill = "var(--danger)";
        } else {
            d.textContent = "有提及";
            d.style.fill = "#000";
        }
    }
}


/* ---------------------------------------------------
 * 4. API 小工具
 * --------------------------------------------------*/
async function api(path, body) {
    const r = await fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: { 'x-api-key': KEY, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : null
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return await r.json();
}

async function apiStream(path, body, onEvent) {
    const r = await fetch(path, {
        method: 'POST',
        headers: { 'x-api-key': KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!r.ok) {
        let message = r.statusText;
        try {
            const data = await r.json();
            message = data.detail || message;
        } catch (e) {
            message = await r.text() || message;
        }
        throw new Error(message);
    }
    if (!r.body) throw new Error('此瀏覽器不支援串流回應');

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
            const raw = line.trim();
            if (!raw) continue;
            const event = JSON.parse(raw);
            onEvent(event);
            if (event.event === 'error') throw new Error(event.message || 'stream error');
        }
    }

    buffer += decoder.decode();
    const raw = buffer.trim();
    if (raw) {
        const event = JSON.parse(raw);
        onEvent(event);
        if (event.event === 'error') throw new Error(event.message || 'stream error');
    }
}

/* ---------------------------------------------------
 * 5. 初始化模型清單
 * --------------------------------------------------*/
const QUANT_ORDER = ["q4", "q5", "q8"];
const QUANT_LABELS = { q4: "Q4", q5: "Q5", q8: "Q8" };
const modelPickerState = {
    translator: { catalog: {}, selectedQuant: "" },
    summarizer: { catalog: {}, selectedQuant: "" },
};

function splitModelTag(name) {
    const idx = name.lastIndexOf(":");
    if (idx < 0) return { base: name, quant: "", full: name };
    return {
        base: name.slice(0, idx),
        quant: name.slice(idx + 1).toLowerCase(),
        full: name,
    };
}

function buildCatalog(names) {
    const catalog = {};
    names.forEach((name) => {
        const { base, quant, full } = splitModelTag(name);
        if (!catalog[base]) catalog[base] = { base, quants: {}, fallback: full };
        if (quant) catalog[base].quants[quant] = full;
        else catalog[base].fallback = full;
    });
    return catalog;
}

function addDisabledLabel(selectEl, label) {
    const opt = new Option(label, "");
    opt.disabled = true;
    opt.className = "option-group-label";
    selectEl.add(opt);
}

function addBaseModels(selectEl, bases) {
    bases.forEach((base) => selectEl.add(new Option(displayModelName(base), base)));
}

function displayModelName(base) {
    return base
        .replace(/^llama-3\.2-3b-instruct-/, "llama3.2-3b-")
        .replace("-translator-baseline150", "-trans-baseline150")
        .replace("-summarizer-clinical-v4", "-sum-clinical-v4")
        .replace("-translator", "-trans")
        .replace("-summarizer", "-sum");
}

function firstEnabledValue(selectEl) {
    return [...selectEl.options].find((opt) => !opt.disabled && opt.value)?.value || "";
}

function chooseQuant(entry, preferred = "") {
    const available = entry ? entry.quants : {};
    if (preferred && available[preferred]) return preferred;
    return QUANT_ORDER.find((q) => available[q]) || "";
}

function defaultBaseAndQuant(defaultName, catalog) {
    if (!defaultName) return { base: "", quant: "" };
    const parsed = splitModelTag(defaultName);
    if (catalog[parsed.base]) return { base: parsed.base, quant: parsed.quant };
    if (catalog[defaultName]) return { base: defaultName, quant: "" };
    return { base: "", quant: "" };
}

function renderQuantButtons(kind, preferredQuant = "") {
    const state = modelPickerState[kind];
    const selectId = kind === "translator" ? "transModel" : "sumModel";
    const quantId = kind === "translator" ? "transQuant" : "sumQuant";
    const selectEl = document.getElementById(selectId);
    const quantEl = document.getElementById(quantId);
    const entry = state.catalog[selectEl.value];
    const selected = chooseQuant(entry, preferredQuant || state.selectedQuant);

    state.selectedQuant = selected;
    quantEl.innerHTML = "";

    QUANT_ORDER.forEach((q) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "quant-pill";
        btn.textContent = QUANT_LABELS[q];
        btn.disabled = !entry || !entry.quants[q];
        btn.title = btn.disabled ? `${QUANT_LABELS[q]} 版本目前不存在` : `使用 ${QUANT_LABELS[q]}`;
        if (q === selected) btn.classList.add("is-active");
        btn.onclick = () => {
            if (btn.disabled) return;
            state.selectedQuant = q;
            renderQuantButtons(kind, q);
        };
        quantEl.appendChild(btn);
    });
}

function selectedModelTag(kind) {
    const state = modelPickerState[kind];
    const selectId = kind === "translator" ? "transModel" : "sumModel";
    const selectEl = document.getElementById(selectId);
    const entry = state.catalog[selectEl.value];
    if (!entry) return selectEl.value;
    const quant = chooseQuant(entry, state.selectedQuant);
    return entry.quants[quant] || entry.fallback || selectEl.value;
}

async function init() {
    try {
        const data = await api('/models');
        const all = (data.names || []).sort();
        const tSel = document.getElementById('transModel');
        const sSel = document.getElementById('sumModel');

        const tModels = all.filter(n => n.toLowerCase().includes('translator'));
        const sModels = all.filter(n => n.toLowerCase().includes('summarizer'));

        tSel.innerHTML = ''; sSel.innerHTML = '';

        const translatorModels = tModels.length ? tModels : all;
        modelPickerState.translator.catalog = buildCatalog(translatorModels);
        const translatorBases = Object.keys(modelPickerState.translator.catalog).sort();
        const newTranslatorModels = translatorBases.filter(
            n => n.toLowerCase().includes('translator-baseline150')
        );
        const oldTranslatorModels = translatorBases.filter(
            n => !n.toLowerCase().includes('translator-baseline150')
        );

        if (newTranslatorModels.length) {
            addDisabledLabel(tSel, '新模型');
            addBaseModels(tSel, newTranslatorModels);
        }
        if (oldTranslatorModels.length) {
            addDisabledLabel(tSel, '舊模型');
            addBaseModels(tSel, oldTranslatorModels);
        }

        const summarizerModels = sModels.length ? sModels : all;
        modelPickerState.summarizer.catalog = buildCatalog(summarizerModels);
        const summarizerBases = Object.keys(modelPickerState.summarizer.catalog).sort();
        const newSummarizerModels = summarizerBases.filter(
            n => n.toLowerCase().includes('summarizer-clinical-v4')
        );
        const oldSummarizerModels = summarizerBases.filter(
            n => !n.toLowerCase().includes('summarizer-clinical-v4')
        );

        if (newSummarizerModels.length) {
            addDisabledLabel(sSel, '新模型');
            addBaseModels(sSel, newSummarizerModels);
        }
        if (oldSummarizerModels.length) {
            addDisabledLabel(sSel, '舊模型');
            addBaseModels(sSel, oldSummarizerModels);
        }

        const tDefault = defaultBaseAndQuant(data.defaults?.translator, modelPickerState.translator.catalog);
        const sDefault = defaultBaseAndQuant(data.defaults?.summarizer, modelPickerState.summarizer.catalog);

        tSel.value = tDefault.base || firstEnabledValue(tSel);
        sSel.value = sDefault.base || firstEnabledValue(sSel);

        renderQuantButtons("translator", tDefault.quant || "q8");
        renderQuantButtons("summarizer", "q5");

        tSel.onchange = () => renderQuantButtons("translator", "q8");
        sSel.onchange = () => renderQuantButtons("summarizer", "q5");
    } catch (e) { }
}

/* ---------------------------------------------------
 * 6. 深淺色主題
 * --------------------------------------------------*/
const themeBtn = document.getElementById('themeToggle');
let heartThemeToken = 0;

function loadImageCandidate(img, candidates, token, idx = 0) {
    if (!img || token !== heartThemeToken) return;
    const src = candidates[idx];
    if (!src) {
        img.src = HEART_IMG_LIGHT;
        return;
    }

    const probe = new Image();
    probe.onload = () => {
        if (token !== heartThemeToken) return;
        img.src = src;
    };
    probe.onerror = () => {
        if (token !== heartThemeToken) return;
        loadImageCandidate(img, candidates, token, idx + 1);
    };
    probe.src = src;
}

function applyThemeHeartImage(theme) {
    const heartImg = document.getElementById('heartImg');
    if (!heartImg) return;
    heartThemeToken += 1;
    const token = heartThemeToken;
    if (theme === 'dark') {
        loadImageCandidate(heartImg, HEART_IMG_DARK_CANDIDATES, token);
    } else {
        heartImg.src = HEART_IMG_LIGHT;
    }
}

function initTheme() {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
    themeBtn.textContent = theme === 'dark' ? '☀' : '☾';
    applyThemeHeartImage(theme);
}
themeBtn.onclick = () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    themeBtn.textContent = next === 'dark' ? '☀' : '☾';
    applyThemeHeartImage(next);
};

/* ---------------------------------------------------
 * 7. 打字機效果 + highlight
 * --------------------------------------------------*/
function typeShow(el, text, done) {
    el.textContent = '';
    if (!text) { if (done) done(); return; }
    let i = 0;
    function loop() {
        el.textContent += text.slice(i, i + 5);
        if (i % 50 === 0) highlight(el.textContent);
        i += 5;
        if (i < text.length) setTimeout(loop, 10);
        else { highlight(text); if (done) done(); }
    }
    loop();
}

let progressTimer = null;
let progressValue = 0;
let progressStatusText = "準備推論";
let progressStatusUpdatedAt = 0;
let progressStatusAnimating = false;
let progressStatusPending = "";
const PROGRESS_STATUS_COOLDOWN_MS = 900;

function progressStatusFor(value) {
    if (value < 14) return "送出報告與模型設定";
    if (value < 42) return "翻譯模型推論中";
    if (value < 72) return "摘要模型推論中";
    if (value < 99) return "整理輸出與一致性檢查";
    return "完成，正在顯示結果";
}

function progressStatusEl(statusEl) {
    if (!statusEl) return null;
    statusEl.childNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) node.remove();
    });
    let textEl = statusEl.querySelector('#progressStatusText');
    if (!textEl) {
        statusEl.innerHTML = '';
        textEl = document.createElement('span');
        textEl.id = 'progressStatusText';
        textEl.className = 'progress-status-text';
        statusEl.appendChild(textEl);
    }
    return textEl;
}

function setProgressStatusText(statusEl, text, immediate = false) {
    const textEl = progressStatusEl(statusEl);
    if (!textEl || !text || textEl.textContent === text) return;

    if (immediate) {
        progressStatusAnimating = false;
        progressStatusPending = '';
        textEl.classList.remove('is-leaving', 'is-entering');
        textEl.textContent = text;
        return;
    }

    if (progressStatusAnimating) {
        progressStatusPending = text;
        return;
    }

    progressStatusAnimating = true;
    textEl.classList.remove('is-entering');
    textEl.classList.add('is-leaving');

    window.setTimeout(() => {
        textEl.textContent = text;
        textEl.classList.remove('is-leaving');
        textEl.classList.add('is-entering');

        requestAnimationFrame(() => {
            textEl.classList.remove('is-entering');
        });

        window.setTimeout(() => {
            progressStatusAnimating = false;
            const pending = progressStatusPending;
            progressStatusPending = '';
            if (pending && pending !== textEl.textContent) {
                setProgressStatusText(statusEl, pending);
            }
        }, 280);
    }, 140);
}

function setProgress(value, status, forceStatus = false) {
    const fill = document.getElementById('progressFill');
    const percent = document.getElementById('progressPercent');
    const statusEl = document.getElementById('progressStatus');
    const next = Math.max(0, Math.min(100, Math.round(value)));
    const nextStatus = status || progressStatusFor(next);
    const now = Date.now();
    if (fill) fill.style.width = `${next}%`;
    if (percent) percent.textContent = `${next}%`;
    if (
        statusEl
        && nextStatus
        && (forceStatus || !progressStatusText || now - progressStatusUpdatedAt >= PROGRESS_STATUS_COOLDOWN_MS)
    ) {
        progressStatusText = nextStatus;
        progressStatusUpdatedAt = now;
        setProgressStatusText(statusEl, nextStatus, forceStatus);
    }
}

function stopProgressTimer() {
    if (!progressTimer) return;
    clearInterval(progressTimer);
    progressTimer = null;
}

function openProgressPanel(panel) {
    if (!panel) return;
    panel.hidden = false;
    panel.classList.remove('is-closing');
    requestAnimationFrame(() => {
        panel.classList.add('is-open');
    });
}

function closeProgressPanel(panel, done) {
    if (!panel) {
        if (done) done();
        return;
    }
    panel.classList.remove('is-open');
    panel.classList.add('is-closing');
    window.setTimeout(() => {
        panel.hidden = true;
        panel.classList.remove('is-closing');
        if (done) done();
    }, 480);
}

function centerProgressPanel(panel) {
    if (!panel || !panel.scrollIntoView) return;
    window.setTimeout(() => {
        panel.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
    }, 180);
}

function startProgress() {
    const panel = document.getElementById('progressPanel');
    const resultsGrid = document.getElementById('resultsGrid');
    stopProgressTimer();
    progressValue = 3;
    progressStatusText = "";
    progressStatusUpdatedAt = 0;
    progressStatusAnimating = false;
    progressStatusPending = "";
    if (panel) {
        panel.classList.remove('is-error');
        openProgressPanel(panel);
        centerProgressPanel(panel);
    }
    if (resultsGrid) resultsGrid.classList.add('is-waiting');
    setProgress(progressValue, "準備推論", true);

    progressTimer = setInterval(() => {
        const ceiling = 92;
        if (progressValue >= ceiling) {
            setProgress(progressValue);
            return;
        }
        const gap = ceiling - progressValue;
        const pace = progressValue < 35 ? 3.2 : progressValue < 70 ? 1.8 : 0.75;
        const nextValue = progressValue + Math.max(0.2, Math.min(pace, gap * 0.18));
        progressValue = Math.max(progressValue, Math.min(ceiling, nextValue));
        setProgress(progressValue);
    }, 520);
}

function finishProgress(done) {
    const panel = document.getElementById('progressPanel');
    const resultsGrid = document.getElementById('resultsGrid');
    stopProgressTimer();
    progressValue = 100;
    setProgress(100, "完成，正在顯示結果", true);
    setTimeout(() => {
        if (resultsGrid) resultsGrid.classList.remove('is-waiting');
        closeProgressPanel(panel, done);
    }, 300);
}

function failProgress(message) {
    const panel = document.getElementById('progressPanel');
    const resultsGrid = document.getElementById('resultsGrid');
    stopProgressTimer();
    if (panel) {
        panel.classList.add('is-error');
        openProgressPanel(panel);
    }
    if (resultsGrid) resultsGrid.classList.remove('is-waiting');
    setProgress(100, message || "推論失敗", true);
}

function resetProgress() {
    const panel = document.getElementById('progressPanel');
    const resultsGrid = document.getElementById('resultsGrid');
    stopProgressTimer();
    progressValue = 0;
    progressStatusText = "";
    progressStatusUpdatedAt = 0;
    progressStatusAnimating = false;
    progressStatusPending = "";
    setProgress(0, "準備推論", true);
    if (panel) {
        panel.hidden = true;
        panel.classList.remove('is-error', 'is-open', 'is-closing');
    }
    if (resultsGrid) resultsGrid.classList.remove('is-waiting');
}

function showStreamingResults() {
    const resultsGrid = document.getElementById('resultsGrid');
    if (resultsGrid) resultsGrid.classList.remove('is-waiting');
}

function setStreamingPhaseProgress(progress, label) {
    progressValue = Math.max(progressValue, progress || 0);
    if (progressValue >= 92) stopProgressTimer();
    setProgress(progressValue, label, true);
}

function tickStreamingProgress(phase) {
    const ceiling = phase === 'translate' ? 50 : 93;
    const bump = phase === 'translate' ? 0.45 : 0.32;
    progressValue = Math.min(ceiling, Math.max(progressValue, phase === 'translate' ? 8 : 58) + bump);
    setProgress(progressValue);
}

/* ---------------------------------------------------
 * 8. Pipeline 按鈕
 * --------------------------------------------------*/
document.getElementById('btn-pipeline').onclick = async () => {
    const src = document.getElementById('src').value.trim();
    if (!src) return alert('請輸入報告內容');

    const btn = document.getElementById('btn-pipeline');
    const elT = document.getElementById('trans');
    const elS = document.getElementById('sum');
    const warnT = document.getElementById('warnT');
    const warnS = document.getElementById('warnS');
    elT.textContent = '';
    elS.textContent = '';
    warnT.textContent = '';
    warnS.textContent = '';
    document.querySelectorAll('.callout-group').forEach(g => g.classList.remove('active'));
    btn.disabled = true;
    btn.textContent = '推論中';
    startProgress();

    let translation = '';
    let summary = '';

    try {
        await apiStream('/pipeline_stream', {
            source: src,
            translator_model: selectedModelTag("translator"),
            summarizer_model: selectedModelTag("summarizer"),
            style: document.getElementById('style').value,
            max_new_tokens_translate: +document.getElementById('maxT').value,
            temperature_translate: +document.getElementById('tempT').value,
            max_new_tokens_summary: +document.getElementById('maxS').value,
            temperature_summary: +document.getElementById('tempS').value,
            top_p: +document.getElementById('topP').value,
            glossary: []
        }, (event) => {
            if (event.event === 'phase_start') {
                setStreamingPhaseProgress(event.progress || 0, event.label);
                if (event.phase === 'translate') {
                    translation = '';
                    elT.textContent = '';
                }
                if (event.phase === 'summary') {
                    summary = '';
                    elS.textContent = '';
                }
                return;
            }

            if (event.event === 'token') {
                showStreamingResults();
                tickStreamingProgress(event.phase);
                if (event.phase === 'translate') {
                    translation += event.delta || '';
                    elT.textContent = translation;
                }
                if (event.phase === 'summary') {
                    summary += event.delta || '';
                    elS.textContent = summary;
                }
                highlight(`${translation}
${summary}`);
                return;
            }

            if (event.event === 'status') {
                setStreamingPhaseProgress(event.progress || progressValue, event.label);
                return;
            }

            if (event.event === 'phase_done') {
                showStreamingResults();
                setStreamingPhaseProgress(event.progress || progressValue, event.label);
                if (event.phase === 'translate') {
                    translation = event.text || translation;
                    elT.textContent = translation;
                    if (event.warn_missing?.length) warnT.textContent = '⚠️ 缺漏: ' + event.warn_missing;
                }
                if (event.phase === 'summary') {
                    summary = event.text || summary;
                    elS.textContent = summary;
                    if (event.warn_missing?.length) warnS.textContent = '⚠️ 缺漏: ' + event.warn_missing;
                }
                highlight(`${translation}
${summary}`);
                return;
            }

            if (event.event === 'done') {
                if (event.warn_translation_missing?.length)
                    warnT.textContent = '⚠️ 缺漏: ' + event.warn_translation_missing;
                if (event.warn_summary_missing?.length)
                    warnS.textContent = '⚠️ 缺漏: ' + event.warn_summary_missing;
            }
        });

        finishProgress(() => {
            highlight(`${translation}
${summary}`);
            btn.disabled = false;
            btn.textContent = '開始分析';
        });
    } catch (e) {
        failProgress("串流推論失敗，請檢查模型服務");
        elT.textContent = '錯誤: ' + e.message;
        elS.textContent = '';
        btn.disabled = false;
        btn.textContent = '開始分析';
    }
};
/* ---------------------------------------------------
 * 9. 其他按鈕
 * --------------------------------------------------*/
document.getElementById('btn-clear').onclick = () => {
    resetProgress();
    document.getElementById('src').value = '';
    document.getElementById('trans').textContent = '';
    document.getElementById('sum').textContent = '';
    document.querySelectorAll('.callout-group').forEach(g => g.classList.remove('active'));

    // 清掉一致性檢測警告
    document.getElementById('warnT').textContent = '';
    document.getElementById('warnS').textContent = '';
};
document.getElementById('logout').onclick = async () => {
    await api('/logout', {});
    location.reload();
};

init();
initTheme();
