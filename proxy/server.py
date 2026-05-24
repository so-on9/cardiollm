# server.py — Cardio Dual-Model (Final Fixed: Correct Coordinates)
from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os, re, requests, time, hmac, hashlib, base64, json

# -------------------------------------------------------------------------
#  Backend
# -------------------------------------------------------------------------


def strip_model_header(text: str) -> str:
    if not text:
        return text
    t = text.lstrip()
    m = re.search(r"[\u4e00-\u9fff]", t)
    if m:
        return t[m.start() :]
    return t


def dedup_summary_lines(text: str) -> str:
    seen = set()
    result_lines = []
    for line in text.splitlines():
        line_stripped = line.rstrip()
        if not line_stripped:
            result_lines.append(line)
            continue
        if line_stripped in seen:
            continue
        seen.add(line_stripped)
        result_lines.append(line)
    return "\n".join(result_lines).strip()


SUMMARY_ANATOMY_TERMS = (
    "左心房", "右心房", "左心室", "右心室",
    "主動脈根部", "升主動脈", "主動脈瓣", "主動脈",
    "肺動脈主幹", "肺動脈幹", "肺動脈瓣", "肺動脈",
    "肺循環", "右心壓力", "右心",
    "二尖瓣", "三尖瓣", "心包腔", "心包膜",
    "室間隔", "心室中隔", "心尖", "下壁", "側壁", "外側壁",
)

UNSUPPORTED_CLAIM_TERMS = (
    "正常", "無顯著", "未見", "無明顯", "沒有明顯",
    "狹窄", "肺高壓", "肺動脈高壓", "壁運動正常",
    "壓力升高", "壓力上升", "可能與",
)


def remove_extra_numbers_from_line(line: str, allowed_numbers: set[str]) -> str:
    cleaned = line
    for raw in NUM_VALUE_RE.findall(line):
        try:
            key = f"{float(raw):g}"
        except Exception:
            key = raw
        if key in allowed_numbers:
            continue
        pattern = rf"\s*[:：]?\s*{re.escape(raw)}\s*(?:cm|mm|公分|毫米|毫米汞柱|%|％)?"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[：:，,、；;]\s*$", "", cleaned).strip()
    return cleaned


def sanitize_summary_against_source(source: str, summary: str) -> str:
    if not source or not summary:
        return summary

    source_norm = source.lower()
    allowed_numbers = extract_nums_units(source)
    kept_lines: list[str] = []

    for line in summary.splitlines():
        raw = line.strip()
        if not raw:
            if kept_lines and kept_lines[-1]:
                kept_lines.append("")
            continue

        is_heading = raw.startswith("【") or bool(re.match(r"^[一二三四五六七八九十]+[、.．]", raw))
        if is_heading:
            kept_lines.append(raw)
            continue

        cleaned = remove_extra_numbers_from_line(raw, allowed_numbers)
        if not cleaned:
            continue

        cleaned_norm = cleaned.lower()
        unsupported_anatomy = [
            term for term in SUMMARY_ANATOMY_TERMS
            if term in cleaned and term not in source
        ]
        unsupported_claim = [
            term for term in UNSUPPORTED_CLAIM_TERMS
            if term in cleaned and term not in source
        ]

        if unsupported_anatomy or unsupported_claim:
            continue

        kept_lines.append(cleaned)

    # Remove headings that ended up with no content beneath them.
    compact: list[str] = []
    for idx, line in enumerate(kept_lines):
        if not line:
            continue
        is_heading = line.startswith("【") or bool(re.match(r"^[一二三四五六七八九十]+[、.．]", line))
        if is_heading:
            has_content = any(
                next_line
                and not next_line.startswith("【")
                and not re.match(r"^[一二三四五六七八九十]+[、.．]", next_line)
                for next_line in kept_lines[idx + 1 :]
            )
            if not has_content:
                continue
        compact.append(line)

    return "\n".join(compact).strip() or summary


def mistral_inst_prompt(instruction: str, body: str) -> str:
    return f"<s>[INST] {instruction.strip()}\n{body.strip()} [/INST]"


# --------- Config / Secrets ---------
API_KEY = os.environ.get("API_KEY", "devkey")
UI_PASSWORD = os.environ.get("UI_PASSWORD", "changeme")
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "8"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_TRANS_DEFAULT = os.environ.get("OLLAMA_TRANS_MODEL", "cardio-translator")
MODEL_SUM_DEFAULT = os.environ.get("OLLAMA_SUM_MODEL", "cardio-summarizer")
KEEP_ALIVE = os.environ.get("KEEP_ALIVE", "3h")

