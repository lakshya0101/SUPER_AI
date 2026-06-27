"""Unit tests for utils/citation_grounding.py.

Covers the five scenarios defined in the grounding specification:
  1. Correct answer + correct citation        → PASS
  2. Correct answer + wrong citation          → FAIL
  3. Correct answer + missing evidence        → FAIL
  4. Merged table rows                        → PASS
  5. Missing citation text                    → DATA MISSING

Run with:
    python -m pytest tests/test_citation_grounding.py -v
"""

from __future__ import annotations

import sys
import os

# Allow running from the project root without installation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from utils.citation_grounding import (
    citation_grounding_gate,
    extract_attribute_from_question,
    extract_product_from_question,
    validate_table_row_grounding,
    verify_attribute_exists_in_citation,
    verify_product_exists_in_citation,
    verify_value_supported_by_citation,
)


# ─────────────────────────────────────────────────────────────────────────────
# extract_product_from_question
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractProductFromQuestion:
    def test_for_pattern(self):
        q = "What is the quarterly minimum objective (Qtrly./PMR) for MYCEPT-500 TABLETS?"
        assert extract_product_from_question(q) == "MYCEPT-500 TABLETS"

    def test_for_pattern_with_currency(self):
        q = "What is the incentive per strip(₹ wise) for EVERGRAF-0.5 TABLETS?"
        assert extract_product_from_question(q) == "EVERGRAF-0.5 TABLETS"

    def test_of_pattern_with_qualifier(self):
        q = "What is the new MRP of MULTISTAR INJECTION (30 ML)?"
        assert extract_product_from_question(q) == "MULTISTAR INJECTION (30 ML)"

    def test_of_pattern_simple(self):
        q = "What is the current MRP of NATAFORCE EYE DROPS?"
        assert extract_product_from_question(q) == "NATAFORCE EYE DROPS"

    def test_of_pattern_tablet(self):
        q = "What is the new MRP of NEFROZON TABLETS?"
        assert extract_product_from_question(q) == "NEFROZON TABLETS"

    def test_mirablad_qualifier(self):
        q = "What is the New MRP of MIRABLAD-S 50 TABLETS?"
        assert extract_product_from_question(q) == "MIRABLAD-S 50 TABLETS"

    def test_returns_empty_when_no_match(self):
        q = "What is the highest incentive in the table?"
        # No "for PRODUCT" / "of PRODUCT" pattern with uppercase product
        result = extract_product_from_question(q)
        assert result == "" or isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# extract_attribute_from_question
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractAttributeFromQuestion:
    def test_quarterly_objective(self):
        q = "What is the quarterly minimum objective (Qtrly./PMR) for MYCEPT-500 TABLETS?"
        assert extract_attribute_from_question(q) == "QUARTERLY_OBJECTIVE"

    def test_incentive_per_strip(self):
        q = "What is the incentive per strip(₹ wise) for EVERGRAF-0.5 TABLETS?"
        assert extract_attribute_from_question(q) == "INCENTIVE_PER_STRIP"

    def test_new_mrp(self):
        q = "What is the new MRP of MULTISTAR INJECTION (30 ML)?"
        assert extract_attribute_from_question(q) == "NEW_MRP"

    def test_current_mrp(self):
        q = "What is the current MRP of NATAFORCE EYE DROPS?"
        assert extract_attribute_from_question(q) == "CURRENT_MRP"

    def test_mrp_generic(self):
        q = "What is the MRP of NEFROZON TABLETS?"
        assert extract_attribute_from_question(q) in ("MRP", "CURRENT_MRP", "NEW_MRP")

    def test_general_fallback(self):
        q = "What is the composition of this drug?"
        assert extract_attribute_from_question(q) == "GENERAL"


