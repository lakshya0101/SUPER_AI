# """OpenAI-powered field-level validation for cited PDF page text."""
 
# from __future__ import annotations
 
# import json
# import os
# from typing import Any
 
# from dotenv import load_dotenv
 
# from config.settings import (
#     OPENAI_VALIDATION_ENABLED,
#     OPENAI_VALIDATION_MODEL,
#     OPENAI_VALIDATION_TIMEOUT,
# )
# from utils.logger import get_logger
 
 
# VALID_RESULTS = {"PASS", "FAIL", "DATA MISSING"}
 
 
# def _azure_openai_settings() -> dict[str, str]:
#     """Return Azure OpenAI settings from environment variables."""
#     return {
#         "api_key": (os.getenv("AZURE_OPENAI_API_KEY") or "").strip(),
#         "endpoint": (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/"),
#         "api_version": (
#             os.getenv("AZURE_OPENAI_API_VERSION") or "2025-04-01-preview"
#         ).strip(),
#         "deployment": (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip(),
#     }
 
 
# def is_openai_validation_available() -> bool:
#     """Return whether OpenAI validation can be used for this run."""
#     load_dotenv()
#     return get_openai_validation_status()["available"]
 
 
# def get_openai_validation_status() -> dict[str, bool | str]:
#     """Return OpenAI validation availability and the exact reason."""
#     load_dotenv()
#     enabled = (
#         os.getenv("OPENAI_VALIDATION_ENABLED", str(int(OPENAI_VALIDATION_ENABLED)))
#         .strip()
#         .lower()
#         not in {"0", "false", "no", "off"}
#     )
#     api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
#     base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
#     azure = _azure_openai_settings()
#     azure_configured = bool(
#         azure["api_key"] and azure["endpoint"] and azure["deployment"]
#     )
#     api_key_set = bool(api_key or azure["api_key"])
#     placeholder_key = api_key in {"your_key_here", "YOUR_KEY_HERE"}
#     standard_openai_key = api_key.startswith(("sk-", "sk-proj-"))
#     custom_endpoint_configured = bool(base_url)
#     usable_key_shape = api_key_set and not placeholder_key and (
#         azure_configured or standard_openai_key or custom_endpoint_configured
#     )
#     available = enabled and usable_key_shape
 
#     if available:
#         if azure_configured:
#             reason = "Azure OpenAI validation is active for all products."
#         else:
#             reason = "OpenAI validation is active for all products."
#     elif not enabled:
#         reason = "OpenAI validation is disabled by OPENAI_VALIDATION_ENABLED."
#     elif not api_key_set:
#         reason = "OPENAI_API_KEY or AZURE_OPENAI_API_KEY is not set."
#     elif placeholder_key:
#         reason = "OPENAI_API_KEY is still a placeholder."
#     else:
#         reason = (
#             "OpenAI configuration is incomplete. For Azure, set "
#             "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and "
#             "AZURE_OPENAI_DEPLOYMENT."
#         )
 
#     return {
#         "available": available,
#         "enabled": enabled,
#         "api_key_set": api_key_set,
#         "base_url_set": custom_endpoint_configured,
#         "azure_openai_set": azure_configured,
#         "model": azure["deployment"]
#         or os.getenv("OPENAI_VALIDATION_MODEL", OPENAI_VALIDATION_MODEL),
#         "reason": reason,
#     }
 
 
# def validate_with_openai(
#     *,
#     question: str,
#     super_ai_response: str,
#     cited_page_text: str,
#     product_name: str = "",
#     page_number: int | str = "",
#     document_name: str = "",
# ) -> dict[str, Any]:
#     """Validate SuperAI output against one cited PDF page using OpenAI.
 
#     The PDF page text is still the source of truth. OpenAI only performs
#     field-level extraction and comparison for the requested attribute.
#     """
#     logger = get_logger("openai_validation_engine")
 
#     if not is_openai_validation_available():
#         return {
#             "result": "DATA MISSING",
#             "reason": "OpenAI validation is disabled or OPENAI_API_KEY is not set.",
#             "matched_value": "",
#             "engine": "rule_based_fallback",
#         }
 
#     timeout = int(os.getenv("OPENAI_VALIDATION_TIMEOUT", str(OPENAI_VALIDATION_TIMEOUT)))
#     azure = _azure_openai_settings()
#     azure_configured = bool(
#         azure["api_key"] and azure["endpoint"] and azure["deployment"]
#     )
 
#     try:
#         if azure_configured:
#             from openai import AzureOpenAI
 
#             client = AzureOpenAI(
#                 api_key=azure["api_key"],
#                 azure_endpoint=azure["endpoint"],
#                 api_version=azure["api_version"],
#                 timeout=timeout,
#             )
#             model = azure["deployment"]
#         else:
#             from openai import OpenAI
 
#             model = os.getenv("OPENAI_VALIDATION_MODEL", OPENAI_VALIDATION_MODEL)
#             base_url = os.getenv("OPENAI_BASE_URL")
#             client_kwargs: dict[str, Any] = {"timeout": timeout}
#             if base_url:
#                 client_kwargs["base_url"] = base_url
#             client = OpenAI(**client_kwargs)
#     except ImportError:
#         return {
#             "result": "DATA MISSING",
#             "reason": "OpenAI package is not installed.",
#             "matched_value": "",
#             "engine": "rule_based_fallback",
#         }
 
