# server.py — Cardio Dual-Model (Final Fixed: Correct Coordinates)
from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlsplit
import logging
import os, requests, time, hmac, hashlib, base64, json

from prompts import (
    apply_term_map,
    build_mistral_summary_prompt,
    build_mistral_translate_prompt,
    build_mistral_v01_summary_prompt,
    build_mistral_v01_translate_prompt,
    build_summary_prompt,
    build_summary_revision_prompt,
    build_translate_prompt,
    dedup_summary_lines,
    extract_nums_units,
    finalize_complete_summary,
    has_summary_loop_tail,
    preserves_model_summary_format,
    preserves_translation_linebreaks,
    strip_model_header,
    trim_summary_repetitions,
    untag_translated_lines,
    uses_complete_clinical_summary_model,
    uses_summary_revision,
)

from image_generation import ImageGenerateReq, generate_image
from structured_json import (
    build_structured_findings_prompt,
    extract_json_object,
    normalize_structured_findings,
    rule_based_structured_findings,
)
from terminology import apply_translation_term_audit, standardize_summary_terms

# -------------------------------------------------------------------------
#  Backend
# -------------------------------------------------------------------------




# --------- Config / Secrets ---------
API_KEY = os.environ.get("API_KEY", "")
UI_PASSWORD = os.environ.get("UI_PASSWORD", "")
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "8"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
DOCS_ENABLED = os.environ.get("DOCS_ENABLED", "false").lower() == "true"
LOGIN_MAX_FAILURES = max(3, int(os.environ.get("LOGIN_MAX_FAILURES", "6")))
LOGIN_WINDOW_SECONDS = max(60, int(os.environ.get("LOGIN_WINDOW_SECONDS", "900")))
LOGIN_BLOCK_SECONDS = max(60, int(os.environ.get("LOGIN_BLOCK_SECONDS", "900")))
OLLAMA_URL = (
    os.environ.get("OLLAMA_URL")
    or os.environ.get("OLLAMA_BASE_URL")
    or "http://localhost:11434"
)
MODEL_TRANS_DEFAULT = os.environ.get("OLLAMA_TRANS_MODEL", "cardio-translator")
MODEL_SUM_DEFAULT = os.environ.get("OLLAMA_SUM_MODEL", "cardio-summarizer")
KEEP_ALIVE = os.environ.get("KEEP_ALIVE", "3h")
LLAMA_COMPLETE_SUMMARY_MAX_TOKENS = int(os.environ.get("LLAMA_COMPLETE_SUMMARY_MAX_TOKENS", "1280"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

logger = logging.getLogger("cardiollm.security")

if COOKIE_SECURE and (API_KEY in {"", "devkey"} or UI_PASSWORD in {"", "changeme"}):
    raise RuntimeError("Production HTTPS mode requires non-default API_KEY and UI_PASSWORD values")
if API_KEY in {"", "devkey"} or UI_PASSWORD in {"", "changeme"}:
    logger.warning("CardioLLM is using development authentication credentials")

app = FastAPI(
    title="Cardio Dual-Model",
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=bool(CORS_ORIGINS),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

COOKIE_NAME = "__Host-cardio_sess" if COOKIE_SECURE else "cardio_sess"
LEGACY_COOKIE_NAME = "cardio_sess"
LOGIN_FAILURES: dict[str, deque[float]] = defaultdict(deque)
LOGIN_BLOCKED_UNTIL: dict[str, float] = {}
LOGIN_RATE_LOCK = Lock()


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


def request_client_id(request: Request) -> str:
    return (
        request.headers.get("x-real-ip", "").strip()
        or (request.client.host if request.client else "unknown")
    )


def login_retry_after(client_id: str) -> int:
    now = time.monotonic()
    with LOGIN_RATE_LOCK:
        blocked_until = LOGIN_BLOCKED_UNTIL.get(client_id, 0.0)
        if blocked_until > now:
            return max(1, int(blocked_until - now) + 1)
        LOGIN_BLOCKED_UNTIL.pop(client_id, None)

        attempts = LOGIN_FAILURES[client_id]
        cutoff = now - LOGIN_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            LOGIN_FAILURES.pop(client_id, None)
        return 0


def record_login_failure(client_id: str) -> int:
    now = time.monotonic()
    with LOGIN_RATE_LOCK:
        attempts = LOGIN_FAILURES[client_id]
        cutoff = now - LOGIN_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        attempts.append(now)
        if len(attempts) < LOGIN_MAX_FAILURES:
            return 0
        LOGIN_FAILURES.pop(client_id, None)
        LOGIN_BLOCKED_UNTIL[client_id] = now + LOGIN_BLOCK_SECONDS
        return LOGIN_BLOCK_SECONDS


def clear_login_failures(client_id: str) -> None:
    with LOGIN_RATE_LOCK:
        LOGIN_FAILURES.pop(client_id, None)
        LOGIN_BLOCKED_UNTIL.pop(client_id, None)


def same_origin_host(request: Request, source_url: str) -> bool:
    try:
        source_host = urlsplit(source_url).netloc.lower()
    except ValueError:
        return False
    request_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or ""
    ).split(",", 1)[0].strip().lower()
    return bool(source_host and request_host and source_host == request_host)


@app.middleware("http")
async def security_policy(request: Request, call_next):
    api_key = request.headers.get("x-api-key")
    session_cookie = request.cookies.get(COOKIE_NAME)

    if request.url.path.startswith("/static/generated/") and not auth_ok(request, api_key):
        response = JSONResponse({"detail": "authentication required"}, status_code=401)
    else:
        unsafe_method = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        api_key_valid = bool(api_key and hmac.compare_digest(api_key, API_KEY))
        if unsafe_method and session_cookie and not api_key_valid:
            fetch_site = request.headers.get("sec-fetch-site", "").lower()
            origin = request.headers.get("origin", "")
            referer = request.headers.get("referer", "")
            cross_site = fetch_site == "cross-site"
            origin_mismatch = bool(origin and not same_origin_host(request, origin))
            referer_mismatch = bool(not origin and referer and not same_origin_host(request, referer))
            if cross_site or origin_mismatch or referer_mismatch:
                response = JSONResponse({"detail": "cross-origin request rejected"}, status_code=403)
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    )
    if request.url.path in {"/", "/login", "/logout"}:
        response.headers.setdefault("Cache-Control", "no-store")
    if COOKIE_SECURE:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response




class GlossaryPair(BaseModel):
    src: str
    tgt: str


class LoginReq(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class TranslateReq(BaseModel):
    source: str = Field(min_length=1)
    target_lang: str = "繁體中文（台灣）"
    style: str = "Clinical"
    keep_formatting: bool = True
    glossary: list[GlossaryPair] = []
    max_new_tokens: int = Field(ge=1, le=4096, default=2048)
    temperature: float = Field(ge=0.0, le=1.5, default=0.10)
    top_p: float = Field(ge=0.1, le=1.0, default=0.95)
    translator_model: str | None = None


class SummarizeReq(BaseModel):
    source: str = Field(min_length=1)
    target_lang: str = "繁體中文（台灣）"
    style: str = "Clinical"
    keep_formatting: bool = True
    max_new_tokens: int = Field(ge=1, le=4096, default=1024)
    temperature: float = Field(ge=0.0, le=1.5, default=0.0)
    top_p: float = Field(ge=0.1, le=1.0, default=0.95)
    summarizer_model: str | None = None


class PipelineReq(BaseModel):
    source: str = Field(min_length=1)
    target_lang: str = "繁體中文（台灣）"
    style: str = "Clinical"
    keep_formatting: bool = True
    glossary: list[GlossaryPair] = []
    max_new_tokens_translate: int = Field(ge=1, le=4096, default=2048)
    temperature_translate: float = Field(ge=0.0, le=1.5, default=0.10)
    max_new_tokens_summary: int = Field(ge=1, le=4096, default=2048)
    temperature_summary: float = Field(ge=0.0, le=1.5, default=0.0)
    top_p: float = Field(ge=0.1, le=1.0, default=0.95)
    translator_model: str | None = None
    summarizer_model: str | None = None


class WarmupReq(BaseModel):
    translator_model: str | None = None
    summarizer_model: str | None = None




def extract_structured_findings(
    model: str,
    source_text: str,
    translation_text: str,
    summary_text: str,
    top_p: float,
) -> dict:
    prompt = build_structured_findings_prompt(source_text, translation_text, summary_text)
    raw = ollama_generate(model, prompt, 768, 0.05, top_p, response_format="json").strip()
    parsed = extract_json_object(raw)
    return normalize_structured_findings(parsed, summary_text)


def build_translation_warn(source: str, translation: str, term_warnings: list[str] | None = None) -> str:
    src_set = extract_nums_units(source)
    tgt_set = extract_nums_units(translation)
    missing = sorted(src_set - tgt_set)
    extra = sorted(tgt_set - src_set)
    warn_parts: list[str] = []
    if missing:
        warn_parts.append("譯文檢查：缺 " + ", ".join(missing))
    if extra:
        warn_parts.append("譯文檢查：多 " + ", ".join(extra))
    if term_warnings:
        warn_parts.append("術語檢查：可能缺 " + ", ".join(term_warnings))
    return "\n".join(warn_parts)




def ollama_generate(
    model: str,
    prompt: str,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    response_format: str | None = None,
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
            "num_predict": effective_num_predict(model, max_new_tokens),
            "repeat_penalty": 1.05,
            "num_ctx": 4096,
        },
    }
    if uses_complete_clinical_summary_model(model):
        payload["options"]["seed"] = 42
    apply_generation_runtime_guards(model, payload["options"])
    if response_format:
        payload["format"] = response_format
    r = requests.post(url, json=payload, timeout=600)
    if r.status_code != 200 and response_format:
        payload.pop("format", None)
        r = requests.post(url, json=payload, timeout=600)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json().get("response", "")


def json_event(event: str, **data) -> str:
    payload = {"event": event, **data}
    return json.dumps(payload, ensure_ascii=False) + "\n"


def ollama_loaded_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/ps", timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    return sorted({
        model.get("name", "")
        for model in data.get("models", [])
        if model.get("name")
    })