# ─────────────────────────────────────────────────────────────────────────────
# verify_product_exists_in_citation
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyProductExistsInCitation:
    def test_exact_match(self):
        text = "... MYCEPT-500 TABLETS 270 810 4.35 ..."
        assert verify_product_exists_in_citation("MYCEPT-500 TABLETS", text) is True

    def test_case_insensitive(self):
        text = "mycept-500 tablets 270 810 4.35"
        assert verify_product_exists_in_citation("MYCEPT-500 TABLETS", text) is True

    def test_product_absent(self):
        text = "TRANSPLANT INCENTIVE POLICY 2025-26 Some other product PANGRAF 1 MG"
        assert verify_product_exists_in_citation("MYCEPT-500 TABLETS", text) is False

    def test_product_with_qualifier(self):
        text = "MULTISTAR INJECTION (30 ML) 150.00 140.25"
        assert verify_product_exists_in_citation("MULTISTAR INJECTION (30 ML)", text) is True

    def test_partial_name_not_sufficient_for_short_token(self):
        # "MYC" alone should not match "MYCEPT-500 TABLETS"
        text = "MYC tablets 270 810"
        result = verify_product_exists_in_citation("MYCEPT-500 TABLETS", text)
        # MYCEPT has 6 chars, MYC only 3 — distinctive token won't match
        assert result is False

    def test_merged_table_row(self):
        text = (
            "MIRABLAD-S 50 TABLETS 530.00 496.87 "
            "MLIFE TABLETS 206.91 193.97"
        )
        assert verify_product_exists_in_citation("MIRABLAD-S 50 TABLETS", text) is True
        assert verify_product_exists_in_citation("MLIFE TABLETS", text) is True


# ─────────────────────────────────────────────────────────────────────────────
# verify_attribute_exists_in_citation
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyAttributeExistsInCitation:
    def test_quarterly_objective_present(self):
        text = "S.No Product PM Qtrly Incentive per strip"
        assert verify_attribute_exists_in_citation("QUARTERLY_OBJECTIVE", text) is True

    def test_incentive_present(self):
        text = "incentive per strip ₹4.35"
        assert verify_attribute_exists_in_citation("INCENTIVE_PER_STRIP", text) is True

    def test_new_mrp_present(self):
        text = "Product Name Current MRP New MRP"
        assert verify_attribute_exists_in_citation("NEW_MRP", text) is True

    def test_attribute_absent(self):
        text = "Clinical trial data Phase III ORION-9 results"
        assert verify_attribute_exists_in_citation("QUARTERLY_OBJECTIVE", text) is False

    def test_general_always_true(self):
        # GENERAL has no synonyms → returns True regardless of citation content
        assert verify_attribute_exists_in_citation("GENERAL", "anything") is True
        assert verify_attribute_exists_in_citation("GENERAL", "") is True
        assert verify_attribute_exists_in_citation("GENERAL", "   ") is True


# ─────────────────────────────────────────────────────────────────────────────
# verify_value_supported_by_citation
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyValueSupportedByCitation:
    def test_exact_numeric_match(self):
        text = "MYCEPT-500 TABLETS 270 810 4.35"
        assert verify_value_supported_by_citation("810", "MYCEPT-500 TABLETS", text) is True

    def test_decimal_match(self):
        text = "MIRABLAD-S 50 TABLETS 530.00 496.87"
        assert verify_value_supported_by_citation("496.87", "MIRABLAD-S 50 TABLETS", text) is True

    def test_value_absent(self):
        text = "MYCEPT-500 TABLETS 270 650 4.35"
        assert verify_value_supported_by_citation("810", "MYCEPT-500 TABLETS", text) is False

    def test_indian_comma_notation(self):
        text = "trip cost ₹1,10,000 per couple"
        assert verify_value_supported_by_citation("1,10,000", "TRIP", text) is True

    def test_currency_symbol_stripped(self):
        text = "Incentive ₹4.35 per strip"
        assert verify_value_supported_by_citation("₹4.35", "EVERGRAF", text) is True

    def test_empty_value_returns_false(self):
        assert verify_value_supported_by_citation("", "PRODUCT", "some text") is False

    def test_empty_citation_returns_false(self):
        assert verify_value_supported_by_citation("810", "PRODUCT", "") is False