#     payload = {
#         "question": question,
#         "product_name": product_name,
#         "super_ai_response": super_ai_response,
#         "cited_page_number": str(page_number),
#         "document_name": document_name,
#         "cited_page_text": cited_page_text,
#     }
 
#     try:
#         completion = client.chat.completions.create(
#             model=model,
#             temperature=0,
#             response_format={"type": "json_object"},
#             messages=[
#                 {
#                     "role": "system",
#                     "content": _system_prompt(),
#                 },
#                 {
#                     "role": "user",
#                     "content": json.dumps(payload, ensure_ascii=False),
#                 },
#             ],
#         )
#         content = completion.choices[0].message.content or "{}"
#         decision = _parse_decision(content)
#         logger.info("OpenAI validation decision: %s", decision)
#         return decision
#     except Exception as exc:
#         logger.exception("OpenAI validation failed: %s", exc)
#         return {
#             "result": "DATA MISSING",
#             "reason": f"OpenAI validation failed: {exc}",
#             "matched_value": "",
#             "engine": "rule_based_fallback",
#         }
 
 
# def _parse_decision(content: str) -> dict[str, Any]:
#     """Normalize the model JSON response into the validator decision schema."""
#     try:
#         parsed = json.loads(content or "{}")
#     except json.JSONDecodeError:
#         return {
#             "result": "DATA MISSING",
#             "reason": "OpenAI validation returned invalid JSON.",
#             "matched_value": "",
#             "engine": "rule_based_fallback",
#         }
 
#     raw_result = str(
#         parsed.get("result")
#         or parsed.get("decision")
#         or parsed.get("status")
#         or parsed.get("answer_status")
#         or ""
#     ).strip().upper()
 
#     if raw_result in {"DATA_MISSING", "MISSING DATA", "MISSING_DATA"}:
#         result = "DATA MISSING"
#     elif raw_result in VALID_RESULTS:
#         result = raw_result
#     elif str(parsed.get("answer") or "").strip().upper() == "DATA_MISSING":
#         result = "DATA MISSING"
#     else:
#         result = "DATA MISSING"
 
#     reason = str(
#         parsed.get("reason")
#         or parsed.get("reasoning")
#         or parsed.get("explanation")
#         or "OpenAI validation did not return a reason."
#     ).strip()
 
#     matched_value = str(
#         parsed.get("matched_value")
#         or parsed.get("answer")
#         or parsed.get("document_value")
#         or parsed.get("document_values")
#         or ""
#     ).strip()
 
#     return {
#         "result": result,
#         "reason": reason,
#         "answer": parsed.get("answer", ""),
#         "evidence": parsed.get("evidence", ""),
#         "confidence": parsed.get("confidence", ""),
#         "reasoning": parsed.get("reasoning", reason),
#         "requested_attribute": parsed.get("requested_attribute", ""),
#         "super_ai_values": parsed.get("super_ai_values", []),
#         "document_values": parsed.get("document_values", []),
#         "matched_value": matched_value,
#         "engine": "openai",
#     }
 
 
# def _system_prompt() -> str:
#     return """
# You are a pharmaceutical citation validation engine.
 
# The cited document text is the ONLY source of truth.
 
# Never use external knowledge.
 
# Your task is to determine whether the cited evidence supports the SuperAI answer.
 
# ---
 
# ## VALIDATION PRINCIPLES
 
# 1. Validate meaning, not keyword overlap.
 
# 2. The question determines what attribute must be validated.
 
# Examples:
 
# * Composition
# * Dosage
# * Indication
# * MOA
# * USP
# * Salient Features
# * Competitor Information
# * Pricing
# * Strength
# * Pack Size
 
# 3. Product names must match.
 
# If the cited evidence belongs to a different product:
 
# Return DATA MISSING.
 
# ---
 
# ## MULTI-CITATION RULE
 
# Multiple citations may support different parts of the same answer.
 
# Treat all provided citations as ONE combined body of evidence.
 
# Do NOT require each citation page to independently support the entire answer.
 
# PASS if the combined evidence supports the answer.
 
# ---
 
# ## NUMERIC VALIDATION RULES
 
# Validate only material values.
 
# Material values include:
 
# * Dosage
# * Composition
# * Strength
# * Pricing
# * Pack size
# * Clinical efficacy
# * Safety values
# * Risk reduction
# * Outcome measures
 
# IGNORE the following:
 
# * Citation numbers
# * Reference markers
# * Footnotes
# * Page numbers
# * Trial identifiers
# * Study identifiers
# * ORION-9
# * ORION-10
# * ORION-11
# * TARGET-3
# * Figure numbers
# * Table numbers
# * Literature references
# * Citation 1, Citation 2, Citation 3
# * Source 1, Source 2
 
# Example:
 
# "48% reduction in ORION-9"
 
# Material value:
# 48%
 
# Ignore:
# 9
 
# ---
 
# ## PASS
 
# Return PASS when:
 
# * Product matches
# * Requested attribute exists
# * Combined evidence supports the answer
# * Minor wording differences exist
# * OCR differences exist
# * Formatting differences exist
 