app = FastAPI(title="Cardio Dual-Model")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COOKIE_NAME = "cardio_sess"


def sign(payload: bytes) -> str:
    return hmac.new(API_KEY.encode(), payload, hashlib.sha256).hexdigest()


def make_token(sub: str, exp_ts: int) -> str:
    payload = f"{sub}|{exp_ts}".encode()
    b64 = base64.urlsafe_b64encode(payload).decode()
    sig = sign(payload)
    return f"{b64}.{sig}"


def parse_token(token: str):
    try:
        b64, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode())
        if not hmac.compare_digest(sign(payload), sig):
            return None
        sub, exp = payload.decode().split("|", 1)
        if int(exp) < int(time.time()):
            return None
        return {"sub": sub, "exp": int(exp)}
    except Exception:
        return None


def auth_ok(request: Request, x_api_key: str | None) -> bool:
    if x_api_key and hmac.compare_digest(x_api_key, API_KEY):
        return True
    token = request.cookies.get(COOKIE_NAME)
    if token and parse_token(token):
        return True
    return False


NUM_VALUE_RE = re.compile(r"\d+(?:\.\d+)?")


def extract_nums_units(text: str) -> set[str]:
    nums: set[str] = set()
    if not text:
        return nums
    for m in NUM_VALUE_RE.finditer(text):
        start = m.start()
        raw = m.group(0)
        if start > 0 and text[start - 1] == "^":
            continue
        try:
            val = float(raw)
            key = f"{val:g}"
        except Exception:
            key = raw
        nums.add(key)
    return nums


def tag_lines_for_translation(text: str) -> str:
    tagged_lines: list[str] = []
    idx = 1
    for raw in text.splitlines():
        if not raw.strip():
            tagged_lines.append("")
        else:
            tag = f"[L{idx:02d}] "
            tagged_lines.append(tag + raw.strip())
            idx += 1
    return "\n".join(tagged_lines)


def untag_translated_lines(text: str) -> str:
    if not text:
        return ""
    if "[L" in text:
        segments = re.split(r"(?=\[L\d+\])", text)
        out_lines: list[str] = []
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            seg = re.sub(r"^\[L\d+\]\s*", "", seg)
            if seg:
                out_lines.append(seg)
        if out_lines:
            return "\n".join(out_lines)
    s = text.strip()
    if not s:
        return ""
    s = " ".join(s.split())
    sentences = [p.strip() for p in re.split(r"(?<=[。！？；])", s) if p.strip()]
    keywords = (
        "左心",
        "右心",
        "心房",
        "心室",
        "主動脈",
        "肺動脈",
        "二尖瓣",
        "三尖瓣",
        "主動脈瓣",
        "肺動脈瓣",
        "心包膜",
        "心肌",
        "心功能",
        "收縮功能",
        "舒張功能",
    )
    lines: list[str] = []
    for sent in sentences:
        parts = re.split(r"(，|,)", sent)
        buf = ""
        i = 0
        while i < len(parts):
            part = parts[i]
            if part in ("，", ","):
                buf += part
                i += 1
                if i < len(parts):
                    nxt = parts[i].lstrip()
                    if any(nxt.startswith(k) for k in keywords):
                        if buf.strip():
                            lines.append(buf.strip())
                        buf = ""
                continue
            else:
                buf += part
                i += 1
        if buf.strip():
            lines.append(buf.strip())
    if not lines:
        return s
    return "\n".join(lines)


TERM_MAP = {
    "連枷樣運動": "飄動樣運動",
    "連枷樣": "飄動樣",
    "連枷運動": "飄動運動",
    "連枷": "飄動",
}


def apply_term_map(text: str) -> str:
    if not text:
        return text
    for src, tgt in TERM_MAP.items():
        text = text.replace(src, tgt)
    return text


class GlossaryPair(BaseModel):
    src: str
    tgt: str