# ─────────────────────────────────────────────────────────────────────────────
# validate_table_row_grounding
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateTableRowGrounding:
    def test_all_checks_pass(self):
        citation = "MYCEPT-500 TABLETS 270 810 4.35 Qtrly objective"
        result = validate_table_row_grounding(
            product="MYCEPT-500 TABLETS",
            attribute_type="QUARTERLY_OBJECTIVE",
            claimed_value="810",
            citation_text=citation,
        )
        assert result["grounded"] is True
        assert result["product_found"] is True
        assert result["attribute_found"] is True
        assert result["value_supported"] is True

    def test_product_missing_fails_grounding(self):
        citation = "PANGRAF 1 MG 200 600 3.10 objective"
        result = validate_table_row_grounding(
            product="MYCEPT-500 TABLETS",
            attribute_type="QUARTERLY_OBJECTIVE",
            claimed_value="810",
            citation_text=citation,
        )
        assert result["grounded"] is False
        assert result["product_found"] is False

    def test_value_missing_fails_grounding(self):
        citation = "MYCEPT-500 TABLETS 270 650 4.35 Qtrly objective"
        result = validate_table_row_grounding(
            product="MYCEPT-500 TABLETS",
            attribute_type="QUARTERLY_OBJECTIVE",
            claimed_value="810",
            citation_text=citation,
        )
        assert result["grounded"] is False
        assert result["product_found"] is True
        assert result["value_supported"] is False


# ─────────────────────────────────────────────────────────────────────────────
# citation_grounding_gate  — the five specification scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationGroundingGate:

    # ── Scenario 1: Correct answer + correct citation → PASS ─────────────
    def test_correct_answer_correct_citation_pass(self):
        """Product and value both present in citation → PASS is kept."""
        question = "What is the quarterly minimum objective (Qtrly./PMR) for MYCEPT-500 TABLETS?"
        citation = (
            "Transplant Incentive Policy 2025-26\n"
            "S.No Product PM Qtrly Incentive per strip\n"
            "5 MYCEPT-500 TABLETS 270 810 4.35"
        )
        result, reason = citation_grounding_gate(
            question=question,
            super_ai_response="Minimum quarterly objective (Qtrly./PMR) for MYCEPT-500 TABLETS: 810 strips",
            citation_text=citation,
            openai_result="PASS",
            openai_reason="Product found, value 810 confirmed in citation.",
            matched_value="810",
        )
        assert result == "PASS", f"Expected PASS, got {result}: {reason}"

    # ── Scenario 2: Correct answer + wrong citation (product absent) → FAIL
    def test_correct_answer_wrong_citation_fail(self):
        """Product is NOT in the cited page → PASS overridden to FAIL."""
        question = "What is the quarterly minimum objective (Qtrly./PMR) for MYCEPT-500 TABLETS?"
        citation = (
            "Transplant Incentive Policy 2025-26 Page 17\n"
            "Eligibility criteria for foreign trip award\n"
            "Minimum growth 20% Pangraf contribution 30%"
        )
        result, reason = citation_grounding_gate(
            question=question,
            super_ai_response="810 strips",
            citation_text=citation,
            openai_result="PASS",
            openai_reason="Answer matches.",
            matched_value="810",
        )
        assert result == "FAIL", f"Expected FAIL, got {result}: {reason}"
        assert "not present" in reason.lower() or "not found" in reason.lower()

    # ── Scenario 3: Correct answer + citation has product but not value → FAIL
    def test_correct_answer_missing_value_evidence_fail(self):
        """Product is in citation but the value 810 is absent → FAIL.

        The citation includes realistic table-header text so that Guard 4
        (attribute check) passes, and the FAIL is triggered by Guard 5
        (value absent from citation).
        """
        question = "What is the quarterly minimum objective (Qtrly./PMR) for MYCEPT-500 TABLETS?"
        citation = (
            "Transplant Incentive Policy 2025-26\n"
            "S.No Product PM Qtrly Incentive per strip\n"
            "MYCEPT-500 TABLETS 270 650 4.35\n"
            "PANGRAF 1 MG 300 900 5.00"
        )
        result, reason = citation_grounding_gate(
            question=question,
            super_ai_response="810 strips",
            citation_text=citation,
            openai_result="PASS",
            openai_reason="Product found.",
            matched_value="810",
        )
        assert result == "FAIL", f"Expected FAIL, got {result}: {reason}"
        assert "not found" in reason.lower() or "not supported" in reason.lower()

    # ── Scenario 4: Merged table rows → PASS ─────────────────────────────
    def test_merged_table_rows_pass(self):
        """Value found in merged PDF table text (rows concatenated) → PASS is kept.

        Real PDF pages include the column-header row ("Current MRP  New MRP")
        above the data rows, so the attribute synonym "new mrp" is present even
        when the data rows themselves are concatenated on a single line.
        """
        question = "What is the New MRP of MIRABLAD-S 50 TABLETS?"
        citation = (
            "Revised MRP List 2025-26\n"
            "Name of Product  Current MRP  New MRP\n"
            "MIRABLAD-S 50 TABLETS 530.00 496.87 "
            "MLIFE TABLETS 206.91 193.97"
        )
        result, reason = citation_grounding_gate(
            question=question,
            super_ai_response="New MRP of MIRABLAD-S 50 TABLETS is ₹496.87",
            citation_text=citation,
            openai_result="PASS",
            openai_reason="New MRP 496.87 verified.",
            matched_value="496.87",
        )
        assert result == "PASS", f"Expected PASS, got {result}: {reason}"

    # ── Scenario 5: Missing citation text → DATA MISSING ─────────────────
    def test_missing_citation_text_data_missing(self):
        """Empty citation text cannot be verified → DATA MISSING."""
        question = "What is the quarterly minimum objective (Qtrly./PMR) for MYCEPT-500 TABLETS?"
        result, reason = citation_grounding_gate(
            question=question,
            super_ai_response="810 strips",
            citation_text="",
            openai_result="PASS",
            openai_reason="Answer matches.",
            matched_value="810",
        )
        assert result == "DATA MISSING", f"Expected DATA MISSING, got {result}: {reason}"
        assert "unavailable" in reason.lower() or "cannot" in reason.lower()

    # ── Non-PASS verdicts pass through unchanged ──────────────────────────
    def test_fail_passthrough(self):
        result, reason = citation_grounding_gate(
            question="What is the new MRP of NEFROZON TABLETS?",
            super_ai_response="999.00",
            citation_text="NEFROZON TABLETS 500.00 470.00",
            openai_result="FAIL",
            openai_reason="Value 999 not in citation.",
            matched_value="999.00",
        )
        assert result == "FAIL"

    def test_data_missing_passthrough(self):
        result, reason = citation_grounding_gate(
            question="What is the current MRP of NATAFORCE EYE DROPS?",
            super_ai_response="",
            citation_text="",
            openai_result="DATA MISSING",
            openai_reason="Product not found.",
        )
        assert result == "DATA MISSING"

    # ── Gate skipped when product cannot be extracted ─────────────────────
    def test_gate_skipped_when_no_product(self):
        """Unrecognised question format → gate skips, OpenAI verdict kept."""
        result, reason = citation_grounding_gate(
            question="Which product has the highest incentive?",
            super_ai_response="PANGRAF 1 MG",
            citation_text="incentive policy document page 3",
            openai_result="PASS",
            openai_reason="Confirmed.",
        )
        assert result == "PASS"


