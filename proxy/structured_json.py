# Structured findings extraction helpers for CardioLLM.
import json
import os
import re

from terminology import build_terminology_context


PART_LABELS = {
    "AO": "主動脈",
    "PA": "肺動脈",
    "LA": "左心房",
    "RA": "右心房",
    "LV": "左心室",
    "RV": "右心室",
}

CONDITION_VALUES = {
    "dilatation",
    "hypertrophy",
    "stenosis",
    "regurgitation",
    "dysfunction",
    "pressure_elevation",
    "aneurysm",
    "hypokinesia",
    "normal",
    "other",
}

SEVERITY_VALUES = {"trace", "mild", "moderate", "severe", "unknown"}
STATUS_VALUES = {"present", "absent", "uncertain"}

STRUCTURED_FINDINGS_PROMPT_TEMPLATE = """### Instruction:
你是一個心臟超音波報告結構化解析器。請只根據下列原始報告、中文翻譯與臨床摘要，輸出單一 JSON 物件。
嚴格規則：
1. 只能輸出 JSON，不可輸出 Markdown、說明文字或程式碼區塊。
2. 不可新增輸入中沒有明確出現的診斷、嚴重度、數值或解剖位置。
3. 若不確定嚴重度，severity 使用 "unknown"；若不確定是否存在，status 使用 "uncertain"。
4. findings 只納入與心臟圖或繪圖提示有關的重點 finding；不要列出所有正常項目。
5. part 僅限：AO, PA, LA, RA, LV, RV。若 finding 屬於瓣膜或其他位置但可明確對應到以上心腔/大血管，才填入最接近 part；否則略過或放入 overall.summary。
6. condition 僅限：dilatation, hypertrophy, stenosis, regurgitation, dysfunction, pressure_elevation, aneurysm, hypokinesia, normal, other。
7. severity 僅限：trace, mild, moderate, severe, unknown。
8. status 僅限：present, absent, uncertain。
9. confidence 介於 0 到 1。
10. measurements 僅放重要且原文/翻譯有明確數值的項目，例如 LVEF, LVIDd, LA size, PASP, TRPG, E/E'。
11. 若下方 Terminology RAG 有命中術語，請用其標準中文與限制規則；Terminology RAG 不是原文，不可當成報告 finding；尤其 measurement 類術語不可自行升級成診斷。

{terminology_context}

請輸出格式：
{
  "version": "1.0",
  "findings": [
    {
      "part": "LA",
      "part_name": "左心房",
      "condition": "dilatation",
      "severity": "mild",
      "status": "present",
      "evidence": "mild LA enlargement",
      "confidence": 0.85,
      "visual_action": "highlight"
    }
  ],
  "measurements": [
    {
      "name": "LVEF",
      "value": 62,
      "unit": "%",
      "interpretation": "normal"
    }
  ],
  "overall": {
    "summary": "...",
    "has_abnormality": true
  }
}

### Input:
原始報告：
{source_text}

中文翻譯：
{translation_text}

臨床摘要：
{summary_text}

### Response:
"""


def build_structured_findings_prompt(source_text: str, translation_text: str, summary_text: str) -> str:
    terminology_context = ""
    if os.environ.get("TERM_RAG_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}:
        terminology_context = build_terminology_context(
            source_text or "",
            translation_text or "",
            summary_text or "",
            max_terms=14,
        )
        if terminology_context:
            terminology_context = (
                "### Terminology RAG / 字庫約束（非原文，不可輸出）:\n"
                "以下內容只作為術語標準化與安全限制；請勿把本段當成報告 finding。\n"
                + terminology_context
            )
    return (
        STRUCTURED_FINDINGS_PROMPT_TEMPLATE
        .replace("{terminology_context}", terminology_context)
        .replace("{source_text}", (source_text or "").strip())
        .replace("{translation_text}", (translation_text or "").strip())
        .replace("{summary_text}", (summary_text or "").strip())
    )


def extract_json_object(text: str) -> dict:
    if not text:
        raise ValueError("empty structured JSON response")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found in structured response")
    return json.loads(cleaned[start : end + 1])


PART_PATTERNS = {
    "AO": re.compile(r"主動脈根部|升主動脈|主動脈|aortic\s+root|ascending\s+aorta|aorta|\bao\b", re.I),
    "PA": re.compile(r"肺動脈主幹|肺動脈幹|肺動脈|pulmonary\s+(?:artery|trunk)|\bpa\b", re.I),
    "LA": re.compile(r"左心房|left\s+atri(?:um|al)|\bla\b", re.I),
    "RA": re.compile(r"右心房|right\s+atri(?:um|al)|\bra\b", re.I),
    "LV": re.compile(r"左心室|left\s+ventric(?:le|ular)|\blv\b|\blvef\b|\blvh\b", re.I),
    "RV": re.compile(r"右心室|right\s+ventric(?:le|ular)|\brv\b", re.I),
}

CONDITION_PATTERNS = [
    ("dilatation", re.compile(r"擴大|擴張|dilat|enlarg", re.I)),
    ("hypertrophy", re.compile(r"肥厚|肥大|hypertroph|thicken|thick", re.I)),
    ("stenosis", re.compile(r"狹窄|stenosis|stenotic", re.I)),
    ("regurgitation", re.compile(r"逆流|regurg", re.I)),
    ("dysfunction", re.compile(r"功能不全|功能異常|dysfunction|impaired", re.I)),
    ("pressure_elevation", re.compile(r"肺高壓|壓力升高|壓力上升|高壓|hypertension|pressure\s+elevat", re.I)),
    ("aneurysm", re.compile(r"動脈瘤|aneurysm", re.I)),
    ("hypokinesia", re.compile(r"運動減弱|運動異常|hypokine|akine|wall\s+motion", re.I)),
]

SEVERITY_PATTERNS = [
    ("severe", re.compile(r"重度|嚴重|severe", re.I)),
    ("moderate", re.compile(r"中度|moderate", re.I)),
    ("mild", re.compile(r"輕度|mild", re.I)),
    ("trace", re.compile(r"極輕度|微量|少量|trace|trivial", re.I)),
]

MEASUREMENT_RE = re.compile(
    r"\b(LVEF|EF|PASP|TRPG|E/E'?|LVIDd|LVIDs|IVSd|LVPWd|LA)\b\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(%|％|mmHg|mm|cm)?",
    re.I,
)


def split_finding_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<!\d)[\n。；;.!?！？，,、]+(?!\d)", text)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def detect_severity(sentence: str) -> str:
    for severity, pattern in SEVERITY_PATTERNS:
        if pattern.search(sentence):
            return severity
    return "unknown"


