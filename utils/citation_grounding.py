"""Citation-grounded validation helpers.

These functions deterministically verify that a cited PDF page actually
contains the product, attribute, and value claimed in a SuperAI response.
They are applied as a post-processing gate AFTER the OpenAI decision is
received: if OpenAI returned PASS but the citation text does not contain
the requested product, the result is overridden to FAIL or DATA MISSING.

Grounding check order
---------------------
1. Citation text present?          → else DATA MISSING
2. Product extractable?            → else skip gate (trust OpenAI)
3. Product in citation?            → else FAIL
4. Attribute in citation?          → else DATA MISSING
5. matched_value in citation?      → else FAIL   (only when value known)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from utils.logger import get_logger

_logger = get_logger("citation_grounding")

# ─────────────────────────────────────────────────────────────────────────────
# Attribute pattern table  (order matters — more specific first)
# ─────────────────────────────────────────────────────────────────────────────

_ATTRIBUTE_PATTERNS: list[tuple[str, str]] = [
    (r"new\s+mrp", "NEW_MRP"),
    (r"current\s+mrp", "CURRENT_MRP"),
    (r"(?:revised\s+)?mrp", "MRP"),
    (r"incentive\s+per\s+(?:strip|tablet|tab|unit)", "INCENTIVE_PER_STRIP"),
    (r"incentive", "INCENTIVE"),
    (r"(?:quarterly|qtrly)[./]?\s*(?:pmr|minimum\s+objective|objective)", "QUARTERLY_OBJECTIVE"),
    (r"(?:pm|pmr)\s*(?:/\s*pmr)?\s*(?:minimum\s+)?objective", "PM_OBJECTIVE"),
    (r"quarterly\s+(?:minimum|objective)", "QUARTERLY_OBJECTIVE"),
    (r"minimum\s+objective", "PM_OBJECTIVE"),
    (r"price", "MRP"),
]

# Synonyms searched inside the citation to confirm an attribute is present.
# An empty list means "always consider the attribute present" (GENERAL catch-all).
_ATTRIBUTE_SYNONYMS: dict[str, list[str]] = {
    "NEW_MRP":             ["new mrp", "revised mrp", "new price"],
    "CURRENT_MRP":         ["current mrp", "mrp", "price"],
    "MRP":                 ["mrp", "price", "rate"],
    "INCENTIVE_PER_STRIP": ["incentive", "strip"],
    "INCENTIVE":           ["incentive"],
    "QUARTERLY_OBJECTIVE": ["quarterly", "qtrly", "pmr", "objective"],
    "PM_OBJECTIVE":        ["pm", "pmr", "objective", "minimum"],
    "GENERAL":             [],
}

# Words that carry no discriminating power in product matching
_PRODUCT_STOPWORDS: frozenset[str] = frozenset({
    "tablets", "tablet", "tab", "tabs",
    "injection", "inj",
    "capsules", "capsule", "cap", "caps",
    "suspension", "syrup", "drops",
    "cream", "gel", "ointment", "solution",
    "eye", "ear", "nasal", "oral",
    "the", "and", "for", "with",
    "mg", "ml", "gm", "g",
})

# Minimum character length for a product token to be considered "significant"
_MIN_TOKEN_LEN = 3


# ─────────────────────────────────────────────────────────────────────────────
# Question decomposition
# ─────────────────────────────────────────────────────────────────────────────

def extract_product_from_question(question: str) -> str:
    """Extract the product name from a question.

    Handles common pharma QA templates:
      "What is the <attribute> for <PRODUCT>?"
      "What is the <attribute> of <PRODUCT>?"

    Product names in this corpus are UPPERCASE with digits, hyphens,
    periods, parenthetical qualifiers, and spaces.

    Returns an empty string when no confident match is found.
    """
    # Patterns: capture everything after "for " or "of " until "?" or EOL
    _PRODUCT_RE = re.compile(
        r"\b(?:for|of)\s+([A-Z][A-Z0-9 \-\.\(\)/]+?)(?:\?|$)",
        re.IGNORECASE,
    )
    q = question.strip()
    for m in _PRODUCT_RE.finditer(q):
        candidate = m.group(1).strip().rstrip("?").strip()
        # Require at least one "real" uppercase token (≥3 letters)
        if re.search(r"[A-Z]{3}", candidate):
            _logger.debug("Extracted product %r from question", candidate)
            return candidate
    _logger.debug("Could not extract product from question: %r", question)
    return ""


def extract_attribute_from_question(question: str) -> str:
    """Return the canonical attribute type requested in the question.

    Returns one of: NEW_MRP, CURRENT_MRP, MRP, INCENTIVE_PER_STRIP,
    INCENTIVE, QUARTERLY_OBJECTIVE, PM_OBJECTIVE, GENERAL.
    """
    norm = question.lower().strip()
    for pattern, attr_type in _ATTRIBUTE_PATTERNS:
        if re.search(pattern, norm):
            _logger.debug("Attribute %r matched pattern %r", attr_type, pattern)
            return attr_type
    return "GENERAL"


# ─────────────────────────────────────────────────────────────────────────────
# Text normalisation utilities
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, NFKD-normalise, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _significant_tokens(product: str) -> list[str]:
    """Return the discriminating lowercase tokens from a product name."""
    raw = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", product.lower())
    return [t for t in raw if t not in _PRODUCT_STOPWORDS and len(t) >= _MIN_TOKEN_LEN]


def _strip_commas(value: str) -> str:
    """Remove comma thousand-separators (Indian notation)."""
    return re.sub(r"(?<=\d),(?=\d)", "", value)


def _bare_number(value: str) -> str:
    """Remove currency symbols, unit labels, and spaces from a value string."""
    return re.sub(r"[₹$€a-z\s,]", "", value.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Core grounding checkers
# ─────────────────────────────────────────────────────────────────────────────

def verify_product_exists_in_citation(product: str, citation_text: str) -> bool:
    """Return True when the product name is found in the citation.

    Uses a progressive strategy:
      1. Exact normalized substring match.
      2. All significant tokens present (ordered scan, ≥2 tokens required).
      3. Single most-distinctive token (≥5 chars) present as last resort.
    """
    if not product or not citation_text:
        _logger.debug("verify_product_exists: empty input — False")
        return False

    norm_cit = _normalize(citation_text)
    norm_prod = _normalize(product)

    # 1. Exact substring
    if norm_prod in norm_cit:
        _logger.debug("Product EXACT match: %r", product)
        return True

    tokens = _significant_tokens(product)
    if not tokens:
        _logger.debug("Product has no significant tokens: %r — False", product)
        return False

    # 2. All significant tokens present (anywhere in citation, in sequence)
    if len(tokens) >= 2:
        pos = 0
        all_found = True
        for tok in tokens:
            idx = norm_cit.find(tok, pos)
            if idx == -1:
                all_found = False
                break
            pos = idx
        if all_found:
            _logger.debug("Product TOKEN match: %r (tokens=%s)", product, tokens)
            return True

    # 3. Most distinctive token (≥5 chars)
    distinctive = [t for t in tokens if len(t) >= 5]
    if distinctive and distinctive[0] in norm_cit:
        _logger.debug("Product DISTINCTIVE-TOKEN match: %r → %r", product, distinctive[0])
        return True

    _logger.debug("Product NOT found: %r", product)
    return False


def verify_attribute_exists_in_citation(attribute_type: str, citation_text: str) -> bool:
    """Return True when the attribute or its synonyms appear in the citation.

    GENERAL always returns True (no attribute constraint).
    All other types require at least one synonym token to be found.
    """
    synonyms = _ATTRIBUTE_SYNONYMS.get(attribute_type, [])
    if not synonyms:
        # GENERAL: no gating needed regardless of citation content
        return True

    if not citation_text:
        return False

    norm = _normalize(citation_text)
    found = any(s in norm for s in synonyms)
    _logger.debug(
        "Attribute %r in citation: %s (synonyms checked=%s)",
        attribute_type, found, synonyms,
    )
    return found


def verify_value_supported_by_citation(
    value: str,
    product: str,  # kept for audit logging; not used for row-scoping
    citation_text: str,
) -> bool:
    """Return True when the numeric/string value appears anywhere in the citation.

    Rationale: Table structure in merged PDF text is hard to parse
    deterministically.  The product-existence check already ensures the page
    is about the right entity; value presence anywhere on the page is a
    necessary (though not sufficient) condition for grounding.  Column
    assignment (Current MRP vs New MRP) is still delegated to OpenAI.

    Normalisation applied:
      - Indian comma notation:  1,10,000 → 110000
      - Currency stripping:     ₹ 810 → 810
      - Whitespace collapse
    """
    if not value or not citation_text:
        return False

    norm_cit = _normalize(citation_text)
    norm_val = _normalize(str(value))

    # Direct match
    if norm_val in norm_cit:
        _logger.debug("Value EXACT match: %r (product=%r)", value, product)
        return True

    # Indian comma notation stripped
    no_comma = _strip_commas(norm_val)
    if no_comma != norm_val and no_comma in _strip_commas(norm_cit):
        _logger.debug("Value COMMA-STRIPPED match: %r → %r", value, no_comma)
        return True

    # Bare number (remove currency, units, spaces)
    bare_val = _bare_number(norm_val)
    bare_cit = _bare_number(norm_cit)
    if bare_val and len(bare_val) >= 2 and bare_val in bare_cit:
        _logger.debug("Value BARE-NUMBER match: %r → %r", value, bare_val)
        return True

    _logger.debug("Value NOT found: %r (product=%r)", value, product)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Full table-row grounding (composite check — used by unit tests + gate)
# ─────────────────────────────────────────────────────────────────────────────

def validate_table_row_grounding(
    product: str,
    attribute_type: str,
    claimed_value: str,
    citation_text: str,
) -> dict[str, Any]:
    """Run all three grounding checks and return a structured audit result.

    Returns
    -------
    dict with keys:
      grounded       – True only when all three checks pass
      product_found  – bool
      attribute_found – bool
      value_supported – bool
      reason         – human-readable audit trail
    """
    product_found = verify_product_exists_in_citation(product, citation_text)
    attribute_found = verify_attribute_exists_in_citation(attribute_type, citation_text)
    value_supported = (
        verify_value_supported_by_citation(claimed_value, product, citation_text)
        if (product_found and claimed_value)
        else False
    )

    grounded = product_found and attribute_found and (
        value_supported if claimed_value else True
    )

    parts: list[str] = []
    parts.append(
        f"Product '{product}' {'FOUND' if product_found else 'NOT FOUND'} in citation."
    )
    parts.append(
        f"Attribute '{attribute_type}' {'FOUND' if attribute_found else 'NOT FOUND'} in citation."
    )
    if claimed_value:
        parts.append(
            f"Value '{claimed_value}' "
            f"{'SUPPORTED' if value_supported else 'NOT SUPPORTED'} by citation."
        )

    reason = " ".join(parts)
    _logger.info(
        "GROUNDING product=%r attr=%r value=%r → grounded=%s | %s",
        product, attribute_type, claimed_value, grounded, reason,
    )
    return {
        "grounded": grounded,
        "product_found": product_found,
        "attribute_found": attribute_found,
        "value_supported": value_supported,
        "reason": reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public gate — called in validate_with_openai after _parse_decision
# ─────────────────────────────────────────────────────────────────────────────

def citation_grounding_gate(
    *,
    question: str,
    super_ai_response: str,  # noqa: ARG001  (reserved for future use)
    citation_text: str,
    openai_result: str,
    openai_reason: str,
    matched_value: str = "",
) -> tuple[str, str]:
    """Apply deterministic citation grounding to an OpenAI PASS verdict.

    Only PASS verdicts are gated.  FAIL and DATA MISSING are returned as-is
    because they are already conservative outcomes.

    Grounding logic
    ---------------
    1. Empty citation         → DATA MISSING  (can't verify anything)
    2. No product extracted   → skip gate     (trust OpenAI)
    3. Product absent         → FAIL
    4. Attribute absent       → DATA MISSING
    5. matched_value absent   → FAIL          (only when value is known)

    Returns
    -------
    (result, reason) – potentially overridden values.
    """
    if openai_result != "PASS":
        return openai_result, openai_reason

    # ── Guard 1: citation text must be present ────────────────────────────
    if not citation_text or not citation_text.strip():
        _logger.warning("Grounding gate: empty citation text → DATA MISSING")
        return (
            "DATA MISSING",
            (
                "Citation text is unavailable; grounding cannot be verified. "
                + openai_reason
            ),
        )

    product = extract_product_from_question(question)
    attribute_type = extract_attribute_from_question(question)

    _logger.info(
        "Grounding gate: product=%r attr=%r matched_value=%r",
        product, attribute_type, matched_value,
    )

    # ── Guard 2: product must be extractable ─────────────────────────────
    if not product:
        _logger.info("Grounding gate: could not extract product — gate skipped.")
        return openai_result, openai_reason

    # ── Guard 3: product must appear in citation ──────────────────────────
    if not verify_product_exists_in_citation(product, citation_text):
        msg = (
            f"Citation grounding FAILED: product '{product}' is not present in the "
            f"cited page. A PASS verdict requires the citation to contain the "
            f"requested product. Original OpenAI reason: {openai_reason}"
        )
        _logger.warning("Grounding gate override PASS → FAIL | %s", msg)
        return "FAIL", msg

    # ── Guard 4: attribute must appear in citation ────────────────────────
    if not verify_attribute_exists_in_citation(attribute_type, citation_text):
        msg = (
            f"Citation grounding FAILED: attribute '{attribute_type}' evidence not "
            f"found in the cited page. Cannot confirm grounding without the relevant "
            f"attribute. Original OpenAI reason: {openai_reason}"
        )
        _logger.warning("Grounding gate override PASS → DATA MISSING | %s", msg)
        return "DATA MISSING", msg

    # ── Guard 5: claimed value must appear in citation ────────────────────
    if matched_value:
        if not verify_value_supported_by_citation(matched_value, product, citation_text):
            msg = (
                f"Citation grounding FAILED: value '{matched_value}' not found in "
                f"the cited page for product '{product}'. The answer value is not "
                f"evidenced by the citation. Original OpenAI reason: {openai_reason}"
            )
            _logger.warning("Grounding gate override PASS → FAIL | %s", msg)
            return "FAIL", msg

    _logger.info("Grounding gate: all checks PASSED for product=%r", product)
    return openai_result, openai_reason