class TranslateReq(BaseModel):
    source: str = Field(min_length=1)
    target_lang: str = "繁體中文（台灣）"
    style: str = "Clinical"
    keep_formatting: bool = True
    glossary: list[GlossaryPair] = []
    max_new_tokens: int = Field(ge=1, le=4096, default=2048)
    temperature: float = Field(ge=0.0, le=1.5, default=0.10)
    top_p: float = Field(ge=0.1, le=1.0, default=0.9)
    translator_model: str | None = None


class SummarizeReq(BaseModel):
    source: str = Field(min_length=1)
    target_lang: str = "繁體中文（台灣）"
    style: str = "Clinical"
    keep_formatting: bool = True
    max_new_tokens: int = Field(ge=1, le=4096, default=1024)
    temperature: float = Field(ge=0.0, le=1.5, default=0.2)
    top_p: float = Field(ge=0.1, le=1.0, default=0.9)
    summarizer_model: str | None = None


class PipelineReq(BaseModel):
    source: str = Field(min_length=1)
    target_lang: str = "繁體中文（台灣）"
    style: str = "Clinical"
    keep_formatting: bool = True
    glossary: list[GlossaryPair] = []
    max_new_tokens_translate: int = Field(ge=1, le=4096, default=2048)
    temperature_translate: float = Field(ge=0.0, le=1.5, default=0.10)
    max_new_tokens_summary: int = Field(ge=1, le=4096, default=1024)
    temperature_summary: float = Field(ge=0.0, le=1.5, default=0.2)
    top_p: float = Field(ge=0.1, le=1.0, default=0.9)
    translator_model: str | None = None
    summarizer_model: str | None = None


def build_mistral_v01_summary_prompt(req: SummarizeReq) -> str:
    instruction = (
        "你是一位資深心臟科醫師。請根據以下「中文心臟超音波報告」，撰寫一份符合臨床醫師風格的完整解讀，"
        "內容請整理成有條理的段落，至少包含：\n"
        "1. 心臟結構與功能（心房、心室、左心室射出分率等）。\n"
        "2. 主要異常發現與可能臨床意義。\n"
        "3. 綜合臨床建議與後續追蹤建議。\n"
        "請不要逐字重述原始報告，不要重複同一段內容兩次，也不要加入醫師姓名或與報告無關的資訊。"
    )
    body = req.source or ""
    return mistral_inst_prompt(instruction, body)


def build_legacy_translate_prompt(req: TranslateReq) -> str:
    instruction = (
        "請將以下心臟超音波報告翻譯為臨床風格的繁體中文，並保持語氣一致且不加入推論。"
    )
    body = req.source.strip()

    return (
        "Below is an instruction that describes a task, paired with an input that provides further context. "
        "Write a response that appropriately completes the request.\n\n"
        "### Instruction:\n"
        f"{instruction}\n\n"
        "### Input:\n"
        f"{body}\n\n"
        "### Response:\n"
    )


def build_strict_translate_prompt(req: TranslateReq) -> str:
    instruction = (
        "請將以下心臟超音波報告翻譯為臨床風格的繁體中文，並保持語氣一致且不加入推論。"
        "請嚴格依照原文順序逐項翻譯為繁體中文，"
        "不可摘要、不可重組句子、不可補充推論、"
        "不可省略數值、單位、嚴重度、解剖位置或檢查結論；"
        "原文中每個以逗號、句號或分號分隔的資訊片段都必須在譯文中對應一次；"
        "括號內尺寸、E/E'、Qp/Qs、PG、GLS、肺動脈高壓、肺動脈主幹、"
        "心包腔、側壁/外側壁/下外側壁、近端1/2、完全無收縮、"
        "極輕度、輕度至中度、極少量等描述必須完整保留。"
    )
    body = req.source.strip()

    return (
        "### Instruction:\n"
        f"{instruction}\n\n"
        "### Input:\n"
        f"{body}\n\n"
        "### Response:\n"
    )


def build_translate_prompt(req: TranslateReq, model_name: str) -> str:
    if "llama-3.2-3b-instruct-translator-deploy" in (model_name or ""):
        return build_strict_translate_prompt(req)
    return build_legacy_translate_prompt(req)


