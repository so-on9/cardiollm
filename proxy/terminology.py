# Lightweight terminology retrieval for echocardiography reports.
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class TermEntry:
    key: str
    zh: str
    aliases: tuple[str, ...]
    category: str
    rules: tuple[str, ...] = ()


TERM_ENTRIES: tuple[TermEntry, ...] = (
    TermEntry(
        key="MR",
        zh="二尖瓣逆流",
        aliases=("MR", "mitral regurgitation"),
        category="valve_regurgitation",
        rules=("保留嚴重度，例如 mild/moderate/severe。",),
    ),
    TermEntry(
        key="TR",
        zh="三尖瓣逆流",
        aliases=("TR", "tricuspid regurgitation"),
        category="valve_regurgitation",
        rules=("保留嚴重度；若只寫 TR 不可自行推論肺高壓。",),
    ),
    TermEntry(
        key="AR",
        zh="主動脈瓣逆流",
        aliases=("AR", "aortic regurgitation"),
        category="valve_regurgitation",
        rules=("保留嚴重度。",),
    ),
    TermEntry(
        key="PR",
        zh="肺動脈瓣逆流",
        aliases=("PR", "pulmonary regurgitation"),
        category="valve_regurgitation",
        rules=("保留嚴重度。",),
    ),
    TermEntry(
        key="AS",
        zh="主動脈瓣狹窄",
        aliases=("AS", "aortic stenosis"),
        category="valve_stenosis",
        rules=("AS 在心臟超音波語境通常指 aortic stenosis；保留嚴重度與壓差。",),
    ),
    TermEntry(
        key="MS",
        zh="二尖瓣狹窄",
        aliases=("MS", "mitral stenosis"),
        category="valve_stenosis",
        rules=("保留嚴重度與瓣口/壓差資訊。",),
    ),
    TermEntry(
        key="TS",
        zh="三尖瓣狹窄",
        aliases=("TS", "tricuspid stenosis"),
        category="valve_stenosis",
        rules=("不可與 TR 三尖瓣逆流混用。",),
    ),
    TermEntry(
        key="PS",
        zh="肺動脈瓣狹窄",
        aliases=("PS", "pulmonary stenosis"),
        category="valve_stenosis",
        rules=("不可與 PR 肺動脈瓣逆流混用。",),
    ),
    TermEntry(
        key="LVH",
        zh="左心室肥厚",
        aliases=("LVH", "left ventricular hypertrophy"),
        category="chamber_hypertrophy",
        rules=("hypertrophy 翻為肥厚；不要誤寫成心室擴大。",),
    ),
    TermEntry(
        key="RVH",
        zh="右心室肥厚",
        aliases=("RVH", "right ventricular hypertrophy"),
        category="chamber_hypertrophy",
        rules=("hypertrophy 翻為肥厚；不要誤寫成心室擴大。",),
    ),
    TermEntry(
        key="LA dilatation",
        zh="左心房擴大",
        aliases=("LA dilatation", "LA dilation", "LA enlargement", "left atrial enlargement", "left atrium dilatation", "左心房擴大"),
        category="chamber_dilatation",
        rules=("dilatation/enlargement 在心腔語境翻為擴大。",),
    ),
    TermEntry(
        key="RA dilatation",
        zh="右心房擴大",
        aliases=("RA dilatation", "RA dilation", "RA enlargement", "right atrial enlargement", "right atrium dilatation", "右心房擴大"),
        category="chamber_dilatation",
        rules=("dilatation/enlargement 在心腔語境翻為擴大。",),
    ),
    TermEntry(
        key="LV dilatation",
        zh="左心室擴大",
        aliases=("LV dilatation", "LV dilation", "LV enlargement", "left ventricular dilatation", "left ventricular enlargement", "左心室擴大"),
        category="chamber_dilatation",
        rules=("不可與 LVH 左心室肥厚混用。",),
    ),
    TermEntry(
        key="RV dilatation",
        zh="右心室擴大",
        aliases=("RV dilatation", "RV dilation", "RV enlargement", "right ventricular dilatation", "right ventricular enlargement", "右心室擴大"),
        category="chamber_dilatation",
        rules=("不可與 RVH 右心室肥厚混用。",),
    ),
    TermEntry(
        key="aortic root dilatation",
        zh="主動脈根部擴大",
        aliases=("aortic root dilatation", "aortic root dilation", "aortic root enlargement", "主動脈根部擴大"),
        category="vessel_dilatation",
        rules=("不可簡化成單純主動脈瓣異常。",),
    ),
    TermEntry(
        key="PA trunk dilatation",
        zh="肺動脈主幹擴張",
        aliases=("PA trunk dilatation", "PA trunk dilation", "main pulmonary artery dilatation", "pulmonary artery trunk dilatation", "肺動脈主幹擴張"),
        category="vessel_dilatation",
        rules=("PA trunk 指肺動脈主幹，不是肺動脈瓣。",),
    ),
    TermEntry(
        key="RA area",
        zh="右心房面積",
        aliases=("RA area", "RA AREA", "right atrial area", "右心房面積"),
        category="measurement",
        rules=("只翻譯為右心房面積；不可自行補成右心房擴大，除非原文另有 dilatation/enlargement。",),
    ),
    TermEntry(
        key="TRPG",
        zh="三尖瓣逆流壓差",
        aliases=("TRPG", "TR PG", "TR pressure gradient", "TR peak gradient", "tricuspid regurgitation pressure gradient", "三尖瓣逆流壓差"),
        category="measurement",
        rules=("TRPG 是由三尖瓣逆流估算的壓差；不可直接寫成肺動脈收縮壓，除非原文明寫 PASP/SPAP。",),
    ),
    TermEntry(
        key="PASP",
        zh="肺動脈收縮壓",
        aliases=("PASP", "SPAP", "pulmonary artery systolic pressure", "systolic pulmonary artery pressure", "肺動脈收縮壓"),
        category="measurement",
        rules=("若原文為 suggest pulmonary hypertension，仍需保留提示/懷疑語氣。",),
    ),
    TermEntry(
        key="TAPSE",
        zh="三尖瓣環平面收縮位移",
        aliases=("TAPSE", "tricuspid annular plane systolic excursion"),
        category="measurement",
        rules=("TAPSE 是右心室縱向收縮功能指標；不可單靠 TAPSE 推論整體右心功能嚴重度。",),
    ),
    TermEntry(
        key="LVEF",
        zh="左心室射出分率",
        aliases=("LVEF", "LV EF", "left ventricular ejection fraction", "ejection fraction", "左心室射出分率"),
        category="measurement",
        rules=("保留百分比數值；50-54% 建議用邊緣偏低/低正常等保守語氣。",),
    ),
    TermEntry(
        key="E/e'",
        zh="E/e' 比值",
        aliases=("E/e'", "E/e’", "E/e ratio", "E/e prime", "E/e′"),
        category="measurement",
        rules=("保留符號與數值；不可自行新增舒張功能分級。",),
    ),
    TermEntry(
        key="ASD",
        zh="心房中隔缺損",
        aliases=("ASD", "atrial septal defect"),
        category="septal_defect",
        rules=("若原文寫 no ASD，必須保留否定。",),
    ),
    TermEntry(
        key="PFO",
        zh="卵圓孔未閉",
        aliases=("PFO", "patent foramen ovale"),
        category="septal_defect",
        rules=("若原文寫 no PFO，必須保留否定。",),
    ),
)

