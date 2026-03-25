const KEY = "supersecret";

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

function loadAnchors(){
  try{
    const raw = localStorage.getItem(ANCHOR_KEY);
    if(!raw) return structuredClone(DEFAULT_ANCHORS);
    const obj = JSON.parse(raw);
    // 補缺項
    return { ...structuredClone(DEFAULT_ANCHORS), ...(obj||{}) };
  }catch(e){
    return structuredClone(DEFAULT_ANCHORS);
  }
}
function saveAnchors(a){
  localStorage.setItem(ANCHOR_KEY, JSON.stringify(a));
}

let anchors = loadAnchors();

function applyAnchor(id){
  const g = document.getElementById("label-" + id);
  if(!g || !anchors[id]) return;
  g.setAttribute("transform", `translate(${anchors[id].x},${anchors[id].y})`);
}
function applyAllAnchors(){
  ["ao","pa","la","ra","lv","rv"].forEach(applyAnchor);
}

/* 校準模式：點圖設定座標 */
let calibOn = false;

function setCalibUI(){
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
  if(!calibOn) return;

  const stack = document.getElementById("heartStack");
  const rect = stack.getBoundingClientRect();  // ✅ 用整個 stack（含留白）

  const x = (ev.clientX - rect.left) / rect.width  * VB_W;
  const y = (ev.clientY - rect.top)  / rect.height * VB_H;

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
  { k: "dilat",       label: "擴大 (Dilatation)" },
  { k: "enlarg",      label: "擴大 (Enlarged)" },
  { k: "hypertroph",  label: "肥厚 (Hypertrophy)" },
  { k: "thick",       label: "壁厚增加 (Thickened)" },
  { k: "stenosis",    label: "狹窄 (Stenosis)" },
  { k: "regurgitation", label: "逆流 (Regurgitation)" },
  { k: "regurgitant",   label: "逆流 (Regurgitation)" },
  { k: "abnormal",    label: "異常 (Abnormal)" },
  { k: "dysfunction", label: "功能異常 (Dysfunction)" },
  { k: "hypokine",    label: "運動減弱 (Hypokinesia)" },
  { k: "akine",       label: "運動缺失 (Akinesia)" },
  { k: "aneurysm",    label: "動脈瘤 (Aneurysm)" },
  { k: "severe",      label: "重度 (Severe)" },
  { k: "moderate",    label: "中度 (Moderate)" },
  { k: "mild",        label: "輕度 (Mild)" },
  { k: "pressure", label: "壓力升高" },
  { k: "elevat", label: "壓力升高" },       // elevated / elevation
  { k: "hypertension", label: "壓力升高" },
  { k: "pulmonary hypertension", label: "壓力升高" },


  // 中文關鍵字
  { k: "擴大",         label: "擴大" },
  { k: "肥厚",         label: "肥厚" },
  { k: "壁厚增加",     label: "壁厚增加" },
  { k: "狹窄",         label: "狹窄" },
  { k: "逆流",         label: "逆流" },
  { k: "功能異常",     label: "功能異常" },
  { k: "收縮功能不全", label: "收縮功能不全" },
  { k: "舒張功能不全", label: "舒張功能不全" },
  { k: "高壓",         label: "壓力升高" }
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
  ["ao","la","lv","ra","rv","pa"].forEach(id => {
    const desc = document.getElementById("desc-" + id);
    if (desc) {
      desc.textContent = "--";
      desc.style.fill = "#000";
    }
  });

  // ✅ 改：每個區域可以累積多個狀況
  const status = {}; // id -> { hit: true, descs: Set() }

  sentences.forEach(sent => {
    const s = sent.trim();
    if (!s) return;

    for (let id in MAP) {
      const keys = MAP[id].k;

      if (keys.some(k => s.includes(k))) {
        if (!status[id]) status[id] = { hit: true, descs: new Set() };

        // ✅ 改：不要 break，全部掃完把符合的都加進去
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
    method: body ? 'POST':'GET', 
    headers: {'x-api-key': KEY, 'Content-Type': 'application/json'},
    body: body ? JSON.stringify(body) : null
  });
  if(!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return await r.json();
}

/* ---------------------------------------------------
 * 5. 初始化模型清單
 * --------------------------------------------------*/
async function init() {
  try {
    const data = await api('/models');
    const all = (data.names || []).sort();
    const tSel = document.getElementById('transModel');
    const sSel = document.getElementById('sumModel');
    
    const tModels = all.filter(n => n.toLowerCase().includes('translator'));
    const sModels = all.filter(n => n.toLowerCase().includes('summarizer'));
    
    tSel.innerHTML=''; sSel.innerHTML='';
    (tModels.length?tModels:all).forEach(n=>tSel.add(new Option(n,n)));
    (sModels.length?sModels:all).forEach(n=>sSel.add(new Option(n,n)));

    if(data.defaults?.translator && tModels.includes(data.defaults.translator)) {
        tSel.value = data.defaults.translator;
    }
    if(data.defaults?.summarizer && sModels.includes(data.defaults.summarizer)) {
        sSel.value = data.defaults.summarizer;
    }
  } catch(e) {}
}

/* ---------------------------------------------------
 * 6. 深淺色主題
 * --------------------------------------------------*/
const themeBtn = document.getElementById('themeToggle');
function initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', theme);
  themeBtn.textContent = theme === 'dark' ? '☀' : '☾';
}
themeBtn.onclick = () => {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  themeBtn.textContent = next === 'dark' ? '☀' : '☾';
};

/* ---------------------------------------------------
 * 7. 打字機效果 + highlight
 * --------------------------------------------------*/
function typeShow(el, text, done) {
  el.textContent = ''; 
  if(!text) { if(done) done(); return; }
  let i=0;
  function loop() {
    el.textContent += text.slice(i, i+5);
    if(i % 50 === 0) highlight(el.textContent); 
    i+=5;
    if(i<text.length) setTimeout(loop, 10);
    else { highlight(text); if(done) done(); }
  }
  loop();
}

/* ---------------------------------------------------
 * 8. Pipeline 按鈕
 * --------------------------------------------------*/
document.getElementById('btn-pipeline').onclick = async () => {
  const src = document.getElementById('src').value.trim();
  if(!src) return alert('請輸入報告內容');
  
  const elT = document.getElementById('trans');
  const elS = document.getElementById('sum');
  elT.textContent = '分析中...'; elS.textContent = '等待中...';
  document.getElementById('warnT').textContent = '';
  document.getElementById('warnS').textContent = '';

  try {
    const res = await api('/pipeline', {
      source: src,
      translator_model: document.getElementById('transModel').value,
      summarizer_model: document.getElementById('sumModel').value,
      style: document.getElementById('style').value,
      max_new_tokens_translate: +document.getElementById('maxT').value,
      temperature_translate: +document.getElementById('tempT').value,
      max_new_tokens_summary: +document.getElementById('maxS').value,
      temperature_summary: +document.getElementById('tempS').value,
      top_p: +document.getElementById('topP').value,
      glossary: []
    });

    const fullText = (res.translation + "\n" + res.summary);

    typeShow(elT, res.translation, () => {
      typeShow(elS, res.summary, () => {
        highlight(fullText);
      });
    });

    if(res.warn_translation_missing?.length)
      document.getElementById('warnT').textContent = '⚠️ 缺漏: ' + res.warn_translation_missing;
    if(res.warn_summary_missing?.length)
      document.getElementById('warnS').textContent = '⚠️ 缺漏: ' + res.warn_summary_missing;

  } catch(e) {
    elT.textContent = '錯誤: ' + e.message;
  }
};

/* ---------------------------------------------------
 * 9. 其他按鈕
 * --------------------------------------------------*/
document.getElementById('btn-clear').onclick = () => {
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