CLINICAL_SUMMARY_SUFFIX = (
    "請以繁體中文輸出保守、忠實、結構化的臨床摘要；"
    "優先整理原文已明確出現的心臟結構與功能、主要異常發現、綜合解說與建議；"
    "保留重要數值、器官、瓣膜、嚴重度與關鍵檢查結論；"
    "不可新增原文沒有的數值、器官、解剖位置、嚴重度、診斷、病理生理推論或治療建議；"
    "不可自行把壓差或量測值推論成新的疾病嚴重度；"
    "若原文語氣保守或不確定，摘要中也必須保留不確定性；"
    "若沒有足夠依據，寧可省略延伸解釋，也不要補寫；"
    "請嚴格使用以下固定格式，若某節沒有足夠依據可省略該節，但不可改寫節名："
    "【主要異常】、【心臟功能】、【建議】；"
    "每節最多 2 點，每點 1 句，總句數盡量控制在 5 句以內；"
    "只可摘錄原文已明確出現的異常與結論，不可為了摘要完整而主動補齊正常項目；"
    "不得輸出綜合敘事段落、病因推測、風險延伸解說或額外衛教語句；"
    "若原文只有數值而沒有明確結論，請保留數值，不可自行判讀成新的異常。"
)

ACADEMIC_SUMMARY_SUFFIX = (
    "請以繁體中文輸出較正式的學術風格結構化摘要，"
    "重點整理心臟結構與功能、主要異常發現、可能的病理生理意義與綜合建議；"
    "保留重要數值、器官、瓣膜、嚴重度與關鍵檢查結論；"
    "不可捏造原文沒有的診斷、數值、器官或治療建議。"
)

PATIENT_SUMMARY_SUFFIX = (
    "請以繁體中文輸出白話、容易理解的摘要，"
    "向非醫療背景讀者說明重點發現、可能代表的意義與後續建議；"
    "可簡化術語，但不可捏造原文沒有的診斷、數值、器官或治療建議。"
)

SUMMARY_REVISION_PROMPT_TEMPLATE = """### Instruction:
請檢查下列臨床摘要草稿是否遺漏原文中已明確出現的主要異常、重要數值、嚴重度、器官/瓣膜結構與關鍵檢查結論。若有遺漏，請輸出修正後的繁體中文臨床摘要。
重要原則：
1. 可以保留有原文依據的摘要化補述，但不可新增原文沒有的數值、器官、嚴重度、診斷或病理生理推論。
2. 優先補回「主要異常」與「心臟功能」中的核心 finding；若只是次要正常描述，可不必補齊。
3. 若原文只有數值而沒有明確結論，可保留數值，但不可自行升級成新的疾病判讀。
4. 請維持簡潔、結構化的臨床摘要格式，不要寫成長段評論。
5. 請優先在原草稿基礎上補回遺漏的重點，不要整篇大幅改寫成新的敘事版本。
6. 請嚴格使用以下固定格式，若某節沒有足夠依據可省略該節：
【主要異常】
- ...
【心臟功能】
- ...
【建議】
- ...
7. 每節最多 2 點，每點 1 句；總句數盡量控制在 6 句以內。
8. 若原文已有明確結論（例如有肺高壓、收縮功能下降、舒張壓升高、重度狹窄/逆流），應優先補回；若原文僅提供量測值而未明確下結論，不可自行推論成新診斷。
9. 特別優先檢查是否遺漏以下資訊：
   - 舒張功能與壓力指標：E/A、E/E'、舒張功能障礙、舒張壓升高、充盈壓升高
   - 右心與肺循環：肺高壓、肺動脈主幹/肺動脈幹擴張、右心房/右心室擴大、三尖瓣壓力梯度
   - 區域性壁運動：心尖、側壁、外側壁、下壁、隔部、前壁等局部異常位置
   - 關鍵嚴重度：極輕度、輕度至中度、中度至重度、重度、少量、極少量
   - 其他高價值 finding：心包積液、心包腔、瓣膜狹窄/逆流嚴重度、肺動脈瓣/主動脈根部/右心房面積等
10. 若原文同時出現「數值 + 已明確判讀」，優先保留已明確判讀，並視需要保留最關鍵數值，不必把所有次要數值全部重抄。

### Input:
原文：
{input_text}

草稿：
{draft_text}

### Response:
"""


def build_llama_summary_prompt(req: SummarizeReq) -> str:
    style = (req.style or "").strip().lower()
    instruction = "請摘要以下心臟超音波報告"
    if "academic" in style:
        instruction = f"{instruction}。{ACADEMIC_SUMMARY_SUFFIX}"
    elif "patient" in style or "friendly" in style or "simple" in style:
        instruction = f"{instruction}。{PATIENT_SUMMARY_SUFFIX}"
    else:
        instruction = f"{instruction}。{CLINICAL_SUMMARY_SUFFIX}"

    return (
        "### Instruction:\n"
        f"{instruction}\n\n"
        "### Input:\n"
        f"{req.source.strip()}\n\n"
        "### Response:\n"
    )