def ollama_unload_model(model: str) -> None:
    payload = {
        "model": model,
        "prompt": "",
        "stream": False,
        "keep_alive": 0,
    }
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(r.text)


def ollama_warm_model(model: str) -> dict:
    payload = {
        "model": model,
        "prompt": "warmup",
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": 0.0,
            "top_p": 1.0,
            "num_predict": 1,
            "num_ctx": 4096,
        },
    }
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    return r.json()


def uses_legacy_mistral_prompt(model_name: str) -> bool:
    model_name = (model_name or "").lower()
    return "mistral" in model_name and "ministral" not in model_name


def uses_llama_complete_summary_runtime_guard(model_name: str) -> bool:
    model_name = (model_name or "").lower()
    return (
        "llama-3.2-3b-instruct-summarizer-clinical-v4" in model_name
        or "llama-3.2-3b-instruct-summarizer-complete-clinical-v5" in model_name
    )


def effective_num_predict(model_name: str, max_new_tokens: int) -> int:
    requested = int(max_new_tokens)
    if uses_llama_complete_summary_runtime_guard(model_name):
        return min(requested, LLAMA_COMPLETE_SUMMARY_MAX_TOKENS)
    return requested


def apply_generation_runtime_guards(model_name: str, options: dict) -> None:
    if uses_llama_complete_summary_runtime_guard(model_name):
        options["repeat_penalty"] = 1.08
        options["repeat_last_n"] = 512


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
            "num_predict": effective_num_predict(model, max_new_tokens),
            "repeat_penalty": 1.05,
            "num_ctx": 4096,
        },
    }
    if uses_complete_clinical_summary_model(model):
        payload["options"]["seed"] = 42
    apply_generation_runtime_guards(model, payload["options"])
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





