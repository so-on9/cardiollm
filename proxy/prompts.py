# Prompt templates and LLM text post-processing helpers for CardioLLM.
from __future__ import annotations

import os
import re

from terminology import apply_term_replacements, build_terminology_context


ECHO_POLICY_PROMPT_TEXT = (
    "心臟超音波專用安全規則："
    "1. 原文若寫 suggest/suspicious/R/O/possible，中文必須保留「提示、懷疑、疑似、可能」等不確定語氣，不可改成確診語氣。"
    "2. `SUGGEST PULMONARY HYPERTENSION` 應翻成「提示/懷疑肺高壓」，不可自行升級成「有重度肺高壓」。"
    "3. `TR WITH PEAK/MEAN SYSTOLIC PG/PRESSURE GRADIENT` 應保守寫成「三尖瓣逆流訊號之峰值/平均收縮期壓差」，不可直接改寫成「肺動脈收縮壓峰值/平均值」。"
    "4. `RA AREA` 只翻成「右心房面積」並保留數值，不可自行補成「右心房擴大」或右心功能異常，除非原文另有 chamber dilatation/enlargement 等明確描述。"
    "5. `TAPSE` 是右心室縱向收縮功能指標；若需解釋，只能寫「提示右心室縱向收縮功能偏低/保留」，不可單靠 TAPSE 推論整體右心功能或病情嚴重度。"
    "6. `LVEF 50-54%` 應優先使用「邊緣偏低/低正常」等保守語氣，不宜直接寫成明確收縮功能障礙。"
    "7. 術後瓣膜若仍有逆流，不可只因跨瓣壓差低就寫成瓣膜功能尚可；需同時保留逆流嚴重度。"
)

BASELINE150_LEGACY_ECHO_POLICY_PROMPT_TEXT = (
    "特別注意不確定語氣：原文若出現 SUGGEST、SUSPECT、SUSPICIOUS、POSSIBLE、PROBABLE、"
    "LIKELY、CANNOT EXCLUDE、RULE OUT、QUERY 或 QUESTIONABLE，不可翻成『有』、『確定』或肯定診斷；"
    "應保留為『提示』、『懷疑』、『疑似』、『可能』、『無法排除』或『需排除』等不確定語氣。"
    "例如 SUGGEST PULMONARY HYPERTENSION 應翻成『提示肺動脈高壓』或『懷疑肺動脈高壓』，"
    "不可翻成『有肺動脈高壓』。"
    "若原文已明確寫 MILD/MODERATE/SEVERE PULMONARY HYPERTENSION 或其他確定結論，才可使用相對肯定語氣。"
)

BASELINE150_LEGACY_TRANSLATION_SUFFIX = (
    "請嚴格依照原文順序逐項翻譯為繁體中文，"
    "不可摘要、不可重組句子、不可補充推論、"
    "不可省略數值、單位、嚴重度、解剖位置或檢查結論；"
    "原文中每個以逗號、句號或分號分隔的資訊片段都必須在譯文中對應一次；"
    "括號內尺寸、E/E'、Qp/Qs、PG、GLS、肺動脈高壓、肺動脈主幹、"
    "心包腔、側壁/外側壁/下外側壁、近端1/2、完全無收縮、"
    "極輕度、輕度至中度、極少量等描述必須完整保留；"
    f"{BASELINE150_LEGACY_ECHO_POLICY_PROMPT_TEXT}"
)


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


def collapse_duplicate_lines_within_sections(text: str) -> str:
    output: list[str] = []
    seen_in_section: set[str] = set()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            output.append(line)
            continue

        is_heading = (
            stripped.startswith("【")
            or bool(re.match(r"^[一二三四五六七八九十]+[、.．]", stripped))
        )
        if is_heading:
            seen_in_section = set()
            output.append(line.rstrip())
            continue

        key = re.sub(r"\s+", "", stripped)
        key = re.sub(r"[，,。；;：:、]$", "", key)
        if key in seen_in_section:
            continue
        seen_in_section.add(key)
        output.append(line.rstrip())

    return "\n".join(output).strip()