def build_summary_revision_prompt(input_text: str, draft_text: str) -> str:
    return SUMMARY_REVISION_PROMPT_TEMPLATE.format(
        input_text=input_text.strip(),
        draft_text=draft_text.strip(),
    )


def uses_summary_revision(model_name: str) -> bool:
    return "llama-3.2-3b-instruct-summarizer-clinical-v4" in (model_name or "")


def build_summary_prompt(req: SummarizeReq, model_name: str = "") -> str:
    if "llama-3.2-3b-instruct-summarizer-clinical-v4" in (model_name or ""):
        return build_llama_summary_prompt(req)

    style = (req.style or "").strip().lower()
    if "clinical" in style:
        tone_prompt = "Write a concise structured clinical summary focusing on cardiac function, abnormalities, and key impressions."
    elif "academic" in style:
        tone_prompt = "Summarize the report in an academic tone, highlighting methodology, results, and interpretations."
    elif "patient" in style or "friendly" in style:
        tone_prompt = "Explain the findings in simple, patient-friendly Traditional Chinese that non-medical readers can understand."
    else:
        tone_prompt = (
            "Provide a brief, professional summary of the cardiac ultrasound findings."
        )
    return (
        "Summarize the following Traditional Chinese echocardiography report.\n"
        "Provide a clear and structured summary with:\n"
        "1. 心臟結構與功能\n"
        "2. 主要異常發現\n"
        "3. 臨床建議或解釋\n\n"
        f"{tone_prompt}\n\n"
        "=== 心臟超音波報告 ===\n"
        f"{req.source.strip()}\n"
        "=== 結束 ==="
    )


def ollama_generate(
    model: str, prompt: str, max_new_tokens: int, temperature: float, top_p: float
) -> str:
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": float(temperature),
            "top_p": float(top_p),
            "num_predict": int(max_new_tokens),
            "repeat_penalty": 1.05,
            "num_ctx": 4096,
        },
    }
    r = requests.post(url, json=payload, timeout=600)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json().get("response", "")


def json_event(event: str, **data) -> str:
    payload = {"event": event, **data}
    return json.dumps(payload, ensure_ascii=False) + "\n"


def ollama_stream_generate(
    model: str, prompt: str, max_new_tokens: int, temperature: float, top_p: float
):
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": float(temperature),
            "top_p": float(top_p),
            "num_predict": int(max_new_tokens),
            "repeat_penalty": 1.05,
            "num_ctx": 4096,
        },
    }
    r = requests.post(url, json=payload, stream=True, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    for line in r.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line.decode("utf-8"))
        except Exception:
            continue
        yield chunk


def build_mistral_translate_prompt(english_text: str, tone: str = "Clinical") -> str:
    tone = tone.strip().lower()
    base = (
        "Translate the following cardiology ultrasound report from English to Traditional Chinese.\n"
        "- Keep the original line breaks and section order.\n"
        "- Do not add, remove, or infer any information.\n"
        "- Translate abbreviations to standard clinical Chinese when common (e.g., MR=二尖瓣逆流).\n"
        "- Keep units and numbers as-is.\n"
        "- Output ONLY the translated report text. Do not include any explanations.\n\n"
    )
    if tone == "clinical":
        tone_hint = "Use formal clinical tone.\n"
    elif tone == "academic":
        tone_hint = (
            "Use academic, publication-style language suitable for medical journals.\n"
        )
    elif tone in ["patient-friendly", "simple"]:
        tone_hint = (
            "Use simple, patient-friendly tone understandable by non-medical readers.\n"
        )
    else:
        tone_hint = ""
    return f"{base}{tone_hint}=== English report ===\n{english_text.strip()}\n=== End ===\n"