# -------------------------------------------------------------------------
#  2. API Routes
# -------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/healthz")
def healthz():
    ok = False
    try:
        ok = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).status_code == 200
    except Exception:
        ok = False
    if not ok:
        return JSONResponse({"ok": False}, status_code=503)
    return {"ok": True}


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


@app.post("/models/warmup_stream")
def warmup_models_stream(req: WarmupReq, request: Request, x_api_key: str = Header(default=None)):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")

    target_models = [
        model
        for model in (req.translator_model or MODEL_TRANS_DEFAULT, req.summarizer_model or MODEL_SUM_DEFAULT)
        if model
    ]
    target_models = list(dict.fromkeys(target_models))

    def event_gen():
        try:
            yield json_event(
                "phase_start",
                phase="inspect",
                label="檢查目前載入模型",
                progress=6,
            )
            loaded = ollama_loaded_models()
            unload_targets = [model for model in loaded if model not in target_models]
            if unload_targets:
                step = 24 / max(len(unload_targets), 1)
                for idx, model in enumerate(unload_targets, start=1):
                    yield json_event(
                        "status",
                        phase="unload",
                        label=f"卸載舊模型：{model}",
                        progress=8 + int(step * (idx - 1)),
                    )
                    ollama_unload_model(model)
            else:
                yield json_event(
                    "status",
                    phase="unload",
                    label="沒有需要卸載的舊模型",
                    progress=28,
                )

            loaded_after_unload = set(ollama_loaded_models())
            load_step = 58 / max(len(target_models), 1)
            for idx, model in enumerate(target_models, start=1):
                base_progress = 32 + int(load_step * (idx - 1))
                if model in loaded_after_unload:
                    yield json_event(
                        "status",
                        phase="load",
                        label=f"模型已在記憶體：{model}",
                        progress=base_progress,
                    )
                    continue
                yield json_event(
                    "status",
                    phase="load",
                    label=f"載入模型：{model}",
                    progress=base_progress,
                )
                stats = ollama_warm_model(model)
                yield json_event(
                    "status",
                    phase="load",
                    label=f"已載入：{model}",
                    progress=32 + int(load_step * idx),
                    load_duration=stats.get("load_duration"),
                )

            final_loaded = ollama_loaded_models()
            yield json_event(
                "done",
                label="模型預熱完成",
                progress=100,
                loaded=final_loaded,
                targets=target_models,
            )
        except Exception as e:
            yield json_event("error", message=str(e), progress=100)

    return StreamingResponse(event_gen(), media_type="text/plain; charset=utf-8")


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
    if preserves_translation_linebreaks(model):
        text = raw_text.strip()
    else:
        text = untag_translated_lines(raw_text)
    text = apply_term_map(text)
    text = strip_model_header(text)
    text, term_warnings = apply_translation_term_audit(req.source, text)
    warn = build_translation_warn(req.source, text, term_warnings)
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
            "num_predict": effective_num_predict(model, req.max_new_tokens),
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
                if preserves_translation_linebreaks(model):
                    final_text = full_text.strip()
                else:
                    final_text = untag_translated_lines(full_text)
                final_text = apply_term_map(final_text)
                final_text = strip_model_header(final_text)
                final_text, term_warnings = apply_translation_term_audit(req.source, final_text)
                warn = build_translation_warn(req.source, final_text, term_warnings)
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
    raw_text = trim_summary_repetitions(text)
    if uses_summary_revision(model) and text:
        revision_prompt = build_summary_revision_prompt(req.source, text)
        revised_text = ollama_generate(
            model, revision_prompt, req.max_new_tokens, 0.1, req.top_p
        ).strip()
        if revised_text:
            text = revised_text
    if uses_complete_clinical_summary_model(model):
        analysis_text = finalize_complete_summary(req.source, text)
    else:
        analysis_text = dedup_summary_lines(text)
    display_text = raw_text if preserves_model_summary_format(model) else analysis_text
    analysis_text = standardize_summary_terms(analysis_text)
    display_text = standardize_summary_terms(display_text)
    src_set = extract_nums_units(req.source)
    tgt_set = extract_nums_units(analysis_text)
    missing = sorted(src_set - tgt_set)
    extra = sorted(tgt_set - src_set)
    warn = ""
    if missing:
        warn += "摘要檢查：缺 " + ", ".join(missing)
    if extra:
        warn += ("\n" if warn else "") + "摘要檢查：多 " + ", ".join(extra)
    return {"summary": display_text, "warn": warn}