def strip_source_check_section(summary: str) -> str:
    if not summary:
        return summary

    stop_markers = (
        "原文資訊核對",
        "原文資訊對照",
        "資訊對照",
        "未自然涵蓋的數字",
        "尚未自然涵蓋",
    )
    kept: list[str] = []
    skipping = False
    for line in summary.splitlines():
        stripped = line.strip()
        if any(marker in stripped for marker in stop_markers):
            skipping = True
            continue
        if skipping:
            is_heading = (
                stripped.startswith("【")
                or bool(re.match(r"^[一二三四五六七八九十]+[、.．]", stripped))
            )
            if is_heading and not any(marker in stripped for marker in stop_markers):
                skipping = False
            else:
                continue
        kept.append(line)
    return "\n".join(kept).strip()


def strip_unsupported_advice_section(source: str, summary: str) -> str:
    if not summary:
        return summary

    source_has_advice = bool(re.search(r"建議|追蹤|治療建議|follow[- ]?up|recommend", source or "", re.IGNORECASE))
    if source_has_advice:
        return summary

    kept: list[str] = []
    skipping = False
    for line in summary.splitlines():
        stripped = line.strip()
        is_heading = stripped.startswith("【") and "】" in stripped
        if is_heading and "建議" in stripped:
            skipping = True
            continue
        if skipping and is_heading:
            skipping = False
        if skipping:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def append_source_number_check(source: str, summary: str) -> str:
    if not source or not summary or "【原文資訊核對】" in summary:
        return summary

    missing = sorted(
        extract_nums_units(source) - extract_nums_units(summary),
        key=lambda item: (float(item) if re.fullmatch(r"\d+(?:\.\d+)?", item) else 10**9, item),
    )
    if not missing:
        return summary

    return (
        summary.rstrip()
        + "\n\n【原文資訊核對】\n"
        + "- 原文尚未呈現數值："
        + "、".join(missing)
    )


SUMMARY_HEADING_MAP = (
    ("瓣膜", "【瓣膜結構與功能評估】"),
    ("壓力", "【壓力與尺寸評估】"),
    ("肺循環", "【壓力與尺寸評估】"),
    ("尺寸", "【壓力與尺寸評估】"),
    ("運動", "【心臟運動與收縮功能評估】"),
    ("收縮", "【心臟運動與收縮功能評估】"),
    ("整體", "【結構與功能評估結論】"),
    ("結論", "【結構與功能評估結論】"),
    ("心臟結構", "【心臟結構與功能評估】"),
    ("心臟功能", "【心臟結構與功能評估】"),
)


def normalize_complete_summary_headings(summary: str) -> str:
    normalized_lines: list[str] = []
    for line in summary.splitlines():
        stripped = line.strip()
        heading_text = stripped
        heading_text = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", heading_text)
        heading_text = heading_text.strip()

        if heading_text.startswith("【") and "】" in heading_text:
            normalized_lines.append(heading_text)
            continue

        if len(heading_text) <= 18 and not re.search(r"[，,。；;：:]", heading_text):
            mapped = None
            for keyword, heading in SUMMARY_HEADING_MAP:
                if keyword in heading_text:
                    mapped = heading
                    break
            if mapped:
                normalized_lines.append(mapped)
                continue

        normalized_lines.append(line.rstrip())
    return "\n".join(normalized_lines).strip()


def _summary_repeat_key(text: str) -> str:
    return re.sub(r"[\s，,。；;：:、.．]+", "", (text or "").strip())


def has_summary_loop_tail(text: str) -> bool:
    key_text = _summary_repeat_key(text)
    if len(key_text) < 240:
        return False

    tail = key_text[-720:]
    for size in (36, 48, 64, 96, 128, 160):
        if len(tail) < size * 3:
            continue
        last = tail[-size:]
        prev = tail[-size * 2 : -size]
        prev2 = tail[-size * 3 : -size * 2]
        if last == prev and len(last) >= 36:
            return True
        if last == prev == prev2 and len(last) >= 24:
            return True

    lines = [_summary_repeat_key(line) for line in text.splitlines() if _summary_repeat_key(line)]
    recent = [line for line in lines[-10:] if len(line) >= 8]
    return any(recent.count(line) >= 3 for line in set(recent))