def build_mistral_summary_prompt(chinese_text: str, style: str = "Clinical") -> str:
    style = style.strip().lower()
    base = (
        "Summarize the following Traditional Chinese echocardiography report into a structured medical summary.\n"
        "Divide the summary into 3 sections:『心臟功能與結構評估』『異常發現』『綜合說明與建議』.\n"
        "Include key metrics (e.g., EF, chamber sizes, valve status) but avoid repeating every number.\n"
    )
    if style == "clinical":
        style_hint = "- Use concise and professional clinical language.\n- Follow hospital reporting style.\n"
    elif style == "academic":
        style_hint = "- Use formal academic tone suitable for scientific discussion.\n- Explain findings with logical reasoning, including possible physiological implications.\n"
    elif style in ["patient-friendly", "simple"]:
        style_hint = "- Explain findings in plain language for patient understanding.\n- Simplify medical terms while keeping accuracy.\n"
    else:
        style_hint = ""
    return f"{base}{style_hint}\n\n=== 心臟超音波報告 ===\n{chinese_text.strip()}\n=== 結束 ===\nPlease output only the structured summary text.\n"


# -------------------------------------------------------------------------
#  2. API Routes
# -------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    ok = False
    try:
        ok = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).status_code == 200
    except Exception:
        ok = False
    return {
        "ok": ok,
        "translator_default": MODEL_TRANS_DEFAULT,
        "summarizer_default": MODEL_SUM_DEFAULT,
    }


@app.get("/models")
def models(request: Request, x_api_key: str = Header(default=None)):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
    data = r.json()
    names = sorted({m.get("name", "") for m in data.get("models", []) if m.get("name")})
    return {
        "names": names,
        "defaults": {
            "translator": MODEL_TRANS_DEFAULT,
            "summarizer": MODEL_SUM_DEFAULT,
        },
    }


@app.post("/translate")
def translate(
    req: TranslateReq, request: Request, x_api_key: str = Header(default=None)
):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    model = req.translator_model or MODEL_TRANS_DEFAULT
    if "mistralv0.1" in model:
        prompt = build_mistral_v01_translate_prompt(req)
    else:
        prompt = build_translate_prompt(req, model)
    raw_text = ollama_generate(
        model, prompt, req.max_new_tokens, req.temperature, req.top_p
    )
    text = untag_translated_lines(raw_text)
    text = apply_term_map(text)
    text = strip_model_header(text)
    src_set = extract_nums_units(req.source)
    tgt_set = extract_nums_units(text)
    missing = sorted(src_set - tgt_set)
    extra = sorted(tgt_set - src_set)
    warn = ""
    if missing:
        warn += "譯文檢查：缺 " + ", ".join(missing)
    if extra:
        warn += ("\n" if warn else "") + "譯文檢查：多 " + ", ".join(extra)
    return {"translation": text, "warn": warn}


@app.post("/translate_stream")
def translate_stream(
    req: TranslateReq, request: Request, x_api_key: str = Header(default=None)
):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    model = req.translator_model or MODEL_TRANS_DEFAULT
    if "mistralv0.1" in model:
        prompt = build_mistral_v01_translate_prompt(req)
    else:
        prompt = build_translate_prompt(req, model)
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": float(req.temperature),
            "top_p": float(req.top_p),
            "num_predict": int(req.max_new_tokens),
            "repeat_penalty": 1.05,
            "num_ctx": 4096,
        },
    }

    def event_gen():
        try:
            r = requests.post(url, json=payload, stream=True, timeout=600)
        except Exception as e:
            err = {"event": "error", "message": str(e)}
            yield json.dumps(err, ensure_ascii=False) + "\n"
            return
        if r.status_code != 200:
            err = {"event": "error", "message": r.text}
            yield json.dumps(err, ensure_ascii=False) + "\n"
            return
        full_text = ""
        for line in r.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            token = chunk.get("response", "")
            done = chunk.get("done", False)
            if token:
                full_text += token
                yield json.dumps(
                    {"event": "token", "delta": token}, ensure_ascii=False
                ) + "\n"
            if done:
                src_set = extract_nums_units(req.source)
                tgt_set = extract_nums_units(full_text)
                missing = sorted(src_set - tgt_set)
                extra = sorted(tgt_set - src_set)
                warn = ""
                if missing:
                    warn += "譯文檢查：缺 " + ", ".join(missing)
                if extra:
                    warn += ("\n" if warn else "") + "譯文檢查：多 " + ", ".join(extra)
                yield json.dumps(
                    {"event": "done", "warn": warn}, ensure_ascii=False
                ) + "\n"
                break

    return StreamingResponse(event_gen(), media_type="text/plain; charset=utf-8")