TERM_REPLACEMENTS = {
    "連枷樣運動": "飄動樣運動",
    "連枷樣": "飄動樣",
    "連枷運動": "飄動運動",
    "連枷": "飄動",
}

TRANSLATION_OUTPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "MR": ("二尖瓣逆流", "僧帽瓣逆流", "二尖瓣返流", "僧帽瓣返流", "mitral regurgitation", "MR"),
    "TR": ("三尖瓣逆流", "三尖瓣返流", "tricuspid regurgitation", "TR"),
    "AR": ("主動脈瓣逆流", "主動脈逆流", "主動脈瓣返流", "aortic regurgitation", "AR"),
    "PR": ("肺動脈瓣逆流", "肺動脈逆流", "肺動脈瓣返流", "pulmonary regurgitation", "PR"),
    "AS": ("主動脈瓣狹窄", "aortic stenosis", "AS"),
    "MS": ("二尖瓣狹窄", "僧帽瓣狹窄", "mitral stenosis", "MS"),
    "TS": ("三尖瓣狹窄", "tricuspid stenosis", "TS"),
    "PS": ("肺動脈瓣狹窄", "pulmonary stenosis", "PS"),
    "LVH": ("左心室肥厚", "左心室肥大", "left ventricular hypertrophy", "LVH"),
    "RVH": ("右心室肥厚", "右心室肥大", "right ventricular hypertrophy", "RVH"),
    "LA dilatation": ("左心房擴大", "左心房擴張", "left atrial enlargement", "LA enlargement"),
    "RA dilatation": ("右心房擴大", "右心房擴張", "right atrial enlargement", "RA enlargement"),
    "LV dilatation": ("左心室擴大", "左心室擴張", "left ventricular enlargement", "LV enlargement"),
    "RV dilatation": ("右心室擴大", "右心室擴張", "right ventricular enlargement", "RV enlargement"),
    "aortic root dilatation": ("主動脈根部擴大", "主動脈根部擴張", "aortic root dilatation"),
    "PA trunk dilatation": ("肺動脈主幹擴張", "肺動脈主幹擴大", "main pulmonary artery dilatation"),
    "RA area": ("右心房面積", "右心房區域", "RA area", "RA AREA"),
    "TRPG": ("三尖瓣逆流壓差", "三尖瓣逆流壓力梯度", "TRPG", "TR PG"),
    "PASP": ("肺動脈收縮壓", "肺動脈收縮期壓", "PASP", "SPAP"),
    "TAPSE": ("三尖瓣環平面收縮位移", "TAPSE"),
    "LVEF": ("左心室射出分率", "左心室收縮分率", "LVEF", "EF"),
    "E/e'": ("E/e' 比值", "E/e’ 比值", "E/e′ 比值", "E/e'", "E/e’", "E/e′"),
    "ASD": ("心房中隔缺損", "ASD"),
    "PFO": ("卵圓孔未閉", "PFO"),
}