def trim_summary_repetitions(text: str) -> str:
    if not text:
        return text

    def key(line: str) -> str:
        return _summary_repeat_key(line)

    lines = [line.rstrip() for line in text.splitlines()]

    compact: list[str] = []
    last_key = ""
    for line in lines:
        current_key = key(line)
        if current_key and current_key == last_key and len(current_key) >= 8:
            continue
        compact.append(line)
        if current_key:
            last_key = current_key

    lines = compact
    for block_size in range(1, 9):
        changed = True
        while changed and len(lines) >= block_size * 2:
            changed = False
            last = lines[-block_size:]
            prev = lines[-block_size * 2:-block_size]
            last_key = "".join(key(line) for line in last)
            prev_key = "".join(key(line) for line in prev)
            if last_key and last_key == prev_key and len(last_key) >= 24:
                del lines[-block_size:]
                changed = True

    return "\n".join(lines).strip()


def collapse_repeated_lines_within_sections(summary: str) -> str:
    output: list[str] = []
    seen_in_section: set[str] = set()
    last_blank = False

    for line in summary.splitlines():
        stripped = line.strip()
        if not stripped:
            if output and not last_blank:
                output.append("")
            last_blank = True
            continue

        last_blank = False
        is_heading = stripped.startswith("【") and "】" in stripped
        if is_heading:
            if output and output[-1].strip() == stripped:
                continue
            output.append(stripped)
            seen_in_section = set()
            continue

        key = re.sub(r"\s+", "", stripped)
        key = re.sub(r"[，,。；;：:、]$", "", key)
        if key in seen_in_section:
            continue
        seen_in_section.add(key)
        output.append(line.rstrip())

    return "\n".join(output).strip()


def finalize_complete_summary(source: str, summary: str) -> str:
    # Keep complete-summary output close to the training/evaluation prompt distribution.
    # Only remove source-check appendices and exact duplicate lines inside the same section.
    summary = strip_source_check_section(summary)
    summary = collapse_duplicate_lines_within_sections(summary)
    return trim_summary_repetitions(summary)


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


def env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def term_rag_enabled() -> bool:
    return env_flag("TERM_RAG_ENABLED")


def summary_rag_enabled() -> bool:
    return env_flag("SUMMARY_RAG_ENABLED")


def build_term_rag_block(text: str, glossary=None, max_terms: int = 14, enabled: bool | None = None) -> str:
    if enabled is None:
        enabled = term_rag_enabled()
    if not enabled:
        return ""
    lines: list[str] = []
    term_context = build_terminology_context(text or "", max_terms=max_terms)
    if term_context:
        lines.append(term_context)
    if glossary:
        manual = []
        for pair in glossary:
            src = getattr(pair, "src", "")
            tgt = getattr(pair, "tgt", "")
            if src and tgt:
                manual.append(f"- User glossary: {src} -> {tgt}")
        if manual:
            lines.append("User-provided glossary:\n" + "\n".join(manual))
    if not lines:
        return ""
    return (
        "\n\n### Terminology RAG / 字庫約束（非原文，不可翻譯或輸出）:\n"
        "以下內容只作為術語標準化與安全限制；請勿把本段當成報告內容。\n"
        + "\n".join(lines)
        + "\n"
    )


def build_summary_term_rag_block(text: str) -> str:
    return build_term_rag_block(text, max_terms=10, enabled=summary_rag_enabled())


def apply_term_map(text: str) -> str:
    return apply_term_replacements(text)



def build_mistral_v01_translate_prompt(req) -> str:
    instruction = (
        "請將以下心臟超音波報告逐行翻譯為臨床風格的繁體中文，"
        "保持原文順序、數值、單位、嚴重度與解剖位置，不可摘要、不可新增推論。"
    )
    instruction += build_term_rag_block(req.source or "", getattr(req, "glossary", None))
    body = req.source or ""
    return mistral_inst_prompt(instruction, body)

def build_mistral_v01_summary_prompt(req: SummarizeReq) -> str:
    instruction = (
        "你是一位資深心臟科醫師。請根據以下「中文心臟超音波報告」，撰寫一份符合臨床醫師風格的完整解讀，"
        "內容請整理成有條理的段落，至少包含：\n"
        "1. 心臟結構與功能（心房、心室、左心室射出分率等）。\n"
        "2. 主要異常發現與可能臨床意義。\n"
        "3. 綜合臨床建議與後續追蹤建議。\n"
        "請不要逐字重述原始報告，不要重複同一段內容兩次，也不要加入醫師姓名或與報告無關的資訊。"
    )
    instruction += build_summary_term_rag_block(req.source or "")
    body = req.source or ""
    return mistral_inst_prompt(instruction, body)