# ---
 
# ## FAIL
 
# Return FAIL only when:
 
# * Product matches
# * Requested attribute exists
# * Evidence contradicts the answer
# * Material values differ
# * Key claims are unsupported
 
# Do NOT fail because of:
 
# * Citation numbering
# * Trial numbering
# * Reference numbering
# * Formatting differences
# * OCR artifacts
 
# ---
 
# ## DATA MISSING
 
# Return DATA MISSING when:
 
# * Product is not found
# * Relevant attribute is absent
# * Citation text is unreadable
# * Validation cannot be performed
 
# ---
 
# ## OUTPUT JSON
 
# {
# "result":"PASS|FAIL|DATA MISSING",
# "reason":"specific explanation",
# "requested_attribute":"attribute",
# "product_name":"product",
# "super_ai_values":["value"],
# "document_values":["value"],
# "matched_value":"value"
# }
# """
 
######################
#######################
 
 
 
"""OpenAI-powered field-level validation for cited PDF page text."""
 
from __future__ import annotations
 
import json
import os
from typing import Any
 
from dotenv import load_dotenv
 
from config.settings import (
    OPENAI_VALIDATION_ENABLED,
    OPENAI_VALIDATION_MODEL,
    OPENAI_VALIDATION_TIMEOUT,
)
from utils.citation_grounding import citation_grounding_gate
from utils.logger import get_logger