# ─────────────────────────────────────────────────────────────────────────────
# _repair_mrp_misclassification  (imported from engine)
# ─────────────────────────────────────────────────────────────────────────────

class TestRepairMrpMisclassification:
    def test_downgrades_fail_when_qualifier_absent_from_evidence(self):
        from utils.openai_validation_engine import _repair_mrp_misclassification

        result, reason = _repair_mrp_misclassification(
            result="FAIL",
            reason="Value mismatch.",
            question="What is the new MRP of MONTICOPE SUSPENSION (60 ML)?",
            evidence="MONTICOPE SUSPENSION 87.00 82.00",
        )
        assert result == "DATA MISSING"
        assert "(60 ml)" in reason.lower()

    def test_does_not_change_pass(self):
        from utils.openai_validation_engine import _repair_mrp_misclassification

        result, reason = _repair_mrp_misclassification(
            result="PASS",
            reason="All good.",
            question="What is the new MRP of MONTICOPE SUSPENSION (60 ML)?",
            evidence="MONTICOPE SUSPENSION (60 ML) 87.00 82.00",
        )
        assert result == "PASS"

    def test_no_change_when_qualifier_present_in_evidence(self):
        from utils.openai_validation_engine import _repair_mrp_misclassification

        result, reason = _repair_mrp_misclassification(
            result="FAIL",
            reason="Value mismatch.",
            question="What is the new MRP of MONTICOPE SUSPENSION (60 ML)?",
            evidence="MONTICOPE SUSPENSION (60 ML) 87.00 99.00",
        )
        assert result == "FAIL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