def build_legacy_translate_prompt(req: TranslateReq) -> str:
    instruction = (
        "請將以下心臟超音波報告翻譯為臨床風格的繁體中文，並保持語氣一致且不加入推論。"
    )
    body = req.source.strip()
    term_block = build_term_rag_block(req.source, getattr(req, "glossary", None))

    return (
        "Below is an instruction that describes a task, paired with an input that provides further context. "
        "Write a response that appropriately completes the request.\n\n"
        "### Instruction:\n"
        f"{instruction}{term_block}\n\n"
        "### Input:\n"
        f"{body}\n\n"
        "### Response:\n"
    )


def build_strict_translate_prompt(req: TranslateReq) -> str:
    instruction = (
        "請將以下心臟超音波報告翻譯為臨床風格的繁體中文，並保持語氣一致且不加入推論。"
        f"{BASELINE150_LEGACY_TRANSLATION_SUFFIX}"
    )
    body = req.source.strip()
    term_block = build_term_rag_block(req.source, getattr(req, "glossary", None))

    return (
        "### Instruction:\n"
        f"{instruction}{term_block}\n\n"
        "### Input:\n"
        f"{body}\n\n"
        "### Response:\n"
    )


def build_translategemma_translate_prompt(req: TranslateReq) -> str:
    instruction = (
        "請將以下心臟超音波報告翻譯為臨床風格的繁體中文，並保持語氣一致且不加入推論。"
        f"{BASELINE150_LEGACY_TRANSLATION_SUFFIX}"
    )
    user_text = (
        f"任務：{instruction}{build_term_rag_block(req.source, getattr(req, 'glossary', None))}\n\n"
        "請只輸出繁體中文譯文，不要加入說明、標題或摘要。\n\n"
        "英文心臟超音波報告：\n"
        f"{req.source.strip()}"
    )

    return (
        "<start_of_turn>user\n"
        "You are a professional English (en) to Chinese (zh-TW) translator. "
        "Your goal is to accurately convey the meaning and nuances of the original English text "
        "while adhering to Chinese grammar, vocabulary, and cultural sensitivities.\n"
        "Produce only the Chinese translation, without any additional explanations or commentary. "
        "Please translate the following English text into Chinese:\n\n\n"
        f"{user_text}"
        "<end_of_turn>\n"
        "<start_of_turn>model\n"
    )


MINISTRAL3_TRANSLATION_SYSTEM_PROMPT = (
    "You are a professional English-to-Traditional-Chinese medical translator. "
    "Translate echocardiography reports faithfully. Keep every number, unit, "
    "severity, anatomy term, uncertainty marker, and original finding. Do not "
    "summarize, infer, explain, or add diagnoses that are not present."
)


MINISTRAL3_SUMMARY_SYSTEM_PROMPT = (
    "You are a professional cardiology assistant. "
    "Generate faithful Traditional-Chinese echocardiography clinical summaries. "
    "Preserve every important number, unit, severity, anatomy term, valve finding, "
    "chamber size, functional assessment, pressure gradient, and source-supported conclusion. "
    "Do not invent unsupported diagnoses, values, treatments, or patient-specific instructions."
)


def build_ministral3_translate_prompt(req: TranslateReq) -> str:
    instruction = (
        "請將以下心臟超音波報告翻譯為臨床風格的繁體中文，並保持語氣一致且不加入推論。"
        f"{BASELINE150_LEGACY_TRANSLATION_SUFFIX}"
    )
    user_text = (
        f"任務：{instruction}{build_term_rag_block(req.source, getattr(req, 'glossary', None))}\n\n"
        "請只輸出繁體中文譯文，不要加入說明、標題或摘要。\n\n"
        "英文心臟超音波報告：\n"
        f"{req.source.strip()}"
    )
    return (
        "<s>[SYSTEM_PROMPT]"
        f"{MINISTRAL3_TRANSLATION_SYSTEM_PROMPT}"
        "[/SYSTEM_PROMPT][INST]"
        f"{user_text}"
        "[/INST]"
    )