VALID_RESULTS = {"PASS", "FAIL", "DATA MISSING"}
 
 
def _azure_openai_settings() -> dict[str, str]:
    """Return Azure OpenAI settings from environment variables."""
    return {
        "api_key": (os.getenv("AZURE_OPENAI_API_KEY") or "").strip(),
        "endpoint": (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/"),
        "api_version": (
            os.getenv("AZURE_OPENAI_API_VERSION") or "2025-04-01-preview"
        ).strip(),
        "deployment": (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip(),
    }
 
 
def is_openai_validation_available() -> bool:
    """Return whether OpenAI validation can be used for this run."""
    load_dotenv()
    return get_openai_validation_status()["available"]
 
 
def get_openai_validation_status() -> dict[str, bool | str]:
    """Return OpenAI validation availability and the exact reason."""
    load_dotenv()
    enabled = (
        os.getenv("OPENAI_VALIDATION_ENABLED", str(int(OPENAI_VALIDATION_ENABLED)))
        .strip()
        .lower()
        not in {"0", "false", "no", "off"}
    )
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    azure = _azure_openai_settings()
    azure_configured = bool(
        azure["api_key"] and azure["endpoint"] and azure["deployment"]
    )
    api_key_set = bool(api_key or azure["api_key"])
    placeholder_key = api_key in {"your_key_here", "YOUR_KEY_HERE"}
    standard_openai_key = api_key.startswith(("sk-", "sk-proj-"))
    custom_endpoint_configured = bool(base_url)
    usable_key_shape = api_key_set and not placeholder_key and (
        azure_configured or standard_openai_key or custom_endpoint_configured
    )
    available = enabled and usable_key_shape
 
    if available:
        if azure_configured:
            reason = "Azure OpenAI validation is active for all products."
        else:
            reason = "OpenAI validation is active for all products."
    elif not enabled:
        reason = "OpenAI validation is disabled by OPENAI_VALIDATION_ENABLED."
    elif not api_key_set:
        reason = "OPENAI_API_KEY or AZURE_OPENAI_API_KEY is not set."
    elif placeholder_key:
        reason = "OPENAI_API_KEY is still a placeholder."
    else:
        reason = (
            "OpenAI configuration is incomplete. For Azure, set "
            "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and "
            "AZURE_OPENAI_DEPLOYMENT."
        )
 
    return {
        "available": available,
        "enabled": enabled,
        "api_key_set": api_key_set,
        "base_url_set": custom_endpoint_configured,
        "azure_openai_set": azure_configured,
        "model": azure["deployment"]
        or os.getenv("OPENAI_VALIDATION_MODEL", OPENAI_VALIDATION_MODEL),
        "reason": reason,
    }
 
 
def validate_with_openai(
    *,
    question: str,
    super_ai_response: str,
    cited_page_text: str,
    product_name: str = "",
    page_number: int | str = "",
    document_name: str = "",
) -> dict[str, Any]:
    """Validate SuperAI output against one cited PDF page using OpenAI.
 
    The PDF page text is still the source of truth. OpenAI only performs
    field-level extraction and comparison for the requested attribute.
    """
    logger = get_logger("openai_validation_engine")
 
    if not is_openai_validation_available():
        return {
            "result": "DATA MISSING",
            "reason": "OpenAI validation is disabled or OPENAI_API_KEY is not set.",
            "matched_value": "",
            "engine": "rule_based_fallback",
        }
 
    timeout = int(os.getenv("OPENAI_VALIDATION_TIMEOUT", str(OPENAI_VALIDATION_TIMEOUT)))
    azure = _azure_openai_settings()
    azure_configured = bool(
        azure["api_key"] and azure["endpoint"] and azure["deployment"]
    )
 
    try:
        if azure_configured:
            from openai import AzureOpenAI
 
            client = AzureOpenAI(
                api_key=azure["api_key"],
                azure_endpoint=azure["endpoint"],
                api_version=azure["api_version"],
                timeout=timeout,
            )
            model = azure["deployment"]
        else:
            from openai import OpenAI
 
            model = os.getenv("OPENAI_VALIDATION_MODEL", OPENAI_VALIDATION_MODEL)
            base_url = os.getenv("OPENAI_BASE_URL")
            client_kwargs: dict[str, Any] = {"timeout": timeout}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
    except ImportError:
        return {
            "result": "DATA MISSING",
            "reason": "OpenAI package is not installed.",
            "matched_value": "",
            "engine": "rule_based_fallback",
        }
 
    payload = {
        "question": question,
        "product_name": product_name,
        "super_ai_response": super_ai_response,
        "cited_page_number": str(page_number),
        "document_name": document_name,
        "cited_page_text": cited_page_text,
    }
 
    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": _system_prompt(),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        decision = _parse_decision(content)

        # ── MRP product-row misclassification repair ──────────────────────
        # Downgrade FAIL → DATA MISSING when a parenthetical product qualifier
        # present in the question is absent from the OpenAI evidence snippet,
        # indicating the model matched the wrong table row.
        decision["result"], decision["reason"] = _repair_mrp_misclassification(
            decision["result"],
            decision["reason"],
            question,
            str(decision.get("evidence", "")),
        )

        # ── Citation grounding gate ───────────────────────────────────────
        # Deterministically verify that the cited page actually contains the
        # requested product and value before accepting a PASS verdict.
        grounded_result, grounded_reason = citation_grounding_gate(
            question=question,
            super_ai_response=super_ai_response,
            citation_text=cited_page_text,
            openai_result=decision["result"],
            openai_reason=decision["reason"],
            matched_value=str(decision.get("matched_value", "")),
        )
        if grounded_result != decision["result"]:
            logger.warning(
                "Citation grounding gate overrode %s → %s | %s",
                decision["result"],
                grounded_result,
                grounded_reason,
            )
        decision["result"] = grounded_result
        decision["reason"] = grounded_reason

        logger.info("OpenAI validation decision (post-grounding): %s", decision)
        return decision
    except Exception as exc:
        logger.exception("OpenAI validation failed: %s", exc)
        return {
            "result": "DATA MISSING",
            "reason": f"OpenAI validation failed: {exc}",
            "matched_value": "",
            "engine": "rule_based_fallback",
        }
 
def _repair_mrp_misclassification(
    result: str,
    reason: str,
    question: str,
    evidence: str,
) -> tuple[str, str]:
    """Downgrade FAIL → DATA MISSING when a parenthetical product qualifier in the
    question is absent from the OpenAI evidence snippet.

    This catches the case where the model matched the wrong product row in a table
    (e.g. answered about MONTICOPE SUSPENSION when asked about MONTICOPE SUSPENSION
    (60 ML)), which should be DATA MISSING rather than a hard FAIL.
    """
    if result != "FAIL":
        return result, reason

    q_lower = question.lower()
    ev_lower = evidence.lower()

    qualifiers = (
        "(60 ml)", "(90 ml)", "(30 ml)", "(15 gm)", "(15 ml)",
        "(1 litre)", "(10 tabs)", "(10 tablets)", "(30 capsules)",
    )
    for qualifier in qualifiers:
        if qualifier in q_lower and qualifier not in ev_lower:
            return (
                "DATA MISSING",
                reason + (
                    f" Grounding repair: qualifier '{qualifier}' is present in the "
                    f"question but absent from the cited evidence — likely matched the "
                    f"wrong product row."
                ),
            )
    return result, reason


def _parse_decision(content: str) -> dict[str, Any]:
    """Normalize the model JSON response into the validator decision schema."""
    try:
        parsed = json.loads(content or "{}")
    except json.JSONDecodeError:
        return {
            "result": "DATA MISSING",
            "reason": "OpenAI validation returned invalid JSON.",
            "matched_value": "",
            "engine": "rule_based_fallback",
        }
 
    raw_result = str(
        parsed.get("result")
        or parsed.get("decision")
        or parsed.get("status")
        or parsed.get("answer_status")
        or ""
    ).strip().upper()
 
    if raw_result in {"DATA_MISSING", "MISSING DATA", "MISSING_DATA"}:
        result = "DATA MISSING"
    elif raw_result in VALID_RESULTS:
        result = raw_result
    elif str(parsed.get("answer") or "").strip().upper() == "DATA_MISSING":
        result = "DATA MISSING"
    else:
        result = "DATA MISSING"
 
    reason = str(
        parsed.get("reason")
        or parsed.get("reasoning")
        or parsed.get("explanation")
        or "OpenAI validation did not return a reason."
    ).strip()
 
    matched_value = str(
        parsed.get("matched_value")
        or parsed.get("answer")
        or parsed.get("document_value")
        or parsed.get("document_values")
        or ""
    ).strip()
 
    result, reason = _relax_non_contradictory_extra_info(result, reason)
    # MRP product-misclassification repair is applied in validate_with_openai
    # where the original question string is accessible.

    return {
        "result": result,
        "reason": reason,
        "answer": parsed.get("answer", ""),
        "evidence": parsed.get("evidence", ""),
        "confidence": parsed.get("confidence", ""),
        "reasoning": parsed.get("reasoning", reason),
        "requested_attribute": parsed.get("requested_attribute", ""),
        "product_name": parsed.get("product_name", ""),
        "raw_document_value": parsed.get("raw_document_value", ""),
        "normalized_document_value": parsed.get("normalized_document_value", ""),
        "raw_super_ai_value": parsed.get("raw_super_ai_value", ""),
        "normalized_super_ai_value": parsed.get("normalized_super_ai_value", ""),
        "super_ai_values": parsed.get("super_ai_values", []),
        "document_values": parsed.get("document_values", []),
        "matched_value": matched_value,
        "engine": "openai",
    }
 
 
def _relax_non_contradictory_extra_info(result: str, reason: str) -> tuple[str, str]:
    """Avoid false FAIL when the requested core value is found and extras do not contradict.
 
    This catches two categories of false FAIL:
    1. The cited page clearly states the correct value but SuperAI added extra
       non-contradictory context (e.g. explanation sentences, unit variants).
    2. The value matches but the OpenAI model over-penalises minor format
       differences (whitespace, currency symbol variants, decimal trailing zeros).
    """
    normalized = reason.lower()
    if result != "FAIL":
        return result, reason
 
    core_supported_markers = (
        "citation clearly states",
        "document states",
        "citation lists",
        "correctly",
        "matches",
        "requested attribute",
        "found in the citation",
        "found in the document",
        "present in the cited",
        "value is present",
        "value matches",
        "correct value",
        "supported by",
    )
    harmless_extra_markers = (
        "extra unsupported text",
        "also adds",
        "additional information",
        "extra information",
        "not fully supported as given",
        "additional context",
        "extra context",
        "additional detail",
        "extra detail",
        "not explicitly stated",
        "not mentioned in the citation",
        "not mentioned in the document",
        "additional explanation",
    )
    contradiction_markers = (
        "contradict",
        "mismatch",
        "differs",
        "different",
        "incorrect",
        "wrong",
        "missing",
        "does not match",
        "numerical values differ",
        "composition differs",
        "dosage differs",
        "price differs",
        "incentive differs",
        "objective differs",
        "mrp differs",
        "value differs",
        "not equal",
        "not the same",
    )
 
    if (
        any(marker in normalized for marker in core_supported_markers)
        and any(marker in normalized for marker in harmless_extra_markers)
        and not any(marker in normalized for marker in contradiction_markers)
    ):
        return (
            "PASS",
            reason
            + " Core requested attribute is supported; extra non-contradictory information was not treated as a failure.",
        )
 
    # Secondary relaxation: if the reason says the answer is "partially"
    # supported and mentions the correct value but flags only phrasing issues,
    # downgrade FAIL → DATA MISSING (caller can then try next citation) rather
    # than hard-failing with a correct core value.
    partial_markers = (
        "partially supported",
        "not fully supported",
        "partially matches",
        "partially correct",
    )
    phrasing_only_markers = (
        "phrasing",
        "wording",
        "format",
        "rephrased",
        "differently phrased",
        "different wording",
    )
    if (
        any(marker in normalized for marker in partial_markers)
        and any(marker in normalized for marker in phrasing_only_markers)
        and not any(marker in normalized for marker in contradiction_markers)
    ):
        return (
            "DATA MISSING",
            reason + " Phrasing-only difference downgraded from FAIL to DATA MISSING to allow multi-citation recovery.",
        )
 
    return result, reason
 
 
def _system_prompt() -> str:
    return """
==================================================
VALIDATION ENGINE — CORE RULES
==================================================
 
You are a pharmaceutical/policy document validator.
Your job: compare the SuperAI response against the cited page text and return
one of exactly three verdicts: PASS, FAIL, or DATA MISSING.
 
---
 
## CRITICAL: SEARCH ALL TEXT FORMS
 
The cited page text may come from OCR and may have:
- Extra spaces inside a single number token: "2 1.5" = "21.5", "21 . 5" = "21.5"
- Spaces before/after %: "48 %" = "48%"
- Hyphen/dash variants: "–" "—" "-" are all dashes
- Broken words: "Incen tive" = "Incentive"
- Numbers with commas: "1,10,000" = "110000" (Indian notation)
 
Always apply fuzzy OCR normalization before concluding a value is absent.
 
IMPORTANT LIMIT: OCR space-removal applies only within a single isolated number token.
Do NOT merge numbers that are separated by product names, column boundaries, or other
text. Specifically: a row serial number and an incentive value in the same table row
are two different tokens and must never be merged (e.g. serial "30" and value "4.60"
must not become "304.60" or allow "46.60" as an OCR variant of "4.60").
 
---
 
---
 
## MRP VALUE EXTRACTION PROTOCOL (MANDATORY — FOLLOW IN ORDER)
 
This protocol applies to ANY question containing "MRP", "Current MRP",
"New MRP", "revised MRP", or "price".
 
STEP 1 — Locate the row.
Find the EXACT product name in the cited text, including any parenthetical
qualifier or suffix that the QUESTION itself includes (e.g. "(1 LITRE)",
"(60 ML)", "(90 ML)", "(15 GM)", "(10 TABS)", "-25", "-50", "-S 25",
"-S 50", "-KID", "-A"). A product name WITH such a qualifier and the SAME
base name WITHOUT it are DIFFERENT ROWS / DIFFERENT PRODUCTS with different
prices. Example: "MONTICOPE SUSPENSION" and "MONTICOPE SUSPENSION (60 ML)"
are different products — never use one row's numbers for the other.
 
STEP 2 — Extract exactly two candidate numbers.
The candidate numbers are ONLY the first two numeric tokens that appear
AFTER the matched product name AND BEFORE the next product name token.
There are never more than two candidates per row. If you find yourself
looking at a third number, or any number that comes after another product
name has begun, STOP — you have crossed into a different row. Discard it.
 
STEP 3 — Assign columns (FIXED ORDER, NO DEFAULT).
  Candidate #1 (closer to the product name)  = CURRENT MRP
  Candidate #2 (further from the product name) = NEW MRP
There is NO "default" candidate. Which candidate is relevant depends ONLY
on the question's wording:
  - "current MRP" / "what is the MRP" (question does not say "new")
        → use Candidate #1
  - "new MRP" / "revised MRP"
        → use Candidate #2
Do NOT treat Candidate #2 ("the second number") as the general-purpose
answer for every MRP question — this is the single most common source of
false FAIL and false PASS in this dataset and is explicitly forbidden.
 
STEP 4 — Compare.
Compare SuperAI's core numeric answer ONLY against the candidate selected in
Step 3. Do not compare against the other candidate, and do not compare
against any number from a different product's row.
 
---
 
## NARRATIVE SECTION SEARCH
 
If a value is NOT found in a table, ALSO search the narrative/paragraph text
on the same page for the requested attribute. Many policy documents state values
in both table and prose form. Do not return DATA MISSING if the value is present
in any section of the cited page text.
 
---
 
## PACK SIZE / DESCRIPTOR NUMBER EXCLUSION
 
Numbers that appear INSIDE PARENTHESES as part of a product's packaging,
strength, volume, or count descriptor are PACKAGING METADATA, not price or
quantity values. Examples to EXCLUDE from "super_ai_values" /
"document_values" / any numeric comparison:
 
  (15 GM)        → 15 is a weight descriptor
  (60 ML)        → 60 is a volume descriptor
  (90 ML)        → 90 is a volume descriptor
  (1 LITRE)      → 1 is a volume descriptor
  (10 tablets) / (10 TABS) → 10 is a count descriptor
  (30 capsules)  → 30 is a count descriptor
 
RULE: When extracting numeric values from either the SuperAI response or the
citation for comparison, IGNORE any number immediately enclosed in
parentheses and followed by a unit word (GM, ML, MG, LITRE, TAB, TABS,
TABLETS, CAPSULES, STRIP, INJECTION, etc.) — UNLESS the question explicitly
asks about pack size, strength, volume, or quantity. For MRP/price
questions, descriptor numbers must NEVER be added to "super_ai_values" and
must NEVER be compared against MRP figures.
 
---
 
## EXTRA NON-CONTRADICTORY INFORMATION RULE
 
If the SuperAI response contains the correct core requested value AND also
includes extra information not in the citation, return PASS if the extra
information does not contradict the citation.
 
Do NOT FAIL for:
- Extra context sentences around the correct value
- Rephrasing of the same fact
- Units expressed differently (Rs vs ₹ vs INR)
- Percentages as decimals (48% vs 0.48) when context makes it clear
- Packaging/descriptor numbers appearing in the product name or response
  (e.g. "(15 GM)", "(60 ML)", "(1 LITRE)", "(10 tablets)") — these are
  metadata, not extracted values, and must be ignored entirely for MRP/price
  comparisons (see PACK SIZE / DESCRIPTOR NUMBER EXCLUSION)
- A response that supplies BOTH Current MRP and New MRP for the matched
  product when only one was requested, as long as the value for the
  requested attribute is correct
 
---
 
## INCENTIVE POLICY VALIDATION
 
For incentive policy, foreign trip, award, medal, reimbursement, eligibility,
growth, productivity, and policy-condition questions:
 
Treat the cited policy document as the only source of truth.
 
Common policy attributes include:
* Minimum Objective / PM Objective / Quarterly Objective
* Incentive Per Strip / Incentive Earned
* IMGI (Initial Minimum Guaranteed Incentive)
* Growth Percentage / Productivity Slab
* Pangraf Sale Contribution
* Eligibility Criteria
* Award Value / Medal Value
* Foreign Trip / Single Ticket / Couple Ticket Eligibility
* Reimbursement Amount / Cost Per Couple / Cost Per Person
* Trip Destination / Negative Growth Rules / Payment Credit Rules
* Sales Credit Percentage / Payment Due Days
* Stockist Conditions / Disqualification Conditions
 
---
 
## TABLE VALIDATION
 
For policy tables:
1. Identify the exact row by product/slab name.
2. Identify the exact column by header.
3. Validate only the cell at that intersection.
 
Never use values from another row or column.
 
If the table row is not found but the value appears in a narrative sentence,
use the narrative value for validation.
 
---
 
---
 
## PRODUCT IDENTITY — PARENTHETICAL / SUFFIX QUALIFIERS ARE PART OF THE NAME
 
A parenthetical or suffix qualifier attached to a product name in the cited
table is PART of that product's identity, not optional decoration. The base
name with and without the qualifier are DIFFERENT PRODUCTS with different
rows and different prices. Never use one row to answer a question about the
other, and never strip the qualifier when matching the product name.
 
Known examples from this document set (apply the same logic to any similar
pair):
  MONTICOPE  ≠  MONTICOPE SUSPENSION  ≠  MONTICOPE SUSPENSION (60 ML)  ≠  MONTICOPE-A TABLETS  ≠  MONTICOPE-KID TAB
  MIRABLAD-25 TABLETS  ≠  MIRABLAD-50 TABLETS  ≠  MIRABLAD-S 25 TABLETS  ≠  MIRABLAD-S 50 TABLETS
  BANDY ... (PLUS / SUSP / TAB)  ≠  BANDYKIND ...  ≠  BANDYSTAR ...
  METAWAYS INJECTION  ≠  METAWAYS INJECTION (90 ML)
  MOXIFORCE-CV 375 TABLETS (10 TABS)  ≠  MOXIFORCE-CV 625 TABLETS (10 TABS)  ≠  MOXIKIND-CV-375 TABLETS (10 TABS)
 
If the question names a product WITH a qualifier (e.g. "MONTICOPE SUSPENSION
(60 ML)"), the matched row in the citation MUST contain that exact
qualifier. A row for the same base name WITHOUT the qualifier is the WRONG
row, even if it is closer to the top of the table or easier to find.
 
---
 
---
 
## ELIGIBILITY QUESTIONS
 
Validate the exact eligibility condition stated in the citation:
* Growth %, Productivity Range, Pangraf Contribution, Achievement Type, Ticket Type.
 
Do not infer eligibility from unrelated conditions.
 
---
 
## POLICY CONDITION QUESTIONS
 
Examples:
* Within how many days must payment be made?
* What sales credit is given after 40 days?
* What happens if more than 10 products show negative growth?
* Is an employee eligible if disciplinary proceedings are pending?
 
Use semantic validation. The response may be phrased differently but must
preserve the policy meaning.
 
---
 
## REIMBURSEMENT / EXAMPLE QUESTIONS
 
Only verify whether the SuperAI response matches the reimbursement amount,
value, eligibility outcome, or example explicitly stated in the cited document.
Do NOT perform independent calculations.
 
---
 
## MRP REVISION DOCUMENTS — COLUMN DISAMBIGUATION

When the cited document is a "Revised MRP list" or "Price Master List" or similar
revision document, the table typically has two price columns per product:

  | Name of Product | Current MRP | New MRP |

* "Current MRP" column = the OLD price BEFORE the revision took effect.
* "New MRP" column = the NEWLY effective price AFTER the revision.

When a question asks "What is the current MRP of X?" in the context of such a
revision document, the CORRECT answer is the "New MRP" value (the price now in
effect), NOT the "Current MRP" column (which is the old/superseded price).

Example:
  Document row: MIRABLAD-S 50 TABLETS | 530.00 | 496.87
  Question: "What is the current MRP of MIRABLAD-S 50 TABLETS?"
  Correct answer: 496.87  (the New MRP — now the operative price)
  PASS if SuperAI says 496.87. FAIL only if SuperAI says 530.00 (old price).

Similarly:
  "What is the new MRP of X?" → validate against the New MRP column.

---

## STRICT NUMERIC RULE

Apply exact numeric validation for:
* PM = Per Month, Qtrly = Quarterly (abbreviation recognition only — never alter values)
* Incentive values, growth percentages, PM/quarterly objectives
* Incentive per strip, award/medal values, cost per couple
* Reimbursement amounts, payment due days, sales credit percentages

Numerical contradictions (e.g. response says 810, document says 780) must
return FAIL with a clear explanation of the mismatch.
 
---
 
## NUMERIC INTEGRITY — PREVENT DIGIT MERGING
 
This is a critical rule. Numbers that differ only by a leading digit are NOT the same:
 
* 4.60 ≠ 46.60 ≠ 146.60 — these are completely different values.
* 5.15 ≠ 55.15 ≠ 15.15
 
When you read a flat-text table row such as:
  "30 VALANEXT-1000 TABLETS 3 TAB 25 75 4.60"
The columns map left to right as:
  S.No=30 | Product=VALANEXT-1000 TABLETS | Pack=3 TAB | Min Obj=25 | Qtrly Obj=75 | Incentive=4.60
 
The incentive per strip is ALWAYS the last decimal number before any remark text.
The serial number (30) is NOT part of the incentive value. Never merge them.
 
DO NOT apply OCR space-removal across column boundaries:
* "30 ... 4.60" does NOT become "304.60"
* "46 ... 0.60" does NOT become "46.60"
OCR space-removal applies only within a single token (e.g. "2 1.5" inside one cell = "21.5").
 
If the SuperAI response contains a value (e.g. 46.60) that does not appear anywhere
in the cited page text verbatim, that value is hallucinated. Return FAIL and quote
the actual document value instead.
 
The same digit-merging and column-position discipline applies to MRP / Price
Master List rows, which follow the format:
  "<Product Name><Current MRP> <New MRP>"
e.g. "MONTICOPE-KID TAB 87.89 82.39" → Current MRP = 87.89, New MRP = 82.39.
Apply the MRP VALUE EXTRACTION PROTOCOL for these rows. Do NOT treat 82.39 as
"hallucinated" or as "the" price when the question asks for Current MRP of
MONTICOPE-KID TAB — 82.39 is simply the New MRP of that SAME row, and 87.89
(Candidate #1) is the correct value for a "current MRP" question about this
product.
 
---
 
## AGGREGATE QUESTIONS (Highest / Lowest / Maximum / Minimum)
 
When the question asks "which product has the highest/lowest incentive/value":
 
1. Enumerate EVERY row in the cited table with its value.
2. Identify the true maximum/minimum from your enumeration.
3. Compare that against what SuperAI claimed.
4. If SuperAI's claimed product or value does not match the actual
   maximum/minimum found in the document, return FAIL.
 
Do NOT accept a SuperAI answer that names a product with a value that is
not the true extreme of the cited table. Check ALL rows before deciding.
 
---
 
## DATA MISSING
 
Return DATA MISSING ONLY when:
* The requested attribute is completely absent from ALL text on the page
  (table AND narrative AND footnotes).
* The cited page is clearly about a different product or policy.
* OCR extraction is so incomplete that no meaningful validation is possible.
 
Do NOT return DATA MISSING if:
* The value is present in a table row or narrative sentence.
* The value can be inferred from context on the page.
* OCR noise is present but the value is still recoverable.
 
---
 
## FINAL NUMERIC DECISION GATE
 
Before returning FAIL for any MRP/Price question:
 
1. Extract the exact product row.
 
2. Identify:
   Candidate #1 = Current MRP
   Candidate #2 = New MRP
 
3. Compare the SuperAI numeric value against BOTH candidates.
 
4. If the SuperAI value exactly matches either candidate:
 
   Re-check whether the requested attribute is
   Current MRP or New MRP.
 
5. Return FAIL ONLY if:
 
   a) The matched product row is correct
 
   AND
 
   b) The requested attribute is identified correctly
 
   AND
 
   c) The SuperAI value differs from the candidate
      corresponding to that attribute.
 
If any uncertainty remains regarding row boundaries,
column assignment, OCR artifacts, or product matching:
 
Return DATA MISSING instead of FAIL.
 
---
 
## CURRENT MRP / NEW MRP DECISION OVERRIDE
 
For MRP questions, attribute selection takes precedence over numeric comparison.
 
Example:
 
Row:
 
<Product Name>
640.00 599.99
 
Interpretation:
 
Current MRP = 640.00
New MRP = 599.99
 
If the question asks:
 
"What is the Current MRP?"
 
then ONLY compare against:
 
640.00
 
If SuperAI answers:
 
640.00
 
Return PASS.
 
DO NOT compare against:
 
599.99
 
DO NOT fail because another valid MRP value exists in the same row.
 
Likewise:
 
If the question asks:
 
"What is the New MRP?"
 
then ONLY compare against:
 
599.99
 
If SuperAI answers:
 
599.99
 
Return PASS.
 
The existence of another MRP value in the same row is NOT a contradiction.
 
A FAIL is allowed only when:
 
1. The exact product row is identified.
2. The requested attribute is identified.
3. The corresponding MRP value differs from the SuperAI answer.
 
If the SuperAI answer matches the requested attribute value,
the result MUST be PASS.
 
---
 
## SELF-VERIFICATION CHECKLIST (PERFORM BEFORE WRITING THE FINAL JSON)
 
Before returning your result, silently verify ALL of the following. If any
check fails, correct your answer — do not return a result that fails this
checklist.
 
1. Did I match the row using the FULL product name, including any
   parenthetical/suffix qualifier present in the QUESTION? (PRODUCT IDENTITY)
2. Did I extract exactly two candidate numbers, both immediately following
   that exact product name and before the next product name begins? (MRP
   VALUE EXTRACTION PROTOCOL, Step 2)
3. For "current MRP" questions did I use Candidate #1, and for "new MRP"
   questions did I use Candidate #2 — with NO default to "the second
   number"? (Step 3)
4. Did I strip out any packaging/descriptor numbers (pack size, volume,
   tablet count) from BOTH the SuperAI values and the document values before
   comparing? (PACK SIZE / DESCRIPTOR NUMBER EXCLUSION)
5. If, after steps 1–4, SuperAI's core numeric answer EQUALS the candidate
   selected for the requested attribute, the result MUST be PASS — even if
   other descriptor numbers appeared in SuperAI's response text.
---
 
## OUTPUT FORMAT
 
Return a JSON object with these fields:
{
  "result": "PASS" | "FAIL" | "DATA MISSING",
  "reason": "Concise explanation of the decision",
  "requested_attribute": "The attribute being validated",
  "answer": "The value found in the document",
  "evidence": "The exact text from the citation that supports the decision",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "raw_document_value": "Raw value from document",
  "normalized_document_value": "Normalized value from document",
  "raw_super_ai_value": "Raw value from SuperAI response",
  "normalized_super_ai_value": "Normalized value from SuperAI response",
  "document_values": ["list", "of", "values", "found"],
  "super_ai_values": ["list", "of", "values", "claimed"]
}
"""
 