TRANSLATION_STANDARD_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("僧帽瓣逆流", "二尖瓣逆流"),
    ("二尖瓣返流", "二尖瓣逆流"),
    ("僧帽瓣返流", "二尖瓣逆流"),
    ("三尖瓣返流", "三尖瓣逆流"),
    ("主動脈逆流", "主動脈瓣逆流"),
    ("主動脈瓣返流", "主動脈瓣逆流"),
    ("肺動脈逆流", "肺動脈瓣逆流"),
    ("肺動脈瓣返流", "肺動脈瓣逆流"),
    ("僧帽瓣狹窄", "二尖瓣狹窄"),
    ("左心室肥大", "左心室肥厚"),
    ("右心室肥大", "右心室肥厚"),
    ("右心房區域", "右心房面積"),
    ("三尖瓣逆流壓力梯度", "三尖瓣逆流壓差"),
    ("肺動脈收縮期壓", "肺動脈收縮壓"),
    ("左心室收縮分率", "左心室射出分率"),
    ("E/e’ 比值", "E/e' 比值"),
    ("E/e′ 比值", "E/e' 比值"),
)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias).replace(r"\ ", r"\s+")
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", alias))
    if has_cjk:
        return re.compile(escaped, re.IGNORECASE)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


_ALIAS_INDEX: tuple[tuple[TermEntry, re.Pattern[str]], ...] = tuple(
    (entry, _alias_pattern(alias))
    for entry in TERM_ENTRIES
    for alias in entry.aliases
)


def retrieve_terms(*texts: str, max_terms: int = 12) -> list[TermEntry]:
    haystack = "\n".join(text for text in texts if text)
    if not haystack:
        return []
    matched: list[TermEntry] = []
    seen: set[str] = set()
    for entry, pattern in _ALIAS_INDEX:
        if entry.key in seen:
            continue
        if pattern.search(haystack):
            matched.append(entry)
            seen.add(entry.key)
            if len(matched) >= max_terms:
                break
    return matched


def format_terminology_context(entries: Iterable[TermEntry]) -> str:
    entries = list(entries)
    if not entries:
        return ""
    lines = ["Terminology constraints from local echo termbase:"]
    for entry in entries:
        alias_text = ", ".join(entry.aliases[:4])
        line = f"- {entry.key}: use 「{entry.zh}」. Aliases: {alias_text}."
        if entry.rules:
            line += " Rules: " + " ".join(entry.rules)
        lines.append(line)
    return "\n".join(lines)


def build_terminology_context(*texts: str, max_terms: int = 12) -> str:
    return format_terminology_context(retrieve_terms(*texts, max_terms=max_terms))


def apply_term_replacements(text: str) -> str:
    if not text:
        return text
    for src, tgt in TERM_REPLACEMENTS.items():
        text = text.replace(src, tgt)
    return text