@app.post("/summarize")
def summarize(
    req: SummarizeReq, request: Request, x_api_key: str = Header(default=None)
):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    model = req.summarizer_model or MODEL_SUM_DEFAULT
    if "mistralv0.1" in model:
        prompt = build_mistral_v01_summary_prompt(req)
    else:
        prompt = build_summary_prompt(req, model)
    text = ollama_generate(
        model, prompt, req.max_new_tokens, req.temperature, req.top_p
    ).strip()
    if uses_summary_revision(model) and text:
        revision_prompt = build_summary_revision_prompt(req.source, text)
        revised_text = ollama_generate(
            model, revision_prompt, req.max_new_tokens, 0.1, req.top_p
        ).strip()
        if revised_text:
            text = revised_text
        text = sanitize_summary_against_source(req.source, text)
    text = dedup_summary_lines(text)
    src_set = extract_nums_units(req.source)
    tgt_set = extract_nums_units(text)
    missing = sorted(src_set - tgt_set)
    extra = sorted(tgt_set - src_set)
    warn = ""
    if missing:
        warn += "摘要檢查：缺 " + ", ".join(missing)
    if extra:
        warn += ("\n" if warn else "") + "摘要檢查：多 " + ", ".join(extra)
    return {"summary": text, "warn": warn}


@app.post("/pipeline")
def pipeline(req: PipelineReq, request: Request, x_api_key: str = Header(default=None)):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    t_model = req.translator_model or MODEL_TRANS_DEFAULT
    s_model = req.summarizer_model or MODEL_SUM_DEFAULT
    mistral_trans = "mistral" in t_model.lower()
    mistral_sum = "mistral" in s_model.lower()
    if mistral_trans:
        t_prompt = build_mistral_translate_prompt(req.source, req.style)
    else:
        t_prompt = build_translate_prompt(
            TranslateReq(
                source=req.source,
                target_lang=req.target_lang,
                style=req.style,
                keep_formatting=req.keep_formatting,
                glossary=req.glossary,
                max_new_tokens=req.max_new_tokens_translate,
                temperature=req.temperature_translate,
                top_p=req.top_p,
            ),
            t_model,
        )
    raw_t = ollama_generate(
        t_model,
        t_prompt,
        req.max_new_tokens_translate,
        req.temperature_translate,
        req.top_p,
    )
    t = untag_translated_lines(raw_t)
    t = apply_term_map(t)
    if mistral_sum:
        s_prompt = build_mistral_summary_prompt(t, req.style)
    else:
        s_prompt = build_summary_prompt(
            SummarizeReq(
                source=t,
                target_lang=req.target_lang,
                style=req.style,
                keep_formatting=req.keep_formatting,
                max_new_tokens=req.max_new_tokens_summary,
                temperature=req.temperature_summary,
                top_p=req.top_p,
            ),
            s_model,
        )
    s = ollama_generate(
        s_model,
        s_prompt,
        req.max_new_tokens_summary,
        req.temperature_summary,
        req.top_p,
    ).strip()
    if uses_summary_revision(s_model) and s:
        revision_prompt = build_summary_revision_prompt(t, s)
        revised_summary = ollama_generate(
            s_model,
            revision_prompt,
            req.max_new_tokens_summary,
            0.1,
            req.top_p,
        ).strip()
        if revised_summary:
            s = revised_summary
        s = sanitize_summary_against_source(t, s)
    src_set = extract_nums_units(req.source)
    trans_set = extract_nums_units(t)
    sum_set = extract_nums_units(s)
    return {
        "translation": t,
        "summary": s,
        "warn_translation_missing": sorted(src_set - trans_set),
        "warn_translation_extra": sorted(trans_set - src_set),
        "warn_summary_missing": sorted(trans_set - sum_set),
        "warn_summary_extra": sorted(sum_set - trans_set),
    }