def preserves_translation_linebreaks(model_name: str) -> bool:
    return "ministral3-3b-instruct-translator" in (model_name or "").lower()


def build_translate_prompt(req: TranslateReq, model_name: str) -> str:
    model_name = model_name or ""
    model_name_lower = model_name.lower()
    if "translategemma-4b-it" in model_name_lower:
        return build_translategemma_translate_prompt(req)
    if "ministral3-3b-instruct-translator" in model_name_lower:
        return build_ministral3_translate_prompt(req)

    # The deployed "LLaMA 3.2 Instruct" option maps to translator-legacy-v3-cp140.
    # Keep cp140 inference aligned with the baseline150-legacy-v3 training prompt;
    # baseline150 Base150 also uses this stricter report-translation prompt.
    if (
        "llama-3.2-3b-instruct-translator-deploy" in model_name
        or "llama-3.2-3b-instruct-translator-legacy-v3-cp140" in model_name
        or "llama-3.2-3b-instruct-translator-baseline150" in model_name
        or "ministral3-3b-instruct-translator-cp220" in model_name_lower
    ):
        return build_strict_translate_prompt(req)
    return build_legacy_translate_prompt(req)


CLINICAL_SUMMARY_SUFFIX = (
    "請輸出忠實、結構化、臨床導向的繁體中文心臟超音波摘要；"
    "只整理原文有依據的心臟結構、功能、主要異常、數值、器官、瓣膜與嚴重度；"
    "可使用精簡分節與條列，但不可改寫成病人衛教、白話解說、正常值比較、追蹤建議或治療建議；"
    "不可新增原文沒有的診斷、數值、器官、嚴重度、病理生理推論或功能判讀；"
    "若原文只有數值而無明確結論，請保留數值並維持保守描述，不可自行升級成確定疾病診斷；"
    "若原文有肺高壓、瓣膜逆流/狹窄、心腔擴大/肥厚、收縮/舒張功能異常、壁運動異常或心包積液，需優先保留；"
    "避免使用箭頭推理符號。"
)


