import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

PROXY_DIR = Path(__file__).resolve().parents[1] / "proxy"
sys.path.insert(0, str(PROXY_DIR))

from terminology import (
    apply_translation_term_audit,
    build_terminology_context,
    retrieve_terms,
    standardize_summary_terms,
)
from prompts import (
    build_strict_translate_prompt,
    build_summary_prompt,
    build_translategemma_translate_prompt,
)
from structured_json import build_structured_findings_prompt, rule_based_structured_findings


class TerminologyRagTests(unittest.TestCase):
    def setUp(self):
        self._old_term_rag = os.environ.get("TERM_RAG_ENABLED")
        self._old_summary_rag = os.environ.get("SUMMARY_RAG_ENABLED")
        os.environ["TERM_RAG_ENABLED"] = "true"
        os.environ["SUMMARY_RAG_ENABLED"] = "true"

    def tearDown(self):
        if self._old_term_rag is None:
            os.environ.pop("TERM_RAG_ENABLED", None)
        else:
            os.environ["TERM_RAG_ENABLED"] = self._old_term_rag
        if self._old_summary_rag is None:
            os.environ.pop("SUMMARY_RAG_ENABLED", None)
        else:
            os.environ["SUMMARY_RAG_ENABLED"] = self._old_summary_rag

    def test_retrieves_echo_terms_and_rules(self):
        text = "Mild MR. TRPG 55 mmHg. RA AREA 24.6 cm2. LVEF 50%."
        terms = retrieve_terms(text)
        keys = {term.key for term in terms}
        self.assertIn("MR", keys)
        self.assertIn("TRPG", keys)
        self.assertIn("RA area", keys)
        self.assertIn("LVEF", keys)
        ctx = build_terminology_context(text)
        self.assertIn("二尖瓣逆流", ctx)
        self.assertIn("三尖瓣逆流壓差", ctx)
        self.assertIn("不可自行補成右心房擴大", ctx)
        self.assertIn("左心室射出分率", ctx)

    def test_translate_prompt_injects_term_rag(self):
        req = SimpleNamespace(
            source="Mild MR with RA AREA 24.6 cm2 and no PFO.",
            glossary=[],
        )
        prompt = build_strict_translate_prompt(req)
        self.assertIn("### Terminology RAG / 字庫約束", prompt)
        self.assertLess(prompt.index("### Terminology RAG"), prompt.index("### Input"))
        self.assertIn("MR: use 「二尖瓣逆流」", prompt)
        self.assertIn("RA area: use 「右心房面積」", prompt)
        self.assertIn("PFO: use 「卵圓孔未閉」", prompt)
        self.assertIn("不可自行補成右心房擴大", prompt)
        input_section = prompt.split("### Input:", 1)[1]
        self.assertNotIn("### Terminology RAG", input_section)

    def test_term_rag_is_disabled_by_default(self):
        os.environ.pop("TERM_RAG_ENABLED", None)
        os.environ.pop("SUMMARY_RAG_ENABLED", None)
        req = SimpleNamespace(
            source="Mild MR with RA AREA 24.6 cm2.",
            glossary=[],
        )
        prompt = build_strict_translate_prompt(req)
        self.assertNotIn("### Terminology RAG", prompt)
        self.assertIn("Mild MR with RA AREA 24.6 cm2.", prompt)

        summary_req = SimpleNamespace(source="輕度 MR。", style="Clinical")
        summary_prompt = build_summary_prompt(summary_req, "llama-3.2-3b-instruct-summarizer-clinical-v4")
        self.assertNotIn("### Terminology RAG", summary_prompt)

    def test_summary_rag_does_not_enable_translation_prompt_rag(self):
        os.environ["TERM_RAG_ENABLED"] = "false"
        os.environ["SUMMARY_RAG_ENABLED"] = "true"

        translate_req = SimpleNamespace(
            source="Mild MR with RA AREA 24.6 cm2.",
            glossary=[],
        )
        translate_prompt = build_strict_translate_prompt(translate_req)
        self.assertNotIn("### Terminology RAG", translate_prompt)

        summary_req = SimpleNamespace(source="輕度 MR。右心房面積 24.6 cm2。", style="Clinical")
        summary_prompt = build_summary_prompt(summary_req, "llama-3.2-3b-instruct-summarizer-clinical-v4")
        self.assertIn("### Terminology RAG / 字庫約束", summary_prompt)
        self.assertIn("MR: use 「二尖瓣逆流」", summary_prompt)

    def test_translategemma_prompt_has_single_term_block(self):
        req = SimpleNamespace(
            source="Moderate TR. PASP 60 mmHg.",
            glossary=[],
        )
        prompt = build_translategemma_translate_prompt(req)
        self.assertEqual(prompt.count("### Terminology RAG / 字庫約束"), 1)
        self.assertLess(prompt.index("### Terminology RAG"), prompt.index("英文心臟超音波報告"))
        self.assertIn("TR: use 「三尖瓣逆流」", prompt)
        self.assertIn("PASP: use 「肺動脈收縮壓」", prompt)

    def test_summary_and_structured_prompts_inject_terms(self):
        req = SimpleNamespace(
            source="右心房面積 24.6 cm2。TRPG 55 mmHg。輕度 MR。",
            style="Clinical",
        )
        summary_prompt = build_summary_prompt(req, "llama-3.2-3b-instruct-summarizer-clinical-v4")
        self.assertIn("### Terminology RAG / 字庫約束", summary_prompt)
        self.assertLess(summary_prompt.index("### Terminology RAG"), summary_prompt.index("### Input"))
        self.assertIn("右心房面積", summary_prompt)
        self.assertIn("三尖瓣逆流壓差", summary_prompt)

        structured_prompt = build_structured_findings_prompt(
            "RA AREA 24.6 cm2; TRPG 55 mmHg; mild MR",
            "右心房面積 24.6 cm2；三尖瓣逆流壓差 55 mmHg；輕度二尖瓣逆流",
            "右心房面積與壓差數值需保留。",
        )
        self.assertIn("### Terminology RAG / 字庫約束", structured_prompt)
        self.assertLess(structured_prompt.index("### Terminology RAG"), structured_prompt.index("### Input"))
        self.assertIn("measurement 類術語不可自行升級成診斷", structured_prompt)
        self.assertIn("不可自行補成右心房擴大", structured_prompt)

    def test_translation_term_audit_standardizes_without_prompt_rag(self):
        source = "Mild MR. RA AREA 24.6 cm2."
        translated = "輕度僧帽瓣逆流。右心房區域 24.6 平方公分。"
        fixed, warnings = apply_translation_term_audit(source, translated)
        self.assertIn("輕度二尖瓣逆流", fixed)
        self.assertIn("右心房面積 24.6", fixed)
        self.assertNotIn("僧帽瓣逆流", fixed)
        self.assertEqual(warnings, [])

    def test_translation_term_audit_warns_missing_terms_only(self):
        source = "TRPG 55 mmHg. Mild MR."
        translated = "輕度二尖瓣逆流。壓差 55 毫米汞柱。"
        fixed, warnings = apply_translation_term_audit(source, translated)
        self.assertEqual(fixed, translated)
        self.assertIn("TRPG→三尖瓣逆流壓差", warnings)
        self.assertNotIn("MR→二尖瓣逆流", warnings)

    def test_source_aware_translation_corrections_from_clean_policy(self):
        source = (
            "RA AREA -- 24.6 CM^2\n"
            "TAPSE -- 1.4 CM\n"
            "MODERATE TR WITH PEAK/MEAN SYSTOLIC PG -- 80/55 MMHG\n"
            "SUGGEST PULMONARY HYPERTENSION\n"
            "THE LV EJECTION FRACTION IS 50 %\n"
        )
        translated = (
            "右心房面積擴大 24.6 平方公分，"
            "三尖瓣環平面收縮位移 1.4 cm，右心室功能下降，"
            "中度三尖瓣逆流，估計肺動脈收縮壓峰值/平均值為80/55毫米汞柱，"
            "有重度肺動脈高壓，"
            "左心室射出分率為50%，低正常。"
        )
        fixed, warnings = apply_translation_term_audit(source, translated)
        self.assertIn("右心房面積 24.6", fixed)
        self.assertNotIn("右心房面積擴大", fixed)
        self.assertIn("三尖瓣環平面收縮位移 1.4 cm", fixed)
        self.assertNotIn("右心室功能下降", fixed)
        self.assertIn("三尖瓣逆流訊號之峰值/平均收縮期壓差為80/55", fixed)
        self.assertNotIn("肺動脈收縮壓峰值/平均值", fixed)
        self.assertIn("提示肺高壓", fixed)
        self.assertNotIn("有重度肺動脈高壓", fixed)
        self.assertIn("左心室射出分率為50%", fixed)
        self.assertNotIn("低正常", fixed)

    def test_source_aware_correction_for_negated_asd_pfo(self):
        source = "NO ASD OR PFO DETECTED"
        translated = "未發現卵圓孔未閉或卵圓孔未閉。"
        fixed, warnings = apply_translation_term_audit(source, translated)
        self.assertIn("未發現心房中隔缺損或卵圓孔未閉", fixed)
        self.assertNotIn("卵圓孔未閉或卵圓孔未閉", fixed)
        self.assertEqual(warnings, [])

    def test_source_aware_correction_for_ra_area_parenthetical_enlargement(self):
        source = "RA AREA - 24.6 CM^2"
        translated = "右心房面積（24.6 平方公分）擴大。"
        fixed, warnings = apply_translation_term_audit(source, translated)
        self.assertIn("右心房面積 24.6 平方公分", fixed)
        self.assertNotIn("右心房面積（24.6 平方公分）擴大", fixed)
        self.assertEqual(warnings, [])

        translated = "右心房面積增大（24.6 平方公分）。"
        fixed, warnings = apply_translation_term_audit(source, translated)
        self.assertIn("右心房面積 24.6 平方公分", fixed)
        self.assertNotIn("右心房面積增大", fixed)
        self.assertEqual(warnings, [])

    def test_summary_terms_standardize_residual_english_measurements(self):
        summary = "肺高壓：三尖瓣逆流 peak systolic pressure gradient = 55 mmHg"
        fixed = standardize_summary_terms(summary)
        self.assertIn("三尖瓣逆流峰值收縮期壓差為 55 mmHg", fixed)
        self.assertNotIn("peak systolic pressure gradient", fixed)

    def test_summary_terms_standardize_tr_peak_mean_pg(self):
        summary = "TR peak/mean systolic PG = 80/55 mmHg，提示肺高壓"
        fixed = standardize_summary_terms(summary)
        self.assertIn("三尖瓣逆流峰值/平均收縮期壓差為 80/55 mmHg", fixed)
        self.assertNotIn("TR peak/mean", fixed)

    def test_diagram_findings_can_be_kept_independent_from_summary(self):
        structured = rule_based_structured_findings(
            "Mild LA enlargement.",
            "輕度左心房擴大。",
            "",
        )
        findings = {(item["part"], item["condition"]) for item in structured["findings"]}
        self.assertIn(("LA", "dilatation"), findings)
        self.assertNotIn(("LV", "hypertrophy"), findings)


if __name__ == "__main__":
    unittest.main()