def standardize_translation_terms(text: str) -> str:
    if not text:
        return text
    text = apply_term_replacements(text)
    for src, tgt in TRANSLATION_STANDARD_REPLACEMENTS:
        text = text.replace(src, tgt)
    return text


def standardize_summary_terms(text: str) -> str:
    """Normalize residual English echo terms in final summary text.

    Summary models occasionally keep measurement labels in English even when
    the translation is already Chinese. Keep this deterministic and narrow so
    it fixes terminology without rewriting the clinical content.
    """
    if not text:
        return text
    text = standardize_translation_terms(text)
    replacements: tuple[tuple[str, str], ...] = (
        (r"三尖瓣逆流\s*peak\s*/\s*mean\s+systolic\s+(?:pressure\s+gradient|PG)\s*=\s*", "三尖瓣逆流峰值/平均收縮期壓差為 "),
        (r"三尖瓣逆流\s*peak\s*/\s*mean\s+systolic\s+(?:pressure\s+gradient|PG)", "三尖瓣逆流峰值/平均收縮期壓差"),
        (r"三尖瓣逆流\s*peak\s+systolic\s+(?:pressure\s+gradient|PG)\s*=\s*", "三尖瓣逆流峰值收縮期壓差為 "),
        (r"三尖瓣逆流\s*peak\s+systolic\s+(?:pressure\s+gradient|PG)", "三尖瓣逆流峰值收縮期壓差"),
        (r"\bTR\s*peak\s*/\s*mean\s+systolic\s+(?:pressure\s+gradient|PG)\s*=\s*", "三尖瓣逆流峰值/平均收縮期壓差為 "),
        (r"\bTR\s*peak\s+systolic\s+(?:pressure\s+gradient|PG)\s*=\s*", "三尖瓣逆流峰值收縮期壓差為 "),
        (r"\bpeak\s*/\s*mean\s+systolic\s+(?:pressure\s+gradient|PG)\b", "峰值/平均收縮期壓差"),
        (r"\bpeak\s+systolic\s+(?:pressure\s+gradient|PG)\b", "峰值收縮期壓差"),
        (r"\bmean\s+systolic\s+(?:pressure\s+gradient|PG)\b", "平均收縮期壓差"),
        (r"\bpressure\s+gradient\b", "壓差"),
        (r"\bpeak\s+gradient\b", "峰值壓差"),
        (r"\bmean\s+gradient\b", "平均壓差"),
        (r"\bchamber\s+dilat(?:ation|ion)\b", "腔室擴大"),
        (r"\bchamber\s+dilation\b", "腔室擴大"),
        (r"\bchamber\s+size\b", "腔室大小"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([，,。；;])", r"\1", text)
    text = re.sub(r"為\s+(\d)", r"為 \1", text)
    return text.strip()


def source_has(pattern: str, source_text: str) -> bool:
    return re.search(pattern, source_text or "", flags=re.IGNORECASE) is not None


def source_has_explicit(patterns: Iterable[str], source_text: str) -> bool:
    return any(source_has(pattern, source_text) for pattern in patterns)


def apply_source_aware_translation_corrections(source_text: str, translated_text: str) -> str:
    """Use the source report to fix high-risk terminology over-interpretation.

    This is intentionally deterministic and conservative: it edits only phrases
    that are known policy violations for the translation task, instead of asking
    the model to rewrite the whole report.
    """
    text = translated_text or ""
    source = source_text or ""

    if source_has(r"\bRA\s*AREA\b", source):
        text = re.sub(
            r"右心房面積(?:顯著|明顯)?(?:擴大|擴張|增大)[（(]\s*([^）)]+?)\s*[）)]",
            r"右心房面積 \1",
            text,
        )
        text = re.sub(
            r"右心房面積[（(]\s*([^）)]+?)\s*[）)]\s*(?:顯著|明顯)?(?:擴大|擴張|增大)",
            r"右心房面積 \1",
            text,
        )
        text = re.sub(r"右心房面積(?:顯著|明顯)?(?:擴大|擴張|增大)", "右心房面積", text)
        text = re.sub(r"右心房(?:的)?面積(?:顯著|明顯)?(?:擴大|擴張|增大)", "右心房面積", text)

    if source_has(r"\bTAPSE\b", source):
        text = re.sub(
            r"(?:，|,|；|;)?\s*右心室(?:縱向)?(?:收縮)?功能(?:明顯|顯著)?(?:下降|降低|減退|偏低|正常|保留|不全)",
            "",
            text,
        )
        text = re.sub(
            r"右心室(?:縱向)?(?:收縮)?功能(?:明顯|顯著)?(?:下降|降低|減退|偏低|正常|保留|不全)[，,、；;]?\s*",
            "",
            text,
        )

    has_tr_gradient = source_has(
        r"\bTR\b.*?(?:PEAK/MEAN\s+)?SYSTOLIC\s+(?:PG|PRESSURE\s+GRADIENT)",
        source,
    ) or source_has(
        r"TRICUSPID\s+REGURGITATION.*?(?:PG|PRESSURE\s+GRADIENT)",
        source,
    )
    has_direct_pasp = source_has_explicit(
        (r"\bPASP\b", r"\bSPAP\b", r"PULMONARY\s+ARTERY\s+SYSTOLIC\s+PRESSURE"),
        source,
    )
    if has_tr_gradient and not has_direct_pasp:
        text = re.sub(
            r"(?:估計)?肺動脈收縮壓(?:峰值/平均值|峰值／平均值)?(?:為|約為)?\s*",
            "三尖瓣逆流訊號之峰值/平均收縮期壓差為",
            text,
        )
        text = re.sub(
            r"右心室收縮期壓(?:力)?(?:梯度|差)?(?:峰值/平均值|峰值／平均值)?(?:為|約為)?\s*",
            "三尖瓣逆流訊號之峰值/平均收縮期壓差為",
            text,
        )

    if source_has(r"SUGGEST\s+PULMONARY\s+HYPERTENSION", source):
        text = re.sub(r"(?:有|合併)(?:重度|嚴重|中度|輕度)?肺(?:動脈)?高壓", "提示肺高壓", text)
        text = re.sub(r"提示(?:有)?肺(?:動脈)?高壓", "提示肺高壓", text)

    has_lvef_50_54 = source_has(r"(?:LVEF|EJECTION\s+FRACTION)\s*(?:IS|=|:)?\s*5[0-4]\s*%", source)
    source_has_lvef_judgement = source_has_explicit(
        (
            r"LOW\s+NORMAL",
            r"BORDERLINE",
            r"SYSTOLIC\s+(?:DYSFUNCTION|FUNCTION)",
            r"HYPOKINESIS",
            r"AKINESIS",
        ),
        source,
    )
    if has_lvef_50_54 and not source_has_lvef_judgement:
        text = re.sub(r"(?:，|,|；|;)?\s*(?:屬)?(?:邊緣偏低|低正常|收縮功能(?:障礙|下降|減退|不全|臨界值))", "", text)

    has_negated_asd_pfo = source_has(
        r"\bNO\s+(?:ASD\s*(?:OR|/|AND)\s*PFO|PFO\s*(?:OR|/|AND)\s*ASD)\b",
        source,
    )
    if has_negated_asd_pfo:
        text = re.sub(
            r"未(?:發現|見|檢出)?卵圓孔未閉(?:或|及|和|與)卵圓孔未閉",
            "未發現心房中隔缺損或卵圓孔未閉",
            text,
        )
        text = re.sub(
            r"無卵圓孔未閉(?:或|及|和|與)卵圓孔未閉",
            "無心房中隔缺損或卵圓孔未閉",
            text,
        )

    text = re.sub(r"\s+([，,。；;])", r"\1", text)
    text = re.sub(r"[，,；;]\s*([，,；;])", r"\1", text)
    return text.strip()


def _has_any_alias(text: str, aliases: Iterable[str]) -> bool:
    if not text:
        return False
    for alias in aliases:
        if _alias_pattern(alias).search(text):
            return True
    return False


def audit_translation_terms(source_text: str, translated_text: str, max_terms: int = 12) -> list[str]:
    terms = retrieve_terms(source_text or "", max_terms=max_terms)
    warnings: list[str] = []
    for term in terms:
        aliases = TRANSLATION_OUTPUT_ALIASES.get(term.key, (term.zh,))
        if not _has_any_alias(translated_text or "", aliases):
            warnings.append(f"{term.key}→{term.zh}")
    return warnings


def apply_translation_term_audit(source_text: str, translated_text: str) -> tuple[str, list[str]]:
    text = standardize_translation_terms(translated_text)
    text = apply_source_aware_translation_corrections(source_text, text)
    return text, audit_translation_terms(source_text, text)