COMPLETE_EXPLANATION_SUFFIX = (
    "請輸出資訊完整、結構化、臨床導向的繁體中文心臟超音波解釋摘要；"
    "第一優先是完整保留原文所有重要資訊、數值、單位、嚴重度、器官、瓣膜、心腔、功能、壓力梯度與關鍵檢查結論；"
    "可補充有原文依據的病情解讀，並可提供保守的一般性建議；"
    "建議必須以回診、追蹤、由心臟科醫師結合症狀與病史評估、必要時進一步檢查等一般方向為限；"
    "不可新增原文沒有支持的病人特定診斷、嚴重度、數值、器官異常、治療指令、用藥或侵入性處置建議；"
    "若原文只有數值而無明確結論，請保留數值並維持保守描述，不可自行升級成確定疾病診斷；"
    f"{ECHO_POLICY_PROMPT_TEXT}"
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
請檢查下列完整臨床解釋摘要草稿是否完整涵蓋原文中已明確出現的所有重要資訊片段、數值、單位、嚴重度、器官/瓣膜結構、心腔大小、心臟功能、壓力梯度與關鍵檢查結論。若有遺漏，請輸出修正後的完整繁體中文臨床解釋摘要。
重要原則：
1. 第一優先是補回原文已有的重要資訊與數值，不要為了簡短而壓縮或省略；每個原文數字、百分比、尺寸、壓力梯度與縮寫指標都要逐項覆核。
2. 若草稿出現原文沒有的數值、正常值比較、嚴重度、器官異常或病人特定診斷，請刪除；可保留或補充有原文依據的病情解讀。
3. 可提供保守一般建議，例如由心臟科醫師結合症狀與病史評估、追蹤心臟超音波、必要時進一步檢查；不可提供個人化治療指令、用藥或侵入性處置建議。
4. 若原文只有數值而沒有明確判讀，請保留數值並維持保守描述，不可自行升級成確定疾病診斷。
5. 不要限制總句數；只要資訊有臨床重要性或包含原文數字，就應保留。
6. 不要輸出「原文資訊核對」、「未自然涵蓋的數字」、「資訊對照」或任何缺漏清單小節；若發現缺漏，請直接補回對應的臨床摘要正文段落。
7. {echo_policy}
{term_block}

### Input:
原文：
{input_text}

草稿：
{draft_text}

### Response:
"""



def build_llama_summary_prompt(req: SummarizeReq, model_name: str = "") -> str:
    style = (req.style or "").strip().lower()
    if uses_complete_clinical_summary_model(model_name):
        instruction = f"請根據心臟超音波中文報告生成完整臨床解釋摘要。{COMPLETE_EXPLANATION_SUFFIX}"
    else:
        instruction = "請摘要以下心臟超音波報告"
        if "academic" in style:
            instruction = f"{instruction}。{ACADEMIC_SUMMARY_SUFFIX}"
        elif "patient" in style or "friendly" in style or "simple" in style:
            instruction = f"{instruction}。{PATIENT_SUMMARY_SUFFIX}"
        else:
            instruction = f"{instruction}。{CLINICAL_SUMMARY_SUFFIX}"

    return (
        "### Instruction:\n"
        f"{instruction}{build_summary_term_rag_block(req.source)}\n\n"
        "### Input:\n"
        f"{req.source.strip()}\n\n"
        "### Response:\n"
    )


def build_summary_revision_prompt(input_text: str, draft_text: str) -> str:
    return SUMMARY_REVISION_PROMPT_TEMPLATE.format(
        input_text=input_text.strip(),
        draft_text=draft_text.strip(),
        echo_policy=ECHO_POLICY_PROMPT_TEXT,
        term_block=build_summary_term_rag_block(input_text + "\n" + draft_text),
    )


def build_translategemma_summary_prompt(req: SummarizeReq, model_name: str = "") -> str:
    user_text = build_llama_summary_prompt(req, model_name).strip()
    return (
        "<start_of_turn>user\n"
        f"{user_text}"
        "<end_of_turn>\n"
        "<start_of_turn>model\n"
    )


def build_ministral3_summary_prompt(req: SummarizeReq, model_name: str = "") -> str:
    user_text = build_llama_summary_prompt(req, model_name).strip()
    return (
        "<s>[SYSTEM_PROMPT]"
        f"{MINISTRAL3_SUMMARY_SYSTEM_PROMPT}"
        "[/SYSTEM_PROMPT][INST]"
        f"{user_text}"
        "[/INST]"
    )


def uses_complete_clinical_summary_model(model_name: str) -> bool:
    model_name = model_name or ""
    return (
        "llama-3.2-3b-instruct-summarizer-clinical-v4" in model_name
        or "llama-3.2-3b-instruct-summarizer-complete-clinical-v5" in model_name
        or "translategemma-4b-it-summary-complete-explanation" in model_name
        or "translategemma-4b-it-summarizer-complete-explanation" in model_name
        or "ministral3-3b-instruct-summarizer-complete-explanation" in model_name
    )

def preserves_model_summary_format(model_name: str) -> bool:
    model_name = (model_name or "").lower()
    return (
        "translategemma-4b-it" in model_name
        or "ministral3-3b-instruct-summarizer" in model_name
    )


def uses_summary_revision(model_name: str) -> bool:
    if preserves_model_summary_format(model_name):
        return False
    return uses_complete_clinical_summary_model(model_name)


def build_summary_prompt(req: SummarizeReq, model_name: str = "") -> str:
    model_name_lower = (model_name or "").lower()
    if "translategemma-4b-it" in model_name_lower:
        return build_translategemma_summary_prompt(req, model_name)
    if "ministral3-3b-instruct-summarizer" in model_name_lower:
        return build_ministral3_summary_prompt(req, model_name)

    if uses_complete_clinical_summary_model(model_name):
        return build_llama_summary_prompt(req, model_name)

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
        f"{build_summary_term_rag_block(req.source)}"
        "=== 心臟超音波報告 ===\n"
        f"{req.source.strip()}"
        "\n=== 結束 ==="
    )


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
    return f"{base}{tone_hint}{build_term_rag_block(english_text)}=== English report ===\n{english_text.strip()}\n=== End ===\n"


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
    return f"{base}{style_hint}\n\n{build_summary_term_rag_block(chinese_text)}=== 心臟超音波報告 ===\n{chinese_text.strip()}\n=== 結束 ===\nPlease output only the structured summary text.\n"