@app.post("/pipeline")
def pipeline(req: PipelineReq, request: Request, x_api_key: str = Header(default=None)):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    t_model = req.translator_model or MODEL_TRANS_DEFAULT
    s_model = req.summarizer_model or MODEL_SUM_DEFAULT
    mistral_trans = uses_legacy_mistral_prompt(t_model)
    mistral_sum = uses_legacy_mistral_prompt(s_model)
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
    if preserves_translation_linebreaks(t_model):
        t = raw_t.strip()
    else:
        t = untag_translated_lines(raw_t)
    t = apply_term_map(t)
    t = strip_model_header(t)
    t, warn_translation_terms = apply_translation_term_audit(req.source, t)
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
    raw_summary = trim_summary_repetitions(s)
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
    if uses_complete_clinical_summary_model(s_model):
        summary_for_analysis = finalize_complete_summary(t, s)
    else:
        summary_for_analysis = dedup_summary_lines(s)
    display_summary = raw_summary if preserves_model_summary_format(s_model) else summary_for_analysis
    summary_for_analysis = standardize_summary_terms(summary_for_analysis)
    display_summary = standardize_summary_terms(display_summary)
    structured = rule_based_structured_findings(req.source, t, "")

    src_set = extract_nums_units(req.source)
    trans_set = extract_nums_units(t)
    sum_set = extract_nums_units(summary_for_analysis)
    return {
        "translation": t,
        "summary": display_summary,
        "structured": structured,
        "warn_translation_missing": sorted(src_set - trans_set),
        "warn_translation_extra": sorted(trans_set - src_set),
        "warn_translation_terms": warn_translation_terms,
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
            mistral_trans = uses_legacy_mistral_prompt(t_model)
            mistral_sum = uses_legacy_mistral_prompt(s_model)

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

            if preserves_translation_linebreaks(t_model):
                t = raw_t.strip()
            else:
                t = untag_translated_lines(raw_t)
            t = apply_term_map(t)
            t = strip_model_header(t)
            t, warn_translation_terms = apply_translation_term_audit(req.source, t)
            src_set = extract_nums_units(req.source)
            trans_set = extract_nums_units(t)
            warn_translation_missing = sorted(src_set - trans_set)
            warn_translation_extra = sorted(trans_set - src_set)
            yield json_event(
                "phase_done",
                phase="translate",
                text=t,
                progress=48,
                warn_missing=warn_translation_missing,
                warn_extra=warn_translation_extra,
                warn_terms=warn_translation_terms,
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
                progress=54,
            )
            s = ""
            summary_loop_guarded = False
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
                    if uses_llama_complete_summary_runtime_guard(s_model) and has_summary_loop_tail(s):
                        summary_loop_guarded = True
                        break
                if done:
                    break

            s = s.strip()
            if summary_loop_guarded:
                yield json_event(
                    "status",
                    phase="summary",
                    label="偵測到摘要重複輸出，已提前整理結果",
                    progress=84,
                )
            display_summary = trim_summary_repetitions(s)
            summary_for_analysis = s
            if uses_summary_revision(s_model) and s:
                yield json_event(
                    "status",
                    phase="summary",
                    label="摘要校正與來源一致性檢查",
                    progress=84,
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
                    summary_for_analysis = revised_summary
            if uses_complete_clinical_summary_model(s_model):
                summary_for_analysis = finalize_complete_summary(t, summary_for_analysis)
            else:
                summary_for_analysis = dedup_summary_lines(summary_for_analysis)
            if preserves_model_summary_format(s_model):
                display_summary = trim_summary_repetitions(display_summary)
            else:
                display_summary = summary_for_analysis
            summary_for_analysis = standardize_summary_terms(summary_for_analysis)
            display_summary = standardize_summary_terms(display_summary)

            sum_set = extract_nums_units(summary_for_analysis)
            warn_summary_missing = sorted(trans_set - sum_set)
            warn_summary_extra = sorted(sum_set - trans_set)
            yield json_event(
                "phase_done",
                phase="summary",
                text=display_summary,
                progress=88,
                warn_missing=warn_summary_missing,
                warn_extra=warn_summary_extra,
            )

            yield json_event(
                "phase_start",
                phase="extract_json",
                label="結構化 JSON 解析中",
                progress=92,
            )
            structured = rule_based_structured_findings(req.source, t, "")
            yield json_event(
                "phase_done",
                phase="extract_json",
                structured=structured,
                progress=97,
            )

            yield json_event(
                "done",
                progress=100,
                structured=structured,
                warn_translation_missing=warn_translation_missing,
                warn_translation_extra=warn_translation_extra,
                warn_translation_terms=warn_translation_terms,
                warn_summary_missing=warn_summary_missing,
                warn_summary_extra=warn_summary_extra,
            )
        except Exception as e:
            yield json_event("error", message=str(e))

    return StreamingResponse(event_gen(), media_type="text/plain; charset=utf-8")


@app.post("/image/generate")
def image_generate(req: ImageGenerateReq, request: Request, x_api_key: str = Header(default=None)):
    if not auth_ok(request, x_api_key):
        raise HTTPException(401, "unauthorized")
    return generate_image(req)

@app.post("/login")
def login(data: LoginReq, request: Request, response: Response):
    client_id = request_client_id(request)
    retry_after = login_retry_after(client_id)
    if retry_after:
        raise HTTPException(
            429,
            "too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    if not hmac.compare_digest(data.password, UI_PASSWORD):
        retry_after = record_login_failure(client_id)
        logger.warning("Rejected login attempt from %s", client_id)
        if retry_after:
            raise HTTPException(
                429,
                "too many login attempts",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(401, "invalid credentials")

    clear_login_failures(client_id)
    exp = int(time.time()) + SESSION_HOURS * 3600
    token = make_token("user", exp)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_HOURS * 3600,
        path="/",
    )
    return {"ok": True, "exp": exp}


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    if LEGACY_COOKIE_NAME != COOKIE_NAME:
        response.delete_cookie(LEGACY_COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def ui(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and parse_token(token):
        return templates.TemplateResponse(request=request, name="ui.html")
    return templates.TemplateResponse(request=request, name="login.html")
