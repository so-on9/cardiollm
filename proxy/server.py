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


def build_translate_prompt(req: TranslateReq) -> str:
    style = (req.style or "").strip().lower()
    if "clinical" in style:
        tone_prompt = "使用臨床報告語氣，專業且精簡。"
    elif "academic" in style:
        tone_prompt = "使用學術性中文，保持邏輯嚴謹與精確。"
    elif "patient" in style or "friendly" in style:
        tone_prompt = "使用淺顯易懂的病患友善中文，保持醫學準確。"
    else:
        tone_prompt = "使用標準專業繁體中文，保持報告格式清晰。"
    src_nums = sorted(extract_nums_units(req.source))
    tagged_src = tag_lines_for_translation(req.source)
    return (
        "你是一位專門翻譯心臟超音波報告的專業醫學翻譯員。\n"
        "請將以下英文報告翻譯成繁體中文（台灣用語）。\n"
        "每一行開頭的 [Lxx] 標記代表原始報告中的一行，請嚴格遵守以下規則：\n"
        "1. 保留每一個 [Lxx] 標記，不要翻譯、刪除或新增標記。\n"
        "2. 每一個 [Lxx] 只能對應一行中文，不要把多行內容合併成一行，也不要拆成多行。\n"
        "3. 不要省略任何含有 [Lxx] 的行，也不要額外新增說明文字。\n"
        "4. 所有數值與單位必須與原文一致，不要自行推論或更改。\n"
        "5. **下面列出的每一個數值都必須完整出現在翻譯中，不能省略或改寫。**\n\n"
        f"原文中的數值列表：{', '.join(src_nums)}\n\n"
        f"語氣設定：{tone_prompt}\n\n"
        "=== 英文報告開始 ===\n"
        f"{tagged_src}\n"
        "=== 英文報告結束 ===\n"
        "請直接輸出對應的繁體中文，每一行前面保留相同的 [Lxx] 標記。"
    )


def build_summary_prompt(req: SummarizeReq) -> str:
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
        prompt = build_translate_prompt(req)
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
        prompt = build_translate_prompt(req)
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
        prompt = build_summary_prompt(req)
    text = ollama_generate(
        model, prompt, req.max_new_tokens, req.temperature, req.top_p
    ).strip()
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
            )
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
            )
        )
    s = ollama_generate(
        s_model,
        s_prompt,
        req.max_new_tokens_summary,
        req.temperature_summary,
        req.top_p,
    ).strip()
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