@app.post("/pipeline_stream")
def pipeline_stream(req: PipelineReq, request: Request, x_api_key: str = Header(default=None)):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")

    def event_gen():
        try:
            t_model = req.translator_model or MODEL_TRANS_DEFAULT
            s_model = req.summarizer_model or MODEL_SUM_DEFAULT
            mistral_trans = "mistral" in t_model.lower()
            mistral_sum = "mistral" in s_model.lower()

            if mistral_trans:
                t_prompt = build_mistral_translate_prompt(req.source, req.style)
            else:
                t_prompt = build_translate_prompt(
                    TranslateReq(
                        source=req.source,
                        target_lang=req.target_lang,
                        style=req.style,
                        keep_formatting=req.keep_formatting,
                        glossary=req.glossary,
                        max_new_tokens=req.max_new_tokens_translate,
                        temperature=req.temperature_translate,
                        top_p=req.top_p,
                    ),
                    t_model,
                )

            yield json_event(
                "phase_start",
                phase="translate",
                label="翻譯模型推論中",
                progress=8,
            )
            raw_t = ""
            for chunk in ollama_stream_generate(
                t_model,
                t_prompt,
                req.max_new_tokens_translate,
                req.temperature_translate,
                req.top_p,
            ):
                token = chunk.get("response", "")
                done = chunk.get("done", False)
                if token:
                    raw_t += token
                    yield json_event("token", phase="translate", delta=token)
                if done:
                    break

            t = untag_translated_lines(raw_t)
            t = apply_term_map(t)
            t = strip_model_header(t)
            src_set = extract_nums_units(req.source)
            trans_set = extract_nums_units(t)
            warn_translation_missing = sorted(src_set - trans_set)
            warn_translation_extra = sorted(trans_set - src_set)
            yield json_event(
                "phase_done",
                phase="translate",
                text=t,
                progress=52,
                warn_missing=warn_translation_missing,
                warn_extra=warn_translation_extra,
            )

            if mistral_sum:
                s_prompt = build_mistral_summary_prompt(t, req.style)
            else:
                s_prompt = build_summary_prompt(
                    SummarizeReq(
                        source=t,
                        target_lang=req.target_lang,
                        style=req.style,
                        keep_formatting=req.keep_formatting,
                        max_new_tokens=req.max_new_tokens_summary,
                        temperature=req.temperature_summary,
                        top_p=req.top_p,
                    ),
                    s_model,
                )

            yield json_event(
                "phase_start",
                phase="summary",
                label="摘要模型推論中",
                progress=58,
            )
            s = ""
            for chunk in ollama_stream_generate(
                s_model,
                s_prompt,
                req.max_new_tokens_summary,
                req.temperature_summary,
                req.top_p,
            ):
                token = chunk.get("response", "")
                done = chunk.get("done", False)
                if token:
                    s += token
                    yield json_event("token", phase="summary", delta=token)
                if done:
                    break

            s = s.strip()
            if uses_summary_revision(s_model) and s:
                yield json_event(
                    "status",
                    phase="summary",
                    label="摘要校正與來源一致性檢查",
                    progress=94,
                )
                revision_prompt = build_summary_revision_prompt(t, s)
                revised_summary = ollama_generate(
                    s_model,
                    revision_prompt,
                    req.max_new_tokens_summary,
                    0.1,
                    req.top_p,
                ).strip()
                if revised_summary:
                    s = revised_summary
                s = sanitize_summary_against_source(t, s)
            s = dedup_summary_lines(s)

            sum_set = extract_nums_units(s)
            warn_summary_missing = sorted(trans_set - sum_set)
            warn_summary_extra = sorted(sum_set - trans_set)
            yield json_event(
                "phase_done",
                phase="summary",
                text=s,
                progress=98,
                warn_missing=warn_summary_missing,
                warn_extra=warn_summary_extra,
            )
            yield json_event(
                "done",
                progress=100,
                warn_translation_missing=warn_translation_missing,
                warn_translation_extra=warn_translation_extra,
                warn_summary_missing=warn_summary_missing,
                warn_summary_extra=warn_summary_extra,
            )
        except Exception as e:
            yield json_event("error", message=str(e))

    return StreamingResponse(event_gen(), media_type="text/plain; charset=utf-8")


@app.post("/login")
def login(data: dict, response: Response):
    pwd = (data or {}).get("password", "")
    if not hmac.compare_digest(pwd, UI_PASSWORD):
        raise HTTPException(401, "wrong password")
    exp = int(time.time()) + SESSION_HOURS * 3600
    token = make_token("user", exp)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
        path="/",
    )
    return {"ok": True, "exp": exp}


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def ui(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and parse_token(token):
        return templates.TemplateResponse("ui.html", {"request": request})
    return templates.TemplateResponse("login.html", {"request": request})