def rule_based_structured_findings(
    source_text: str,
    translation_text: str,
    summary_text: str,
    error: str | None = None,
) -> dict:
    text = "\n".join(part for part in [source_text, translation_text, summary_text] if part)
    findings = []
    seen: set[tuple[str, str, str]] = set()

    for sentence in split_finding_sentences(text):
        matched_parts = [part for part, pattern in PART_PATTERNS.items() if pattern.search(sentence)]
        if not matched_parts:
            continue
        matched_conditions = [condition for condition, pattern in CONDITION_PATTERNS if pattern.search(sentence)]
        if not matched_conditions:
            continue
        severity = detect_severity(sentence)
        evidence = sentence[:240]
        for part in matched_parts:
            for condition in matched_conditions:
                key = (part, condition, severity)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "part": part,
                        "part_name": PART_LABELS[part],
                        "condition": condition,
                        "severity": severity,
                        "status": "present",
                        "evidence": evidence,
                        "confidence": 0.62,
                        "visual_action": "highlight",
                    }
                )
                if len(findings) >= 18:
                    break
            if len(findings) >= 18:
                break
        if len(findings) >= 18:
            break

    measurements = []
    seen_measurements: set[tuple[str, str, str]] = set()
    for m in MEASUREMENT_RE.finditer(text):
        key = (m.group(1).upper(), m.group(2), m.group(3) or "")
        if key in seen_measurements:
            continue
        seen_measurements.add(key)
        measurements.append(
            {
                "name": m.group(1).upper(),
                "value": float(m.group(2)) if "." in m.group(2) else int(m.group(2)),
                "unit": m.group(3) or "",
                "interpretation": "",
            }
        )
        if len(measurements) >= 12:
            break

    summary = (summary_text or translation_text or source_text or "").strip()
    if len(summary) > 360:
        summary = summary[:360].rstrip() + "..."

    structured = {
        "version": "1.0",
        "findings": findings,
        "measurements": measurements,
        "overall": {
            "summary": summary,
            "has_abnormality": bool(findings),
        },
        "source": "rule_fallback",
    }
    if error:
        structured["error"] = error
    return structured


def normalize_structured_findings(data: dict, fallback_summary: str = "") -> dict:
    if not isinstance(data, dict):
        data = {}

    normalized = {
        "version": str(data.get("version") or "1.0"),
        "findings": [],
        "measurements": [],
        "overall": {},
    }

    for item in data.get("findings") or []:
        if not isinstance(item, dict):
            continue
        part = str(item.get("part") or "").upper().strip()
        if part not in PART_LABELS:
            continue
        condition = str(item.get("condition") or "other").strip().lower()
        if condition not in CONDITION_VALUES:
            condition = "other"
        severity = str(item.get("severity") or "unknown").strip().lower()
        if severity not in SEVERITY_VALUES:
            severity = "unknown"
        status = str(item.get("status") or "present").strip().lower()
        if status not in STATUS_VALUES:
            status = "uncertain"
        try:
            confidence = float(item.get("confidence", 0.5))
        except Exception:
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        evidence = str(item.get("evidence") or "").strip()
        normalized["findings"].append(
            {
                "part": part,
                "part_name": PART_LABELS[part],
                "condition": condition,
                "severity": severity,
                "status": status,
                "evidence": evidence[:240],
                "confidence": round(confidence, 2),
                "visual_action": str(item.get("visual_action") or "highlight").strip() or "highlight",
            }
        )

    for item in data.get("measurements") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        normalized["measurements"].append(
            {
                "name": name[:40],
                "value": item.get("value"),
                "unit": str(item.get("unit") or "").strip()[:20],
                "interpretation": str(item.get("interpretation") or "").strip()[:80],
            }
        )

    overall = data.get("overall") if isinstance(data.get("overall"), dict) else {}
    normalized["overall"] = {
        "summary": str(overall.get("summary") or fallback_summary or "").strip()[:500],
        "has_abnormality": bool(overall.get("has_abnormality", bool(normalized["findings"]))),
    }
    return normalized
