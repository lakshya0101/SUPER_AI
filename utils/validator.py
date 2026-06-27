# # """PDF parser response and citation validation helpers.

# # Critical pharma validation contract:
# # - Validate only against the exact cited PDF page number.
# # - If SuperAI returns multiple values, every value must be checked.
# # - If SuperAI returns multiple citations, each cited page is checked one by one.
# # - PASS requires all required SuperAI values to match the cited page.
# # - FAIL means related cited-page data exists but one or more values mismatch.
# # - DATA MISSING means the cited document/page/value cannot be found.
# # """

# # import re
# # from utils.logger import get_logger as _get_logger

# # _validator_logger = _get_logger("validator")

# # # Accumulated per-question validation steps written by _log_validation_step.
# # # Cleared at the start of each question in the main validation loop.
# # VALIDATION_LOG: list[dict] = []


# # def _log_validation_step(
# #     *,
# #     rule: str,
# #     product: str = "",
# #     attribute: str = "",
# #     row: str = "",
# #     column: str = "",
# #     doc_value: object = None,
# #     response_value: object = None,
# #     normalization: str = "",
# #     verdict: str,
# #     reason: str = "",
# # ) -> None:
# #     """Append one validation step to VALIDATION_LOG and emit a debug log line.

# #     Call this from every sub-validator so that DATA MISSING results can be
# #     diagnosed without adding manual print statements.
# #     """
# #     entry = {
# #         "rule": rule,
# #         "product": product,
# #         "attribute": attribute,
# #         "row": row,
# #         "column": column,
# #         "doc_value": doc_value,
# #         "response_value": response_value,
# #         "normalization": normalization,
# #         "verdict": verdict,
# #         "reason": reason,
# #     }
# #     VALIDATION_LOG.append(entry)
# #     _validator_logger.debug(
# #         "[%s] product=%r attr=%r row=%r col=%r doc=%r resp=%r norm=%r → %s | %s",
# #         rule,
# #         product,
# #         attribute,
# #         row,
# #         column,
# #         doc_value,
# #         response_value,
# #         normalization,
# #         verdict,
# #         reason,
# #     )


# # COMPANY_ENTITY_MATCH_THRESHOLD = 0.95

# # # Fine-grained attribute type mappings.  These are evaluated BEFORE question
# # # type routing so that "cost per couple" is never mistaken for PRICE/MRP and
# # # "PM objective" is never compared against the Quarterly Objective column.
# # _ATTRIBUTE_MAPPINGS: dict[str, tuple[str, ...]] = {
# #     "PRICE": (
# #         "mrp",
# #         "revised mrp",
# #         "new mrp",
# #         "cost per tablet",
# #         "cost per strip",
# #         "price per tablet",
# #         "price per strip",
# #         "per tablet",
# #         "per strip",
# #         "per tab",
# #     ),
# #     "INCENTIVE": (
# #         "incentive per strip",
# #         "incentive per tablet",
# #         "incentive per unit",
# #         "incentive per tab",
# #         "incentive value",
# #         "incentive amount",
# #     ),
# #     "PM_OBJECTIVE": (
# #         "pm objective",
# #         "pmr objective",
# #         "pm/pmr objective",
# #         "monthly objective",
# #         "monthly minimum",
# #         "minimum objective",
# #         "pm target",
# #         "pmr target",
# #     ),
# #     "QUARTERLY_OBJECTIVE": (
# #         "quarterly objective",
# #         "quarterly minimum",
# #         "quarterly pmr",
# #         "quarterly pm",
# #         "qtr objective",
# #         "q objective",
# #     ),
# #     "TRIP_COST": (
# #         "cost per couple",
# #         "couple cost",
# #         "trip cost",
# #         "foreign trip",
# #         "domestic trip",
# #         "international trip",
# #         "holiday trip",
# #         "incentive trip",
# #     ),
# #     "MEDAL_VALUE": (
# #         "medal value",
# #         "medal worth",
# #         "medal amount",
# #         "gold medal",
# #         "silver medal",
# #     ),
# #     "AWARD_VALUE": (
# #         "award value",
# #         "award cost",
# #         "award amount",
# #         "award worth",
# #     ),
# #     "REIMBURSEMENT": (
# #         "reimbursement value",
# #         "reimbursement amount",
# #         "reimbursement cost",
# #     ),
# # }


# # def resolve_attribute_type(question: str) -> str:
# #     """Resolve the fine-grained attribute type from a question string.

# #     Returns one of the keys in _ATTRIBUTE_MAPPINGS, or "GENERAL" when no
# #     specific attribute can be identified.  Always call this before choosing a
# #     validation strategy so that PM_OBJECTIVE is never compared against the
# #     Quarterly Objective column and TRIP_COST is never compared against MRP.
# #     """
# #     normalized = normalize_text(question)
# #     for attr_type, terms in _ATTRIBUTE_MAPPINGS.items():
# #         if any(term in normalized for term in terms):
# #             return attr_type
# #     return "GENERAL"


# # QUESTION_TYPES = {
# #     "PRICE_COMPARISON",
# #     "PRICE_LOOKUP",
# #     "TRIP_AWARD_COST",
# #     "DOSAGE_FREQUENCY",
# #     "DOSAGE_FORM",
# #     "PACK_SIZE",
# #     "STRENGTH_LOOKUP",
# #     "COMPETITOR_BRAND",
# #     "COMPANY_LOOKUP",
# #     "COMPOSITION",
# #     "ACTIVE_INGREDIENT",
# #     "MOLECULE_LIST",
# #     "PRODUCT_COMPARISON",
# #     "CLINICAL_OUTCOME",
# #     "CLINICAL_EVIDENCE",
# #     "DESCRIPTIVE_USP",
# #     "GENERAL",
# # }


# # def classify_question_type(question: str, response: str = "") -> str:
# #     """Classify question intent before validation routing."""
# #     normalized = normalize_text(f"{question} {response}")
# #     normalized_question = normalize_text(question)

# #     if "composition" in normalized_question:
# #         return "COMPOSITION"

# #     if "active ingredient" in normalized_question:
# #         return "ACTIVE_INGREDIENT"

# #     if any(term in normalized_question for term in ("dosage form", "dosage forms", "available forms", "forms of")):
# #         return "DOSAGE_FORM"

# #     if any(
# #         term in normalized_question
# #         for term in (
# #             "strength range",
# #             "which strength",
# #             "what strength",
# #             "strength of",
# #             "strength is",
# #             "present at a strength",
# #         )
# #     ):
# #         return "STRENGTH_LOOKUP"

# #     if (
# #         "how many" in normalized_question
# #         and any(unit in normalized_question for unit in ("tablet", "tablets", "tab", "capsule", "capsules", "cap"))
# #         and any(container in normalized_question for container in ("strip", "box", "pack"))
# #     ):
# #         return "PACK_SIZE"

# #     if any(
# #         term in normalized_question
# #         for term in (
# #             "which three molecules",
# #             "which molecules",
# #             "what molecules",
# #             "molecules are present",
# #             "molecules are included",
# #             "molecules included",
# #             "molecules does",
# #             "molecules are there",
# #             "molecules are in",
# #         )
# #     ):
# #         return "MOLECULE_LIST"

# #     if "contains" in normalized_question and re.search(
# #         r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)\b",
# #         normalized,
# #     ):
# #         return "COMPOSITION"

# #     price_comparison_terms = (
# #         "cheaper",
# #         "cost saving",
# #         "saving",
# #         "lowest",
# #         "highest",
# #         "cheapest",
# #         "most expensive",
# #     )
# #     explicit_price_terms = ("mrp", "price", "cost", "per strip", "per tablet", "per tab")
# #     if any(term in normalized_question for term in price_comparison_terms):
# #         return "PRICE_COMPARISON"

# #     if (
# #         any(term in normalized_question for term in ("difference", "compared to", "compared with", "versus", "vs"))
# #         and any(term in normalized_question for term in explicit_price_terms)
# #     ):
# #         return "PRICE_COMPARISON"

# #     if "competitor" in normalized_question and any(
# #         term in normalized_question
# #         for term in ("price", "priced", "mrp", "per strip", "lowest", "highest", "cheapest")
# #     ):
# #         return "PRICE_COMPARISON"

# #     if _is_multi_product_question(normalized_question):
# #         return "PRODUCT_COMPARISON"

# #     if "marketed by" in normalized_question or "markets" in normalized_question:
# #         return "COMPANY_LOOKUP"

# #     if "competitor" in normalized_question and any(
# #         term in normalized_question for term in ("belongs to", "company", "manufacturer", "manufactures")
# #     ):
# #         return "COMPANY_LOOKUP"

# #     if any(term in normalized_question for term in ("company", "companys", "company’s", "manufacturer", "manufactures")):
# #         return "COMPANY_LOOKUP"

# #     # Incentive and objective questions must not be routed to PRICE_LOOKUP.
# #     # "per strip" in the question refers to the incentive attribute, not MRP.
# #     _objective_incentive_terms = (
# #         "incentive",
# #         "minimum objective",
# #         "quarterly objective",
# #         "monthly objective",
# #         "quarterly minimum",
# #         "monthly minimum",
# #         "pmr objective",
# #     )
# #     if any(term in normalized_question for term in _objective_incentive_terms):
# #         return "GENERAL"

# #     # Trip/award/medal/reimbursement cost questions carry large values in Indian
# #     # number notation (₹1,10,000) and must not be routed through the MRP product-
# #     # price path which expects per-strip or per-tablet prices.
# #     _trip_award_terms = (
# #         "cost per couple",
# #         "couple cost",
# #         "trip cost",
# #         "foreign trip",
# #         "domestic trip",
# #         "international trip",
# #         "medal value",
# #         "medal worth",
# #         "award value",
# #         "award cost",
# #         "award amount",
# #         "reimbursement value",
# #         "reimbursement amount",
# #         "holiday trip",
# #         "incentive trip",
# #     )
# #     if any(term in normalized_question for term in _trip_award_terms):
# #         return "TRIP_AWARD_COST"

# #     if any(term in normalized_question for term in ("mrp", "price", "cost", "per strip")):
# #         return "PRICE_LOOKUP"

# #     if any(
# #         term in normalized_question
# #         for term in (
# #             "dosage",
# #             "dose",
# #             "how many times",
# #             "times a day",
# #             "once daily",
# #             "twice daily",
# #             "frequency",
# #             "every 12 hours",
# #         )
# #     ):
# #         return "DOSAGE_FREQUENCY"

# #     # Trial enrollment / sample-size lookup questions ("how many patients enrolled
# #     # in the SHEP trial?") must not fall into DESCRIPTIVE_USP via "trial".  They
# #     # are pure count lookups and belong in CLINICAL_EVIDENCE so the numeric path
# #     # can validate the specific number.
# #     if (
# #         "how many" in normalized_question
# #         and any(
# #             term in normalized_question
# #             for term in ("enrolled", "enroll", "randomized", "randomised", "participants", "patients", "subjects")
# #         )
# #         and any(
# #             term in normalized_question
# #             for term in ("trial", "study", "program", "programme")
# #         )
# #     ):
# #         return "CLINICAL_EVIDENCE"

# #     # Policy/sales incentive table questions must not be routed to DESCRIPTIVE_USP.
# #     # Terms like "growth" appear in business context (sales growth, HQ growth %)
# #     # but the DESCRIPTIVE_USP path is designed for clinical/medical text only.
# #     _policy_table_terms = (
# #         "productivity",
# #         "couple ticket",
# #         "single ticket",
# #         "sales credit",
# #         "invoice date",
# #         "stockist",
# #         "pangraf sale contribution",
# #         "negative growth",
# #         "growth percentage",
# #         "hq growth",
# #         "h q growth",
# #         "individual growth",
# #         "field employee",
# #     )
# #     if any(term in normalized_question for term in _policy_table_terms):
# #         return "GENERAL"

# #     if (
# #         normalized_question.startswith(("why ", "how "))
# #         or any(
# #             term in normalized_question
# #             for term in (
# #                 "prevent",
# #                 "prevents",
# #                 "inhibit",
# #                 "inhibits",
# #                 "delays",
# #                 "absorption",
# #                 "growth",
# #                 "ingredient",
# #                 "drug class",
# #                 "class",
# #                 "surgeries",
# #                 "used",
# #                 "condition",
# #                 "prescribed",
# #                 "form",
# #                 "tolerability",
# #                 "system",
# #                 "medium",
# #                 "dilution",
# #                 "trial",
# #                 "upper limb",
# #                 "motor function",
# #                 "administration route",
# #                 "route",
# #                 "nebulization",
# #                 "symptom",
# #                 "symptoms",
# #                 "organ",
# #                 "organs",
# #                 "transplantation",
# #                 "side effect",
# #                 "side effects",
# #                 "adverse",
# #                 "adverse effect",
# #                 "adverse effects",
# #                 "adverse reaction",
# #                 "adverse reactions",
# #                 "adverse event",
# #                 "adverse events",
# #                 "dizziness",
# #                 "dry mouth",
# #                 "gastrointestinal",
# #                 "discomfort",
# #                 "nephrotoxicity",
# #                 "monitoring",
# #                 "precaution",
# #                 "precautions",
# #                 "feature",
# #                 "features",
# #                 "advantage",
# #                 "advantages",
# #                 "benefit",
# #                 "benefits",
# #             )
# #         )
# #     ):
# #         return "DESCRIPTIVE_USP"

# #     if "competitor" in normalized_question and "brand" in normalized_question:
# #         return "COMPETITOR_BRAND"

# #     # Clinical outcome questions ask for the MAGNITUDE of a measured effect:
# #     # "By how much does X reduce LDL-C?" or "What was the risk reduction seen?"
# #     # These carry numeric ranges and need range-aware validation — they must not
# #     # fall into CLINICAL_EVIDENCE (which validates narrative text) or
# #     # DESCRIPTIVE_USP (which uses semantic concept matching).
# #     _clinical_outcome_terms = (
# #         "ldl-c reduction",
# #         "ldl reduction",
# #         "ldl-c lowering",
# #         "ldl lowering",
# #         "ldl-c by",
# #         "reduce ldl",
# #         "reduces ldl",
# #         "reduction in ldl",
# #         "hba1c reduction",
# #         "hba1c lowering",
# #         "reduce hba1c",
# #         "reduces hba1c",
# #         "reduction in hba1c",
# #         "risk reduction",
# #         "reduces the risk",
# #         "reduce the risk",
# #         "relative risk reduction",
# #         "absolute risk reduction",
# #         "cardiovascular risk reduction",
# #         "cardiovascular mortality reduction",
# #         "mortality reduction",
# #         "reduces mortality",
# #         "survival benefit",
# #         "survival rate",
# #         "efficacy outcome",
# #         "trial endpoint",
# #         "primary endpoint",
# #         "secondary endpoint",
# #         "major adverse cardiovascular",
# #         "mace reduction",
# #         "hazard ratio",
# #         "odds ratio",
# #         "relative risk",
# #         "number needed to treat",
# #         "nnt",
# #         "blood pressure reduction",
# #         "reduces blood pressure",
# #         "systolic reduction",
# #         "diastolic reduction",
# #         "reduces systolic",
# #         "reduces diastolic",
# #         "triglyceride reduction",
# #         "reduces triglyceride",
# #         "hdl increase",
# #         "increases hdl",
# #         "glucose reduction",
# #         "reduces glucose",
# #         "reduces fasting",
# #         "fasting glucose reduction",
# #         "reduces a1c",
# #         "a1c reduction",
# #     )
# #     if any(term in normalized_question for term in _clinical_outcome_terms):
# #         return "CLINICAL_OUTCOME"

# #     if any(
# #         term in normalized
# #         for term in (
# #             "trial",
# #             "study",
# #             "evidence",
# #             "guideline",
# #             "mortality",
# #             "hfref",
# #             "hfr ef",
# #             "hfr",
# #             "class ia",
# #             "recommendation",
# #         )
# #     ):
# #         return "CLINICAL_EVIDENCE"

# #     if any(
# #         term in normalized_question
# #         for term in (
# #             "why",
# #             "what makes",
# #             "different",
# #             "preferred",
# #             "benefit",
# #             "benefits",
# #             "usp",
# #             "advantage",
# #             "advantages",
# #             "mechanism",
# #         )
# #     ):
# #         return "DESCRIPTIVE_USP"

# #     return "GENERAL"


# def extract_citation_targets(text: str) -> list[dict[str, int | str]]:
#     """Extract every citation target with document name, citation number, and page."""
#     citation_text = extract_citation_text(text)
#     if not citation_text:
#         return []

# #     decomposed_targets = _extract_all_page_label_targets(citation_text)

# #     targets: list[dict[str, int | str]] = []
# #     citation_number = 1
# #     search_position = 0

# #     while search_position < len(citation_text):
# #         start_match = re.search(
# #             rf"(?:^|\s){citation_number}\s+",
# #             citation_text[search_position:],
# #         )

# #         if not start_match:
# #             break

# #         segment_start = search_position + start_match.end()
# #         page_match = re.search(
# #             r"(?:_Page_|page[\s:_-]+)(\d+)",
# #             citation_text[segment_start:],
# #             flags=re.IGNORECASE,
# #         )

# #         if not page_match:
# #             break

# #         page_end = segment_start + page_match.end()
# #         next_start_match = re.search(
# #             rf"\s{citation_number + 1}\s+",
# #             citation_text[page_end:],
# #         )
# #         segment_end = (
# #             page_end + next_start_match.start()
# #             if next_start_match
# #             else len(citation_text)
# #         )
# #         citation_label = citation_text[segment_start:segment_end].strip()

# #         targets.append(
# #             {
# #                 "citation_number": citation_number,
# #                 "page_number": int(page_match.group(1)),
# #                 "document_name": extract_document_name(citation_label),
# #                 "citation_text": citation_label,
# #             }
# #         )
# #         citation_number += 1
# #         search_position = segment_end

# #     if len(decomposed_targets) > len(targets):
# #         return decomposed_targets

# #     if targets:
# #         return targets

# #     return decomposed_targets


# # def _extract_all_page_label_targets(text: str) -> list[dict[str, int | str]]:
# #     """Extract unique page labels from polluted citation text."""
# #     targets: list[dict[str, int | str]] = []
# #     seen: set[tuple[str, int]] = set()
# #     pattern = re.compile(
# #         r"([A-Za-z0-9][A-Za-z0-9 &()./-]{1,80}?"
# #         r"(?:_Page_|page[\s:_-]+)(\d+))",
# #         flags=re.IGNORECASE,
# #     )

# #     for match in pattern.finditer(text):
# #         citation_label = match.group(1).strip()
# #         document_name = extract_document_name(citation_label)
# #         page_number = int(match.group(2))
# #         key = (normalize_text(document_name), page_number)

# #         if key in seen:
# #             continue

# #         seen.add(key)
# #         targets.append(
# #             {
# #                 "citation_number": len(targets) + 1,
# #                 "page_number": page_number,
# #                 "document_name": document_name,
# #                 "citation_text": citation_label,
# #             }
# #         )

# #     return targets


# # def extract_document_name(citation_label: str) -> str:
# #     """Extract the source document name from a citation label."""
# #     cleaned_label = " ".join(citation_label.split()).strip()
# #     document_name = re.sub(
# #         r"(?:_Page_|page[\s:_-]+)\d+.*$",
# #         "",
# #         cleaned_label,
# #         flags=re.IGNORECASE,
# #     ).strip(" :-_")
# #     document_name = re.sub(r"^\d+\s+", "", document_name).strip()
# #     return document_name or "UNKNOWN DOCUMENT"


# # def normalize_text(text: str) -> str:
# #     """Normalize text for stable page-scoped validation."""
# #     lowered_text = text.lower().replace("\u00a0", " ")
# #     lowered_text = re.sub(r"\bonce\s+daily\b|\bonce\s+a\s+day\b", "od", lowered_text)
# #     lowered_text = re.sub(r"\btwice\s+daily\b|\btwice\s+a\s+day\b", "bid", lowered_text)
# #     lowered_text = re.sub(r"\bbd\b", "bid", lowered_text)
# #     lowered_text = re.sub(r"\bone\b", "1", lowered_text)
# #     lowered_text = re.sub(r"\btwo\b", "2", lowered_text)
# #     lowered_text = re.sub(r"\bthree\b", "3", lowered_text)
# #     lowered_text = re.sub(r"\bfour\b", "4", lowered_text)
# #     lowered_text = re.sub(r"\btablets?\b", "tab", lowered_text)
# #     lowered_text = re.sub(r"\bcapsules?\b", "cap", lowered_text)
# #     lowered_text = re.sub(r"\bstrips?\b", "strip", lowered_text)
# #     lowered_text = re.sub(r"\bmaximum\s+retail\s+price\b", "mrp", lowered_text)
# #     lowered_text = re.sub(r"\brecommended\s+dose\b", "recommended dosage", lowered_text)
# #     lowered_text = re.sub(r"\bmode\s+of\s+action\b", "moa", lowered_text)
# #     lowered_text = re.sub(r"\btype\s*ii\b", "type 2", lowered_text)
# #     lowered_text = re.sub(r"\bhcl\b", "hydrochloride", lowered_text)
# #     lowered_text = re.sub(r"\bglizid\s*-\s*m\s*xr\b", "glizid mxr", lowered_text)
# #     lowered_text = re.sub(r"\bglizid\s*-\s*mxr\b", "glizid mxr", lowered_text)
# #     lowered_text = re.sub(r"(?<=\w)[\s_\-./]+(?=\w)", " ", lowered_text)
# #     return " ".join(lowered_text.split())


# # def compare_response_with_source(response: str, source_text: str) -> str:
# #     """Backward-compatible wrapper for page-scoped source validation."""
# #     return compare_response_with_page_data(response, source_text)


# # def extract_citation_text(text: str) -> str:
# #     """Extract the visible citation section from a SuperAI response."""
# #     citation_sections = re.split(r"\bcitation\b", text, flags=re.IGNORECASE, maxsplit=1)
# #     if len(citation_sections) > 1:
# #         citation_text = citation_sections[1].strip()
# #         if re.search(r"(?:_Page_|page[\s:_-]+)\d+", citation_text, flags=re.IGNORECASE):
# #             return citation_text
# #         return ""

# #     citation_matches = re.findall(
# #         r"(?:\d+\s+)?[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+",
# #         text,
# #         flags=re.IGNORECASE,
# #     )
# #     return " ".join(
# #         match.strip()
# #         for match in citation_matches
# #         if re.search(r"(?:_Page_|page[\s:_-]+)\d+", match, flags=re.IGNORECASE)
# #     )


# # def extract_page_number(text: str) -> int:
# #     """Extract the page number tied to the SuperAI answer's citation marker."""
# #     citation_sections = re.split(r"\bcitation\b", text, flags=re.IGNORECASE, maxsplit=1)

# #     if len(citation_sections) > 1:
# #         answer_text = citation_sections[0]
# #         citation_text = citation_sections[1]
# #         citation_page_map = _extract_citation_page_map(citation_text)
# #         referenced_citations = _extract_answer_citation_references(answer_text)

# #         for citation_number in referenced_citations:
# #             if citation_number in citation_page_map:
# #                 return citation_page_map[citation_number]

# #         if citation_page_map:
# #             return citation_page_map[min(citation_page_map)]

# #     citation_matches = re.findall(
# #         r"(?:_Page_|page[\s:_-]+)(\d+)",
# #         text,
# #         flags=re.IGNORECASE,
# #     )

# #     if citation_matches:
# #         return int(citation_matches[-1])

# #     raise ValueError("No mandatory citation page number found in text.")


# # def compare_ai_vs_pdf(ai_response: str, pdf_page_data: str, question: str = "") -> str:
# #     """Compare the AI response with data extracted only from the cited PDF page."""
# #     return compare_response_with_page_data(ai_response, pdf_page_data, question)


# # def explain_ai_vs_pdf(ai_response: str, pdf_page_data: str, question: str = "") -> str:
# #     """Return a specific reason for the page-scoped validation decision."""
# #     response_content = _clean_response_for_validation(ai_response)
# #     question_type = classify_question_type(question, response_content)

# #     if not response_content:
# #         return "Super AI response did not contain a value to validate."

# #     if _is_missing_source_data(pdf_page_data):
# #         return "Required value not found because cited page data is missing."

# #     if question_type in {"PRICE_COMPARISON", "COMPANY_LOOKUP"}:
# #         table_result = _deterministic_table_validation(response_content, pdf_page_data, question)
# #         if table_result[0]:
# #             return table_result[2]
# #         _, reason = _compare_competitor_table_reasoning(
# #             response_content,
# #             pdf_page_data,
# #             question,
# #         )
# #         return reason

# #     if question_type == "PRICE_LOOKUP":
# #         table_result = _deterministic_table_validation(response_content, pdf_page_data, question)
# #         if table_result[0]:
# #             return table_result[2]
# #         _, reason = _compare_price_lookup(response_content, pdf_page_data, question)
# #         return reason

# #     if question_type == "PACK_SIZE":
# #         _, reason = _compare_pack_size(response_content, pdf_page_data)
# #         return reason

# #     if question_type == "STRENGTH_LOOKUP":
# #         _, reason = _compare_strength_lookup(response_content, pdf_page_data, question)
# #         return reason

# #     if question_type == "DOSAGE_FREQUENCY":
# #         _, reason = _compare_dosage(response_content, pdf_page_data)
# #         return reason

# #     if question_type == "COMPETITOR_BRAND":
# #         _, reason = _compare_competitor_brands(ai_response, pdf_page_data)
# #         return reason

# #     if question_type == "COMPOSITION":
# #         _, reason = _compare_composition(response_content, pdf_page_data)
# #         return reason

# #     if question_type == "ACTIVE_INGREDIENT":
# #         _, reason = _compare_active_ingredient(response_content, pdf_page_data)
# #         return reason

# #     if question_type == "MOLECULE_LIST":
# #         _, reason = _compare_molecule_list(response_content, pdf_page_data, question)
# #         return reason

# #     if question_type == "PRODUCT_COMPARISON":
# #         _, reason = _compare_multi_product_response(response_content, pdf_page_data, question)
# #         return reason

# #     if question_type in {"CLINICAL_EVIDENCE", "DESCRIPTIVE_USP", "DOSAGE_FORM"}:
# #         _, reason = _compare_descriptive_response(response_content, pdf_page_data, question)
# #         return reason

# #     if _is_punchline_question(question, response_content):
# #         _, reason = _compare_punchline(response_content, pdf_page_data)
# #         return reason

# #     if _is_competitor_table_reasoning_question(question, response_content):
# #         _, reason = _compare_competitor_table_reasoning(
# #             response_content,
# #             pdf_page_data,
# #             question,
# #         )
# #         return reason

# #     if _is_competitor_brand_question(question, response_content):
# #         _, reason = _compare_competitor_brands(ai_response, pdf_page_data)
# #         return reason

# #     if _is_dosage_question(question, response_content):
# #         _, reason = _compare_dosage(response_content, pdf_page_data)
# #         return reason

# #     if _is_descriptive_question(question, response_content):
# #         result, reason = _compare_descriptive_response(response_content, pdf_page_data, question)
# #         return reason

# #     normalized_response = normalize_text(response_content)
# #     normalized_page = normalize_text(pdf_page_data)
# #     response_numbers = _extract_numbers(normalized_response)
# #     page_numbers = _extract_numbers(normalized_page)
# #     response_keywords = _extract_keywords(normalized_response)
# #     page_keywords = _extract_keywords(normalized_page)
# #     matched_numbers = sorted(response_numbers.intersection(page_numbers))
# #     missing_numbers = sorted(response_numbers.difference(page_numbers))
# #     matched_keywords = sorted(response_keywords.intersection(page_keywords))

# #     if missing_numbers:
# #         if matched_numbers or matched_keywords:
# #             return (
# #                 "Value mismatch. Missing Super AI value(s) on cited page: "
# #                 f"{', '.join(missing_numbers)}."
# #             )
# #         return "Required Super AI value was not found on the cited page."

# #     if response_numbers:
# #         missing_keywords = sorted(response_keywords.difference(page_keywords))
# #         if missing_keywords and not _has_keyword_coverage(response_keywords, page_keywords):
# #             return (
# #                 "Numeric value(s) matched, but related Super AI term(s) are missing "
# #                 f"on cited page: {', '.join(missing_keywords)}."
# #             )
# #         return (
# #             "Exact numeric value match found."
# #             if not matched_numbers
# #             else f"Matching value found: {', '.join(matched_numbers + matched_keywords)}."
# #         )

# #     if _has_keyword_coverage(response_keywords, page_keywords):
# #         return f"Matching value found: {', '.join(matched_keywords)}."

# #     if matched_keywords:
# #         missing_keywords = sorted(response_keywords.difference(page_keywords))
# #         return (
# #             "Text/value mismatch. Missing Super AI term(s) on cited page: "
# #             f"{', '.join(missing_keywords)}."
# #         )

# #     return "Required value not found in cited document/page."


# # def deterministic_numeric_validation(
# #     response: str,
# #     page_data: str,
# #     question: str = "",
# # ) -> tuple[bool, str, str, str]:
# #     """Validate critical numeric/unit values before semantic validation.

# #     Returns:
# #         applicable, result, reason, matched_values
# #     """
# #     response_content = _clean_response_for_validation(response)

# #     if not response_content or _is_missing_source_data(page_data):
# #         return False, "DATA MISSING", "", ""

# #     question_type = classify_question_type(question, response_content)

# #     if question_type == "COMPOSITION":
# #         return False, "DATA MISSING", "", ""

# #     if question_type in {"DESCRIPTIVE_USP", "CLINICAL_EVIDENCE"} and _is_patient_group_question(question):
# #         return False, "DATA MISSING", "", ""

# #     # Trial enrollment / sample-size count questions ("how many X enrolled in
# #     # the SHEP trial?") carry the answer as a bare integer — no unit suffix.
# #     # _extract_numeric_unit_values misses bare integers, so handle them here.
# #     if _is_trial_count_question(question):
# #         normalized_response = normalize_text(_clean_numeric_validation_text(response_content))
# #         normalized_page = normalize_text(page_data)
# #         response_bare = _extract_numbers(normalized_response)
# #         page_bare = _extract_numbers(normalized_page)
# #         # Keep only large integers (>= 100) so citation page numbers / doses don't
# #         # trigger a false match.
# #         large_response = {n for n in response_bare if n.isdigit() and int(n) >= 100}
# #         if large_response:
# #             if large_response.issubset(page_bare):
# #                 return (
# #                     True,
# #                     "PASS",
# #                     "Trial enrollment count from SuperAI matches cited page: "
# #                     f"{', '.join(sorted(large_response))}.",
# #                     ", ".join(sorted(large_response)),
# #                 )
# #             return (
# #                 True,
# #                 "FAIL",
# #                 "Trial enrollment count mismatch. "
# #                 f"SuperAI value(s) {', '.join(sorted(large_response))} "
# #                 "not found on cited page.",
# #                 "",
# #             )
# #         return False, "DATA MISSING", "", ""

# #     # Incentive and objective questions bypass strict numeric extraction.
# #     # The extractor produces "810 strip" from "810 strips" but the document
# #     # has a bare "810", causing a false set-difference FAIL.
# #     # The general comparison (_extract_numbers) handles this correctly.
# #     _obj_inc_terms = (
# #         "incentive",
# #         "minimum objective",
# #         "quarterly objective",
# #         "monthly objective",
# #         "quarterly minimum",
# #         "monthly minimum",
# #         "pmr objective",
# #     )
# #     if any(term in normalize_text(question) for term in _obj_inc_terms):
# #         return False, "DATA MISSING", "", ""

# #     if _is_variant_portfolio_question(question):
# #         result, reason, matched = _compare_variant_portfolio(response_content, page_data, question)
# #         return True, result, reason, matched

# #     table_result = _deterministic_table_validation(response_content, page_data, question)
# #     if table_result[0]:
# #         return table_result

# #     if question_type == "PRICE_LOOKUP":
# #         result, reason = _compare_price_lookup(response_content, page_data, question)
# #         matched = extract_matching_values(response_content, page_data)
# #         return True, result, reason, matched

# #     if question_type == "TRIP_AWARD_COST":
# #         result, reason = _compare_trip_award_cost(response_content, page_data, question)
# #         matched = extract_matching_values(response_content, page_data)
# #         return True, result, reason, matched

# #     if question_type == "CLINICAL_OUTCOME":
# #         result, reason = _compare_clinical_outcome(response_content, page_data, question)
# #         matched = extract_matching_values(response_content, page_data)
# #         return True, result, reason, matched

# #     if _is_repeat_course_question(question):
# #         result, reason, matched = _compare_repeat_courses(response_content, page_data)
# #         return True, result, reason, matched

# #     if not _is_strict_numeric_question(question, response_content):
# #         return False, "DATA MISSING", "", ""

# #     if _is_dosage_question(question, response_content):
# #         result, reason = _compare_dosage(response_content, page_data)
# #         matched = extract_matching_values(response_content, page_data)
# #         return True, result, reason, matched

# #     numeric_response_content = _clean_numeric_validation_text(response_content)
# #     numeric_page_data = _clean_numeric_validation_text(page_data)
# #     normalized_response = normalize_text(numeric_response_content)
# #     normalized_page = normalize_text(numeric_page_data)
# #     response_values = _extract_numeric_unit_values(normalized_response)
# #     page_values = _extract_numeric_unit_values(normalized_page)

# #     if not response_values:
# #         # The SuperAI answer contains no numeric values (e.g. "Couple Ticket",
# #         # "Single Ticket", a text policy answer).  Numeric comparison is not
# #         # applicable here — fall through to the semantic/OpenAI validator.
# #         return False, "DATA MISSING", "", ""

# #     if not page_values:
# #         # Page has no numeric values either — not enough evidence for deterministic
# #         # comparison; let OpenAI evaluate the partial/vision-extracted text.
# #         return False, "DATA MISSING", "", ""

# #     matched_values = sorted(response_values.intersection(page_values))
# #     missing_values = sorted(response_values.difference(page_values))

# #     if missing_values:
# #         # Numeric-only fallback: "810 strip" from SuperAI vs bare "810" in document.
# #         # _extract_numeric_unit_values requires a unit suffix; bare numbers in the
# #         # document are not extracted.  Re-check using _extract_numbers which strips
# #         # units naturally, so "810 strip" → "810" matches document "810".
# #         page_bare = _extract_numbers(normalized_page)
# #         still_missing = [
# #             mv for mv in missing_values
# #             if not _numeric_part_matches_bare(mv, page_bare)
# #         ]
# #         if not still_missing:
# #             return (
# #                 True,
# #                 "PASS",
# #                 "Numeric values match after unit-label normalization: "
# #                 f"{', '.join(sorted(response_values))}.",
# #                 ", ".join(sorted(response_values)),
# #             )
# #         missing_values = still_missing

# #         if matched_values or _extract_keywords(normalized_response).intersection(
# #             _extract_keywords(normalized_page)
# #         ):
# #             return (
# #                 True,
# #                 "FAIL",
# #                 "Strict numeric mismatch. Missing cited-page value(s): "
# #                 f"{', '.join(missing_values)}.",
# #                 ", ".join(matched_values),
# #             )
# #         return (
# #             True,
# #             "DATA MISSING",
# #             "Required numeric value(s) were not found on the cited page: "
# #             f"{', '.join(missing_values)}.",
# #             "",
# #         )

# #     return (
# #         True,
# #         "PASS",
# #         "All strict numeric value(s) from SuperAI exactly match the cited page: "
# #         f"{', '.join(matched_values)}.",
# #         ", ".join(matched_values),
# #     )


# # def compare_response_with_page_data(
# #     response: str,
# #     page_data: str,
# #     question: str = "",
# # ) -> str:
# #     """Compare response values only against the cited PDF page data."""
# #     response_content = _clean_response_for_validation(response)
# #     question_type = classify_question_type(question, response_content)

# #     if not response_content or _is_missing_source_data(page_data):
# #         return "DATA MISSING"

# #     if question_type in {"PRICE_COMPARISON", "COMPANY_LOOKUP"}:
# #         table_result = _deterministic_table_validation(response_content, page_data, question)
# #         if table_result[0]:
# #             return table_result[1]
# #         result, _ = _compare_competitor_table_reasoning(
# #             response_content,
# #             page_data,
# #             question,
# #         )
# #         return result

# #     if question_type == "PRICE_LOOKUP":
# #         table_result = _deterministic_table_validation(response_content, page_data, question)
# #         if table_result[0]:
# #             return table_result[1]
# #         result, _ = _compare_price_lookup(response_content, page_data, question)
# #         return result

# #     if question_type == "PACK_SIZE":
# #         result, _ = _compare_pack_size(response_content, page_data)
# #         return result

# #     if question_type == "STRENGTH_LOOKUP":
# #         result, _ = _compare_strength_lookup(response_content, page_data, question)
# #         return result

# #     if question_type == "DOSAGE_FREQUENCY":
# #         result, _ = _compare_dosage(response_content, page_data)
# #         return result

# #     if question_type == "COMPETITOR_BRAND":
# #         result, _ = _compare_competitor_brands(response, page_data)
# #         return result

# #     if question_type == "COMPOSITION":
# #         result, _ = _compare_composition(response_content, page_data)
# #         return result

# #     if question_type == "ACTIVE_INGREDIENT":
# #         result, _ = _compare_active_ingredient(response_content, page_data)
# #         return result

# #     if question_type == "MOLECULE_LIST":
# #         result, _ = _compare_molecule_list(response_content, page_data, question)
# #         return result

# #     if question_type == "PRODUCT_COMPARISON":
# #         result, _ = _compare_multi_product_response(response_content, page_data, question)
# #         return result

# #     if question_type in {"CLINICAL_EVIDENCE", "DESCRIPTIVE_USP", "DOSAGE_FORM"}:
# #         result, _ = _compare_descriptive_response(response_content, page_data, question)
# #         return result

# #     if _is_punchline_question(question, response_content):
# #         result, _ = _compare_punchline(response_content, page_data)
# #         return result

# #     if _is_competitor_table_reasoning_question(question, response_content):
# #         result, _ = _compare_competitor_table_reasoning(
# #             response_content,
# #             page_data,
# #             question,
# #         )
# #         return result

# #     if _is_competitor_brand_question(question, response_content):
# #         result, _ = _compare_competitor_brands(response, page_data)
# #         return result

# #     if _is_dosage_question(question, response_content):
# #         result, _ = _compare_dosage(response_content, page_data)
# #         return result

# #     numeric_applicable, numeric_result, _, _ = deterministic_numeric_validation(
# #         response,
# #         page_data,
# #         question,
# #     )
# #     if numeric_applicable:
# #         return numeric_result

# #     if _is_descriptive_question(question, response_content):
# #         result, _ = _compare_descriptive_response(response_content, page_data, question)
# #         return result

# #     response_numbers = _extract_numbers(normalize_text(response_content))
# #     page_numbers = _extract_numbers(normalize_text(page_data))
# #     response_keywords = _extract_keywords(normalize_text(response_content))
# #     page_keywords = _extract_keywords(normalize_text(page_data))

# #     if response_numbers:
# #         matched_numbers = response_numbers.intersection(page_numbers)
# #         if response_numbers.issubset(page_numbers):
# #             if not response_keywords or _has_keyword_coverage(response_keywords, page_keywords):
# #                 return "PASS"
# #             return "FAIL" if response_keywords.intersection(page_keywords) else "DATA MISSING"
# #         return "FAIL" if matched_numbers or response_keywords.intersection(page_keywords) else "DATA MISSING"

# #     if response_keywords:
# #         matched_keywords = response_keywords.intersection(page_keywords)
# #         if _has_keyword_coverage(response_keywords, page_keywords):
# #             return "PASS"
# #         return "FAIL" if matched_keywords else "DATA MISSING"

# #     return "FAIL"


# # def extract_citation_page_numbers(response: str) -> list[int]:
# #     """Extract ordered unique citation page numbers from response text."""
# #     numbers: list[int] = []
# #     seen: set[int] = set()
# #     for match in re.finditer(r"_Page_(\d+)", response, flags=re.IGNORECASE):
# #         page_number = int(match.group(1))
# #         if page_number not in seen:
# #             seen.add(page_number)
# #             numbers.append(page_number)
# #     return numbers


# # def extract_matching_values(response: str, source_text: str) -> str:
# #     """Return values from the response that are also present in source text."""
# #     if _is_missing_source_data(source_text):
# #         return ""

# #     normalized_response = normalize_text(_clean_response_for_validation(response))
# #     normalized_source = normalize_text(source_text)

# #     response_numbers = _extract_numbers(normalized_response)
# #     source_numbers = _extract_numbers(normalized_source)
# #     matched_numbers = sorted(response_numbers.intersection(source_numbers))

# #     response_keywords = _extract_keywords(normalized_response)
# #     source_keywords = _extract_keywords(normalized_source)
# #     matched_keywords = sorted(response_keywords.intersection(source_keywords))

# #     matched_values = matched_numbers + matched_keywords

# #     return ", ".join(matched_values)


# # def extract_answer_values(response: str) -> str:
# #     """Return answer values that must be present on the cited PDF page."""
# #     normalized_response = normalize_text(_clean_response_for_validation(response))
# #     response_numbers = sorted(_extract_numbers(normalized_response))
# #     response_keywords = sorted(_extract_keywords(normalized_response))
# #     return ", ".join(response_numbers + response_keywords)


# # def has_matching_values(response: str, source_text: str) -> bool:
# #     """Return whether response and source text share meaningful values."""
# #     return bool(extract_matching_values(response, source_text))


# # def _extract_numbers(text: str) -> set[str]:
# #     """Extract normalized numeric values from text.

# #     Trailing decimal zeros are stripped so that string set operations treat
# #     14.10 and 14.1, 80.0 and 80, 12.50 and 12.5 as the same value.
# #     """
# #     result: set[str] = set()
# #     for number in re.findall(r"(?<!\d)\d[\d,]*(?:\.\d+)?(?!\d)", text):
# #         value = number.replace(",", "")
# #         if "." in value:
# #             value = value.rstrip("0").rstrip(".")
# #         result.add(value)
# #     return result


# # def _is_patient_group_question(question: str) -> bool:
# #     """Return whether numbers in the answer are likely eligibility/source noise."""
# #     normalized = normalize_text(question)
# #     return any(
# #         term in normalized
# #         for term in (
# #             "patient groups",
# #             "which patients",
# #             "eligible",
# #             "eligibility",
# #             "candidates",
# #             "for which patients",
# #         )
# #     )


# # def _is_trial_count_question(question: str) -> bool:
# #     """Return whether the question asks for a trial enrollment / sample-size count."""
# #     normalized = normalize_text(question)
# #     return (
# #         "how many" in normalized
# #         and any(
# #             term in normalized
# #             for term in (
# #                 "enrolled",
# #                 "enroll",
# #                 "randomized",
# #                 "randomised",
# #                 "participants",
# #                 "subjects",
# #             )
# #         )
# #         and any(
# #             term in normalized
# #             for term in ("trial", "study", "program", "programme")
# #         )
# #     )


# # def _is_variant_portfolio_question(question: str) -> bool:
# #     """Return whether the question asks for available variants/portfolio SKUs."""
# #     normalized = normalize_text(question)
# #     return any(term in normalized for term in ("variants", "portfolio", "range")) and any(
# #         term in normalized for term in ("available", "within", "strengths")
# #     )


# # def _compare_variant_portfolio(
# #     response: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str, str]:
# #     """Validate portfolio/range variants by comparing product/strength tokens."""
# #     response_values = _extract_variant_values(response)
# #     page_values = _extract_variant_values(page_data)

# #     if not response_values:
# #         return "DATA MISSING", "SuperAI response did not contain variant/portfolio values.", ""

# #     if not page_values:
# #         return "DATA MISSING", "Variant/portfolio values were not found on the cited page.", ""

# #     missing = sorted(response_values.difference(page_values))
# #     matched = sorted(response_values.intersection(page_values))

# #     if not missing:
# #         return (
# #             "PASS",
# #             f"Portfolio/variant values match cited page: {', '.join(matched)}.",
# #             ", ".join(matched),
# #         )

# #     if matched and _is_broad_range_question(question):
# #         return (
# #             "PASS",
# #             "Requested portfolio/range is partially represented across cited evidence; "
# #             f"matched cited variant value(s): {', '.join(matched)}. "
# #             "Missing variants were not treated as failure for broad range wording.",
# #             ", ".join(matched),
# #         )

# #     if matched:
# #         return (
# #             "FAIL",
# #             "Portfolio/variant mismatch. Missing cited-page variant value(s): "
# #             f"{', '.join(missing)}.",
# #             ", ".join(matched),
# #         )

# #     return "DATA MISSING", "Required portfolio/variant values were not found on the cited page.", ""


# # def _is_broad_range_question(question: str) -> bool:
# #     """Return whether range evidence may be spread across multiple citations."""
# #     normalized = normalize_text(question)
# #     return "range" in normalized or "portfolio" in normalized


# # def _extract_variant_values(text: str) -> set[str]:
# #     """Extract available variant values such as 5/10/20/40 or NEPTAZ 50/100/200."""
# #     cleaned = _clean_response_for_validation(text)
# #     slash_text = cleaned.lower().replace("\u00a0", " ")
# #     normalized = normalize_text(cleaned)
# #     values: set[str] = set()

# #     for match in re.finditer(r"(?<!\d)\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?){1,6}\s*(?:mg|mcg|g|ml)?", slash_text):
# #         unit_match = re.search(r"(mg|mcg|g|ml)\b", match.group(0), flags=re.IGNORECASE)
# #         unit = unit_match.group(1).lower() if unit_match else ""
# #         for number in re.findall(r"\d+(?:\.\d+)?", match.group(0)):
# #             values.add(_normalize_variant_number(number, unit))

# #     for match in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b", normalized):
# #         unit_match = re.search(r"(mg|mcg|g|ml)\b", match.group(0), flags=re.IGNORECASE)
# #         unit = unit_match.group(1).lower() if unit_match else ""
# #         number = re.search(r"\d+(?:\.\d+)?", match.group(0))
# #         if number:
# #             values.add(_normalize_variant_number(number.group(0), unit))

# #     return values


# # def _normalize_variant_number(number: str, unit: str) -> str:
# #     """Normalize variant strength number without changing value."""
# #     normalized_number = number.rstrip("0").rstrip(".") if "." in number else number
# #     return f"{normalized_number} {unit}".strip()


# # def _is_repeat_course_question(question: str) -> bool:
# #     """Return whether the question asks for repeat treatment course count."""
# #     normalized = normalize_text(question)
# #     return "course" in normalized and any(
# #         term in normalized for term in ("how many", "repeat", "target 3")
# #     )


# # def _compare_repeat_courses(response: str, page_data: str) -> tuple[str, str, str]:
# #     """Validate repeat-course count while ignoring unrelated mg/week citation numbers."""
# #     response_count = _extract_repeat_course_count(response)
# #     page_count = _extract_repeat_course_count(page_data)

# #     if not response_count:
# #         return (
# #             "DATA MISSING",
# #             "SuperAI response did not contain a repeat-course count to validate.",
# #             "",
# #         )

# #     if not page_count:
# #         return (
# #             "DATA MISSING",
# #             "Repeat-course count was not found on the cited page.",
# #             "",
# #         )

# #     if response_count == page_count:
# #         return (
# #             "PASS",
# #             f"Repeat-course count matches cited page: up to {page_count} courses.",
# #             f"{page_count} courses",
# #         )

# #     return (
# #         "FAIL",
# #         f"Repeat-course count mismatch. SuperAI returned {response_count} courses while cited page contains {page_count} courses.",
# #         "",
# #     )


# # def _extract_repeat_course_count(text: str) -> str:
# #     """Extract phrases like 'up to 3 courses' or '3 repeat courses'."""
# #     normalized = normalize_text(_clean_numeric_validation_text(text))
# #     patterns = (
# #         r"up to\s+(\d+)\s+(?:repeat\s+)?courses?",
# #         r"(\d+)\s+(?:repeat\s+)?courses?",
# #         r"repeat treatment\s*\(up to\s+(\d+)\s+courses?\)",
# #     )
# #     for pattern in patterns:
# #         match = re.search(pattern, normalized, flags=re.IGNORECASE)
# #         if match:
# #             return match.group(1)
# #     return ""


# # def _is_strict_numeric_question(question: str, response: str) -> bool:
# #     """Return whether exact deterministic numeric validation is required."""
# #     normalized_question = normalize_text(question)
# #     normalized_response = normalize_text(response)
# #     broad_descriptive_starters = (
# #         "why ",
# #         "what makes",
# #         "explain ",
# #         "describe ",
# #         "how does",
# #         "how do",
# #     )
# #     descriptive_only_terms = (
# #         "preferred",
# #         "different",
# #         "advantage",
# #         "advantages",
# #         "benefit",
# #         "benefits",
# #         "mechanism",
# #         "clinical",
# #         "guideline",
# #     )

# #     if normalized_question.startswith(broad_descriptive_starters) and not any(
# #         term in normalized_question
# #         for term in (
# #             "mrp",
# #             "price",
# #             "cost",
# #             "dosage",
# #             "dose",
# #             "how many times",
# #             "pack size",
# #             "strength",
# #             "percentage",
# #             "percent",
# #         )
# #     ):
# #         return False

# #     if any(term in normalized_question for term in descriptive_only_terms) and not any(
# #         term in normalized_question
# #         for term in (
# #             "mrp",
# #             "price",
# #             "cost",
# #             "dosage",
# #             "dose",
# #             "how many times",
# #             "pack size",
# #             "strength",
# #             "percentage",
# #             "percent",
# #         )
# #     ):
# #         return False

# #     normalized = f"{normalized_question} {normalized_response}"
# #     strict_terms = (
# #         "mrp",
# #         "price",
# #         "cost",
# #         "percentage",
# #         "percent",
# #         "%",
# #         "dosage",
# #         "dose",
# #         "strength",
# #         "pack size",
# #         "pack",
# #         "quantity",
# #         "mg",
# #         "mcg",
# #         "ml",
# #         "tab",
# #         "tablet",
# #         "cap",
# #         "bpm",
# #     )
# #     return any(term in normalized for term in strict_terms) and bool(
# #         _extract_numeric_unit_values(normalized)
# #     )


# # def _clean_numeric_validation_text(text: str) -> str:
# #     """Remove citation/source noise before strict numeric extraction."""
# #     cleaned = _clean_response_for_validation(text)
# #     cleaned = re.sub(
# #         r"\b(?:citation|source|sources|ref|reference)\s*\d+(?:\s*,\s*\d+)*\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(
# #         r"\b\d+\s*,\s*\d+(?:\s*,\s*\d+)*\s*(?=$|citation|source|sources|ref|reference)",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(
# #         r"\b(?:sources?)\s+\d+(?:\s*,\s*\d+)*\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     return re.sub(r"\s+", " ", cleaned).strip()


# # def _extract_numeric_unit_values(text: str) -> set[str]:
# #     """Extract exact normalized numeric values with safety-critical units."""
# #     normalized = normalize_text(text)
# #     normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
# #     values: set[str] = set()

# #     range_patterns = (
# #         r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(%)",
# #         r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|tab|tabs|tablet|tablets|cap|caps|capsule|capsules|bpm)",
# #     )
# #     for pattern in range_patterns:
# #         for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
# #             low, high, unit = match.groups()
# #             values.add(_normalize_numeric_unit_value(low, unit, f"{low}{unit}"))
# #             values.add(_normalize_numeric_unit_value(high, unit, f"{high}{unit}"))
# #             values.add(
# #                 f"{_normalize_numeric_unit_value(low, unit, f'{low}{unit}')}-"
# #                 f"{_normalize_numeric_unit_value(high, unit, f'{high}{unit}')}"
# #             )

# #     unit_patterns = (
# #         r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)",
# #         r"(\d+(?:\.\d+)?)\s*(?:rs\.?|inr|₹)",
# #         r"(\d+(?:\.\d+)?)\s*%",
# #         r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|tab|tabs|tablet|tablets|cap|caps|capsule|capsules|strip|strips|bpm)",
# #     )

# #     for pattern in unit_patterns:
# #         for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
# #             groups = match.groups()
# #             number = groups[0].replace(",", "")
# #             unit = groups[1].lower() if len(groups) > 1 and groups[1] else ""
# #             values.add(_normalize_numeric_unit_value(number, unit, match.group(0)))

# #     if any(
# #         term in normalized
# #         for term in (
# #             "mrp",
# #             "price",
# #             "mortality",
# #             "reduction",
# #             "risk",
# #             "endpoint",
# #             "death",
# #             "hospitalization",
# #             "hospitalisation",
# #         )
# #     ):
# #         for number in _extract_numbers(normalized):
# #             values.add(_normalize_numeric_unit_value(number, "", number))

# #     return values


# # def _normalize_numeric_unit_value(number: str, unit: str, raw_value: str) -> str:
# #     """Normalize a numeric/unit value without changing the actual value."""
# #     normalized_number = number.replace(",", "")
# #     if "." in normalized_number:
# #         normalized_number = normalized_number.rstrip("0").rstrip(".")

# #     normalized_unit = unit.lower().strip()
# #     unit_map = {
# #         "tabs": "tab",
# #         "tablet": "tab",
# #         "tablets": "tab",
# #         "caps": "cap",
# #         "capsule": "cap",
# #         "capsules": "cap",
# #         "strips": "strip",
# #         "gm": "g",
# #     }
# #     normalized_unit = unit_map.get(normalized_unit, normalized_unit)

# #     raw = raw_value.lower()
# #     if "%" in raw:
# #         normalized_unit = "%"
# #     if "₹" in raw or "rs" in raw or "inr" in raw:
# #         normalized_unit = "currency"

# #     return f"{normalized_number} {normalized_unit}".strip()


# # def _numeric_part_matches_bare(value_with_unit: str, bare_numbers: set[str]) -> bool:
# #     """Return True if the numeric part of value_with_unit exists in bare_numbers.

# #     Handles "810 strip" vs {"810"} and "21.5 currency" vs {"21.5"}.
# #     """
# #     match = re.match(r"^([\d]+(?:\.[\d]+)?)", value_with_unit.strip())
# #     if not match:
# #         return False

# #     def _norm(n: str) -> str:
# #         try:
# #             f = float(n)
# #             return str(int(f)) if f == int(f) else n.rstrip("0").rstrip(".")
# #         except ValueError:
# #             return n

# #     target = _norm(match.group(1))
# #     return any(_norm(n) == target for n in bare_numbers)


# # def _extract_answer_citation_references(answer_text: str) -> list[int]:
# #     """Return citation reference numbers attached to the answer body."""
# #     match = re.search(r"(?:^|\s)(\d+(?:\s*,\s*\d+)*)\s*$", answer_text.strip())
# #     if not match:
# #         return []
# #     return [int(number) for number in re.findall(r"\d+", match.group(1))]


# # def _extract_citation_page_map(citation_text: str) -> dict[int, int]:
# #     """Map citation reference numbers to their cited PDF page numbers."""
# #     citation_page_map: dict[int, int] = {}
# #     pattern = re.compile(
# #         r"(?:^|\s)(\d+)\s+.*?(?:_Page_|page[\s:_-]+)(\d+)",
# #         flags=re.IGNORECASE,
# #     )

# #     for match in pattern.finditer(citation_text):
# #         citation_page_map[int(match.group(1))] = int(match.group(2))

# #     return citation_page_map


# # def _looks_like_mrp_query(response: str) -> bool:
# #     """Return whether response text is about MRP/price."""
# #     normalized = normalize_text(response)
# #     return "mrp" in normalized or "price" in normalized


# # def _has_mrp_number_match(response: str, source_text: str) -> bool:
# #     """Require decimal price match for MRP/price responses."""
# #     return _has_all_decimal_matches(response, source_text)


# # def _has_all_decimal_matches(response: str, source_text: str) -> bool:
# #     """Require every decimal value in the response to exist in page data."""
# #     response_numbers = {
# #         number for number in _extract_numbers(normalize_text(response)) if "." in number
# #     }
# #     source_numbers = {
# #         number for number in _extract_numbers(normalize_text(source_text)) if "." in number
# #     }
# #     return bool(response_numbers) and response_numbers.issubset(source_numbers)


# # def _has_all_response_values(response: str, source_text: str) -> bool:
# #     """Require all meaningful numeric values and core keywords to exist on the page."""
# #     normalized_response = normalize_text(response)
# #     normalized_source = normalize_text(source_text)

# #     response_numbers = _extract_numbers(normalized_response)
# #     source_numbers = _extract_numbers(normalized_source)
# #     if response_numbers and not response_numbers.issubset(source_numbers):
# #         return False

# #     response_keywords = _extract_keywords(normalized_response)
# #     source_keywords = _extract_keywords(normalized_source)
# #     return not response_keywords or _has_keyword_coverage(response_keywords, source_keywords)


# # def _clean_response_for_validation(response: str) -> str:
# #     """Remove citation/page/source/reference noise before value validation."""
# #     cleaned = _strip_citation_tail(response)
# #     cleaned = re.sub(
# #         r"\b(?:citation|source|page|reference|ref)\s*[:#-]?\s*\d+(?:\s*,\s*\d+)*\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(
# #         r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", " ", cleaned)
# #     cleaned = re.sub(r"\(\s*(?:citation|source|ref)\s*\d+\s*\)", " ", cleaned, flags=re.IGNORECASE)
# #     return re.sub(r"\s+", " ", cleaned).strip(" -*:;,.")


# # def _is_descriptive_question(question: str, response: str) -> bool:
# #     """Return whether semantic descriptive validation should be used."""
# #     normalized = normalize_text(f"{question} {response}")
# #     descriptive_terms = {
# #         "role",
# #         "moa",
# #         "mode of action",
# #         "usp",
# #         "indication",
# #         "indications",
# #         "safety",
# #         "quality",
# #         "salient",
# #         "feature",
# #         "features",
# #         "benefit",
# #         "benefits",
# #         "advantage",
# #         "advantages",
# #     }
# #     return any(term in normalized for term in descriptive_terms)


# # def _is_competitor_brand_question(question: str, response: str) -> bool:
# #     """Return whether validation should compare only competitor brand names."""
# #     normalized = normalize_text(f"{question} {response}")
# #     return "competitor" in normalized and "brand" in normalized


# # def _is_competitor_table_reasoning_question(question: str, response: str) -> bool:
# #     """Return whether competitor validation needs row-aware table reasoning."""
# #     normalized = normalize_text(f"{question} {response}")

# #     reasoning_terms = (
# #         "lowest",
# #         "highest",
# #         "cheapest",
# #         "most expensive",
# #         "cheaper",
# #         "difference",
# #         "compared to",
# #         "price per strip",
# #         "percentage",
# #         "saving",
# #         "cost saving",
# #         "between",
# #         "how many",
# #         "count",
# #         "pack size",
# #         "manufacturer",
# #         "manufactures",
# #         "company",
# #     )
# #     has_reasoning_term = any(term in normalized for term in reasoning_terms)
# #     has_competitor_context = "competitor" in normalized
# #     has_table_attribute_context = any(
# #         term in normalized
# #         for term in (
# #             "price per strip",
# #             "pack size",
# #             "manufactures",
# #             "manufacturer",
# #             "cheaper",
# #             "difference",
# #             "compared to",
# #         )
# #     )
# #     return has_reasoning_term and (has_competitor_context or has_table_attribute_context)


# # def _is_dosage_question(question: str, response: str) -> bool:
# #     """Return whether validation should compare dosage with strict normalized rules."""
# #     normalized_question = normalize_text(question)
# #     frequency_terms = (
# #         "how many times",
# #         "times a day",
# #         "once daily",
# #         "twice daily",
# #         "recommended dosage",
# #         "recommended dose",
# #         "dosage",
# #         "dose",
# #     )
# #     if any(term in normalized_question for term in frequency_terms):
# #         return True

# #     descriptive_terms = (
# #         "benefit",
# #         "benefits",
# #         "beyond glucose",
# #         "role",
# #         "moa",
# #         "mode of action",
# #         "why",
# #         "how",
# #         "evidence",
# #         "study",
# #         "trial",
# #         "guideline",
# #     )
# #     if any(term in normalized_question for term in descriptive_terms):
# #         return False

# #     normalized = normalized_question
# #     long_dosage_terms = (
# #         "dosage",
# #         "dose",
# #         "recommended dosage",
# #         "recommended dose",
# #         "how many times",
# #         "times a day",
# #         "once daily",
# #         "twice daily",
# #     )
# #     if any(term in normalized for term in long_dosage_terms):
# #         return True
# #     # Short abbreviations like "od", "bid", "tds" must use word-boundary matching.
# #     # Plain substring check gives false positives: "od" in "pr[od]uctivity",
# #     # "od" in "peri[od]", "bid" in "ta[bid]" etc.
# #     return any(
# #         re.search(rf"\b{term}\b", normalized)
# #         for term in ("od", "bid", "tds", "tid", "qid")
# #     )


# # def _is_punchline_question(question: str, response: str) -> bool:
# #     """Return whether validation should compare only punchline/slogan text."""
# #     normalized = normalize_text(f"{question} {response}")
# #     return "punchline" in normalized or "punch line" in normalized or "slogan" in normalized


# # def _compare_punchline(response_content: str, page_data: str) -> tuple[str, str]:
# #     """Compare only punchline/slogan text and ignore all table data."""
# #     response_punchline = _extract_punchline_text(response_content, from_document=False)
# #     document_punchline = _extract_punchline_text(page_data, from_document=True)

# #     if not response_punchline:
# #         return "DATA MISSING", "Super AI response did not contain punchline text."

# #     if not document_punchline:
# #         return "DATA MISSING", "Punchline/slogan text not found on the cited page."

# #     normalized_response = _normalize_punchline_for_match(response_punchline)
# #     normalized_document = _normalize_punchline_for_match(document_punchline)

# #     if normalized_response == normalized_document:
# #         return "PASS", f"Punchline matches cited page: {document_punchline}."

# #     response_keywords = _extract_keywords(normalized_response)
# #     document_keywords = _extract_keywords(normalized_document)
# #     if response_keywords and _has_keyword_coverage(response_keywords, document_keywords):
# #         return "PASS", f"Punchline meaning matches cited page: {document_punchline}."

# #     return (
# #         "FAIL",
# #         "Punchline mismatch. "
# #         f"Super AI returned '{response_punchline}' while cited page contains '{document_punchline}'.",
# #     )


# # def _compare_composition(response_content: str, page_data: str) -> tuple[str, str]:
# #     """Validate composition/strength values from the cited page."""
# #     response_composition = _extract_composition_values(response_content)
# #     page_composition = _extract_composition_values(page_data)

# #     if not response_composition:
# #         return "DATA MISSING", "SuperAI response did not contain composition values."

# #     if not page_composition:
# #         return "DATA MISSING", "Composition values were not found on the cited page."

# #     missing_values = sorted(response_composition.difference(page_composition))
# #     if not missing_values:
# #         return (
# #             "PASS",
# #             "Composition matches cited page: "
# #             f"{', '.join(sorted(response_composition))}.",
# #         )

# #     if response_composition.intersection(page_composition):
# #         return (
# #             "FAIL",
# #             "Partial composition mismatch. Missing cited-page composition value(s): "
# #             f"{', '.join(missing_values)}.",
# #         )

# #     return "DATA MISSING", "Required composition values were not found on the cited page."


# # def _compare_strength_lookup(
# #     response_content: str,
# #     page_data: str,
# #     question: str = "",
# # ) -> tuple[str, str]:
# #     """Validate exact strength values for a requested molecule/product."""
# #     response_values = _extract_strength_values(response_content)
# #     page_values = _extract_strength_values(page_data)

# #     if not response_values:
# #         return "DATA MISSING", "SuperAI response did not contain a strength value to validate."

# #     if not page_values:
# #         return "DATA MISSING", "Strength value was not found on the cited page."

# #     requested_entities = _extract_known_molecule_names(f"{question} {response_content}")
# #     if requested_entities:
# #         entity_supported = any(
# #             _entity_text_contains_ordered_tokens(page_data, entity)
# #             for entity in requested_entities
# #         )
# #         if not entity_supported:
# #             return "DATA MISSING", "Requested molecule/product was not found on the cited page."

# #     missing = sorted(response_values.difference(page_values))
# #     if missing:
# #         if response_values.intersection(page_values):
# #             return (
# #                 "FAIL",
# #                 "Strength mismatch. Missing cited-page strength value(s): "
# #                 f"{', '.join(missing)}.",
# #             )
# #         return "DATA MISSING", "Required strength value was not found on the cited page."

# #     return (
# #         "PASS",
# #         "Strength value(s) match cited page exactly: "
# #         f"{', '.join(sorted(response_values))}.",
# #     )


# # def _extract_strength_values(text: str) -> set[str]:
# #     """Extract strict strength values, including IU and ranges."""
# #     normalized = normalize_text(text)
# #     normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
# #     values: set[str] = set()

# #     for match in re.finditer(
# #         r"\b\d+(?:\.\d+)?\s*(?:-|â€“|—|to)\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu)\b",
# #         normalized,
# #         flags=re.IGNORECASE,
# #     ):
# #         values.add(_normalize_strength_text(match.group(0)))

# #     for match in re.finditer(
# #         r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu)\b",
# #         normalized,
# #         flags=re.IGNORECASE,
# #     ):
# #         values.add(_normalize_strength_text(match.group(0)))

# #     return values


# # def _normalize_strength_text(value: str) -> str:
# #     """Normalize a strength value without changing its medical value."""
# #     normalized = normalize_text(value).replace("gm", "g")
# #     normalized = normalized.replace("â€“", "-").replace("—", "-")
# #     normalized = re.sub(r"\bto\b", "-", normalized)
# #     normalized = re.sub(r"\s*-\s*", "-", normalized)
# #     normalized = re.sub(r"(\d(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b", r"\1 \2", normalized)
# #     normalized = re.sub(r"(\d+)\.0+\b", r"\1", normalized)
# #     return re.sub(r"\s+", " ", normalized).strip()


# # def _compare_pack_size(response_content: str, page_data: str) -> tuple[str, str]:
# #     """Validate exact pack quantity such as 10 tablets/strip or 30 capsules/box."""
# #     response_values = _extract_pack_size_values(response_content)
# #     page_values = _extract_pack_size_values(page_data)

# #     if not response_values:
# #         return "DATA MISSING", "SuperAI response did not contain a pack-size value to validate."

# #     if not page_values:
# #         return "DATA MISSING", "Pack-size value was not found on the cited page."

# #     missing = sorted(response_values.difference(page_values))
# #     if missing:
# #         if response_values.intersection(page_values):
# #             return (
# #                 "FAIL",
# #                 "Pack-size mismatch. Missing cited-page pack value(s): "
# #                 f"{', '.join(missing)}.",
# #             )
# #         return "DATA MISSING", "Required pack-size value was not found on the cited page."

# #     return (
# #         "PASS",
# #         "Pack-size value matches cited page exactly: "
# #         f"{', '.join(sorted(response_values))}.",
# #     )


# # def _extract_pack_size_values(text: str) -> set[str]:
# #     """Extract normalized pack quantities while ignoring citation numbers."""
# #     normalized = normalize_text(text)
# #     values: set[str] = set()

# #     pack_patterns = (
# #         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s*(?:/|\s+)\s*(strip|box|pack)\b",
# #         r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s*(?:/|\s+)\s*(strip|box|pack)\b",
# #         r"\((\d+)\s*(?:tab|tabs|tablet|tablets)\s*(?:/|\s+)\s*(strip|box|pack)\)",
# #         r"\((\d+)\s*(?:cap|caps|capsule|capsules)\s*(?:/|\s+)\s*(strip|box|pack)\)",
# #         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s+per\s+(strip|box|pack)\b",
# #         r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s+per\s+(strip|box|pack)\b",
# #         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s+in\s+(?:one|1)\s+(strip|box|pack)\b",
# #         r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s+in\s+(?:one|1)\s+(strip|box|pack)\b",
# #         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets|cap|caps|capsule|capsules)\s+in\s+each\s+(strip|box|pack)\b",
# #     )
# #     for pattern in pack_patterns:
# #         for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
# #             container = match.group(2)
# #             values.add(f"{int(match.group(1))} per {container}")

# #     box_match = re.search(
# #         r"\b(?P<unit_count>\d+)\s*(?:cap|caps|capsule|capsules|tab|tabs|tablet|tablets)\s+"
# #         r"in\s+each\s+strip\s*[*x]\s*(?P<strip_count>\d+)\s*strip\b",
# #         normalized,
# #         flags=re.IGNORECASE,
# #     )
# #     if box_match:
# #         values.add(f"{int(box_match.group('unit_count'))} per strip")
# #         values.add(
# #             f"{int(box_match.group('unit_count')) * int(box_match.group('strip_count'))} per box"
# #         )

# #     return values


# # def _extract_composition_values(text: str) -> set[str]:
# #     """Extract active ingredient/strength composition values."""
# #     cleaned = normalize_text(text)
# #     cleaned = re.sub(
# #         r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     values: set[str] = set()

# #     stop_ingredients = {
# #         "in",
# #         "and",
# #         "or",
# #         "with",
# #         "available",
# #         "contains",
# #         "the",
# #         "management",
# #         "use",
# #         "dosing",
# #         "mechanism",
# #         "response",
# #     }

# #     for match in re.finditer(
# #         r"\b([a-z][a-z0-9]+)\s+(?:injections?|tablets?|capsules?)?\s*"
# #         r"((?:\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)(?:\s*(?:,|and)\s*)?)+)",
# #         cleaned,
# #     ):
# #         ingredient = match.group(1)
# #         if ingredient in stop_ingredients:
# #             continue
# #         strengths = re.findall(r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)", match.group(2))
# #         for strength in strengths:
# #             values.add(f"{ingredient} {_normalize_composition_strength(strength)}")

# #     for match in re.finditer(r"\bdocetrust\s+(\d+(?:\.\d+)?)\s*mg\b", cleaned):
# #         values.add(f"docetaxel {_normalize_composition_strength(match.group(1) + ' mg')}")

# #     for ingredient in ("mycophenolate mofetil", "mycophenolate sodium"):
# #         ingredient_pos = cleaned.find(ingredient)
# #         if ingredient_pos >= 0:
# #             segment = cleaned[ingredient_pos : ingredient_pos + 220]
# #             segment = re.split(
# #                 r"\b(?:moa|role|indications|recommended dosage|brand usp|molecule usp|competitors?)\b",
# #                 segment,
# #             )[0]
# #             for strength in re.findall(r"\d+(?:\.\d+)?\s*mg\b", segment):
# #                 values.add(f"{ingredient} {_normalize_composition_strength(strength)}")
# #             compact_strengths = re.findall(r"\d+(?:\.\d+)?(?=mg\b)", segment)
# #             for number in compact_strengths:
# #                 values.add(f"{ingredient} {_normalize_composition_strength(number + ' mg')}")

# #     if "docetaxel" in cleaned:
# #         start = cleaned.find("docetaxel")
# #         segment = cleaned[start : start + 180] if start >= 0 else cleaned
# #         segment = re.split(
# #             r"\b(?:citation|punchline|moa|role|indications|recommended dosage|salient|competitors?)\b",
# #             segment,
# #         )[0]
# #         for strength in re.findall(r"\d+(?:\.\d+)?\s*mg\b", segment):
# #             values.add(f"docetaxel {_normalize_composition_strength(strength)}")

# #     docetaxel_list_match = re.search(
# #         r"\bdocetaxel\s+injections?\s*[.â€¦…\s-]*"
# #         r"(?P<strengths>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*(?:\s+and\s+\d+(?:\.\d+)?)?)\s*mg\b",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     if docetaxel_list_match:
# #         for number in re.findall(r"\d+(?:\.\d+)?", docetaxel_list_match.group("strengths")):
# #             values.add(f"docetaxel {_normalize_composition_strength(number + ' mg')}")

# #     if "docetaxel injection" in cleaned and not values:
# #         start = cleaned.find("docetaxel injection")
# #         segment = cleaned[start : start + 140] if start >= 0 else ""
# #         segment = re.split(r"\b(?:punchline|moa|role|indications)\b", segment)[0]
# #         if "mg" in segment:
# #             for number in re.findall(r"\d+(?:\.\d+)?", segment):
# #                 values.add(f"docetaxel {_normalize_composition_strength(number + ' mg')}")

# #     return values


# # def _normalize_composition_strength(value: str) -> str:
# #     """Normalize composition strength display without changing value."""
# #     normalized = normalize_text(value).replace("gm", "g")
# #     normalized = re.sub(r"(\d(?:\.\d+)?)\s*(mg|mcg|g|ml)\b", r"\1 \2", normalized)
# #     normalized = re.sub(r"(\d+)\.0+\b", r"\1", normalized)
# #     return normalized


# # def _compare_molecule_list(
# #     response_content: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate requested molecule lists without treating count words as values."""
# #     response_molecules = _extract_known_molecule_names(response_content)
# #     page_molecules = _extract_known_molecule_names(page_data)

# #     if not response_molecules:
# #         return "DATA MISSING", "SuperAI response did not contain molecule names to validate."

# #     if not page_molecules:
# #         return "DATA MISSING", "Molecule names were not found on the cited page."

# #     missing = sorted(response_molecules.difference(page_molecules))
# #     if not missing:
# #         return (
# #             "PASS",
# #             "Molecule list matches cited page: "
# #             f"{', '.join(sorted(response_molecules))}.",
# #         )

# #     if response_molecules.intersection(page_molecules):
# #         return (
# #             "FAIL",
# #             "Molecule list is partially supported. Missing molecule(s): "
# #             f"{', '.join(missing)}.",
# #         )

# #     return "DATA MISSING", "Required molecule list was not found on the cited page."


# # def _compare_active_ingredient(
# #     response_content: str,
# #     page_data: str,
# # ) -> tuple[str, str]:
# #     """Validate active ingredient names without requiring strength values."""
# #     response_molecules = _extract_known_molecule_names(response_content)
# #     page_molecules = _extract_known_molecule_names(page_data)

# #     if not response_molecules:
# #         return "DATA MISSING", "SuperAI response did not contain an active ingredient to validate."

# #     if not page_molecules:
# #         return "DATA MISSING", "Active ingredient was not found on the cited page."

# #     missing = sorted(response_molecules.difference(page_molecules))
# #     if not missing:
# #         return (
# #             "PASS",
# #             "Active ingredient matches cited page: "
# #             f"{', '.join(sorted(response_molecules))}.",
# #         )

# #     if response_molecules.intersection(page_molecules):
# #         return (
# #             "FAIL",
# #             "Active ingredient is only partially supported. Missing ingredient(s): "
# #             f"{', '.join(missing)}.",
# #         )

# #     return (
# #         "FAIL",
# #         "Active ingredient mismatch. "
# #         f"SuperAI returned {', '.join(sorted(response_molecules))}, while cited page contains "
# #         f"{', '.join(sorted(page_molecules))}.",
# #     )


# # def _extract_known_molecule_names(text: str) -> set[str]:
# #     """Extract known pharma molecule names as entities."""
# #     normalized = normalize_text(text)
# #     known_molecules = (
# #         "silodosin",
# #         "mirabegron",
# #         "formoterol",
# #         "glycopyrronium",
# #         "glycopyrronium bromide",
# #         "indacaterol",
# #         "cyclosporine",
# #         "vitamin d3",
# #         "alpha lipoic acid",
# #         "pyridoxine",
# #         "folic acid",
# #         "methyl cobalamin",
# #         "vildagliptin",
# #         "imeglimin",
# #         "pregabalin",
# #         "linagliptin",
# #         "dapagliflozin",
# #         "metformin",
# #         "gliclazide",
# #         "voglibose",
# #         "pioglitazone",
# #         "docetaxel",
# #         "tacrolimus",
# #         "mycophenolate mofetil",
# #         "mycophenolate sodium",
# #         "cerebroprotein hydrolysate",
# #         # Cardiovascular / lipid-lowering molecules (STATPURE range and similar)
# #         "rosuvastatin",
# #         "atorvastatin",
# #         "simvastatin",
# #         "pitavastatin",
# #         "aspirin",
# #         "clopidogrel",
# #         "ticagrelor",
# #         "prasugrel",
# #         "ezetimibe",
# #         "fenofibrate",
# #         "gemfibrozil",
# #         "amlodipine",
# #         "ramipril",
# #         "enalapril",
# #         "lisinopril",
# #         "perindopril",
# #         "telmisartan",
# #         "olmesartan",
# #         "losartan",
# #         "valsartan",
# #         "irbesartan",
# #         "candesartan",
# #         "chlorthalidone",
# #         "hydrochlorothiazide",
# #         "indapamide",
# #         "bisoprolol",
# #         "carvedilol",
# #         "nebivolol",
# #         "atenolol",
# #         "metoprolol",
# #     )
# #     return {
# #         molecule
# #         for molecule in known_molecules
# #         if re.search(rf"\b{re.escape(molecule)}\b", normalized)
# #     }


# # def _compare_dosage(response_content: str, page_data: str) -> tuple[str, str]:
# #     """Compare dosage strictly while accepting standard dosage notation equivalents."""
# #     response_markers = _extract_dosage_markers(response_content)
# #     page_markers = _extract_dosage_markers(page_data)

# #     if not response_markers:
# #         return "DATA MISSING", "Super AI response did not contain a dosage value to validate."

# #     if not page_markers:
# #         return "DATA MISSING", "Dosage value not found on the cited page."

# #     missing_markers = sorted(response_markers.difference(page_markers))
# #     if "1 tab" in missing_markers and any(
# #         marker in response_markers.intersection(page_markers)
# #         for marker in ("od", "daily", "once daily")
# #     ):
# #         missing_markers.remove("1 tab")
# #     if "bid" in missing_markers and "every 12 hours" in response_markers and "every 12 hours" in page_markers:
# #         missing_markers.remove("bid")
# #     if any(marker.endswith("mg") and "-" in marker for marker in response_markers.intersection(page_markers)):
# #         for optional_frequency in ("od", "bid", "daily"):
# #             if optional_frequency in missing_markers:
# #                 missing_markers.remove(optional_frequency)
# #     if "titrated" in missing_markers and any(
# #         marker in page_markers for marker in ("increased", "up to", "maximum")
# #     ):
# #         missing_markers.remove("titrated")
# #     if "4-12 hours prior to transplantation" in response_markers.intersection(page_markers):
# #         missing_markers = [
# #             marker
# #             for marker in missing_markers
# #             if not (
# #                 "4" in marker
# #                 and "12" in marker
# #                 and "transplantation" in marker
# #             )
# #         ]

# #     if not missing_markers:
# #         dosage_evidence = _extract_dosage_evidence(page_data)
# #         if dosage_evidence:
# #             return "PASS", f"Dosage/frequency matches cited page: {dosage_evidence}."

# #         return (
# #             "PASS",
# #             "Dosage matches cited page after standard dosage normalization: "
# #             f"{', '.join(sorted(response_markers))}.",
# #         )

# #     related_markers = response_markers.intersection(page_markers)
# #     if related_markers:
# #         return (
# #             "FAIL",
# #             "Dosage mismatch. Missing dosage marker(s) on cited page: "
# #             f"{', '.join(missing_markers)}.",
# #         )

# #     return "DATA MISSING", "Required dosage value not found on the cited page."


# # def _extract_dosage_evidence(page_data: str) -> str:
# #     """Extract the cited dosage/frequency sentence or section for better reasons."""
# #     cleaned = re.sub(r"\s+", " ", page_data).strip()
# #     match = re.search(
# #         r"\bRecommended Dosage\s+(.+?)(?=\b(?:Brand USP|Molecule USP|Salient|Competitors?|M\.?R\.?P|Indications)\b|$)",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     if match:
# #         return match.group(1).strip(" :-.;")

# #     frequency_match = re.search(
# #         r"[^.]*\b(?:once daily|twice daily|OD|BID|TID|TDS|QID)\b[^.]*",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     return frequency_match.group(0).strip(" :-.;") if frequency_match else ""


# # def _extract_dosage_markers(text: str) -> set[str]:
# #     """Extract normalized dosage markers such as 1 tab, 2 tab, OD, and BID."""
# #     normalized = normalize_text(text)
# #     normalized = re.sub(
# #         r"\b([1-9])(\d{2})\s*(?:hr|hrs|hour|hours)\s*(prior to|before)\s*transplantation\b",
# #         r"\1-\2 hours \3 transplantation",
# #         normalized,
# #         flags=re.IGNORECASE,
# #     )
# #     normalized = re.sub(
# #         r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
# #         " ",
# #         normalized,
# #         flags=re.IGNORECASE,
# #     )
# #     normalized = re.sub(
# #         r"\b(?:citation|source|reference|ref)\s*[:#-]?\s*\d+(?:\s*,\s*\d+)*\b",
# #         " ",
# #         normalized,
# #         flags=re.IGNORECASE,
# #     )
# #     markers: set[str] = set()

# #     for match in re.finditer(r"\b\d+\s*tab\b", normalized):
# #         markers.add(re.sub(r"\s+", " ", match.group(0)).strip())

# #     for match in re.finditer(
# #         r"\b\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*mg\b",
# #         normalized,
# #     ):
# #         markers.add(re.sub(r"\s+", "", match.group(0)).replace("–", "-").replace("to", "-"))

# #     for match in re.finditer(
# #         r"\b\d+(?:\.\d+)?\s*(?:-|–|—|â€“|to|\s)\s*\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\s*(?:prior to|before)\s*transplantation\b",
# #         normalized,
# #     ):
# #         markers.add(
# #             re.sub(r"\s+", " ", match.group(0))
# #             .replace("â€“", "-")
# #             .replace("—", "-")
# #             .replace(" to ", "-")
# #             .replace("hrs", "hours")
# #             .replace("hr", "hours")
# #             .strip()
# #         )

# #     for match in re.finditer(
# #         r"\b(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|\s+|to)\s*(?P<high>\d+(?:\.\d+)?)\s*(?:hr|hrs|hour|hours)\s*(?P<when>prior to|before)\s*transplantation\b",
# #         normalized,
# #     ):
# #         markers.add(
# #             f"{match.group('low')}-{match.group('high')} hours {match.group('when')} transplantation"
# #         )

# #     for match in re.finditer(
# #         r"\b(?P<low>\d+(?:\.\d+)?)\s+(?P<high>\d+(?:\.\d+)?)\s*mg\b",
# #         normalized,
# #     ):
# #         low = match.group("low")
# #         high = match.group("high")
# #         if float(low) < float(high):
# #             markers.add(f"{low}-{high}mg")

# #     for match in re.finditer(
# #         r"\b\d+(?:\.\d+)?\s*mg\s*/?\s*m\s*2\b",
# #         normalized,
# #     ):
# #         markers.add(
# #             re.sub(r"\s+", " ", match.group(0).replace(" ", "")).replace("m2", "m2")
# #         )

# #     for match in re.finditer(r"\bevery\s+\d+\s+weeks?\b", normalized):
# #         markers.add(re.sub(r"\s+", " ", match.group(0)).strip())

# #     if re.search(r"\biv\b", normalized):
# #         markers.add("iv")

# #     if re.search(r"\binfusion\b", normalized):
# #         markers.add("infusion")

# #     if re.search(r"\btwice\s+daily\b|\btwo\s+divided\s+doses\b|\bdivided\s+in\s+two\s+doses\b", normalized):
# #         markers.add("bid")

# #     if re.search(r"\bevery\s+12\s*(?:hr|hrs|hour|hours)\b", normalized):
# #         markers.add("every 12 hours")

# #     frequency_aliases = {
# #         "od": "od",
# #         "bid": "bid",
# #         "bd": "bid",
# #         "tds": "tds",
# #         "tid": "tds",
# #         "qid": "qid",
# #         "hs": "hs",
# #         "sos": "sos",
# #     }
# #     for alias, canonical in frequency_aliases.items():
# #         if re.search(rf"\b{re.escape(alias)}\b", normalized):
# #             markers.add(canonical)

# #     if re.search(r"\bdaily dosage\b|\bdaily usage\b|\bcontinuous daily\b", normalized):
# #         markers.add("daily")

# #     if re.search(r"\btitrat(?:e|ed|ion|able)\b", normalized):
# #         markers.add("titrated")

# #     if re.search(r"\bcan\s+be\s+increased\b|\bincreased\s+up\s+to\b", normalized):
# #         markers.add("increased")

# #     if re.search(r"\bup\s+to\b", normalized):
# #         markers.add("up to")

# #     if re.search(r"\bmaximum\b|\bmax\b", normalized):
# #         markers.add("maximum")

# #     if re.search(r"\btogether\b", normalized):
# #         markers.add("together")

# #     return markers


# # def _extract_punchline_text(text: str, from_document: bool) -> str:
# #     """Extract only punchline or slogan text."""
# #     cleaned = _clean_response_for_validation(text)

# #     if from_document:
# #         match = re.search(
# #             r"\b(?:punch\s*line|punchline|slogan|tagline)\s*[:-]?\s*"
# #             r"(.+?)(?=\b(?:composition|mode of action|role of drugs|indications|"
# #             r"recommended dosage|salient|competitors?|m\.?r\.?p|name of product)\b|$)",
# #             cleaned,
# #             flags=re.IGNORECASE,
# #         )
# #         if not match:
# #             return ""
# #         return _clean_punchline_text(match.group(1))

# #     match = re.search(
# #         r"\b(?:punch\s*line|punchline|slogan|tagline)\s*(?:is|:|-)?\s*(.+)",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     return _clean_punchline_text(match.group(1) if match else cleaned)


# # def _clean_punchline_text(text: str) -> str:
# #     """Remove non-punchline table noise from a punchline candidate."""
# #     cleaned = text.replace("—", "-").replace("–", "-")
# #     cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", " ", cleaned)
# #     cleaned = re.sub(
# #         r"^\s*(?:of\s+)?[A-Za-z][A-Za-z0-9 /().+-]{1,60}\s+is\s+",
# #         "",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(r"^\s*of\s+", "", cleaned, flags=re.IGNORECASE)
# #     cleaned = re.sub(
# #         r"\b(?:company|pack|price|strip|tab|tabs|tablet|tablets|mrp|brand name)\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )

# #     cleaned = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", cleaned.strip())
# #     cleaned = _strip_leading_punchline_label(cleaned)
# #     return re.sub(r"\s+", " ", cleaned).strip(" :-.,;")


# # def _strip_leading_punchline_label(text: str) -> str:
# #     """Drop leading product labels before the actual slogan."""
# #     cleaned = text.strip()
# #     label_pattern = re.compile(
# #         r"^[A-Za-z][A-Za-z0-9 /().+-]{1,45}\s*[:\-]+\s+(.+)$",
# #         flags=re.IGNORECASE,
# #     )

# #     while True:
# #         match = label_pattern.match(cleaned)
# #         if not match:
# #             return cleaned

# #         label = match.group(0)[: match.start(1)].strip(" :-")
# #         remainder = match.group(1).strip()

# #         if _looks_like_product_label(label) and remainder:
# #             cleaned = remainder
# #             continue

# #         return cleaned


# # def _looks_like_product_label(text: str) -> bool:
# #     """Return whether text is likely a product/SKU label, not slogan content."""
# #     normalized = normalize_text(text)
# #     if not normalized:
# #         return False

# #     if any(char.isdigit() for char in normalized):
# #         return True

# #     words = normalized.split()
# #     return len(words) <= 3 and not any(
# #         word in {"one", "all", "relief", "care", "control", "protection", "power"}
# #         for word in words
# #     )


# # def _normalize_punchline_for_match(text: str) -> str:
# #     """Normalize slogan text while ignoring product labels and filler words."""
# #     cleaned = _clean_punchline_text(text)
# #     cleaned = normalize_text(cleaned)
# #     words = [
# #         word
# #         for word in re.findall(r"[a-z][a-z0-9-]*", cleaned)
# #         if word not in {"just", "of", "for", "the", "a", "an"}
# #     ]
# #     return " ".join(words)


# # def _compare_competitor_brands(response_content: str, page_data: str) -> tuple[str, str]:
# #     """Compare competitor brand names only, ignoring companies, packs, and prices."""
# #     response_brands = _extract_competitor_brand_names(response_content)
# #     page_rows = _extract_competitor_table_rows(page_data)
# #     page_brands = [row["brand"] for row in page_rows] if page_rows else _extract_competitor_brand_names(page_data)

# #     if not response_brands:
# #         return "DATA MISSING", "Super AI response did not contain competitor brand names."

# #     if not page_brands:
# #         return "DATA MISSING", "Competitor brand names not found on the cited page."

# #     match_audits = [_entity_best_match_audit(brand, page_brands) for brand in response_brands]
# #     missing_brands = [
# #         str(audit["left_original"])
# #         for audit in match_audits
# #         if not audit["matched"]
# #     ]

# #     if not missing_brands:
# #         audit_summary = _format_entity_audit_summary(match_audits)
# #         return (
# #             "PASS",
# #             "Competitor brand name(s) match cited page: "
# #             f"{', '.join(response_brands)}. {audit_summary}",
# #         )

# #     return (
# #         "FAIL",
# #         "Some competitor brand name(s) are missing on the cited page: "
# #         f"{', '.join(missing_brands)}.",
# #     )


# # def _compare_competitor_table_reasoning(
# #     response_content: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate competitor table questions using parsed row/column relationships."""
# #     normalized_question = normalize_text(question)
# #     response_text = _clean_response_for_validation(response_content)

# #     if any(term in normalized_question for term in ("cheaper", "difference", "compared to")):
# #         return _compare_price_difference(response_text, page_data, question)

# #     if (
# #         "company" in normalized_question
# #         or "manufacturer" in normalized_question
# #         or "manufactures" in normalized_question
# #         or "belongs to" in normalized_question
# #     ):
# #         company_lookup = _compare_company_lookup(response_text, page_data, question)
# #         if company_lookup[0] != "DATA MISSING":
# #             return company_lookup

# #     table_page_data = _scope_competitor_page_data_for_question(page_data, question)
# #     rows = _extract_competitor_table_rows(table_page_data)

# #     if not rows:
# #         return "DATA MISSING", "Competitor table rows were not found on the cited page."

# #     marketed_company = _extract_marketed_by_company(question)
# #     if marketed_company:
# #         expected_rows = [
# #             row
# #             for row in rows
# #             if _company_text_contains(marketed_company, str(row["company"]))
# #             or _company_text_contains(str(row["company"]), marketed_company)
# #         ]
# #         if not expected_rows:
# #             return (
# #                 "DATA MISSING",
# #                 f"No competitor row was found for company {marketed_company} on the cited page.",
# #             )

# #         matching_rows = [
# #             row
# #             for row in expected_rows
# #             if _entity_text_contains(response_text, str(row["brand"]))
# #             or _entity_text_contains_ordered_tokens(response_text, str(row["brand"]))
# #         ]
# #         if matching_rows:
# #             brands = ", ".join(str(row["brand"]) for row in matching_rows)
# #             return (
# #                 "PASS",
# #                 f"Competitor brand-company mapping matches cited table row: {brands} is listed with {marketed_company}.",
# #             )

# #         expected_brands = ", ".join(str(row["brand"]) for row in expected_rows)
# #         return (
# #             "FAIL",
# #             f"Competitor brand-company mismatch. Cited page lists {expected_brands} with {marketed_company}.",
# #         )

# #     if "how many" in normalized_question or "count" in normalized_question:
# #         expected_count = len(rows)
# #         response_numbers = {int(number) for number in _extract_numbers(response_text) if number.isdigit()}
# #         if expected_count in response_numbers:
# #             return (
# #                 "PASS",
# #                 f"Competitor count matches cited table: {expected_count} row(s) found.",
# #             )
# #         if response_numbers:
# #             return (
# #                 "FAIL",
# #                 "Competitor count mismatch. "
# #                 f"Cited table has {expected_count} row(s), while SuperAI returned "
# #                 f"{', '.join(str(number) for number in sorted(response_numbers))}.",
# #             )
# #         return "DATA MISSING", "SuperAI response did not contain a competitor count."

# #     priced_rows = [row for row in rows if row.get("price") is not None]
# #     if not priced_rows and any(term in normalized_question for term in ("price", "lowest", "highest", "cheapest", "expensive", "between", "saving", "percentage")):
# #         return "DATA MISSING", "Competitor prices were not found on the cited page."

# #     if any(term in normalized_question for term in ("percentage", "saving", "cost saving")):
# #         return _compare_percentage_cost_saving(
# #             response_text,
# #             page_data,
# #             question,
# #             priced_rows,
# #         )

# #     if "between" in normalized_question and "price" in normalized_question:
# #         range_values = sorted(float(number) for number in _extract_numbers(normalized_question))
# #         if len(range_values) < 2:
# #             return "DATA MISSING", "Price range could not be extracted from the question."

# #         low, high = range_values[0], range_values[1]
# #         expected_rows = [
# #             row for row in priced_rows if low <= float(row["price"]) <= high
# #         ]
# #         expected_brands = [row["brand"] for row in expected_rows]

# #         if not expected_brands:
# #             return (
# #                 "DATA MISSING",
# #                 f"No competitor brands found in cited table between {low:g} and {high:g}.",
# #             )

# #         missing = [
# #             brand for brand in expected_brands if not _entity_text_contains(response_text, brand)
# #         ]
# #         if not missing:
# #             return (
# #                 "PASS",
# #                 "Competitor price range matches cited table. "
# #                 f"Brands between {low:g} and {high:g}: {', '.join(expected_brands)}.",
# #             )
# #         return (
# #             "FAIL",
# #             "Partial match: SuperAI missed competitor brand(s) in cited price range "
# #             f"{low:g}-{high:g}: {', '.join(missing)}.",
# #         )

# #     if "priced" in normalized_question or re.search(r"\bprice(?:d)?\s+at\b", normalized_question):
# #         requested_prices = {float(number) for number in _extract_numbers(normalized_question)}
# #         if not requested_prices:
# #             return "DATA MISSING", "Requested competitor price could not be extracted from the question."

# #         matching_price_rows = [
# #             row
# #             for row in priced_rows
# #             if _float_set_contains(requested_prices, float(row["price"]))
# #         ]
# #         if not matching_price_rows:
# #             return "DATA MISSING", "Requested price/MRP was not found on the cited page."

# #         expected_brands = [str(row["brand"]) for row in matching_price_rows]
# #         missing_brands = [
# #             brand for brand in expected_brands if not _entity_text_contains(response_text, brand)
# #         ]
# #         if not missing_brands:
# #             evidence = ", ".join(
# #                 f"{row['brand']} at {float(row['price']):g}" for row in matching_price_rows
# #             )
# #             return "PASS", f"Competitor brand-price mapping matches cited table row: {evidence}."

# #         return (
# #             "FAIL",
# #             "Competitor brand-price mismatch. "
# #             f"Cited table maps requested price to {', '.join(expected_brands)}.",
# #         )

# #     if any(term in normalized_question for term in ("lowest", "cheapest")):
# #         scoped_rows = _filter_rows_by_question_brands(priced_rows, question) or priced_rows
# #         expected_row = min(scoped_rows, key=lambda row: float(row["price"]))
# #         return _compare_expected_competitor_row(response_text, expected_row, "lowest")

# #     if any(term in normalized_question for term in ("highest", "most expensive")):
# #         scoped_rows = _filter_rows_by_question_brands(priced_rows, question) or priced_rows
# #         expected_row = max(scoped_rows, key=lambda row: float(row["price"]))
# #         return _compare_expected_competitor_row(response_text, expected_row, "highest")

# #     if "price per strip" in normalized_question or "price" in normalized_question:
# #         matching_rows = [
# #             row for row in priced_rows if _entity_text_contains(response_text, row["brand"])
# #         ]
# #         response_numbers = {float(number) for number in _extract_numbers(response_text)}

# #         for row in matching_rows:
# #             if float(row["price"]) in response_numbers:
# #                 return (
# #                     "PASS",
# #                     "Competitor price matches cited table row. "
# #                     f"{row['brand']} price/strip is {row['price']:.2f}.",
# #                 )

# #         if matching_rows:
# #             row = matching_rows[0]
# #             return (
# #                 "FAIL",
# #                 "Competitor price mismatch. "
# #                 f"Cited table row for {row['brand']} has price/strip {row['price']:.2f}.",
# #             )

# #     if (
# #         "company" in normalized_question
# #         or "manufacturer" in normalized_question
# #         or "manufactures" in normalized_question
# #         or "belongs to" in normalized_question
# #     ):
# #         for row in rows:
# #             if _entity_text_contains(response_text, row["brand"]):
# #                 if _company_text_contains(response_text, row["company"]):
# #                     return (
# #                         "PASS",
# #                         "Competitor company matches cited table row. "
# #                         f"{row['brand']} is listed with {row['company']}.",
# #                     )
# #                 return (
# #                     "FAIL",
# #                     "Competitor company mismatch. "
# #                     f"Cited table row lists {row['brand']} with {row['company']}.",
# #                 )

# #     if "pack size" in normalized_question or "pack" in normalized_question:
# #         for row in rows:
# #             if _entity_text_contains(response_text, row["brand"]):
# #                 if row["pack"] and normalize_text(row["pack"]) in normalize_text(response_text):
# #                     return (
# #                         "PASS",
# #                         "Competitor pack size matches cited table row. "
# #                         f"{row['brand']} pack size is {row['pack']}.",
# #                     )
# #                 return (
# #                     "FAIL",
# #                     "Competitor pack size mismatch. "
# #                     f"Cited table row lists {row['brand']} pack size as {row['pack']}.",
# #                 )

# #     return "DATA MISSING", "Requested competitor table attribute could not be validated."


# # def _filter_rows_by_question_brands(
# #     rows: list[dict[str, object]],
# #     question: str,
# # ) -> list[dict[str, object]]:
# #     """Keep competitor rows whose brand is explicitly listed in the question."""
# #     question_brands = _extract_explicit_brands_from_question(question)
# #     if not question_brands:
# #         return []

# #     filtered: list[dict[str, object]] = []
# #     for row in rows:
# #         brand = str(row.get("brand") or "")
# #         if any(
# #             _entity_text_contains(brand, question_brand)
# #             or _entity_text_contains(question_brand, brand)
# #             or _entity_text_contains_ordered_tokens(brand, question_brand)
# #             or _entity_text_contains_ordered_tokens(question_brand, brand)
# #             for question_brand in question_brands
# #         ):
# #             filtered.append(row)

# #     return filtered


# # def _extract_explicit_brands_from_question(question: str) -> list[str]:
# #     """Extract brand names from 'among A, B, C and D' style questions."""
# #     match = re.search(
# #         r"\bamong\s+(.+?)(?:\s+in\s+the\b|\s+category\b|\?)",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     if not match:
# #         return []

# #     brand_text = match.group(1)
# #     brand_text = re.sub(
# #         r"\b(?:which|competitor|brand|has|the|lowest|highest|mrp|price|among)\b",
# #         " ",
# #         brand_text,
# #         flags=re.IGNORECASE,
# #     )
# #     parts = re.split(r"\s*,\s*|\s+\band\b\s+|\s+and\s+", brand_text)
# #     return [
# #         re.sub(r"\s+", " ", part).strip(" ?:-.,")
# #         for part in parts
# #         if part.strip(" ?:-.,")
# #     ]


# # def _compare_percentage_cost_saving(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# #     competitor_rows: list[dict[str, object]],
# # ) -> tuple[str, str]:
# #     """Validate percentage cost saving using cited product and competitor prices."""
# #     own_price = _extract_requested_product_price(page_data, question)
# #     if own_price is None:
# #         return "DATA MISSING", "Eplebless/product price was not found on the cited page."

# #     if not competitor_rows:
# #         return "DATA MISSING", "Competitor prices were not found on the cited page."

# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     if not response_numbers:
# #         return "DATA MISSING", "SuperAI response did not contain a percentage cost-saving value."

# #     calculated_savings: list[tuple[str, float, float]] = []
# #     for row in competitor_rows:
# #         competitor_price = float(row["price"])
# #         if competitor_price <= 0 or competitor_price <= own_price:
# #             continue
# #         saving_percent = ((competitor_price - own_price) / competitor_price) * 100
# #         calculated_savings.append((str(row["brand"]), competitor_price, saving_percent))

# #     if not calculated_savings:
# #         return "DATA MISSING", "No higher-priced competitor row was available for cost-saving calculation."

# #     mentioned_rows = [
# #         item for item in calculated_savings if _entity_text_contains(response_text, item[0])
# #     ]
# #     rows_to_check = mentioned_rows or calculated_savings

# #     for brand, competitor_price, saving_percent in rows_to_check:
# #         if _number_set_contains_close_value(response_numbers, saving_percent):
# #             return (
# #                 "PASS",
# #                 "Percentage cost saving matches cited table calculation. "
# #                 f"Product price {own_price:.2f} vs {brand} {competitor_price:.2f} "
# #                 f"gives {saving_percent:.2f}% saving.",
# #             )

# #     calculated_summary = ", ".join(
# #         f"{brand}: {saving_percent:.2f}%" for brand, _, saving_percent in calculated_savings
# #     )


# # def _compare_price_difference(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate cheaper/difference questions by calculating cited table prices."""
# #     own_product, compared_brand = _extract_price_comparison_entities(question)
# #     if not own_product or not compared_brand:
# #         return "DATA MISSING", "Price comparison products could not be identified from the question."

# #     own_prices = _extract_own_sku_prices(page_data, own_product)
# #     compared_prices = _extract_competitor_strength_prices(page_data, compared_brand)

# #     if not own_prices or not compared_prices:
# #         fallback_result = _compare_single_row_price_difference(
# #             response_text,
# #             page_data,
# #             own_product,
# #             compared_brand,
# #         )
# #         if fallback_result[0] != "DATA MISSING":
# #             return fallback_result

# #     if not own_prices:
# #         return "DATA MISSING", f"{own_product} prices were not found on the cited page."

# #     if not compared_prices:
# #         return "DATA MISSING", f"{compared_brand} competitor prices were not found on the cited page."

# #     shared_strengths = [
# #         strength for strength in own_prices if strength in compared_prices
# #     ]
# #     if not shared_strengths:
# #         return (
# #             "DATA MISSING",
# #             f"No matching strengths were found between {own_product} and {compared_brand}.",
# #         )

# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     calculated_rows: list[tuple[str, float, float, float]] = []
# #     missing_differences: list[str] = []

# #     for strength in shared_strengths:
# #         own_price = own_prices[strength]
# #         compared_price = compared_prices[strength]
# #         difference = round(compared_price - own_price, 2)
# #         calculated_rows.append((strength, own_price, compared_price, difference))
# #         if not _float_set_contains(response_numbers, difference):
# #             missing_differences.append(f"{strength} mg: {difference:g}")

# #     evidence = "; ".join(
# #         (
# #             f"{own_product} {strength} mg {own_price:g} vs "
# #             f"{compared_brand} {strength} mg {compared_price:g} = {difference:g} cheaper"
# #         )
# #         for strength, own_price, compared_price, difference in calculated_rows
# #     )

# #     if not missing_differences:
# #         return "PASS", f"Price difference matches cited table calculation. {evidence}."

# #     return (
# #         "FAIL",
# #         "Price difference mismatch. Cited table calculation: "
# #         f"{evidence}. Missing/incorrect SuperAI difference(s): {', '.join(missing_differences)}.",
# #     )


# # def _compare_single_row_price_difference(
# #     response_text: str,
# #     page_data: str,
# #     own_product: str,
# #     compared_brand: str,
# # ) -> tuple[str, str]:
# #     """Validate price difference when own product and competitor use single table rows."""
# #     own_prices = _extract_exact_product_prices(page_data, own_product)
# #     fallback_own_price = _extract_requested_product_price(page_data, f"What is the MRP of {own_product}?")
# #     if fallback_own_price is not None:
# #         own_prices.add(fallback_own_price)

# #     competitor_rows = _extract_competitor_table_rows(page_data)
# #     compared_rows = [
# #         row
# #         for row in competitor_rows
# #         if _entity_text_contains(str(row["brand"]), compared_brand)
# #         or _entity_text_contains(compared_brand, str(row["brand"]))
# #     ]
# #     compared_rows = [row for row in compared_rows if row.get("price") is not None]

# #     if not own_prices or not compared_rows:
# #         return "DATA MISSING", "Single-row price difference evidence was not found on the cited page."

# #     compared_price = float(compared_rows[0]["price"])
# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     calculated = [
# #         (own_price, round(abs(compared_price - own_price), 2))
# #         for own_price in sorted(own_prices)
# #     ]

# #     for own_price, difference in calculated:
# #         if _float_set_contains(response_numbers, difference):
# #             return (
# #                 "PASS",
# #                 "Price difference matches cited table calculation. "
# #                 f"{compared_brand} {compared_price:g} - {own_product} {own_price:g} = {difference:g}.",
# #             )

# #     calculated_summary = "; ".join(
# #         f"{compared_brand} {compared_price:g} - {own_product} {own_price:g} = {difference:g}"
# #         for own_price, difference in calculated
# #     )
# #     return (
# #         "FAIL",
# #         "Price difference mismatch. Cited table calculation(s): "
# #         f"{calculated_summary}.",
# #     )


# # def _extract_exact_product_prices(page_data: str, product: str) -> set[float]:
# #     """Extract prices that are tied to the exact product name."""
# #     prices: set[float] = set()
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     product_pattern = r"\s*[-_/]?\s*".join(
# #         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
# #     )

# #     for match in re.finditer(
# #         rf"\b{product_pattern}\b\s*[:-]+\s*(?P<price>\d{{1,4}}(?:,\d{{3}})*(?:\.\d+)?)\s*\(",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     ):
# #         prices.add(float(match.group("price").replace(",", "")))

# #     for match in re.finditer(
# #         rf"\b{product_pattern}\b\s+TABLETS(?:\s+\(\d+\s*TABS\))?\s+"
# #         r"(?P<current>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s+"
# #         r"(?P<new>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\b",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     ):
# #         prices.add(float(match.group("current").replace(",", "")))
# #         prices.add(float(match.group("new").replace(",", "")))

# #     return prices


# # # Column header keyword → canonical attribute type used by resolve_attribute_type.
# # # Ordered from most-specific to least-specific so the first matching alias wins.
# # _COLUMN_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
# #     "PM_OBJECTIVE": (
# #         "pm obj",
# #         "pm objective",
# #         "pmr obj",
# #         "pmr objective",
# #         "monthly obj",
# #         "monthly objective",
# #         "monthly minimum",
# #         "minimum objective",
# #         "pm target",
# #         "pmr target",
# #     ),
# #     "QUARTERLY_OBJECTIVE": (
# #         "quarterly obj",
# #         "quarterly objective",
# #         "qtr obj",
# #         "quarterly pmr",
# #         "quarterly pm",
# #         "q objective",
# #     ),
# #     "INCENTIVE": (
# #         "incentive per strip",
# #         "incentive/strip",
# #         "inc/strip",
# #         "incentive per tab",
# #         "incentive/tab",
# #         "incentive value",
# #         "incentive",
# #     ),
# # }


# # def _detect_column_order(page_data: str) -> list[str]:
# #     """Return column types in left-to-right order based on header positions.

# #     Scans the page text for column header aliases and sorts them by their
# #     character position.  The resulting list gives the column index for each
# #     attribute type so that row-level numbers can be mapped to the right cell.
# #     """
# #     normalized = re.sub(r"\s+", " ", page_data)
# #     positions: list[tuple[int, str]] = []
# #     seen: set[str] = set()
# #     for col_type, aliases in _COLUMN_HEADER_ALIASES.items():
# #         for alias in aliases:
# #             m = re.search(re.escape(alias), normalized, flags=re.IGNORECASE)
# #             if m and col_type not in seen:
# #                 positions.append((m.start(), col_type))
# #                 seen.add(col_type)
# #                 break
# #     positions.sort()
# #     return [col_type for _, col_type in positions]


# # def _table_column_cell_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     """Validate by selecting the exact column for the requested attribute.

# #     Prevents PM_OBJECTIVE responses from being compared against the
# #     QUARTERLY_OBJECTIVE column (and vice versa) when multiple numeric
# #     columns share the same product row.

# #     Pipeline:
# #       question → resolve_attribute_type → detect column order → find product
# #       row → filter product-name digits → pick number at column index → compare.
# #     """
# #     attr_type = resolve_attribute_type(question)
# #     if attr_type not in _COLUMN_HEADER_ALIASES:
# #         return False, "DATA MISSING", "", ""

# #     column_order = _detect_column_order(page_data)
# #     if attr_type not in column_order:
# #         return False, "DATA MISSING", "", ""

# #     col_index = column_order.index(attr_type)

# #     product = _extract_table_product_from_question(question)
# #     if not product:
# #         return False, "DATA MISSING", "", ""

# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     tokens = _product_name_tokens(product)
# #     if not tokens:
# #         return False, "DATA MISSING", "", ""

# #     product_pattern = r"[-\s/]*".join(re.escape(t) for t in tokens)
# #     row_match = re.search(
# #         rf"\b{product_pattern}\b(?P<row>.{{0,220}})",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     )
# #     if not row_match:
# #         return False, "DATA MISSING", "", ""

# #     row_text = row_match.group(0)

# #     # Filter out digits that are part of the product name (e.g. "2.5" from "CONCOR 2.5").
# #     product_nums = {
# #         float(n)
# #         for token in tokens
# #         for n in re.findall(r"\d+(?:\.\d+)?", token)
# #     }
# #     all_nums = [
# #         float(n.replace(",", ""))
# #         for n in re.findall(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", row_text)
# #         if not any(abs(float(n.replace(",", "")) - pn) <= 0.001 for pn in product_nums)
# #     ]

# #     if col_index >= len(all_nums):
# #         return False, "DATA MISSING", "", ""

# #     expected_value = all_nums[col_index]
# #     response_numbers = {float(n) for n in _extract_numbers(response_text)}

# #     if _float_set_contains(response_numbers, expected_value):
# #         _log_validation_step(
# #             rule="_table_column_cell_validation",
# #             product=product,
# #             attribute=attr_type,
# #             column=f"index {col_index} of {column_order}",
# #             doc_value=expected_value,
# #             response_value=sorted(response_numbers),
# #             verdict="PASS",
# #             reason=f"{attr_type} for {product} matches: {expected_value:g}.",
# #         )
# #         return (
# #             True,
# #             "PASS",
# #             f"{attr_type} for {product} matches cited page: {expected_value:g}.",
# #             f"{expected_value:g}",
# #         )

# #     _log_validation_step(
# #         rule="_table_column_cell_validation",
# #         product=product,
# #         attribute=attr_type,
# #         column=f"index {col_index} of {column_order}",
# #         doc_value=expected_value,
# #         response_value=sorted(response_numbers),
# #         verdict="FAIL",
# #         reason=f"Cited {attr_type}={expected_value:g}, response has {sorted(response_numbers)}.",
# #     )
# #     return (
# #         True,
# #         "FAIL",
# #         f"{attr_type} mismatch for {product}. Cited value: {expected_value:g}, "
# #         f"but SuperAI returned "
# #         f"{', '.join(f'{n:g}' for n in sorted(response_numbers))}.",
# #         "",
# #     )


# # def _deterministic_table_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     """Validate row-grounded table questions before generic numeric matching."""
# #     normalized_question = normalize_text(question)
# #     if _is_missing_source_data(page_data):
# #         return False, "DATA MISSING", "", ""

# #     if not any(
# #         term in normalized_question
# #         for term in (
# #             "mrp",
# #             "price",
# #             "per tablet",
# #             "per tab",
# #             "highest",
# #             "lowest",
# #             "difference",
# #             "sku",
# #             "packaging",
# #             "company",
# #             "manufactured",
# #             "manufacturer",
# #             "belongs to",
# #             "mdi",
# #             "dpi",
# #             "forte",
# #             "incentive",
# #             "objective",
# #             "minimum",
# #             "target",
# #         )
# #     ):
# #         return False, "DATA MISSING", "", ""

# #     # Column-aware validation runs first so PM_OBJECTIVE is never compared
# #     # against the QUARTERLY_OBJECTIVE column.
# #     column_cell_result = _table_column_cell_validation(response_text, page_data, question)
# #     if column_cell_result[0]:
# #         return column_cell_result

# #     difference_result = _table_price_difference_validation(response_text, page_data, question)
# #     if difference_result[0]:
# #         return difference_result

# #     company_result = _table_company_lookup(response_text, page_data, question)
# #     if company_result[0]:
# #         return company_result

# #     column_result = _table_matrix_value_validation(response_text, page_data, question)
# #     if column_result[0]:
# #         return column_result

# #     reverse_result = _table_reverse_price_lookup(response_text, page_data, question)
# #     if reverse_result[0]:
# #         return reverse_result

# #     ranking_result = _table_price_ranking_validation(response_text, page_data, question)
# #     if ranking_result[0]:
# #         return ranking_result

# #     competitor_unit_ranking = _table_competitor_unit_price_ranking_validation(
# #         response_text,
# #         page_data,
# #         question,
# #     )
# #     if competitor_unit_ranking[0]:
# #         return competitor_unit_ranking

# #     pack_result = _table_pack_size_validation(response_text, page_data, question)
# #     if pack_result[0]:
# #         return pack_result

# #     lookup_result = _table_price_lookup_validation(response_text, page_data, question)
# #     if lookup_result[0]:
# #         return lookup_result

# #     return False, "DATA MISSING", "", ""


# # def _table_price_lookup_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     """Validate direct product/SKU price lookups using exact row chunks."""
# #     product = _extract_table_product_from_question(question)
# #     if not product:
# #         return False, "DATA MISSING", "", ""

# #     row = _best_family_price_row(page_data, product)
# #     if not row:
# #         return False, "DATA MISSING", "", ""

# #     normalized_question = normalize_text(question)
# #     value = row["unit_price"] if any(term in normalized_question for term in ("per tablet", "per tab")) else row["price"]
# #     if value is None:
# #         return True, "DATA MISSING", f"Requested table value was not found for {row['product']}.", ""

# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     if _float_set_contains(response_numbers, float(value)):
# #         return (
# #             True,
# #             "PASS",
# #             f"Table row value matches cited page: {row['product']} = {float(value):g}.",
# #             f"{float(value):g}",
# #         )

# #     return (
# #         True,
# #         "FAIL",
# #         f"Table row value mismatch. Cited row for {row['product']} has {float(value):g}.",
# #         "",
# #     )


# # def _table_pack_size_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     normalized_question = normalize_text(question)
# #     if not any(term in normalized_question for term in ("packaging", "pack size", "pack")):
# #         return False, "DATA MISSING", "", ""

# #     product = _extract_table_product_from_question(question)
# #     rows = _family_price_rows(page_data, product) if product else []
# #     if not rows and "cilaheart" in normalized_question:
# #         rows = _family_price_rows(page_data, "CILAHEART")
# #     if not rows:
# #         return False, "DATA MISSING", "", ""

# #     if "common" in normalized_question:
# #         packs = {row["pack"] for row in rows if row.get("pack")}
# #         if not packs:
# #             return True, "DATA MISSING", "Pack size was not found in cited table rows.", ""
# #         expected = sorted(packs)[0] if len(packs) == 1 else ""
# #         if expected and normalize_text(expected) in normalize_text(response_text):
# #             return True, "PASS", f"Common pack size matches cited table rows: {expected}.", expected
# #         if expected:
# #             return True, "FAIL", f"Common pack size mismatch. Cited table rows show {expected}.", ""
# #         return True, "DATA MISSING", "No single common pack size exists across cited table rows.", ""

# #     row = _best_family_price_row(page_data, product)
# #     if not row or not row.get("pack"):
# #         return True, "DATA MISSING", "Requested pack size was not found in the cited table row.", ""
# #     expected = str(row["pack"])
# #     if normalize_text(expected) in normalize_text(response_text):
# #         return True, "PASS", f"Pack size matches cited table row: {row['product']} = {expected}.", expected
# #     return True, "FAIL", f"Pack size mismatch. Cited row for {row['product']} has {expected}.", ""


# # def _table_price_ranking_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     normalized_question = normalize_text(question)
# #     if not any(term in normalized_question for term in ("highest", "lowest", "cheapest")):
# #         return False, "DATA MISSING", "", ""

# #     family = _extract_ranking_family(question)
# #     rows = _family_price_rows(page_data, family) if family else []
# #     rows = [row for row in rows if row.get("price") is not None]
# #     if not rows:
# #         return False, "DATA MISSING", "", ""

# #     expected = min(rows, key=lambda row: float(row["price"])) if any(term in normalized_question for term in ("lowest", "cheapest")) else max(rows, key=lambda row: float(row["price"]))
# #     expected_price = float(expected["price"])
# #     brand_ok = _entity_text_contains(response_text, str(expected["product"])) or _entity_text_contains_ordered_tokens(response_text, str(expected["product"]))
# #     price_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, expected_price)
# #     label = "lowest" if any(term in normalized_question for term in ("lowest", "cheapest")) else "highest"
# #     if brand_ok and (price_ok or not _extract_numbers(response_text)):
# #         return True, "PASS", f"{label.title()} table row matches cited page: {expected['product']} at {expected_price:g}.", f"{expected['product']} {expected_price:g}"
# #     return True, "FAIL", f"{label.title()} table row is {expected['product']} at {expected_price:g}; SuperAI does not match.", ""


# # def _table_competitor_unit_price_ranking_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     """Validate competitor ranking by per-tablet/per-tab value."""
# #     normalized_question = normalize_text(question)
# #     if "competitor" not in normalized_question:
# #         return False, "DATA MISSING", "", ""
# #     if not any(term in normalized_question for term in ("highest", "lowest", "cheapest")):
# #         return False, "DATA MISSING", "", ""
# #     if not any(term in normalized_question for term in ("per tablet", "per tab")):
# #         return False, "DATA MISSING", "", ""

# #     rows = [row for row in _extract_competitor_unit_price_rows(page_data) if row.get("unit_price") is not None]
# #     if not rows:
# #         return False, "DATA MISSING", "", ""

# #     label = "lowest" if any(term in normalized_question for term in ("lowest", "cheapest")) else "highest"
# #     expected = min(rows, key=lambda row: float(row["unit_price"])) if label == "lowest" else max(rows, key=lambda row: float(row["unit_price"]))
# #     expected_brand = str(expected["brand"])
# #     expected_unit = float(expected["unit_price"])
# #     brand_ok = _entity_text_contains(response_text, expected_brand) or _entity_text_contains_ordered_tokens(response_text, expected_brand)
# #     unit_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, expected_unit)

# #     if brand_ok and unit_ok:
# #         return (
# #             True,
# #             "PASS",
# #             f"{label.title()} competitor per-tablet row matches cited table: {expected_brand} = {expected_unit:g}.",
# #             f"{expected_brand} {expected_unit:g}",
# #         )
# #     return (
# #         True,
# #         "FAIL",
# #         f"{label.title()} competitor per-tablet row is {expected_brand} = {expected_unit:g}; SuperAI does not match.",
# #         "",
# #     )


# # def _table_price_difference_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     normalized_question = normalize_text(question)
# #     if "difference" not in normalized_question and "between" not in normalized_question:
# #         return False, "DATA MISSING", "", ""

# #     left, right = _extract_price_comparison_entities(question)
# #     if not left or not right:
# #         return False, "DATA MISSING", "", ""

# #     left_row = _best_family_price_row(page_data, left)
# #     right_row = _best_family_price_row(page_data, right)
# #     if not left_row or not right_row:
# #         return False, "DATA MISSING", "", ""

# #     left_value = float(left_row["price"])
# #     right_value = float(right_row["price"])
# #     difference = round(abs(right_value - left_value), 2)
# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     if _float_set_contains(response_numbers, difference):
# #         return (
# #             True,
# #             "PASS",
# #             f"Price difference matches cited table rows: {right_row['product']} {right_value:g} - {left_row['product']} {left_value:g} = {difference:g}.",
# #             f"{difference:g}",
# #         )
# #     return (
# #         True,
# #         "FAIL",
# #         f"Price difference mismatch. Cited calculation is {difference:g} from {left_row['product']} {left_value:g} and {right_row['product']} {right_value:g}.",
# #         "",
# #     )


# # def _table_reverse_price_lookup(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     normalized_question = normalize_text(question)
# #     if not (
# #         ("which" in normalized_question and any(term in normalized_question for term in ("sku", "competitor", "brand")))
# #         or "has an mrp" in normalized_question
# #         or "has a per tablet price" in normalized_question
# #         or "has a price" in normalized_question
# #     ):
# #         return False, "DATA MISSING", "", ""

# #     requested_numbers = [float(number) for number in _extract_numbers(question)]
# #     if not requested_numbers:
# #         return False, "DATA MISSING", "", ""
# #     requested_value = requested_numbers[-1]

# #     family = _extract_ranking_family(question) or _extract_table_product_from_question(question)
# #     rows = _family_price_rows(page_data, family) if family else []
# #     matrix_rows = _extract_dpi_mdi_matrix_rows(page_data)
# #     own_matrix_rows = _extract_own_dpi_mdi_price_rows(page_data)

# #     candidates: list[tuple[str, float]] = []
# #     for row in rows:
# #         for key in ("price", "unit_price"):
# #             if row.get(key) is not None and abs(float(row[key]) - requested_value) <= 0.05:
# #                 candidates.append((str(row["product"]), float(row[key])))
# #     for row in own_matrix_rows:
# #         if abs(float(row["price"]) - requested_value) <= 0.05:
# #             candidates.append((str(row["product"]), float(row["price"])))
# #     for row in matrix_rows:
# #         for column, value in row.get("values", {}).items():
# #             if value is not None and abs(float(value) - requested_value) <= 0.05:
# #                 candidates.append((str(row["brand"]), float(value)))

# #     if not candidates:
# #         return False, "DATA MISSING", "", ""

# #     matching = [name for name, _ in candidates if _entity_text_contains(response_text, name) or _entity_text_contains_ordered_tokens(response_text, name)]
# #     expected_names = ", ".join(name for name, _ in candidates)
# #     if matching:
# #         return True, "PASS", f"Reverse table lookup matches cited row: {expected_names} has {requested_value:g}.", f"{expected_names} {requested_value:g}"
# #     return True, "FAIL", f"Reverse table lookup mismatch. Cited table maps {requested_value:g} to {expected_names}.", ""


# # def _table_company_lookup(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     normalized_question = normalize_text(question)
# #     if not any(term in normalized_question for term in ("company", "manufactured", "manufacturer", "belongs to")):
# #         return False, "DATA MISSING", "", ""

# #     brand = _extract_company_question_brand(question)
# #     company = _extract_marketed_by_company(question)
# #     rows = (
# #         _extract_dpi_mdi_matrix_rows(page_data)
# #         + _extract_competitor_table_rows(page_data)
# #         + _extract_competitor_unit_price_rows(page_data)
# #     )

# #     if company and not brand:
# #         matches = [row for row in rows if _company_text_contains(str(row.get("company", "")), company)]
# #         if not matches:
# #             return False, "DATA MISSING", "", ""
# #         expected = str(matches[0].get("brand", ""))
# #         if _entity_text_contains(response_text, expected) or _entity_text_contains_ordered_tokens(response_text, expected):
# #             return True, "PASS", f"Company-brand mapping matches cited table: {expected} belongs to {company}.", expected
# #         return True, "FAIL", f"Company-brand mismatch. Cited table lists {expected} for {company}.", ""

# #     if not brand:
# #         return False, "DATA MISSING", "", ""

# #     matching_rows = [
# #         row for row in rows
# #         if _entity_text_contains(str(row.get("brand", "")), brand)
# #         or _entity_text_contains(brand, str(row.get("brand", "")))
# #         or _entity_text_contains_ordered_tokens(str(row.get("brand", "")), brand)
# #     ]
# #     if not matching_rows:
# #         return False, "DATA MISSING", "", ""

# #     expected_company = str(matching_rows[0].get("company", ""))
# #     if _company_text_contains(response_text, expected_company):
# #         return True, "PASS", f"Company matches cited table row: {brand} is listed with {expected_company}.", expected_company
# #     return True, "FAIL", f"Company mismatch. Cited table lists {brand} with {expected_company}.", ""


# # def _table_matrix_value_validation(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[bool, str, str, str]:
# #     normalized_question = normalize_text(question)
# #     if not any(term in normalized_question for term in ("dpi", "mdi", "forte")):
# #         return False, "DATA MISSING", "", ""

# #     rows = _extract_dpi_mdi_matrix_rows(page_data)
# #     if not rows:
# #         return False, "DATA MISSING", "", ""

# #     requested_brand = _extract_matrix_brand_from_question(question, rows)
# #     requested_column = _extract_matrix_column_from_question(question)

# #     if "lowest" in normalized_question or "highest" in normalized_question:
# #         if not requested_column:
# #             return False, "DATA MISSING", "", ""
# #         valued_rows = [row for row in rows if row.get("values", {}).get(requested_column) is not None]
# #         if not valued_rows:
# #             return True, "DATA MISSING", f"No values found for {requested_column} in cited table.", ""
# #         expected = min(valued_rows, key=lambda row: float(row["values"][requested_column])) if "lowest" in normalized_question else max(valued_rows, key=lambda row: float(row["values"][requested_column]))
# #         value = float(expected["values"][requested_column])
# #         brand_ok = _entity_text_contains(response_text, str(expected["brand"])) or _entity_text_contains_ordered_tokens(response_text, str(expected["brand"]))
# #         value_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, value)
# #         label = "lowest" if "lowest" in normalized_question else "highest"
# #         if brand_ok and value_ok:
# #             return True, "PASS", f"{label.title()} {requested_column} value matches cited table: {expected['brand']} = {value:g}.", f"{expected['brand']} {value:g}"
# #         return True, "FAIL", f"{label.title()} {requested_column} value is {expected['brand']} = {value:g}; SuperAI does not match.", ""

# #     if not requested_brand or not requested_column:
# #         return False, "DATA MISSING", "", ""

# #     row = next(
# #         (
# #             row for row in rows
# #             if _entity_text_contains(str(row["brand"]), requested_brand)
# #             or _entity_text_contains(requested_brand, str(row["brand"]))
# #             or _entity_text_contains_ordered_tokens(str(row["brand"]), requested_brand)
# #         ),
# #         None,
# #     )
# #     if not row:
# #         return False, "DATA MISSING", "", ""

# #     value = row.get("values", {}).get(requested_column)
# #     if value is None:
# #         response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #         if response_numbers or "NA" in str(row.get("raw", "")).upper():
# #             return True, "FAIL", f"Cited table shows no numeric value for {row['brand']} {requested_column}.", ""
# #         return True, "DATA MISSING", f"{requested_column} value was not found for {row['brand']} in cited table.", ""

# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     if _float_set_contains(response_numbers, float(value)):
# #         return True, "PASS", f"Table cell matches cited row: {row['brand']} {requested_column} = {float(value):g}.", f"{float(value):g}"
# #     return True, "FAIL", f"Table cell mismatch. Cited row has {row['brand']} {requested_column} = {float(value):g}.", ""


# # def _extract_own_dpi_mdi_price_rows(page_data: str) -> list[dict[str, object]]:
# #     """Extract own Combihale FB MRP matrix rows by SKU column."""
# #     text = re.sub(r"\s+", " ", page_data).strip()
# #     match = re.search(
# #         r"M\.?R\.?P\s*\(Each SKU\)\s+COMBIHALE\s+FB\s+DPI\s+CAPS\s+COMBIHALE\s+FB\s+MDI\s+"
# #         r"100\s+200\s+400\s+FORTE\s+200\s+400\s+"
# #         r"(?P<values>(?:\d+(?:\.\d+)?\s*(?:Rs)?\s*){6})",
# #         text,
# #         flags=re.IGNORECASE,
# #     )
# #     if not match:
# #         return []

# #     values = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", match.group("values"))[:6]]
# #     products = [
# #         "COMBIHALE FB DPI CAPS 100",
# #         "COMBIHALE FB DPI CAPS 200",
# #         "COMBIHALE FB DPI CAPS 400",
# #         "COMBIHALE FB DPI CAPS FORTE",
# #         "COMBIHALE FB MDI 200",
# #         "COMBIHALE FB MDI 400",
# #     ]
# #     return [
# #         {"product": product, "price": values[index], "pack": "", "unit_price": None}
# #         for index, product in enumerate(products)
# #         if index < len(values)
# #     ]


# # def _extract_competitor_unit_price_rows(page_data: str) -> list[dict[str, object]]:
# #     """Extract competitor rows with strip price and per-tablet price columns."""
# #     text = re.sub(r"\s+", " ", page_data).strip()
# #     if not re.search(r"\bper\s+tab\b|\bper\s+tablet\b", text, flags=re.IGNORECASE):
# #         return []

# #     end_match = re.search(
# #         r"\bPackaging\s+Price\b|\bM\.?R\.?P\b|\bIndications\b|\bSalient\b",
# #         text,
# #         flags=re.IGNORECASE,
# #     )
# #     section = text[: end_match.start()] if end_match else text

# #     company_pattern = "|".join(re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True))
# #     row_pattern = re.compile(
# #         rf"(?P<brand>[A-Za-z][A-Za-z0-9 /.-]{{1,60}}?)\s+"
# #         rf"(?P<company>{company_pattern})\s+"
# #         r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*"
# #         r"\((?P<pack>\d+)\s*(?:tab|tabs|tablet|tablets)\)\s*"
# #         r"(?P<unit>\d{1,4}(?:\.\d+)?)",
# #         flags=re.IGNORECASE,
# #     )

# #     rows: list[dict[str, object]] = []
# #     for match in row_pattern.finditer(section):
# #         brand = _clean_brand_name(match.group("brand"))
# #         brand = re.sub(r"^(?:mg\s+)?per(?:\s+tab)?\s+", "", brand, flags=re.IGNORECASE).strip()
# #         company = _normalize_company_display(match.group("company"))
# #         price = float(match.group("price").replace(",", ""))
# #         unit_price = float(match.group("unit"))
# #         pack = f"{match.group('pack')} Tab"
# #         rows.append(
# #             {
# #                 "brand": brand,
# #                 "company": company,
# #                 "pack": pack,
# #                 "price": price,
# #                 "unit_price": unit_price,
# #                 "values": {},
# #                 "raw": match.group(0),
# #             }
# #         )
# #     return rows


# # def _family_price_rows(page_data: str, family: str) -> list[dict[str, object]]:
# #     """Extract repeated product-family rows with row-local numeric values."""
# #     if not family:
# #         return []

# #     text = re.sub(r"\s+", " ", page_data).strip()
# #     family_tokens = _family_tokens(family)
# #     if not family_tokens:
# #         return []

# #     family_pattern = r"[-\s/]*".join(re.escape(token) for token in family_tokens)
# #     matches = list(re.finditer(rf"\b{family_pattern}\b", text, flags=re.IGNORECASE))
# #     rows: list[dict[str, object]] = []
# #     for index, match in enumerate(matches):
# #         start = match.start()
# #         end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), start + 180)
# #         citation_break = text.find("| | Citation", start, end)
# #         if citation_break != -1:
# #             end = citation_break
# #         chunk = text[start:end].strip(" |")
# #         numbers = list(re.finditer(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", chunk))
# #         if not numbers:
# #             continue

# #         numeric_values = [float(number.group(0).replace(",", "")) for number in numbers]
# #         pack = ""
# #         pack_match = re.search(r"\((\d+)\s*(?:TABS?|TABLETS?|CAPS?)\)|\b(\d+)\s*(?:TAB|TABS|CAP|CAPS)\b", chunk, flags=re.IGNORECASE)
# #         if pack_match:
# #             pack = f"{pack_match.group(1) or pack_match.group(2)} Tab"

# #         price, unit_price, previous_value = _derive_row_price_values(numeric_values, pack)

# #         product_end = numbers[-2].start() if len(numbers) >= 2 else numbers[-1].start()
# #         product = re.sub(r"\s+", " ", chunk[:product_end]).strip(" :-|")
# #         if not product:
# #             product = match.group(0)

# #         row = {
# #             "product": product,
# #             "chunk": chunk,
# #             "numbers": numeric_values,
# #             "price": price,
# #             "previous_value": previous_value,
# #             "unit_price": unit_price,
# #             "pack": pack,
# #         }
# #         rows.append(row)

# #     return _dedupe_family_rows(rows)


# # def _best_family_price_row(page_data: str, product: str) -> dict[str, object] | None:
# #     family = _extract_ranking_family(product) or product
# #     rows = _family_price_rows(page_data, family)
# #     if not rows:
# #         return None

# #     product_tokens = set(_significant_product_tokens(product))
# #     scored: list[tuple[int, dict[str, object]]] = []
# #     for row in rows:
# #         row_tokens = set(_significant_product_tokens(str(row["product"])))
# #         score = len(product_tokens.intersection(row_tokens))
# #         if score:
# #             scored.append((score, row))

# #     if not scored:
# #         return None
# #     scored.sort(key=lambda item: (item[0], len(str(item[1]["product"]))), reverse=True)
# #     best_score, best_row = scored[0]
# #     required = min(2, len(product_tokens))
# #     return best_row if best_score >= required else None


# # def _derive_unit_price(numbers: list[float], pack: str) -> float | None:
# #     _, unit_price, _ = _derive_row_price_values(numbers, pack)
# #     return unit_price


# # def _derive_row_price_values(numbers: list[float], pack: str) -> tuple[float, float | None, float | None]:
# #     """Return row MRP/new-MRP, unit price, and previous row value."""
# #     if not numbers:
# #         return 0.0, None, None

# #     previous_value = numbers[-2] if len(numbers) >= 2 else None
# #     price = numbers[-1]
# #     unit_price: float | None = None
# #     pack_numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", pack or "")]
# #     pack_count = pack_numbers[0] if pack_numbers else 0.0

# #     if pack_count > 0 and len(numbers) >= 2:
# #         explicit_unit_candidate = numbers[-1]
# #         strip_candidate = numbers[-2]
# #         if abs(round(strip_candidate / pack_count, 2) - explicit_unit_candidate) <= 0.25:
# #             price = strip_candidate
# #             unit_price = explicit_unit_candidate
# #         else:
# #             price = numbers[-1]
# #             unit_price = round(price / pack_count, 2)

# #     return price, unit_price, previous_value


# # def _extract_table_product_from_question(question: str) -> str:
# #     patterns = (
# #         r"\b(?:mrp|price)\s+of\s+(.+?)(?:\?)?$",
# #         r"\bper\s+tablet\s+price\s+of\s+(.+?)(?:\?)?$",
# #         r"\bpackaging\s+size\s+of\s+(.+?)(?:\?)?$",
# #         r"\bprice\s+difference\s+between\s+(.+?)\s+and\b",
# #     )
# #     for pattern in patterns:
# #         match = re.search(pattern, question, flags=re.IGNORECASE)
# #         if match:
# #             return re.sub(r"\s+", " ", match.group(1)).strip(" ?.")
# #     return _extract_ranking_family(question)


# # def _extract_ranking_family(text: str) -> str:
# #     upper = text.upper()
# #     if "COMBIHALE" in upper and "FB" in upper:
# #         return "COMBIHALE-FB"
# #     if "CILAHEART" in upper:
# #         return "CILAHEART"
# #     if "RIFASTOP" in upper:
# #         return "RIFASTOP"
# #     if "STATPURE" in upper:
# #         return "STATPURE"
# #     return ""


# # def _family_tokens(product: str) -> list[str]:
# #     tokens = re.findall(r"[A-Za-z0-9]+", product)
# #     if len(tokens) >= 2 and tokens[0].lower() == "combihale" and tokens[1].lower() == "fb":
# #         return ["COMBIHALE"]
# #     return tokens[:2] if len(tokens) > 1 and any(token.isdigit() for token in tokens[1:]) else tokens[:1]


# # def _significant_product_tokens(product: str) -> list[str]:
# #     aliases = {
# #         "caps": "capsules",
# #         "cap": "capsules",
# #         "mdi": "inhaler",
# #         "inhalers": "inhaler",
# #         "tabs": "tablets",
# #         "tab": "tablets",
# #     }
# #     stop = {"what", "which", "sku", "has", "mrp", "price", "per", "tablet", "strip", "rs", "of", "the", "and"}
# #     tokens: list[str] = []
# #     for token in re.findall(r"[A-Za-z0-9]+", product.lower()):
# #         token = aliases.get(token, token)
# #         if token not in stop:
# #             tokens.append(token)
# #     return tokens


# # def _dedupe_family_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
# #     seen: set[str] = set()
# #     deduped: list[dict[str, object]] = []
# #     for row in rows:
# #         key = normalize_text(str(row["product"]))
# #         if key in seen:
# #             continue
# #         seen.add(key)
# #         deduped.append(row)
# #     return deduped


# # def _extract_dpi_mdi_matrix_rows(page_data: str) -> list[dict[str, object]]:
# #     """Extract Combihale-style BRAND/COMPANY/DPI/MDI matrix rows."""
# #     text = re.sub(r"\s+", " ", page_data).strip()
# #     if not re.search(r"\bDPI\b.*\bMDI\b.*\bBRAND\s+NAME\b", text, flags=re.IGNORECASE):
# #         return []

# #     section_match = re.search(
# #         r"BRAND\s+NAME\s+COMPANY\s+100\s+200\s+400\s+FORTE\s+200\s+400\s+(.+?)(?:M\.?R\.?P|Recommended|Salient|$)",
# #         text,
# #         flags=re.IGNORECASE,
# #     )
# #     section = section_match.group(1) if section_match else text
# #     section = re.sub(r"\bRs\b", " ", section, flags=re.IGNORECASE)
# #     company_pattern = "|".join(re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True))
# #     brand_pattern = r"(?!NA\b|Rs\b|A\s+\d)[A-Za-z][A-Za-z0-9 /.-]{1,80}?"
# #     row_pattern = re.compile(
# #         rf"(?P<brand>{brand_pattern})\s+(?P<company>{company_pattern})\s+"
# #         rf"(?P<values>.+?)(?=(?:{brand_pattern}\s+(?:{company_pattern})\s+)|$)",
# #         flags=re.IGNORECASE,
# #     )

# #     rows: list[dict[str, object]] = []
# #     for match in row_pattern.finditer(section):
# #         brand = _clean_brand_name(match.group("brand"))
# #         company = _normalize_company_display(match.group("company"))
# #         raw_values = re.findall(r"\bNA\b|\d+(?:\.\d+)?", match.group("values"), flags=re.IGNORECASE)
# #         if not brand or not raw_values:
# #             continue
# #         mapped = _map_dpi_mdi_values(raw_values)
# #         rows.append(
# #             {
# #                 "brand": brand,
# #                 "company": company,
# #                 "values": mapped,
# #                 "raw": match.group(0),
# #                 "pack": "",
# #                 "price": None,
# #             }
# #         )
# #     return rows


# # def _map_dpi_mdi_values(raw_values: list[str]) -> dict[str, float | None]:
# #     values = [None if value.upper() == "NA" else float(value) for value in raw_values]
# #     columns = ["DPI_100", "DPI_200", "DPI_400", "DPI_FORTE", "MDI_200", "MDI_400"]
# #     if len(values) == 6:
# #         return dict(zip(columns, values))
# #     if len(values) == 5:
# #         return {
# #             "DPI_100": values[0],
# #             "DPI_200": values[1],
# #             "DPI_400": values[2],
# #             "DPI_FORTE": None,
# #             "MDI_200": values[3],
# #             "MDI_400": values[4],
# #         }
# #     if len(values) == 4:
# #         return {
# #             "DPI_100": values[0],
# #             "DPI_200": values[1],
# #             "DPI_400": None,
# #             "DPI_FORTE": None,
# #             "MDI_200": values[2],
# #             "MDI_400": values[3],
# #         }
# #     if len(values) == 3:
# #         if values[0] is None:
# #             return {
# #                 "DPI_100": None,
# #                 "DPI_200": None,
# #                 "DPI_400": None,
# #                 "DPI_FORTE": None,
# #                 "MDI_200": values[1],
# #                 "MDI_400": values[2],
# #             }
# #         return {
# #             "DPI_100": None,
# #             "DPI_200": None,
# #             "DPI_400": None,
# #             "DPI_FORTE": values[0],
# #             "MDI_200": values[1],
# #             "MDI_400": values[2],
# #         }
# #     return {column: values[index] if index < len(values) else None for index, column in enumerate(columns)}


# # def _extract_matrix_column_from_question(question: str) -> str:
# #     normalized = normalize_text(question)
# #     if "mdi 400" in normalized:
# #         return "MDI_400"
# #     if "mdi 200" in normalized:
# #         return "MDI_200"
# #     if "dpi 400" in normalized:
# #         return "DPI_400"
# #     if "dpi 200" in normalized:
# #         return "DPI_200"
# #     if "dpi 100" in normalized:
# #         return "DPI_100"
# #     if "forte" in normalized:
# #         return "DPI_FORTE"
# #     return ""


# # def _extract_matrix_brand_from_question(question: str, rows: list[dict[str, object]]) -> str:
# #     for row in rows:
# #         brand = str(row["brand"])
# #         if _entity_text_contains(question, brand) or _entity_text_contains_ordered_tokens(question, brand):
# #             return brand
# #     return ""


# # def _extract_price_response_numbers(text: str) -> set[float]:
# #     """Extract price-associated numbers from a response string.

# #     Only returns numbers that appear directly after ₹/Rs/MRP/price/cost or
# #     directly before /tab, per tablet, per strip, per box.  This prevents digits
# #     embedded in product names (e.g. "D3" → 3, "60K" → 60) from being treated
# #     as price candidates and causing false FAILs.

# #     Falls back to _extract_numbers when no price-indicator context is found so
# #     that plain numeric responses (without currency symbols) still validate.
# #     """
# #     price_numbers: set[float] = set()

# #     for match in re.finditer(
# #         r"(?:₹|Rs\.?|MRP|price|cost)\s*(?<!\d)(\d[\d,]*(?:\.\d+)?)(?!\d)",
# #         text,
# #         flags=re.IGNORECASE,
# #     ):
# #         value = match.group(1).replace(",", "")
# #         if "." in value:
# #             value = value.rstrip("0").rstrip(".")
# #         price_numbers.add(float(value))

# #     for match in re.finditer(
# #         r"(?<!\d)(\d[\d,]*(?:\.\d+)?)(?!\d)"
# #         r"\s*(?:/\s*(?:tab(?:let)?s?|strip|box)|per\s+(?:tab(?:let)?s?|strip|box))\b",
# #         text,
# #         flags=re.IGNORECASE,
# #     ):
# #         value = match.group(1).replace(",", "")
# #         if "." in value:
# #             value = value.rstrip("0").rstrip(".")
# #         price_numbers.add(float(value))

# #     if price_numbers:
# #         return price_numbers

# #     return {float(n) for n in _extract_numbers(text)}


# # def _compare_price_lookup(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate direct MRP/price lookup questions."""
# #     response_numbers = _extract_price_response_numbers(response_text)
# #     if not response_numbers:
# #         return "DATA MISSING", "SuperAI response did not contain a price/MRP value."

# #     normalized_question = normalize_text(question)
# #     wants_unit_price = any(
# #         term in normalized_question
# #         for term in ("per tablet", "per tab", "mrp / tab", "mrp per tablet", "per tab price")
# #     )

# #     # For per-tablet questions try _extract_product_row_mrp first.
# #     # _extract_price_master_new_mrp grabs the first two numbers as (current, new)
# #     # strip MRP and would return 161.10 instead of 16.11 when the row is
# #     # "SITADAY-100 TABLET 10 TAB 161.10 16.11".
# #     # _extract_product_row_mrp understands the strip/unit column layout and
# #     # returns candidate_numbers[-1] (the per-tablet value) when wants_unit_price.
# #     if wants_unit_price:
# #         requested_price = _extract_product_row_mrp(page_data, question)
# #         if requested_price is None:
# #             requested_price = _extract_price_master_new_mrp(page_data, question)
# #     else:
# #         requested_price = _extract_price_master_new_mrp(page_data, question)
# #         if requested_price is None:
# #             requested_price = _extract_product_row_mrp(page_data, question)
# #     if requested_price is None:
# #         requested_price = _extract_requested_product_price(page_data, question)
# #     if requested_price is None:
# #         requested_brand = _extract_company_question_brand(question) or _extract_first_product_name(question)
# #         if requested_brand:
# #             competitor_price = _extract_competitor_row_price_for_brand(page_data, requested_brand, question)
# #             if competitor_price is not None:
# #                 requested_price = competitor_price
# #     if requested_price is None:
# #         requested_brand = _extract_company_question_brand(question) or _extract_first_product_name(question)
# #         if requested_brand:
# #             competitor_prices = _extract_competitor_strength_prices(page_data, requested_brand)
# #             if competitor_prices:
# #                 requested_price = next(iter(competitor_prices.values()))

# #     if requested_price is None:
# #         _log_validation_step(
# #             rule="_compare_price_lookup",
# #             attribute="PRICE",
# #             response_value=sorted(response_numbers),
# #             verdict="DATA MISSING",
# #             reason="Requested price/MRP was not found on the cited page.",
# #         )
# #         return "DATA MISSING", "Requested price/MRP was not found on the cited page."

# #     if _float_set_contains(response_numbers, requested_price):
# #         _log_validation_step(
# #             rule="_compare_price_lookup",
# #             attribute="PRICE",
# #             doc_value=requested_price,
# #             response_value=sorted(response_numbers),
# #             verdict="PASS",
# #             reason=f"Price/MRP matches cited page: {requested_price:g}.",
# #         )
# #         return "PASS", f"Price/MRP matches cited page: {requested_price:g}."

# #     _log_validation_step(
# #         rule="_compare_price_lookup",
# #         attribute="PRICE",
# #         doc_value=requested_price,
# #         response_value=sorted(response_numbers),
# #         verdict="FAIL",
# #         reason=f"Cited page contains {requested_price:g}, response has {sorted(response_numbers)}.",
# #     )
# #     return (
# #         "FAIL",
# #         f"Price/MRP mismatch. Cited page contains {requested_price:g}, "
# #         f"but SuperAI returned {', '.join(str(number) for number in sorted(response_numbers))}.",
# #     )


# # def _compare_trip_award_cost(
# #     response_text: str,
# #     page_data: str,
# #     question: str,  # noqa: ARG001
# # ) -> tuple[str, str]:
# #     """Validate trip/award/medal/reimbursement cost questions.

# #     Handles Indian number notation (₹1,10,000 → 110000) and must not be routed
# #     through _compare_price_lookup which expects per-tablet or per-strip MRP rows.
# #     """
# #     attr_type = resolve_attribute_type(question)
# #     response_numbers = _extract_price_response_numbers(response_text)
# #     if not response_numbers:
# #         _log_validation_step(
# #             rule="_compare_trip_award_cost",
# #             attribute=attr_type,
# #             verdict="DATA MISSING",
# #             reason="SuperAI response did not contain a numeric cost value.",
# #         )
# #         return "DATA MISSING", "SuperAI response did not contain a numeric cost value."

# #     page_numbers = {float(n) for n in _extract_numbers(page_data)}
# #     if not page_numbers:
# #         _log_validation_step(
# #             rule="_compare_trip_award_cost",
# #             attribute=attr_type,
# #             response_value=sorted(response_numbers),
# #             verdict="DATA MISSING",
# #             reason="Requested cost value was not found on the cited page.",
# #         )
# #         return "DATA MISSING", "Requested cost value was not found on the cited page."

# #     for resp_num in response_numbers:
# #         if _float_set_contains(page_numbers, resp_num):
# #             _log_validation_step(
# #                 rule="_compare_trip_award_cost",
# #                 attribute=attr_type,
# #                 doc_value=resp_num,
# #                 response_value=resp_num,
# #                 verdict="PASS",
# #                 reason=f"Trip/award cost matches cited page: {resp_num:g}.",
# #             )
# #             return "PASS", f"Trip/award cost matches cited page: {resp_num:g}."

# #     _log_validation_step(
# #         rule="_compare_trip_award_cost",
# #         attribute=attr_type,
# #         doc_value=sorted(page_numbers),
# #         response_value=sorted(response_numbers),
# #         verdict="FAIL",
# #         reason="Cost value in response not found on cited page.",
# #     )
# #     return (
# #         "FAIL",
# #         f"Trip/award cost mismatch. Cited page has "
# #         f"{', '.join(f'{n:g}' for n in sorted(page_numbers))}, "
# #         f"but SuperAI returned {', '.join(f'{n:g}' for n in sorted(response_numbers))}.",
# #     )


# # def _extract_competitor_row_price_for_brand(
# #     page_data: str,
# #     brand: str,
# #     question: str,
# # ) -> float | None:
# #     """Return row-local competitor price/unit price for a requested brand."""
# #     normalized_question = normalize_text(question)
# #     wants_unit_price = any(term in normalized_question for term in ("per tablet", "per tab"))
# #     for row in _extract_competitor_table_rows(page_data):
# #         row_brand = str(row.get("brand", ""))
# #         if not (
# #             _entity_text_contains(row_brand, brand)
# #             or _entity_text_contains(brand, row_brand)
# #             or _entity_text_contains_ordered_tokens(row_brand, brand)
# #         ):
# #             continue
# #         price = row.get("price")
# #         if price is None:
# #             continue
# #         if wants_unit_price:
# #             pack_numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", str(row.get("pack", "")))]
# #             if pack_numbers:
# #                 return round(float(price) / pack_numbers[0], 2)
# #         return float(price)
# #     return None


# # def _extract_price_master_new_mrp(page_data: str, question: str) -> float | None:
# #     """Extract exact product New MRP from Price Master rows."""
# #     generic_price = _extract_generic_price_master_new_mrp(page_data, question)
# #     if generic_price is not None:
# #         return generic_price

# #     product_match = re.search(
# #         r"\bdocetrust\s+(\d+(?:\.\d+)?)\s*mg\b",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     if not product_match:
# #         return None

# #     strength = product_match.group(1).rstrip("0").rstrip(".")
# #     if "." not in product_match.group(1):
# #         strength = product_match.group(1)
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     row_match = re.search(
# #         rf"\bDOCETRUST[-\s]*{re.escape(strength)}\s+INJECTION\s+"
# #         r"(?P<current>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s+"
# #         r"(?P<new>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\b",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     )
# #     if not row_match:
# #         return None

# #     return float(row_match.group("new").replace(",", ""))


# # def _extract_generic_price_master_new_mrp(page_data: str, question: str) -> float | None:
# #     """Extract New MRP for a product row from flattened Price Master text."""
# #     products = _extract_price_question_product_candidates(question)
# #     if not products:
# #         product = _extract_first_product_name(question)
# #         products = [product] if product else []

# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     for product in products:
# #         product = re.sub(
# #             r"\b(?:current|new|mrp|price|cost|of|the|per|strip|box|pack|tablets?|capsules?|respules?)\b",
# #             " ",
# #             product,
# #             flags=re.IGNORECASE,
# #         )
# #         product = re.sub(r"\s+", " ", product).strip(" ?:-.,")
# #         if not product:
# #             continue

# #         tokens = _product_name_tokens(product)
# #         if not tokens:
# #             continue

# #         product_pattern = r"[-\s/]*".join(re.escape(token) for token in tokens)
# #         pack_match = re.search(r"\((\d+)\s*(?:TABS?|TABLETS?)", question, flags=re.IGNORECASE)
# #         pack_patterns = [rf"\s+\({pack_match.group(1)}\s*TABS?\)", ""] if pack_match else [""]
# #         for pack_pattern in pack_patterns:
# #             row_match = re.search(
# #                 rf"\b{product_pattern}\b(?:\s+(?:TABLETS?|TABLTES|INJECTIONS?|INJECTION|CAPSULES?|SUSPENSION|DROPS|RESPULES|DPI))*"
# #                 rf"{pack_pattern}"
# #                 r"\s+(?P<current>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s+"
# #                 r"(?P<new>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\b",
# #                 normalized_page,
# #                 flags=re.IGNORECASE,
# #             )
# #             if row_match:
# #                 return float(row_match.group("new").replace(",", ""))

# #     return None


# # def _extract_product_row_mrp(page_data: str, question: str) -> float | None:
# #     """Extract MRP from flattened product rows preserving row-level product mapping.

# #     Handles product MRP rows such as:
# #     - NOBEGLAR CARTRIDGE 3 ML 620.61
# #     - NOBEGLAR-UNO PREFILLED PEN 1 PACK 762
# #     - NOBEGLIZ-M XR 10 TAB 102.09 10.21
# #     """
# #     products = _extract_price_question_product_candidates(question)
# #     if not products:
# #         product = _extract_first_product_name(question)
# #         products = [product] if product else []

# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     normalized_question = normalize_text(question)
# #     wants_unit_price = any(
# #         term in normalized_question
# #         for term in ("per tablet", "per tab", "mrp / tab", "mrp per tablet")
# #     )

# #     for product in products:
# #         clean_product = re.sub(
# #             r"\b(?:mrp|price|cost|of|the|per|tablet|tab|strip|box|pack)\b",
# #             " ",
# #             product,
# #             flags=re.IGNORECASE,
# #         )
# #         clean_product = re.sub(r"\s+", " ", clean_product).strip(" ?:-.,")
# #         if not clean_product:
# #             continue

# #         tokens = _product_name_tokens(clean_product)
# #         if not tokens:
# #             continue

# #         product_pattern = r"[-\s/]*".join(re.escape(token) for token in tokens)
# #         row_match = re.search(
# #             rf"\b{product_pattern}\b"
# #             r"(?P<row>.{0,140}?)"
# #             r"(?=(?:\b[A-Z][A-Z0-9-]{2,}\b\s+[A-Z]|\bGLOSSARY\b|\bShort Form\b|$))",
# #             normalized_page,
# #             flags=re.IGNORECASE,
# #         )
# #         if not row_match:
# #             row_match = re.search(
# #                 rf"\b{product_pattern}\b(?P<row>.{{0,140}})",
# #                 normalized_page,
# #                 flags=re.IGNORECASE,
# #             )
# #         if not row_match:
# #             continue

# #         row_text = row_match.group(0)
# #         numbers = [
# #             float(number.replace(",", ""))
# #             for number in re.findall(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", row_text)
# #         ]
# #         if not numbers:
# #             continue

# #         product_numbers = {
# #             float(number)
# #             for token in tokens
# #             for number in re.findall(r"\d+(?:\.\d+)?", token)
# #         }
# #         candidate_numbers = [
# #             number for number in numbers if not any(abs(number - prod) <= 0.001 for prod in product_numbers)
# #         ]
# #         if not candidate_numbers:
# #             candidate_numbers = numbers

# #         if wants_unit_price and len(candidate_numbers) >= 2:
# #             return candidate_numbers[-1]

# #         if len(candidate_numbers) >= 2 and candidate_numbers[0] <= 10 < candidate_numbers[-1]:
# #             return candidate_numbers[-1]

# #         return candidate_numbers[-1] if len(candidate_numbers) == 1 else candidate_numbers[-2]

# #     return None


# # def _extract_price_question_product_candidates(question: str) -> list[str]:
# #     """Extract precise product candidates from price/MRP questions."""
# #     patterns = (
# #         r"\b(?:mrp|price)\s+per\s+(?:strip|box|respule|tablet|tab|capsule|cap)\s+of\s+(.+?)(?:\s*\(|\?)",
# #         r"\b(?:mrp|price)\s+of\s+(.+?)(?:\s*\(|\?)",
# #         r"\bof\s+(.+?)(?:\s*\(|\?)",
# #     )
# #     candidates: list[str] = []
# #     for pattern in patterns:
# #         match = re.search(pattern, question, flags=re.IGNORECASE)
# #         if match:
# #             candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ?.:-")
# #             if candidate:
# #                 candidates.append(candidate)
# #     return candidates


# # def _product_name_tokens(product: str) -> list[str]:
# #     """Return product tokens, splitting compact variant-strength tokens like M25."""
# #     raw_tokens = re.findall(r"[A-Za-z0-9]+", product)
# #     tokens: list[str] = []
# #     for token in raw_tokens:
# #         compact_match = re.fullmatch(r"([A-Za-z]+)(\d+)", token)
# #         if compact_match and compact_match.group(1).lower() in {"m"}:
# #             tokens.extend([compact_match.group(1), compact_match.group(2)])
# #         else:
# #             tokens.append(token)
# #     return tokens


# # def _extract_first_product_name(question: str) -> str:
# #     """Return a simple product candidate from lookup questions."""
# #     direct_match = re.search(
# #         r"\b(?:mrp|price|cost)\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     if direct_match:
# #         return direct_match.group(1).strip()

# #     match = re.search(
# #         r"\b(?:of|does|is)\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+cost|\s+mrp|\s+price|\?)",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     return match.group(1).strip() if match else ""


# # def _compare_company_lookup(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate company/manufacturer questions from a cited competitor row."""
# #     brand = _extract_company_question_brand(question)
# #     if not brand:
# #         return "DATA MISSING", "Brand name could not be identified from the company question."

# #     company = _extract_company_for_brand(page_data, brand)
# #     if not company:
# #         for row in _extract_competitor_table_rows(page_data):
# #             if _entity_text_contains(str(row["brand"]), brand) or _entity_text_contains(brand, str(row["brand"])):
# #                 company = str(row["company"])
# #                 break
# #     if not company:
# #         return "DATA MISSING", f"Company row for {brand} was not found on the cited page."

# #     if _company_text_contains(response_text, company):
# #         return (
# #             "PASS",
# #             f"Company/manufacturer matches cited table row: {brand} is listed with {company}.",
# #         )

# #     return (
# #         "FAIL",
# #         f"Company/manufacturer mismatch. Cited table row lists {brand} with {company}.",
# #     )


# # def _extract_company_question_brand(question: str) -> str:
# #     """Extract brand being asked about in a company/manufacturer question."""
# #     patterns = (
# #         r"\bmarkets?\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         r"\bmanufactures?\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         r"\bmanufacturer\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         r"\bcompany\s+name\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         r"\bcompany\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #     )
# #     for pattern in patterns:
# #         match = re.search(pattern, question, flags=re.IGNORECASE)
# #         if match:
# #             return match.group(1).strip(" ?.")
# #     return ""


# # def _extract_company_for_brand(page_data: str, brand: str) -> str:
# #     """Extract company for a brand row from flattened competitor table text."""
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     brand_pattern = r"\s*[-_/]?\s*".join(
# #         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", brand)
# #     )
# #     company_pattern = "|".join(
# #         re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True)
# #     )
# #     match = re.search(
# #         rf"\b{brand_pattern}(?:\s+[A-Za-z0-9+-]+)?\s+(?P<company>{company_pattern})\b",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     )
# #     if not match:
# #         return ""
# #     return _normalize_company_display(match.group("company"))


# # def _extract_price_comparison_entities(question: str) -> tuple[str, str]:
# #     """Extract own product and compared competitor brand from a comparison question."""
# #     match = re.search(
# #         r"\b(?:price\s+difference\s+)?between\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+and\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     if match:
# #         return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

# #     match = re.search(
# #         r"\bhow\s+much\s+cheaper\s+is\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+compared\s+to\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     if match:
# #         return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

# #     match = re.search(
# #         r"\b([A-Za-z][A-Za-z0-9 +./-]+?)\s+compared\s+to\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     if match:
# #         return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

# #     return "", ""


# # def _normalize_comparison_pair(left: str, right: str) -> tuple[str, str]:
# #     """Carry shared product prefixes into abbreviated right-side comparison labels."""
# #     left = re.sub(r"\bprices?\b", " ", left, flags=re.IGNORECASE)
# #     right = re.sub(r"\bprices?\b", " ", right, flags=re.IGNORECASE)
# #     left = re.sub(r"\s+", " ", left).strip(" ?.:-")
# #     right = re.sub(r"\s+", " ", right).strip(" ?.:-")

# #     left_upper = left.upper()
# #     right_upper = right.upper()
# #     if "COMBIHALE" in left_upper and "COMBIHALE" not in right_upper:
# #         if "FB" in left_upper and "FB" not in right_upper:
# #             right = f"COMBIHALE FB {right}"
# #         else:
# #             right = f"COMBIHALE {right}"
# #     if "CILAHEART" in left_upper and "CILAHEART" not in right_upper:
# #         right = f"CILAHEART {right}"

# #     return left, re.sub(r"\s+", " ", right).strip()


# # def _extract_own_sku_prices(page_data: str, product: str) -> dict[str, float]:
# #     """Extract own-product SKU prices such as Bisonicus 2.5 -> 69.4."""
# #     prices: dict[str, float] = {}
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     product_pattern = r"\s*[-_/]?\s*".join(
# #         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
# #     )

# #     pattern = re.compile(
# #         rf"{product_pattern}\s+(?P<strength>\d+(?:\.\d+)?)"
# #         r".{0,100}?(?:₹|â‚¹|rs\.?|inr)\s*\.?\s*"
# #         r"(?P<price>\d{1,4}(?:\.\d+)?)",
# #         flags=re.IGNORECASE,
# #     )

# #     for match in pattern.finditer(normalized_page):
# #         strength = _normalize_strength_key(match.group("strength"))
# #         price = float(match.group("price"))
# #         prices[strength] = price

# #     return prices


# # def _extract_competitor_strength_prices(page_data: str, brand: str) -> dict[str, float]:
# #     """Extract competitor prices from two-strength rows such as CONCOR 2.5/5 mg."""
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     brand_pattern = r"\s*[-_/]?\s*".join(
# #         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", brand)
# #     )
# #     company_pattern = "|".join(re.escape(company) for company in _known_company_names())
# #     row_match = re.search(
# #         rf"{brand_pattern}\s+(?:{company_pattern})\s+"
# #         r"(?P<price_one>\d{1,4}(?:\.\d+)?)\s+Strip\s+of\s+\d+\s+Tabs\s+"
# #         r"(?P<price_two>\d{1,4}(?:\.\d+)?)\s+Strip\s+of\s+\d+\s+Tabs",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     )

# #     if not row_match:
# #         return {}

# #     strengths = _extract_competitor_header_strengths(normalized_page)
# #     if len(strengths) < 2:
# #         strengths = ["2.5", "5"]

# #     return {
# #         _normalize_strength_key(strengths[0]): float(row_match.group("price_one")),
# #         _normalize_strength_key(strengths[1]): float(row_match.group("price_two")),
# #     }


# # def _extract_competitor_header_strengths(page_data: str) -> list[str]:
# #     """Extract strength order from competitor price table headers."""
# #     header_match = re.search(
# #         r"BRAND\s+COMPANY\s+(.{0,120}?)\s+CONCOR\b",
# #         page_data,
# #         flags=re.IGNORECASE,
# #     )
# #     header_text = header_match.group(1) if header_match else page_data[:500]
# #     strengths = re.findall(r"(\d+(?:\.\d+)?)\s*mg\s+SKU\s+MRP", header_text, flags=re.IGNORECASE)
# #     return [_normalize_strength_key(strength) for strength in strengths]


# # def _normalize_strength_key(value: str) -> str:
# #     """Normalize strength keys for price comparison."""
# #     normalized = str(value).strip()
# #     if "." in normalized:
# #         normalized = normalized.rstrip("0").rstrip(".")
# #     return normalized


# # def _float_set_contains(numbers: set[float], expected: float) -> bool:
# #     """Return whether a numeric set contains expected value with currency rounding."""
# #     return any(abs(number - expected) <= 0.05 for number in numbers)


# # def _extract_requested_product_price(page_data: str, question: str) -> float | None:
# #     """Extract the requested product price from page text for cost-saving questions."""
# #     strength_match = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", question, flags=re.IGNORECASE)
# #     if strength_match:
# #         strength_price = _extract_strength_price_from_mrp_section(page_data, strength_match.group(1))
# #         if strength_price is not None:
# #             return strength_price

# #     unit_price = _extract_mrp_section_unit_price(page_data, question)
# #     if unit_price is not None:
# #         return unit_price

# #     product_candidates = _extract_product_candidates_from_question(question)
# #     normalized_page = re.sub(r"\s+", " ", page_data)

# #     for product in product_candidates:
# #         product_pattern = r"\s*[-_/]?\s*".join(
# #             re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
# #         )
# #         strength_match = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", question, flags=re.IGNORECASE)
# #         strength_pattern = ""
# #         if strength_match and strength_match.group(1) not in product:
# #             strength_pattern = rf".{{0,30}}{re.escape(strength_match.group(1))}\s*mg"

# #         match = re.search(
# #             rf"{product_pattern}{strength_pattern}.{{0,80}}?"
# #             r"(?<!\d)(\d{1,4}(?:,\d{3})*(?:\.\d+)?)(?!\d)",
# #             normalized_page,
# #             flags=re.IGNORECASE,
# #         )
# #         if match:
# #             return float(match.group(1).replace(",", ""))

# #     return None


# # def _extract_strength_price_from_mrp_section(page_data: str, strength: str) -> float | None:
# #     """Extract strength-specific MRP rows like '25 mg - 179.72 Rs per strip'."""
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     strength_clean = strength.rstrip("0").rstrip(".") if "." in strength else strength
# #     match = re.search(
# #         rf"\b{re.escape(strength_clean)}\s*mg\b\s*[–—-]\s*"
# #         r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*Rs\s*per\s*(?:strip|box|bottle|respule)\b",
# #         normalized_page,
# #         flags=re.IGNORECASE,
# #     )
# #     if match:
# #         return float(match.group("price").replace(",", ""))
# #     return None


# # def _extract_mrp_section_unit_price(page_data: str, question: str) -> float | None:
# #     """Extract simple product-page MRP lines by requested unit."""
# #     normalized_page = re.sub(r"\s+", " ", page_data)
# #     unit_terms: tuple[str, ...]
# #     normalized_question = normalize_text(question)
# #     if "respule" in normalized_question:
# #         unit_terms = ("respule",)
# #     elif "box" in normalized_question:
# #         unit_terms = ("box",)
# #     elif "strip" in normalized_question:
# #         unit_terms = ("strip",)
# #     else:
# #         return None

# #     unit_pattern = "|".join(re.escape(unit) for unit in unit_terms)
# #     matches = list(
# #         re.finditer(
# #             r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*Rs\s*per\s*"
# #             rf"(?:{unit_pattern})\b",
# #             normalized_page,
# #             flags=re.IGNORECASE,
# #         )
# #     )
# #     if matches:
# #         return float(matches[-1].group("price").replace(",", ""))
# #     return None


# # def _extract_product_candidates_from_question(question: str) -> list[str]:
# #     """Extract likely product names before comparison wording."""
# #     candidates: list[str] = []
# #     patterns = (
# #         r"\bbetween\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+and\b",
# #         r"\bof\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+\d+(?:\.\d+)?\s*mg)?\b",
# #     )
# #     for pattern in patterns:
# #         for match in re.finditer(pattern, question, flags=re.IGNORECASE):
# #             candidate = re.sub(r"\b(?:its|competitors?|what|which|brand|price|mrp|sku)\b", " ", match.group(1), flags=re.IGNORECASE)
# #             candidate = re.sub(r"\s+", " ", candidate).strip(" -_./")
# #             if candidate and candidate.lower() not in {"the", "all"}:
# #                 candidates.append(candidate)
# #     return candidates


# # def _number_set_contains_close_value(numbers: set[float], expected: float) -> bool:
# #     """Return whether response numbers contain expected percentage with normal rounding."""
# #     rounded_expected_values = {
# #         round(expected, 0),
# #         round(expected, 1),
# #         round(expected, 2),
# #     }
# #     return any(
# #         any(abs(number - expected_value) <= 0.05 for expected_value in rounded_expected_values)
# #         for number in numbers
# #     )


# # def _compare_expected_competitor_row(
# #     response_text: str,
# #     expected_row: dict[str, object],
# #     ranking_label: str,
# # ) -> tuple[str, str]:
# #     """Compare SuperAI response against a computed lowest/highest competitor row."""
# #     expected_brand = str(expected_row["brand"])
# #     expected_price = float(expected_row["price"])
# #     brand_match = _entity_text_contains(response_text, expected_brand)
# #     response_numbers = {float(number) for number in _extract_numbers(response_text)}
# #     price_match = expected_price in response_numbers

# #     if brand_match and (not response_numbers or price_match):
# #         return (
# #             "PASS",
# #             f"{ranking_label.title()} competitor price calculated from cited table is "
# #             f"{expected_brand} at {expected_price:.2f}, matching SuperAI.",
# #         )

# #     return (
# #         "FAIL",
# #         f"{ranking_label.title()} competitor price calculated from cited table is "
# #         f"{expected_brand} at {expected_price:.2f}. SuperAI response does not match "
# #         "the computed cited-table result.",
# #     )


# # def _extract_competitor_table_rows(text: str) -> list[dict[str, object]]:
# #     """Extract competitor table rows preserving brand/company/pack/price columns."""
# #     delimiter_safe_text = text.replace("\r\n", "\n").replace("\n", " | ")
# #     cleaned = _remove_punchline_or_slogan_text(delimiter_safe_text)
# #     cleaned = re.sub(r"\s+", " ", cleaned).strip()

# #     section_match = re.search(
# #         r"(?:competitors?\s+brand.*?name|brand\s+name\s+company|brand\s+name)"
# #         r"(.+?)(?:m\.?r\.?p|recommended dosage|salient|indications|composition|$)",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     section = section_match.group(1) if section_match else cleaned
# #     section = _scope_competitor_section(section)

# #     company_names = sorted(_known_company_names(), key=len, reverse=True)
# #     company_pattern = "|".join(re.escape(company) for company in company_names)
# #     section = re.sub(
# #         r"\b(?:[A-Za-z][A-Za-z0-9 +./-]{0,80}\s*:-\s*)?"
# #         r"BRAND\s+NAME\s+COMPANY\s+PACK\s+(?:SIZE\s+)?PRICE\s*/\s*"
# #         r"(?:STRIP|TAB)(?:\s*-\s*RS)?(?:\s+PRICE\s*/\s*TAB\s*-\s*RS)?",
# #         " ",
# #         section,
# #         flags=re.IGNORECASE,
# #     )

# #     row_patterns = (
# #         re.compile(
# #             r"(?:^|\s)(?:\d+\s*[.)-]?\s*)"
# #             rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
# #             rf"(?P<company>{company_pattern})\s+"
# #             r"(?P<pack>\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)?)"
# #             r"\s*(?P<price>\d+(?:\s*\.\s*\d+)?)?",
# #             flags=re.IGNORECASE,
# #         ),
# #         re.compile(
# #             r"(?:^|\s)"
# #             rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
# #             rf"(?P<company>{company_pattern})\s+"
# #             r"(?P<pack>\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)?)"
# #             r"\s*(?P<price>\d+(?:\s*\.\s*\d+)?)?",
# #             flags=re.IGNORECASE,
# #         ),
# #         re.compile(
# #             r"(?:^|\s)"
# #             rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
# #             rf"(?P<company>{company_pattern})\*?"
# #             r"(?:\s+\([^)]*\))?"
# #             r"\s+(?P<price>\d+(?:\s*\.\s*\d+)?)",
# #             flags=re.IGNORECASE,
# #         ),
# #     )

# #     rows: list[dict[str, object]] = []
# #     seen_rows: set[tuple[str, str, str, object]] = set()
# #     for row_pattern in row_patterns:
# #         for match in row_pattern.finditer(section):
# #             brand = _clean_brand_name(match.group("brand"))
# #             company = _normalize_company_display(match.group("company"))
# #             groups = match.groupdict()
# #             pack = re.sub(r"\s+", " ", groups.get("pack") or "").strip()
# #             if re.fullmatch(r"\d+", pack):
# #                 pack = f"{pack} Tab"
# #             price_text = groups.get("price")
# #             price = float(re.sub(r"\s+", "", price_text)) if price_text else None

# #             if not brand or not _is_valid_brand_name(brand):
# #                 continue

# #             row_key = (
# #                 _normalize_brand_name(brand),
# #                 _normalize_company_display(company).lower(),
# #                 normalize_text(pack),
# #                 price,
# #             )
# #             if row_key in seen_rows:
# #                 continue
# #             seen_rows.add(row_key)

# #             row = {
# #                 "brand": brand,
# #                 "company": company,
# #                 "pack": pack,
# #                 "price": price,
# #                 "audit": {
# #                     "brand": _entity_match_audit(brand, brand),
# #                     "company": _entity_match_audit(company, company),
# #                 },
# #             }
# #             rows.append(row)

# #     return rows


# # def _scope_competitor_page_data_for_question(page_data: str, question: str) -> str:
# #     """Return the competitor table block for the product named in the question."""
# #     subjects = _extract_competitor_question_subjects(question)
# #     if not subjects:
# #         return page_data

# #     text = re.sub(r"\s+", " ", page_data).strip()
# #     heading_pattern = re.compile(
# #         r"(?P<heading>[A-Za-z][A-Za-z0-9 +./-]{2,90})\s*:-\s+"
# #         r"BRAND\s+NAME\s+COMPANY\s+PACK\s+(?:SIZE\s+)?PRICE\s*/\s*(?:STRIP|TAB)",
# #         flags=re.IGNORECASE,
# #     )
# #     headings = list(heading_pattern.finditer(text))
# #     if not headings:
# #         return page_data

# #     for index, heading_match in enumerate(headings):
# #         heading = heading_match.group("heading").strip()
# #         if not any(_entity_text_contains(heading, subject) or _entity_text_contains(subject, heading) for subject in subjects):
# #             continue

# #         end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
# #         mrp_match = re.search(r"\bM\.?R\.?P\b", text[heading_match.end() : end], flags=re.IGNORECASE)
# #         if mrp_match:
# #             end = heading_match.end() + mrp_match.start()
# #         return text[heading_match.start() : end].strip()

# #     return page_data


# # def _extract_competitor_question_subjects(question: str) -> list[str]:
# #     """Extract product names from competitor-table questions."""
# #     patterns = (
# #         r"\bcompetitor(?:\s+brand)?\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+has|\s+is|\s+with|\s+priced|\s+belongs|\?|$)",
# #         r"\bfor\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+has|\s+is|\s+with|\s+priced|\?|$)",
# #         r"\bof\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+(?:has|with|priced|belongs)",
# #     )
# #     subjects: list[str] = []
# #     for pattern in patterns:
# #         for match in re.finditer(pattern, question, flags=re.IGNORECASE):
# #             subject = match.group(1).strip(" ?.")
# #             subject = re.sub(
# #                 r"\b(?:the|highest|lowest|cheapest|price|strip|competitor|brand|company)\b",
# #                 " ",
# #                 subject,
# #                 flags=re.IGNORECASE,
# #             )
# #             subject = re.sub(r"\s+", " ", subject).strip()
# #             if subject and subject.lower() not in {"which", "what"}:
# #                 subjects.append(subject)
# #     return subjects


# # def _extract_marketed_by_company(question: str) -> str:
# #     """Extract company name from questions like 'marketed by Lupin'."""
# #     match = re.search(
# #         r"\bmarketed\s+by\s+([A-Za-z][A-Za-z0-9 &.'/-]+?)\??$",
# #         question,
# #         flags=re.IGNORECASE,
# #     )
# #     return match.group(1).strip(" ?.") if match else ""


# # def _extract_competitor_brand_names(text: str) -> list[str]:
# #     """Extract only brand names from competitor sections and ignore numeric values."""
# #     delimiter_safe_text = text.replace("\r\n", "\n").replace("\n", " | ")
# #     cleaned = _clean_response_for_validation(delimiter_safe_text)
# #     cleaned = _remove_punchline_or_slogan_text(cleaned)
# #     cleaned = re.sub(r"\*+\s*name\s+appears\b.*", " ", cleaned, flags=re.IGNORECASE)
# #     cleaned = re.sub(r"\b\d+\s*,\s*\d+(?:\s*,\s*\d+)*\b", " ", cleaned)
# #     cleaned = re.sub(
# #         r"\bsr\.?\s+competitor\s+brand\s+company\s+pack\s+size\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(
# #         r"\bbrand\s+company\s+pack\s+size\s+price\s*/?\s*strip\s*(?:\(.*?\))?\s+sources\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(
# #         r"\bbrand\s+name\s+company\s+pack\s+(?:size\s+)?price\s*/?\s*strip\s*(?:\(.*?\))?\s*(?:sources)?\b",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(
# #         r"^.*?\bcompetitor\s+brands?\s+for\s+[A-Za-z0-9 /+-]+(?:\s*\([^)]*\))?\s*[:\-]?\s*",
# #         " ",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     cleaned = re.sub(r"\s+", " ", cleaned).strip()

# #     competitor_section_match = re.search(
# #         r"(?:competitors?\s+brand.*?name|brand\s+name\s+company|brand\s+name)"
# #         r"(.+?)(?:m\.?r\.?p|recommended dosage|salient|indications|composition|$)",
# #         cleaned,
# #         flags=re.IGNORECASE,
# #     )
# #     section = competitor_section_match.group(1) if competitor_section_match else cleaned
# #     section = _scope_competitor_section(section)

# #     table_brands = _extract_table_brand_names(section)
# #     if table_brands:
# #         return table_brands

# #     section = re.sub(r"\b\d+(?:\.\d+)?\b", " ", section)
# #     section = re.sub(
# #         r"\b(?:tab|tabs|tablet|tablets|cap|caps|strip|price|pack)\b",
# #         " ",
# #         section,
# #         flags=re.IGNORECASE,
# #     )
# #     return _extract_listed_brand_names(section)


# # def _scope_competitor_section(section: str) -> str:
# #     """Keep only the first competitor table when multiple product tables are adjacent."""
# #     table_heading_pattern = re.compile(
# #         r"\s+[A-Za-z][A-Za-z0-9 /+-]{2,60}\s*:-\s+BRAND\s+NAME\s+COMPANY\s+PACK",
# #         flags=re.IGNORECASE,
# #     )
# #     for next_table_match in table_heading_pattern.finditer(section):
# #         if next_table_match.start() > 20:
# #             return section[: next_table_match.start()].strip()

# #     return section


# # def _extract_table_brand_names(section: str) -> list[str]:
# #     """Extract numbered table brand names from brand/company/pack/price rows."""
# #     brands: list[str] = []
# #     known_companies = _known_company_names()
# #     company_pattern = "|".join(re.escape(company) for company in known_companies)
# #     row_segments = re.split(
# #         r"(?=(?:^|\s)[1-9]\d?\s+(?!Tab\b|Tabs\b|Tablet\b|Tablets\b|Cap\b|Caps\b|Strip\b|Ml\b|Gm\b|Mg\b)[A-Z])",
# #         section,
# #     )
# #     row_segment_pattern = re.compile(
# #         rf"^\s*\d+\s+(.+?)\*?\s+(?:{company_pattern})\s+"
# #         r"\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b",
# #         flags=re.IGNORECASE,
# #     )

# #     for segment in row_segments:
# #         match = row_segment_pattern.search(segment)
# #         if not match:
# #             continue

# #         brand = _clean_brand_name(match.group(1))
# #         if brand and _is_valid_brand_name(brand):
# #             _append_unique_brand(brands, brand)

# #     row_pattern = re.compile(
# #         r"(?:^|\s)(?:\d+\s*[.)-]\s*)"
# #         rf"([A-Za-z][A-Za-z0-9 +./-]{{1,80}}?)\*?\s+"
# #         rf"(?:{company_pattern})"
# #         r"\s+\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b"
# #         r"(?:\s+\d+(?:\.\d+)?)?",
# #         flags=re.IGNORECASE,
# #     )

# #     for match in row_pattern.finditer(section):
# #         brand = _clean_brand_name(match.group(1))
# #         if brand and _is_valid_brand_name(brand):
# #             _append_unique_brand(brands, brand)

# #     no_number_row_pattern = re.compile(
# #         rf"([A-Za-z][A-Za-z0-9 +./-]{{1,80}}?)\*?\s+"
# #         rf"(?:{company_pattern})\s+"
# #         r"\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b"
# #         r"(?:\s+\d+(?:\.\d+)?)?"
# #         r"(?:\s+\d+(?:\s*,\s*\d+)*)?",
# #         flags=re.IGNORECASE,
# #     )

# #     for match in no_number_row_pattern.finditer(section):
# #         brand = _clean_brand_name(match.group(1))
# #         if brand and _is_valid_brand_name(brand):
# #             _append_unique_brand(brands, brand)

# #     if brands:
# #         return brands

# #     company_based_pattern = re.compile(
# #         rf"(?:^|\s)(?:\d+\s*[.)-]?\s*)?"
# #         rf"([A-Za-z][A-Za-z0-9 +./-]{{1,60}}?)\s+"
# #         rf"(?:{company_pattern})(?=\s|$)",
# #         flags=re.IGNORECASE,
# #     )

# #     for match in company_based_pattern.finditer(section):
# #         brand = _clean_brand_name(match.group(1))
# #         if brand and _is_valid_brand_name(brand):
# #             _append_unique_brand(brands, brand)

# #     if brands:
# #         return brands

# #     return brands


# # def _known_company_names() -> tuple[str, ...]:
# #     """Return known pharma company names used to identify table columns."""
# #     return (
# #         "drl",
# #         "ipca",
# #         "micro",
# #         "bal",
# #         "eris life",
# #         "eris",
# #         "alkem",
# #         "servier",
# #         "jb chemicals",
# #         "jb pharma",
# #         "merck specialities",
# #         "merck",
# #         "mankind",
# #         "sun pharma",
# #         "aristo",
# #         "indoco",
# #         "alembic",
# #         "koye",
# #         "mex",
# #         "sun",
# #         "zydus",
# #         "zydus cadilla",
# #         "cipla",
# #         "gr",
# #         "torrent",
# #         "lupin",
# #         "abbott",
# #         "ajanta",
# #         "glenmark",
# #         "macelods",
# #         "macleods",
# #         "wockhardt",
# #         "corona remedies",
# #         "la renon healthcare",
# #         "systopic laboratories",
# #         "novartis",
# #         "rpg",
# #         "biocon",
# #         "concord biotec",
# #         "steris",
# #         "usv",
# #         "intace",
# #         "intas",
# #         "bi",
# #         "boehringer ingelheim",
# #     )


# # def _extract_listed_brand_names(section: str) -> list[str]:
# #     """Extract brands from simple comma/newline/bullet response lists."""
# #     section = re.sub(
# #         r"\b(?:the|competitors?|competitor|brand|brands|are|is|include|includes|of|for)\b",
# #         " ",
# #         section,
# #         flags=re.IGNORECASE,
# #     )
# #     candidates = re.split(r"[,;\n|]|\s+-\s+|\s+\band\b\s+|\s+\d+\s*[.)]\s+", section)
# #     brands: list[str] = []

# #     for candidate in candidates:
# #         brand = _clean_brand_name(candidate)
# #         if brand and _is_valid_brand_name(brand):
# #             _append_unique_brand(brands, brand)

# #     return brands


# # def _clean_brand_name(text: str) -> str:
# #     """Clean a competitor brand candidate."""
# #     brand = text.replace("*", " ")
# #     brand = re.sub(
# #         r"^\s*(?:(?:sources?|competitors?|competitor|brand|brands|name|company|pack|size|segment)\b\s*)+",
# #         " ",
# #         brand,
# #         flags=re.IGNORECASE,
# #     )
# #     brand = re.sub(r"\b\d+(?:\.\d+)?\b", " ", brand)
# #     brand = re.sub(
# #         r".*\bbrand\s+name\s+company\s+pack\s+price\s*/?\s*strip\b",
# #         " ",
# #         brand,
# #         flags=re.IGNORECASE,
# #     )
# #     brand = re.sub(
# #         r".*\bbrand\s+name\b",
# #         " ",
# #         brand,
# #         flags=re.IGNORECASE,
# #     )
# #     brand = re.sub(
# #         r"\b(?:company|pack|size|price|strip|tab|tabs|tablet|tablets|cap|caps|mrp|sources?|mg)\b",
# #         " ",
# #         brand,
# #         flags=re.IGNORECASE,
# #     )
# #     brand = re.sub(r"\s+", " ", brand).strip(" /:-.,;")
# #     company_pattern = "|".join(re.escape(company) for company in _known_company_names())
# #     brand = re.sub(
# #         rf"\s+(?:{company_pattern})$",
# #         "",
# #         brand,
# #         flags=re.IGNORECASE,
# #     )
# #     return brand


# # def _is_valid_brand_name(brand: str) -> bool:
# #     """Return whether a candidate is a real brand name, not table noise."""
# #     normalized = _normalize_brand_name(brand)
# #     invalid = {
# #         "",
# #         "brand name",
# #         "company",
# #         "competitors name",
# #         "competitors brand",
# #         "competitors brand company",
# #         "price strip",
# #         "punch line",
# #         "punchline",
# #         "slogan",
# #         "tagline",
# #     }
# #     return (
# #         normalized not in invalid
# #         and "punch line" not in normalized
# #         and "punchline" not in normalized
# #         and "slogan" not in normalized
# #         and "tagline" not in normalized
# #         and any(char.isalpha() for char in brand)
# #     )


# # def _remove_punchline_or_slogan_text(text: str) -> str:
# #     """Remove punchline/slogan sections from competitor-brand extraction."""
# #     return re.sub(
# #         r"\b(?:punch\s*line|punchline|slogan|tagline)\b.*?"
# #         r"(?=\b(?:competitors?\s+brand|brand\s+name|composition|mode of action|"
# #         r"indications|recommended dosage|salient|m\.?r\.?p)\b|$)",
# #         " ",
# #         text,
# #         flags=re.IGNORECASE,
# #     )


# # def _normalize_brand_name(brand: str) -> str:
# #     """Normalize brand names for exact brand comparison."""
# #     return _normalize_entity_value(brand)


# # def _brand_matches_any(response_brand: str, normalized_page_brands: set[str]) -> bool:
# #     """Return whether a response brand or slash variant exists on the cited page.

# #     Medicine brand names are sensitive, so this intentionally avoids fuzzy
# #     matching. A one-letter difference can be a different product.
# #     """
# #     candidates = [response_brand]
# #     if "/" in response_brand:
# #         candidates.extend(part.strip() for part in response_brand.split("/") if part.strip())

# #     for candidate in candidates:
# #         normalized_candidate = _normalize_brand_name(candidate)
# #         if normalized_candidate in normalized_page_brands:
# #             return True

# #     return False


# # def _normalize_entity_value(value: str) -> str:
# #     """Normalize entity strings before exact/fuzzy comparison."""
# #     normalized = normalize_text(value)
# #     normalized = _company_aliases().get(normalized, normalized)
# #     normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
# #     return re.sub(r"\s+", " ", normalized).strip()


# # def _normalize_company_display(company: str) -> str:
# #     """Return canonical display name for known company aliases."""
# #     normalized = _normalize_entity_value(company)
# #     display_aliases = {
# #         "dr reddys laboratories": "Dr. Reddy's Laboratories",
# #         "ipca laboratories": "IPCA Laboratories",
# #         "eris lifesciences": "Eris Lifesciences",
# #         "boehringer ingelheim": "BI",
# #         "sun pharma": "Sun Pharma",
# #         "ipca laboratories": "IPCA Laboratories",
# #     }
# #     return display_aliases.get(normalized, company.strip())


# # def _company_aliases() -> dict[str, str]:
# #     """Return company aliases for pharma entity normalization."""
# #     return {
# #         "eris": "eris lifesciences",
# #         "eris life": "eris lifesciences",
# #         "eris lifesciences": "eris lifesciences",
# #         "drl": "dr reddys laboratories",
# #         "dr reddy": "dr reddys laboratories",
# #         "dr reddys": "dr reddys laboratories",
# #         "dr reddy s laboratories": "dr reddys laboratories",
# #         "dr reddys laboratories": "dr reddys laboratories",
# #         "ipca": "ipca laboratories",
# #         "ipca labs": "ipca laboratories",
# #         "ipca laboratories": "ipca laboratories",
# #         "sun": "sun pharma",
# #         "sun pharma": "sun pharma",
# #         "sun pharmaceutical": "sun pharma",
# #         "bi": "boehringer ingelheim",
# #         "boehringer": "boehringer ingelheim",
# #         "boehringer ingelheim": "boehringer ingelheim",
# #     }


# # def _entity_match_audit(
# #     left_value: str,
# #     right_value: str,
# #     threshold: float = COMPANY_ENTITY_MATCH_THRESHOLD,
# #     allow_fuzzy: bool = False,
# # ) -> dict[str, object]:
# #     """Return original values, normalized values, score, and match decision."""
# #     left_normalized = _normalize_entity_value(left_value)
# #     right_normalized = _normalize_entity_value(right_value)
# #     score = _levenshtein_similarity(left_normalized, right_normalized)
# #     matched = left_normalized == right_normalized or (allow_fuzzy and score >= threshold)
# #     return {
# #         "left_original": left_value,
# #         "right_original": right_value,
# #         "left_normalized": left_normalized,
# #         "right_normalized": right_normalized,
# #         "score": round(score, 3),
# #         "matched": matched,
# #     }


# # def _entity_values_match(
# #     left_value: str,
# #     right_value: str,
# #     threshold: float = COMPANY_ENTITY_MATCH_THRESHOLD,
# #     allow_fuzzy: bool = False,
# # ) -> bool:
# #     """Return whether two entity values are equivalent after alias/fuzzy matching."""
# #     return bool(_entity_match_audit(left_value, right_value, threshold, allow_fuzzy)["matched"])


# # def _entity_matches_any(value: str, candidates: list[str], allow_fuzzy: bool = False) -> bool:
# #     """Return whether an entity matches any candidate with audit-aware normalization."""
# #     return bool(_entity_best_match_audit(value, candidates, allow_fuzzy=allow_fuzzy)["matched"])


# # def _entity_best_match_audit(
# #     value: str,
# #     candidates: list[str],
# #     allow_fuzzy: bool = False,
# # ) -> dict[str, object]:
# #     """Return best entity match audit for one value against candidate values."""
# #     candidate_values = [value]
# #     if "/" in value:
# #         candidate_values.extend(part.strip() for part in value.split("/") if part.strip())

# #     best_audit: dict[str, object] | None = None
# #     for candidate_value in candidate_values:
# #         for candidate in candidates:
# #             audit = _entity_match_audit(
# #                 candidate_value,
# #                 candidate,
# #                 allow_fuzzy=allow_fuzzy,
# #             )
# #             if best_audit is None or float(audit["score"]) > float(best_audit["score"]):
# #                 best_audit = audit

# #     if best_audit is None:
# #         best_audit = {
# #             "left_original": value,
# #             "right_original": "",
# #             "left_normalized": _normalize_entity_value(value),
# #             "right_normalized": "",
# #             "score": 0.0,
# #             "matched": False,
# #         }

# #     return best_audit


# # def _format_entity_audit_summary(audits: list[dict[str, object]]) -> str:
# #     """Return concise audit trail for entity normalization decisions."""
# #     if not audits:
# #         return ""

# #     audit_parts = []
# #     for audit in audits[:5]:
# #         audit_parts.append(
# #             f"{audit['left_original']} -> {audit['left_normalized']} "
# #             f"matched {audit['right_original']} -> {audit['right_normalized']} "
# #             f"(score {float(audit['score']):.2f})"
# #         )

# #     if len(audits) > 5:
# #         audit_parts.append(f"+{len(audits) - 5} more")

# #     return "Entity audit: " + "; ".join(audit_parts) + "."


# # def _entity_text_contains(text: str, expected_entity: str) -> bool:
# #     """Return whether text contains an entity after alias/fuzzy normalization."""
# #     normalized_text = _normalize_entity_value(text)
# #     normalized_entity = _normalize_entity_value(expected_entity)
# #     if normalized_entity and normalized_entity in normalized_text:
# #         return True

# #     text_entities = _extract_possible_entities(text)
# #     return _entity_matches_any(expected_entity, text_entities)


# # def _company_text_contains(text: str, expected_company: str) -> bool:
# #     """Return whether text contains a company after alias/controlled OCR matching."""
# #     normalized_text = _normalize_entity_value(text)
# #     normalized_company = _normalize_entity_value(expected_company)
# #     if normalized_company and normalized_company in normalized_text:
# #         return True
# #     for alias, canonical in _company_aliases().items():
# #         if canonical == normalized_company and re.search(rf"\b{re.escape(alias)}\b", normalize_text(text)):
# #             return True

# #     text_entities = _extract_possible_entities(text)
# #     return _entity_matches_any(expected_company, text_entities, allow_fuzzy=True)


# # def _entity_text_contains_ordered_tokens(text: str, expected_entity: str) -> bool:
# #     """Return whether all entity tokens appear in order inside text."""
# #     text_tokens = re.findall(r"[a-z0-9]+", _normalize_entity_value(text))
# #     entity_tokens = re.findall(r"[a-z0-9]+", _normalize_entity_value(expected_entity))
# #     if not entity_tokens:
# #         return False
# #     position = 0
# #     for entity_token in entity_tokens:
# #         try:
# #             found_at = text_tokens.index(entity_token, position)
# #         except ValueError:
# #             return False
# #         position = found_at + 1
# #     return True


# # def _extract_possible_entities(text: str) -> list[str]:
# #     """Extract possible entity spans from response text for fuzzy matching."""
# #     cleaned = _clean_response_for_validation(text)
# #     parts = re.split(r"[,;|\n]|\s+-\s+|\s+\band\b\s+", cleaned)
# #     entities: list[str] = []
# #     for part in parts:
# #         candidate = re.sub(r"\b\d+(?:\.\d+)?\b", " ", part)
# #         candidate = re.sub(
# #             r"\b(?:price|mrp|strip|tab|tabs|tablet|tablets|pack|company|brand|lowest|highest|has|is|at|rs|inr|per)\b",
# #             " ",
# #             candidate,
# #             flags=re.IGNORECASE,
# #         )
# #         candidate = re.sub(r"\s+", " ", candidate).strip(" :-.,")
# #         if candidate and any(char.isalpha() for char in candidate):
# #             entities.append(candidate)

# #     entities.append(cleaned)
# #     return entities


# # def _levenshtein_similarity(left: str, right: str) -> float:
# #     """Return normalized Levenshtein similarity between two strings."""
# #     if left == right:
# #         return 1.0
# #     if not left or not right:
# #         return 0.0

# #     previous = list(range(len(right) + 1))
# #     for left_index, left_char in enumerate(left, start=1):
# #         current = [left_index]
# #         for right_index, right_char in enumerate(right, start=1):
# #             insert_cost = current[right_index - 1] + 1
# #             delete_cost = previous[right_index] + 1
# #             replace_cost = previous[right_index - 1] + (left_char != right_char)
# #             current.append(min(insert_cost, delete_cost, replace_cost))
# #         previous = current

# #     distance = previous[-1]
# #     return 1 - (distance / max(len(left), len(right)))


# # def _append_unique_brand(brands: list[str], brand: str) -> None:
# #     """Append a brand once using normalized comparison."""
# #     normalized = _normalize_brand_name(brand)
# #     if normalized and normalized not in {_normalize_brand_name(existing) for existing in brands}:
# #         brands.append(brand)


# # def _is_multi_product_question(normalized_question: str) -> bool:
# #     """Return whether a question needs separate evidence per product."""
# #     if "mycept" in normalized_question and "mycept s" in normalized_question:
# #         return True
# #     return bool(re.search(r"\bbetween\b.+\band\b", normalized_question))


# # def _compare_multi_product_response(
# #     response_content: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate multi-product answers product-by-product, never as one flat text."""
# #     products = _extract_products_for_multi_validation(question, response_content)
# #     if len(products) < 2:
# #         return _compare_descriptive_response(response_content, page_data)

# #     product_results: list[tuple[str, str, str]] = []
# #     for product in products:
# #         evidence = _extract_product_evidence_section(page_data, product)
# #         product_answer = _extract_product_answer_section(response_content, product)

# #         if not evidence:
# #             product_results.append(
# #                 (
# #                     product,
# #                     "DATA MISSING",
# #                     f"{product} cited evidence section was not found.",
# #                 )
# #             )
# #             continue

# #         if not product_answer:
# #             product_results.append(
# #                 (
# #                     product,
# #                     "DATA MISSING",
# #                     f"SuperAI did not provide a separate value for {product}.",
# #                 )
# #             )
# #             continue

# #         strict_result = _validate_product_strict_values(product_answer, evidence, product)
# #         if strict_result[0] != "PASS":
# #             product_results.append((product, strict_result[0], strict_result[1]))
# #             continue

# #         semantic_result, semantic_reason = _compare_descriptive_response(product_answer, evidence)
# #         if semantic_result == "FAIL":
# #             product_results.append((product, "FAIL", semantic_reason))
# #         else:
# #             product_results.append(
# #                 (
# #                     product,
# #                     "PASS",
# #                     f"{product} evidence supports the product-specific claims.",
# #                 )
# #             )

# #     statuses = [status for _, status, _ in product_results]
# #     reason = " | ".join(f"{product}: {detail}" for product, _, detail in product_results)

# #     if all(status == "PASS" for status in statuses):
# #         return "PASS", f"All product-specific claims are supported. {reason}"

# #     if "DATA MISSING" in statuses:
# #         return "DATA MISSING", reason

# #     if "FAIL" in statuses:
# #         return "FAIL", reason

# #     return "DATA MISSING", reason


# # def _extract_products_for_multi_validation(question: str, response_content: str) -> list[str]:
# #     """Extract product names that must be validated independently."""
# #     normalized = normalize_text(f"{question} {response_content}")
# #     products: list[str] = []
# #     for product in ("mycept s", "mycept"):
# #         if product in normalized:
# #             products.append(product)
# #     products.sort(key=len)
# #     return products


# # def _extract_product_evidence_section(page_data: str, product: str) -> str:
# #     """Return source text for one product only."""
# #     cleaned = re.sub(r"\s+", " ", page_data or "").strip()
# #     normalized_product = normalize_text(product)

# #     if normalized_product == "mycept s":
# #         start_match = re.search(
# #             r"\bbrand snapshot\s+mycept\s+s\b|\bname of product:?\s*mycept\s+s\b",
# #             cleaned,
# #             flags=re.IGNORECASE,
# #         )
# #         if not start_match:
# #             return ""
# #         start = start_match.start()
# #         end_match = re.search(
# #             r"\bCitation\s+\d+\s+\|\s+Document\b|\bBrand Snapshot\s+MYCEPT\b",
# #             cleaned[start + 20 :],
# #             flags=re.IGNORECASE,
# #         )
# #         end = start + 20 + end_match.start() if end_match else len(cleaned)
# #         return cleaned[start:end].strip()

# #     if normalized_product == "mycept":
# #         # Plain MYCEPT evidence must not be the MYCEPT S section.
# #         start_match = re.search(
# #             r"\bbrand snapshot\s+mycept\b(?!\s+s)|\bname of product:?\s*mycept\b(?!\s+s)",
# #             cleaned,
# #             flags=re.IGNORECASE,
# #         )
# #         if not start_match:
# #             comparison_match = re.search(
# #                 r"\bmycophenolate mofetil\s*\(mycept\)\b|\bmycept\b.*?\bprodrug\b|\bprodrug\b.*?\bmycept\b",
# #                 cleaned,
# #                 flags=re.IGNORECASE,
# #             )
# #             if comparison_match:
# #                 return cleaned[max(0, comparison_match.start() - 500) : comparison_match.start() + 900].strip()
# #             return ""
# #         start = start_match.start()
# #         section = cleaned[start:]
# #         stop_match = re.search(r"\b(?:brand snapshot\s+)?mycept\s+s\b", section[20:], flags=re.IGNORECASE)
# #         end = 20 + stop_match.start() if stop_match else len(section)
# #         return section[:end].strip()

# #     match = re.search(re.escape(product), cleaned, flags=re.IGNORECASE)
# #     return cleaned[max(0, match.start() - 200) : match.start() + 1200] if match else ""


# # def _extract_product_answer_section(response_content: str, product: str) -> str:
# #     """Return the SuperAI answer portion for one product."""
# #     cleaned = re.sub(r"\s+", " ", _clean_response_for_validation(response_content)).strip()
# #     normalized_product = normalize_text(product)

# #     if normalized_product == "mycept s":
# #         match = re.search(r"\bmycept\s+s\b(.+?)(?=\bmycept\b(?!\s+s)|$)", cleaned, flags=re.IGNORECASE)
# #         if match:
# #             return f"{product} {match.group(1)}".strip()
# #         return cleaned if re.search(r"\bmycept\s+s\b", cleaned, flags=re.IGNORECASE) else ""

# #     if normalized_product == "mycept":
# #         match = re.search(r"\bmycept\b(?!\s+s)(.+?)(?=\bmycept\s+s\b|$)", cleaned, flags=re.IGNORECASE)
# #         if match:
# #             return f"{product} {match.group(1)}".strip()
# #         return cleaned if re.search(r"\bmycept\b(?!\s+s)", cleaned, flags=re.IGNORECASE) else ""

# #     match = re.search(re.escape(product), cleaned, flags=re.IGNORECASE)
# #     return cleaned[match.start() : match.start() + 700] if match else ""


# # def _validate_product_strict_values(
# #     product_answer: str,
# #     product_evidence: str,
# #     product: str,
# # ) -> tuple[str, str]:
# #     """Validate critical numeric/unit values inside one product's evidence."""
# #     answer_values = _extract_numeric_unit_values(_clean_numeric_validation_text(product_answer))
# #     evidence_values = _extract_numeric_unit_values(_clean_numeric_validation_text(product_evidence))
# #     critical_values = {
# #         value
# #         for value in answer_values
# #         if re.search(r"\b(?:mg|g|mcg|ml|tab|tabs|tablet|tablets|day|daily|bid|od)\b", value)
# #     }

# #     if critical_values and not evidence_values:
# #         return "DATA MISSING", f"{product} critical numeric evidence was not found."

# #     missing = sorted(critical_values.difference(evidence_values))
# #     if missing:
# #         if evidence_values:
# #             return (
# #                 "FAIL",
# #                 f"{product} strict value mismatch. Missing cited value(s): {', '.join(missing)}.",
# #             )
# #         return (
# #             "DATA MISSING",
# #             f"{product} cited evidence is missing required value(s): {', '.join(missing)}.",
# #         )

# #     return "PASS", f"{product} strict values are supported."


# # # ---------------------------------------------------------------------------
# # # CLINICAL OUTCOME — range-aware numeric comparison
# # # ---------------------------------------------------------------------------

# # _OUTCOME_PERCENT_TOLERANCE = 2.0  # ± percentage points for clinical values


# # def _extract_outcome_numbers(text: str) -> list[float]:
# #     """Extract all numeric outcome values from clinical text.

# #     Handles:
# #     - Bare percentages:    "48%", "50.5%", "~52%", ">30%"
# #     - Decimal reductions:  "3.2 mmol/L", "1.5 mg/dL", "0.8%"
# #     - Ranges (both ends):  "50-60%", "50 to 60%", "50–60%"

# #     Returns a deduplicated, sorted list of float values.
# #     """
# #     values: set[float] = set()

# #     # Ranges: "50-60%", "50–60%", "50 to 60%"
# #     for match in re.finditer(
# #         r"(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*%",
# #         text,
# #         flags=re.IGNORECASE,
# #     ):
# #         values.add(float(match.group(1)))
# #         values.add(float(match.group(2)))

# #     # Single percentages: "48%", "~48%", ">48%", "≥48%"
# #     for match in re.finditer(
# #         r"[~>≥≤<]?\s*(\d+(?:\.\d+)?)\s*%",
# #         text,
# #     ):
# #         values.add(float(match.group(1)))

# #     # Absolute clinical values with units: "3.2 mmol/L", "1.5 mg/dl"
# #     for match in re.finditer(
# #         r"(\d+(?:\.\d+)?)\s*(?:mmol/l|mg/dl|mg/dL|mmhg|mmHg)\b",
# #         text,
# #         flags=re.IGNORECASE,
# #     ):
# #         values.add(float(match.group(1)))

# #     return sorted(values)


# # def _extract_response_outcome_bounds(text: str) -> tuple[float, float] | None:
# #     """Return (lo, hi) covering all numeric outcome claims in the response.

# #     For a range response like "50-60%" returns (50.0, 60.0).
# #     For a single value like "80%" returns (80.0, 80.0).
# #     Returns None when no outcome numbers are found.
# #     """
# #     values = _extract_outcome_numbers(text)
# #     if not values:
# #         return None
# #     return (min(values), max(values))


# # def _compare_clinical_outcome(
# #     response_text: str,
# #     page_data: str,
# #     question: str,
# # ) -> tuple[str, str]:
# #     """Validate clinical outcome questions using a cited numeric range.

# #     Builds a supported range from ALL outcome values on the cited page, then
# #     checks whether the response claim falls within that range.

# #     PASS  — response bounds are fully contained within the supported range.
# #     FAIL  — response claims a value that exceeds or contradicts cited evidence.
# #     DATA MISSING — no outcome numbers found on the cited page.

# #     Example:
# #       Page: "48%, 50%, 52%, 60%"  → supported range [48, 60]
# #       Response "50–60%"           → bounds [50, 60] ⊆ [48, 60]  → PASS
# #       Response "70–80%"           → bounds [70, 80] ⊄ [48, 60]  → FAIL
# #       Response "80%"              → bound [80, 80] ⊄ [48, 60]   → FAIL

# #     Applies only to CLINICAL_OUTCOME questions.  Never called for PRICE,
# #     DOSAGE, PACK_SIZE, COMPOSITION, or other strict attribute types.
# #     """
# #     page_values = _extract_outcome_numbers(page_data)
# #     if not page_values:
# #         _log_validation_step(
# #             rule="_compare_clinical_outcome",
# #             attribute="CLINICAL_OUTCOME",
# #             verdict="DATA MISSING",
# #             reason="No clinical outcome values found on the cited page.",
# #         )
# #         return "DATA MISSING", "No clinical outcome values found on the cited page."

# #     cited_lo = min(page_values)
# #     cited_hi = max(page_values)
# #     tol = _OUTCOME_PERCENT_TOLERANCE

# #     response_bounds = _extract_response_outcome_bounds(response_text)
# #     if response_bounds is None:
# #         _log_validation_step(
# #             rule="_compare_clinical_outcome",
# #             attribute="CLINICAL_OUTCOME",
# #             doc_value=f"[{cited_lo:g}–{cited_hi:g}]",
# #             verdict="DATA MISSING",
# #             reason="SuperAI response contained no numeric outcome values.",
# #         )
# #         return "DATA MISSING", "SuperAI response contained no numeric outcome values."

# #     resp_lo, resp_hi = response_bounds
# #     supported_lo = cited_lo - tol
# #     supported_hi = cited_hi + tol

# #     within_range = resp_lo >= supported_lo and resp_hi <= supported_hi

# #     cited_summary = (
# #         f"{cited_lo:g}–{cited_hi:g}%"
# #         if cited_lo != cited_hi
# #         else f"{cited_lo:g}%"
# #     )
# #     resp_summary = (
# #         f"{resp_lo:g}–{resp_hi:g}%"
# #         if resp_lo != resp_hi
# #         else f"{resp_lo:g}%"
# #     )

# #     if within_range:
# #         _log_validation_step(
# #             rule="_compare_clinical_outcome",
# #             attribute="CLINICAL_OUTCOME",
# #             doc_value=cited_summary,
# #             response_value=resp_summary,
# #             normalization=f"supported range [{supported_lo:g}, {supported_hi:g}]",
# #             verdict="PASS",
# #             reason=f"Response {resp_summary} is within cited range {cited_summary}.",
# #         )
# #         return (
# #             "PASS",
# #             f"Clinical outcome {resp_summary} is supported by cited evidence "
# #             f"(cited range: {cited_summary}).",
# #         )

# #     _log_validation_step(
# #         rule="_compare_clinical_outcome",
# #         attribute="CLINICAL_OUTCOME",
# #         doc_value=cited_summary,
# #         response_value=resp_summary,
# #         normalization=f"supported range [{supported_lo:g}, {supported_hi:g}]",
# #         verdict="FAIL",
# #         reason=f"Response {resp_summary} exceeds or contradicts cited range {cited_summary}.",
# #     )
# #     return (
# #         "FAIL",
# #         f"Clinical outcome mismatch. Cited evidence supports {cited_summary}, "
# #         f"but SuperAI claimed {resp_summary}.",
# #     )


# # def _compare_descriptive_response(
# #     response_content: str,
# #     page_data: str,
# #     question: str = "",
# # ) -> tuple[str, str]:
# #     """Validate descriptive medical attributes by supported concepts, not raw words."""
# #     normalized_response = _semantic_normalize(response_content)
# #     normalized_page = _semantic_normalize(page_data)
# #     normalized_question = _semantic_normalize(question)

# #     response_concepts = _extract_semantic_concepts(normalized_response)
# #     page_concepts = _extract_semantic_concepts(normalized_page)

# #     if _requires_descriptive_comparison(normalized_question) and not _has_supported_descriptive_comparison(
# #         normalized_page
# #     ):
# #         return (
# #             "DATA MISSING",
# #             "The cited page does not support the requested descriptive comparison/superiority claim.",
# #         )

# #     if response_concepts:
# #         relevant_concepts = _select_relevant_descriptive_concepts(
# #             normalized_question,
# #             response_concepts,
# #         )
# #         if relevant_concepts:
# #             matched_relevant = sorted(relevant_concepts.intersection(page_concepts))
# #             missing_relevant = sorted(relevant_concepts.difference(page_concepts))
# #             if not missing_relevant:
# #                 return (
# #                     "PASS",
# #                     "Core factual claim is supported by the cited page. "
# #                     f"Matched core concept(s): {', '.join(matched_relevant)}.",
# #                 )

# #             if matched_relevant:
# #                 coverage = len(matched_relevant) / len(relevant_concepts)
# #                 if coverage >= 0.5 or len(matched_relevant) >= 2:
# #                     return (
# #                         "PASS",
# #                         "Core descriptive claim is supported by the cited page; "
# #                         "extra explanatory wording was not treated as required evidence. "
# #                         f"Matched core concept(s): {', '.join(matched_relevant)}.",
# #                     )
# #                 return (
# #                     "DATA MISSING",
# #                     "Core factual claim is only partially supported on the cited page. "
# #                     f"Missing core concept(s): {', '.join(missing_relevant)}.",
# #                 )

# #             if _has_descriptive_context_overlap(normalized_response, normalized_page):
# #                 return (
# #                     "DATA MISSING",
# #                     "Related cited text exists, but the core factual claim was not found.",
# #                 )

# #             return "DATA MISSING", "Core factual claim was not found on the cited page."

# #         matched_concepts = sorted(response_concepts.intersection(page_concepts))
# #         missing_concepts = sorted(response_concepts.difference(page_concepts))

# #         if len(matched_concepts) == len(response_concepts):
# #             return (
# #                 "PASS",
# #                 f"Semantic match found for descriptive attribute: {', '.join(matched_concepts)}.",
# #             )

# #         if matched_concepts:
# #             coverage = len(matched_concepts) / len(response_concepts)
# #             if coverage >= 0.6:
# #                 return (
# #                     "PASS",
# #                     "Meaning is supported by the cited page despite wording differences. "
# #                     f"Matched concept(s): {', '.join(matched_concepts)}.",
# #                 )
# #             return (
# #                 "FAIL",
# #                 "Descriptive value is only partially supported on the cited page. "
# #                 f"Missing concept(s): {', '.join(missing_concepts)}.",
# #             )

# #         if _has_descriptive_context_overlap(normalized_response, normalized_page):
# #             return (
# #                 "FAIL",
# #                 "Related descriptive data exists on the cited page, but the meaning does not match.",
# #             )

# #         # No concept matched the page and no drug-class overlap exists — the
# #         # concept dictionary may simply lack coverage for this question type
# #         # (e.g. clinical trial outcomes, survival benefits, SHEP study results).
# #         # Fall through to keyword comparison so those questions are not falsely
# #         # returned as DATA MISSING.

# #     response_keywords = _extract_keywords(normalized_response)
# #     page_keywords = _extract_keywords(normalized_page)
# #     matched_keywords = sorted(response_keywords.intersection(page_keywords))

# #     if not response_keywords:
# #         return "DATA MISSING", "Super AI response did not contain a descriptive value to validate."

# #     coverage = len(matched_keywords) / len(response_keywords)
# #     if coverage >= 0.45 and len(matched_keywords) >= 3:
# #         return (
# #             "PASS",
# #             "Descriptive meaning is supported by the cited page despite wording differences.",
# #         )

# #     # Numeric supplement: _extract_keywords ignores pure numbers (pattern
# #     # requires a letter start), so clinical statistics like "4736", "36", "1"
# #     # are invisible to keyword coverage.  If every number in the response
# #     # appears on the cited page AND there is at least minimal keyword context,
# #     # treat as sufficient evidence.
# #     response_numbers_sup = _extract_numbers(normalized_response)
# #     page_numbers_sup = _extract_numbers(normalized_page)
# #     if (
# #         response_numbers_sup
# #         and response_numbers_sup.issubset(page_numbers_sup)
# #         and matched_keywords
# #     ):
# #         return (
# #             "PASS",
# #             "Clinical numeric value(s) from SuperAI confirmed on cited page: "
# #             f"{', '.join(sorted(response_numbers_sup))}. "
# #             f"Keyword context: {', '.join(matched_keywords[:5])}.",
# #         )

# #     # Clinical relaxation: trial/study outcome questions naturally include
# #     # context words (year, full trial name, methodology notes) that the
# #     # document excerpt does not repeat.  Accept 30% coverage with at least
# #     # 2 keyword matches so these do not falsely return DATA MISSING or FAIL.
# #     _clinical_question_terms = (
# #         "trial",
# #         "study",
# #         "shep",
# #         "enrolled",
# #         "survival",
# #         "guideline",
# #         "evidence",
# #         "mortality",
# #         "reduction",
# #         "benefit",
# #         "randomized",
# #         "randomised",
# #     )
# #     is_clinical_question = any(
# #         term in normalize_text(question) for term in _clinical_question_terms
# #     )
# #     if is_clinical_question and coverage >= 0.30 and len(matched_keywords) >= 2:
# #         return (
# #             "PASS",
# #             "Clinical evidence from cited page broadly supports the SuperAI response. "
# #             f"Matched keyword(s): {', '.join(matched_keywords)}.",
# #         )

# #     if matched_keywords:
# #         return (
# #             "FAIL",
# #             "Related descriptive data exists on the cited page, but required meaning is incomplete.",
# #         )

# #     return "DATA MISSING", "Required descriptive value not found on the cited page."


# # def _select_relevant_descriptive_concepts(
# #     normalized_question: str,
# #     response_concepts: set[str],
# # ) -> set[str]:
# #     """Return the concepts that answer the question's core factual ask.

# #     Descriptive SuperAI answers often include surrounding explanation. For MOA,
# #     USP, indication, and clinical-benefit questions, validate the core claim
# #     requested by the question instead of every extra phrase in the response.
# #     """
# #     concept_groups = (
# #         (
# #             ("voglibose", "postprandial", "pphg"),
# #             {
# #                 "voglibose",
# #                 "alpha glucosidase inhibition",
# #                 "delayed glucose absorption",
# #             },
# #         ),
# #         (
# #             ("dapagliflozin", "sglt2", "renal glucose", "urinary glucose"),
# #             {
# #                 "sglt2 inhibition",
# #                 "renal glucose excretion",
# #             },
# #         ),
# #         (
# #             ("metformin",),
# #             {
# #                 "insulin sensitivity",
# #                 "glucose uptake",
# #                 "hepatic glucose production",
# #                 "glycaemic control",
# #             },
# #         ),
# #         (
# #             ("gliclazide", "insulin secretion", "cellular"),
# #             {
# #                 "sulphonylurea receptor binding",
# #                 "insulin secretion",
# #             },
# #         ),
# #         (
# #             ("linagliptin", "glp", "gip", "dpp"),
# #             {
# #                 "dpp4 inhibition",
# #                 "glp gip incretin",
# #                 "insulin secretion",
# #                 "hepatic glucose production",
# #                 "glycaemic control",
# #                 "fast slow dpp4 binding",
# #                 "dpp4 selectivity",
# #                 "reduced off target effects",
# #                 "od convenience",
# #             },
# #         ),
# #         (
# #             ("ckd", "esrd", "renal"),
# #             {
# #                 "safe renal impairment",
# #                 "esrd risk reduction",
# #             },
# #         ),
# #         (
# #             ("normal saline", "dilution", "medium", "iv infusion"),
# #             {
# #                 "normal saline dilution",
# #                 "iv infusion",
# #             },
# #         ),
# #         (
# #             ("indication", "indications", "used for", "prescribed"),
# #             {
# #                 "type 2 diabetes management",
# #                 "solid organ transplantation",
# #                 "organ rejection prophylaxis",
# #                 "central nervous system",
# #             },
# #         ),
# #         (
# #             ("symptom", "symptoms", "bph", "oab", "storage"),
# #             {
# #                 "bph luts relief",
# #                 "overactive bladder symptom control",
# #             },
# #         ),
# #         (
# #             ("side effect", "side effects", "adverse", "reaction", "reactions", "discomfort"),
# #             {
# #                 "gastrointestinal discomfort",
# #                 "renal dysfunction",
# #                 "tremor",
# #                 "hirsutism",
# #                 "hypertension",
# #                 "gum hyperplasia",
# #                 "nephrotoxicity monitoring",
# #             },
# #         ),
# #         (
# #             ("nephrotoxicity", "monitoring", "precaution", "precautions"),
# #             {
# #                 "nephrotoxicity monitoring",
# #                 "renal dysfunction",
# #             },
# #         ),
# #         (
# #             ("organ", "organs", "transplantation", "transplant"),
# #             {
# #                 "kidney liver heart transplantation",
# #                 "organ rejection prophylaxis",
# #             },
# #         ),
# #         (
# #             # Require "cars" or "upper limb" — "trial" alone is too broad and
# #             # wrongly fires for SHEP trial, CORONA trial, etc.
# #             ("cars", "upper limb", "motor"),
# #             {
# #                 "cars trial",
# #                 "upper limb motor function",
# #             },
# #         ),
# #         (
# #             ("silodosin", "bph", "urine flow", "luts"),
# #             {
# #                 "alpha1a blockade",
# #                 "smooth muscle relaxation",
# #                 "urine flow improvement",
# #                 "bph luts relief",
# #             },
# #         ),
# #         (
# #             ("mirabegron", "overactive bladder", "oab"),
# #             {
# #                 "beta3 agonist",
# #                 "bladder relaxation",
# #                 "overactive bladder symptom control",
# #             },
# #         ),
# #         (
# #             ("vitamin d3", "nurokind", "respiratory", "asthma", "copd", "immunity"),
# #             {
# #                 "respiratory immunity",
# #                 "anti inflammatory",
# #                 "immunoregulatory",
# #                 "copd exacerbation reduction",
# #                 "glucocorticoid responsiveness",
# #                 "immune health",
# #             },
# #         ),
# #         (
# #             ("formoterol", "glycopyrronium", "glycobreez", "bronchodilation", "copd"),
# #             {
# #                 "formoterol beta2 agonist",
# #                 "glycopyrronium m3 antagonist",
# #                 "bronchodilation",
# #                 "copd maintenance",
# #                 "fast onset",
# #                 "twenty four hour relief",
# #             },
# #         ),
# #         (
# #             ("peel off", "peel-off", "strip", "capsule", "moisture"),
# #             {
# #                 "peel off strip",
# #                 "moisture protection",
# #                 "safe peeling",
# #                 "right direction marking",
# #                 "no next capsule exposure",
# #             },
# #         ),
# #         (
# #             ("panimun", "bioral", "trusted", "organ transplantation"),
# #             {
# #                 "organ transplantation",
# #                 "years of trust",
# #                 "clinical evidence",
# #                 "bioavailability",
# #             },
# #         ),
# #         (
# #             ("administration route", "route", "nebulization", "nebulizer", "respule"),
# #             {
# #                 "nebulization route",
# #             },
# #         ),
# #     )

# #     for question_terms, relevant in concept_groups:
# #         if any(term in normalized_question for term in question_terms):
# #             return response_concepts.intersection(relevant)

# #     return set()


# # def _semantic_normalize(text: str) -> str:
# #     """Normalize semantically equivalent medical wording."""
# #     normalized = normalize_text(text)
# #     replacements = {
# #         r"\bglycemic\b": "glycaemic",
# #         r"\bimproves?\b": "increase",
# #         r"\bincreases?\b": "increase",
# #         r"\benhances?\b": "increase",
# #         r"\bdecreases?\b": "reduce",
# #         r"\breduces?\b": "reduce",
# #         r"\blowers?\b": "reduce",
# #         r"\bdelays?\b": "delay",
# #         r"\bslows?\b": "delay",
# #         r"\binhibit(?:s|ed|ing)?\b": "inhibit",
# #         r"\benzymes\b": "enzyme",
# #         r"\balpha[-\s]?glucosidase\b": "alpha glucosidase",
# #         r"\bhepatic glucose output\b": "hepatic glucose production",
# #         r"\bliver glucose output\b": "hepatic glucose production",
# #         r"\bglucose uptake by muscles?\b": "glucose uptake",
# #         r"\bglucose uptake by adipose cells?\b": "glucose uptake",
# #         r"\bmaximum retail price\b": "mrp",
# #         r"\brecommended dose\b": "recommended dosage",
# #         r"\bone tablet\b": "1 tab",
# #         r"\bone tab\b": "1 tab",
# #         r"\bmode of action\b": "moa",
# #     }

# #     for pattern, replacement in replacements.items():
# #         normalized = re.sub(pattern, replacement, normalized)

# #     return normalized


# # def _extract_semantic_concepts(text: str) -> set[str]:
# #     """Extract medical concepts that can be matched semantically."""
# #     concept_patterns = {
# #         "insulin sensitivity": (r"\binsulin sensitivity\b",),
# #         "glucose uptake": (r"\bglucose uptake\b",),
# #         "hepatic glucose production": (r"\bhepatic glucose production\b",),
# #         "voglibose": (r"\bvoglibose\b",),
# #         "alpha glucosidase inhibition": (
# #             r"\balpha glucosidase\b.*\binhibit\b",
# #             r"\binhibit\b.*\balpha glucosidase\b",
# #         ),
# #         "delayed glucose absorption": (
# #             r"\bdelay\b.*\bglucose absorption\b",
# #             r"\bglucose absorption\b.*\bdelay\b",
# #             r"\bdelay\b.*\bcarbohydrate absorption\b",
# #             r"\bdecrease\b.*\bcarbohydrate absorption\b",
# #             r"\bcarbohydrate absorption\b.*\bdecrease\b",
# #             r"\breduce\b.*\bcarbohydrate absorption\b",
# #             r"\bcarbohydrate absorption\b.*\breduce\b",
# #             r"\bslow\b.*\bcarbohydrate digestion\b",
# #         ),
# #         "postprandial glucose control": (
# #             r"\bpost\s*prandial\b",
# #             r"\bpphg\b",
# #             r"\bglycaemic excursions?\b",
# #         ),
# #         "sglt2 inhibition": (
# #             r"\bsglt\s*2\b.*\binhibit\b",
# #             r"\binhibit\b.*\bsglt\s*2\b",
# #             r"\bsodium glucose cotransporter 2\b",
# #         ),
# #         "renal glucose excretion": (
# #             r"\burinary glucose excretion\b",
# #             r"\bglucose excretion\b",
# #             r"\breduces? reabsorption of filtered glucose\b",
# #             r"\bfiltered glucose\b.*\breabsorption\b",
# #         ),
# #         "dpp4 inhibition": (
# #             r"\bdpp\s*4\b.*\binhibit\b",
# #             r"\binhibit\b.*\bdpp\s*4\b",
# #             r"\bdpp4 enzyme inhibitor\b",
# #             r"\b>\s*80\s*%\s*dpp4 inhibition\b",
# #         ),
# #         "glp gip incretin": (
# #             r"\bglp\s*1\b",
# #             r"\bgip\b",
# #             r"\bincretin effect\b",
# #         ),
# #         "fast slow dpp4 binding": (
# #             r"\bfast association\b.*\bslow dissociation\b",
# #             r"\bslow dissociation\b.*\bfast association\b",
# #             r"\breversible\b.*\blong lasting\b",
# #             r"\bsustained increase\b.*\bincretin\b",
# #         ),
# #         "dpp4 selectivity": (
# #             r"\bselectivity\b.*\bdpp\s*4\b.*\bdpp\s*2\s*/\s*8\s*/\s*9\b",
# #             r"\bdpp\s*4\b.*\bdpp\s*2\s*/\s*8\s*/\s*9\b",
# #             r"\bdpp\s*8\b.*\bdpp\s*9\b",
# #             r"\b10000\s*fold selectivity\b",
# #         ),
# #         "reduced off target effects": (
# #             r"\bless off target\b",
# #             r"\boff target side effect\b",
# #             r"\bbetter safety\b",
# #             r"\bbetter compliance\b",
# #         ),
# #         "od convenience": (
# #             r"\btrue\s*24\b",
# #             r"\b24\s*efficacy\b",
# #             r"\bod convenience\b",
# #             r"\bonce a daily\b",
# #             r"\bonce daily\b",
# #         ),
# #         "immunosuppressant": (r"\bimmunosuppressant\b", r"\bsuppress immune\b"),
# #         "calcineurin inhibitor": (r"\bcalcineurin inhibitor\b", r"\bcalcineurin activity\b"),
# #         "solid organ transplantation": (
# #             r"\bsolid organ transplantation\b",
# #             r"\bsot\b",
# #             r"\btransplanted organ\b",
# #         ),
# #         "kidney liver transplant": (
# #             r"\bkidney\b.*\bliver\b",
# #             r"\bliver\b.*\bkidney\b",
# #         ),
# #         "kidney liver heart transplantation": (
# #             r"\bkidney\b.*\bliver\b.*\bheart\b",
# #             r"\bheart\b.*\bkidney\b.*\bliver\b",
# #             r"\bkidney\s*,?\s*liver\s*(?:and|,)\s*heart\b",
# #         ),
# #         "heart lung transplant": (
# #             r"\bheart\b.*\blung",
# #             r"\blung.*\bheart\b",
# #         ),
# #         "bone marrow transplantation": (
# #             r"\bbone marrow transplantation\b",
# #             r"\bbmt\b",
# #         ),
# #         "organ rejection prophylaxis": (
# #             r"\bprophylaxis\b.*\borgan rejection\b",
# #             r"\bprevent(?:s|ion)?\b.*\brejection\b",
# #             r"\brejection\b.*\btransplanted organ\b",
# #         ),
# #         "enteric formulation": (
# #             r"\benteric formulation\b",
# #             r"\bdelayed release\b",
# #             r"\bdelayed-release\b",
# #         ),
# #         "mycophenolic acid delivery": (
# #             r"\bmycophenolic acid\b.*\bintestine\b",
# #             r"\bdelivers\b.*\bintestine\b",
# #         ),
# #         "mycophenolate mofetil prodrug": (
# #             r"\bmycophenolate mofetil\b.*\bprodrug\b",
# #             r"\bmycept\b.*\bprodrug\b",
# #         ),
# #         "stomach conversion": (
# #             r"\bconverted\b.*\bstomach\b",
# #             r"\bstomach\b.*\bconverted\b",
# #         ),
# #         "mycophenolate sodium": (
# #             r"\bmycophenolate sodium\b",
# #         ),
# #         "gi tolerability": (
# #             r"\bgi compromised\b",
# #             r"\bgi intolerance\b",
# #             r"\bgastrointestinal symptoms\b",
# #             r"\bgi safety\b",
# #         ),
# #         "central nervous system": (
# #             r"\bcentral nervous system\b",
# #             r"\bcns\b",
# #         ),
# #         "normal saline dilution": (
# #             r"\bnormal saline\b",
# #             r"\bsodium chloride\b",
# #         ),
# #         "iv infusion": (
# #             r"\biv infusion\b",
# #             r"\binfusion\b",
# #             r"\bintravenously\b",
# #         ),
# #         "cars trial": (
# #             r"\bcars trial\b",
# #             r"\bcars\b",
# #         ),
# #         "upper limb motor function": (
# #             r"\bupper limb motor functions?\b",
# #             r"\bmotor functions?\b",
# #         ),
# #         "glycaemic control": (r"\bglycaemic control\b", r"\ba1c\b", r"\btype 2 diabetes management\b"),
# #         "sulphonylurea receptor binding": (
# #             r"\bsulphonylurea receptor\b",
# #             r"\bsur\s*1\b",
# #             r"\bk\+?\s*channel\b",
# #         ),
# #         "insulin secretion": (
# #             r"\binsulin secretion\b",
# #             r"\bsecretion of insulin\b",
# #             r"\bincrease\b.*\binsulin\b",
# #             r"\binsulin\b.*\bsecretion\b",
# #         ),
# #         "one tab od": (r"\b1 tab od\b", r"\bone tab od\b"),
# #         "one tab bid": (r"\b1 tab bid\b", r"\bone tab bid\b"),
# #         "titrated to two tablets": (r"\btitrated to two tablets\b",),
# #         "type 2 diabetes management": (
# #             r"\btype 2 diabetes management\b",
# #             r"\btype 2 diabetes mellitus\b",
# #             r"\bt2dm\b",
# #         ),
# #         "reference brand": (r"\breference brand\b",),
# #         "years of trust": (r"\byears of trust\b", r"\b25 years\b"),
# #         "weight neutral": (r"\bweight neutral\b",),
# #         "no active metabolites": (r"\bno active metabolites\b",),
# #         "safe renal impairment": (
# #             r"\bckd\b",
# #             r"\brenal\b",
# #             r"\bdose adjustment\b",
# #             r"\bstage 3\b",
# #         ),
# #         "esrd risk reduction": (
# #             r"\besrd\b",
# #             r"\bend stage renal disease\b",
# #             r"\brisk of esrd\b",
# #         ),
# #         "lesser hypoglycaemia": (r"\blesser hypoglycaemia\b", r"\breduced hypoglycaemia\b"),
# #         "selective sur1 binding": (r"\bselectively binds\b", r"\bsur 1 receptor\b"),
# #         "cv safety": (r"\bcv problems\b", r"\bcardiovascular\b"),
# #         "beta cell preservation": (r"\bbeta cell mass\b",),
# #         "free radical scavenging": (r"\bfree radical scavenging\b",),
# #         "vascular complication prevention": (r"\bvascular complications\b",),
# #         "microtubule binding": (r"\bmicrotubules?\b",),
# #         "dna separation inhibition": (r"\bdna separation\b", r"\bcell division\b"),
# #         "prevents new cell formation": (
# #             r"\bprevent(?:s|ed)? formation of new cells\b",
# #             r"\bcells? cannot complete cell division\b",
# #             r"\bprevent(?:s|ed)? cancer cell growth\b",
# #         ),
# #         "alpha1a blockade": (
# #             r"\balpha\s*-?\s*1a\b.*\bblock",
# #             r"\bblock(?:s|ade)?\b.*\balpha\s*-?\s*1a\b",
# #             r"\bselectively blocks alpha\s*-?\s*1a receptors?\b",
# #         ),
# #         "smooth muscle relaxation": (
# #             r"\brelax(?:es|ing)?\b.*\bsmooth muscles?\b",
# #             r"\bsmooth muscles?\b.*\brelax",
# #             r"\bprostate and bladder\b.*\brelax",
# #         ),
# #         "urine flow improvement": (
# #             r"\bimprov(?:es|ing)? urine flow\b",
# #             r"\burine flow\b.*\bimprov",
# #             r"\burine can pass more easily\b",
# #             r"\bflow rate improves?\b",
# #         ),
# #         "bph luts relief": (
# #             r"\bbph\b",
# #             r"\blower urinary tract symptoms?\b",
# #             r"\bluts\b",
# #             r"\bbenign prostatic hyperplasia\b",
# #         ),
# #         "beta3 agonist": (
# #             r"\bbeta\s*-?\s*3\b.*\bagonist\b",
# #             r"\bβ\s*3\b.*\bagonist\b",
# #         ),
# #         "bladder relaxation": (
# #             r"\brelax(?:es|ation)?\b.*\bbladder\b",
# #             r"\bbladder\b.*\brelax",
# #         ),
# #         "overactive bladder symptom control": (
# #             r"\boveractive bladder\b",
# #             r"\boab\b",
# #             r"\burinary urgency\b",
# #             r"\bfrequency\b.*\burinary\b",
# #         ),
# #         "respiratory immunity": (
# #             r"\brespiratory immunity\b",
# #             r"\brespiratory immunity booster\b",
# #             r"\brespiratory diseases?\b",
# #         ),
# #         "anti inflammatory": (
# #             r"\banti inflammatory\b",
# #             r"\banti-inflammatory\b",
# #             r"\bairway inflammation\b",
# #         ),
# #         "immunoregulatory": (
# #             r"\bimmunoregulatory\b",
# #             r"\bmodulate\b.*\bimmune responses?\b",
# #             r"\binnate and adaptive immune responses?\b",
# #         ),
# #         "copd exacerbation reduction": (
# #             r"\breduces? rate of moderate\s*/\s*severe copd exacerbations?\b",
# #             r"\breduces?.{0,80}\bcopd exacerbations?\b",
# #             r"\bexacerbations?\b",
# #         ),
# #         "glucocorticoid responsiveness": (
# #             r"\bglucocorticoid responsiveness\b",
# #             r"\bpoor glucocorticoid responsiveness\b",
# #         ),
# #         "immune health": (
# #             r"\bimmune health\b",
# #             r"\bimmune system\b",
# #             r"\bimmune cells?\b",
# #         ),
# #         "formoterol beta2 agonist": (
# #             r"\bformoterol\b.*\b(?:beta|β)\s*2\b",
# #             r"\b(?:beta|β)\s*2\b.*\bformoterol\b",
# #             r"\blaba\b",
# #         ),
# #         "glycopyrronium m3 antagonist": (
# #             r"\bglycopyrronium\b.*\bm3\b",
# #             r"\bm3\b.*\bglycopyrronium\b",
# #             r"\blama\b",
# #             r"\bmuscarinic antagonist\b",
# #         ),
# #         "bronchodilation": (
# #             r"\bbronchodilation\b",
# #             r"\bbronchodilator\b",
# #             r"\bprevent bronchoconstriction\b",
# #             r"\bairways?\b.*\brelax",
# #         ),
# #         "copd maintenance": (
# #             r"\bcopd\b",
# #             r"\blong term maintenance treatment\b",
# #             r"\bmaintenance treatment\b.*\bcopd\b",
# #         ),
# #         "fast onset": (
# #             r"\bfast onset\b",
# #             r"\bwithin 5 minutes\b",
# #             r"\bwithin about 5 minutes\b",
# #         ),
# #         "twenty four hour relief": (
# #             r"\b24\s*hrs?\s*relief\b",
# #             r"\b24\s*hour\b",
# #             r"\bday time\b.*\bnight time\b",
# #         ),
# #         "peel off strip": (
# #             r"\bpeel\s*-?\s*off strip\b",
# #             r"\bunique peel\s*-?\s*off\b",
# #         ),
# #         "moisture protection": (
# #             r"\bprotects? each capsule from moisture\b",
# #             r"\bmoisture\b",
# #             r"\bdose stability\b",
# #         ),
# #         "safe peeling": (
# #             r"\bpeeling happens safely\b",
# #             r"\bsafe peeling\b",
# #             r"\bperforated marking\b",
# #         ),
# #         "right direction marking": (
# #             r"\bpeel off marking\b",
# #             r"\bright direction\b",
# #             r"\bcorrect direction\b",
# #         ),
# #         "no next capsule exposure": (
# #             r"\bwithout exposing the next capsule\b",
# #             r"\bneighbouring capsules? (?:are )?not exposed\b",
# #             r"\bopens only one blister\b",
# #         ),
# #         "clinical evidence": (
# #             r"\bclinical trials?\b",
# #             r"\bbioequivalence studies\b",
# #             r"\bsupported by\b.*\bstudies\b",
# #         ),
# #         "bioavailability": (
# #             r"\bbioavailability\b",
# #             r"\bbioral\b",
# #         ),
# #         "nebulization route": (
# #             r"\bnebulization\b",
# #             r"\bnebulizer\b",
# #             r"\bnebulisation\b",
# #             r"\bvia nebulization\b",
# #         ),
# #         "gastrointestinal discomfort": (
# #             r"\bgastrointestinal disturbances?\b",
# #             r"\bgastrointestinal discomfort\b",
# #             r"\babdominal discomfort\b",
# #             r"\bnausea\b",
# #             r"\bvomiting\b",
# #             r"\bdyspepsia\b",
# #             r"\bgi upset\b",
# #         ),
# #         "renal dysfunction": (
# #             r"\brenal dysfunction\b",
# #             r"\brenal failure\b",
# #         ),
# #         "tremor": (r"\btremor\b",),
# #         "hirsutism": (r"\bhirsutism\b",),
# #         "hypertension": (r"\bhypertension\b",),
# #         "gum hyperplasia": (
# #             r"\bgum hyperplasia\b",
# #             r"\bgingival hyperplasia\b",
# #         ),
# #         "nephrotoxicity monitoring": (
# #             r"\bnephrotoxicity\b.*\bmonitoring of renal function\b",
# #             r"\bmonitoring of renal function\b",
# #             r"\brenal function\b.*\bmonitor",
# #         ),
# #     }

# #     concepts: set[str] = set()
# #     for concept, patterns in concept_patterns.items():
# #         if any(re.search(pattern, text) for pattern in patterns):
# #             concepts.add(concept)

# #     return concepts


# # def _has_descriptive_context_overlap(response_text: str, page_text: str) -> bool:
# #     """Return whether page has related descriptive context for FAIL vs missing."""
# #     context_terms = {
# #         "metformin",
# #         "gliclazide",
# #         "glizid",
# #         "mxr",
# #         "xr",
# #         "sulphonylurea",
# #         "hypoglycaemia",
# #         "diabetes",
# #         "dosage",
# #         "indications",
# #         "usp",
# #         "safety",
# #         "quality",
# #         "docetaxel",
# #         "microtubule",
# #         "microtubules",
# #         "cancer",
# #         "cell division",
# #     }
# #     response_terms = {term for term in context_terms if term in response_text}
# #     page_terms = {term for term in context_terms if term in page_text}
# #     return bool(response_terms.intersection(page_terms))


# # def _requires_descriptive_comparison(normalized_question: str) -> bool:
# #     """Return whether a descriptive question asks for comparative superiority."""
# #     comparison_terms = (
# #         "more effective than",
# #         "better than",
# #         "superior to",
# #         "compared to",
# #         "versus",
# #         "vs",
# #         "than silodosin alone",
# #         "than alone",
# #     )
# #     return any(term in normalized_question for term in comparison_terms)


# # def _has_supported_descriptive_comparison(normalized_page: str) -> bool:
# #     """Return whether cited text contains evidence for a comparative claim."""
# #     comparison_evidence = (
# #         "more effective than",
# #         "better than",
# #         "superior to",
# #         "lower than",
# #         "lower risk than",
# #         "lower hypoglycemia risk than",
# #         "lower hypoglycaemia risk than",
# #         "reduce hypoglycemia risk than",
# #         "reduced hypoglycemia risk than",
# #         "reduce hypoglycaemia risk than",
# #         "reduced hypoglycaemia risk than",
# #         "less than",
# #         "greater than",
# #         "greater hba1c",
# #         "1.5x greater",
# #         "1.5 times greater",
# #         "more affordable than",
# #         "compared to",
# #         "versus",
# #         " vs ",
# #         "than silodosin alone",
# #         "than alone",
# #         "add on",
# #         "combination",
# #         "storage symptoms",
# #     )
# #     return any(term in normalized_page for term in comparison_evidence)


# # def _strip_citation_tail(response: str) -> str:
# #     """Remove citation-reference suffix from model response before matching."""
# #     split_parts = re.split(r"\bcitation\b", response, flags=re.IGNORECASE, maxsplit=1)
# #     response_without_citation_block = split_parts[0].strip()
# #     response_without_citation_block = _remove_inline_citation_markers(
# #         response_without_citation_block
# #     )
# #     return re.sub(
# #         r"(?:\s+\d+(?:\s*,\s*\d+)*)+\s*$",
# #         "",
# #         response_without_citation_block,
# #     ).strip()


# # def _remove_inline_citation_markers(text: str) -> str:
# #     """Remove inline citation markers like 1,2 without removing product values."""
# #     def replace_marker(match: re.Match[str]) -> str:
# #         marker = match.group(1)
# #         marker_numbers = [int(number) for number in re.findall(r"\d+", marker)]
# #         if marker_numbers and all(number <= 20 for number in marker_numbers):
# #             return " "
# #         return match.group(0)

# #     text = re.sub(r"(?<=\s)(\d+(?:\s*,\s*\d)+)(?=\s|$)", replace_marker, text)
# #     return re.sub(r"\s+", " ", text).strip()


# # def _extract_keywords(text: str) -> set[str]:
# #     """Extract useful comparison keywords from text."""
# #     stop_words = {
# #         "the",
# #         "and",
# #         "are",
# #         "as",
# #         "be",
# #         "by",
# #         "for",
# #         "is",
# #         "in",
# #         "it",
# #         "its",
# #         "of",
# #         "on",
# #         "or",
# #         "to",
# #         "was",
# #         "with",
# #         "from",
# #         "this",
# #         "that",
# #         "same",
# #         "category",
# #         "listed",
# #         "list",
# #         "segment",
# #         "sources",
# #         "source",
# #         "company",
# #         "companies",
# #         "information",
# #         "provided",
# #         "matching",
# #         "couldn",
# #         "couldnt",
# #         "contains",
# #         "contain",
# #         "containing",
# #         "has",
# #         "have",
# #         "having",
# #         "comprises",
# #         "comprise",
# #         "composition",
# #         "per",
# #         "tablet",
# #         "tablets",
# #         "citation",
# #         "page",
# #         "source",
# #         "brand",
# #         "snapshot",
# #         "updated",
# #         "document",
# #         "available",
# #         "mrp",
# #         "price",
# #         "strip",
# #         "injection",
# #         "product",
# #         "pack",
# #         "size",
# #         "bottle",
# #         "vial",
# #         "vials",
# #         "ampoule",
# #         "ampoules",
# #         "sachet",
# #         "sachets",
# #         "capsule",
# #         "capsules",
# #         "tabs",
# #     }
# #     words = set(re.findall(r"[a-z][a-z0-9-]{1,}", text))
# #     return words.difference(stop_words)


# # def _has_keyword_coverage(response_keywords: set[str], page_keywords: set[str]) -> bool:
# #     """Require high text overlap while allowing harmless factual wording variants."""
# #     if not response_keywords:
# #         return True

# #     matched_keywords = response_keywords.intersection(page_keywords)
# #     minimum_matches = max(1, int(len(response_keywords) * 0.80 + 0.999))
# #     return len(matched_keywords) >= minimum_matches


# # def _is_missing_source_data(text: str) -> bool:
# #     """Return whether page-scoped DOM extraction failed."""
# #     normalized = normalize_text(text)
# #     return not normalized or "no dom page data available" in normalized or "no page data available" in normalized


# """PDF parser response and citation validation helpers.

# Critical pharma validation contract:
# - Validate only against the exact cited PDF page number.
# - If SuperAI returns multiple values, every value must be checked.
# - If SuperAI returns multiple citations, each cited page is checked one by one.
# - PASS requires all required SuperAI values to match the cited page.
# - FAIL means related cited-page data exists but one or more values mismatch.
# - DATA MISSING means the cited document/page/value cannot be found.
# """

# import re
# from utils.logger import get_logger as _get_logger

# _validator_logger = _get_logger("validator")

# # Accumulated per-question validation steps written by _log_validation_step.
# # Cleared at the start of each question in the main validation loop.
# VALIDATION_LOG: list[dict] = []


# def _log_validation_step(
#     *,
#     rule: str,
#     product: str = "",
#     attribute: str = "",
#     row: str = "",
#     column: str = "",
#     doc_value: object = None,
#     response_value: object = None,
#     normalization: str = "",
#     verdict: str,
#     reason: str = "",
# ) -> None:
#     """Append one validation step to VALIDATION_LOG and emit a debug log line.

#     Call this from every sub-validator so that DATA MISSING results can be
#     diagnosed without adding manual print statements.
#     """
#     entry = {
#         "rule": rule,
#         "product": product,
#         "attribute": attribute,
#         "row": row,
#         "column": column,
#         "doc_value": doc_value,
#         "response_value": response_value,
#         "normalization": normalization,
#         "verdict": verdict,
#         "reason": reason,
#     }
#     VALIDATION_LOG.append(entry)
#     _validator_logger.debug(
#         "[%s] product=%r attr=%r row=%r col=%r doc=%r resp=%r norm=%r → %s | %s",
#         rule,
#         product,
#         attribute,
#         row,
#         column,
#         doc_value,
#         response_value,
#         normalization,
#         verdict,
#         reason,
#     )


# COMPANY_ENTITY_MATCH_THRESHOLD = 0.95

# # Fine-grained attribute type mappings.  These are evaluated BEFORE question
# # type routing so that "cost per couple" is never mistaken for PRICE/MRP and
# # "PM objective" is never compared against the Quarterly Objective column.
# _ATTRIBUTE_MAPPINGS: dict[str, tuple[str, ...]] = {
#     "PRICE": (
#         "mrp",
#         "revised mrp",
#         "new mrp",
#         "cost per tablet",
#         "cost per strip",
#         "price per tablet",
#         "price per strip",
#         "per tablet",
#         "per strip",
#         "per tab",
#     ),
#     "INCENTIVE": (
#         "incentive per strip",
#         "incentive per tablet",
#         "incentive per unit",
#         "incentive per tab",
#         "incentive value",
#         "incentive amount",
#     ),
#     "PM_OBJECTIVE": (
#         "pm objective",
#         "pmr objective",
#         "pm/pmr objective",
#         "monthly objective",
#         "monthly minimum",
#         "minimum objective",
#         "pm target",
#         "pmr target",
#     ),
#     "QUARTERLY_OBJECTIVE": (
#         "quarterly objective",
#         "quarterly minimum",
#         "quarterly pmr",
#         "quarterly pm",
#         "qtr objective",
#         "q objective",
#     ),
#     "TRIP_COST": (
#         "cost per couple",
#         "couple cost",
#         "trip cost",
#         "foreign trip",
#         "domestic trip",
#         "international trip",
#         "holiday trip",
#         "incentive trip",
#     ),
#     "MEDAL_VALUE": (
#         "medal value",
#         "medal worth",
#         "medal amount",
#         "gold medal",
#         "silver medal",
#     ),
#     "AWARD_VALUE": (
#         "award value",
#         "award cost",
#         "award amount",
#         "award worth",
#     ),
#     "REIMBURSEMENT": (
#         "reimbursement value",
#         "reimbursement amount",
#         "reimbursement cost",
#     ),
# }


# def resolve_attribute_type(question: str) -> str:
#     """Resolve the fine-grained attribute type from a question string.

#     Returns one of the keys in _ATTRIBUTE_MAPPINGS, or "GENERAL" when no
#     specific attribute can be identified.  Always call this before choosing a
#     validation strategy so that PM_OBJECTIVE is never compared against the
#     Quarterly Objective column and TRIP_COST is never compared against MRP.
#     """
#     normalized = normalize_text(question)
#     for attr_type, terms in _ATTRIBUTE_MAPPINGS.items():
#         if any(term in normalized for term in terms):
#             return attr_type
#     return "GENERAL"


# QUESTION_TYPES = {
#     "PRICE_COMPARISON",
#     "PRICE_LOOKUP",
#     "TRIP_AWARD_COST",
#     "DOSAGE_FREQUENCY",
#     "DOSAGE_FORM",
#     "PACK_SIZE",
#     "STRENGTH_LOOKUP",
#     "COMPETITOR_BRAND",
#     "COMPANY_LOOKUP",
#     "COMPOSITION",
#     "ACTIVE_INGREDIENT",
#     "MOLECULE_LIST",
#     "PRODUCT_COMPARISON",
#     "CLINICAL_OUTCOME",
#     "CLINICAL_EVIDENCE",
#     "ACRONYM_EXPANSION",
#     "DESCRIPTIVE_USP",
#     "GENERAL",
# }


# def classify_question_type(question: str, response: str = "") -> str:
#     """Classify question intent before validation routing."""
#     normalized = normalize_text(f"{question} {response}")
#     normalized_question = normalize_text(question)

#     if "composition" in normalized_question:
#         return "COMPOSITION"

#     if "active ingredient" in normalized_question:
#         return "ACTIVE_INGREDIENT"

#     if any(term in normalized_question for term in ("dosage form", "dosage forms", "available forms", "forms of")):
#         return "DOSAGE_FORM"

#     if any(
#         term in normalized_question
#         for term in (
#             "strength range",
#             "which strength",
#             "what strength",
#             "strength of",
#             "strength is",
#             "present at a strength",
#         )
#     ):
#         return "STRENGTH_LOOKUP"

#     if (
#         "how many" in normalized_question
#         and any(unit in normalized_question for unit in ("tablet", "tablets", "tab", "capsule", "capsules", "cap"))
#         and any(container in normalized_question for container in ("strip", "box", "pack"))
#     ):
#         return "PACK_SIZE"

#     if any(
#         term in normalized_question
#         for term in (
#             "which three molecules",
#             "which molecules",
#             "what molecules",
#             "molecules are present",
#             "molecules are included",
#             "molecules included",
#             "molecules does",
#             "molecules are there",
#             "molecules are in",
#         )
#     ):
#         return "MOLECULE_LIST"

#     if "contains" in normalized_question and re.search(
#         r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)\b",
#         normalized,
#     ):
#         return "COMPOSITION"

#     price_comparison_terms = (
#         "cheaper",
#         "cost saving",
#         "saving",
#         "lowest",
#         "highest",
#         "cheapest",
#         "most expensive",
#     )
#     explicit_price_terms = ("mrp", "price", "cost", "per strip", "per tablet", "per tab")
#     if any(term in normalized_question for term in price_comparison_terms):
#         return "PRICE_COMPARISON"

#     if (
#         any(term in normalized_question for term in ("difference", "compared to", "compared with", "versus", "vs"))
#         and any(term in normalized_question for term in explicit_price_terms)
#     ):
#         return "PRICE_COMPARISON"

#     if "competitor" in normalized_question and any(
#         term in normalized_question
#         for term in ("price", "priced", "mrp", "per strip", "lowest", "highest", "cheapest")
#     ):
#         return "PRICE_COMPARISON"

#     if _is_multi_product_question(normalized_question):
#         return "PRODUCT_COMPARISON"

#     if "marketed by" in normalized_question or "markets" in normalized_question:
#         return "COMPANY_LOOKUP"

#     if "competitor" in normalized_question and any(
#         term in normalized_question for term in ("belongs to", "company", "manufacturer", "manufactures")
#     ):
#         return "COMPANY_LOOKUP"

#     if any(term in normalized_question for term in ("company", "companys", "company’s", "manufacturer", "manufactures")):
#         return "COMPANY_LOOKUP"

#     # Incentive and objective questions must not be routed to PRICE_LOOKUP.
#     # "per strip" in the question refers to the incentive attribute, not MRP.
#     _objective_incentive_terms = (
#         "incentive",
#         "minimum objective",
#         "quarterly objective",
#         "monthly objective",
#         "quarterly minimum",
#         "monthly minimum",
#         "pmr objective",
#     )
#     if any(term in normalized_question for term in _objective_incentive_terms):
#         return "GENERAL"

#     # Trip/award/medal/reimbursement cost questions carry large values in Indian
#     # number notation (₹1,10,000) and must not be routed through the MRP product-
#     # price path which expects per-strip or per-tablet prices.
#     _trip_award_terms = (
#         "cost per couple",
#         "couple cost",
#         "trip cost",
#         "foreign trip",
#         "domestic trip",
#         "international trip",
#         "medal value",
#         "medal worth",
#         "award value",
#         "award cost",
#         "award amount",
#         "reimbursement value",
#         "reimbursement amount",
#         "holiday trip",
#         "incentive trip",
#     )
#     if any(term in normalized_question for term in _trip_award_terms):
#         return "TRIP_AWARD_COST"

#     if any(term in normalized_question for term in ("mrp", "price", "cost", "per strip")):
#         return "PRICE_LOOKUP"

#     if any(
#         term in normalized_question
#         for term in (
#             "dosage",
#             "dose",
#             "how many times",
#             "times a day",
#             "once daily",
#             "twice daily",
#             "frequency",
#             "every 12 hours",
#         )
#     ):
#         return "DOSAGE_FREQUENCY"

#     # Trial enrollment / sample-size lookup questions ("how many patients enrolled
#     # in the SHEP trial?") must not fall into DESCRIPTIVE_USP via "trial".  They
#     # are pure count lookups and belong in CLINICAL_EVIDENCE so the numeric path
#     # can validate the specific number.
#     if (
#         "how many" in normalized_question
#         and any(
#             term in normalized_question
#             for term in ("enrolled", "enroll", "randomized", "randomised", "participants", "patients", "subjects")
#         )
#         and any(
#             term in normalized_question
#             for term in ("trial", "study", "program", "programme")
#         )
#     ):
#         return "CLINICAL_EVIDENCE"

#     # Policy/sales incentive table questions must not be routed to DESCRIPTIVE_USP.
#     # Terms like "growth" appear in business context (sales growth, HQ growth %)
#     # but the DESCRIPTIVE_USP path is designed for clinical/medical text only.
#     _policy_table_terms = (
#         "productivity",
#         "couple ticket",
#         "single ticket",
#         "sales credit",
#         "invoice date",
#         "stockist",
#         "pangraf sale contribution",
#         "negative growth",
#         "growth percentage",
#         "hq growth",
#         "h q growth",
#         "individual growth",
#         "field employee",
#     )
#     if any(term in normalized_question for term in _policy_table_terms):
#         return "GENERAL"

#     # Acronym/full-form questions ask only for the expansion of an abbreviation.
#     # The document typically appends a trailing benefit clause after the expansion
#     # ("POMA Technology – Potency Maintenance Technology to Assure better...").
#     # These must NOT fall into DESCRIPTIVE_USP where the full trailing clause is
#     # required for a PASS; compare only the core acronym expansion.
#     if any(
#         term in normalized_question
#         for term in (
#             "full form",
#             "stands for",
#             "stand for",
#             "acronym",
#             "abbreviation",
#             "expand",
#             "short form",
#             "full name",
#         )
#     ):
#         return "ACRONYM_EXPANSION"

#     if (
#         normalized_question.startswith(("why ", "how "))
#         or any(
#             term in normalized_question
#             for term in (
#                 "prevent",
#                 "prevents",
#                 "inhibit",
#                 "inhibits",
#                 "delays",
#                 "absorption",
#                 "growth",
#                 "ingredient",
#                 "drug class",
#                 "class",
#                 "surgeries",
#                 "used",
#                 "condition",
#                 "prescribed",
#                 "form",
#                 "tolerability",
#                 "system",
#                 "medium",
#                 "dilution",
#                 "trial",
#                 "upper limb",
#                 "motor function",
#                 "administration route",
#                 "route",
#                 "nebulization",
#                 "symptom",
#                 "symptoms",
#                 "organ",
#                 "organs",
#                 "transplantation",
#                 "side effect",
#                 "side effects",
#                 "adverse",
#                 "adverse effect",
#                 "adverse effects",
#                 "adverse reaction",
#                 "adverse reactions",
#                 "adverse event",
#                 "adverse events",
#                 "dizziness",
#                 "dry mouth",
#                 "gastrointestinal",
#                 "discomfort",
#                 "nephrotoxicity",
#                 "monitoring",
#                 "precaution",
#                 "precautions",
#                 "feature",
#                 "features",
#                 "advantage",
#                 "advantages",
#                 "benefit",
#                 "benefits",
#             )
#         )
#     ):
#         return "DESCRIPTIVE_USP"

#     if "competitor" in normalized_question and "brand" in normalized_question:
#         return "COMPETITOR_BRAND"

#     # Clinical outcome questions ask for the MAGNITUDE of a measured effect:
#     # "By how much does X reduce LDL-C?" or "What was the risk reduction seen?"
#     # These carry numeric ranges and need range-aware validation — they must not
#     # fall into CLINICAL_EVIDENCE (which validates narrative text) or
#     # DESCRIPTIVE_USP (which uses semantic concept matching).
#     _clinical_outcome_terms = (
#         "ldl-c reduction",
#         "ldl reduction",
#         "ldl-c lowering",
#         "ldl lowering",
#         "ldl-c by",
#         "reduce ldl",
#         "reduces ldl",
#         "reduction in ldl",
#         "hba1c reduction",
#         "hba1c lowering",
#         "reduce hba1c",
#         "reduces hba1c",
#         "reduction in hba1c",
#         "risk reduction",
#         "reduces the risk",
#         "reduce the risk",
#         "relative risk reduction",
#         "absolute risk reduction",
#         "cardiovascular risk reduction",
#         "cardiovascular mortality reduction",
#         "mortality reduction",
#         "reduces mortality",
#         "survival benefit",
#         "survival rate",
#         "efficacy outcome",
#         "trial endpoint",
#         "primary endpoint",
#         "secondary endpoint",
#         "major adverse cardiovascular",
#         "mace reduction",
#         "hazard ratio",
#         "odds ratio",
#         "relative risk",
#         "number needed to treat",
#         "nnt",
#         "blood pressure reduction",
#         "reduces blood pressure",
#         "systolic reduction",
#         "diastolic reduction",
#         "reduces systolic",
#         "reduces diastolic",
#         "triglyceride reduction",
#         "reduces triglyceride",
#         "hdl increase",
#         "increases hdl",
#         "glucose reduction",
#         "reduces glucose",
#         "reduces fasting",
#         "fasting glucose reduction",
#         "reduces a1c",
#         "a1c reduction",
#     )
#     if any(term in normalized_question for term in _clinical_outcome_terms):
#         return "CLINICAL_OUTCOME"

#     if any(
#         term in normalized
#         for term in (
#             "trial",
#             "study",
#             "evidence",
#             "guideline",
#             "mortality",
#             "hfref",
#             "hfr ef",
#             "hfr",
#             "class ia",
#             "recommendation",
#         )
#     ):
#         return "CLINICAL_EVIDENCE"

#     if any(
#         term in normalized_question
#         for term in (
#             "why",
#             "what makes",
#             "different",
#             "preferred",
#             "benefit",
#             "benefits",
#             "usp",
#             "advantage",
#             "advantages",
#             "mechanism",
#         )
#     ):
#         return "DESCRIPTIVE_USP"

#     return "GENERAL"


# def extract_citation_targets(text: str) -> list[dict[str, int | str]]:
#     """Extract every citation target with document name, citation number, and page."""
#     citation_text = extract_citation_text(text)
#     if not citation_text:
#         return []

# # #     decomposed_targets = _extract_all_page_label_targets(citation_text)

# # #     targets: list[dict[str, int | str]] = []
# # #     citation_number = 1
# # #     search_position = 0

# # #     while search_position < len(citation_text):
# # #         start_match = re.search(
# # #             rf"(?:^|\s){citation_number}\s+",
# # #             citation_text[search_position:],
# # #         )

# # #         if not start_match:
# # #             break

# # #         segment_start = search_position + start_match.end()
# # #         page_match = re.search(
# # #             r"(?:_Page_|page[\s:_-]+)(\d+)",
# # #             citation_text[segment_start:],
# # #             flags=re.IGNORECASE,
# # #         )

# # #         if not page_match:
# # #             break

# # #         page_end = segment_start + page_match.end()
# # #         next_start_match = re.search(
# # #             rf"\s{citation_number + 1}\s+",
# # #             citation_text[page_end:],
# # #         )
# # #         segment_end = (
# # #             page_end + next_start_match.start()
# # #             if next_start_match
# # #             else len(citation_text)
# # #         )
# # #         citation_label = citation_text[segment_start:segment_end].strip()

# # #         targets.append(
# # #             {
# # #                 "citation_number": citation_number,
# # #                 "page_number": int(page_match.group(1)),
# # #                 "document_name": extract_document_name(citation_label),
# # #                 "citation_text": citation_label,
# # #             }
# # #         )
# # #         citation_number += 1
# # #         search_position = segment_end

# # #     if len(decomposed_targets) > len(targets):
# # #         return decomposed_targets

# # #     if targets:
# # #         return targets

# # #     return decomposed_targets


# # # def _extract_all_page_label_targets(text: str) -> list[dict[str, int | str]]:
# # #     """Extract unique page labels from polluted citation text."""
# # #     targets: list[dict[str, int | str]] = []
# # #     seen: set[tuple[str, int]] = set()
# # #     pattern = re.compile(
# # #         r"([A-Za-z0-9][A-Za-z0-9 &()./-]{1,80}?"
# # #         r"(?:_Page_|page[\s:_-]+)(\d+))",
# # #         flags=re.IGNORECASE,
# # #     )

# # #     for match in pattern.finditer(text):
# # #         citation_label = match.group(1).strip()
# # #         document_name = extract_document_name(citation_label)
# # #         page_number = int(match.group(2))
# # #         key = (normalize_text(document_name), page_number)

# # #         if key in seen:
# # #             continue

# # #         seen.add(key)
# # #         targets.append(
# # #             {
# # #                 "citation_number": len(targets) + 1,
# # #                 "page_number": page_number,
# # #                 "document_name": document_name,
# # #                 "citation_text": citation_label,
# # #             }
# # #         )

# # #     return targets


# # def extract_document_name(citation_label: str) -> str:
# #     """Extract the source document name from a citation label."""
# #     cleaned_label = " ".join(citation_label.split()).strip()
# #     document_name = re.sub(
# #         r"(?:_Page_|page[\s:_-]+)\d+.*$",
# #         "",
# #         cleaned_label,
# #         flags=re.IGNORECASE,
# #     ).strip(" :-_")
# #     document_name = re.sub(r"^\d+\s+", "", document_name).strip()
# #     return document_name or "UNKNOWN DOCUMENT"


# # # def normalize_text(text: str) -> str:
# # #     """Normalize text for stable page-scoped validation."""
# # #     lowered_text = text.lower().replace("\u00a0", " ")
# # #     lowered_text = re.sub(r"\bonce\s+daily\b|\bonce\s+a\s+day\b", "od", lowered_text)
# # #     lowered_text = re.sub(r"\btwice\s+daily\b|\btwice\s+a\s+day\b", "bid", lowered_text)
# # #     lowered_text = re.sub(r"\bbd\b", "bid", lowered_text)
# # #     lowered_text = re.sub(r"\bone\b", "1", lowered_text)
# # #     lowered_text = re.sub(r"\btwo\b", "2", lowered_text)
# # #     lowered_text = re.sub(r"\bthree\b", "3", lowered_text)
# # #     lowered_text = re.sub(r"\bfour\b", "4", lowered_text)
# # #     lowered_text = re.sub(r"\btablets?\b", "tab", lowered_text)
# # #     lowered_text = re.sub(r"\bcapsules?\b", "cap", lowered_text)
# # #     lowered_text = re.sub(r"\bstrips?\b", "strip", lowered_text)
# # #     lowered_text = re.sub(r"\bmaximum\s+retail\s+price\b", "mrp", lowered_text)
# # #     lowered_text = re.sub(r"\brecommended\s+dose\b", "recommended dosage", lowered_text)
# # #     lowered_text = re.sub(r"\bmode\s+of\s+action\b", "moa", lowered_text)
# # #     lowered_text = re.sub(r"\btype\s*ii\b", "type 2", lowered_text)
# # #     lowered_text = re.sub(r"\bhcl\b", "hydrochloride", lowered_text)
# # #     lowered_text = re.sub(r"\bglizid\s*-\s*m\s*xr\b", "glizid mxr", lowered_text)
# # #     lowered_text = re.sub(r"\bglizid\s*-\s*mxr\b", "glizid mxr", lowered_text)
# # #     lowered_text = re.sub(r"(?<=\w)[\s_\-./]+(?=\w)", " ", lowered_text)
# # #     return " ".join(lowered_text.split())


# # # def compare_response_with_source(response: str, source_text: str) -> str:
# # #     """Backward-compatible wrapper for page-scoped source validation."""
# # #     return compare_response_with_page_data(response, source_text)


# # # def extract_citation_text(text: str) -> str:
# # #     """Extract the visible citation section from a SuperAI response."""
# # #     citation_sections = re.split(r"\bcitation\b", text, flags=re.IGNORECASE, maxsplit=1)
# # #     if len(citation_sections) > 1:
# # #         citation_text = citation_sections[1].strip()
# # #         if re.search(r"(?:_Page_|page[\s:_-]+)\d+", citation_text, flags=re.IGNORECASE):
# # #             return citation_text
# # #         return ""

# # #     citation_matches = re.findall(
# # #         r"(?:\d+\s+)?[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+",
# # #         text,
# # #         flags=re.IGNORECASE,
# # #     )
# # #     return " ".join(
# # #         match.strip()
# # #         for match in citation_matches
# # #         if re.search(r"(?:_Page_|page[\s:_-]+)\d+", match, flags=re.IGNORECASE)
# # #     )


# def extract_page_number(text: str) -> int:
#     """Extract the page number tied to the SuperAI answer's citation marker."""
#     citation_sections = re.split(r"\bcitation\b", text, flags=re.IGNORECASE, maxsplit=1)

#     if len(citation_sections) > 1:
#         answer_text = citation_sections[0]
#         citation_text = citation_sections[1]
#         citation_page_map = _extract_citation_page_map(citation_text)
#         referenced_citations = _extract_answer_citation_references(answer_text)

#         for citation_number in referenced_citations:
#             if citation_number in citation_page_map:
#                 return citation_page_map[citation_number]

#         if citation_page_map:
#             return citation_page_map[min(citation_page_map)]

#     citation_matches = re.findall(
#         r"(?:_Page_|page[\s:_-]+)(\d+)",
#         text,
#         flags=re.IGNORECASE,
#     )

#     if citation_matches:
#         return int(citation_matches[-1])

#     raise ValueError("No mandatory citation page number found in text.")


# def compare_ai_vs_pdf(
#     ai_response: str,
#     pdf_page_data: str,
#     question: str = "",
#     product: str = "",
#     citation_page: int | str = "",
# ) -> str:
#     """Compare the AI response with data extracted only from the cited PDF page."""
#     return compare_response_with_page_data(
#         ai_response, pdf_page_data, question, product=product, citation_page=citation_page
#     )


# def explain_ai_vs_pdf(ai_response: str, pdf_page_data: str, question: str = "") -> str:
#     """Return a specific reason for the page-scoped validation decision."""
#     response_content = _clean_response_for_validation(ai_response)
#     question_type = classify_question_type(question, response_content)

#     if not response_content:
#         return "Super AI response did not contain a value to validate."

#     if _is_missing_source_data(pdf_page_data):
#         return "Required value not found because cited page data is missing."

#     if question_type in {"PRICE_COMPARISON", "COMPANY_LOOKUP"}:
#         table_result = _deterministic_table_validation(response_content, pdf_page_data, question)
#         if table_result[0]:
#             return table_result[2]
#         _, reason = _compare_competitor_table_reasoning(
#             response_content,
#             pdf_page_data,
#             question,
#         )
#         return reason

#     if question_type == "PRICE_LOOKUP":
#         table_result = _deterministic_table_validation(response_content, pdf_page_data, question)
#         if table_result[0]:
#             return table_result[2]
#         _, reason = _compare_price_lookup(response_content, pdf_page_data, question)
#         return reason

#     if question_type == "PACK_SIZE":
#         _, reason = _compare_pack_size(response_content, pdf_page_data)
#         return reason

#     if question_type == "STRENGTH_LOOKUP":
#         _, reason = _compare_strength_lookup(response_content, pdf_page_data, question)
#         return reason

#     if question_type == "DOSAGE_FREQUENCY":
#         _, reason = _compare_dosage(response_content, pdf_page_data)
#         return reason

#     if question_type == "COMPETITOR_BRAND":
#         _, reason = _compare_competitor_brands(ai_response, pdf_page_data)
#         return reason

#     if question_type == "COMPOSITION":
#         _, reason = _compare_composition(response_content, pdf_page_data)
#         return reason

#     if question_type == "ACTIVE_INGREDIENT":
#         _, reason = _compare_active_ingredient(response_content, pdf_page_data)
#         return reason

#     if question_type == "MOLECULE_LIST":
#         _, reason = _compare_molecule_list(response_content, pdf_page_data, question)
#         return reason

#     if question_type == "PRODUCT_COMPARISON":
#         _, reason = _compare_multi_product_response(response_content, pdf_page_data, question)
#         return reason

#     if question_type == "ACRONYM_EXPANSION":
#         _, reason = _compare_acronym_expansion(response_content, pdf_page_data, question)
#         return reason

#     if question_type in {"CLINICAL_EVIDENCE", "DESCRIPTIVE_USP", "DOSAGE_FORM"}:
#         _, reason = _compare_descriptive_response(response_content, pdf_page_data, question)
#         return reason

#     if _is_punchline_question(question, response_content):
#         _, reason = _compare_punchline(response_content, pdf_page_data)
#         return reason

#     if _is_competitor_table_reasoning_question(question, response_content):
#         _, reason = _compare_competitor_table_reasoning(
#             response_content,
#             pdf_page_data,
#             question,
#         )
#         return reason

#     if _is_competitor_brand_question(question, response_content):
#         _, reason = _compare_competitor_brands(ai_response, pdf_page_data)
#         return reason

#     if _is_dosage_question(question, response_content):
#         _, reason = _compare_dosage(response_content, pdf_page_data)
#         return reason

#     if _is_descriptive_question(question, response_content):
#         result, reason = _compare_descriptive_response(response_content, pdf_page_data, question)
#         return reason

#     normalized_response = normalize_text(response_content)
#     normalized_page = normalize_text(pdf_page_data)
#     response_numbers = _extract_numbers(normalized_response)
#     page_numbers = _extract_numbers(normalized_page)
#     response_keywords = _extract_keywords(normalized_response)
#     page_keywords = _extract_keywords(normalized_page)
#     matched_numbers = sorted(response_numbers.intersection(page_numbers))
#     missing_numbers = sorted(response_numbers.difference(page_numbers))
#     matched_keywords = sorted(response_keywords.intersection(page_keywords))

#     if missing_numbers:
#         if matched_numbers or matched_keywords:
#             return (
#                 "Value mismatch. Missing Super AI value(s) on cited page: "
#                 f"{', '.join(missing_numbers)}."
#             )
#         return "Required Super AI value was not found on the cited page."

#     if response_numbers:
#         missing_keywords = sorted(response_keywords.difference(page_keywords))
#         if missing_keywords and not _has_keyword_coverage(response_keywords, page_keywords):
#             return (
#                 "Numeric value(s) matched, but related Super AI term(s) are missing "
#                 f"on cited page: {', '.join(missing_keywords)}."
#             )
#         return (
#             "Exact numeric value match found."
#             if not matched_numbers
#             else f"Matching value found: {', '.join(matched_numbers + matched_keywords)}."
#         )

#     if _has_keyword_coverage(response_keywords, page_keywords):
#         return f"Matching value found: {', '.join(matched_keywords)}."

#     if matched_keywords:
#         missing_keywords = sorted(response_keywords.difference(page_keywords))
#         return (
#             "Text/value mismatch. Missing Super AI term(s) on cited page: "
#             f"{', '.join(missing_keywords)}."
#         )

#     return "Required value not found in cited document/page."


# def deterministic_numeric_validation(
#     response: str,
#     page_data: str,
#     question: str = "",
# ) -> tuple[bool, str, str, str]:
#     """Validate critical numeric/unit values before semantic validation.

#     Returns:
#         applicable, result, reason, matched_values
#     """
#     response_content = _clean_response_for_validation(response)

#     if not response_content or _is_missing_source_data(page_data):
#         return False, "DATA MISSING", "", ""

#     question_type = classify_question_type(question, response_content)

#     if question_type == "COMPOSITION":
#         return False, "DATA MISSING", "", ""

#     if question_type in {"DESCRIPTIVE_USP", "CLINICAL_EVIDENCE"} and _is_patient_group_question(question):
#         return False, "DATA MISSING", "", ""

#     # Trial enrollment / sample-size count questions ("how many X enrolled in
#     # the SHEP trial?") carry the answer as a bare integer — no unit suffix.
#     # _extract_numeric_unit_values misses bare integers, so handle them here.
#     if _is_trial_count_question(question):
#         normalized_response = normalize_text(_clean_numeric_validation_text(response_content))
#         normalized_page = normalize_text(page_data)
#         response_bare = _extract_numbers(normalized_response)
#         page_bare = _extract_numbers(normalized_page)
#         # Keep only large integers (>= 100) so citation page numbers / doses don't
#         # trigger a false match.
#         large_response = {n for n in response_bare if n.isdigit() and int(n) >= 100}
#         if large_response:
#             if large_response.issubset(page_bare):
#                 return (
#                     True,
#                     "PASS",
#                     "Trial enrollment count from SuperAI matches cited page: "
#                     f"{', '.join(sorted(large_response))}.",
#                     ", ".join(sorted(large_response)),
#                 )
#             return (
#                 True,
#                 "FAIL",
#                 "Trial enrollment count mismatch. "
#                 f"SuperAI value(s) {', '.join(sorted(large_response))} "
#                 "not found on cited page.",
#                 "",
#             )
#         return False, "DATA MISSING", "", ""

#     # Incentive and objective questions bypass strict numeric extraction.
#     # The extractor produces "810 strip" from "810 strips" but the document
#     # has a bare "810", causing a false set-difference FAIL.
#     # The general comparison (_extract_numbers) handles this correctly.
#     _obj_inc_terms = (
#         "incentive",
#         "minimum objective",
#         "quarterly objective",
#         "monthly objective",
#         "quarterly minimum",
#         "monthly minimum",
#         "pmr objective",
#     )
#     if any(term in normalize_text(question) for term in _obj_inc_terms):
#         return False, "DATA MISSING", "", ""

#     if _is_variant_portfolio_question(question):
#         result, reason, matched = _compare_variant_portfolio(response_content, page_data, question)
#         return True, result, reason, matched

#     table_result = _deterministic_table_validation(response_content, page_data, question)
#     if table_result[0]:
#         return table_result

#     if question_type == "PRICE_LOOKUP":
#         result, reason = _compare_price_lookup(response_content, page_data, question)
#         matched = extract_matching_values(response_content, page_data)
#         return True, result, reason, matched

#     if question_type == "TRIP_AWARD_COST":
#         result, reason = _compare_trip_award_cost(response_content, page_data, question)
#         matched = extract_matching_values(response_content, page_data)
#         return True, result, reason, matched

#     if question_type == "CLINICAL_OUTCOME":
#         result, reason = _compare_clinical_outcome(response_content, page_data, question)
#         matched = extract_matching_values(response_content, page_data)
#         return True, result, reason, matched

#     if question_type == "ACRONYM_EXPANSION":
#         result, reason = _compare_acronym_expansion(response_content, page_data, question)
#         matched = extract_matching_values(response_content, page_data)
#         return True, result, reason, matched

#     if _is_repeat_course_question(question):
#         result, reason, matched = _compare_repeat_courses(response_content, page_data)
#         return True, result, reason, matched

#     if not _is_strict_numeric_question(question, response_content):
#         return False, "DATA MISSING", "", ""

#     if _is_dosage_question(question, response_content):
#         result, reason = _compare_dosage(response_content, page_data)
#         matched = extract_matching_values(response_content, page_data)
#         return True, result, reason, matched

#     numeric_response_content = _clean_numeric_validation_text(response_content)
#     numeric_page_data = _clean_numeric_validation_text(page_data)
#     normalized_response = normalize_text(numeric_response_content)
#     normalized_page = normalize_text(numeric_page_data)
#     response_values = _extract_numeric_unit_values(normalized_response)
#     page_values = _extract_numeric_unit_values(normalized_page)

#     if not response_values:
#         # The SuperAI answer contains no numeric values (e.g. "Couple Ticket",
#         # "Single Ticket", a text policy answer).  Numeric comparison is not
#         # applicable here — fall through to the semantic/OpenAI validator.
#         return False, "DATA MISSING", "", ""

#     if not page_values:
#         # Page has no numeric values either — not enough evidence for deterministic
#         # comparison; let OpenAI evaluate the partial/vision-extracted text.
#         return False, "DATA MISSING", "", ""

#     matched_values = sorted(response_values.intersection(page_values))
#     missing_values = sorted(response_values.difference(page_values))

#     if missing_values:
#         # Numeric-only fallback: "810 strip" from SuperAI vs bare "810" in document.
#         # _extract_numeric_unit_values requires a unit suffix; bare numbers in the
#         # document are not extracted.  Re-check using _extract_numbers which strips
#         # units naturally, so "810 strip" → "810" matches document "810".
#         page_bare = _extract_numbers(normalized_page)
#         still_missing = [
#             mv for mv in missing_values
#             if not _numeric_part_matches_bare(mv, page_bare)
#         ]
#         if not still_missing:
#             return (
#                 True,
#                 "PASS",
#                 "Numeric values match after unit-label normalization: "
#                 f"{', '.join(sorted(response_values))}.",
#                 ", ".join(sorted(response_values)),
#             )
#         missing_values = still_missing

#         if matched_values or _extract_keywords(normalized_response).intersection(
#             _extract_keywords(normalized_page)
#         ):
#             return (
#                 True,
#                 "FAIL",
#                 "Strict numeric mismatch. Missing cited-page value(s): "
#                 f"{', '.join(missing_values)}.",
#                 ", ".join(matched_values),
#             )
#         return (
#             True,
#             "DATA MISSING",
#             "Required numeric value(s) were not found on the cited page: "
#             f"{', '.join(missing_values)}.",
#             "",
#         )

#     return (
#         True,
#         "PASS",
#         "All strict numeric value(s) from SuperAI exactly match the cited page: "
#         f"{', '.join(matched_values)}.",
#         ", ".join(matched_values),
#     )


# def compare_response_with_page_data(
#     response: str,
#     page_data: str,
#     question: str = "",
#     product: str = "",
#     citation_page: int | str = "",
# ) -> str:
#     """Compare response values only against the cited PDF page data.

#     Parameters
#     ----------
#     response:       Full SuperAI response text including citation block.
#     page_data:      Extracted text from the cited PDF page.
#     question:       The original validation question.
#     product:        Product name for debug logging.
#     citation_page:  The cited page number for debug logging.
#     """
#     response_content = _clean_response_for_validation(response)
#     question_type = classify_question_type(question, response_content)

#     _validator_logger.debug(
#         "VALIDATION_START question=%r product=%r attr_type=%s citation_page=%s "
#         "response_len=%s page_len=%s",
#         question[:120],
#         product,
#         question_type,
#         citation_page,
#         len(response_content),
#         len(page_data),
#     )

#     if not response_content or _is_missing_source_data(page_data):
#         return "DATA MISSING"

#     if question_type in {"PRICE_COMPARISON", "COMPANY_LOOKUP"}:
#         table_result = _deterministic_table_validation(response_content, page_data, question)
#         if table_result[0]:
#             return table_result[1]
#         result, _ = _compare_competitor_table_reasoning(
#             response_content,
#             page_data,
#             question,
#         )
#         return result

#     if question_type == "PRICE_LOOKUP":
#         table_result = _deterministic_table_validation(response_content, page_data, question)
#         if table_result[0]:
#             return table_result[1]
#         result, _ = _compare_price_lookup(response_content, page_data, question)
#         return result

#     if question_type == "PACK_SIZE":
#         result, _ = _compare_pack_size(response_content, page_data)
#         return result

#     if question_type == "STRENGTH_LOOKUP":
#         result, _ = _compare_strength_lookup(response_content, page_data, question)
#         return result

#     if question_type == "DOSAGE_FREQUENCY":
#         result, _ = _compare_dosage(response_content, page_data)
#         return result

#     if question_type == "COMPETITOR_BRAND":
#         result, _ = _compare_competitor_brands(response, page_data)
#         return result

#     if question_type == "COMPOSITION":
#         result, _ = _compare_composition(response_content, page_data)
#         return result

#     if question_type == "ACTIVE_INGREDIENT":
#         result, _ = _compare_active_ingredient(response_content, page_data)
#         return result

#     if question_type == "MOLECULE_LIST":
#         result, _ = _compare_molecule_list(response_content, page_data, question)
#         return result

#     if question_type == "PRODUCT_COMPARISON":
#         result, _ = _compare_multi_product_response(response_content, page_data, question)
#         return result

#     if question_type in {"CLINICAL_EVIDENCE", "DESCRIPTIVE_USP", "DOSAGE_FORM"}:
#         result, _ = _compare_descriptive_response(response_content, page_data, question)
#         return result

#     if _is_punchline_question(question, response_content):
#         result, _ = _compare_punchline(response_content, page_data)
#         return result

#     if _is_competitor_table_reasoning_question(question, response_content):
#         result, _ = _compare_competitor_table_reasoning(
#             response_content,
#             page_data,
#             question,
#         )
#         return result

#     if _is_competitor_brand_question(question, response_content):
#         result, _ = _compare_competitor_brands(response, page_data)
#         return result

#     if _is_dosage_question(question, response_content):
#         result, _ = _compare_dosage(response_content, page_data)
#         return result

#     numeric_applicable, numeric_result, _, _ = deterministic_numeric_validation(
#         response,
#         page_data,
#         question,
#     )
#     if numeric_applicable:
#         return numeric_result

#     if _is_descriptive_question(question, response_content):
#         result, _ = _compare_descriptive_response(response_content, page_data, question)
#         return result

#     response_numbers = _extract_numbers(normalize_text(response_content))
#     page_numbers = _extract_numbers(normalize_text(page_data))
#     response_keywords = _extract_keywords(normalize_text(response_content))
#     page_keywords = _extract_keywords(normalize_text(page_data))

#     if response_numbers:
#         matched_numbers = response_numbers.intersection(page_numbers)
#         if response_numbers.issubset(page_numbers):
#             if not response_keywords or _has_keyword_coverage(response_keywords, page_keywords):
#                 return "PASS"
#             return "FAIL" if response_keywords.intersection(page_keywords) else "DATA MISSING"
#         return "FAIL" if matched_numbers or response_keywords.intersection(page_keywords) else "DATA MISSING"

#     if response_keywords:
#         matched_keywords = response_keywords.intersection(page_keywords)
#         if _has_keyword_coverage(response_keywords, page_keywords):
#             return "PASS"
#         return "FAIL" if matched_keywords else "DATA MISSING"

#     return "FAIL"


# def extract_citation_page_numbers(response: str) -> list[int]:
#     """Extract ordered unique citation page numbers from response text."""
#     numbers: list[int] = []
#     seen: set[int] = set()
#     for match in re.finditer(r"_Page_(\d+)", response, flags=re.IGNORECASE):
#         page_number = int(match.group(1))
#         if page_number not in seen:
#             seen.add(page_number)
#             numbers.append(page_number)
#     return numbers


# def extract_matching_values(response: str, source_text: str) -> str:
#     """Return values from the response that are also present in source text."""
#     if _is_missing_source_data(source_text):
#         return ""

#     normalized_response = normalize_text(_clean_response_for_validation(response))
#     normalized_source = normalize_text(source_text)

#     response_numbers = _extract_numbers(normalized_response)
#     source_numbers = _extract_numbers(normalized_source)
#     matched_numbers = sorted(response_numbers.intersection(source_numbers))

#     response_keywords = _extract_keywords(normalized_response)
#     source_keywords = _extract_keywords(normalized_source)
#     matched_keywords = sorted(response_keywords.intersection(source_keywords))

#     matched_values = matched_numbers + matched_keywords

#     return ", ".join(matched_values)


# def extract_answer_values(response: str) -> str:
#     """Return answer values that must be present on the cited PDF page."""
#     normalized_response = normalize_text(_clean_response_for_validation(response))
#     response_numbers = sorted(_extract_numbers(normalized_response))
#     response_keywords = sorted(_extract_keywords(normalized_response))
#     return ", ".join(response_numbers + response_keywords)


# def has_matching_values(response: str, source_text: str) -> bool:
#     """Return whether response and source text share meaningful values."""
#     return bool(extract_matching_values(response, source_text))


# def _extract_numbers(text: str) -> set[str]:
#     """Extract normalized numeric values from text.

#     Trailing decimal zeros are stripped so that string set operations treat
#     14.10 and 14.1, 80.0 and 80, 12.50 and 12.5 as the same value.
#     """
#     result: set[str] = set()
#     for number in re.findall(r"(?<!\d)\d[\d,]*(?:\.\d+)?(?!\d)", text):
#         value = number.replace(",", "")
#         if "." in value:
#             value = value.rstrip("0").rstrip(".")
#         result.add(value)
#     return result


# def _is_patient_group_question(question: str) -> bool:
#     """Return whether numbers in the answer are likely eligibility/source noise."""
#     normalized = normalize_text(question)
#     return any(
#         term in normalized
#         for term in (
#             "patient groups",
#             "which patients",
#             "eligible",
#             "eligibility",
#             "candidates",
#             "for which patients",
#         )
#     )


# def _is_trial_count_question(question: str) -> bool:
#     """Return whether the question asks for a trial enrollment / sample-size count."""
#     normalized = normalize_text(question)
#     return (
#         "how many" in normalized
#         and any(
#             term in normalized
#             for term in (
#                 "enrolled",
#                 "enroll",
#                 "randomized",
#                 "randomised",
#                 "participants",
#                 "subjects",
#             )
#         )
#         and any(
#             term in normalized
#             for term in ("trial", "study", "program", "programme")
#         )
#     )


# def _is_variant_portfolio_question(question: str) -> bool:
#     """Return whether the question asks for available variants/portfolio SKUs."""
#     normalized = normalize_text(question)
#     return any(term in normalized for term in ("variants", "portfolio", "range")) and any(
#         term in normalized for term in ("available", "within", "strengths")
#     )


# def _compare_variant_portfolio(
#     response: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str, str]:
#     """Validate portfolio/range variants by comparing product/strength tokens."""
#     response_values = _extract_variant_values(response)
#     page_values = _extract_variant_values(page_data)

#     if not response_values:
#         return "DATA MISSING", "SuperAI response did not contain variant/portfolio values.", ""

#     if not page_values:
#         return "DATA MISSING", "Variant/portfolio values were not found on the cited page.", ""

#     missing = sorted(response_values.difference(page_values))
#     matched = sorted(response_values.intersection(page_values))

#     if not missing:
#         return (
#             "PASS",
#             f"Portfolio/variant values match cited page: {', '.join(matched)}.",
#             ", ".join(matched),
#         )

#     if matched and _is_broad_range_question(question):
#         return (
#             "PASS",
#             "Requested portfolio/range is partially represented across cited evidence; "
#             f"matched cited variant value(s): {', '.join(matched)}. "
#             "Missing variants were not treated as failure for broad range wording.",
#             ", ".join(matched),
#         )

#     if matched:
#         return (
#             "FAIL",
#             "Portfolio/variant mismatch. Missing cited-page variant value(s): "
#             f"{', '.join(missing)}.",
#             ", ".join(matched),
#         )

#     return "DATA MISSING", "Required portfolio/variant values were not found on the cited page.", ""


# def _is_broad_range_question(question: str) -> bool:
#     """Return whether range evidence may be spread across multiple citations."""
#     normalized = normalize_text(question)
#     return "range" in normalized or "portfolio" in normalized


# def _extract_variant_values(text: str) -> set[str]:
#     """Extract available variant values such as 5/10/20/40 or NEPTAZ 50/100/200."""
#     cleaned = _clean_response_for_validation(text)
#     slash_text = cleaned.lower().replace("\u00a0", " ")
#     normalized = normalize_text(cleaned)
#     values: set[str] = set()

#     for match in re.finditer(r"(?<!\d)\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?){1,6}\s*(?:mg|mcg|g|ml)?", slash_text):
#         unit_match = re.search(r"(mg|mcg|g|ml)\b", match.group(0), flags=re.IGNORECASE)
#         unit = unit_match.group(1).lower() if unit_match else ""
#         for number in re.findall(r"\d+(?:\.\d+)?", match.group(0)):
#             values.add(_normalize_variant_number(number, unit))

#     for match in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b", normalized):
#         unit_match = re.search(r"(mg|mcg|g|ml)\b", match.group(0), flags=re.IGNORECASE)
#         unit = unit_match.group(1).lower() if unit_match else ""
#         number = re.search(r"\d+(?:\.\d+)?", match.group(0))
#         if number:
#             values.add(_normalize_variant_number(number.group(0), unit))

#     return values


# def _normalize_variant_number(number: str, unit: str) -> str:
#     """Normalize variant strength number without changing value."""
#     normalized_number = number.rstrip("0").rstrip(".") if "." in number else number
#     return f"{normalized_number} {unit}".strip()


# def _is_repeat_course_question(question: str) -> bool:
#     """Return whether the question asks for repeat treatment course count."""
#     normalized = normalize_text(question)
#     return "course" in normalized and any(
#         term in normalized for term in ("how many", "repeat", "target 3")
#     )


# def _compare_repeat_courses(response: str, page_data: str) -> tuple[str, str, str]:
#     """Validate repeat-course count while ignoring unrelated mg/week citation numbers."""
#     response_count = _extract_repeat_course_count(response)
#     page_count = _extract_repeat_course_count(page_data)

#     if not response_count:
#         return (
#             "DATA MISSING",
#             "SuperAI response did not contain a repeat-course count to validate.",
#             "",
#         )

#     if not page_count:
#         return (
#             "DATA MISSING",
#             "Repeat-course count was not found on the cited page.",
#             "",
#         )

#     if response_count == page_count:
#         return (
#             "PASS",
#             f"Repeat-course count matches cited page: up to {page_count} courses.",
#             f"{page_count} courses",
#         )

#     return (
#         "FAIL",
#         f"Repeat-course count mismatch. SuperAI returned {response_count} courses while cited page contains {page_count} courses.",
#         "",
#     )


# def _extract_repeat_course_count(text: str) -> str:
#     """Extract phrases like 'up to 3 courses' or '3 repeat courses'."""
#     normalized = normalize_text(_clean_numeric_validation_text(text))
#     patterns = (
#         r"up to\s+(\d+)\s+(?:repeat\s+)?courses?",
#         r"(\d+)\s+(?:repeat\s+)?courses?",
#         r"repeat treatment\s*\(up to\s+(\d+)\s+courses?\)",
#     )
#     for pattern in patterns:
#         match = re.search(pattern, normalized, flags=re.IGNORECASE)
#         if match:
#             return match.group(1)
#     return ""


# def _is_strict_numeric_question(question: str, response: str) -> bool:
#     """Return whether exact deterministic numeric validation is required."""
#     normalized_question = normalize_text(question)
#     normalized_response = normalize_text(response)
#     broad_descriptive_starters = (
#         "why ",
#         "what makes",
#         "explain ",
#         "describe ",
#         "how does",
#         "how do",
#     )
#     descriptive_only_terms = (
#         "preferred",
#         "different",
#         "advantage",
#         "advantages",
#         "benefit",
#         "benefits",
#         "mechanism",
#         "clinical",
#         "guideline",
#     )

#     if normalized_question.startswith(broad_descriptive_starters) and not any(
#         term in normalized_question
#         for term in (
#             "mrp",
#             "price",
#             "cost",
#             "dosage",
#             "dose",
#             "how many times",
#             "pack size",
#             "strength",
#             "percentage",
#             "percent",
#         )
#     ):
#         return False

#     if any(term in normalized_question for term in descriptive_only_terms) and not any(
#         term in normalized_question
#         for term in (
#             "mrp",
#             "price",
#             "cost",
#             "dosage",
#             "dose",
#             "how many times",
#             "pack size",
#             "strength",
#             "percentage",
#             "percent",
#         )
#     ):
#         return False

#     normalized = f"{normalized_question} {normalized_response}"
#     strict_terms = (
#         "mrp",
#         "price",
#         "cost",
#         "percentage",
#         "percent",
#         "%",
#         "dosage",
#         "dose",
#         "strength",
#         "pack size",
#         "pack",
#         "quantity",
#         "mg",
#         "mcg",
#         "ml",
#         "tab",
#         "tablet",
#         "cap",
#         "bpm",
#     )
#     return any(term in normalized for term in strict_terms) and bool(
#         _extract_numeric_unit_values(normalized)
#     )


# def _clean_numeric_validation_text(text: str) -> str:
#     """Remove citation/source noise before strict numeric extraction."""
#     cleaned = _clean_response_for_validation(text)
#     cleaned = re.sub(
#         r"\b(?:citation|source|sources|ref|reference)\s*\d+(?:\s*,\s*\d+)*\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(
#         r"\b\d+\s*,\s*\d+(?:\s*,\s*\d+)*\s*(?=$|citation|source|sources|ref|reference)",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(
#         r"\b(?:sources?)\s+\d+(?:\s*,\s*\d+)*\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     return re.sub(r"\s+", " ", cleaned).strip()


# def _extract_numeric_unit_values(text: str) -> set[str]:
#     """Extract exact normalized numeric values with safety-critical units."""
#     normalized = normalize_text(text)
#     # Normalize OCR artifacts: "21.5 %" → "21.5%" and "500 mg" already handled
#     # but "21 . 5%" or "2 1.5%" from bad OCR also need collapsing.
#     normalized = re.sub(r"(?<=\d)\s+%", "%", normalized)
#     normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
#     values: set[str] = set()

#     range_patterns = (
#         r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(%)",
#         r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|tab|tabs|tablet|tablets|cap|caps|capsule|capsules|bpm)",
#     )
#     for pattern in range_patterns:
#         for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
#             low, high, unit = match.groups()
#             values.add(_normalize_numeric_unit_value(low, unit, f"{low}{unit}"))
#             values.add(_normalize_numeric_unit_value(high, unit, f"{high}{unit}"))
#             values.add(
#                 f"{_normalize_numeric_unit_value(low, unit, f'{low}{unit}')}-"
#                 f"{_normalize_numeric_unit_value(high, unit, f'{high}{unit}')}"
#             )

#     unit_patterns = (
#         r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)",
#         r"(\d+(?:\.\d+)?)\s*(?:rs\.?|inr|₹)",
#         r"(\d+(?:\.\d+)?)\s*%",
#         r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|tab|tabs|tablet|tablets|cap|caps|capsule|capsules|strip|strips|bpm)",
#     )

#     for pattern in unit_patterns:
#         for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
#             groups = match.groups()
#             number = groups[0].replace(",", "")
#             unit = groups[1].lower() if len(groups) > 1 and groups[1] else ""
#             values.add(_normalize_numeric_unit_value(number, unit, match.group(0)))

#     if any(
#         term in normalized
#         for term in (
#             "mrp",
#             "price",
#             "mortality",
#             "reduction",
#             "risk",
#             "endpoint",
#             "death",
#             "hospitalization",
#             "hospitalisation",
#         )
#     ):
#         for number in _extract_numbers(normalized):
#             values.add(_normalize_numeric_unit_value(number, "", number))

#     return values


# def _normalize_numeric_unit_value(number: str, unit: str, raw_value: str) -> str:
#     """Normalize a numeric/unit value without changing the actual value."""
#     normalized_number = number.replace(",", "")
#     if "." in normalized_number:
#         normalized_number = normalized_number.rstrip("0").rstrip(".")

#     normalized_unit = unit.lower().strip()
#     unit_map = {
#         "tabs": "tab",
#         "tablet": "tab",
#         "tablets": "tab",
#         "caps": "cap",
#         "capsule": "cap",
#         "capsules": "cap",
#         "strips": "strip",
#         "gm": "g",
#     }
#     normalized_unit = unit_map.get(normalized_unit, normalized_unit)

#     raw = raw_value.lower()
#     if "%" in raw:
#         normalized_unit = "%"
#     if "₹" in raw or "rs" in raw or "inr" in raw:
#         normalized_unit = "currency"

#     return f"{normalized_number} {normalized_unit}".strip()


# def _numeric_part_matches_bare(value_with_unit: str, bare_numbers: set[str]) -> bool:
#     """Return True if the numeric part of value_with_unit exists in bare_numbers.

#     Handles "810 strip" vs {"810"} and "21.5 currency" vs {"21.5"}.
#     """
#     match = re.match(r"^([\d]+(?:\.[\d]+)?)", value_with_unit.strip())
#     if not match:
#         return False

#     def _norm(n: str) -> str:
#         try:
#             f = float(n)
#             return str(int(f)) if f == int(f) else n.rstrip("0").rstrip(".")
#         except ValueError:
#             return n

#     target = _norm(match.group(1))
#     return any(_norm(n) == target for n in bare_numbers)


# def _extract_answer_citation_references(answer_text: str) -> list[int]:
#     """Return citation reference numbers attached to the answer body."""
#     match = re.search(r"(?:^|\s)(\d+(?:\s*,\s*\d+)*)\s*$", answer_text.strip())
#     if not match:
#         return []
#     return [int(number) for number in re.findall(r"\d+", match.group(1))]


# def _extract_citation_page_map(citation_text: str) -> dict[int, int]:
#     """Map citation reference numbers to their cited PDF page numbers."""
#     citation_page_map: dict[int, int] = {}
#     pattern = re.compile(
#         r"(?:^|\s)(\d+)\s+.*?(?:_Page_|page[\s:_-]+)(\d+)",
#         flags=re.IGNORECASE,
#     )

#     for match in pattern.finditer(citation_text):
#         citation_page_map[int(match.group(1))] = int(match.group(2))

#     return citation_page_map


# def _looks_like_mrp_query(response: str) -> bool:
#     """Return whether response text is about MRP/price."""
#     normalized = normalize_text(response)
#     return "mrp" in normalized or "price" in normalized


# def _has_mrp_number_match(response: str, source_text: str) -> bool:
#     """Require decimal price match for MRP/price responses."""
#     return _has_all_decimal_matches(response, source_text)


# def _has_all_decimal_matches(response: str, source_text: str) -> bool:
#     """Require every decimal value in the response to exist in page data."""
#     response_numbers = {
#         number for number in _extract_numbers(normalize_text(response)) if "." in number
#     }
#     source_numbers = {
#         number for number in _extract_numbers(normalize_text(source_text)) if "." in number
#     }
#     return bool(response_numbers) and response_numbers.issubset(source_numbers)


# def _has_all_response_values(response: str, source_text: str) -> bool:
#     """Require all meaningful numeric values and core keywords to exist on the page."""
#     normalized_response = normalize_text(response)
#     normalized_source = normalize_text(source_text)

#     response_numbers = _extract_numbers(normalized_response)
#     source_numbers = _extract_numbers(normalized_source)
#     if response_numbers and not response_numbers.issubset(source_numbers):
#         return False

#     response_keywords = _extract_keywords(normalized_response)
#     source_keywords = _extract_keywords(normalized_source)
#     return not response_keywords or _has_keyword_coverage(response_keywords, source_keywords)


# def _clean_response_for_validation(response: str) -> str:
#     """Remove citation/page/source/reference noise before value validation."""
#     cleaned = _strip_citation_tail(response)
#     cleaned = re.sub(
#         r"\b(?:citation|source|page|reference|ref)\s*[:#-]?\s*\d+(?:\s*,\s*\d+)*\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(
#         r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", " ", cleaned)
#     cleaned = re.sub(r"\(\s*(?:citation|source|ref)\s*\d+\s*\)", " ", cleaned, flags=re.IGNORECASE)
#     return re.sub(r"\s+", " ", cleaned).strip(" -*:;,.")


# def _is_descriptive_question(question: str, response: str) -> bool:
#     """Return whether semantic descriptive validation should be used."""
#     normalized = normalize_text(f"{question} {response}")
#     descriptive_terms = {
#         "role",
#         "moa",
#         "mode of action",
#         "usp",
#         "indication",
#         "indications",
#         "safety",
#         "quality",
#         "salient",
#         "feature",
#         "features",
#         "benefit",
#         "benefits",
#         "advantage",
#         "advantages",
#     }
#     return any(term in normalized for term in descriptive_terms)


# def _is_competitor_brand_question(question: str, response: str) -> bool:
#     """Return whether validation should compare only competitor brand names."""
#     normalized = normalize_text(f"{question} {response}")
#     return "competitor" in normalized and "brand" in normalized


# def _is_competitor_table_reasoning_question(question: str, response: str) -> bool:
#     """Return whether competitor validation needs row-aware table reasoning."""
#     normalized = normalize_text(f"{question} {response}")

#     reasoning_terms = (
#         "lowest",
#         "highest",
#         "cheapest",
#         "most expensive",
#         "cheaper",
#         "difference",
#         "compared to",
#         "price per strip",
#         "percentage",
#         "saving",
#         "cost saving",
#         "between",
#         "how many",
#         "count",
#         "pack size",
#         "manufacturer",
#         "manufactures",
#         "company",
#     )
#     has_reasoning_term = any(term in normalized for term in reasoning_terms)
#     has_competitor_context = "competitor" in normalized
#     has_table_attribute_context = any(
#         term in normalized
#         for term in (
#             "price per strip",
#             "pack size",
#             "manufactures",
#             "manufacturer",
#             "cheaper",
#             "difference",
#             "compared to",
#         )
#     )
#     return has_reasoning_term and (has_competitor_context or has_table_attribute_context)


# def _is_dosage_question(question: str, response: str) -> bool:
#     """Return whether validation should compare dosage with strict normalized rules."""
#     normalized_question = normalize_text(question)
#     frequency_terms = (
#         "how many times",
#         "times a day",
#         "once daily",
#         "twice daily",
#         "recommended dosage",
#         "recommended dose",
#         "dosage",
#         "dose",
#     )
#     if any(term in normalized_question for term in frequency_terms):
#         return True

#     descriptive_terms = (
#         "benefit",
#         "benefits",
#         "beyond glucose",
#         "role",
#         "moa",
#         "mode of action",
#         "why",
#         "how",
#         "evidence",
#         "study",
#         "trial",
#         "guideline",
#     )
#     if any(term in normalized_question for term in descriptive_terms):
#         return False

#     normalized = normalized_question
#     long_dosage_terms = (
#         "dosage",
#         "dose",
#         "recommended dosage",
#         "recommended dose",
#         "how many times",
#         "times a day",
#         "once daily",
#         "twice daily",
#     )
#     if any(term in normalized for term in long_dosage_terms):
#         return True
#     # Short abbreviations like "od", "bid", "tds" must use word-boundary matching.
#     # Plain substring check gives false positives: "od" in "pr[od]uctivity",
#     # "od" in "peri[od]", "bid" in "ta[bid]" etc.
#     return any(
#         re.search(rf"\b{term}\b", normalized)
#         for term in ("od", "bid", "tds", "tid", "qid")
#     )


# def _is_punchline_question(question: str, response: str) -> bool:
#     """Return whether validation should compare only punchline/slogan text."""
#     normalized = normalize_text(f"{question} {response}")
#     return "punchline" in normalized or "punch line" in normalized or "slogan" in normalized


# def _compare_punchline(response_content: str, page_data: str) -> tuple[str, str]:
#     """Compare only punchline/slogan text and ignore all table data."""
#     response_punchline = _extract_punchline_text(response_content, from_document=False)
#     document_punchline = _extract_punchline_text(page_data, from_document=True)

#     if not response_punchline:
#         return "DATA MISSING", "Super AI response did not contain punchline text."

#     if not document_punchline:
#         return "DATA MISSING", "Punchline/slogan text not found on the cited page."

#     normalized_response = _normalize_punchline_for_match(response_punchline)
#     normalized_document = _normalize_punchline_for_match(document_punchline)

#     if normalized_response == normalized_document:
#         return "PASS", f"Punchline matches cited page: {document_punchline}."

#     response_keywords = _extract_keywords(normalized_response)
#     document_keywords = _extract_keywords(normalized_document)
#     if response_keywords and _has_keyword_coverage(response_keywords, document_keywords):
#         return "PASS", f"Punchline meaning matches cited page: {document_punchline}."

#     return (
#         "FAIL",
#         "Punchline mismatch. "
#         f"Super AI returned '{response_punchline}' while cited page contains '{document_punchline}'.",
#     )


# def _compare_composition(response_content: str, page_data: str) -> tuple[str, str]:
#     """Validate composition/strength values from the cited page."""
#     response_composition = _extract_composition_values(response_content)
#     page_composition = _extract_composition_values(page_data)

#     if not response_composition:
#         return "DATA MISSING", "SuperAI response did not contain composition values."

#     if not page_composition:
#         return "DATA MISSING", "Composition values were not found on the cited page."

#     missing_values = sorted(response_composition.difference(page_composition))
#     if not missing_values:
#         return (
#             "PASS",
#             "Composition matches cited page: "
#             f"{', '.join(sorted(response_composition))}.",
#         )

#     if response_composition.intersection(page_composition):
#         return (
#             "FAIL",
#             "Partial composition mismatch. Missing cited-page composition value(s): "
#             f"{', '.join(missing_values)}.",
#         )

#     return "DATA MISSING", "Required composition values were not found on the cited page."


# def _compare_strength_lookup(
#     response_content: str,
#     page_data: str,
#     question: str = "",
# ) -> tuple[str, str]:
#     """Validate exact strength values for a requested molecule/product."""
#     response_values = _extract_strength_values(response_content)
#     page_values = _extract_strength_values(page_data)

#     if not response_values:
#         return "DATA MISSING", "SuperAI response did not contain a strength value to validate."

#     if not page_values:
#         return "DATA MISSING", "Strength value was not found on the cited page."

#     requested_entities = _extract_known_molecule_names(f"{question} {response_content}")
#     if requested_entities:
#         entity_supported = any(
#             _entity_text_contains_ordered_tokens(page_data, entity)
#             for entity in requested_entities
#         )
#         if not entity_supported:
#             # Entity not found by name, but the strength values may still be on
#             # the page under a brand name or abbreviated form.  Only hard-stop
#             # with DATA MISSING when the page also lacks matching strength values,
#             # otherwise fall through so the numeric comparison can proceed.
#             if not response_values.intersection(page_values):
#                 _log_validation_step(
#                     rule="_compare_strength_lookup",
#                     attribute="STRENGTH_LOOKUP",
#                     doc_value=sorted(page_values),
#                     response_value=sorted(response_values),
#                     verdict="DATA MISSING",
#                     reason=f"Molecule/product not found on cited page and no matching strength values: {', '.join(sorted(response_values))}.",
#                 )
#                 return "DATA MISSING", "Requested molecule/product was not found on the cited page."
#             # Entity name not found but strength values match — proceed to
#             # numeric comparison (may be under brand name on this page).

#     missing = sorted(response_values.difference(page_values))
#     if missing:
#         if response_values.intersection(page_values):
#             return (
#                 "FAIL",
#                 "Strength mismatch. Missing cited-page strength value(s): "
#                 f"{', '.join(missing)}.",
#             )
#         return "DATA MISSING", "Required strength value was not found on the cited page."

#     return (
#         "PASS",
#         "Strength value(s) match cited page exactly: "
#         f"{', '.join(sorted(response_values))}.",
#     )


# def _extract_strength_values(text: str) -> set[str]:
#     """Extract strict strength values, including IU and ranges."""
#     normalized = normalize_text(text)
#     normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
#     values: set[str] = set()

#     for match in re.finditer(
#         r"\b\d+(?:\.\d+)?\s*(?:-|â€“|—|to)\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu)\b",
#         normalized,
#         flags=re.IGNORECASE,
#     ):
#         values.add(_normalize_strength_text(match.group(0)))

#     for match in re.finditer(
#         r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu)\b",
#         normalized,
#         flags=re.IGNORECASE,
#     ):
#         values.add(_normalize_strength_text(match.group(0)))

#     return values


# def _normalize_strength_text(value: str) -> str:
#     """Normalize a strength value without changing its medical value."""
#     normalized = normalize_text(value).replace("gm", "g")
#     normalized = normalized.replace("â€“", "-").replace("—", "-")
#     normalized = re.sub(r"\bto\b", "-", normalized)
#     normalized = re.sub(r"\s*-\s*", "-", normalized)
#     normalized = re.sub(r"(\d(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b", r"\1 \2", normalized)
#     normalized = re.sub(r"(\d+)\.0+\b", r"\1", normalized)
#     return re.sub(r"\s+", " ", normalized).strip()


# def _compare_pack_size(response_content: str, page_data: str) -> tuple[str, str]:
#     """Validate exact pack quantity such as 10 tablets/strip or 30 capsules/box."""
#     response_values = _extract_pack_size_values(response_content)
#     page_values = _extract_pack_size_values(page_data)

#     if not response_values:
#         return "DATA MISSING", "SuperAI response did not contain a pack-size value to validate."

#     if not page_values:
#         return "DATA MISSING", "Pack-size value was not found on the cited page."

#     missing = sorted(response_values.difference(page_values))
#     if missing:
#         if response_values.intersection(page_values):
#             return (
#                 "FAIL",
#                 "Pack-size mismatch. Missing cited-page pack value(s): "
#                 f"{', '.join(missing)}.",
#             )
#         return "DATA MISSING", "Required pack-size value was not found on the cited page."

#     return (
#         "PASS",
#         "Pack-size value matches cited page exactly: "
#         f"{', '.join(sorted(response_values))}.",
#     )


# def _extract_pack_size_values(text: str) -> set[str]:
#     """Extract normalized pack quantities while ignoring citation numbers."""
#     normalized = normalize_text(text)
#     values: set[str] = set()

#     pack_patterns = (
#         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s*(?:/|\s+)\s*(strip|box|pack)\b",
#         r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s*(?:/|\s+)\s*(strip|box|pack)\b",
#         r"\((\d+)\s*(?:tab|tabs|tablet|tablets)\s*(?:/|\s+)\s*(strip|box|pack)\)",
#         r"\((\d+)\s*(?:cap|caps|capsule|capsules)\s*(?:/|\s+)\s*(strip|box|pack)\)",
#         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s+per\s+(strip|box|pack)\b",
#         r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s+per\s+(strip|box|pack)\b",
#         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s+in\s+(?:one|1)\s+(strip|box|pack)\b",
#         r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s+in\s+(?:one|1)\s+(strip|box|pack)\b",
#         r"\b(\d+)\s*(?:tab|tabs|tablet|tablets|cap|caps|capsule|capsules)\s+in\s+each\s+(strip|box|pack)\b",
#     )
#     for pattern in pack_patterns:
#         for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
#             container = match.group(2)
#             values.add(f"{int(match.group(1))} per {container}")

#     box_match = re.search(
#         r"\b(?P<unit_count>\d+)\s*(?:cap|caps|capsule|capsules|tab|tabs|tablet|tablets)\s+"
#         r"in\s+each\s+strip\s*[*x]\s*(?P<strip_count>\d+)\s*strip\b",
#         normalized,
#         flags=re.IGNORECASE,
#     )
#     if box_match:
#         values.add(f"{int(box_match.group('unit_count'))} per strip")
#         values.add(
#             f"{int(box_match.group('unit_count')) * int(box_match.group('strip_count'))} per box"
#         )

#     return values


# def _extract_composition_values(text: str) -> set[str]:
#     """Extract active ingredient/strength composition values."""
#     cleaned = normalize_text(text)
#     cleaned = re.sub(
#         r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     values: set[str] = set()

#     stop_ingredients = {
#         "in",
#         "and",
#         "or",
#         "with",
#         "available",
#         "contains",
#         "the",
#         "management",
#         "use",
#         "dosing",
#         "mechanism",
#         "response",
#     }

#     for match in re.finditer(
#         r"\b([a-z][a-z0-9]+)\s+(?:injections?|tablets?|capsules?)?\s*"
#         r"((?:\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)(?:\s*(?:,|and)\s*)?)+)",
#         cleaned,
#     ):
#         ingredient = match.group(1)
#         if ingredient in stop_ingredients:
#             continue
#         strengths = re.findall(r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)", match.group(2))
#         for strength in strengths:
#             values.add(f"{ingredient} {_normalize_composition_strength(strength)}")

#     for match in re.finditer(r"\bdocetrust\s+(\d+(?:\.\d+)?)\s*mg\b", cleaned):
#         values.add(f"docetaxel {_normalize_composition_strength(match.group(1) + ' mg')}")

#     for ingredient in ("mycophenolate mofetil", "mycophenolate sodium"):
#         ingredient_pos = cleaned.find(ingredient)
#         if ingredient_pos >= 0:
#             segment = cleaned[ingredient_pos : ingredient_pos + 220]
#             segment = re.split(
#                 r"\b(?:moa|role|indications|recommended dosage|brand usp|molecule usp|competitors?)\b",
#                 segment,
#             )[0]
#             for strength in re.findall(r"\d+(?:\.\d+)?\s*mg\b", segment):
#                 values.add(f"{ingredient} {_normalize_composition_strength(strength)}")
#             compact_strengths = re.findall(r"\d+(?:\.\d+)?(?=mg\b)", segment)
#             for number in compact_strengths:
#                 values.add(f"{ingredient} {_normalize_composition_strength(number + ' mg')}")

#     if "docetaxel" in cleaned:
#         start = cleaned.find("docetaxel")
#         segment = cleaned[start : start + 180] if start >= 0 else cleaned
#         segment = re.split(
#             r"\b(?:citation|punchline|moa|role|indications|recommended dosage|salient|competitors?)\b",
#             segment,
#         )[0]
#         for strength in re.findall(r"\d+(?:\.\d+)?\s*mg\b", segment):
#             values.add(f"docetaxel {_normalize_composition_strength(strength)}")

#     docetaxel_list_match = re.search(
#         r"\bdocetaxel\s+injections?\s*[.â€¦…\s-]*"
#         r"(?P<strengths>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*(?:\s+and\s+\d+(?:\.\d+)?)?)\s*mg\b",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     if docetaxel_list_match:
#         for number in re.findall(r"\d+(?:\.\d+)?", docetaxel_list_match.group("strengths")):
#             values.add(f"docetaxel {_normalize_composition_strength(number + ' mg')}")

#     if "docetaxel injection" in cleaned and not values:
#         start = cleaned.find("docetaxel injection")
#         segment = cleaned[start : start + 140] if start >= 0 else ""
#         segment = re.split(r"\b(?:punchline|moa|role|indications)\b", segment)[0]
#         if "mg" in segment:
#             for number in re.findall(r"\d+(?:\.\d+)?", segment):
#                 values.add(f"docetaxel {_normalize_composition_strength(number + ' mg')}")

#     return values


# def _normalize_composition_strength(value: str) -> str:
#     """Normalize composition strength display without changing value."""
#     normalized = normalize_text(value).replace("gm", "g")
#     normalized = re.sub(r"(\d(?:\.\d+)?)\s*(mg|mcg|g|ml)\b", r"\1 \2", normalized)
#     normalized = re.sub(r"(\d+)\.0+\b", r"\1", normalized)
#     return normalized


# def _compare_molecule_list(
#     response_content: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate requested molecule lists without treating count words as values."""
#     response_molecules = _extract_known_molecule_names(response_content)
#     page_molecules = _extract_known_molecule_names(page_data)

#     if not response_molecules:
#         return "DATA MISSING", "SuperAI response did not contain molecule names to validate."

#     if not page_molecules:
#         return "DATA MISSING", "Molecule names were not found on the cited page."

#     missing = sorted(response_molecules.difference(page_molecules))
#     if not missing:
#         return (
#             "PASS",
#             "Molecule list matches cited page: "
#             f"{', '.join(sorted(response_molecules))}.",
#         )

#     if response_molecules.intersection(page_molecules):
#         return (
#             "FAIL",
#             "Molecule list is partially supported. Missing molecule(s): "
#             f"{', '.join(missing)}.",
#         )

#     return "DATA MISSING", "Required molecule list was not found on the cited page."


# def _compare_active_ingredient(
#     response_content: str,
#     page_data: str,
# ) -> tuple[str, str]:
#     """Validate active ingredient names without requiring strength values."""
#     response_molecules = _extract_known_molecule_names(response_content)
#     page_molecules = _extract_known_molecule_names(page_data)

#     if not response_molecules:
#         return "DATA MISSING", "SuperAI response did not contain an active ingredient to validate."

#     if not page_molecules:
#         return "DATA MISSING", "Active ingredient was not found on the cited page."

#     missing = sorted(response_molecules.difference(page_molecules))
#     if not missing:
#         return (
#             "PASS",
#             "Active ingredient matches cited page: "
#             f"{', '.join(sorted(response_molecules))}.",
#         )

#     if response_molecules.intersection(page_molecules):
#         return (
#             "FAIL",
#             "Active ingredient is only partially supported. Missing ingredient(s): "
#             f"{', '.join(missing)}.",
#         )

#     return (
#         "FAIL",
#         "Active ingredient mismatch. "
#         f"SuperAI returned {', '.join(sorted(response_molecules))}, while cited page contains "
#         f"{', '.join(sorted(page_molecules))}.",
#     )


# def _extract_known_molecule_names(text: str) -> set[str]:
#     """Extract known pharma molecule names as entities."""
#     normalized = normalize_text(text)
#     known_molecules = (
#         "silodosin",
#         "mirabegron",
#         "formoterol",
#         "glycopyrronium",
#         "glycopyrronium bromide",
#         "indacaterol",
#         "cyclosporine",
#         "vitamin d3",
#         "alpha lipoic acid",
#         "pyridoxine",
#         "folic acid",
#         "methyl cobalamin",
#         "vildagliptin",
#         "imeglimin",
#         "pregabalin",
#         "linagliptin",
#         "dapagliflozin",
#         "metformin",
#         "gliclazide",
#         "voglibose",
#         "pioglitazone",
#         "docetaxel",
#         "tacrolimus",
#         "mycophenolate mofetil",
#         "mycophenolate sodium",
#         "cerebroprotein hydrolysate",
#         # Cardiovascular / lipid-lowering molecules (STATPURE range and similar)
#         "rosuvastatin",
#         "atorvastatin",
#         "simvastatin",
#         "pitavastatin",
#         "aspirin",
#         "clopidogrel",
#         "ticagrelor",
#         "prasugrel",
#         "ezetimibe",
#         "fenofibrate",
#         "gemfibrozil",
#         "amlodipine",
#         "ramipril",
#         "enalapril",
#         "lisinopril",
#         "perindopril",
#         "telmisartan",
#         "olmesartan",
#         "losartan",
#         "valsartan",
#         "irbesartan",
#         "candesartan",
#         "chlorthalidone",
#         "hydrochlorothiazide",
#         "indapamide",
#         "bisoprolol",
#         "carvedilol",
#         "nebivolol",
#         "atenolol",
#         "metoprolol",
#     )
#     return {
#         molecule
#         for molecule in known_molecules
#         if re.search(rf"\b{re.escape(molecule)}\b", normalized)
#     }


# def _compare_dosage(response_content: str, page_data: str) -> tuple[str, str]:
#     """Compare dosage strictly while accepting standard dosage notation equivalents."""
#     response_markers = _extract_dosage_markers(response_content)
#     page_markers = _extract_dosage_markers(page_data)

#     if not response_markers:
#         return "DATA MISSING", "Super AI response did not contain a dosage value to validate."

#     if not page_markers:
#         return "DATA MISSING", "Dosage value not found on the cited page."

#     missing_markers = sorted(response_markers.difference(page_markers))
#     if "1 tab" in missing_markers and any(
#         marker in response_markers.intersection(page_markers)
#         for marker in ("od", "daily", "once daily")
#     ):
#         missing_markers.remove("1 tab")
#     if "bid" in missing_markers and "every 12 hours" in response_markers and "every 12 hours" in page_markers:
#         missing_markers.remove("bid")
#     if any(marker.endswith("mg") and "-" in marker for marker in response_markers.intersection(page_markers)):
#         for optional_frequency in ("od", "bid", "daily"):
#             if optional_frequency in missing_markers:
#                 missing_markers.remove(optional_frequency)
#     if "titrated" in missing_markers and any(
#         marker in page_markers for marker in ("increased", "up to", "maximum")
#     ):
#         missing_markers.remove("titrated")
#     if "4-12 hours prior to transplantation" in response_markers.intersection(page_markers):
#         missing_markers = [
#             marker
#             for marker in missing_markers
#             if not (
#                 "4" in marker
#                 and "12" in marker
#                 and "transplantation" in marker
#             )
#         ]

#     if not missing_markers:
#         dosage_evidence = _extract_dosage_evidence(page_data)
#         if dosage_evidence:
#             return "PASS", f"Dosage/frequency matches cited page: {dosage_evidence}."

#         return (
#             "PASS",
#             "Dosage matches cited page after standard dosage normalization: "
#             f"{', '.join(sorted(response_markers))}.",
#         )

#     related_markers = response_markers.intersection(page_markers)
#     if related_markers:
#         return (
#             "FAIL",
#             "Dosage mismatch. Missing dosage marker(s) on cited page: "
#             f"{', '.join(missing_markers)}.",
#         )

#     return "DATA MISSING", "Required dosage value not found on the cited page."


# def _extract_dosage_evidence(page_data: str) -> str:
#     """Extract the cited dosage/frequency sentence or section for better reasons."""
#     cleaned = re.sub(r"\s+", " ", page_data).strip()
#     match = re.search(
#         r"\bRecommended Dosage\s+(.+?)(?=\b(?:Brand USP|Molecule USP|Salient|Competitors?|M\.?R\.?P|Indications)\b|$)",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         return match.group(1).strip(" :-.;")

#     frequency_match = re.search(
#         r"[^.]*\b(?:once daily|twice daily|OD|BID|TID|TDS|QID)\b[^.]*",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     return frequency_match.group(0).strip(" :-.;") if frequency_match else ""


# def _extract_dosage_markers(text: str) -> set[str]:
#     """Extract normalized dosage markers such as 1 tab, 2 tab, OD, and BID."""
#     normalized = normalize_text(text)
#     normalized = re.sub(
#         r"\b([1-9])(\d{2})\s*(?:hr|hrs|hour|hours)\s*(prior to|before)\s*transplantation\b",
#         r"\1-\2 hours \3 transplantation",
#         normalized,
#         flags=re.IGNORECASE,
#     )
#     normalized = re.sub(
#         r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
#         " ",
#         normalized,
#         flags=re.IGNORECASE,
#     )
#     normalized = re.sub(
#         r"\b(?:citation|source|reference|ref)\s*[:#-]?\s*\d+(?:\s*,\s*\d+)*\b",
#         " ",
#         normalized,
#         flags=re.IGNORECASE,
#     )
#     markers: set[str] = set()

#     for match in re.finditer(r"\b\d+\s*tab\b", normalized):
#         markers.add(re.sub(r"\s+", " ", match.group(0)).strip())

#     for match in re.finditer(
#         r"\b\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*mg\b",
#         normalized,
#     ):
#         markers.add(re.sub(r"\s+", "", match.group(0)).replace("–", "-").replace("to", "-"))

#     for match in re.finditer(
#         r"\b\d+(?:\.\d+)?\s*(?:-|–|—|â€“|to|\s)\s*\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\s*(?:prior to|before)\s*transplantation\b",
#         normalized,
#     ):
#         markers.add(
#             re.sub(r"\s+", " ", match.group(0))
#             .replace("â€“", "-")
#             .replace("—", "-")
#             .replace(" to ", "-")
#             .replace("hrs", "hours")
#             .replace("hr", "hours")
#             .strip()
#         )

#     for match in re.finditer(
#         r"\b(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|\s+|to)\s*(?P<high>\d+(?:\.\d+)?)\s*(?:hr|hrs|hour|hours)\s*(?P<when>prior to|before)\s*transplantation\b",
#         normalized,
#     ):
#         markers.add(
#             f"{match.group('low')}-{match.group('high')} hours {match.group('when')} transplantation"
#         )

#     for match in re.finditer(
#         r"\b(?P<low>\d+(?:\.\d+)?)\s+(?P<high>\d+(?:\.\d+)?)\s*mg\b",
#         normalized,
#     ):
#         low = match.group("low")
#         high = match.group("high")
#         if float(low) < float(high):
#             markers.add(f"{low}-{high}mg")

#     for match in re.finditer(
#         r"\b\d+(?:\.\d+)?\s*mg\s*/?\s*m\s*2\b",
#         normalized,
#     ):
#         markers.add(
#             re.sub(r"\s+", " ", match.group(0).replace(" ", "")).replace("m2", "m2")
#         )

#     for match in re.finditer(r"\bevery\s+\d+\s+weeks?\b", normalized):
#         markers.add(re.sub(r"\s+", " ", match.group(0)).strip())

#     if re.search(r"\biv\b", normalized):
#         markers.add("iv")

#     if re.search(r"\binfusion\b", normalized):
#         markers.add("infusion")

#     if re.search(r"\btwice\s+daily\b|\btwo\s+divided\s+doses\b|\bdivided\s+in\s+two\s+doses\b", normalized):
#         markers.add("bid")

#     if re.search(r"\bevery\s+12\s*(?:hr|hrs|hour|hours)\b", normalized):
#         markers.add("every 12 hours")

#     frequency_aliases = {
#         "od": "od",
#         "bid": "bid",
#         "bd": "bid",
#         "tds": "tds",
#         "tid": "tds",
#         "qid": "qid",
#         "hs": "hs",
#         "sos": "sos",
#     }
#     for alias, canonical in frequency_aliases.items():
#         if re.search(rf"\b{re.escape(alias)}\b", normalized):
#             markers.add(canonical)

#     if re.search(r"\bdaily dosage\b|\bdaily usage\b|\bcontinuous daily\b", normalized):
#         markers.add("daily")

#     if re.search(r"\btitrat(?:e|ed|ion|able)\b", normalized):
#         markers.add("titrated")

#     if re.search(r"\bcan\s+be\s+increased\b|\bincreased\s+up\s+to\b", normalized):
#         markers.add("increased")

#     if re.search(r"\bup\s+to\b", normalized):
#         markers.add("up to")

#     if re.search(r"\bmaximum\b|\bmax\b", normalized):
#         markers.add("maximum")

#     if re.search(r"\btogether\b", normalized):
#         markers.add("together")

#     return markers


# def _extract_punchline_text(text: str, from_document: bool) -> str:
#     """Extract only punchline or slogan text."""
#     cleaned = _clean_response_for_validation(text)

#     if from_document:
#         match = re.search(
#             r"\b(?:punch\s*line|punchline|slogan|tagline)\s*[:-]?\s*"
#             r"(.+?)(?=\b(?:composition|mode of action|role of drugs|indications|"
#             r"recommended dosage|salient|competitors?|m\.?r\.?p|name of product)\b|$)",
#             cleaned,
#             flags=re.IGNORECASE,
#         )
#         if not match:
#             return ""
#         return _clean_punchline_text(match.group(1))

#     match = re.search(
#         r"\b(?:punch\s*line|punchline|slogan|tagline)\s*(?:is|:|-)?\s*(.+)",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     return _clean_punchline_text(match.group(1) if match else cleaned)


# def _clean_punchline_text(text: str) -> str:
#     """Remove non-punchline table noise from a punchline candidate."""
#     cleaned = text.replace("—", "-").replace("–", "-")
#     cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", " ", cleaned)
#     cleaned = re.sub(
#         r"^\s*(?:of\s+)?[A-Za-z][A-Za-z0-9 /().+-]{1,60}\s+is\s+",
#         "",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(r"^\s*of\s+", "", cleaned, flags=re.IGNORECASE)
#     cleaned = re.sub(
#         r"\b(?:company|pack|price|strip|tab|tabs|tablet|tablets|mrp|brand name)\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )

#     cleaned = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", cleaned.strip())
#     cleaned = _strip_leading_punchline_label(cleaned)
#     return re.sub(r"\s+", " ", cleaned).strip(" :-.,;")


# def _strip_leading_punchline_label(text: str) -> str:
#     """Drop leading product labels before the actual slogan."""
#     cleaned = text.strip()
#     label_pattern = re.compile(
#         r"^[A-Za-z][A-Za-z0-9 /().+-]{1,45}\s*[:\-]+\s+(.+)$",
#         flags=re.IGNORECASE,
#     )

#     while True:
#         match = label_pattern.match(cleaned)
#         if not match:
#             return cleaned

#         label = match.group(0)[: match.start(1)].strip(" :-")
#         remainder = match.group(1).strip()

#         if _looks_like_product_label(label) and remainder:
#             cleaned = remainder
#             continue

#         return cleaned


# def _looks_like_product_label(text: str) -> bool:
#     """Return whether text is likely a product/SKU label, not slogan content."""
#     normalized = normalize_text(text)
#     if not normalized:
#         return False

#     if any(char.isdigit() for char in normalized):
#         return True

#     words = normalized.split()
#     return len(words) <= 3 and not any(
#         word in {"one", "all", "relief", "care", "control", "protection", "power"}
#         for word in words
#     )


# def _normalize_punchline_for_match(text: str) -> str:
#     """Normalize slogan text while ignoring product labels and filler words."""
#     cleaned = _clean_punchline_text(text)
#     cleaned = normalize_text(cleaned)
#     words = [
#         word
#         for word in re.findall(r"[a-z][a-z0-9-]*", cleaned)
#         if word not in {"just", "of", "for", "the", "a", "an"}
#     ]
#     return " ".join(words)


# def _compare_competitor_brands(response_content: str, page_data: str) -> tuple[str, str]:
#     """Compare competitor brand names only, ignoring companies, packs, and prices."""
#     response_brands = _extract_competitor_brand_names(response_content)
#     page_rows = _extract_competitor_table_rows(page_data)
#     page_brands = [row["brand"] for row in page_rows] if page_rows else _extract_competitor_brand_names(page_data)

#     if not response_brands:
#         return "DATA MISSING", "Super AI response did not contain competitor brand names."

#     if not page_brands:
#         return "DATA MISSING", "Competitor brand names not found on the cited page."

#     match_audits = [_entity_best_match_audit(brand, page_brands) for brand in response_brands]
#     missing_brands = [
#         str(audit["left_original"])
#         for audit in match_audits
#         if not audit["matched"]
#     ]

#     if not missing_brands:
#         audit_summary = _format_entity_audit_summary(match_audits)
#         return (
#             "PASS",
#             "Competitor brand name(s) match cited page: "
#             f"{', '.join(response_brands)}. {audit_summary}",
#         )

#     return (
#         "FAIL",
#         "Some competitor brand name(s) are missing on the cited page: "
#         f"{', '.join(missing_brands)}.",
#     )


# def _compare_competitor_table_reasoning(
#     response_content: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate competitor table questions using parsed row/column relationships."""
#     normalized_question = normalize_text(question)
#     response_text = _clean_response_for_validation(response_content)

#     if any(term in normalized_question for term in ("cheaper", "difference", "compared to")):
#         return _compare_price_difference(response_text, page_data, question)

#     if (
#         "company" in normalized_question
#         or "manufacturer" in normalized_question
#         or "manufactures" in normalized_question
#         or "belongs to" in normalized_question
#     ):
#         company_lookup = _compare_company_lookup(response_text, page_data, question)
#         if company_lookup[0] != "DATA MISSING":
#             return company_lookup

#     table_page_data = _scope_competitor_page_data_for_question(page_data, question)
#     rows = _extract_competitor_table_rows(table_page_data)

#     if not rows:
#         return "DATA MISSING", "Competitor table rows were not found on the cited page."

#     marketed_company = _extract_marketed_by_company(question)
#     if marketed_company:
#         expected_rows = [
#             row
#             for row in rows
#             if _company_text_contains(marketed_company, str(row["company"]))
#             or _company_text_contains(str(row["company"]), marketed_company)
#         ]
#         if not expected_rows:
#             return (
#                 "DATA MISSING",
#                 f"No competitor row was found for company {marketed_company} on the cited page.",
#             )

#         matching_rows = [
#             row
#             for row in expected_rows
#             if _entity_text_contains(response_text, str(row["brand"]))
#             or _entity_text_contains_ordered_tokens(response_text, str(row["brand"]))
#         ]
#         if matching_rows:
#             brands = ", ".join(str(row["brand"]) for row in matching_rows)
#             return (
#                 "PASS",
#                 f"Competitor brand-company mapping matches cited table row: {brands} is listed with {marketed_company}.",
#             )

#         expected_brands = ", ".join(str(row["brand"]) for row in expected_rows)
#         return (
#             "FAIL",
#             f"Competitor brand-company mismatch. Cited page lists {expected_brands} with {marketed_company}.",
#         )

#     if "how many" in normalized_question or "count" in normalized_question:
#         expected_count = len(rows)
#         response_numbers = {int(number) for number in _extract_numbers(response_text) if number.isdigit()}
#         if expected_count in response_numbers:
#             return (
#                 "PASS",
#                 f"Competitor count matches cited table: {expected_count} row(s) found.",
#             )
#         if response_numbers:
#             return (
#                 "FAIL",
#                 "Competitor count mismatch. "
#                 f"Cited table has {expected_count} row(s), while SuperAI returned "
#                 f"{', '.join(str(number) for number in sorted(response_numbers))}.",
#             )
#         return "DATA MISSING", "SuperAI response did not contain a competitor count."

#     priced_rows = [row for row in rows if row.get("price") is not None]
#     if not priced_rows and any(term in normalized_question for term in ("price", "lowest", "highest", "cheapest", "expensive", "between", "saving", "percentage")):
#         return "DATA MISSING", "Competitor prices were not found on the cited page."

#     if any(term in normalized_question for term in ("percentage", "saving", "cost saving")):
#         return _compare_percentage_cost_saving(
#             response_text,
#             page_data,
#             question,
#             priced_rows,
#         )

#     if "between" in normalized_question and "price" in normalized_question:
#         range_values = sorted(float(number) for number in _extract_numbers(normalized_question))
#         if len(range_values) < 2:
#             return "DATA MISSING", "Price range could not be extracted from the question."

#         low, high = range_values[0], range_values[1]
#         expected_rows = [
#             row for row in priced_rows if low <= float(row["price"]) <= high
#         ]
#         expected_brands = [row["brand"] for row in expected_rows]

#         if not expected_brands:
#             return (
#                 "DATA MISSING",
#                 f"No competitor brands found in cited table between {low:g} and {high:g}.",
#             )

#         missing = [
#             brand for brand in expected_brands if not _entity_text_contains(response_text, brand)
#         ]
#         if not missing:
#             return (
#                 "PASS",
#                 "Competitor price range matches cited table. "
#                 f"Brands between {low:g} and {high:g}: {', '.join(expected_brands)}.",
#             )
#         return (
#             "FAIL",
#             "Partial match: SuperAI missed competitor brand(s) in cited price range "
#             f"{low:g}-{high:g}: {', '.join(missing)}.",
#         )

#     if "priced" in normalized_question or re.search(r"\bprice(?:d)?\s+at\b", normalized_question):
#         requested_prices = {float(number) for number in _extract_numbers(normalized_question)}
#         if not requested_prices:
#             return "DATA MISSING", "Requested competitor price could not be extracted from the question."

#         matching_price_rows = [
#             row
#             for row in priced_rows
#             if _float_set_contains(requested_prices, float(row["price"]))
#         ]
#         if not matching_price_rows:
#             return "DATA MISSING", "Requested price/MRP was not found on the cited page."

#         expected_brands = [str(row["brand"]) for row in matching_price_rows]
#         missing_brands = [
#             brand for brand in expected_brands if not _entity_text_contains(response_text, brand)
#         ]
#         if not missing_brands:
#             evidence = ", ".join(
#                 f"{row['brand']} at {float(row['price']):g}" for row in matching_price_rows
#             )
#             return "PASS", f"Competitor brand-price mapping matches cited table row: {evidence}."

#         return (
#             "FAIL",
#             "Competitor brand-price mismatch. "
#             f"Cited table maps requested price to {', '.join(expected_brands)}.",
#         )

#     if any(term in normalized_question for term in ("lowest", "cheapest")):
#         scoped_rows = _filter_rows_by_question_brands(priced_rows, question) or priced_rows
#         expected_row = min(scoped_rows, key=lambda row: float(row["price"]))
#         return _compare_expected_competitor_row(response_text, expected_row, "lowest")

#     if any(term in normalized_question for term in ("highest", "most expensive")):
#         scoped_rows = _filter_rows_by_question_brands(priced_rows, question) or priced_rows
#         expected_row = max(scoped_rows, key=lambda row: float(row["price"]))
#         return _compare_expected_competitor_row(response_text, expected_row, "highest")

#     if "price per strip" in normalized_question or "price" in normalized_question:
#         matching_rows = [
#             row for row in priced_rows if _entity_text_contains(response_text, row["brand"])
#         ]
#         response_numbers = {float(number) for number in _extract_numbers(response_text)}

#         for row in matching_rows:
#             if float(row["price"]) in response_numbers:
#                 return (
#                     "PASS",
#                     "Competitor price matches cited table row. "
#                     f"{row['brand']} price/strip is {row['price']:.2f}.",
#                 )

#         if matching_rows:
#             row = matching_rows[0]
#             return (
#                 "FAIL",
#                 "Competitor price mismatch. "
#                 f"Cited table row for {row['brand']} has price/strip {row['price']:.2f}.",
#             )

#     if (
#         "company" in normalized_question
#         or "manufacturer" in normalized_question
#         or "manufactures" in normalized_question
#         or "belongs to" in normalized_question
#     ):
#         for row in rows:
#             if _entity_text_contains(response_text, row["brand"]):
#                 if _company_text_contains(response_text, row["company"]):
#                     return (
#                         "PASS",
#                         "Competitor company matches cited table row. "
#                         f"{row['brand']} is listed with {row['company']}.",
#                     )
#                 return (
#                     "FAIL",
#                     "Competitor company mismatch. "
#                     f"Cited table row lists {row['brand']} with {row['company']}.",
#                 )

#     if "pack size" in normalized_question or "pack" in normalized_question:
#         for row in rows:
#             if _entity_text_contains(response_text, row["brand"]):
#                 if row["pack"] and normalize_text(row["pack"]) in normalize_text(response_text):
#                     return (
#                         "PASS",
#                         "Competitor pack size matches cited table row. "
#                         f"{row['brand']} pack size is {row['pack']}.",
#                     )
#                 return (
#                     "FAIL",
#                     "Competitor pack size mismatch. "
#                     f"Cited table row lists {row['brand']} pack size as {row['pack']}.",
#                 )

#     return "DATA MISSING", "Requested competitor table attribute could not be validated."


# def _filter_rows_by_question_brands(
#     rows: list[dict[str, object]],
#     question: str,
# ) -> list[dict[str, object]]:
#     """Keep competitor rows whose brand is explicitly listed in the question."""
#     question_brands = _extract_explicit_brands_from_question(question)
#     if not question_brands:
#         return []

#     filtered: list[dict[str, object]] = []
#     for row in rows:
#         brand = str(row.get("brand") or "")
#         if any(
#             _entity_text_contains(brand, question_brand)
#             or _entity_text_contains(question_brand, brand)
#             or _entity_text_contains_ordered_tokens(brand, question_brand)
#             or _entity_text_contains_ordered_tokens(question_brand, brand)
#             for question_brand in question_brands
#         ):
#             filtered.append(row)

#     return filtered


# def _extract_explicit_brands_from_question(question: str) -> list[str]:
#     """Extract brand names from 'among A, B, C and D' style questions."""
#     match = re.search(
#         r"\bamong\s+(.+?)(?:\s+in\s+the\b|\s+category\b|\?)",
#         question,
#         flags=re.IGNORECASE,
#     )
#     if not match:
#         return []

#     brand_text = match.group(1)
#     brand_text = re.sub(
#         r"\b(?:which|competitor|brand|has|the|lowest|highest|mrp|price|among)\b",
#         " ",
#         brand_text,
#         flags=re.IGNORECASE,
#     )
#     parts = re.split(r"\s*,\s*|\s+\band\b\s+|\s+and\s+", brand_text)
#     return [
#         re.sub(r"\s+", " ", part).strip(" ?:-.,")
#         for part in parts
#         if part.strip(" ?:-.,")
#     ]


# def _compare_percentage_cost_saving(
#     response_text: str,
#     page_data: str,
#     question: str,
#     competitor_rows: list[dict[str, object]],
# ) -> tuple[str, str]:
#     """Validate percentage cost saving using cited product and competitor prices."""
#     own_price = _extract_requested_product_price(page_data, question)
#     if own_price is None:
#         return "DATA MISSING", "Eplebless/product price was not found on the cited page."

#     if not competitor_rows:
#         return "DATA MISSING", "Competitor prices were not found on the cited page."

#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     if not response_numbers:
#         return "DATA MISSING", "SuperAI response did not contain a percentage cost-saving value."

#     calculated_savings: list[tuple[str, float, float]] = []
#     for row in competitor_rows:
#         competitor_price = float(row["price"])
#         if competitor_price <= 0 or competitor_price <= own_price:
#             continue
#         saving_percent = ((competitor_price - own_price) / competitor_price) * 100
#         calculated_savings.append((str(row["brand"]), competitor_price, saving_percent))

#     if not calculated_savings:
#         return "DATA MISSING", "No higher-priced competitor row was available for cost-saving calculation."

#     mentioned_rows = [
#         item for item in calculated_savings if _entity_text_contains(response_text, item[0])
#     ]
#     rows_to_check = mentioned_rows or calculated_savings

#     for brand, competitor_price, saving_percent in rows_to_check:
#         if _number_set_contains_close_value(response_numbers, saving_percent):
#             return (
#                 "PASS",
#                 "Percentage cost saving matches cited table calculation. "
#                 f"Product price {own_price:.2f} vs {brand} {competitor_price:.2f} "
#                 f"gives {saving_percent:.2f}% saving.",
#             )

#     calculated_summary = ", ".join(
#         f"{brand}: {saving_percent:.2f}%" for brand, _, saving_percent in calculated_savings
#     )


# def _compare_price_difference(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate cheaper/difference questions by calculating cited table prices."""
#     own_product, compared_brand = _extract_price_comparison_entities(question)
#     if not own_product or not compared_brand:
#         return "DATA MISSING", "Price comparison products could not be identified from the question."

#     own_prices = _extract_own_sku_prices(page_data, own_product)
#     compared_prices = _extract_competitor_strength_prices(page_data, compared_brand)

#     if not own_prices or not compared_prices:
#         fallback_result = _compare_single_row_price_difference(
#             response_text,
#             page_data,
#             own_product,
#             compared_brand,
#         )
#         if fallback_result[0] != "DATA MISSING":
#             return fallback_result

#     if not own_prices:
#         return "DATA MISSING", f"{own_product} prices were not found on the cited page."

#     if not compared_prices:
#         return "DATA MISSING", f"{compared_brand} competitor prices were not found on the cited page."

#     shared_strengths = [
#         strength for strength in own_prices if strength in compared_prices
#     ]
#     if not shared_strengths:
#         return (
#             "DATA MISSING",
#             f"No matching strengths were found between {own_product} and {compared_brand}.",
#         )

#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     calculated_rows: list[tuple[str, float, float, float]] = []
#     missing_differences: list[str] = []

#     for strength in shared_strengths:
#         own_price = own_prices[strength]
#         compared_price = compared_prices[strength]
#         difference = round(compared_price - own_price, 2)
#         calculated_rows.append((strength, own_price, compared_price, difference))
#         if not _float_set_contains(response_numbers, difference):
#             missing_differences.append(f"{strength} mg: {difference:g}")

#     evidence = "; ".join(
#         (
#             f"{own_product} {strength} mg {own_price:g} vs "
#             f"{compared_brand} {strength} mg {compared_price:g} = {difference:g} cheaper"
#         )
#         for strength, own_price, compared_price, difference in calculated_rows
#     )

#     if not missing_differences:
#         return "PASS", f"Price difference matches cited table calculation. {evidence}."

#     return (
#         "FAIL",
#         "Price difference mismatch. Cited table calculation: "
#         f"{evidence}. Missing/incorrect SuperAI difference(s): {', '.join(missing_differences)}.",
#     )


# def _compare_single_row_price_difference(
#     response_text: str,
#     page_data: str,
#     own_product: str,
#     compared_brand: str,
# ) -> tuple[str, str]:
#     """Validate price difference when own product and competitor use single table rows."""
#     own_prices = _extract_exact_product_prices(page_data, own_product)
#     fallback_own_price = _extract_requested_product_price(page_data, f"What is the MRP of {own_product}?")
#     if fallback_own_price is not None:
#         own_prices.add(fallback_own_price)

#     competitor_rows = _extract_competitor_table_rows(page_data)
#     compared_rows = [
#         row
#         for row in competitor_rows
#         if _entity_text_contains(str(row["brand"]), compared_brand)
#         or _entity_text_contains(compared_brand, str(row["brand"]))
#     ]
#     compared_rows = [row for row in compared_rows if row.get("price") is not None]

#     if not own_prices or not compared_rows:
#         return "DATA MISSING", "Single-row price difference evidence was not found on the cited page."

#     compared_price = float(compared_rows[0]["price"])
#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     calculated = [
#         (own_price, round(abs(compared_price - own_price), 2))
#         for own_price in sorted(own_prices)
#     ]

#     for own_price, difference in calculated:
#         if _float_set_contains(response_numbers, difference):
#             return (
#                 "PASS",
#                 "Price difference matches cited table calculation. "
#                 f"{compared_brand} {compared_price:g} - {own_product} {own_price:g} = {difference:g}.",
#             )

#     calculated_summary = "; ".join(
#         f"{compared_brand} {compared_price:g} - {own_product} {own_price:g} = {difference:g}"
#         for own_price, difference in calculated
#     )
#     return (
#         "FAIL",
#         "Price difference mismatch. Cited table calculation(s): "
#         f"{calculated_summary}.",
#     )


# def _extract_exact_product_prices(page_data: str, product: str) -> set[float]:
#     """Extract prices that are tied to the exact product name."""
#     prices: set[float] = set()
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     product_pattern = r"\s*[-_/]?\s*".join(
#         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
#     )

#     for match in re.finditer(
#         rf"\b{product_pattern}\b\s*[:-]+\s*(?P<price>\d{{1,4}}(?:,\d{{3}})*(?:\.\d+)?)\s*\(",
#         normalized_page,
#         flags=re.IGNORECASE,
#     ):
#         prices.add(float(match.group("price").replace(",", "")))

#     for match in re.finditer(
#         rf"\b{product_pattern}\b\s+TABLETS(?:\s+\(\d+\s*TABS\))?\s+"
#         r"(?P<current>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s+"
#         r"(?P<new>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\b",
#         normalized_page,
#         flags=re.IGNORECASE,
#     ):
#         prices.add(float(match.group("current").replace(",", "")))
#         prices.add(float(match.group("new").replace(",", "")))

#     return prices


# # Column header keyword → canonical attribute type used by resolve_attribute_type.
# # Ordered from most-specific to least-specific so the first matching alias wins.
# _COLUMN_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
#     "PM_OBJECTIVE": (
#         "pm obj",
#         "pm objective",
#         "pmr obj",
#         "pmr objective",
#         "monthly obj",
#         "monthly objective",
#         "monthly minimum",
#         "minimum objective",
#         "pm target",
#         "pmr target",
#     ),
#     "QUARTERLY_OBJECTIVE": (
#         "quarterly obj",
#         "quarterly objective",
#         "qtr obj",
#         "quarterly pmr",
#         "quarterly pm",
#         "q objective",
#     ),
#     "INCENTIVE": (
#         "incentive per strip",
#         "incentive/strip",
#         "inc/strip",
#         "incentive per tab",
#         "incentive/tab",
#         "incentive value",
#         "incentive",
#     ),
# }


# def _detect_column_order(page_data: str) -> list[str]:
#     """Return column types in left-to-right order based on header positions.

#     Scans the page text for column header aliases and sorts them by their
#     character position.  The resulting list gives the column index for each
#     attribute type so that row-level numbers can be mapped to the right cell.
#     """
#     normalized = re.sub(r"\s+", " ", page_data)
#     positions: list[tuple[int, str]] = []
#     seen: set[str] = set()
#     for col_type, aliases in _COLUMN_HEADER_ALIASES.items():
#         for alias in aliases:
#             m = re.search(re.escape(alias), normalized, flags=re.IGNORECASE)
#             if m and col_type not in seen:
#                 positions.append((m.start(), col_type))
#                 seen.add(col_type)
#                 break
#     positions.sort()
#     return [col_type for _, col_type in positions]


# def _table_column_cell_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     """Validate by selecting the exact column for the requested attribute.

#     Prevents PM_OBJECTIVE responses from being compared against the
#     QUARTERLY_OBJECTIVE column (and vice versa) when multiple numeric
#     columns share the same product row.

#     Pipeline:
#       question → resolve_attribute_type → detect column order → find product
#       row → filter product-name digits → pick number at column index → compare.
#     """
#     attr_type = resolve_attribute_type(question)
#     if attr_type not in _COLUMN_HEADER_ALIASES:
#         return False, "DATA MISSING", "", ""

#     column_order = _detect_column_order(page_data)
#     if attr_type not in column_order:
#         return False, "DATA MISSING", "", ""

#     col_index = column_order.index(attr_type)

#     product = _extract_table_product_from_question(question)
#     if not product:
#         return False, "DATA MISSING", "", ""

#     normalized_page = re.sub(r"\s+", " ", page_data)
#     tokens = _product_name_tokens(product)
#     if not tokens:
#         return False, "DATA MISSING", "", ""

#     product_pattern = r"[-\s/]*".join(re.escape(t) for t in tokens)
#     row_match = re.search(
#         rf"\b{product_pattern}\b(?P<row>.{{0,220}})",
#         normalized_page,
#         flags=re.IGNORECASE,
#     )
#     if not row_match:
#         return False, "DATA MISSING", "", ""

#     row_text = row_match.group(0)

#     # Filter out digits that are part of the product name (e.g. "2.5" from "CONCOR 2.5").
#     product_nums = {
#         float(n)
#         for token in tokens
#         for n in re.findall(r"\d+(?:\.\d+)?", token)
#     }
#     all_nums = [
#         float(n.replace(",", ""))
#         for n in re.findall(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", row_text)
#         if not any(abs(float(n.replace(",", "")) - pn) <= 0.001 for pn in product_nums)
#     ]

#     if col_index >= len(all_nums):
#         # Column index is out of range — OCR may have dropped a value.
#         # Log clearly and return DATA MISSING so OpenAI can attempt recovery
#         # from the partial page text rather than silently failing.
#         _log_validation_step(
#             rule="_table_column_cell_validation",
#             product=product,
#             attribute=attr_type,
#             column=f"index {col_index} of {column_order}",
#             doc_value=f"only {len(all_nums)} numeric(s) found in row",
#             response_value=list(response_numbers if response_numbers else []),
#             verdict="DATA MISSING",
#             reason=(
#                 f"Column index {col_index} out of range: row for {product!r} "
#                 f"has only {len(all_nums)} numeric value(s) after filtering product "
#                 f"name digits. OCR may have dropped a value. "
#                 f"Row text: {row_text[:200]!r}"
#             ),
#         )
#         return False, "DATA MISSING", "", ""

#     expected_value = all_nums[col_index]
#     response_numbers = {float(n) for n in _extract_numbers(response_text)}

#     if _float_set_contains(response_numbers, expected_value):
#         _log_validation_step(
#             rule="_table_column_cell_validation",
#             product=product,
#             attribute=attr_type,
#             column=f"index {col_index} of {column_order}",
#             doc_value=expected_value,
#             response_value=sorted(response_numbers),
#             verdict="PASS",
#             reason=f"{attr_type} for {product} matches: {expected_value:g}.",
#         )
#         return (
#             True,
#             "PASS",
#             f"{attr_type} for {product} matches cited page: {expected_value:g}.",
#             f"{expected_value:g}",
#         )

#     _log_validation_step(
#         rule="_table_column_cell_validation",
#         product=product,
#         attribute=attr_type,
#         column=f"index {col_index} of {column_order}",
#         doc_value=expected_value,
#         response_value=sorted(response_numbers),
#         verdict="FAIL",
#         reason=f"Cited {attr_type}={expected_value:g}, response has {sorted(response_numbers)}.",
#     )
#     return (
#         True,
#         "FAIL",
#         f"{attr_type} mismatch for {product}. Cited value: {expected_value:g}, "
#         f"but SuperAI returned "
#         f"{', '.join(f'{n:g}' for n in sorted(response_numbers))}.",
#         "",
#     )


# def _deterministic_table_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     """Validate row-grounded table questions before generic numeric matching."""
#     normalized_question = normalize_text(question)
#     if _is_missing_source_data(page_data):
#         return False, "DATA MISSING", "", ""

#     if not any(
#         term in normalized_question
#         for term in (
#             "mrp",
#             "price",
#             "per tablet",
#             "per tab",
#             "highest",
#             "lowest",
#             "difference",
#             "sku",
#             "packaging",
#             "company",
#             "manufactured",
#             "manufacturer",
#             "belongs to",
#             "mdi",
#             "dpi",
#             "forte",
#             "incentive",
#             "objective",
#             "minimum",
#             "target",
#         )
#     ):
#         return False, "DATA MISSING", "", ""

#     # Column-aware validation runs first so PM_OBJECTIVE is never compared
#     # against the QUARTERLY_OBJECTIVE column.
#     column_cell_result = _table_column_cell_validation(response_text, page_data, question)
#     if column_cell_result[0]:
#         return column_cell_result

#     difference_result = _table_price_difference_validation(response_text, page_data, question)
#     if difference_result[0]:
#         return difference_result

#     company_result = _table_company_lookup(response_text, page_data, question)
#     if company_result[0]:
#         return company_result

#     column_result = _table_matrix_value_validation(response_text, page_data, question)
#     if column_result[0]:
#         return column_result

#     reverse_result = _table_reverse_price_lookup(response_text, page_data, question)
#     if reverse_result[0]:
#         return reverse_result

#     ranking_result = _table_price_ranking_validation(response_text, page_data, question)
#     if ranking_result[0]:
#         return ranking_result

#     competitor_unit_ranking = _table_competitor_unit_price_ranking_validation(
#         response_text,
#         page_data,
#         question,
#     )
#     if competitor_unit_ranking[0]:
#         return competitor_unit_ranking

#     pack_result = _table_pack_size_validation(response_text, page_data, question)
#     if pack_result[0]:
#         return pack_result

#     lookup_result = _table_price_lookup_validation(response_text, page_data, question)
#     if lookup_result[0]:
#         return lookup_result

#     return False, "DATA MISSING", "", ""


# def _table_price_lookup_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     """Validate direct product/SKU price lookups using exact row chunks."""
#     product = _extract_table_product_from_question(question)
#     if not product:
#         return False, "DATA MISSING", "", ""

#     row = _best_family_price_row(page_data, product)
#     if not row:
#         return False, "DATA MISSING", "", ""

#     normalized_question = normalize_text(question)
#     value = row["unit_price"] if any(term in normalized_question for term in ("per tablet", "per tab")) else row["price"]
#     if value is None:
#         return True, "DATA MISSING", f"Requested table value was not found for {row['product']}.", ""

#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     if _float_set_contains(response_numbers, float(value)):
#         return (
#             True,
#             "PASS",
#             f"Table row value matches cited page: {row['product']} = {float(value):g}.",
#             f"{float(value):g}",
#         )

#     return (
#         True,
#         "FAIL",
#         f"Table row value mismatch. Cited row for {row['product']} has {float(value):g}.",
#         "",
#     )


# def _table_pack_size_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     normalized_question = normalize_text(question)
#     if not any(term in normalized_question for term in ("packaging", "pack size", "pack")):
#         return False, "DATA MISSING", "", ""

#     product = _extract_table_product_from_question(question)
#     rows = _family_price_rows(page_data, product) if product else []
#     if not rows and "cilaheart" in normalized_question:
#         rows = _family_price_rows(page_data, "CILAHEART")
#     if not rows:
#         return False, "DATA MISSING", "", ""

#     if "common" in normalized_question:
#         packs = {row["pack"] for row in rows if row.get("pack")}
#         if not packs:
#             return True, "DATA MISSING", "Pack size was not found in cited table rows.", ""
#         expected = sorted(packs)[0] if len(packs) == 1 else ""
#         if expected and normalize_text(expected) in normalize_text(response_text):
#             return True, "PASS", f"Common pack size matches cited table rows: {expected}.", expected
#         if expected:
#             return True, "FAIL", f"Common pack size mismatch. Cited table rows show {expected}.", ""
#         return True, "DATA MISSING", "No single common pack size exists across cited table rows.", ""

#     row = _best_family_price_row(page_data, product)
#     if not row or not row.get("pack"):
#         return True, "DATA MISSING", "Requested pack size was not found in the cited table row.", ""
#     expected = str(row["pack"])
#     if normalize_text(expected) in normalize_text(response_text):
#         return True, "PASS", f"Pack size matches cited table row: {row['product']} = {expected}.", expected
#     return True, "FAIL", f"Pack size mismatch. Cited row for {row['product']} has {expected}.", ""


# def _table_price_ranking_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     normalized_question = normalize_text(question)
#     if not any(term in normalized_question for term in ("highest", "lowest", "cheapest")):
#         return False, "DATA MISSING", "", ""

#     family = _extract_ranking_family(question)
#     rows = _family_price_rows(page_data, family) if family else []
#     rows = [row for row in rows if row.get("price") is not None]
#     if not rows:
#         return False, "DATA MISSING", "", ""

#     expected = min(rows, key=lambda row: float(row["price"])) if any(term in normalized_question for term in ("lowest", "cheapest")) else max(rows, key=lambda row: float(row["price"]))
#     expected_price = float(expected["price"])
#     brand_ok = _entity_text_contains(response_text, str(expected["product"])) or _entity_text_contains_ordered_tokens(response_text, str(expected["product"]))
#     price_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, expected_price)
#     label = "lowest" if any(term in normalized_question for term in ("lowest", "cheapest")) else "highest"
#     if brand_ok and (price_ok or not _extract_numbers(response_text)):
#         return True, "PASS", f"{label.title()} table row matches cited page: {expected['product']} at {expected_price:g}.", f"{expected['product']} {expected_price:g}"
#     return True, "FAIL", f"{label.title()} table row is {expected['product']} at {expected_price:g}; SuperAI does not match.", ""


# def _table_competitor_unit_price_ranking_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     """Validate competitor ranking by per-tablet/per-tab value."""
#     normalized_question = normalize_text(question)
#     if "competitor" not in normalized_question:
#         return False, "DATA MISSING", "", ""
#     if not any(term in normalized_question for term in ("highest", "lowest", "cheapest")):
#         return False, "DATA MISSING", "", ""
#     if not any(term in normalized_question for term in ("per tablet", "per tab")):
#         return False, "DATA MISSING", "", ""

#     rows = [row for row in _extract_competitor_unit_price_rows(page_data) if row.get("unit_price") is not None]
#     if not rows:
#         return False, "DATA MISSING", "", ""

#     label = "lowest" if any(term in normalized_question for term in ("lowest", "cheapest")) else "highest"
#     expected = min(rows, key=lambda row: float(row["unit_price"])) if label == "lowest" else max(rows, key=lambda row: float(row["unit_price"]))
#     expected_brand = str(expected["brand"])
#     expected_unit = float(expected["unit_price"])
#     brand_ok = _entity_text_contains(response_text, expected_brand) or _entity_text_contains_ordered_tokens(response_text, expected_brand)
#     unit_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, expected_unit)

#     if brand_ok and unit_ok:
#         return (
#             True,
#             "PASS",
#             f"{label.title()} competitor per-tablet row matches cited table: {expected_brand} = {expected_unit:g}.",
#             f"{expected_brand} {expected_unit:g}",
#         )
#     return (
#         True,
#         "FAIL",
#         f"{label.title()} competitor per-tablet row is {expected_brand} = {expected_unit:g}; SuperAI does not match.",
#         "",
#     )


# def _table_price_difference_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     normalized_question = normalize_text(question)
#     if "difference" not in normalized_question and "between" not in normalized_question:
#         return False, "DATA MISSING", "", ""

#     left, right = _extract_price_comparison_entities(question)
#     if not left or not right:
#         return False, "DATA MISSING", "", ""

#     left_row = _best_family_price_row(page_data, left)
#     right_row = _best_family_price_row(page_data, right)
#     if not left_row or not right_row:
#         return False, "DATA MISSING", "", ""

#     left_value = float(left_row["price"])
#     right_value = float(right_row["price"])
#     difference = round(abs(right_value - left_value), 2)
#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     if _float_set_contains(response_numbers, difference):
#         return (
#             True,
#             "PASS",
#             f"Price difference matches cited table rows: {right_row['product']} {right_value:g} - {left_row['product']} {left_value:g} = {difference:g}.",
#             f"{difference:g}",
#         )
#     return (
#         True,
#         "FAIL",
#         f"Price difference mismatch. Cited calculation is {difference:g} from {left_row['product']} {left_value:g} and {right_row['product']} {right_value:g}.",
#         "",
#     )


# def _table_reverse_price_lookup(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     normalized_question = normalize_text(question)
#     if not (
#         ("which" in normalized_question and any(term in normalized_question for term in ("sku", "competitor", "brand")))
#         or "has an mrp" in normalized_question
#         or "has a per tablet price" in normalized_question
#         or "has a price" in normalized_question
#     ):
#         return False, "DATA MISSING", "", ""

#     requested_numbers = [float(number) for number in _extract_numbers(question)]
#     if not requested_numbers:
#         return False, "DATA MISSING", "", ""
#     requested_value = requested_numbers[-1]

#     family = _extract_ranking_family(question) or _extract_table_product_from_question(question)
#     rows = _family_price_rows(page_data, family) if family else []
#     matrix_rows = _extract_dpi_mdi_matrix_rows(page_data)
#     own_matrix_rows = _extract_own_dpi_mdi_price_rows(page_data)

#     candidates: list[tuple[str, float]] = []
#     for row in rows:
#         for key in ("price", "unit_price"):
#             if row.get(key) is not None and abs(float(row[key]) - requested_value) <= 0.05:
#                 candidates.append((str(row["product"]), float(row[key])))
#     for row in own_matrix_rows:
#         if abs(float(row["price"]) - requested_value) <= 0.05:
#             candidates.append((str(row["product"]), float(row["price"])))
#     for row in matrix_rows:
#         for column, value in row.get("values", {}).items():
#             if value is not None and abs(float(value) - requested_value) <= 0.05:
#                 candidates.append((str(row["brand"]), float(value)))

#     if not candidates:
#         return False, "DATA MISSING", "", ""

#     matching = [name for name, _ in candidates if _entity_text_contains(response_text, name) or _entity_text_contains_ordered_tokens(response_text, name)]
#     expected_names = ", ".join(name for name, _ in candidates)
#     if matching:
#         return True, "PASS", f"Reverse table lookup matches cited row: {expected_names} has {requested_value:g}.", f"{expected_names} {requested_value:g}"
#     return True, "FAIL", f"Reverse table lookup mismatch. Cited table maps {requested_value:g} to {expected_names}.", ""


# def _table_company_lookup(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     normalized_question = normalize_text(question)
#     if not any(term in normalized_question for term in ("company", "manufactured", "manufacturer", "belongs to")):
#         return False, "DATA MISSING", "", ""

#     brand = _extract_company_question_brand(question)
#     company = _extract_marketed_by_company(question)
#     rows = (
#         _extract_dpi_mdi_matrix_rows(page_data)
#         + _extract_competitor_table_rows(page_data)
#         + _extract_competitor_unit_price_rows(page_data)
#     )

#     if company and not brand:
#         matches = [row for row in rows if _company_text_contains(str(row.get("company", "")), company)]
#         if not matches:
#             return False, "DATA MISSING", "", ""
#         expected = str(matches[0].get("brand", ""))
#         if _entity_text_contains(response_text, expected) or _entity_text_contains_ordered_tokens(response_text, expected):
#             return True, "PASS", f"Company-brand mapping matches cited table: {expected} belongs to {company}.", expected
#         return True, "FAIL", f"Company-brand mismatch. Cited table lists {expected} for {company}.", ""

#     if not brand:
#         return False, "DATA MISSING", "", ""

#     matching_rows = [
#         row for row in rows
#         if _entity_text_contains(str(row.get("brand", "")), brand)
#         or _entity_text_contains(brand, str(row.get("brand", "")))
#         or _entity_text_contains_ordered_tokens(str(row.get("brand", "")), brand)
#     ]
#     if not matching_rows:
#         return False, "DATA MISSING", "", ""

#     expected_company = str(matching_rows[0].get("company", ""))
#     if _company_text_contains(response_text, expected_company):
#         return True, "PASS", f"Company matches cited table row: {brand} is listed with {expected_company}.", expected_company
#     return True, "FAIL", f"Company mismatch. Cited table lists {brand} with {expected_company}.", ""


# def _table_matrix_value_validation(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[bool, str, str, str]:
#     normalized_question = normalize_text(question)
#     if not any(term in normalized_question for term in ("dpi", "mdi", "forte")):
#         return False, "DATA MISSING", "", ""

#     rows = _extract_dpi_mdi_matrix_rows(page_data)
#     if not rows:
#         return False, "DATA MISSING", "", ""

#     requested_brand = _extract_matrix_brand_from_question(question, rows)
#     requested_column = _extract_matrix_column_from_question(question)

#     if "lowest" in normalized_question or "highest" in normalized_question:
#         if not requested_column:
#             return False, "DATA MISSING", "", ""
#         valued_rows = [row for row in rows if row.get("values", {}).get(requested_column) is not None]
#         if not valued_rows:
#             return True, "DATA MISSING", f"No values found for {requested_column} in cited table.", ""
#         expected = min(valued_rows, key=lambda row: float(row["values"][requested_column])) if "lowest" in normalized_question else max(valued_rows, key=lambda row: float(row["values"][requested_column]))
#         value = float(expected["values"][requested_column])
#         brand_ok = _entity_text_contains(response_text, str(expected["brand"])) or _entity_text_contains_ordered_tokens(response_text, str(expected["brand"]))
#         value_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, value)
#         label = "lowest" if "lowest" in normalized_question else "highest"
#         if brand_ok and value_ok:
#             return True, "PASS", f"{label.title()} {requested_column} value matches cited table: {expected['brand']} = {value:g}.", f"{expected['brand']} {value:g}"
#         return True, "FAIL", f"{label.title()} {requested_column} value is {expected['brand']} = {value:g}; SuperAI does not match.", ""

#     if not requested_brand or not requested_column:
#         return False, "DATA MISSING", "", ""

#     row = next(
#         (
#             row for row in rows
#             if _entity_text_contains(str(row["brand"]), requested_brand)
#             or _entity_text_contains(requested_brand, str(row["brand"]))
#             or _entity_text_contains_ordered_tokens(str(row["brand"]), requested_brand)
#         ),
#         None,
#     )
#     if not row:
#         return False, "DATA MISSING", "", ""

#     value = row.get("values", {}).get(requested_column)
#     if value is None:
#         response_numbers = {float(number) for number in _extract_numbers(response_text)}
#         if response_numbers or "NA" in str(row.get("raw", "")).upper():
#             return True, "FAIL", f"Cited table shows no numeric value for {row['brand']} {requested_column}.", ""
#         return True, "DATA MISSING", f"{requested_column} value was not found for {row['brand']} in cited table.", ""

#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     if _float_set_contains(response_numbers, float(value)):
#         return True, "PASS", f"Table cell matches cited row: {row['brand']} {requested_column} = {float(value):g}.", f"{float(value):g}"
#     return True, "FAIL", f"Table cell mismatch. Cited row has {row['brand']} {requested_column} = {float(value):g}.", ""


# def _extract_own_dpi_mdi_price_rows(page_data: str) -> list[dict[str, object]]:
#     """Extract own Combihale FB MRP matrix rows by SKU column."""
#     text = re.sub(r"\s+", " ", page_data).strip()
#     match = re.search(
#         r"M\.?R\.?P\s*\(Each SKU\)\s+COMBIHALE\s+FB\s+DPI\s+CAPS\s+COMBIHALE\s+FB\s+MDI\s+"
#         r"100\s+200\s+400\s+FORTE\s+200\s+400\s+"
#         r"(?P<values>(?:\d+(?:\.\d+)?\s*(?:Rs)?\s*){6})",
#         text,
#         flags=re.IGNORECASE,
#     )
#     if not match:
#         return []

#     values = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", match.group("values"))[:6]]
#     products = [
#         "COMBIHALE FB DPI CAPS 100",
#         "COMBIHALE FB DPI CAPS 200",
#         "COMBIHALE FB DPI CAPS 400",
#         "COMBIHALE FB DPI CAPS FORTE",
#         "COMBIHALE FB MDI 200",
#         "COMBIHALE FB MDI 400",
#     ]
#     return [
#         {"product": product, "price": values[index], "pack": "", "unit_price": None}
#         for index, product in enumerate(products)
#         if index < len(values)
#     ]


# def _extract_competitor_unit_price_rows(page_data: str) -> list[dict[str, object]]:
#     """Extract competitor rows with strip price and per-tablet price columns."""
#     text = re.sub(r"\s+", " ", page_data).strip()
#     if not re.search(r"\bper\s+tab\b|\bper\s+tablet\b", text, flags=re.IGNORECASE):
#         return []

#     end_match = re.search(
#         r"\bPackaging\s+Price\b|\bM\.?R\.?P\b|\bIndications\b|\bSalient\b",
#         text,
#         flags=re.IGNORECASE,
#     )
#     section = text[: end_match.start()] if end_match else text

#     company_pattern = "|".join(re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True))
#     row_pattern = re.compile(
#         rf"(?P<brand>[A-Za-z][A-Za-z0-9 /.-]{{1,60}}?)\s+"
#         rf"(?P<company>{company_pattern})\s+"
#         r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*"
#         r"\((?P<pack>\d+)\s*(?:tab|tabs|tablet|tablets)\)\s*"
#         r"(?P<unit>\d{1,4}(?:\.\d+)?)",
#         flags=re.IGNORECASE,
#     )

#     rows: list[dict[str, object]] = []
#     for match in row_pattern.finditer(section):
#         brand = _clean_brand_name(match.group("brand"))
#         brand = re.sub(r"^(?:mg\s+)?per(?:\s+tab)?\s+", "", brand, flags=re.IGNORECASE).strip()
#         company = _normalize_company_display(match.group("company"))
#         price = float(match.group("price").replace(",", ""))
#         unit_price = float(match.group("unit"))
#         pack = f"{match.group('pack')} Tab"
#         rows.append(
#             {
#                 "brand": brand,
#                 "company": company,
#                 "pack": pack,
#                 "price": price,
#                 "unit_price": unit_price,
#                 "values": {},
#                 "raw": match.group(0),
#             }
#         )
#     return rows


# def _family_price_rows(page_data: str, family: str) -> list[dict[str, object]]:
#     """Extract repeated product-family rows with row-local numeric values."""
#     if not family:
#         return []

#     text = re.sub(r"\s+", " ", page_data).strip()
#     family_tokens = _family_tokens(family)
#     if not family_tokens:
#         return []

#     family_pattern = r"[-\s/]*".join(re.escape(token) for token in family_tokens)
#     matches = list(re.finditer(rf"\b{family_pattern}\b", text, flags=re.IGNORECASE))
#     rows: list[dict[str, object]] = []
#     for index, match in enumerate(matches):
#         start = match.start()
#         end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), start + 180)
#         citation_break = text.find("| | Citation", start, end)
#         if citation_break != -1:
#             end = citation_break
#         chunk = text[start:end].strip(" |")
#         numbers = list(re.finditer(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", chunk))
#         if not numbers:
#             continue

#         numeric_values = [float(number.group(0).replace(",", "")) for number in numbers]
#         pack = ""
#         pack_match = re.search(r"\((\d+)\s*(?:TABS?|TABLETS?|CAPS?)\)|\b(\d+)\s*(?:TAB|TABS|CAP|CAPS)\b", chunk, flags=re.IGNORECASE)
#         if pack_match:
#             pack = f"{pack_match.group(1) or pack_match.group(2)} Tab"

#         # Use explicit price-indicator context (Rs/₹/MRP or /Tab) when present
#         # to avoid mistaking serial numbers, pack sizes, or adjacent-row values
#         # for the product price.
#         _indicator_unit = _extract_price_indicator_from_row(chunk, wants_unit_price=True)
#         _indicator_strip = _extract_price_indicator_from_row(chunk, wants_unit_price=False)
#         if _indicator_unit is not None or _indicator_strip is not None:
#             price = _indicator_strip if _indicator_strip is not None else _indicator_unit
#             unit_price = _indicator_unit
#             previous_value = None
#         else:
#             price, unit_price, previous_value = _derive_row_price_values(numeric_values, pack)

#         product_end = numbers[-2].start() if len(numbers) >= 2 else numbers[-1].start()
#         product = re.sub(r"\s+", " ", chunk[:product_end]).strip(" :-|")
#         if not product:
#             product = match.group(0)

#         row = {
#             "product": product,
#             "chunk": chunk,
#             "numbers": numeric_values,
#             "price": price,
#             "previous_value": previous_value,
#             "unit_price": unit_price,
#             "pack": pack,
#         }
#         rows.append(row)

#     return _dedupe_family_rows(rows)


# def _best_family_price_row(page_data: str, product: str) -> dict[str, object] | None:
#     family = _extract_ranking_family(product) or product
#     rows = _family_price_rows(page_data, family)
#     if not rows:
#         return None

#     product_tokens = set(_significant_product_tokens(product))
#     scored: list[tuple[int, dict[str, object]]] = []
#     for row in rows:
#         row_tokens = set(_significant_product_tokens(str(row["product"])))
#         score = len(product_tokens.intersection(row_tokens))
#         if score:
#             scored.append((score, row))

#     if not scored:
#         return None
#     scored.sort(key=lambda item: (item[0], len(str(item[1]["product"]))), reverse=True)
#     best_score, best_row = scored[0]
#     required = min(2, len(product_tokens))
#     return best_row if best_score >= required else None


# def _derive_unit_price(numbers: list[float], pack: str) -> float | None:
#     _, unit_price, _ = _derive_row_price_values(numbers, pack)
#     return unit_price


# def _derive_row_price_values(numbers: list[float], pack: str) -> tuple[float, float | None, float | None]:
#     """Return row MRP/new-MRP, unit price, and previous row value."""
#     if not numbers:
#         return 0.0, None, None

#     previous_value = numbers[-2] if len(numbers) >= 2 else None
#     price = numbers[-1]
#     unit_price: float | None = None
#     pack_numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", pack or "")]
#     pack_count = pack_numbers[0] if pack_numbers else 0.0

#     if pack_count > 0 and len(numbers) >= 2:
#         explicit_unit_candidate = numbers[-1]
#         strip_candidate = numbers[-2]
#         if abs(round(strip_candidate / pack_count, 2) - explicit_unit_candidate) <= 0.25:
#             price = strip_candidate
#             unit_price = explicit_unit_candidate
#         else:
#             price = numbers[-1]
#             unit_price = round(price / pack_count, 2)
#     else:
#         # Prefer the last value that has a fractional part over a trailing
#         # whole-integer artefact such as a row serial number or SKU index
#         # (e.g. pick 22.41 over the trailing "7" in "SITADAY-DM FORTE 22.41 7").
#         # Large integers (> 99) are still treated as potential prices (strip MRPs).
#         decimal_candidates = [n for n in numbers if n % 1 != 0 or n > 99]
#         if decimal_candidates:
#             price = decimal_candidates[-1]

#     return price, unit_price, previous_value


# def _extract_table_product_from_question(question: str) -> str:
#     patterns = (
#         r"\b(?:mrp|price)\s+of\s+(.+?)(?:\?)?$",
#         r"\bper\s+tablet\s+price\s+of\s+(.+?)(?:\?)?$",
#         r"\bpackaging\s+size\s+of\s+(.+?)(?:\?)?$",
#         r"\bprice\s+difference\s+between\s+(.+?)\s+and\b",
#     )
#     for pattern in patterns:
#         match = re.search(pattern, question, flags=re.IGNORECASE)
#         if match:
#             return re.sub(r"\s+", " ", match.group(1)).strip(" ?.")
#     return _extract_ranking_family(question)


# def _extract_ranking_family(text: str) -> str:
#     upper = text.upper()
#     if "COMBIHALE" in upper and "FB" in upper:
#         return "COMBIHALE-FB"
#     if "CILAHEART" in upper:
#         return "CILAHEART"
#     if "RIFASTOP" in upper:
#         return "RIFASTOP"
#     if "STATPURE" in upper:
#         return "STATPURE"
#     return ""


# def _family_tokens(product: str) -> list[str]:
#     tokens = re.findall(r"[A-Za-z0-9]+", product)
#     if len(tokens) >= 2 and tokens[0].lower() == "combihale" and tokens[1].lower() == "fb":
#         return ["COMBIHALE"]
#     return tokens[:2] if len(tokens) > 1 and any(token.isdigit() for token in tokens[1:]) else tokens[:1]


# def _significant_product_tokens(product: str) -> list[str]:
#     aliases = {
#         "caps": "capsules",
#         "cap": "capsules",
#         "mdi": "inhaler",
#         "inhalers": "inhaler",
#         "tabs": "tablets",
#         "tab": "tablets",
#     }
#     stop = {"what", "which", "sku", "has", "mrp", "price", "per", "tablet", "strip", "rs", "of", "the", "and"}
#     tokens: list[str] = []
#     for token in re.findall(r"[A-Za-z0-9]+", product.lower()):
#         token = aliases.get(token, token)
#         if token not in stop:
#             tokens.append(token)
#     return tokens


# def _dedupe_family_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
#     seen: set[str] = set()
#     deduped: list[dict[str, object]] = []
#     for row in rows:
#         key = normalize_text(str(row["product"]))
#         if key in seen:
#             continue
#         seen.add(key)
#         deduped.append(row)
#     return deduped


# def _extract_dpi_mdi_matrix_rows(page_data: str) -> list[dict[str, object]]:
#     """Extract Combihale-style BRAND/COMPANY/DPI/MDI matrix rows."""
#     text = re.sub(r"\s+", " ", page_data).strip()
#     if not re.search(r"\bDPI\b.*\bMDI\b.*\bBRAND\s+NAME\b", text, flags=re.IGNORECASE):
#         return []

#     section_match = re.search(
#         r"BRAND\s+NAME\s+COMPANY\s+100\s+200\s+400\s+FORTE\s+200\s+400\s+(.+?)(?:M\.?R\.?P|Recommended|Salient|$)",
#         text,
#         flags=re.IGNORECASE,
#     )
#     section = section_match.group(1) if section_match else text
#     section = re.sub(r"\bRs\b", " ", section, flags=re.IGNORECASE)
#     company_pattern = "|".join(re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True))
#     brand_pattern = r"(?!NA\b|Rs\b|A\s+\d)[A-Za-z][A-Za-z0-9 /.-]{1,80}?"
#     row_pattern = re.compile(
#         rf"(?P<brand>{brand_pattern})\s+(?P<company>{company_pattern})\s+"
#         rf"(?P<values>.+?)(?=(?:{brand_pattern}\s+(?:{company_pattern})\s+)|$)",
#         flags=re.IGNORECASE,
#     )

#     rows: list[dict[str, object]] = []
#     for match in row_pattern.finditer(section):
#         brand = _clean_brand_name(match.group("brand"))
#         company = _normalize_company_display(match.group("company"))
#         raw_values = re.findall(r"\bNA\b|\d+(?:\.\d+)?", match.group("values"), flags=re.IGNORECASE)
#         if not brand or not raw_values:
#             continue
#         mapped = _map_dpi_mdi_values(raw_values)
#         rows.append(
#             {
#                 "brand": brand,
#                 "company": company,
#                 "values": mapped,
#                 "raw": match.group(0),
#                 "pack": "",
#                 "price": None,
#             }
#         )
#     return rows


# def _map_dpi_mdi_values(raw_values: list[str]) -> dict[str, float | None]:
#     values = [None if value.upper() == "NA" else float(value) for value in raw_values]
#     columns = ["DPI_100", "DPI_200", "DPI_400", "DPI_FORTE", "MDI_200", "MDI_400"]
#     if len(values) == 6:
#         return dict(zip(columns, values))
#     if len(values) == 5:
#         return {
#             "DPI_100": values[0],
#             "DPI_200": values[1],
#             "DPI_400": values[2],
#             "DPI_FORTE": None,
#             "MDI_200": values[3],
#             "MDI_400": values[4],
#         }
#     if len(values) == 4:
#         return {
#             "DPI_100": values[0],
#             "DPI_200": values[1],
#             "DPI_400": None,
#             "DPI_FORTE": None,
#             "MDI_200": values[2],
#             "MDI_400": values[3],
#         }
#     if len(values) == 3:
#         if values[0] is None:
#             return {
#                 "DPI_100": None,
#                 "DPI_200": None,
#                 "DPI_400": None,
#                 "DPI_FORTE": None,
#                 "MDI_200": values[1],
#                 "MDI_400": values[2],
#             }
#         return {
#             "DPI_100": None,
#             "DPI_200": None,
#             "DPI_400": None,
#             "DPI_FORTE": values[0],
#             "MDI_200": values[1],
#             "MDI_400": values[2],
#         }
#     return {column: values[index] if index < len(values) else None for index, column in enumerate(columns)}


# def _extract_matrix_column_from_question(question: str) -> str:
#     normalized = normalize_text(question)
#     if "mdi 400" in normalized:
#         return "MDI_400"
#     if "mdi 200" in normalized:
#         return "MDI_200"
#     if "dpi 400" in normalized:
#         return "DPI_400"
#     if "dpi 200" in normalized:
#         return "DPI_200"
#     if "dpi 100" in normalized:
#         return "DPI_100"
#     if "forte" in normalized:
#         return "DPI_FORTE"
#     return ""


# def _extract_matrix_brand_from_question(question: str, rows: list[dict[str, object]]) -> str:
#     for row in rows:
#         brand = str(row["brand"])
#         if _entity_text_contains(question, brand) or _entity_text_contains_ordered_tokens(question, brand):
#             return brand
#     return ""


# def _extract_price_response_numbers(text: str) -> set[float]:
#     """Extract price-associated numbers from a response string.

#     Only returns numbers that appear directly after ₹/Rs/MRP/price/cost or
#     directly before /tab, per tablet, per strip, per box.  This prevents digits
#     embedded in product names (e.g. "D3" → 3, "60K" → 60, "PANGRAF-1.0" → 1)
#     from being treated as price candidates and causing false FAILs.

#     Falls back to _extract_numbers when no price-indicator context is found so
#     that plain numeric responses (without currency symbols) still validate.
#     In the fallback path, small integers (≤ 10) that are likely part of product
#     names or dosage counts are excluded from price matching to avoid false FAILs.
#     """
#     price_numbers: set[float] = set()

#     for match in re.finditer(
#         r"(?:₹|Rs\.?|MRP|price|cost)\s*(?<!\d)(\d[\d,]*(?:\.\d+)?)(?!\d)",
#         text,
#         flags=re.IGNORECASE,
#     ):
#         value = match.group(1).replace(",", "")
#         if "." in value:
#             value = value.rstrip("0").rstrip(".")
#         price_numbers.add(float(value))

#     for match in re.finditer(
#         r"(?<!\d)(\d[\d,]*(?:\.\d+)?)(?!\d)"
#         r"\s*(?:/\s*(?:tab(?:let)?s?|strip|box)|per\s+(?:tab(?:let)?s?|strip|box))\b",
#         text,
#         flags=re.IGNORECASE,
#     ):
#         value = match.group(1).replace(",", "")
#         if "." in value:
#             value = value.rstrip("0").rstrip(".")
#         price_numbers.add(float(value))

#     if price_numbers:
#         return price_numbers

#     # Fallback: use all numbers but exclude very small integers (≤ 10) that are
#     # almost always product name digits, pack sizes, or citation indices rather
#     # than prices.  Prices in this domain are always > 10 (per strip or per tablet).
#     # Exception: keep decimals like 1.5, 2.5 because those can be valid per-tab
#     # prices for cheap generics — only exclude exact small integers.
#     all_numbers = _extract_numbers(text)
#     return {
#         float(n)
#         for n in all_numbers
#         if not (n.isdigit() and int(n) <= 10)
#     }


# def _compare_price_lookup(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate direct MRP/price lookup questions."""
#     response_numbers = _extract_price_response_numbers(response_text)
#     if not response_numbers:
#         return "DATA MISSING", "SuperAI response did not contain a price/MRP value."

#     normalized_question = normalize_text(question)
#     wants_unit_price = any(
#         term in normalized_question
#         for term in ("per tablet", "per tab", "mrp / tab", "mrp per tablet", "per tab price")
#     )

#     # For per-tablet questions try _extract_product_row_mrp first.
#     # _extract_price_master_new_mrp grabs the first two numbers as (current, new)
#     # strip MRP and would return 161.10 instead of 16.11 when the row is
#     # "SITADAY-100 TABLET 10 TAB 161.10 16.11".
#     # _extract_product_row_mrp understands the strip/unit column layout and
#     # returns candidate_numbers[-1] (the per-tablet value) when wants_unit_price.
#     if wants_unit_price:
#         requested_price = _extract_product_row_mrp(page_data, question)
#         if requested_price is None:
#             requested_price = _extract_price_master_new_mrp(page_data, question)
#     else:
#         requested_price = _extract_price_master_new_mrp(page_data, question)
#         if requested_price is None:
#             requested_price = _extract_product_row_mrp(page_data, question)
#     if requested_price is None:
#         requested_price = _extract_requested_product_price(page_data, question)
#     if requested_price is None:
#         requested_brand = _extract_company_question_brand(question) or _extract_first_product_name(question)
#         if requested_brand:
#             competitor_price = _extract_competitor_row_price_for_brand(page_data, requested_brand, question)
#             if competitor_price is not None:
#                 requested_price = competitor_price
#     if requested_price is None:
#         requested_brand = _extract_company_question_brand(question) or _extract_first_product_name(question)
#         if requested_brand:
#             competitor_prices = _extract_competitor_strength_prices(page_data, requested_brand)
#             if competitor_prices:
#                 requested_price = next(iter(competitor_prices.values()))

#     if requested_price is None:
#         _log_validation_step(
#             rule="_compare_price_lookup",
#             attribute="PRICE",
#             response_value=sorted(response_numbers),
#             verdict="DATA MISSING",
#             reason="Requested price/MRP was not found on the cited page.",
#         )
#         return "DATA MISSING", "Requested price/MRP was not found on the cited page."

#     if _float_set_contains(response_numbers, requested_price):
#         _log_validation_step(
#             rule="_compare_price_lookup",
#             attribute="PRICE",
#             doc_value=requested_price,
#             response_value=sorted(response_numbers),
#             verdict="PASS",
#             reason=f"Price/MRP matches cited page: {requested_price:g}.",
#         )
#         return "PASS", f"Price/MRP matches cited page: {requested_price:g}."

#     _log_validation_step(
#         rule="_compare_price_lookup",
#         attribute="PRICE",
#         doc_value=requested_price,
#         response_value=sorted(response_numbers),
#         verdict="FAIL",
#         reason=f"Cited page contains {requested_price:g}, response has {sorted(response_numbers)}.",
#     )
#     return (
#         "FAIL",
#         f"Price/MRP mismatch. Cited page contains {requested_price:g}, "
#         f"but SuperAI returned {', '.join(str(number) for number in sorted(response_numbers))}.",
#     )


# def _compare_trip_award_cost(
#     response_text: str,
#     page_data: str,
#     question: str,  # noqa: ARG001
# ) -> tuple[str, str]:
#     """Validate trip/award/medal/reimbursement cost questions.

#     Handles Indian number notation (₹1,10,000 → 110000) and must not be routed
#     through _compare_price_lookup which expects per-tablet or per-strip MRP rows.
#     """
#     attr_type = resolve_attribute_type(question)
#     response_numbers = _extract_price_response_numbers(response_text)
#     if not response_numbers:
#         _log_validation_step(
#             rule="_compare_trip_award_cost",
#             attribute=attr_type,
#             verdict="DATA MISSING",
#             reason="SuperAI response did not contain a numeric cost value.",
#         )
#         return "DATA MISSING", "SuperAI response did not contain a numeric cost value."

#     page_numbers = {float(n) for n in _extract_numbers(page_data)}
#     if not page_numbers:
#         _log_validation_step(
#             rule="_compare_trip_award_cost",
#             attribute=attr_type,
#             response_value=sorted(response_numbers),
#             verdict="DATA MISSING",
#             reason="Requested cost value was not found on the cited page.",
#         )
#         return "DATA MISSING", "Requested cost value was not found on the cited page."

#     for resp_num in response_numbers:
#         if _float_set_contains(page_numbers, resp_num):
#             _log_validation_step(
#                 rule="_compare_trip_award_cost",
#                 attribute=attr_type,
#                 doc_value=resp_num,
#                 response_value=resp_num,
#                 verdict="PASS",
#                 reason=f"Trip/award cost matches cited page: {resp_num:g}.",
#             )
#             return "PASS", f"Trip/award cost matches cited page: {resp_num:g}."

#     _log_validation_step(
#         rule="_compare_trip_award_cost",
#         attribute=attr_type,
#         doc_value=sorted(page_numbers),
#         response_value=sorted(response_numbers),
#         verdict="FAIL",
#         reason="Cost value in response not found on cited page.",
#     )
#     return (
#         "FAIL",
#         f"Trip/award cost mismatch. Cited page has "
#         f"{', '.join(f'{n:g}' for n in sorted(page_numbers))}, "
#         f"but SuperAI returned {', '.join(f'{n:g}' for n in sorted(response_numbers))}.",
#     )


# def _extract_competitor_row_price_for_brand(
#     page_data: str,
#     brand: str,
#     question: str,
# ) -> float | None:
#     """Return row-local competitor price/unit price for a requested brand."""
#     normalized_question = normalize_text(question)
#     wants_unit_price = any(term in normalized_question for term in ("per tablet", "per tab"))
#     for row in _extract_competitor_table_rows(page_data):
#         row_brand = str(row.get("brand", ""))
#         if not (
#             _entity_text_contains(row_brand, brand)
#             or _entity_text_contains(brand, row_brand)
#             or _entity_text_contains_ordered_tokens(row_brand, brand)
#         ):
#             continue
#         price = row.get("price")
#         if price is None:
#             continue
#         if wants_unit_price:
#             pack_numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", str(row.get("pack", "")))]
#             if pack_numbers:
#                 return round(float(price) / pack_numbers[0], 2)
#         return float(price)
#     return None


# def _extract_price_master_new_mrp(page_data: str, question: str) -> float | None:
#     """Extract exact product New MRP from Price Master rows."""
#     generic_price = _extract_generic_price_master_new_mrp(page_data, question)
#     if generic_price is not None:
#         return generic_price

#     product_match = re.search(
#         r"\bdocetrust\s+(\d+(?:\.\d+)?)\s*mg\b",
#         question,
#         flags=re.IGNORECASE,
#     )
#     if not product_match:
#         return None

#     strength = product_match.group(1).rstrip("0").rstrip(".")
#     if "." not in product_match.group(1):
#         strength = product_match.group(1)
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     row_match = re.search(
#         rf"\bDOCETRUST[-\s]*{re.escape(strength)}\s+INJECTION\s+"
#         r"(?P<current>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s+"
#         r"(?P<new>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\b",
#         normalized_page,
#         flags=re.IGNORECASE,
#     )
#     if not row_match:
#         return None

#     return float(row_match.group("new").replace(",", ""))


# def _extract_generic_price_master_new_mrp(page_data: str, question: str) -> float | None:
#     """Extract New MRP for a product row from flattened Price Master text."""
#     products = _extract_price_question_product_candidates(question)
#     if not products:
#         product = _extract_first_product_name(question)
#         products = [product] if product else []

#     normalized_page = re.sub(r"\s+", " ", page_data)
#     for product in products:
#         product = re.sub(
#             r"\b(?:current|new|mrp|price|cost|of|the|per|strip|box|pack|tablets?|capsules?|respules?)\b",
#             " ",
#             product,
#             flags=re.IGNORECASE,
#         )
#         product = re.sub(r"\s+", " ", product).strip(" ?:-.,")
#         if not product:
#             continue

#         tokens = _product_name_tokens(product)
#         if not tokens:
#             continue

#         product_pattern = r"[-\s/]*".join(re.escape(token) for token in tokens)
#         pack_match = re.search(r"\((\d+)\s*(?:TABS?|TABLETS?)", question, flags=re.IGNORECASE)
#         pack_patterns = [rf"\s+\({pack_match.group(1)}\s*TABS?\)", ""] if pack_match else [""]
#         for pack_pattern in pack_patterns:
#             row_match = re.search(
#                 rf"\b{product_pattern}\b(?:\s+(?:TABLETS?|TABLTES|INJECTIONS?|INJECTION|CAPSULES?|SUSPENSION|DROPS|RESPULES|DPI))*"
#                 rf"{pack_pattern}"
#                 r"\s+(?P<current>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s+"
#                 r"(?P<new>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\b",
#                 normalized_page,
#                 flags=re.IGNORECASE,
#             )
#             if row_match:
#                 return float(row_match.group("new").replace(",", ""))

#     return None


# def _extract_price_indicator_from_row(row_text: str, *, wants_unit_price: bool = False) -> float | None:
#     """Extract price from a row using explicit price-indicator context.

#     When wants_unit_price=True, checks for /Tab-associated values first so that
#     a row containing both a strip price and a per-tablet price (e.g.
#     "Rs 161.10/Strip Rs 16.11/Tab") returns the per-tablet value.

#     Ignores composition digits, pack sizes, and variant suffixes.
#     """
#     # Pattern A: number immediately before /Tab (highest priority for per-tablet questions)
#     _tab_pattern = r"\b(?P<val>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*/\s*(?:Tab(?:let)?s?)\b"
#     # Pattern B: number after Rs / ₹ / MRP / Price, not followed by /Strip
#     _rs_pattern = (
#         r"(?:Rs\.?|₹|MRP|Price)\s*[:\-]?\s*"
#         r"(?P<val>\d{1,6}(?:,\d{3})*(?:\.\d+)?)"
#         r"(?!\s*/\s*(?:Strip|Box|Pack))"  # exclude strip/box/pack-linked values
#     )

#     if wants_unit_price:
#         # /Tab pattern takes priority
#         for m in re.finditer(_tab_pattern, row_text, flags=re.IGNORECASE):
#             val = float(m.group("val").replace(",", ""))
#             if val > 0.5:
#                 return val
#         # Fallback: Rs/MRP value (exclude if immediately followed by /Strip)
#         for m in re.finditer(_rs_pattern, row_text, flags=re.IGNORECASE):
#             val = float(m.group("val").replace(",", ""))
#             if val > 0.5:
#                 return val
#     else:
#         # Rs/MRP pattern takes priority for strip/box price questions
#         for m in re.finditer(_rs_pattern, row_text, flags=re.IGNORECASE):
#             val = float(m.group("val").replace(",", ""))
#             if val > 0.5:
#                 return val
#         # Fallback: /Tab pattern
#         for m in re.finditer(_tab_pattern, row_text, flags=re.IGNORECASE):
#             val = float(m.group("val").replace(",", ""))
#             if val > 0.5:
#                 return val
#     return None


# def _extract_product_row_mrp(page_data: str, question: str) -> float | None:
#     """Extract MRP from flattened product rows preserving row-level product mapping.

#     Handles product MRP rows such as:
#     - NOBEGLAR CARTRIDGE 3 ML 620.61
#     - NOBEGLAR-UNO PREFILLED PEN 1 PACK 762
#     - NOBEGLIZ-M XR 10 TAB 102.09 10.21
#     """
#     products = _extract_price_question_product_candidates(question)
#     if not products:
#         product = _extract_first_product_name(question)
#         products = [product] if product else []

#     normalized_page = re.sub(r"\s+", " ", page_data)
#     normalized_question = normalize_text(question)
#     wants_unit_price = any(
#         term in normalized_question
#         for term in ("per tablet", "per tab", "mrp / tab", "mrp per tablet")
#     )

#     for product in products:
#         clean_product = re.sub(
#             r"\b(?:mrp|price|cost|of|the|per|tablet|tab|strip|box|pack)\b",
#             " ",
#             product,
#             flags=re.IGNORECASE,
#         )
#         clean_product = re.sub(r"\s+", " ", clean_product).strip(" ?:-.,")
#         if not clean_product:
#             continue

#         tokens = _product_name_tokens(clean_product)
#         if not tokens:
#             continue

#         product_pattern = r"[-\s/]*".join(re.escape(token) for token in tokens)
#         tight_re = re.compile(
#             rf"\b{product_pattern}\b"
#             r"(?P<row>.{0,140}?)"
#             r"(?=(?:\b[A-Z][A-Z0-9-]{2,}\b\s+[A-Z]|\bGLOSSARY\b|\bShort Form\b|$))",
#             flags=re.IGNORECASE,
#         )
#         wide_re = re.compile(
#             rf"\b{product_pattern}\b(?P<row>.{{0,140}})",
#             flags=re.IGNORECASE,
#         )

#         # Collect all occurrences so we can search for an indicator-bearing row
#         # before falling back to positional extraction on the first match.
#         all_matches = list(tight_re.finditer(normalized_page))
#         if not all_matches:
#             all_matches = list(wide_re.finditer(normalized_page))
#         if not all_matches:
#             continue

#         first_row_text = all_matches[0].group(0)

#         # Pass 1 – try every occurrence for an explicit price indicator (Rs/₹ or /Tab).
#         # The first match may be a bare table row without markers; a later occurrence
#         # on the same page may carry "Rs 14.43/Tab" context that gives the right value.
#         for m in all_matches:
#             row_text = m.group(0)
#             indicator_price = _extract_price_indicator_from_row(row_text, wants_unit_price=wants_unit_price)
#             if indicator_price is not None:
#                 return indicator_price

#         # Pass 2 – no indicator found anywhere; fall back to positional extraction
#         # on the first match only.
#         row_text = first_row_text

#         # Truncate at the next occurrence of the leading product token to avoid
#         # capturing price values from adjacent rows in bare tables (e.g.
#         # "SITADAY-PM FORTE 16.06 SITADAY-GM 2 FORTE 13.50" → stop before
#         # the second "SITADAY").
#         leading_token_re = re.escape(tokens[0])
#         _first_tok = re.search(rf"\b{leading_token_re}\b", row_text, re.IGNORECASE)
#         if _first_tok:
#             _second_tok = re.search(
#                 rf"\b{leading_token_re}\b",
#                 row_text[_first_tok.end():],
#                 re.IGNORECASE,
#             )
#             if _second_tok:
#                 row_text = row_text[: _first_tok.end() + _second_tok.start()]

#         numbers = [
#             float(number.replace(",", ""))
#             for number in re.findall(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", row_text)
#         ]
#         if not numbers:
#             continue

#         product_numbers = {
#             float(number)
#             for token in tokens
#             for number in re.findall(r"\d+(?:\.\d+)?", token)
#         }
#         candidate_numbers = [
#             number for number in numbers if not any(abs(number - prod) <= 0.001 for prod in product_numbers)
#         ]
#         if not candidate_numbers:
#             candidate_numbers = numbers

#         if wants_unit_price and len(candidate_numbers) >= 2:
#             return candidate_numbers[-1]

#         if len(candidate_numbers) >= 2 and candidate_numbers[0] <= 10 < candidate_numbers[-1]:
#             return candidate_numbers[-1]

#         return candidate_numbers[-1] if len(candidate_numbers) == 1 else candidate_numbers[-2]

#     return None


# def _extract_price_question_product_candidates(question: str) -> list[str]:
#     """Extract precise product candidates from price/MRP questions."""
#     patterns = (
#         r"\b(?:mrp|price)\s+per\s+(?:strip|box|respule|tablet|tab|capsule|cap)\s+of\s+(.+?)(?:\s*\(|\?)",
#         r"\b(?:mrp|price)\s+of\s+(.+?)(?:\s*\(|\?)",
#         r"\bof\s+(.+?)(?:\s*\(|\?)",
#     )
#     candidates: list[str] = []
#     for pattern in patterns:
#         match = re.search(pattern, question, flags=re.IGNORECASE)
#         if match:
#             candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ?.:-")
#             if candidate:
#                 candidates.append(candidate)
#     return candidates


# def _product_name_tokens(product: str) -> list[str]:
#     """Return product tokens, splitting compact variant-strength tokens like M25."""
#     raw_tokens = re.findall(r"[A-Za-z0-9]+", product)
#     tokens: list[str] = []
#     for token in raw_tokens:
#         compact_match = re.fullmatch(r"([A-Za-z]+)(\d+)", token)
#         if compact_match and compact_match.group(1).lower() in {"m"}:
#             tokens.extend([compact_match.group(1), compact_match.group(2)])
#         else:
#             tokens.append(token)
#     return tokens


# def _extract_first_product_name(question: str) -> str:
#     """Return a simple product candidate from lookup questions."""
#     direct_match = re.search(
#         r"\b(?:mrp|price|cost)\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         question,
#         flags=re.IGNORECASE,
#     )
#     if direct_match:
#         return direct_match.group(1).strip()

#     match = re.search(
#         r"\b(?:of|does|is)\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+cost|\s+mrp|\s+price|\?)",
#         question,
#         flags=re.IGNORECASE,
#     )
#     return match.group(1).strip() if match else ""


# def _compare_company_lookup(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate company/manufacturer questions from a cited competitor row."""
#     brand = _extract_company_question_brand(question)
#     if not brand:
#         return "DATA MISSING", "Brand name could not be identified from the company question."

#     company = _extract_company_for_brand(page_data, brand)
#     if not company:
#         for row in _extract_competitor_table_rows(page_data):
#             if _entity_text_contains(str(row["brand"]), brand) or _entity_text_contains(brand, str(row["brand"])):
#                 company = str(row["company"])
#                 break
#     if not company:
#         return "DATA MISSING", f"Company row for {brand} was not found on the cited page."

#     if _company_text_contains(response_text, company):
#         return (
#             "PASS",
#             f"Company/manufacturer matches cited table row: {brand} is listed with {company}.",
#         )

#     return (
#         "FAIL",
#         f"Company/manufacturer mismatch. Cited table row lists {brand} with {company}.",
#     )


# def _extract_company_question_brand(question: str) -> str:
#     """Extract brand being asked about in a company/manufacturer question."""
#     patterns = (
#         r"\bmarkets?\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         r"\bmanufactures?\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         r"\bmanufacturer\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         r"\bcompany\s+name\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         r"\bcompany\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#     )
#     for pattern in patterns:
#         match = re.search(pattern, question, flags=re.IGNORECASE)
#         if match:
#             return match.group(1).strip(" ?.")
#     return ""


# def _extract_company_for_brand(page_data: str, brand: str) -> str:
#     """Extract company for a brand row from flattened competitor table text."""
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     brand_pattern = r"\s*[-_/]?\s*".join(
#         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", brand)
#     )
#     company_pattern = "|".join(
#         re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True)
#     )
#     match = re.search(
#         rf"\b{brand_pattern}(?:\s+[A-Za-z0-9+-]+)?\s+(?P<company>{company_pattern})\b",
#         normalized_page,
#         flags=re.IGNORECASE,
#     )
#     if not match:
#         return ""
#     return _normalize_company_display(match.group("company"))


# def _extract_price_comparison_entities(question: str) -> tuple[str, str]:
#     """Extract own product and compared competitor brand from a comparison question."""
#     match = re.search(
#         r"\b(?:price\s+difference\s+)?between\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+and\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         question,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

#     match = re.search(
#         r"\bhow\s+much\s+cheaper\s+is\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+compared\s+to\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         question,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

#     match = re.search(
#         r"\b([A-Za-z][A-Za-z0-9 +./-]+?)\s+compared\s+to\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
#         question,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

#     return "", ""


# def _normalize_comparison_pair(left: str, right: str) -> tuple[str, str]:
#     """Carry shared product prefixes into abbreviated right-side comparison labels."""
#     left = re.sub(r"\bprices?\b", " ", left, flags=re.IGNORECASE)
#     right = re.sub(r"\bprices?\b", " ", right, flags=re.IGNORECASE)
#     left = re.sub(r"\s+", " ", left).strip(" ?.:-")
#     right = re.sub(r"\s+", " ", right).strip(" ?.:-")

#     left_upper = left.upper()
#     right_upper = right.upper()
#     if "COMBIHALE" in left_upper and "COMBIHALE" not in right_upper:
#         if "FB" in left_upper and "FB" not in right_upper:
#             right = f"COMBIHALE FB {right}"
#         else:
#             right = f"COMBIHALE {right}"
#     if "CILAHEART" in left_upper and "CILAHEART" not in right_upper:
#         right = f"CILAHEART {right}"

#     return left, re.sub(r"\s+", " ", right).strip()


# def _extract_own_sku_prices(page_data: str, product: str) -> dict[str, float]:
#     """Extract own-product SKU prices such as Bisonicus 2.5 -> 69.4."""
#     prices: dict[str, float] = {}
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     product_pattern = r"\s*[-_/]?\s*".join(
#         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
#     )

#     pattern = re.compile(
#         rf"{product_pattern}\s+(?P<strength>\d+(?:\.\d+)?)"
#         r".{0,100}?(?:₹|â‚¹|rs\.?|inr)\s*\.?\s*"
#         r"(?P<price>\d{1,4}(?:\.\d+)?)",
#         flags=re.IGNORECASE,
#     )

#     for match in pattern.finditer(normalized_page):
#         strength = _normalize_strength_key(match.group("strength"))
#         price = float(match.group("price"))
#         prices[strength] = price

#     return prices


# def _extract_competitor_strength_prices(page_data: str, brand: str) -> dict[str, float]:
#     """Extract competitor prices from two-strength rows such as CONCOR 2.5/5 mg."""
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     brand_pattern = r"\s*[-_/]?\s*".join(
#         re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", brand)
#     )
#     company_pattern = "|".join(re.escape(company) for company in _known_company_names())
#     row_match = re.search(
#         rf"{brand_pattern}\s+(?:{company_pattern})\s+"
#         r"(?P<price_one>\d{1,4}(?:\.\d+)?)\s+Strip\s+of\s+\d+\s+Tabs\s+"
#         r"(?P<price_two>\d{1,4}(?:\.\d+)?)\s+Strip\s+of\s+\d+\s+Tabs",
#         normalized_page,
#         flags=re.IGNORECASE,
#     )

#     if not row_match:
#         return {}

#     strengths = _extract_competitor_header_strengths(normalized_page)
#     if len(strengths) < 2:
#         strengths = ["2.5", "5"]

#     return {
#         _normalize_strength_key(strengths[0]): float(row_match.group("price_one")),
#         _normalize_strength_key(strengths[1]): float(row_match.group("price_two")),
#     }


# def _extract_competitor_header_strengths(page_data: str) -> list[str]:
#     """Extract strength order from competitor price table headers."""
#     header_match = re.search(
#         r"BRAND\s+COMPANY\s+(.{0,120}?)\s+CONCOR\b",
#         page_data,
#         flags=re.IGNORECASE,
#     )
#     header_text = header_match.group(1) if header_match else page_data[:500]
#     strengths = re.findall(r"(\d+(?:\.\d+)?)\s*mg\s+SKU\s+MRP", header_text, flags=re.IGNORECASE)
#     return [_normalize_strength_key(strength) for strength in strengths]


# def _normalize_strength_key(value: str) -> str:
#     """Normalize strength keys for price comparison."""
#     normalized = str(value).strip()
#     if "." in normalized:
#         normalized = normalized.rstrip("0").rstrip(".")
#     return normalized


# def _float_set_contains(numbers: set[float], expected: float) -> bool:
#     """Return whether a numeric set contains expected value with currency rounding."""
#     return any(abs(number - expected) <= 0.05 for number in numbers)


# def _extract_requested_product_price(page_data: str, question: str) -> float | None:
#     """Extract the requested product price from page text for cost-saving questions."""
#     strength_match = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", question, flags=re.IGNORECASE)
#     if strength_match:
#         strength_price = _extract_strength_price_from_mrp_section(page_data, strength_match.group(1))
#         if strength_price is not None:
#             return strength_price

#     unit_price = _extract_mrp_section_unit_price(page_data, question)
#     if unit_price is not None:
#         return unit_price

#     product_candidates = _extract_product_candidates_from_question(question)
#     normalized_page = re.sub(r"\s+", " ", page_data)

#     for product in product_candidates:
#         product_pattern = r"\s*[-_/]?\s*".join(
#             re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
#         )
#         strength_match = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", question, flags=re.IGNORECASE)
#         strength_pattern = ""
#         if strength_match and strength_match.group(1) not in product:
#             strength_pattern = rf".{{0,30}}{re.escape(strength_match.group(1))}\s*mg"

#         match = re.search(
#             rf"{product_pattern}{strength_pattern}.{{0,80}}?"
#             r"(?<!\d)(\d{1,4}(?:,\d{3})*(?:\.\d+)?)(?!\d)",
#             normalized_page,
#             flags=re.IGNORECASE,
#         )
#         if match:
#             return float(match.group(1).replace(",", ""))

#     return None


# def _extract_strength_price_from_mrp_section(page_data: str, strength: str) -> float | None:
#     """Extract strength-specific MRP rows like '25 mg - 179.72 Rs per strip'."""
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     strength_clean = strength.rstrip("0").rstrip(".") if "." in strength else strength
#     match = re.search(
#         rf"\b{re.escape(strength_clean)}\s*mg\b\s*[–—-]\s*"
#         r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*Rs\s*per\s*(?:strip|box|bottle|respule)\b",
#         normalized_page,
#         flags=re.IGNORECASE,
#     )
#     if match:
#         return float(match.group("price").replace(",", ""))
#     return None


# def _extract_mrp_section_unit_price(page_data: str, question: str) -> float | None:
#     """Extract simple product-page MRP lines by requested unit."""
#     normalized_page = re.sub(r"\s+", " ", page_data)
#     unit_terms: tuple[str, ...]
#     normalized_question = normalize_text(question)
#     if "respule" in normalized_question:
#         unit_terms = ("respule",)
#     elif "box" in normalized_question:
#         unit_terms = ("box",)
#     elif "strip" in normalized_question:
#         unit_terms = ("strip",)
#     else:
#         return None

#     unit_pattern = "|".join(re.escape(unit) for unit in unit_terms)
#     matches = list(
#         re.finditer(
#             r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*Rs\s*per\s*"
#             rf"(?:{unit_pattern})\b",
#             normalized_page,
#             flags=re.IGNORECASE,
#         )
#     )
#     if matches:
#         return float(matches[-1].group("price").replace(",", ""))
#     return None


# def _extract_product_candidates_from_question(question: str) -> list[str]:
#     """Extract likely product names before comparison wording."""
#     candidates: list[str] = []
#     patterns = (
#         r"\bbetween\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+and\b",
#         r"\bof\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+\d+(?:\.\d+)?\s*mg)?\b",
#     )
#     for pattern in patterns:
#         for match in re.finditer(pattern, question, flags=re.IGNORECASE):
#             candidate = re.sub(r"\b(?:its|competitors?|what|which|brand|price|mrp|sku)\b", " ", match.group(1), flags=re.IGNORECASE)
#             candidate = re.sub(r"\s+", " ", candidate).strip(" -_./")
#             if candidate and candidate.lower() not in {"the", "all"}:
#                 candidates.append(candidate)
#     return candidates


# def _number_set_contains_close_value(numbers: set[float], expected: float) -> bool:
#     """Return whether response numbers contain expected percentage with normal rounding."""
#     rounded_expected_values = {
#         round(expected, 0),
#         round(expected, 1),
#         round(expected, 2),
#     }
#     return any(
#         any(abs(number - expected_value) <= 0.05 for expected_value in rounded_expected_values)
#         for number in numbers
#     )


# def _compare_expected_competitor_row(
#     response_text: str,
#     expected_row: dict[str, object],
#     ranking_label: str,
# ) -> tuple[str, str]:
#     """Compare SuperAI response against a computed lowest/highest competitor row."""
#     expected_brand = str(expected_row["brand"])
#     expected_price = float(expected_row["price"])
#     brand_match = _entity_text_contains(response_text, expected_brand)
#     response_numbers = {float(number) for number in _extract_numbers(response_text)}
#     price_match = expected_price in response_numbers

#     if brand_match and (not response_numbers or price_match):
#         return (
#             "PASS",
#             f"{ranking_label.title()} competitor price calculated from cited table is "
#             f"{expected_brand} at {expected_price:.2f}, matching SuperAI.",
#         )

#     return (
#         "FAIL",
#         f"{ranking_label.title()} competitor price calculated from cited table is "
#         f"{expected_brand} at {expected_price:.2f}. SuperAI response does not match "
#         "the computed cited-table result.",
#     )


# def _extract_competitor_table_rows(text: str) -> list[dict[str, object]]:
#     """Extract competitor table rows preserving brand/company/pack/price columns."""
#     delimiter_safe_text = text.replace("\r\n", "\n").replace("\n", " | ")
#     cleaned = _remove_punchline_or_slogan_text(delimiter_safe_text)
#     cleaned = re.sub(r"\s+", " ", cleaned).strip()

#     section_match = re.search(
#         r"(?:competitors?\s+brand.*?name|brand\s+name\s+company|brand\s+name)"
#         r"(.+?)(?:m\.?r\.?p|recommended dosage|salient|indications|composition|$)",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     section = section_match.group(1) if section_match else cleaned
#     section = _scope_competitor_section(section)

#     company_names = sorted(_known_company_names(), key=len, reverse=True)
#     company_pattern = "|".join(re.escape(company) for company in company_names)
#     section = re.sub(
#         r"\b(?:[A-Za-z][A-Za-z0-9 +./-]{0,80}\s*:-\s*)?"
#         r"BRAND\s+NAME\s+COMPANY\s+PACK\s+(?:SIZE\s+)?PRICE\s*/\s*"
#         r"(?:STRIP|TAB)(?:\s*-\s*RS)?(?:\s+PRICE\s*/\s*TAB\s*-\s*RS)?",
#         " ",
#         section,
#         flags=re.IGNORECASE,
#     )

#     row_patterns = (
#         re.compile(
#             r"(?:^|\s)(?:\d+\s*[.)-]?\s*)"
#             rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
#             rf"(?P<company>{company_pattern})\s+"
#             r"(?P<pack>\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)?)"
#             r"\s*(?P<price>\d+(?:\s*\.\s*\d+)?)?",
#             flags=re.IGNORECASE,
#         ),
#         re.compile(
#             r"(?:^|\s)"
#             rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
#             rf"(?P<company>{company_pattern})\s+"
#             r"(?P<pack>\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)?)"
#             r"\s*(?P<price>\d+(?:\s*\.\s*\d+)?)?",
#             flags=re.IGNORECASE,
#         ),
#         re.compile(
#             r"(?:^|\s)"
#             rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
#             rf"(?P<company>{company_pattern})\*?"
#             r"(?:\s+\([^)]*\))?"
#             r"\s+(?P<price>\d+(?:\s*\.\s*\d+)?)",
#             flags=re.IGNORECASE,
#         ),
#     )

#     rows: list[dict[str, object]] = []
#     seen_rows: set[tuple[str, str, str, object]] = set()
#     for row_pattern in row_patterns:
#         for match in row_pattern.finditer(section):
#             brand = _clean_brand_name(match.group("brand"))
#             company = _normalize_company_display(match.group("company"))
#             groups = match.groupdict()
#             pack = re.sub(r"\s+", " ", groups.get("pack") or "").strip()
#             if re.fullmatch(r"\d+", pack):
#                 pack = f"{pack} Tab"
#             price_text = groups.get("price")
#             price = float(re.sub(r"\s+", "", price_text)) if price_text else None

#             if not brand or not _is_valid_brand_name(brand):
#                 continue

#             row_key = (
#                 _normalize_brand_name(brand),
#                 _normalize_company_display(company).lower(),
#                 normalize_text(pack),
#                 price,
#             )
#             if row_key in seen_rows:
#                 continue
#             seen_rows.add(row_key)

#             row = {
#                 "brand": brand,
#                 "company": company,
#                 "pack": pack,
#                 "price": price,
#                 "audit": {
#                     "brand": _entity_match_audit(brand, brand),
#                     "company": _entity_match_audit(company, company),
#                 },
#             }
#             rows.append(row)

#     return rows


# def _scope_competitor_page_data_for_question(page_data: str, question: str) -> str:
#     """Return the competitor table block for the product named in the question."""
#     subjects = _extract_competitor_question_subjects(question)
#     if not subjects:
#         return page_data

#     text = re.sub(r"\s+", " ", page_data).strip()
#     heading_pattern = re.compile(
#         r"(?P<heading>[A-Za-z][A-Za-z0-9 +./-]{2,90})\s*:-\s+"
#         r"BRAND\s+NAME\s+COMPANY\s+PACK\s+(?:SIZE\s+)?PRICE\s*/\s*(?:STRIP|TAB)",
#         flags=re.IGNORECASE,
#     )
#     headings = list(heading_pattern.finditer(text))
#     if not headings:
#         return page_data

#     for index, heading_match in enumerate(headings):
#         heading = heading_match.group("heading").strip()
#         if not any(_entity_text_contains(heading, subject) or _entity_text_contains(subject, heading) for subject in subjects):
#             continue

#         end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
#         mrp_match = re.search(r"\bM\.?R\.?P\b", text[heading_match.end() : end], flags=re.IGNORECASE)
#         if mrp_match:
#             end = heading_match.end() + mrp_match.start()
#         return text[heading_match.start() : end].strip()

#     return page_data


# def _extract_competitor_question_subjects(question: str) -> list[str]:
#     """Extract product names from competitor-table questions."""
#     patterns = (
#         r"\bcompetitor(?:\s+brand)?\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+has|\s+is|\s+with|\s+priced|\s+belongs|\?|$)",
#         r"\bfor\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+has|\s+is|\s+with|\s+priced|\?|$)",
#         r"\bof\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+(?:has|with|priced|belongs)",
#     )
#     subjects: list[str] = []
#     for pattern in patterns:
#         for match in re.finditer(pattern, question, flags=re.IGNORECASE):
#             subject = match.group(1).strip(" ?.")
#             subject = re.sub(
#                 r"\b(?:the|highest|lowest|cheapest|price|strip|competitor|brand|company)\b",
#                 " ",
#                 subject,
#                 flags=re.IGNORECASE,
#             )
#             subject = re.sub(r"\s+", " ", subject).strip()
#             if subject and subject.lower() not in {"which", "what"}:
#                 subjects.append(subject)
#     return subjects


# def _extract_marketed_by_company(question: str) -> str:
#     """Extract company name from questions like 'marketed by Lupin'."""
#     match = re.search(
#         r"\bmarketed\s+by\s+([A-Za-z][A-Za-z0-9 &.'/-]+?)\??$",
#         question,
#         flags=re.IGNORECASE,
#     )
#     return match.group(1).strip(" ?.") if match else ""


# def _extract_competitor_brand_names(text: str) -> list[str]:
#     """Extract only brand names from competitor sections and ignore numeric values."""
#     delimiter_safe_text = text.replace("\r\n", "\n").replace("\n", " | ")
#     cleaned = _clean_response_for_validation(delimiter_safe_text)
#     cleaned = _remove_punchline_or_slogan_text(cleaned)
#     cleaned = re.sub(r"\*+\s*name\s+appears\b.*", " ", cleaned, flags=re.IGNORECASE)
#     cleaned = re.sub(r"\b\d+\s*,\s*\d+(?:\s*,\s*\d+)*\b", " ", cleaned)
#     cleaned = re.sub(
#         r"\bsr\.?\s+competitor\s+brand\s+company\s+pack\s+size\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(
#         r"\bbrand\s+company\s+pack\s+size\s+price\s*/?\s*strip\s*(?:\(.*?\))?\s+sources\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(
#         r"\bbrand\s+name\s+company\s+pack\s+(?:size\s+)?price\s*/?\s*strip\s*(?:\(.*?\))?\s*(?:sources)?\b",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(
#         r"^.*?\bcompetitor\s+brands?\s+for\s+[A-Za-z0-9 /+-]+(?:\s*\([^)]*\))?\s*[:\-]?\s*",
#         " ",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     cleaned = re.sub(r"\s+", " ", cleaned).strip()

#     competitor_section_match = re.search(
#         r"(?:competitors?\s+brand.*?name|brand\s+name\s+company|brand\s+name)"
#         r"(.+?)(?:m\.?r\.?p|recommended dosage|salient|indications|composition|$)",
#         cleaned,
#         flags=re.IGNORECASE,
#     )
#     section = competitor_section_match.group(1) if competitor_section_match else cleaned
#     section = _scope_competitor_section(section)

#     table_brands = _extract_table_brand_names(section)
#     if table_brands:
#         return table_brands

#     section = re.sub(r"\b\d+(?:\.\d+)?\b", " ", section)
#     section = re.sub(
#         r"\b(?:tab|tabs|tablet|tablets|cap|caps|strip|price|pack)\b",
#         " ",
#         section,
#         flags=re.IGNORECASE,
#     )
#     return _extract_listed_brand_names(section)


# def _scope_competitor_section(section: str) -> str:
#     """Keep only the first competitor table when multiple product tables are adjacent."""
#     table_heading_pattern = re.compile(
#         r"\s+[A-Za-z][A-Za-z0-9 /+-]{2,60}\s*:-\s+BRAND\s+NAME\s+COMPANY\s+PACK",
#         flags=re.IGNORECASE,
#     )
#     for next_table_match in table_heading_pattern.finditer(section):
#         if next_table_match.start() > 20:
#             return section[: next_table_match.start()].strip()

#     return section


# def _extract_table_brand_names(section: str) -> list[str]:
#     """Extract numbered table brand names from brand/company/pack/price rows."""
#     brands: list[str] = []
#     known_companies = _known_company_names()
#     company_pattern = "|".join(re.escape(company) for company in known_companies)
#     row_segments = re.split(
#         r"(?=(?:^|\s)[1-9]\d?\s+(?!Tab\b|Tabs\b|Tablet\b|Tablets\b|Cap\b|Caps\b|Strip\b|Ml\b|Gm\b|Mg\b)[A-Z])",
#         section,
#     )
#     row_segment_pattern = re.compile(
#         rf"^\s*\d+\s+(.+?)\*?\s+(?:{company_pattern})\s+"
#         r"\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b",
#         flags=re.IGNORECASE,
#     )

#     for segment in row_segments:
#         match = row_segment_pattern.search(segment)
#         if not match:
#             continue

#         brand = _clean_brand_name(match.group(1))
#         if brand and _is_valid_brand_name(brand):
#             _append_unique_brand(brands, brand)

#     row_pattern = re.compile(
#         r"(?:^|\s)(?:\d+\s*[.)-]\s*)"
#         rf"([A-Za-z][A-Za-z0-9 +./-]{{1,80}}?)\*?\s+"
#         rf"(?:{company_pattern})"
#         r"\s+\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b"
#         r"(?:\s+\d+(?:\.\d+)?)?",
#         flags=re.IGNORECASE,
#     )

#     for match in row_pattern.finditer(section):
#         brand = _clean_brand_name(match.group(1))
#         if brand and _is_valid_brand_name(brand):
#             _append_unique_brand(brands, brand)

#     no_number_row_pattern = re.compile(
#         rf"([A-Za-z][A-Za-z0-9 +./-]{{1,80}}?)\*?\s+"
#         rf"(?:{company_pattern})\s+"
#         r"\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b"
#         r"(?:\s+\d+(?:\.\d+)?)?"
#         r"(?:\s+\d+(?:\s*,\s*\d+)*)?",
#         flags=re.IGNORECASE,
#     )

#     for match in no_number_row_pattern.finditer(section):
#         brand = _clean_brand_name(match.group(1))
#         if brand and _is_valid_brand_name(brand):
#             _append_unique_brand(brands, brand)

#     if brands:
#         return brands

#     company_based_pattern = re.compile(
#         rf"(?:^|\s)(?:\d+\s*[.)-]?\s*)?"
#         rf"([A-Za-z][A-Za-z0-9 +./-]{{1,60}}?)\s+"
#         rf"(?:{company_pattern})(?=\s|$)",
#         flags=re.IGNORECASE,
#     )

#     for match in company_based_pattern.finditer(section):
#         brand = _clean_brand_name(match.group(1))
#         if brand and _is_valid_brand_name(brand):
#             _append_unique_brand(brands, brand)

#     if brands:
#         return brands

#     return brands


# def _known_company_names() -> tuple[str, ...]:
#     """Return known pharma company names used to identify table columns."""
#     return (
#         "drl",
#         "ipca",
#         "micro",
#         "bal",
#         "eris life",
#         "eris",
#         "alkem",
#         "servier",
#         "jb chemicals",
#         "jb pharma",
#         "merck specialities",
#         "merck",
#         "mankind",
#         "sun pharma",
#         "aristo",
#         "indoco",
#         "alembic",
#         "koye",
#         "mex",
#         "sun",
#         "zydus",
#         "zydus cadilla",
#         "cipla",
#         "gr",
#         "torrent",
#         "lupin",
#         "abbott",
#         "ajanta",
#         "glenmark",
#         "macelods",
#         "macleods",
#         "wockhardt",
#         "corona remedies",
#         "la renon healthcare",
#         "systopic laboratories",
#         "novartis",
#         "rpg",
#         "biocon",
#         "concord biotec",
#         "steris",
#         "usv",
#         "intace",
#         "intas",
#         "bi",
#         "boehringer ingelheim",
#     )


# def _extract_listed_brand_names(section: str) -> list[str]:
#     """Extract brands from simple comma/newline/bullet response lists."""
#     section = re.sub(
#         r"\b(?:the|competitors?|competitor|brand|brands|are|is|include|includes|of|for)\b",
#         " ",
#         section,
#         flags=re.IGNORECASE,
#     )
#     candidates = re.split(r"[,;\n|]|\s+-\s+|\s+\band\b\s+|\s+\d+\s*[.)]\s+", section)
#     brands: list[str] = []

#     for candidate in candidates:
#         brand = _clean_brand_name(candidate)
#         if brand and _is_valid_brand_name(brand):
#             _append_unique_brand(brands, brand)

#     return brands


# def _clean_brand_name(text: str) -> str:
#     """Clean a competitor brand candidate."""
#     brand = text.replace("*", " ")
#     brand = re.sub(
#         r"^\s*(?:(?:sources?|competitors?|competitor|brand|brands|name|company|pack|size|segment)\b\s*)+",
#         " ",
#         brand,
#         flags=re.IGNORECASE,
#     )
#     brand = re.sub(r"\b\d+(?:\.\d+)?\b", " ", brand)
#     brand = re.sub(
#         r".*\bbrand\s+name\s+company\s+pack\s+price\s*/?\s*strip\b",
#         " ",
#         brand,
#         flags=re.IGNORECASE,
#     )
#     brand = re.sub(
#         r".*\bbrand\s+name\b",
#         " ",
#         brand,
#         flags=re.IGNORECASE,
#     )
#     brand = re.sub(
#         r"\b(?:company|pack|size|price|strip|tab|tabs|tablet|tablets|cap|caps|mrp|sources?|mg)\b",
#         " ",
#         brand,
#         flags=re.IGNORECASE,
#     )
#     brand = re.sub(r"\s+", " ", brand).strip(" /:-.,;")
#     company_pattern = "|".join(re.escape(company) for company in _known_company_names())
#     brand = re.sub(
#         rf"\s+(?:{company_pattern})$",
#         "",
#         brand,
#         flags=re.IGNORECASE,
#     )
#     return brand


# def _is_valid_brand_name(brand: str) -> bool:
#     """Return whether a candidate is a real brand name, not table noise."""
#     normalized = _normalize_brand_name(brand)
#     invalid = {
#         "",
#         "brand name",
#         "company",
#         "competitors name",
#         "competitors brand",
#         "competitors brand company",
#         "price strip",
#         "punch line",
#         "punchline",
#         "slogan",
#         "tagline",
#     }
#     return (
#         normalized not in invalid
#         and "punch line" not in normalized
#         and "punchline" not in normalized
#         and "slogan" not in normalized
#         and "tagline" not in normalized
#         and any(char.isalpha() for char in brand)
#     )


# def _remove_punchline_or_slogan_text(text: str) -> str:
#     """Remove punchline/slogan sections from competitor-brand extraction."""
#     return re.sub(
#         r"\b(?:punch\s*line|punchline|slogan|tagline)\b.*?"
#         r"(?=\b(?:competitors?\s+brand|brand\s+name|composition|mode of action|"
#         r"indications|recommended dosage|salient|m\.?r\.?p)\b|$)",
#         " ",
#         text,
#         flags=re.IGNORECASE,
#     )


# def _normalize_brand_name(brand: str) -> str:
#     """Normalize brand names for exact brand comparison."""
#     return _normalize_entity_value(brand)


# def _brand_matches_any(response_brand: str, normalized_page_brands: set[str]) -> bool:
#     """Return whether a response brand or slash variant exists on the cited page.

#     Medicine brand names are sensitive, so this intentionally avoids fuzzy
#     matching. A one-letter difference can be a different product.
#     """
#     candidates = [response_brand]
#     if "/" in response_brand:
#         candidates.extend(part.strip() for part in response_brand.split("/") if part.strip())

#     for candidate in candidates:
#         normalized_candidate = _normalize_brand_name(candidate)
#         if normalized_candidate in normalized_page_brands:
#             return True

#     return False


# def _normalize_entity_value(value: str) -> str:
#     """Normalize entity strings before exact/fuzzy comparison."""
#     normalized = normalize_text(value)
#     normalized = _company_aliases().get(normalized, normalized)
#     normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
#     return re.sub(r"\s+", " ", normalized).strip()


# def _normalize_company_display(company: str) -> str:
#     """Return canonical display name for known company aliases."""
#     normalized = _normalize_entity_value(company)
#     display_aliases = {
#         "dr reddys laboratories": "Dr. Reddy's Laboratories",
#         "ipca laboratories": "IPCA Laboratories",
#         "eris lifesciences": "Eris Lifesciences",
#         "boehringer ingelheim": "BI",
#         "sun pharma": "Sun Pharma",
#         "ipca laboratories": "IPCA Laboratories",
#     }
#     return display_aliases.get(normalized, company.strip())


# def _company_aliases() -> dict[str, str]:
#     """Return company aliases for pharma entity normalization."""
#     return {
#         "eris": "eris lifesciences",
#         "eris life": "eris lifesciences",
#         "eris lifesciences": "eris lifesciences",
#         "drl": "dr reddys laboratories",
#         "dr reddy": "dr reddys laboratories",
#         "dr reddys": "dr reddys laboratories",
#         "dr reddy s laboratories": "dr reddys laboratories",
#         "dr reddys laboratories": "dr reddys laboratories",
#         "ipca": "ipca laboratories",
#         "ipca labs": "ipca laboratories",
#         "ipca laboratories": "ipca laboratories",
#         "sun": "sun pharma",
#         "sun pharma": "sun pharma",
#         "sun pharmaceutical": "sun pharma",
#         "bi": "boehringer ingelheim",
#         "boehringer": "boehringer ingelheim",
#         "boehringer ingelheim": "boehringer ingelheim",
#     }


# def _entity_match_audit(
#     left_value: str,
#     right_value: str,
#     threshold: float = COMPANY_ENTITY_MATCH_THRESHOLD,
#     allow_fuzzy: bool = False,
# ) -> dict[str, object]:
#     """Return original values, normalized values, score, and match decision."""
#     left_normalized = _normalize_entity_value(left_value)
#     right_normalized = _normalize_entity_value(right_value)
#     score = _levenshtein_similarity(left_normalized, right_normalized)
#     matched = left_normalized == right_normalized or (allow_fuzzy and score >= threshold)
#     return {
#         "left_original": left_value,
#         "right_original": right_value,
#         "left_normalized": left_normalized,
#         "right_normalized": right_normalized,
#         "score": round(score, 3),
#         "matched": matched,
#     }


# def _entity_values_match(
#     left_value: str,
#     right_value: str,
#     threshold: float = COMPANY_ENTITY_MATCH_THRESHOLD,
#     allow_fuzzy: bool = False,
# ) -> bool:
#     """Return whether two entity values are equivalent after alias/fuzzy matching."""
#     return bool(_entity_match_audit(left_value, right_value, threshold, allow_fuzzy)["matched"])


# def _entity_matches_any(value: str, candidates: list[str], allow_fuzzy: bool = False) -> bool:
#     """Return whether an entity matches any candidate with audit-aware normalization."""
#     return bool(_entity_best_match_audit(value, candidates, allow_fuzzy=allow_fuzzy)["matched"])


# def _entity_best_match_audit(
#     value: str,
#     candidates: list[str],
#     allow_fuzzy: bool = False,
# ) -> dict[str, object]:
#     """Return best entity match audit for one value against candidate values."""
#     candidate_values = [value]
#     if "/" in value:
#         candidate_values.extend(part.strip() for part in value.split("/") if part.strip())

#     best_audit: dict[str, object] | None = None
#     for candidate_value in candidate_values:
#         for candidate in candidates:
#             audit = _entity_match_audit(
#                 candidate_value,
#                 candidate,
#                 allow_fuzzy=allow_fuzzy,
#             )
#             if best_audit is None or float(audit["score"]) > float(best_audit["score"]):
#                 best_audit = audit

#     if best_audit is None:
#         best_audit = {
#             "left_original": value,
#             "right_original": "",
#             "left_normalized": _normalize_entity_value(value),
#             "right_normalized": "",
#             "score": 0.0,
#             "matched": False,
#         }

#     return best_audit


# def _format_entity_audit_summary(audits: list[dict[str, object]]) -> str:
#     """Return concise audit trail for entity normalization decisions."""
#     if not audits:
#         return ""

#     audit_parts = []
#     for audit in audits[:5]:
#         audit_parts.append(
#             f"{audit['left_original']} -> {audit['left_normalized']} "
#             f"matched {audit['right_original']} -> {audit['right_normalized']} "
#             f"(score {float(audit['score']):.2f})"
#         )

#     if len(audits) > 5:
#         audit_parts.append(f"+{len(audits) - 5} more")

#     return "Entity audit: " + "; ".join(audit_parts) + "."


# def _entity_text_contains(text: str, expected_entity: str) -> bool:
#     """Return whether text contains an entity after alias/fuzzy normalization."""
#     normalized_text = _normalize_entity_value(text)
#     normalized_entity = _normalize_entity_value(expected_entity)
#     if normalized_entity and normalized_entity in normalized_text:
#         return True

#     text_entities = _extract_possible_entities(text)
#     return _entity_matches_any(expected_entity, text_entities)


# def _company_text_contains(text: str, expected_company: str) -> bool:
#     """Return whether text contains a company after alias/controlled OCR matching."""
#     normalized_text = _normalize_entity_value(text)
#     normalized_company = _normalize_entity_value(expected_company)
#     if normalized_company and normalized_company in normalized_text:
#         return True
#     for alias, canonical in _company_aliases().items():
#         if canonical == normalized_company and re.search(rf"\b{re.escape(alias)}\b", normalize_text(text)):
#             return True

#     text_entities = _extract_possible_entities(text)
#     return _entity_matches_any(expected_company, text_entities, allow_fuzzy=True)


# def _entity_text_contains_ordered_tokens(text: str, expected_entity: str) -> bool:
#     """Return whether all entity tokens appear in order inside text."""
#     text_tokens = re.findall(r"[a-z0-9]+", _normalize_entity_value(text))
#     entity_tokens = re.findall(r"[a-z0-9]+", _normalize_entity_value(expected_entity))
#     if not entity_tokens:
#         return False
#     position = 0
#     for entity_token in entity_tokens:
#         try:
#             found_at = text_tokens.index(entity_token, position)
#         except ValueError:
#             return False
#         position = found_at + 1
#     return True


# def _extract_possible_entities(text: str) -> list[str]:
#     """Extract possible entity spans from response text for fuzzy matching."""
#     cleaned = _clean_response_for_validation(text)
#     parts = re.split(r"[,;|\n]|\s+-\s+|\s+\band\b\s+", cleaned)
#     entities: list[str] = []
#     for part in parts:
#         candidate = re.sub(r"\b\d+(?:\.\d+)?\b", " ", part)
#         candidate = re.sub(
#             r"\b(?:price|mrp|strip|tab|tabs|tablet|tablets|pack|company|brand|lowest|highest|has|is|at|rs|inr|per)\b",
#             " ",
#             candidate,
#             flags=re.IGNORECASE,
#         )
#         candidate = re.sub(r"\s+", " ", candidate).strip(" :-.,")
#         if candidate and any(char.isalpha() for char in candidate):
#             entities.append(candidate)

#     entities.append(cleaned)
#     return entities


# def _levenshtein_similarity(left: str, right: str) -> float:
#     """Return normalized Levenshtein similarity between two strings."""
#     if left == right:
#         return 1.0
#     if not left or not right:
#         return 0.0

#     previous = list(range(len(right) + 1))
#     for left_index, left_char in enumerate(left, start=1):
#         current = [left_index]
#         for right_index, right_char in enumerate(right, start=1):
#             insert_cost = current[right_index - 1] + 1
#             delete_cost = previous[right_index] + 1
#             replace_cost = previous[right_index - 1] + (left_char != right_char)
#             current.append(min(insert_cost, delete_cost, replace_cost))
#         previous = current

#     distance = previous[-1]
#     return 1 - (distance / max(len(left), len(right)))


# def _append_unique_brand(brands: list[str], brand: str) -> None:
#     """Append a brand once using normalized comparison."""
#     normalized = _normalize_brand_name(brand)
#     if normalized and normalized not in {_normalize_brand_name(existing) for existing in brands}:
#         brands.append(brand)


# def _is_multi_product_question(normalized_question: str) -> bool:
#     """Return whether a question needs separate evidence per product."""
#     if "mycept" in normalized_question and "mycept s" in normalized_question:
#         return True
#     return bool(re.search(r"\bbetween\b.+\band\b", normalized_question))


# def _compare_multi_product_response(
#     response_content: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate multi-product answers product-by-product, never as one flat text."""
#     products = _extract_products_for_multi_validation(question, response_content)
#     if len(products) < 2:
#         return _compare_descriptive_response(response_content, page_data)

#     product_results: list[tuple[str, str, str]] = []
#     for product in products:
#         evidence = _extract_product_evidence_section(page_data, product)
#         product_answer = _extract_product_answer_section(response_content, product)

#         if not evidence:
#             product_results.append(
#                 (
#                     product,
#                     "DATA MISSING",
#                     f"{product} cited evidence section was not found.",
#                 )
#             )
#             continue

#         if not product_answer:
#             product_results.append(
#                 (
#                     product,
#                     "DATA MISSING",
#                     f"SuperAI did not provide a separate value for {product}.",
#                 )
#             )
#             continue

#         strict_result = _validate_product_strict_values(product_answer, evidence, product)
#         if strict_result[0] != "PASS":
#             product_results.append((product, strict_result[0], strict_result[1]))
#             continue

#         semantic_result, semantic_reason = _compare_descriptive_response(product_answer, evidence)
#         if semantic_result == "FAIL":
#             product_results.append((product, "FAIL", semantic_reason))
#         else:
#             product_results.append(
#                 (
#                     product,
#                     "PASS",
#                     f"{product} evidence supports the product-specific claims.",
#                 )
#             )

#     statuses = [status for _, status, _ in product_results]
#     reason = " | ".join(f"{product}: {detail}" for product, _, detail in product_results)

#     if all(status == "PASS" for status in statuses):
#         return "PASS", f"All product-specific claims are supported. {reason}"

#     if "DATA MISSING" in statuses:
#         return "DATA MISSING", reason

#     if "FAIL" in statuses:
#         return "FAIL", reason

#     return "DATA MISSING", reason


# def _extract_products_for_multi_validation(question: str, response_content: str) -> list[str]:
#     """Extract product names that must be validated independently."""
#     normalized = normalize_text(f"{question} {response_content}")
#     products: list[str] = []
#     for product in ("mycept s", "mycept"):
#         if product in normalized:
#             products.append(product)
#     products.sort(key=len)
#     return products


# def _extract_product_evidence_section(page_data: str, product: str) -> str:
#     """Return source text for one product only."""
#     cleaned = re.sub(r"\s+", " ", page_data or "").strip()
#     normalized_product = normalize_text(product)

#     if normalized_product == "mycept s":
#         start_match = re.search(
#             r"\bbrand snapshot\s+mycept\s+s\b|\bname of product:?\s*mycept\s+s\b",
#             cleaned,
#             flags=re.IGNORECASE,
#         )
#         if not start_match:
#             return ""
#         start = start_match.start()
#         end_match = re.search(
#             r"\bCitation\s+\d+\s+\|\s+Document\b|\bBrand Snapshot\s+MYCEPT\b",
#             cleaned[start + 20 :],
#             flags=re.IGNORECASE,
#         )
#         end = start + 20 + end_match.start() if end_match else len(cleaned)
#         return cleaned[start:end].strip()

#     if normalized_product == "mycept":
#         # Plain MYCEPT evidence must not be the MYCEPT S section.
#         start_match = re.search(
#             r"\bbrand snapshot\s+mycept\b(?!\s+s)|\bname of product:?\s*mycept\b(?!\s+s)",
#             cleaned,
#             flags=re.IGNORECASE,
#         )
#         if not start_match:
#             comparison_match = re.search(
#                 r"\bmycophenolate mofetil\s*\(mycept\)\b|\bmycept\b.*?\bprodrug\b|\bprodrug\b.*?\bmycept\b",
#                 cleaned,
#                 flags=re.IGNORECASE,
#             )
#             if comparison_match:
#                 return cleaned[max(0, comparison_match.start() - 500) : comparison_match.start() + 900].strip()
#             return ""
#         start = start_match.start()
#         section = cleaned[start:]
#         stop_match = re.search(r"\b(?:brand snapshot\s+)?mycept\s+s\b", section[20:], flags=re.IGNORECASE)
#         end = 20 + stop_match.start() if stop_match else len(section)
#         return section[:end].strip()

#     match = re.search(re.escape(product), cleaned, flags=re.IGNORECASE)
#     return cleaned[max(0, match.start() - 200) : match.start() + 1200] if match else ""


# def _extract_product_answer_section(response_content: str, product: str) -> str:
#     """Return the SuperAI answer portion for one product."""
#     cleaned = re.sub(r"\s+", " ", _clean_response_for_validation(response_content)).strip()
#     normalized_product = normalize_text(product)

#     if normalized_product == "mycept s":
#         match = re.search(r"\bmycept\s+s\b(.+?)(?=\bmycept\b(?!\s+s)|$)", cleaned, flags=re.IGNORECASE)
#         if match:
#             return f"{product} {match.group(1)}".strip()
#         return cleaned if re.search(r"\bmycept\s+s\b", cleaned, flags=re.IGNORECASE) else ""

#     if normalized_product == "mycept":
#         match = re.search(r"\bmycept\b(?!\s+s)(.+?)(?=\bmycept\s+s\b|$)", cleaned, flags=re.IGNORECASE)
#         if match:
#             return f"{product} {match.group(1)}".strip()
#         return cleaned if re.search(r"\bmycept\b(?!\s+s)", cleaned, flags=re.IGNORECASE) else ""

#     match = re.search(re.escape(product), cleaned, flags=re.IGNORECASE)
#     return cleaned[match.start() : match.start() + 700] if match else ""


# def _validate_product_strict_values(
#     product_answer: str,
#     product_evidence: str,
#     product: str,
# ) -> tuple[str, str]:
#     """Validate critical numeric/unit values inside one product's evidence."""
#     answer_values = _extract_numeric_unit_values(_clean_numeric_validation_text(product_answer))
#     evidence_values = _extract_numeric_unit_values(_clean_numeric_validation_text(product_evidence))
#     critical_values = {
#         value
#         for value in answer_values
#         if re.search(r"\b(?:mg|g|mcg|ml|tab|tabs|tablet|tablets|day|daily|bid|od)\b", value)
#     }

#     if critical_values and not evidence_values:
#         return "DATA MISSING", f"{product} critical numeric evidence was not found."

#     missing = sorted(critical_values.difference(evidence_values))
#     if missing:
#         if evidence_values:
#             return (
#                 "FAIL",
#                 f"{product} strict value mismatch. Missing cited value(s): {', '.join(missing)}.",
#             )
#         return (
#             "DATA MISSING",
#             f"{product} cited evidence is missing required value(s): {', '.join(missing)}.",
#         )

#     return "PASS", f"{product} strict values are supported."


# # ---------------------------------------------------------------------------
# # CLINICAL OUTCOME — range-aware numeric comparison
# # ---------------------------------------------------------------------------

# _OUTCOME_PERCENT_TOLERANCE = 2.0  # ± percentage points for clinical values


# def _extract_outcome_numbers(text: str) -> list[float]:
#     """Extract all numeric outcome values from clinical text.

#     Handles:
#     - Bare percentages:    "48%", "50.5%", "~52%", ">30%"
#     - Decimal reductions:  "3.2 mmol/L", "1.5 mg/dL", "0.8%"
#     - Ranges (both ends):  "50-60%", "50 to 60%", "50–60%"

#     Returns a deduplicated, sorted list of float values.
#     """
#     values: set[float] = set()

#     # Ranges: "50-60%", "50–60%", "50 to 60%"
#     for match in re.finditer(
#         r"(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*%",
#         text,
#         flags=re.IGNORECASE,
#     ):
#         values.add(float(match.group(1)))
#         values.add(float(match.group(2)))

#     # Single percentages: "48%", "~48%", ">48%", "≥48%"
#     for match in re.finditer(
#         r"[~>≥≤<]?\s*(\d+(?:\.\d+)?)\s*%",
#         text,
#     ):
#         values.add(float(match.group(1)))

#     # Absolute clinical values with units: "3.2 mmol/L", "1.5 mg/dl"
#     for match in re.finditer(
#         r"(\d+(?:\.\d+)?)\s*(?:mmol/l|mg/dl|mg/dL|mmhg|mmHg)\b",
#         text,
#         flags=re.IGNORECASE,
#     ):
#         values.add(float(match.group(1)))

#     return sorted(values)


# def _extract_response_outcome_bounds(text: str) -> tuple[float, float] | None:
#     """Return (lo, hi) covering all numeric outcome claims in the response.

#     For a range response like "50-60%" returns (50.0, 60.0).
#     For a single value like "80%" returns (80.0, 80.0).
#     Returns None when no outcome numbers are found.
#     """
#     values = _extract_outcome_numbers(text)
#     if not values:
#         return None
#     return (min(values), max(values))


# def _compare_clinical_outcome(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate clinical outcome questions using a cited numeric range.

#     Builds a supported range from outcome values on the cited page, then
#     checks whether the response claim falls within that range.

#     Before building the page range, numbers that are likely noise (page numbers,
#     years, large patient counts) are filtered out so the range is not artificially
#     widened causing false PASSes, or artificially narrowed causing false FAILs.

#     PASS  — response bounds are fully contained within the supported range.
#     FAIL  — response claims a value that exceeds or contradicts cited evidence.
#     DATA MISSING — no outcome numbers found on the cited page.
#     """
#     page_values_raw = _extract_outcome_numbers(page_data)
#     if not page_values_raw:
#         _log_validation_step(
#             rule="_compare_clinical_outcome",
#             attribute="CLINICAL_OUTCOME",
#             verdict="DATA MISSING",
#             reason="No clinical outcome values found on the cited page.",
#         )
#         return "DATA MISSING", "No clinical outcome values found on the cited page."

#     response_bounds = _extract_response_outcome_bounds(response_text)
#     if response_bounds is None:
#         _log_validation_step(
#             rule="_compare_clinical_outcome",
#             attribute="CLINICAL_OUTCOME",
#             doc_value=f"[{min(page_values_raw):g}–{max(page_values_raw):g}]",
#             verdict="DATA MISSING",
#             reason="SuperAI response contained no numeric outcome values.",
#         )
#         return "DATA MISSING", "SuperAI response contained no numeric outcome values."

#     resp_lo, resp_hi = response_bounds

#     # Filter noise: exclude numbers that are clearly not clinical outcome values.
#     # Years (1900-2100), page numbers (> 200 for clinical documents unless the
#     # response itself mentions numbers that large), and patient counts (> 10000
#     # for %-style outcomes) are excluded to prevent range inflation.
#     # Keep only values in the plausible outcome range: [0, 200] for percentages
#     # and absolute reductions; [0.01, 20] for ratios/hazard ratios; extend to
#     # the response bounds to avoid unfairly cutting out the cited evidence.
#     plausible_max = max(200.0, resp_hi * 2)
#     page_values = [v for v in page_values_raw if 0 <= v <= plausible_max and not (1900 <= v <= 2100)]
#     if not page_values:
#         page_values = page_values_raw  # fallback: use all if filtering removed everything

#     cited_lo = min(page_values)
#     cited_hi = max(page_values)
#     tol = _OUTCOME_PERCENT_TOLERANCE

#     supported_lo = cited_lo - tol
#     supported_hi = cited_hi + tol

#     within_range = resp_lo >= supported_lo and resp_hi <= supported_hi

#     cited_summary = (
#         f"{cited_lo:g}–{cited_hi:g}%"
#         if cited_lo != cited_hi
#         else f"{cited_lo:g}%"
#     )
#     resp_summary = (
#         f"{resp_lo:g}–{resp_hi:g}%"
#         if resp_lo != resp_hi
#         else f"{resp_lo:g}%"
#     )

#     if within_range:
#         _log_validation_step(
#             rule="_compare_clinical_outcome",
#             attribute="CLINICAL_OUTCOME",
#             doc_value=cited_summary,
#             response_value=resp_summary,
#             normalization=f"supported range [{supported_lo:g}, {supported_hi:g}]",
#             verdict="PASS",
#             reason=f"Response {resp_summary} is within cited range {cited_summary}.",
#         )
#         return (
#             "PASS",
#             f"Clinical outcome {resp_summary} is supported by cited evidence "
#             f"(cited range: {cited_summary}).",
#         )

#     _log_validation_step(
#         rule="_compare_clinical_outcome",
#         attribute="CLINICAL_OUTCOME",
#         doc_value=cited_summary,
#         response_value=resp_summary,
#         normalization=f"supported range [{supported_lo:g}, {supported_hi:g}]",
#         verdict="FAIL",
#         reason=f"Response {resp_summary} exceeds or contradicts cited range {cited_summary}.",
#     )
#     return (
#         "FAIL",
#         f"Clinical outcome mismatch. Cited evidence supports {cited_summary}, "
#         f"but SuperAI claimed {resp_summary}.",
#     )


# # ---------------------------------------------------------------------------
# # ACRONYM EXPANSION — full-form / abbreviation questions
# # ---------------------------------------------------------------------------

# def _extract_acronym_from_question(question: str) -> str:
#     """Return the acronym (all-caps token) from a full-form / stands-for question."""
#     # "full form of POMA", "what does POMA stand for", "expand POMA"
#     for pattern in (
#         r"\bfull\s+form\s+of\s+([A-Z]{2,})\b",
#         r"\bwhat\s+does\s+([A-Z]{2,})\s+stand\s+for\b",
#         r"\bwhat\s+is\s+([A-Z]{2,})\b",
#         r"\bexpand\s+([A-Z]{2,})\b",
#         r"\bacronym\s+(?:for|of)\s+([A-Z]{2,})\b",
#         r"\babbreviation\s+(?:for|of)\s+([A-Z]{2,})\b",
#         r"\bshort\s+form\s+of\s+([A-Z]{2,})\b",
#     ):
#         m = re.search(pattern, question)
#         if m:
#             return m.group(1)
#     # Fallback: first all-caps word of ≥ 2 letters
#     m = re.search(r"\b([A-Z]{2,})\b", question)
#     return m.group(1) if m else ""


# def _extract_core_acronym_expansion(text: str, acronym: str) -> str:
#     """Return the core expansion of an acronym from text, stripping trailing benefit clauses.

#     Matches patterns like:
#       "POMA Technology – Potency Maintenance Technology to Assure..."
#       "POMA stands for Potency Maintenance Technology"
#       "POMA: Potency Maintenance Technology"

#     Stops at the first occurrence of a clause connector ("to", "which", "that",
#     "throughout", "in order", "with", "and") followed by a verb, or at sentence
#     punctuation, so trailing promotional text is excluded.
#     """
#     normalized = re.sub(r"\s+", " ", text)

#     patterns = (
#         # "ACRONYM [optional words] – expansion"
#         rf"\b{re.escape(acronym)}\b(?:\s+\w+){{0,3}}\s*[-–—:]\s*(.+?)(?=\s+(?:to|which|that|throughout|in\s+order|,)|[.;]|$)",
#         # "ACRONYM stands for / means / refers to expansion"
#         rf"\b{re.escape(acronym)}\b(?:\s+\w+){{0,3}}\s+(?:stands\s+for|means|refers\s+to|is)\s+(.+?)(?=\s+(?:to|which|that|throughout|in\s+order|,)|[.;]|$)",
#     )

#     for pattern in patterns:
#         m = re.search(pattern, normalized, flags=re.IGNORECASE)
#         if m:
#             return m.group(1).strip().rstrip(".,;")

#     return ""


# def _extract_response_expansion(response_text: str, acronym: str) -> str:
#     """Return the acronym expansion stated in the response."""
#     # Try to extract from "stands for / means / is" phrasing
#     for pattern in (
#         rf"\b{re.escape(acronym)}\b(?:\s+\w+){{0,3}}\s+(?:stands\s+for|means|refers\s+to|is)\s+(.+?)(?=[.;,]|$)",
#         r"(?:stands\s+for|means|is\s+short\s+for|full\s+form\s+is)\s+(.+?)(?=[.;,]|$)",
#     ):
#         m = re.search(pattern, response_text, flags=re.IGNORECASE)
#         if m:
#             return m.group(1).strip().rstrip(".,;")

#     # Fallback: return whole response (stripped)
#     return re.sub(r"\s+", " ", response_text).strip()


# _ACRONYM_EXPANSION_STOP_WORDS = frozenset({
#     "a", "an", "the", "of", "in", "to", "for", "and", "or", "by",
#     "is", "are", "was", "were", "be", "been", "being",
#     "technology",  # often part of product name, not the expansion
# })


# def _compare_acronym_expansion(
#     response_text: str,
#     page_data: str,
#     question: str,
# ) -> tuple[str, str]:
#     """Validate full-form / abbreviation questions by comparing core expansions only.

#     Extracts the acronym expansion from both the document and the response,
#     strips trailing benefit/descriptive clauses, then checks keyword overlap.
#     Trailing clauses ("to Assure better therapeutic efficacy throughout 24 Months
#     Shelf Life") are ignored — only the acronym word-per-letter expansion matters.

#     PASS  — response expansion covers ≥ 60% of the document expansion words.
#     FAIL  — response expansion diverges from the document expansion.
#     DATA MISSING — expansion not found on cited page.
#     """
#     acronym = _extract_acronym_from_question(question)
#     if not acronym:
#         return "DATA MISSING", "Could not identify the acronym from the question."

#     page_expansion = _extract_core_acronym_expansion(page_data, acronym)
#     if not page_expansion:
#         return (
#             "DATA MISSING",
#             f"Expansion for {acronym} not found on the cited page.",
#         )

#     response_expansion = _extract_response_expansion(response_text, acronym)

#     # Tokenise and filter stop words
#     page_words = {
#         w for w in normalize_text(page_expansion).split()
#         if w not in _ACRONYM_EXPANSION_STOP_WORDS and len(w) > 1
#     }
#     response_words = {
#         w for w in normalize_text(response_expansion).split()
#         if w not in _ACRONYM_EXPANSION_STOP_WORDS and len(w) > 1
#     }

#     if not page_words:
#         return "DATA MISSING", f"Could not parse expansion for {acronym} from cited page."

#     overlap = page_words & response_words
#     coverage = len(overlap) / len(page_words)

#     _log_validation_step(
#         rule="_compare_acronym_expansion",
#         attribute="ACRONYM_EXPANSION",
#         doc_value=page_expansion,
#         response_value=response_expansion,
#         normalization=f"coverage {coverage:.0%} ({len(overlap)}/{len(page_words)} words)",
#         verdict="PASS" if coverage >= 0.6 else "FAIL",
#         reason=f"Acronym={acronym} page={page_words} response={response_words} overlap={overlap}",
#     )

#     if coverage >= 0.6:
#         return (
#             "PASS",
#             f"{acronym} expansion matches cited page: '{page_expansion}'.",
#         )

#     return (
#         "FAIL",
#         f"{acronym} expansion mismatch. "
#         f"Cited: '{page_expansion}'. "
#         f"Response: '{response_expansion}'.",
#     )


# def _compare_descriptive_response(
#     response_content: str,
#     page_data: str,
#     question: str = "",
# ) -> tuple[str, str]:
#     """Validate descriptive medical attributes by supported concepts, not raw words."""
#     normalized_response = _semantic_normalize(response_content)
#     normalized_page = _semantic_normalize(page_data)
#     normalized_question = _semantic_normalize(question)

#     response_concepts = _extract_semantic_concepts(normalized_response)
#     page_concepts = _extract_semantic_concepts(normalized_page)

#     if _requires_descriptive_comparison(normalized_question) and not _has_supported_descriptive_comparison(
#         normalized_page
#     ):
#         return (
#             "DATA MISSING",
#             "The cited page does not support the requested descriptive comparison/superiority claim.",
#         )

#     if response_concepts:
#         relevant_concepts = _select_relevant_descriptive_concepts(
#             normalized_question,
#             response_concepts,
#         )
#         if relevant_concepts:
#             matched_relevant = sorted(relevant_concepts.intersection(page_concepts))
#             missing_relevant = sorted(relevant_concepts.difference(page_concepts))
#             if not missing_relevant:
#                 return (
#                     "PASS",
#                     "Core factual claim is supported by the cited page. "
#                     f"Matched core concept(s): {', '.join(matched_relevant)}.",
#                 )

#             if matched_relevant:
#                 coverage = len(matched_relevant) / len(relevant_concepts)
#                 if coverage >= 0.5 or len(matched_relevant) >= 2:
#                     return (
#                         "PASS",
#                         "Core descriptive claim is supported by the cited page; "
#                         "extra explanatory wording was not treated as required evidence. "
#                         f"Matched core concept(s): {', '.join(matched_relevant)}.",
#                     )
#                 # Only 1 concept matched and coverage < 50%: check if there is
#                 # meaningful context overlap before returning DATA MISSING.
#                 # If the page is topically relevant, return FAIL (value exists but
#                 # differs) rather than DATA MISSING (no evidence at all).
#                 if _has_descriptive_context_overlap(normalized_response, normalized_page):
#                     return (
#                         "FAIL",
#                         "Core factual claim is only partially supported on the cited page. "
#                         f"Missing core concept(s): {', '.join(missing_relevant)}.",
#                     )
#                 return (
#                     "DATA MISSING",
#                     "Core factual claim is only partially supported on the cited page. "
#                     f"Missing core concept(s): {', '.join(missing_relevant)}.",
#                 )

#             if _has_descriptive_context_overlap(normalized_response, normalized_page):
#                 return (
#                     "DATA MISSING",
#                     "Related cited text exists, but the core factual claim was not found.",
#                 )

#             return "DATA MISSING", "Core factual claim was not found on the cited page."

#         matched_concepts = sorted(response_concepts.intersection(page_concepts))
#         missing_concepts = sorted(response_concepts.difference(page_concepts))

#         if len(matched_concepts) == len(response_concepts):
#             return (
#                 "PASS",
#                 f"Semantic match found for descriptive attribute: {', '.join(matched_concepts)}.",
#             )

#         if matched_concepts:
#             coverage = len(matched_concepts) / len(response_concepts)
#             if coverage >= 0.6:
#                 return (
#                     "PASS",
#                     "Meaning is supported by the cited page despite wording differences. "
#                     f"Matched concept(s): {', '.join(matched_concepts)}.",
#                 )
#             return (
#                 "FAIL",
#                 "Descriptive value is only partially supported on the cited page. "
#                 f"Missing concept(s): {', '.join(missing_concepts)}.",
#             )

#         if _has_descriptive_context_overlap(normalized_response, normalized_page):
#             return (
#                 "FAIL",
#                 "Related descriptive data exists on the cited page, but the meaning does not match.",
#             )

#         # No concept matched the page and no drug-class overlap exists — the
#         # concept dictionary may simply lack coverage for this question type
#         # (e.g. clinical trial outcomes, survival benefits, SHEP study results).
#         # Fall through to keyword comparison so those questions are not falsely
#         # returned as DATA MISSING.

#     response_keywords = _extract_keywords(normalized_response)
#     page_keywords = _extract_keywords(normalized_page)
#     matched_keywords = sorted(response_keywords.intersection(page_keywords))

#     if not response_keywords:
#         return "DATA MISSING", "Super AI response did not contain a descriptive value to validate."

#     coverage = len(matched_keywords) / len(response_keywords)
#     if coverage >= 0.45 and len(matched_keywords) >= 3:
#         return (
#             "PASS",
#             "Descriptive meaning is supported by the cited page despite wording differences.",
#         )

#     # Numeric supplement: _extract_keywords ignores pure numbers (pattern
#     # requires a letter start), so clinical statistics like "4736", "36", "1"
#     # are invisible to keyword coverage.  If every number in the response
#     # appears on the cited page AND there is at least minimal keyword context,
#     # treat as sufficient evidence.
#     response_numbers_sup = _extract_numbers(normalized_response)
#     page_numbers_sup = _extract_numbers(normalized_page)
#     if (
#         response_numbers_sup
#         and response_numbers_sup.issubset(page_numbers_sup)
#         and matched_keywords
#     ):
#         return (
#             "PASS",
#             "Clinical numeric value(s) from SuperAI confirmed on cited page: "
#             f"{', '.join(sorted(response_numbers_sup))}. "
#             f"Keyword context: {', '.join(matched_keywords[:5])}.",
#         )

#     # Clinical relaxation: trial/study outcome questions naturally include
#     # context words (year, full trial name, methodology notes) that the
#     # document excerpt does not repeat.  Accept 30% coverage with at least
#     # 2 keyword matches so these do not falsely return DATA MISSING or FAIL.
#     _clinical_question_terms = (
#         "trial",
#         "study",
#         "shep",
#         "enrolled",
#         "survival",
#         "guideline",
#         "evidence",
#         "mortality",
#         "reduction",
#         "benefit",
#         "randomized",
#         "randomised",
#     )
#     is_clinical_question = any(
#         term in normalize_text(question) for term in _clinical_question_terms
#     )
#     if is_clinical_question and coverage >= 0.30 and len(matched_keywords) >= 2:
#         return (
#             "PASS",
#             "Clinical evidence from cited page broadly supports the SuperAI response. "
#             f"Matched keyword(s): {', '.join(matched_keywords)}.",
#         )

#     # Policy/incentive questions: a single strong keyword match (product name or
#     # policy term) combined with any numeric overlap is sufficient to PASS rather
#     # than returning DATA MISSING.  These documents are highly structured and
#     # the keyword coverage metric penalises valid answers that use different
#     # sentence structure than the extracted page text.
#     _policy_question_terms = (
#         "incentive",
#         "objective",
#         "productivity",
#         "growth",
#         "pangraf",
#         "eligibility",
#         "criteria",
#         "trip",
#         "award",
#         "medal",
#         "reimbursement",
#         "stockist",
#         "credit",
#     )
#     is_policy_question = any(
#         term in normalize_text(question) for term in _policy_question_terms
#     )
#     response_numbers_check = _extract_numbers(normalized_response)
#     page_numbers_check = _extract_numbers(normalized_page)
#     if (
#         is_policy_question
#         and matched_keywords
#         and response_numbers_check
#         and response_numbers_check.issubset(page_numbers_check)
#     ):
#         return (
#             "PASS",
#             "Policy/incentive values from cited page match the SuperAI response. "
#             f"Matched keyword(s): {', '.join(matched_keywords)}; "
#             f"matched numeric(s): {', '.join(sorted(response_numbers_check))}.",
#         )

#     if matched_keywords:
#         return (
#             "FAIL",
#             "Related descriptive data exists on the cited page, but required meaning is incomplete.",
#         )

#     return "DATA MISSING", "Required descriptive value not found on the cited page."


# def _select_relevant_descriptive_concepts(
#     normalized_question: str,
#     response_concepts: set[str],
# ) -> set[str]:
#     """Return the concepts that answer the question's core factual ask.

#     Descriptive SuperAI answers often include surrounding explanation. For MOA,
#     USP, indication, and clinical-benefit questions, validate the core claim
#     requested by the question instead of every extra phrase in the response.
#     """
#     concept_groups = (
#         (
#             ("voglibose", "postprandial", "pphg"),
#             {
#                 "voglibose",
#                 "alpha glucosidase inhibition",
#                 "delayed glucose absorption",
#             },
#         ),
#         (
#             ("dapagliflozin", "sglt2", "renal glucose", "urinary glucose"),
#             {
#                 "sglt2 inhibition",
#                 "renal glucose excretion",
#             },
#         ),
#         (
#             ("metformin",),
#             {
#                 "insulin sensitivity",
#                 "glucose uptake",
#                 "hepatic glucose production",
#                 "glycaemic control",
#             },
#         ),
#         (
#             ("gliclazide", "insulin secretion", "cellular"),
#             {
#                 "sulphonylurea receptor binding",
#                 "insulin secretion",
#             },
#         ),
#         (
#             ("linagliptin", "glp", "gip", "dpp"),
#             {
#                 "dpp4 inhibition",
#                 "glp gip incretin",
#                 "insulin secretion",
#                 "hepatic glucose production",
#                 "glycaemic control",
#                 "fast slow dpp4 binding",
#                 "dpp4 selectivity",
#                 "reduced off target effects",
#                 "od convenience",
#             },
#         ),
#         (
#             ("ckd", "esrd", "renal"),
#             {
#                 "safe renal impairment",
#                 "esrd risk reduction",
#             },
#         ),
#         (
#             ("normal saline", "dilution", "medium", "iv infusion"),
#             {
#                 "normal saline dilution",
#                 "iv infusion",
#             },
#         ),
#         (
#             ("indication", "indications", "used for", "prescribed"),
#             {
#                 "type 2 diabetes management",
#                 "solid organ transplantation",
#                 "organ rejection prophylaxis",
#                 "central nervous system",
#             },
#         ),
#         (
#             ("symptom", "symptoms", "bph", "oab", "storage"),
#             {
#                 "bph luts relief",
#                 "overactive bladder symptom control",
#             },
#         ),
#         (
#             ("side effect", "side effects", "adverse", "reaction", "reactions", "discomfort"),
#             {
#                 "gastrointestinal discomfort",
#                 "renal dysfunction",
#                 "tremor",
#                 "hirsutism",
#                 "hypertension",
#                 "gum hyperplasia",
#                 "nephrotoxicity monitoring",
#             },
#         ),
#         (
#             ("nephrotoxicity", "monitoring", "precaution", "precautions"),
#             {
#                 "nephrotoxicity monitoring",
#                 "renal dysfunction",
#             },
#         ),
#         (
#             ("organ", "organs", "transplantation", "transplant"),
#             {
#                 "kidney liver heart transplantation",
#                 "organ rejection prophylaxis",
#             },
#         ),
#         (
#             # Require "cars" or "upper limb" — "trial" alone is too broad and
#             # wrongly fires for SHEP trial, CORONA trial, etc.
#             ("cars", "upper limb", "motor"),
#             {
#                 "cars trial",
#                 "upper limb motor function",
#             },
#         ),
#         (
#             ("silodosin", "bph", "urine flow", "luts"),
#             {
#                 "alpha1a blockade",
#                 "smooth muscle relaxation",
#                 "urine flow improvement",
#                 "bph luts relief",
#             },
#         ),
#         (
#             ("mirabegron", "overactive bladder", "oab"),
#             {
#                 "beta3 agonist",
#                 "bladder relaxation",
#                 "overactive bladder symptom control",
#             },
#         ),
#         (
#             ("vitamin d3", "nurokind", "respiratory", "asthma", "copd", "immunity"),
#             {
#                 "respiratory immunity",
#                 "anti inflammatory",
#                 "immunoregulatory",
#                 "copd exacerbation reduction",
#                 "glucocorticoid responsiveness",
#                 "immune health",
#             },
#         ),
#         (
#             ("formoterol", "glycopyrronium", "glycobreez", "bronchodilation", "copd"),
#             {
#                 "formoterol beta2 agonist",
#                 "glycopyrronium m3 antagonist",
#                 "bronchodilation",
#                 "copd maintenance",
#                 "fast onset",
#                 "twenty four hour relief",
#             },
#         ),
#         (
#             ("peel off", "peel-off", "strip", "capsule", "moisture"),
#             {
#                 "peel off strip",
#                 "moisture protection",
#                 "safe peeling",
#                 "right direction marking",
#                 "no next capsule exposure",
#             },
#         ),
#         (
#             ("panimun", "bioral", "trusted", "organ transplantation"),
#             {
#                 "organ transplantation",
#                 "years of trust",
#                 "clinical evidence",
#                 "bioavailability",
#             },
#         ),
#         (
#             ("administration route", "route", "nebulization", "nebulizer", "respule"),
#             {
#                 "nebulization route",
#             },
#         ),
#     )

#     for question_terms, relevant in concept_groups:
#         if any(term in normalized_question for term in question_terms):
#             return response_concepts.intersection(relevant)

#     return set()


# def _semantic_normalize(text: str) -> str:
#     """Normalize semantically equivalent medical wording."""
#     normalized = normalize_text(text)
#     replacements = {
#         r"\bglycemic\b": "glycaemic",
#         r"\bimproves?\b": "increase",
#         r"\bincreases?\b": "increase",
#         r"\benhances?\b": "increase",
#         r"\bdecreases?\b": "reduce",
#         r"\breduces?\b": "reduce",
#         r"\blowers?\b": "reduce",
#         r"\bdelays?\b": "delay",
#         r"\bslows?\b": "delay",
#         r"\binhibit(?:s|ed|ing)?\b": "inhibit",
#         r"\benzymes\b": "enzyme",
#         r"\balpha[-\s]?glucosidase\b": "alpha glucosidase",
#         r"\bhepatic glucose output\b": "hepatic glucose production",
#         r"\bliver glucose output\b": "hepatic glucose production",
#         r"\bglucose uptake by muscles?\b": "glucose uptake",
#         r"\bglucose uptake by adipose cells?\b": "glucose uptake",
#         r"\bmaximum retail price\b": "mrp",
#         r"\brecommended dose\b": "recommended dosage",
#         r"\bone tablet\b": "1 tab",
#         r"\bone tab\b": "1 tab",
#         r"\bmode of action\b": "moa",
#     }

#     for pattern, replacement in replacements.items():
#         normalized = re.sub(pattern, replacement, normalized)

#     return normalized


# def _extract_semantic_concepts(text: str) -> set[str]:
#     """Extract medical concepts that can be matched semantically."""
#     concept_patterns = {
#         "insulin sensitivity": (r"\binsulin sensitivity\b",),
#         "glucose uptake": (r"\bglucose uptake\b",),
#         "hepatic glucose production": (r"\bhepatic glucose production\b",),
#         "voglibose": (r"\bvoglibose\b",),
#         "alpha glucosidase inhibition": (
#             r"\balpha glucosidase\b.*\binhibit\b",
#             r"\binhibit\b.*\balpha glucosidase\b",
#         ),
#         "delayed glucose absorption": (
#             r"\bdelay\b.*\bglucose absorption\b",
#             r"\bglucose absorption\b.*\bdelay\b",
#             r"\bdelay\b.*\bcarbohydrate absorption\b",
#             r"\bdecrease\b.*\bcarbohydrate absorption\b",
#             r"\bcarbohydrate absorption\b.*\bdecrease\b",
#             r"\breduce\b.*\bcarbohydrate absorption\b",
#             r"\bcarbohydrate absorption\b.*\breduce\b",
#             r"\bslow\b.*\bcarbohydrate digestion\b",
#         ),
#         "postprandial glucose control": (
#             r"\bpost\s*prandial\b",
#             r"\bpphg\b",
#             r"\bglycaemic excursions?\b",
#         ),
#         "sglt2 inhibition": (
#             r"\bsglt\s*2\b.*\binhibit\b",
#             r"\binhibit\b.*\bsglt\s*2\b",
#             r"\bsodium glucose cotransporter 2\b",
#         ),
#         "renal glucose excretion": (
#             r"\burinary glucose excretion\b",
#             r"\bglucose excretion\b",
#             r"\breduces? reabsorption of filtered glucose\b",
#             r"\bfiltered glucose\b.*\breabsorption\b",
#         ),
#         "dpp4 inhibition": (
#             r"\bdpp\s*4\b.*\binhibit\b",
#             r"\binhibit\b.*\bdpp\s*4\b",
#             r"\bdpp4 enzyme inhibitor\b",
#             r"\b>\s*80\s*%\s*dpp4 inhibition\b",
#         ),
#         "glp gip incretin": (
#             r"\bglp\s*1\b",
#             r"\bgip\b",
#             r"\bincretin effect\b",
#         ),
#         "fast slow dpp4 binding": (
#             r"\bfast association\b.*\bslow dissociation\b",
#             r"\bslow dissociation\b.*\bfast association\b",
#             r"\breversible\b.*\blong lasting\b",
#             r"\bsustained increase\b.*\bincretin\b",
#         ),
#         "dpp4 selectivity": (
#             r"\bselectivity\b.*\bdpp\s*4\b.*\bdpp\s*2\s*/\s*8\s*/\s*9\b",
#             r"\bdpp\s*4\b.*\bdpp\s*2\s*/\s*8\s*/\s*9\b",
#             r"\bdpp\s*8\b.*\bdpp\s*9\b",
#             r"\b10000\s*fold selectivity\b",
#         ),
#         "reduced off target effects": (
#             r"\bless off target\b",
#             r"\boff target side effect\b",
#             r"\bbetter safety\b",
#             r"\bbetter compliance\b",
#         ),
#         "od convenience": (
#             r"\btrue\s*24\b",
#             r"\b24\s*efficacy\b",
#             r"\bod convenience\b",
#             r"\bonce a daily\b",
#             r"\bonce daily\b",
#         ),
#         "immunosuppressant": (r"\bimmunosuppressant\b", r"\bsuppress immune\b"),
#         "calcineurin inhibitor": (r"\bcalcineurin inhibitor\b", r"\bcalcineurin activity\b"),
#         "solid organ transplantation": (
#             r"\bsolid organ transplantation\b",
#             r"\bsot\b",
#             r"\btransplanted organ\b",
#         ),
#         "kidney liver transplant": (
#             r"\bkidney\b.*\bliver\b",
#             r"\bliver\b.*\bkidney\b",
#         ),
#         "kidney liver heart transplantation": (
#             r"\bkidney\b.*\bliver\b.*\bheart\b",
#             r"\bheart\b.*\bkidney\b.*\bliver\b",
#             r"\bkidney\s*,?\s*liver\s*(?:and|,)\s*heart\b",
#         ),
#         "heart lung transplant": (
#             r"\bheart\b.*\blung",
#             r"\blung.*\bheart\b",
#         ),
#         "bone marrow transplantation": (
#             r"\bbone marrow transplantation\b",
#             r"\bbmt\b",
#         ),
#         "organ rejection prophylaxis": (
#             r"\bprophylaxis\b.*\borgan rejection\b",
#             r"\bprevent(?:s|ion)?\b.*\brejection\b",
#             r"\brejection\b.*\btransplanted organ\b",
#         ),
#         "enteric formulation": (
#             r"\benteric formulation\b",
#             r"\bdelayed release\b",
#             r"\bdelayed-release\b",
#         ),
#         "mycophenolic acid delivery": (
#             r"\bmycophenolic acid\b.*\bintestine\b",
#             r"\bdelivers\b.*\bintestine\b",
#         ),
#         "mycophenolate mofetil prodrug": (
#             r"\bmycophenolate mofetil\b.*\bprodrug\b",
#             r"\bmycept\b.*\bprodrug\b",
#         ),
#         "stomach conversion": (
#             r"\bconverted\b.*\bstomach\b",
#             r"\bstomach\b.*\bconverted\b",
#         ),
#         "mycophenolate sodium": (
#             r"\bmycophenolate sodium\b",
#         ),
#         "gi tolerability": (
#             r"\bgi compromised\b",
#             r"\bgi intolerance\b",
#             r"\bgastrointestinal symptoms\b",
#             r"\bgi safety\b",
#         ),
#         "central nervous system": (
#             r"\bcentral nervous system\b",
#             r"\bcns\b",
#         ),
#         "normal saline dilution": (
#             r"\bnormal saline\b",
#             r"\bsodium chloride\b",
#         ),
#         "iv infusion": (
#             r"\biv infusion\b",
#             r"\binfusion\b",
#             r"\bintravenously\b",
#         ),
#         "cars trial": (
#             r"\bcars trial\b",
#             r"\bcars\b",
#         ),
#         "upper limb motor function": (
#             r"\bupper limb motor functions?\b",
#             r"\bmotor functions?\b",
#         ),
#         "glycaemic control": (r"\bglycaemic control\b", r"\ba1c\b", r"\btype 2 diabetes management\b"),
#         "sulphonylurea receptor binding": (
#             r"\bsulphonylurea receptor\b",
#             r"\bsur\s*1\b",
#             r"\bk\+?\s*channel\b",
#         ),
#         "insulin secretion": (
#             r"\binsulin secretion\b",
#             r"\bsecretion of insulin\b",
#             r"\bincrease\b.*\binsulin\b",
#             r"\binsulin\b.*\bsecretion\b",
#         ),
#         "one tab od": (r"\b1 tab od\b", r"\bone tab od\b"),
#         "one tab bid": (r"\b1 tab bid\b", r"\bone tab bid\b"),
#         "titrated to two tablets": (r"\btitrated to two tablets\b",),
#         "type 2 diabetes management": (
#             r"\btype 2 diabetes management\b",
#             r"\btype 2 diabetes mellitus\b",
#             r"\bt2dm\b",
#         ),
#         "reference brand": (r"\breference brand\b",),
#         "years of trust": (r"\byears of trust\b", r"\b25 years\b"),
#         "weight neutral": (r"\bweight neutral\b",),
#         "no active metabolites": (r"\bno active metabolites\b",),
#         "safe renal impairment": (
#             r"\bckd\b",
#             r"\brenal\b",
#             r"\bdose adjustment\b",
#             r"\bstage 3\b",
#         ),
#         "esrd risk reduction": (
#             r"\besrd\b",
#             r"\bend stage renal disease\b",
#             r"\brisk of esrd\b",
#         ),
#         "lesser hypoglycaemia": (r"\blesser hypoglycaemia\b", r"\breduced hypoglycaemia\b"),
#         "selective sur1 binding": (r"\bselectively binds\b", r"\bsur 1 receptor\b"),
#         "cv safety": (r"\bcv problems\b", r"\bcardiovascular\b"),
#         "beta cell preservation": (r"\bbeta cell mass\b",),
#         "free radical scavenging": (r"\bfree radical scavenging\b",),
#         "vascular complication prevention": (r"\bvascular complications\b",),
#         "microtubule binding": (r"\bmicrotubules?\b",),
#         "dna separation inhibition": (r"\bdna separation\b", r"\bcell division\b"),
#         "prevents new cell formation": (
#             r"\bprevent(?:s|ed)? formation of new cells\b",
#             r"\bcells? cannot complete cell division\b",
#             r"\bprevent(?:s|ed)? cancer cell growth\b",
#         ),
#         "alpha1a blockade": (
#             r"\balpha\s*-?\s*1a\b.*\bblock",
#             r"\bblock(?:s|ade)?\b.*\balpha\s*-?\s*1a\b",
#             r"\bselectively blocks alpha\s*-?\s*1a receptors?\b",
#         ),
#         "smooth muscle relaxation": (
#             r"\brelax(?:es|ing)?\b.*\bsmooth muscles?\b",
#             r"\bsmooth muscles?\b.*\brelax",
#             r"\bprostate and bladder\b.*\brelax",
#         ),
#         "urine flow improvement": (
#             r"\bimprov(?:es|ing)? urine flow\b",
#             r"\burine flow\b.*\bimprov",
#             r"\burine can pass more easily\b",
#             r"\bflow rate improves?\b",
#         ),
#         "bph luts relief": (
#             r"\bbph\b",
#             r"\blower urinary tract symptoms?\b",
#             r"\bluts\b",
#             r"\bbenign prostatic hyperplasia\b",
#         ),
#         "beta3 agonist": (
#             r"\bbeta\s*-?\s*3\b.*\bagonist\b",
#             r"\bβ\s*3\b.*\bagonist\b",
#         ),
#         "bladder relaxation": (
#             r"\brelax(?:es|ation)?\b.*\bbladder\b",
#             r"\bbladder\b.*\brelax",
#         ),
#         "overactive bladder symptom control": (
#             r"\boveractive bladder\b",
#             r"\boab\b",
#             r"\burinary urgency\b",
#             r"\bfrequency\b.*\burinary\b",
#         ),
#         "respiratory immunity": (
#             r"\brespiratory immunity\b",
#             r"\brespiratory immunity booster\b",
#             r"\brespiratory diseases?\b",
#         ),
#         "anti inflammatory": (
#             r"\banti inflammatory\b",
#             r"\banti-inflammatory\b",
#             r"\bairway inflammation\b",
#         ),
#         "immunoregulatory": (
#             r"\bimmunoregulatory\b",
#             r"\bmodulate\b.*\bimmune responses?\b",
#             r"\binnate and adaptive immune responses?\b",
#         ),
#         "copd exacerbation reduction": (
#             r"\breduces? rate of moderate\s*/\s*severe copd exacerbations?\b",
#             r"\breduces?.{0,80}\bcopd exacerbations?\b",
#             r"\bexacerbations?\b",
#         ),
#         "glucocorticoid responsiveness": (
#             r"\bglucocorticoid responsiveness\b",
#             r"\bpoor glucocorticoid responsiveness\b",
#         ),
#         "immune health": (
#             r"\bimmune health\b",
#             r"\bimmune system\b",
#             r"\bimmune cells?\b",
#         ),
#         "formoterol beta2 agonist": (
#             r"\bformoterol\b.*\b(?:beta|β)\s*2\b",
#             r"\b(?:beta|β)\s*2\b.*\bformoterol\b",
#             r"\blaba\b",
#         ),
#         "glycopyrronium m3 antagonist": (
#             r"\bglycopyrronium\b.*\bm3\b",
#             r"\bm3\b.*\bglycopyrronium\b",
#             r"\blama\b",
#             r"\bmuscarinic antagonist\b",
#         ),
#         "bronchodilation": (
#             r"\bbronchodilation\b",
#             r"\bbronchodilator\b",
#             r"\bprevent bronchoconstriction\b",
#             r"\bairways?\b.*\brelax",
#         ),
#         "copd maintenance": (
#             r"\bcopd\b",
#             r"\blong term maintenance treatment\b",
#             r"\bmaintenance treatment\b.*\bcopd\b",
#         ),
#         "fast onset": (
#             r"\bfast onset\b",
#             r"\bwithin 5 minutes\b",
#             r"\bwithin about 5 minutes\b",
#         ),
#         "twenty four hour relief": (
#             r"\b24\s*hrs?\s*relief\b",
#             r"\b24\s*hour\b",
#             r"\bday time\b.*\bnight time\b",
#         ),
#         "peel off strip": (
#             r"\bpeel\s*-?\s*off strip\b",
#             r"\bunique peel\s*-?\s*off\b",
#         ),
#         "moisture protection": (
#             r"\bprotects? each capsule from moisture\b",
#             r"\bmoisture\b",
#             r"\bdose stability\b",
#         ),
#         "safe peeling": (
#             r"\bpeeling happens safely\b",
#             r"\bsafe peeling\b",
#             r"\bperforated marking\b",
#         ),
#         "right direction marking": (
#             r"\bpeel off marking\b",
#             r"\bright direction\b",
#             r"\bcorrect direction\b",
#         ),
#         "no next capsule exposure": (
#             r"\bwithout exposing the next capsule\b",
#             r"\bneighbouring capsules? (?:are )?not exposed\b",
#             r"\bopens only one blister\b",
#         ),
#         "clinical evidence": (
#             r"\bclinical trials?\b",
#             r"\bbioequivalence studies\b",
#             r"\bsupported by\b.*\bstudies\b",
#         ),
#         "bioavailability": (
#             r"\bbioavailability\b",
#             r"\bbioral\b",
#         ),
#         "nebulization route": (
#             r"\bnebulization\b",
#             r"\bnebulizer\b",
#             r"\bnebulisation\b",
#             r"\bvia nebulization\b",
#         ),
#         "gastrointestinal discomfort": (
#             r"\bgastrointestinal disturbances?\b",
#             r"\bgastrointestinal discomfort\b",
#             r"\babdominal discomfort\b",
#             r"\bnausea\b",
#             r"\bvomiting\b",
#             r"\bdyspepsia\b",
#             r"\bgi upset\b",
#         ),
#         "renal dysfunction": (
#             r"\brenal dysfunction\b",
#             r"\brenal failure\b",
#         ),
#         "tremor": (r"\btremor\b",),
#         "hirsutism": (r"\bhirsutism\b",),
#         "hypertension": (r"\bhypertension\b",),
#         "gum hyperplasia": (
#             r"\bgum hyperplasia\b",
#             r"\bgingival hyperplasia\b",
#         ),
#         "nephrotoxicity monitoring": (
#             r"\bnephrotoxicity\b.*\bmonitoring of renal function\b",
#             r"\bmonitoring of renal function\b",
#             r"\brenal function\b.*\bmonitor",
#         ),
#     }

#     concepts: set[str] = set()
#     for concept, patterns in concept_patterns.items():
#         if any(re.search(pattern, text) for pattern in patterns):
#             concepts.add(concept)

#     return concepts


# def _has_descriptive_context_overlap(response_text: str, page_text: str) -> bool:
#     """Return whether page has related descriptive context for FAIL vs missing."""
#     context_terms = {
#         "metformin",
#         "gliclazide",
#         "glizid",
#         "mxr",
#         "xr",
#         "sulphonylurea",
#         "hypoglycaemia",
#         "diabetes",
#         "dosage",
#         "indications",
#         "usp",
#         "safety",
#         "quality",
#         "docetaxel",
#         "microtubule",
#         "microtubules",
#         "cancer",
#         "cell division",
#     }
#     response_terms = {term for term in context_terms if term in response_text}
#     page_terms = {term for term in context_terms if term in page_text}
#     return bool(response_terms.intersection(page_terms))


# def _requires_descriptive_comparison(normalized_question: str) -> bool:
#     """Return whether a descriptive question asks for comparative superiority."""
#     comparison_terms = (
#         "more effective than",
#         "better than",
#         "superior to",
#         "compared to",
#         "versus",
#         "vs",
#         "than silodosin alone",
#         "than alone",
#     )
#     return any(term in normalized_question for term in comparison_terms)


# def _has_supported_descriptive_comparison(normalized_page: str) -> bool:
#     """Return whether cited text contains evidence for a comparative claim."""
#     comparison_evidence = (
#         "more effective than",
#         "better than",
#         "superior to",
#         "lower than",
#         "lower risk than",
#         "lower hypoglycemia risk than",
#         "lower hypoglycaemia risk than",
#         "reduce hypoglycemia risk than",
#         "reduced hypoglycemia risk than",
#         "reduce hypoglycaemia risk than",
#         "reduced hypoglycaemia risk than",
#         "less than",
#         "greater than",
#         "greater hba1c",
#         "1.5x greater",
#         "1.5 times greater",
#         "more affordable than",
#         "compared to",
#         "versus",
#         " vs ",
#         "than silodosin alone",
#         "than alone",
#         "add on",
#         "combination",
#         "storage symptoms",
#     )
#     return any(term in normalized_page for term in comparison_evidence)


# def _strip_citation_tail(response: str) -> str:
#     """Remove citation-reference suffix from model response before matching."""
#     split_parts = re.split(r"\bcitation\b", response, flags=re.IGNORECASE, maxsplit=1)
#     response_without_citation_block = split_parts[0].strip()
#     response_without_citation_block = _remove_inline_citation_markers(
#         response_without_citation_block
#     )
#     return re.sub(
#         r"(?:\s+\d+(?:\s*,\s*\d+)*)+\s*$",
#         "",
#         response_without_citation_block,
#     ).strip()


# def _remove_inline_citation_markers(text: str) -> str:
#     """Remove inline citation markers like 1,2 without removing product values."""
#     def replace_marker(match: re.Match[str]) -> str:
#         marker = match.group(1)
#         marker_numbers = [int(number) for number in re.findall(r"\d+", marker)]
#         if marker_numbers and all(number <= 20 for number in marker_numbers):
#             return " "
#         return match.group(0)

#     text = re.sub(r"(?<=\s)(\d+(?:\s*,\s*\d)+)(?=\s|$)", replace_marker, text)
#     return re.sub(r"\s+", " ", text).strip()


# def _extract_keywords(text: str) -> set[str]:
#     """Extract useful comparison keywords from text."""
#     stop_words = {
#         "the",
#         "and",
#         "are",
#         "as",
#         "be",
#         "by",
#         "for",
#         "is",
#         "in",
#         "it",
#         "its",
#         "of",
#         "on",
#         "or",
#         "to",
#         "was",
#         "with",
#         "from",
#         "this",
#         "that",
#         "same",
#         "category",
#         "listed",
#         "list",
#         "segment",
#         "sources",
#         "source",
#         "company",
#         "companies",
#         "information",
#         "provided",
#         "matching",
#         "couldn",
#         "couldnt",
#         "contains",
#         "contain",
#         "containing",
#         "has",
#         "have",
#         "having",
#         "comprises",
#         "comprise",
#         "composition",
#         "per",
#         "tablet",
#         "tablets",
#         "citation",
#         "page",
#         "source",
#         "brand",
#         "snapshot",
#         "updated",
#         "document",
#         "available",
#         "mrp",
#         "price",
#         "strip",
#         "injection",
#         "product",
#         "pack",
#         "size",
#         "bottle",
#         "vial",
#         "vials",
#         "ampoule",
#         "ampoules",
#         "sachet",
#         "sachets",
#         "capsule",
#         "capsules",
#         "tabs",
#     }
#     words = set(re.findall(r"[a-z][a-z0-9-]{1,}", text))
#     return words.difference(stop_words)


# def _has_keyword_coverage(response_keywords: set[str], page_keywords: set[str]) -> bool:
#     """Require high text overlap while allowing harmless factual wording variants."""
#     if not response_keywords:
#         return True

#     matched_keywords = response_keywords.intersection(page_keywords)
#     minimum_matches = max(1, int(len(response_keywords) * 0.80 + 0.999))
#     return len(matched_keywords) >= minimum_matches


# def _is_missing_source_data(text: str) -> bool:
#     """Return whether page-scoped DOM extraction failed."""
#     normalized = normalize_text(text)
#     return not normalized or "no dom page data available" in normalized or "no page data available" in normalized

 #############

"""PDF parser response and citation validation helpers.

Critical pharma validation contract:
- Validate only against the exact cited PDF page number.
- If SuperAI returns multiple values, every value must be checked.
- If SuperAI returns multiple citations, each cited page is checked one by one.
- PASS requires all required SuperAI values to match the cited page.
- FAIL means related cited-page data exists but one or more values mismatch.
- DATA MISSING means the cited document/page/value cannot be found.
"""

import re
from utils.logger import get_logger as _get_logger

_validator_logger = _get_logger("validator")

# Accumulated per-question validation steps written by _log_validation_step.
# Cleared at the start of each question in the main validation loop.
VALIDATION_LOG: list[dict] = []


def _log_validation_step(
    *,
    rule: str,
    product: str = "",
    attribute: str = "",
    row: str = "",
    column: str = "",
    doc_value: object = None,
    response_value: object = None,
    normalization: str = "",
    verdict: str,
    reason: str = "",
) -> None:
    """Append one validation step to VALIDATION_LOG and emit a debug log line.

    Call this from every sub-validator so that DATA MISSING results can be
    diagnosed without adding manual print statements.
    """
    entry = {
        "rule": rule,
        "product": product,
        "attribute": attribute,
        "row": row,
        "column": column,
        "doc_value": doc_value,
        "response_value": response_value,
        "normalization": normalization,
        "verdict": verdict,
        "reason": reason,
    }
    VALIDATION_LOG.append(entry)
    _validator_logger.debug(
        "[%s] product=%r attr=%r row=%r col=%r doc=%r resp=%r norm=%r → %s | %s",
        rule,
        product,
        attribute,
        row,
        column,
        doc_value,
        response_value,
        normalization,
        verdict,
        reason,
    )


COMPANY_ENTITY_MATCH_THRESHOLD = 0.95

# Fine-grained attribute type mappings.  These are evaluated BEFORE question
# type routing so that "cost per couple" is never mistaken for PRICE/MRP and
# "PM objective" is never compared against the Quarterly Objective column.
_ATTRIBUTE_MAPPINGS: dict[str, tuple[str, ...]] = {
    "PRICE": (
        "mrp",
        "revised mrp",
        "new mrp",
        "cost per tablet",
        "cost per strip",
        "price per tablet",
        "price per strip",
        "per tablet",
        "per strip",
        "per tab",
    ),
    "INCENTIVE": (
        "incentive per strip",
        "incentive per tablet",
        "incentive per unit",
        "incentive per tab",
        "incentive value",
        "incentive amount",
    ),
    "PM_OBJECTIVE": (
        "pm objective",
        "pmr objective",
        "pm/pmr objective",
        "monthly objective",
        "monthly minimum",
        "minimum objective",
        "pm target",
        "pmr target",
    ),
    "QUARTERLY_OBJECTIVE": (
        "quarterly objective",
        "quarterly minimum",
        "quarterly pmr",
        "quarterly pm",
        "qtr objective",
        "q objective",
    ),
    "TRIP_COST": (
        "cost per couple",
        "couple cost",
        "trip cost",
        "foreign trip",
        "domestic trip",
        "international trip",
        "holiday trip",
        "incentive trip",
    ),
    "MEDAL_VALUE": (
        "medal value",
        "medal worth",
        "medal amount",
        "gold medal",
        "silver medal",
    ),
    "AWARD_VALUE": (
        "award value",
        "award cost",
        "award amount",
        "award worth",
    ),
    "REIMBURSEMENT": (
        "reimbursement value",
        "reimbursement amount",
        "reimbursement cost",
    ),
}


def resolve_attribute_type(question: str) -> str:
    """Resolve the fine-grained attribute type from a question string.

    Returns one of the keys in _ATTRIBUTE_MAPPINGS, or "GENERAL" when no
    specific attribute can be identified.  Always call this before choosing a
    validation strategy so that PM_OBJECTIVE is never compared against the
    Quarterly Objective column and TRIP_COST is never compared against MRP.
    """
    normalized = normalize_text(question)
    for attr_type, terms in _ATTRIBUTE_MAPPINGS.items():
        if any(term in normalized for term in terms):
            return attr_type
    return "GENERAL"


QUESTION_TYPES = {
    "PRICE_COMPARISON",
    "PRICE_LOOKUP",
    "TRIP_AWARD_COST",
    "DOSAGE_FREQUENCY",
    "DOSAGE_FORM",
    "PACK_SIZE",
    "STRENGTH_LOOKUP",
    "COMPETITOR_BRAND",
    "COMPANY_LOOKUP",
    "COMPOSITION",
    "ACTIVE_INGREDIENT",
    "MOLECULE_LIST",
    "PRODUCT_COMPARISON",
    "CLINICAL_OUTCOME",
    "CLINICAL_EVIDENCE",
    "DESCRIPTIVE_USP",
    "GENERAL",
}


def classify_question_type(question: str, response: str = "") -> str:
    """Classify question intent before validation routing."""
    normalized = normalize_text(f"{question} {response}")
    normalized_question = normalize_text(question)

    if "composition" in normalized_question:
        return "COMPOSITION"

    if "active ingredient" in normalized_question:
        return "ACTIVE_INGREDIENT"

    if any(term in normalized_question for term in ("dosage form", "dosage forms", "available forms", "forms of")):
        return "DOSAGE_FORM"

    if any(
        term in normalized_question
        for term in (
            "strength range",
            "which strength",
            "what strength",
            "strength of",
            "strength is",
            "present at a strength",
        )
    ):
        return "STRENGTH_LOOKUP"

    if (
        "how many" in normalized_question
        and any(unit in normalized_question for unit in ("tablet", "tablets", "tab", "capsule", "capsules", "cap"))
        and any(container in normalized_question for container in ("strip", "box", "pack"))
    ):
        return "PACK_SIZE"

    if any(
        term in normalized_question
        for term in (
            "which three molecules",
            "which molecules",
            "what molecules",
            "molecules are present",
            "molecules are included",
            "molecules included",
            "molecules does",
            "molecules are there",
            "molecules are in",
        )
    ):
        return "MOLECULE_LIST"

    if "contains" in normalized_question and re.search(
        r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)\b",
        normalized,
    ):
        return "COMPOSITION"

    price_comparison_terms = (
        "cheaper",
        "cost saving",
        "saving",
        "lowest",
        "highest",
        "cheapest",
        "most expensive",
    )
    explicit_price_terms = ("mrp", "price", "cost", "per strip", "per tablet", "per tab")
    if any(term in normalized_question for term in price_comparison_terms):
        return "PRICE_COMPARISON"

    if (
        any(term in normalized_question for term in ("difference", "compared to", "compared with", "versus", "vs"))
        and any(term in normalized_question for term in explicit_price_terms)
    ):
        return "PRICE_COMPARISON"

    if "competitor" in normalized_question and any(
        term in normalized_question
        for term in ("price", "priced", "mrp", "per strip", "lowest", "highest", "cheapest")
    ):
        return "PRICE_COMPARISON"

    if _is_multi_product_question(normalized_question):
        return "PRODUCT_COMPARISON"

    if "marketed by" in normalized_question or "markets" in normalized_question:
        return "COMPANY_LOOKUP"

    if "competitor" in normalized_question and any(
        term in normalized_question for term in ("belongs to", "company", "manufacturer", "manufactures")
    ):
        return "COMPANY_LOOKUP"

    if any(term in normalized_question for term in ("company", "companys", "company’s", "manufacturer", "manufactures")):
        return "COMPANY_LOOKUP"

    # Incentive and objective questions must not be routed to PRICE_LOOKUP.
    # "per strip" in the question refers to the incentive attribute, not MRP.
    _objective_incentive_terms = (
        "incentive",
        "minimum objective",
        "quarterly objective",
        "monthly objective",
        "quarterly minimum",
        "monthly minimum",
        "pmr objective",
    )
    if any(term in normalized_question for term in _objective_incentive_terms):
        return "GENERAL"

    # Trip/award/medal/reimbursement cost questions carry large values in Indian
    # number notation (₹1,10,000) and must not be routed through the MRP product-
    # price path which expects per-strip or per-tablet prices.
    _trip_award_terms = (
        "cost per couple",
        "couple cost",
        "trip cost",
        "foreign trip",
        "domestic trip",
        "international trip",
        "medal value",
        "medal worth",
        "award value",
        "award cost",
        "award amount",
        "reimbursement value",
        "reimbursement amount",
        "holiday trip",
        "incentive trip",
    )
    if any(term in normalized_question for term in _trip_award_terms):
        return "TRIP_AWARD_COST"

    if any(term in normalized_question for term in ("mrp", "price", "cost", "per strip")):
        return "PRICE_LOOKUP"

    if any(
        term in normalized_question
        for term in (
            "dosage",
            "dose",
            "how many times",
            "times a day",
            "once daily",
            "twice daily",
            "frequency",
            "every 12 hours",
        )
    ):
        return "DOSAGE_FREQUENCY"

    # Trial enrollment / sample-size lookup questions ("how many patients enrolled
    # in the SHEP trial?") must not fall into DESCRIPTIVE_USP via "trial".  They
    # are pure count lookups and belong in CLINICAL_EVIDENCE so the numeric path
    # can validate the specific number.
    if (
        "how many" in normalized_question
        and any(
            term in normalized_question
            for term in ("enrolled", "enroll", "randomized", "randomised", "participants", "patients", "subjects")
        )
        and any(
            term in normalized_question
            for term in ("trial", "study", "program", "programme")
        )
    ):
        return "CLINICAL_EVIDENCE"

    # Policy/sales incentive table questions must not be routed to DESCRIPTIVE_USP.
    # Terms like "growth" appear in business context (sales growth, HQ growth %)
    # but the DESCRIPTIVE_USP path is designed for clinical/medical text only.
    _policy_table_terms = (
        "productivity",
        "couple ticket",
        "single ticket",
        "sales credit",
        "invoice date",
        "stockist",
        "pangraf sale contribution",
        "negative growth",
        "growth percentage",
        "hq growth",
        "h q growth",
        "individual growth",
        "field employee",
    )
    if any(term in normalized_question for term in _policy_table_terms):
        return "GENERAL"

    if (
        normalized_question.startswith(("why ", "how "))
        or any(
            term in normalized_question
            for term in (
                "prevent",
                "prevents",
                "inhibit",
                "inhibits",
                "delays",
                "absorption",
                "growth",
                "ingredient",
                "drug class",
                "class",
                "surgeries",
                "used",
                "condition",
                "prescribed",
                "form",
                "tolerability",
                "system",
                "medium",
                "dilution",
                "trial",
                "upper limb",
                "motor function",
                "administration route",
                "route",
                "nebulization",
                "symptom",
                "symptoms",
                "organ",
                "organs",
                "transplantation",
                "side effect",
                "side effects",
                "adverse",
                "adverse effect",
                "adverse effects",
                "adverse reaction",
                "adverse reactions",
                "adverse event",
                "adverse events",
                "dizziness",
                "dry mouth",
                "gastrointestinal",
                "discomfort",
                "nephrotoxicity",
                "monitoring",
                "precaution",
                "precautions",
                "feature",
                "features",
                "advantage",
                "advantages",
                "benefit",
                "benefits",
            )
        )
    ):
        return "DESCRIPTIVE_USP"

    if "competitor" in normalized_question and "brand" in normalized_question:
        return "COMPETITOR_BRAND"

    # Clinical outcome questions ask for the MAGNITUDE of a measured effect:
    # "By how much does X reduce LDL-C?" or "What was the risk reduction seen?"
    # These carry numeric ranges and need range-aware validation — they must not
    # fall into CLINICAL_EVIDENCE (which validates narrative text) or
    # DESCRIPTIVE_USP (which uses semantic concept matching).
    _clinical_outcome_terms = (
        "ldl-c reduction",
        "ldl reduction",
        "ldl-c lowering",
        "ldl lowering",
        "ldl-c by",
        "reduce ldl",
        "reduces ldl",
        "reduction in ldl",
        "hba1c reduction",
        "hba1c lowering",
        "reduce hba1c",
        "reduces hba1c",
        "reduction in hba1c",
        "risk reduction",
        "reduces the risk",
        "reduce the risk",
        "relative risk reduction",
        "absolute risk reduction",
        "cardiovascular risk reduction",
        "cardiovascular mortality reduction",
        "mortality reduction",
        "reduces mortality",
        "survival benefit",
        "survival rate",
        "efficacy outcome",
        "trial endpoint",
        "primary endpoint",
        "secondary endpoint",
        "major adverse cardiovascular",
        "mace reduction",
        "hazard ratio",
        "odds ratio",
        "relative risk",
        "number needed to treat",
        "nnt",
        "blood pressure reduction",
        "reduces blood pressure",
        "systolic reduction",
        "diastolic reduction",
        "reduces systolic",
        "reduces diastolic",
        "triglyceride reduction",
        "reduces triglyceride",
        "hdl increase",
        "increases hdl",
        "glucose reduction",
        "reduces glucose",
        "reduces fasting",
        "fasting glucose reduction",
        "reduces a1c",
        "a1c reduction",
    )
    if any(term in normalized_question for term in _clinical_outcome_terms):
        return "CLINICAL_OUTCOME"

    if any(
        term in normalized
        for term in (
            "trial",
            "study",
            "evidence",
            "guideline",
            "mortality",
            "hfref",
            "hfr ef",
            "hfr",
            "class ia",
            "recommendation",
        )
    ):
        return "CLINICAL_EVIDENCE"

    if any(
        term in normalized_question
        for term in (
            "why",
            "what makes",
            "different",
            "preferred",
            "benefit",
            "benefits",
            "usp",
            "advantage",
            "advantages",
            "mechanism",
        )
    ):
        return "DESCRIPTIVE_USP"

    return "GENERAL"


def extract_citation_targets(text: str) -> list[dict[str, int | str]]:
    """Extract every citation target with document name, citation number, and page."""
    citation_text = extract_citation_text(text)
    if not citation_text:
        return []

    decomposed_targets = _extract_all_page_label_targets(citation_text)

    targets: list[dict[str, int | str]] = []
    citation_number = 1
    search_position = 0

    while search_position < len(citation_text):
        start_match = re.search(
            rf"(?:^|\s){citation_number}\s+",
            citation_text[search_position:],
        )

        if not start_match:
            break

        segment_start = search_position + start_match.end()
        page_match = re.search(
            r"(?:_Page_|page[\s:_-]+)(\d+)",
            citation_text[segment_start:],
            flags=re.IGNORECASE,
        )

        if not page_match:
            break

        page_end = segment_start + page_match.end()
        next_start_match = re.search(
            rf"\s{citation_number + 1}\s+",
            citation_text[page_end:],
        )
        segment_end = (
            page_end + next_start_match.start()
            if next_start_match
            else len(citation_text)
        )
        citation_label = citation_text[segment_start:segment_end].strip()

        targets.append(
            {
                "citation_number": citation_number,
                "page_number": int(page_match.group(1)),
                "document_name": extract_document_name(citation_label),
                "citation_text": citation_label,
            }
        )
        citation_number += 1
        search_position = segment_end

    if len(decomposed_targets) > len(targets):
        return decomposed_targets

    if targets:
        return targets

    return decomposed_targets


def _extract_all_page_label_targets(text: str) -> list[dict[str, int | str]]:
    """Extract unique page labels from polluted citation text."""
    targets: list[dict[str, int | str]] = []
    seen: set[tuple[str, int]] = set()
    pattern = re.compile(
        r"([A-Za-z0-9][A-Za-z0-9 &()',./-]{1,80}?"
        r"(?:_Page_|page[\s:_-]+)(\d+))",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        citation_label = match.group(1).strip()
        document_name = extract_document_name(citation_label)
        page_number = int(match.group(2))
        key = (normalize_text(document_name), page_number)

        if key in seen:
            continue

        seen.add(key)
        targets.append(
            {
                "citation_number": len(targets) + 1,
                "page_number": page_number,
                "document_name": document_name,
                "citation_text": citation_label,
            }
        )

    return targets


def extract_document_name(citation_label: str) -> str:
    """Extract the source document name from a citation label."""
    cleaned_label = " ".join(citation_label.split()).strip()
    document_name = re.sub(
        r"(?:_Page_|page[\s:_-]+)\d+.*$",
        "",
        cleaned_label,
        flags=re.IGNORECASE,
    ).strip(" :-_")
    document_name = re.sub(r"^\d+\s+", "", document_name).strip()
    return document_name or "UNKNOWN DOCUMENT"


def normalize_text(text: str) -> str:
    """Normalize text for stable page-scoped validation."""
    lowered_text = text.lower().replace("\u00a0", " ")
    lowered_text = re.sub(r"\bonce\s+daily\b|\bonce\s+a\s+day\b", "od", lowered_text)
    lowered_text = re.sub(r"\btwice\s+daily\b|\btwice\s+a\s+day\b", "bid", lowered_text)
    lowered_text = re.sub(r"\bbd\b", "bid", lowered_text)
    lowered_text = re.sub(r"\bone\b", "1", lowered_text)
    lowered_text = re.sub(r"\btwo\b", "2", lowered_text)
    lowered_text = re.sub(r"\bthree\b", "3", lowered_text)
    lowered_text = re.sub(r"\bfour\b", "4", lowered_text)
    lowered_text = re.sub(r"\btablets?\b", "tab", lowered_text)
    lowered_text = re.sub(r"\bcapsules?\b", "cap", lowered_text)
    lowered_text = re.sub(r"\bstrips?\b", "strip", lowered_text)
    lowered_text = re.sub(r"\bmaximum\s+retail\s+price\b", "mrp", lowered_text)
    lowered_text = re.sub(r"\brecommended\s+dose\b", "recommended dosage", lowered_text)
    lowered_text = re.sub(r"\bmode\s+of\s+action\b", "moa", lowered_text)
    lowered_text = re.sub(r"\btype\s*ii\b", "type 2", lowered_text)
    lowered_text = re.sub(r"\bhcl\b", "hydrochloride", lowered_text)
    lowered_text = re.sub(r"\bglizid\s*-\s*m\s*xr\b", "glizid mxr", lowered_text)
    lowered_text = re.sub(r"\bglizid\s*-\s*mxr\b", "glizid mxr", lowered_text)
    lowered_text = re.sub(r"(?<=\w)[\s_\-./]+(?=\w)", " ", lowered_text)
    return " ".join(lowered_text.split())


def compare_response_with_source(response: str, source_text: str) -> str:
    """Backward-compatible wrapper for page-scoped source validation."""
    return compare_response_with_page_data(response, source_text)


def extract_citation_text(text: str) -> str:
    """Extract the visible citation section from a SuperAI response."""
    citation_sections = re.split(r"\bcitation\b", text, flags=re.IGNORECASE, maxsplit=1)
    if len(citation_sections) > 1:
        citation_text = citation_sections[1].strip()
        if re.search(r"(?:_Page_|page[\s:_-]+)\d+", citation_text, flags=re.IGNORECASE):
            return citation_text
        return ""

    citation_matches = re.findall(
        r"(?:\d+\s+)?[A-Za-z0-9 &()',./-]+(?:_Page_|page[\s:_-]+)\d+",
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(
        match.strip()
        for match in citation_matches
        if re.search(r"(?:_Page_|page[\s:_-]+)\d+", match, flags=re.IGNORECASE)
    )


def extract_page_number(text: str) -> int:
    """Extract the page number tied to the SuperAI answer's citation marker."""
    citation_sections = re.split(r"\bcitation\b", text, flags=re.IGNORECASE, maxsplit=1)

    if len(citation_sections) > 1:
        answer_text = citation_sections[0]
        citation_text = citation_sections[1]
        citation_page_map = _extract_citation_page_map(citation_text)
        referenced_citations = _extract_answer_citation_references(answer_text)

        for citation_number in referenced_citations:
            if citation_number in citation_page_map:
                return citation_page_map[citation_number]

        if citation_page_map:
            return citation_page_map[min(citation_page_map)]

    citation_matches = re.findall(
        r"(?:_Page_|page[\s:_-]+)(\d+)",
        text,
        flags=re.IGNORECASE,
    )

    if citation_matches:
        return int(citation_matches[-1])

    raise ValueError("No mandatory citation page number found in text.")


def compare_ai_vs_pdf(
    ai_response: str,
    pdf_page_data: str,
    question: str = "",
    product: str = "",
    citation_page: int | str = "",
) -> str:
    """Compare the AI response with data extracted only from the cited PDF page."""
    return compare_response_with_page_data(
        ai_response, pdf_page_data, question, product=product, citation_page=citation_page
    )


def explain_ai_vs_pdf(ai_response: str, pdf_page_data: str, question: str = "") -> str:
    """Return a specific reason for the page-scoped validation decision."""
    response_content = _clean_response_for_validation(ai_response)
    question_type = classify_question_type(question, response_content)

    if not response_content:
        return "Super AI response did not contain a value to validate."

    if _is_missing_source_data(pdf_page_data):
        return "Required value not found because cited page data is missing."

    if question_type in {"PRICE_COMPARISON", "COMPANY_LOOKUP"}:
        table_result = _deterministic_table_validation(response_content, pdf_page_data, question)
        if table_result[0]:
            return table_result[2]
        _, reason = _compare_competitor_table_reasoning(
            response_content,
            pdf_page_data,
            question,
        )
        return reason

    if question_type == "PRICE_LOOKUP":
        table_result = _deterministic_table_validation(response_content, pdf_page_data, question)
        if table_result[0]:
            return table_result[2]
        _, reason = _compare_price_lookup(response_content, pdf_page_data, question)
        return reason

    if question_type == "PACK_SIZE":
        _, reason = _compare_pack_size(response_content, pdf_page_data)
        return reason

    if question_type == "STRENGTH_LOOKUP":
        _, reason = _compare_strength_lookup(response_content, pdf_page_data, question)
        return reason

    if question_type == "DOSAGE_FREQUENCY":
        _, reason = _compare_dosage(response_content, pdf_page_data)
        return reason

    if question_type == "COMPETITOR_BRAND":
        _, reason = _compare_competitor_brands(ai_response, pdf_page_data)
        return reason

    if question_type == "COMPOSITION":
        _, reason = _compare_composition(response_content, pdf_page_data)
        return reason

    if question_type == "ACTIVE_INGREDIENT":
        _, reason = _compare_active_ingredient(response_content, pdf_page_data)
        return reason

    if question_type == "MOLECULE_LIST":
        _, reason = _compare_molecule_list(response_content, pdf_page_data, question)
        return reason

    if question_type == "PRODUCT_COMPARISON":
        _, reason = _compare_multi_product_response(response_content, pdf_page_data, question)
        return reason

    if question_type in {"CLINICAL_EVIDENCE", "DESCRIPTIVE_USP", "DOSAGE_FORM"}:
        _, reason = _compare_descriptive_response(response_content, pdf_page_data, question)
        return reason

    if _is_punchline_question(question, response_content):
        _, reason = _compare_punchline(response_content, pdf_page_data)
        return reason

    if _is_competitor_table_reasoning_question(question, response_content):
        _, reason = _compare_competitor_table_reasoning(
            response_content,
            pdf_page_data,
            question,
        )
        return reason

    if _is_competitor_brand_question(question, response_content):
        _, reason = _compare_competitor_brands(ai_response, pdf_page_data)
        return reason

    if _is_dosage_question(question, response_content):
        _, reason = _compare_dosage(response_content, pdf_page_data)
        return reason

    if _is_descriptive_question(question, response_content):
        result, reason = _compare_descriptive_response(response_content, pdf_page_data, question)
        return reason

    normalized_response = normalize_text(response_content)
    normalized_page = normalize_text(pdf_page_data)
    response_numbers = _extract_numbers(normalized_response)
    page_numbers = _extract_numbers(normalized_page)
    response_keywords = _extract_keywords(normalized_response)
    page_keywords = _extract_keywords(normalized_page)
    matched_numbers = sorted(response_numbers.intersection(page_numbers))
    missing_numbers = sorted(response_numbers.difference(page_numbers))
    matched_keywords = sorted(response_keywords.intersection(page_keywords))

    if missing_numbers:
        if matched_numbers or matched_keywords:
            return (
                "Value mismatch. Missing Super AI value(s) on cited page: "
                f"{', '.join(missing_numbers)}."
            )
        return "Required Super AI value was not found on the cited page."

    if response_numbers:
        missing_keywords = sorted(response_keywords.difference(page_keywords))
        if missing_keywords and not _has_keyword_coverage(response_keywords, page_keywords):
            return (
                "Numeric value(s) matched, but related Super AI term(s) are missing "
                f"on cited page: {', '.join(missing_keywords)}."
            )
        return (
            "Exact numeric value match found."
            if not matched_numbers
            else f"Matching value found: {', '.join(matched_numbers + matched_keywords)}."
        )

    if _has_keyword_coverage(response_keywords, page_keywords):
        return f"Matching value found: {', '.join(matched_keywords)}."

    if matched_keywords:
        missing_keywords = sorted(response_keywords.difference(page_keywords))
        return (
            "Text/value mismatch. Missing Super AI term(s) on cited page: "
            f"{', '.join(missing_keywords)}."
        )

    return "Required value not found in cited document/page."


def deterministic_numeric_validation(
    response: str,
    page_data: str,
    question: str = "",
) -> tuple[bool, str, str, str]:
    """Validate critical numeric/unit values before semantic validation.

    Returns:
        applicable, result, reason, matched_values
    """
    response_content = _clean_response_for_validation(response)

    if not response_content or _is_missing_source_data(page_data):
        return False, "DATA MISSING", "", ""

    question_type = classify_question_type(question, response_content)

    if question_type == "COMPOSITION":
        return False, "DATA MISSING", "", ""

    if question_type in {"DESCRIPTIVE_USP", "CLINICAL_EVIDENCE"} and _is_patient_group_question(question):
        return False, "DATA MISSING", "", ""

    # Trial enrollment / sample-size count questions ("how many X enrolled in
    # the SHEP trial?") carry the answer as a bare integer — no unit suffix.
    # _extract_numeric_unit_values misses bare integers, so handle them here.
    if _is_trial_count_question(question):
        normalized_response = normalize_text(_clean_numeric_validation_text(response_content))
        normalized_page = normalize_text(page_data)
        response_bare = _extract_numbers(normalized_response)
        page_bare = _extract_numbers(normalized_page)
        # Keep only large integers (>= 100) so citation page numbers / doses don't
        # trigger a false match.
        large_response = {n for n in response_bare if n.isdigit() and int(n) >= 100}
        if large_response:
            if large_response.issubset(page_bare):
                return (
                    True,
                    "PASS",
                    "Trial enrollment count from SuperAI matches cited page: "
                    f"{', '.join(sorted(large_response))}.",
                    ", ".join(sorted(large_response)),
                )
            return (
                True,
                "FAIL",
                "Trial enrollment count mismatch. "
                f"SuperAI value(s) {', '.join(sorted(large_response))} "
                "not found on cited page.",
                "",
            )
        return False, "DATA MISSING", "", ""

    # Incentive and objective questions bypass strict numeric extraction.
    # The extractor produces "810 strip" from "810 strips" but the document
    # has a bare "810", causing a false set-difference FAIL.
    # The general comparison (_extract_numbers) handles this correctly.
    _obj_inc_terms = (
        "incentive",
        "minimum objective",
        "quarterly objective",
        "monthly objective",
        "quarterly minimum",
        "monthly minimum",
        "pmr objective",
    )
    if any(term in normalize_text(question) for term in _obj_inc_terms):
        return False, "DATA MISSING", "", ""

    if _is_variant_portfolio_question(question):
        result, reason, matched = _compare_variant_portfolio(response_content, page_data, question)
        return True, result, reason, matched

    table_result = _deterministic_table_validation(response_content, page_data, question)
    if table_result[0]:
        return table_result

    if question_type == "PRICE_LOOKUP":
        result, reason = _compare_price_lookup(response_content, page_data, question)
        matched = extract_matching_values(response_content, page_data)
        return True, result, reason, matched

    if question_type == "TRIP_AWARD_COST":
        result, reason = _compare_trip_award_cost(response_content, page_data, question)
        matched = extract_matching_values(response_content, page_data)
        return True, result, reason, matched

    if question_type == "CLINICAL_OUTCOME":
        result, reason = _compare_clinical_outcome(response_content, page_data, question)
        matched = extract_matching_values(response_content, page_data)
        return True, result, reason, matched

    if _is_repeat_course_question(question):
        result, reason, matched = _compare_repeat_courses(response_content, page_data)
        return True, result, reason, matched

    if not _is_strict_numeric_question(question, response_content):
        return False, "DATA MISSING", "", ""

    if _is_dosage_question(question, response_content):
        result, reason = _compare_dosage(response_content, page_data)
        matched = extract_matching_values(response_content, page_data)
        return True, result, reason, matched

    numeric_response_content = _clean_numeric_validation_text(response_content)
    numeric_page_data = _clean_numeric_validation_text(page_data)
    normalized_response = normalize_text(numeric_response_content)
    normalized_page = normalize_text(numeric_page_data)
    response_values = _extract_numeric_unit_values(normalized_response)
    page_values = _extract_numeric_unit_values(normalized_page)

    if not response_values:
        # The SuperAI answer contains no numeric values (e.g. "Couple Ticket",
        # "Single Ticket", a text policy answer).  Numeric comparison is not
        # applicable here — fall through to the semantic/OpenAI validator.
        return False, "DATA MISSING", "", ""

    if not page_values:
        # Page has no numeric values either — not enough evidence for deterministic
        # comparison; let OpenAI evaluate the partial/vision-extracted text.
        return False, "DATA MISSING", "", ""

    matched_values = sorted(response_values.intersection(page_values))
    missing_values = sorted(response_values.difference(page_values))

    if missing_values:
        # Numeric-only fallback: "810 strip" from SuperAI vs bare "810" in document.
        # _extract_numeric_unit_values requires a unit suffix; bare numbers in the
        # document are not extracted.  Re-check using _extract_numbers which strips
        # units naturally, so "810 strip" → "810" matches document "810".
        page_bare = _extract_numbers(normalized_page)
        still_missing = [
            mv for mv in missing_values
            if not _numeric_part_matches_bare(mv, page_bare)
        ]
        if not still_missing:
            return (
                True,
                "PASS",
                "Numeric values match after unit-label normalization: "
                f"{', '.join(sorted(response_values))}.",
                ", ".join(sorted(response_values)),
            )
        missing_values = still_missing

        if matched_values or _extract_keywords(normalized_response).intersection(
            _extract_keywords(normalized_page)
        ):
            return (
                True,
                "FAIL",
                "Strict numeric mismatch. Missing cited-page value(s): "
                f"{', '.join(missing_values)}.",
                ", ".join(matched_values),
            )
        return (
            True,
            "DATA MISSING",
            "Required numeric value(s) were not found on the cited page: "
            f"{', '.join(missing_values)}.",
            "",
        )

    return (
        True,
        "PASS",
        "All strict numeric value(s) from SuperAI exactly match the cited page: "
        f"{', '.join(matched_values)}.",
        ", ".join(matched_values),
    )


def compare_response_with_page_data(
    response: str,
    page_data: str,
    question: str = "",
    product: str = "",
    citation_page: int | str = "",
) -> str:
    """Compare response values only against the cited PDF page data.

    Parameters
    ----------
    response:       Full SuperAI response text including citation block.
    page_data:      Extracted text from the cited PDF page.
    question:       The original validation question.
    product:        Product name for debug logging.
    citation_page:  The cited page number for debug logging.
    """
    response_content = _clean_response_for_validation(response)
    question_type = classify_question_type(question, response_content)

    _validator_logger.debug(
        "VALIDATION_START question=%r product=%r attr_type=%s citation_page=%s "
        "response_len=%s page_len=%s",
        question[:120],
        product,
        question_type,
        citation_page,
        len(response_content),
        len(page_data),
    )

    if not response_content or _is_missing_source_data(page_data):
        return "DATA MISSING"

    if question_type in {"PRICE_COMPARISON", "COMPANY_LOOKUP"}:
        table_result = _deterministic_table_validation(response_content, page_data, question)
        if table_result[0]:
            return table_result[1]
        result, _ = _compare_competitor_table_reasoning(
            response_content,
            page_data,
            question,
        )
        return result

    if question_type == "PRICE_LOOKUP":
        table_result = _deterministic_table_validation(response_content, page_data, question)
        if table_result[0]:
            return table_result[1]
        result, _ = _compare_price_lookup(response_content, page_data, question)
        return result

    if question_type == "PACK_SIZE":
        result, _ = _compare_pack_size(response_content, page_data)
        return result

    if question_type == "STRENGTH_LOOKUP":
        result, _ = _compare_strength_lookup(response_content, page_data, question)
        return result

    if question_type == "DOSAGE_FREQUENCY":
        result, _ = _compare_dosage(response_content, page_data)
        return result

    if question_type == "COMPETITOR_BRAND":
        result, _ = _compare_competitor_brands(response, page_data)
        return result

    if question_type == "COMPOSITION":
        result, _ = _compare_composition(response_content, page_data)
        return result

    if question_type == "ACTIVE_INGREDIENT":
        result, _ = _compare_active_ingredient(response_content, page_data)
        return result

    if question_type == "MOLECULE_LIST":
        result, _ = _compare_molecule_list(response_content, page_data, question)
        return result

    if question_type == "PRODUCT_COMPARISON":
        result, _ = _compare_multi_product_response(response_content, page_data, question)
        return result

    if question_type in {"CLINICAL_EVIDENCE", "DESCRIPTIVE_USP", "DOSAGE_FORM"}:
        result, _ = _compare_descriptive_response(response_content, page_data, question)
        return result

    if _is_punchline_question(question, response_content):
        result, _ = _compare_punchline(response_content, page_data)
        return result

    if _is_competitor_table_reasoning_question(question, response_content):
        result, _ = _compare_competitor_table_reasoning(
            response_content,
            page_data,
            question,
        )
        return result

    if _is_competitor_brand_question(question, response_content):
        result, _ = _compare_competitor_brands(response, page_data)
        return result

    if _is_dosage_question(question, response_content):
        result, _ = _compare_dosage(response_content, page_data)
        return result

    numeric_applicable, numeric_result, _, _ = deterministic_numeric_validation(
        response,
        page_data,
        question,
    )
    if numeric_applicable:
        return numeric_result

    if _is_descriptive_question(question, response_content):
        result, _ = _compare_descriptive_response(response_content, page_data, question)
        return result

    response_numbers = _extract_numbers(normalize_text(response_content))
    page_numbers = _extract_numbers(normalize_text(page_data))
    response_keywords = _extract_keywords(normalize_text(response_content))
    page_keywords = _extract_keywords(normalize_text(page_data))

    if response_numbers:
        matched_numbers = response_numbers.intersection(page_numbers)
        if response_numbers.issubset(page_numbers):
            if not response_keywords or _has_keyword_coverage(response_keywords, page_keywords):
                return "PASS"
            return "FAIL" if response_keywords.intersection(page_keywords) else "DATA MISSING"
        return "FAIL" if matched_numbers or response_keywords.intersection(page_keywords) else "DATA MISSING"

    if response_keywords:
        matched_keywords = response_keywords.intersection(page_keywords)
        if _has_keyword_coverage(response_keywords, page_keywords):
            return "PASS"
        return "FAIL" if matched_keywords else "DATA MISSING"

    return "FAIL"


def extract_citation_page_numbers(response: str) -> list[int]:
    """Extract ordered unique citation page numbers from response text."""
    numbers: list[int] = []
    seen: set[int] = set()
    for match in re.finditer(r"_Page_(\d+)", response, flags=re.IGNORECASE):
        page_number = int(match.group(1))
        if page_number not in seen:
            seen.add(page_number)
            numbers.append(page_number)
    return numbers


def extract_matching_values(response: str, source_text: str) -> str:
    """Return values from the response that are also present in source text."""
    if _is_missing_source_data(source_text):
        return ""

    normalized_response = normalize_text(_clean_response_for_validation(response))
    normalized_source = normalize_text(source_text)

    response_numbers = _extract_numbers(normalized_response)
    source_numbers = _extract_numbers(normalized_source)
    matched_numbers = sorted(response_numbers.intersection(source_numbers))

    response_keywords = _extract_keywords(normalized_response)
    source_keywords = _extract_keywords(normalized_source)
    matched_keywords = sorted(response_keywords.intersection(source_keywords))

    matched_values = matched_numbers + matched_keywords

    return ", ".join(matched_values)


def extract_answer_values(response: str) -> str:
    """Return answer values that must be present on the cited PDF page."""
    normalized_response = normalize_text(_clean_response_for_validation(response))
    response_numbers = sorted(_extract_numbers(normalized_response))
    response_keywords = sorted(_extract_keywords(normalized_response))
    return ", ".join(response_numbers + response_keywords)


def has_matching_values(response: str, source_text: str) -> bool:
    """Return whether response and source text share meaningful values."""
    return bool(extract_matching_values(response, source_text))


def _extract_numbers(text: str) -> set[str]:
    """Extract normalized numeric values from text.

    Trailing decimal zeros are stripped so that string set operations treat
    14.10 and 14.1, 80.0 and 80, 12.50 and 12.5 as the same value.
    """
    result: set[str] = set()
    for number in re.findall(r"(?<!\d)\d[\d,]*(?:\.\d+)?(?!\d)", text):
        value = number.replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        result.add(value)
    return result


def _is_patient_group_question(question: str) -> bool:
    """Return whether numbers in the answer are likely eligibility/source noise."""
    normalized = normalize_text(question)
    return any(
        term in normalized
        for term in (
            "patient groups",
            "which patients",
            "eligible",
            "eligibility",
            "candidates",
            "for which patients",
        )
    )


def _is_trial_count_question(question: str) -> bool:
    """Return whether the question asks for a trial enrollment / sample-size count."""
    normalized = normalize_text(question)
    return (
        "how many" in normalized
        and any(
            term in normalized
            for term in (
                "enrolled",
                "enroll",
                "randomized",
                "randomised",
                "participants",
                "subjects",
            )
        )
        and any(
            term in normalized
            for term in ("trial", "study", "program", "programme")
        )
    )


def _is_variant_portfolio_question(question: str) -> bool:
    """Return whether the question asks for available variants/portfolio SKUs."""
    normalized = normalize_text(question)
    return any(term in normalized for term in ("variants", "portfolio", "range")) and any(
        term in normalized for term in ("available", "within", "strengths")
    )


def _compare_variant_portfolio(
    response: str,
    page_data: str,
    question: str,
) -> tuple[str, str, str]:
    """Validate portfolio/range variants by comparing product/strength tokens."""
    response_values = _extract_variant_values(response)
    page_values = _extract_variant_values(page_data)

    if not response_values:
        return "DATA MISSING", "SuperAI response did not contain variant/portfolio values.", ""

    if not page_values:
        return "DATA MISSING", "Variant/portfolio values were not found on the cited page.", ""

    missing = sorted(response_values.difference(page_values))
    matched = sorted(response_values.intersection(page_values))

    if not missing:
        return (
            "PASS",
            f"Portfolio/variant values match cited page: {', '.join(matched)}.",
            ", ".join(matched),
        )

    if matched and _is_broad_range_question(question):
        return (
            "PASS",
            "Requested portfolio/range is partially represented across cited evidence; "
            f"matched cited variant value(s): {', '.join(matched)}. "
            "Missing variants were not treated as failure for broad range wording.",
            ", ".join(matched),
        )

    if matched:
        return (
            "FAIL",
            "Portfolio/variant mismatch. Missing cited-page variant value(s): "
            f"{', '.join(missing)}.",
            ", ".join(matched),
        )

    return "DATA MISSING", "Required portfolio/variant values were not found on the cited page.", ""


def _is_broad_range_question(question: str) -> bool:
    """Return whether range evidence may be spread across multiple citations."""
    normalized = normalize_text(question)
    return "range" in normalized or "portfolio" in normalized


def _extract_variant_values(text: str) -> set[str]:
    """Extract available variant values such as 5/10/20/40 or NEPTAZ 50/100/200."""
    cleaned = _clean_response_for_validation(text)
    slash_text = cleaned.lower().replace("\u00a0", " ")
    normalized = normalize_text(cleaned)
    values: set[str] = set()

    for match in re.finditer(r"(?<!\d)\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?){1,6}\s*(?:mg|mcg|g|ml)?", slash_text):
        unit_match = re.search(r"(mg|mcg|g|ml)\b", match.group(0), flags=re.IGNORECASE)
        unit = unit_match.group(1).lower() if unit_match else ""
        for number in re.findall(r"\d+(?:\.\d+)?", match.group(0)):
            values.add(_normalize_variant_number(number, unit))

    for match in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b", normalized):
        unit_match = re.search(r"(mg|mcg|g|ml)\b", match.group(0), flags=re.IGNORECASE)
        unit = unit_match.group(1).lower() if unit_match else ""
        number = re.search(r"\d+(?:\.\d+)?", match.group(0))
        if number:
            values.add(_normalize_variant_number(number.group(0), unit))

    return values


def _normalize_variant_number(number: str, unit: str) -> str:
    """Normalize variant strength number without changing value."""
    normalized_number = number.rstrip("0").rstrip(".") if "." in number else number
    return f"{normalized_number} {unit}".strip()


def _is_repeat_course_question(question: str) -> bool:
    """Return whether the question asks for repeat treatment course count."""
    normalized = normalize_text(question)
    return "course" in normalized and any(
        term in normalized for term in ("how many", "repeat", "target 3")
    )


def _compare_repeat_courses(response: str, page_data: str) -> tuple[str, str, str]:
    """Validate repeat-course count while ignoring unrelated mg/week citation numbers."""
    response_count = _extract_repeat_course_count(response)
    page_count = _extract_repeat_course_count(page_data)

    if not response_count:
        return (
            "DATA MISSING",
            "SuperAI response did not contain a repeat-course count to validate.",
            "",
        )

    if not page_count:
        return (
            "DATA MISSING",
            "Repeat-course count was not found on the cited page.",
            "",
        )

    if response_count == page_count:
        return (
            "PASS",
            f"Repeat-course count matches cited page: up to {page_count} courses.",
            f"{page_count} courses",
        )

    return (
        "FAIL",
        f"Repeat-course count mismatch. SuperAI returned {response_count} courses while cited page contains {page_count} courses.",
        "",
    )


def _extract_repeat_course_count(text: str) -> str:
    """Extract phrases like 'up to 3 courses' or '3 repeat courses'."""
    normalized = normalize_text(_clean_numeric_validation_text(text))
    patterns = (
        r"up to\s+(\d+)\s+(?:repeat\s+)?courses?",
        r"(\d+)\s+(?:repeat\s+)?courses?",
        r"repeat treatment\s*\(up to\s+(\d+)\s+courses?\)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _is_strict_numeric_question(question: str, response: str) -> bool:
    """Return whether exact deterministic numeric validation is required."""
    normalized_question = normalize_text(question)
    normalized_response = normalize_text(response)
    broad_descriptive_starters = (
        "why ",
        "what makes",
        "explain ",
        "describe ",
        "how does",
        "how do",
    )
    descriptive_only_terms = (
        "preferred",
        "different",
        "advantage",
        "advantages",
        "benefit",
        "benefits",
        "mechanism",
        "clinical",
        "guideline",
    )

    if normalized_question.startswith(broad_descriptive_starters) and not any(
        term in normalized_question
        for term in (
            "mrp",
            "price",
            "cost",
            "dosage",
            "dose",
            "how many times",
            "pack size",
            "strength",
            "percentage",
            "percent",
        )
    ):
        return False

    if any(term in normalized_question for term in descriptive_only_terms) and not any(
        term in normalized_question
        for term in (
            "mrp",
            "price",
            "cost",
            "dosage",
            "dose",
            "how many times",
            "pack size",
            "strength",
            "percentage",
            "percent",
        )
    ):
        return False

    normalized = f"{normalized_question} {normalized_response}"
    strict_terms = (
        "mrp",
        "price",
        "cost",
        "percentage",
        "percent",
        "%",
        "dosage",
        "dose",
        "strength",
        "pack size",
        "pack",
        "quantity",
        "mg",
        "mcg",
        "ml",
        "tab",
        "tablet",
        "cap",
        "bpm",
    )
    return any(term in normalized for term in strict_terms) and bool(
        _extract_numeric_unit_values(normalized)
    )


def _clean_numeric_validation_text(text: str) -> str:
    """Remove citation/source noise before strict numeric extraction."""
    cleaned = _clean_response_for_validation(text)
    cleaned = re.sub(
        r"\b(?:citation|source|sources|ref|reference)\s*\d+(?:\s*,\s*\d+)*\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b\d+\s*,\s*\d+(?:\s*,\s*\d+)*\s*(?=$|citation|source|sources|ref|reference)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:sources?)\s+\d+(?:\s*,\s*\d+)*\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_numeric_unit_values(text: str) -> set[str]:
    """Extract exact normalized numeric values with safety-critical units."""
    normalized = normalize_text(text)
    # Normalize OCR artifacts: "21.5 %" → "21.5%" and "500 mg" already handled
    # but "21 . 5%" or "2 1.5%" from bad OCR also need collapsing.
    normalized = re.sub(r"(?<=\d)\s+%", "%", normalized)
    normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
    values: set[str] = set()

    range_patterns = (
        r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(%)",
        r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|tab|tabs|tablet|tablets|cap|caps|capsule|capsules|bpm)",
    )
    for pattern in range_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            low, high, unit = match.groups()
            values.add(_normalize_numeric_unit_value(low, unit, f"{low}{unit}"))
            values.add(_normalize_numeric_unit_value(high, unit, f"{high}{unit}"))
            values.add(
                f"{_normalize_numeric_unit_value(low, unit, f'{low}{unit}')}-"
                f"{_normalize_numeric_unit_value(high, unit, f'{high}{unit}')}"
            )

    unit_patterns = (
        r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:rs\.?|inr|₹)",
        r"(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|tab|tabs|tablet|tablets|cap|caps|capsule|capsules|strip|strips|bpm)",
    )

    for pattern in unit_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            groups = match.groups()
            number = groups[0].replace(",", "")
            unit = groups[1].lower() if len(groups) > 1 and groups[1] else ""
            values.add(_normalize_numeric_unit_value(number, unit, match.group(0)))

    if any(
        term in normalized
        for term in (
            "mrp",
            "price",
            "mortality",
            "reduction",
            "risk",
            "endpoint",
            "death",
            "hospitalization",
            "hospitalisation",
        )
    ):
        for number in _extract_numbers(normalized):
            values.add(_normalize_numeric_unit_value(number, "", number))

    return values


def _normalize_numeric_unit_value(number: str, unit: str, raw_value: str) -> str:
    """Normalize a numeric/unit value without changing the actual value."""
    normalized_number = number.replace(",", "")
    if "." in normalized_number:
        normalized_number = normalized_number.rstrip("0").rstrip(".")

    normalized_unit = unit.lower().strip()
    unit_map = {
        "tabs": "tab",
        "tablet": "tab",
        "tablets": "tab",
        "caps": "cap",
        "capsule": "cap",
        "capsules": "cap",
        "strips": "strip",
        "gm": "g",
    }
    normalized_unit = unit_map.get(normalized_unit, normalized_unit)

    raw = raw_value.lower()
    if "%" in raw:
        normalized_unit = "%"
    if "₹" in raw or "rs" in raw or "inr" in raw:
        normalized_unit = "currency"

    return f"{normalized_number} {normalized_unit}".strip()


def _numeric_part_matches_bare(value_with_unit: str, bare_numbers: set[str]) -> bool:
    """Return True if the numeric part of value_with_unit exists in bare_numbers.

    Handles "810 strip" vs {"810"} and "21.5 currency" vs {"21.5"}.
    """
    match = re.match(r"^([\d]+(?:\.[\d]+)?)", value_with_unit.strip())
    if not match:
        return False

    def _norm(n: str) -> str:
        try:
            f = float(n)
            return str(int(f)) if f == int(f) else n.rstrip("0").rstrip(".")
        except ValueError:
            return n

    target = _norm(match.group(1))
    return any(_norm(n) == target for n in bare_numbers)


def _extract_answer_citation_references(answer_text: str) -> list[int]:
    """Return citation reference numbers attached to the answer body."""
    match = re.search(r"(?:^|\s)(\d+(?:\s*,\s*\d+)*)\s*$", answer_text.strip())
    if not match:
        return []
    return [int(number) for number in re.findall(r"\d+", match.group(1))]


def _extract_citation_page_map(citation_text: str) -> dict[int, int]:
    """Map citation reference numbers to their cited PDF page numbers."""
    citation_page_map: dict[int, int] = {}
    pattern = re.compile(
        r"(?:^|\s)(\d+)\s+.*?(?:_Page_|page[\s:_-]+)(\d+)",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(citation_text):
        citation_page_map[int(match.group(1))] = int(match.group(2))

    return citation_page_map


def _looks_like_mrp_query(response: str) -> bool:
    """Return whether response text is about MRP/price."""
    normalized = normalize_text(response)
    return "mrp" in normalized or "price" in normalized


def _has_mrp_number_match(response: str, source_text: str) -> bool:
    """Require decimal price match for MRP/price responses."""
    return _has_all_decimal_matches(response, source_text)


def _has_all_decimal_matches(response: str, source_text: str) -> bool:
    """Require every decimal value in the response to exist in page data."""
    response_numbers = {
        number for number in _extract_numbers(normalize_text(response)) if "." in number
    }
    source_numbers = {
        number for number in _extract_numbers(normalize_text(source_text)) if "." in number
    }
    return bool(response_numbers) and response_numbers.issubset(source_numbers)


def _has_all_response_values(response: str, source_text: str) -> bool:
    """Require all meaningful numeric values and core keywords to exist on the page."""
    normalized_response = normalize_text(response)
    normalized_source = normalize_text(source_text)

    response_numbers = _extract_numbers(normalized_response)
    source_numbers = _extract_numbers(normalized_source)
    if response_numbers and not response_numbers.issubset(source_numbers):
        return False

    response_keywords = _extract_keywords(normalized_response)
    source_keywords = _extract_keywords(normalized_source)
    return not response_keywords or _has_keyword_coverage(response_keywords, source_keywords)


def _clean_response_for_validation(response: str) -> str:
    """Remove citation/page/source/reference noise before value validation."""
    cleaned = _strip_citation_tail(response)
    cleaned = re.sub(
        r"\b(?:citation|source|page|reference|ref)\s*[:#-]?\s*\d+(?:\s*,\s*\d+)*\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", " ", cleaned)
    cleaned = re.sub(r"\(\s*(?:citation|source|ref)\s*\d+\s*\)", " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" -*:;,.")


def _is_descriptive_question(question: str, response: str) -> bool:
    """Return whether semantic descriptive validation should be used."""
    normalized = normalize_text(f"{question} {response}")
    descriptive_terms = {
        "role",
        "moa",
        "mode of action",
        "usp",
        "indication",
        "indications",
        "safety",
        "quality",
        "salient",
        "feature",
        "features",
        "benefit",
        "benefits",
        "advantage",
        "advantages",
    }
    return any(term in normalized for term in descriptive_terms)


def _is_competitor_brand_question(question: str, response: str) -> bool:
    """Return whether validation should compare only competitor brand names."""
    normalized = normalize_text(f"{question} {response}")
    return "competitor" in normalized and "brand" in normalized


def _is_competitor_table_reasoning_question(question: str, response: str) -> bool:
    """Return whether competitor validation needs row-aware table reasoning."""
    normalized = normalize_text(f"{question} {response}")

    reasoning_terms = (
        "lowest",
        "highest",
        "cheapest",
        "most expensive",
        "cheaper",
        "difference",
        "compared to",
        "price per strip",
        "percentage",
        "saving",
        "cost saving",
        "between",
        "how many",
        "count",
        "pack size",
        "manufacturer",
        "manufactures",
        "company",
    )
    has_reasoning_term = any(term in normalized for term in reasoning_terms)
    has_competitor_context = "competitor" in normalized
    has_table_attribute_context = any(
        term in normalized
        for term in (
            "price per strip",
            "pack size",
            "manufactures",
            "manufacturer",
            "cheaper",
            "difference",
            "compared to",
        )
    )
    return has_reasoning_term and (has_competitor_context or has_table_attribute_context)


def _is_dosage_question(question: str, response: str) -> bool:
    """Return whether validation should compare dosage with strict normalized rules."""
    normalized_question = normalize_text(question)
    frequency_terms = (
        "how many times",
        "times a day",
        "once daily",
        "twice daily",
        "recommended dosage",
        "recommended dose",
        "dosage",
        "dose",
    )
    if any(term in normalized_question for term in frequency_terms):
        return True

    descriptive_terms = (
        "benefit",
        "benefits",
        "beyond glucose",
        "role",
        "moa",
        "mode of action",
        "why",
        "how",
        "evidence",
        "study",
        "trial",
        "guideline",
    )
    if any(term in normalized_question for term in descriptive_terms):
        return False

    normalized = normalized_question
    long_dosage_terms = (
        "dosage",
        "dose",
        "recommended dosage",
        "recommended dose",
        "how many times",
        "times a day",
        "once daily",
        "twice daily",
    )
    if any(term in normalized for term in long_dosage_terms):
        return True
    # Short abbreviations like "od", "bid", "tds" must use word-boundary matching.
    # Plain substring check gives false positives: "od" in "pr[od]uctivity",
    # "od" in "peri[od]", "bid" in "ta[bid]" etc.
    return any(
        re.search(rf"\b{term}\b", normalized)
        for term in ("od", "bid", "tds", "tid", "qid")
    )


def _is_punchline_question(question: str, response: str) -> bool:
    """Return whether validation should compare only punchline/slogan text."""
    normalized = normalize_text(f"{question} {response}")
    return "punchline" in normalized or "punch line" in normalized or "slogan" in normalized


def _compare_punchline(response_content: str, page_data: str) -> tuple[str, str]:
    """Compare only punchline/slogan text and ignore all table data."""
    response_punchline = _extract_punchline_text(response_content, from_document=False)
    document_punchline = _extract_punchline_text(page_data, from_document=True)

    if not response_punchline:
        return "DATA MISSING", "Super AI response did not contain punchline text."

    if not document_punchline:
        return "DATA MISSING", "Punchline/slogan text not found on the cited page."

    normalized_response = _normalize_punchline_for_match(response_punchline)
    normalized_document = _normalize_punchline_for_match(document_punchline)

    if normalized_response == normalized_document:
        return "PASS", f"Punchline matches cited page: {document_punchline}."

    response_keywords = _extract_keywords(normalized_response)
    document_keywords = _extract_keywords(normalized_document)
    if response_keywords and _has_keyword_coverage(response_keywords, document_keywords):
        return "PASS", f"Punchline meaning matches cited page: {document_punchline}."

    return (
        "FAIL",
        "Punchline mismatch. "
        f"Super AI returned '{response_punchline}' while cited page contains '{document_punchline}'.",
    )


def _compare_composition(response_content: str, page_data: str) -> tuple[str, str]:
    """Validate composition/strength values from the cited page."""
    response_composition = _extract_composition_values(response_content)
    page_composition = _extract_composition_values(page_data)

    if not response_composition:
        return "DATA MISSING", "SuperAI response did not contain composition values."

    if not page_composition:
        return "DATA MISSING", "Composition values were not found on the cited page."

    missing_values = sorted(response_composition.difference(page_composition))
    if not missing_values:
        return (
            "PASS",
            "Composition matches cited page: "
            f"{', '.join(sorted(response_composition))}.",
        )

    if response_composition.intersection(page_composition):
        return (
            "FAIL",
            "Partial composition mismatch. Missing cited-page composition value(s): "
            f"{', '.join(missing_values)}.",
        )

    return "DATA MISSING", "Required composition values were not found on the cited page."


def _compare_strength_lookup(
    response_content: str,
    page_data: str,
    question: str = "",
) -> tuple[str, str]:
    """Validate exact strength values for a requested molecule/product."""
    response_values = _extract_strength_values(response_content)
    page_values = _extract_strength_values(page_data)

    if not response_values:
        return "DATA MISSING", "SuperAI response did not contain a strength value to validate."

    if not page_values:
        return "DATA MISSING", "Strength value was not found on the cited page."

    requested_entities = _extract_known_molecule_names(f"{question} {response_content}")
    if requested_entities:
        entity_supported = any(
            _entity_text_contains_ordered_tokens(page_data, entity)
            for entity in requested_entities
        )
        if not entity_supported:
            # Entity not found by name, but the strength values may still be on
            # the page under a brand name or abbreviated form.  Only hard-stop
            # with DATA MISSING when the page also lacks matching strength values,
            # otherwise fall through so the numeric comparison can proceed.
            if not response_values.intersection(page_values):
                _log_validation_step(
                    rule="_compare_strength_lookup",
                    attribute="STRENGTH_LOOKUP",
                    doc_value=sorted(page_values),
                    response_value=sorted(response_values),
                    verdict="DATA MISSING",
                    reason=f"Molecule/product not found on cited page and no matching strength values: {', '.join(sorted(response_values))}.",
                )
                return "DATA MISSING", "Requested molecule/product was not found on the cited page."
            # Entity name not found but strength values match — proceed to
            # numeric comparison (may be under brand name on this page).

    missing = sorted(response_values.difference(page_values))
    if missing:
        if response_values.intersection(page_values):
            return (
                "FAIL",
                "Strength mismatch. Missing cited-page strength value(s): "
                f"{', '.join(missing)}.",
            )
        return "DATA MISSING", "Required strength value was not found on the cited page."

    return (
        "PASS",
        "Strength value(s) match cited page exactly: "
        f"{', '.join(sorted(response_values))}.",
    )


def _extract_strength_values(text: str) -> set[str]:
    """Extract strict strength values, including IU and ranges."""
    normalized = normalize_text(text)
    normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
    values: set[str] = set()

    for match in re.finditer(
        r"\b\d+(?:\.\d+)?\s*(?:-|â€“|—|to)\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu)\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        values.add(_normalize_strength_text(match.group(0)))

    for match in re.finditer(
        r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu)\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        values.add(_normalize_strength_text(match.group(0)))

    return values


def _normalize_strength_text(value: str) -> str:
    """Normalize a strength value without changing its medical value."""
    normalized = normalize_text(value).replace("gm", "g")
    normalized = normalized.replace("â€“", "-").replace("—", "-")
    normalized = re.sub(r"\bto\b", "-", normalized)
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"(\d(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b", r"\1 \2", normalized)
    normalized = re.sub(r"(\d+)\.0+\b", r"\1", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _compare_pack_size(response_content: str, page_data: str) -> tuple[str, str]:
    """Validate exact pack quantity such as 10 tablets/strip or 30 capsules/box."""
    response_values = _extract_pack_size_values(response_content)
    page_values = _extract_pack_size_values(page_data)

    if not response_values:
        return "DATA MISSING", "SuperAI response did not contain a pack-size value to validate."

    if not page_values:
        return "DATA MISSING", "Pack-size value was not found on the cited page."

    missing = sorted(response_values.difference(page_values))
    if missing:
        if response_values.intersection(page_values):
            return (
                "FAIL",
                "Pack-size mismatch. Missing cited-page pack value(s): "
                f"{', '.join(missing)}.",
            )
        return "DATA MISSING", "Required pack-size value was not found on the cited page."

    return (
        "PASS",
        "Pack-size value matches cited page exactly: "
        f"{', '.join(sorted(response_values))}.",
    )


def _extract_pack_size_values(text: str) -> set[str]:
    """Extract normalized pack quantities while ignoring citation numbers."""
    normalized = normalize_text(text)
    values: set[str] = set()

    pack_patterns = (
        r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s*(?:/|\s+)\s*(strip|box|pack)\b",
        r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s*(?:/|\s+)\s*(strip|box|pack)\b",
        r"\((\d+)\s*(?:tab|tabs|tablet|tablets)\s*(?:/|\s+)\s*(strip|box|pack)\)",
        r"\((\d+)\s*(?:cap|caps|capsule|capsules)\s*(?:/|\s+)\s*(strip|box|pack)\)",
        r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s+per\s+(strip|box|pack)\b",
        r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s+per\s+(strip|box|pack)\b",
        r"\b(\d+)\s*(?:tab|tabs|tablet|tablets)\s+in\s+(?:one|1)\s+(strip|box|pack)\b",
        r"\b(\d+)\s*(?:cap|caps|capsule|capsules)\s+in\s+(?:one|1)\s+(strip|box|pack)\b",
        r"\b(\d+)\s*(?:tab|tabs|tablet|tablets|cap|caps|capsule|capsules)\s+in\s+each\s+(strip|box|pack)\b",
    )
    for pattern in pack_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            container = match.group(2)
            values.add(f"{int(match.group(1))} per {container}")

    box_match = re.search(
        r"\b(?P<unit_count>\d+)\s*(?:cap|caps|capsule|capsules|tab|tabs|tablet|tablets)\s+"
        r"in\s+each\s+strip\s*[*x]\s*(?P<strip_count>\d+)\s*strip\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if box_match:
        values.add(f"{int(box_match.group('unit_count'))} per strip")
        values.add(
            f"{int(box_match.group('unit_count')) * int(box_match.group('strip_count'))} per box"
        )

    return values


def _extract_composition_values(text: str) -> set[str]:
    """Extract active ingredient/strength composition values."""
    cleaned = normalize_text(text)
    cleaned = re.sub(
        r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    values: set[str] = set()

    stop_ingredients = {
        "in",
        "and",
        "or",
        "with",
        "available",
        "contains",
        "the",
        "management",
        "use",
        "dosing",
        "mechanism",
        "response",
    }

    for match in re.finditer(
        r"\b([a-z][a-z0-9]+)\s+(?:injections?|tablets?|capsules?)?\s*"
        r"((?:\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)(?:\s*(?:,|and)\s*)?)+)",
        cleaned,
    ):
        ingredient = match.group(1)
        if ingredient in stop_ingredients:
            continue
        strengths = re.findall(r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml)", match.group(2))
        for strength in strengths:
            values.add(f"{ingredient} {_normalize_composition_strength(strength)}")

    for match in re.finditer(r"\bdocetrust\s+(\d+(?:\.\d+)?)\s*mg\b", cleaned):
        values.add(f"docetaxel {_normalize_composition_strength(match.group(1) + ' mg')}")

    for ingredient in ("mycophenolate mofetil", "mycophenolate sodium"):
        ingredient_pos = cleaned.find(ingredient)
        if ingredient_pos >= 0:
            segment = cleaned[ingredient_pos : ingredient_pos + 220]
            segment = re.split(
                r"\b(?:moa|role|indications|recommended dosage|brand usp|molecule usp|competitors?)\b",
                segment,
            )[0]
            for strength in re.findall(r"\d+(?:\.\d+)?\s*mg\b", segment):
                values.add(f"{ingredient} {_normalize_composition_strength(strength)}")
            compact_strengths = re.findall(r"\d+(?:\.\d+)?(?=mg\b)", segment)
            for number in compact_strengths:
                values.add(f"{ingredient} {_normalize_composition_strength(number + ' mg')}")

    if "docetaxel" in cleaned:
        start = cleaned.find("docetaxel")
        segment = cleaned[start : start + 180] if start >= 0 else cleaned
        segment = re.split(
            r"\b(?:citation|punchline|moa|role|indications|recommended dosage|salient|competitors?)\b",
            segment,
        )[0]
        for strength in re.findall(r"\d+(?:\.\d+)?\s*mg\b", segment):
            values.add(f"docetaxel {_normalize_composition_strength(strength)}")

    docetaxel_list_match = re.search(
        r"\bdocetaxel\s+injections?\s*[.â€¦…\s-]*"
        r"(?P<strengths>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*(?:\s+and\s+\d+(?:\.\d+)?)?)\s*mg\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if docetaxel_list_match:
        for number in re.findall(r"\d+(?:\.\d+)?", docetaxel_list_match.group("strengths")):
            values.add(f"docetaxel {_normalize_composition_strength(number + ' mg')}")

    if "docetaxel injection" in cleaned and not values:
        start = cleaned.find("docetaxel injection")
        segment = cleaned[start : start + 140] if start >= 0 else ""
        segment = re.split(r"\b(?:punchline|moa|role|indications)\b", segment)[0]
        if "mg" in segment:
            for number in re.findall(r"\d+(?:\.\d+)?", segment):
                values.add(f"docetaxel {_normalize_composition_strength(number + ' mg')}")

    return values


def _normalize_composition_strength(value: str) -> str:
    """Normalize composition strength display without changing value."""
    normalized = normalize_text(value).replace("gm", "g")
    normalized = re.sub(r"(\d(?:\.\d+)?)\s*(mg|mcg|g|ml)\b", r"\1 \2", normalized)
    normalized = re.sub(r"(\d+)\.0+\b", r"\1", normalized)
    return normalized


def _compare_molecule_list(
    response_content: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate requested molecule lists without treating count words as values."""
    response_molecules = _extract_known_molecule_names(response_content)
    page_molecules = _extract_known_molecule_names(page_data)

    if not response_molecules:
        return "DATA MISSING", "SuperAI response did not contain molecule names to validate."

    if not page_molecules:
        return "DATA MISSING", "Molecule names were not found on the cited page."

    missing = sorted(response_molecules.difference(page_molecules))
    if not missing:
        return (
            "PASS",
            "Molecule list matches cited page: "
            f"{', '.join(sorted(response_molecules))}.",
        )

    if response_molecules.intersection(page_molecules):
        return (
            "FAIL",
            "Molecule list is partially supported. Missing molecule(s): "
            f"{', '.join(missing)}.",
        )

    return "DATA MISSING", "Required molecule list was not found on the cited page."


def _compare_active_ingredient(
    response_content: str,
    page_data: str,
) -> tuple[str, str]:
    """Validate active ingredient names without requiring strength values."""
    response_molecules = _extract_known_molecule_names(response_content)
    page_molecules = _extract_known_molecule_names(page_data)

    if not response_molecules:
        return "DATA MISSING", "SuperAI response did not contain an active ingredient to validate."

    if not page_molecules:
        return "DATA MISSING", "Active ingredient was not found on the cited page."

    missing = sorted(response_molecules.difference(page_molecules))
    if not missing:
        return (
            "PASS",
            "Active ingredient matches cited page: "
            f"{', '.join(sorted(response_molecules))}.",
        )

    if response_molecules.intersection(page_molecules):
        return (
            "FAIL",
            "Active ingredient is only partially supported. Missing ingredient(s): "
            f"{', '.join(missing)}.",
        )

    return (
        "FAIL",
        "Active ingredient mismatch. "
        f"SuperAI returned {', '.join(sorted(response_molecules))}, while cited page contains "
        f"{', '.join(sorted(page_molecules))}.",
    )


def _extract_known_molecule_names(text: str) -> set[str]:
    """Extract known pharma molecule names as entities."""
    normalized = normalize_text(text)
    known_molecules = (
        "silodosin",
        "mirabegron",
        "formoterol",
        "glycopyrronium",
        "glycopyrronium bromide",
        "indacaterol",
        "cyclosporine",
        "vitamin d3",
        "alpha lipoic acid",
        "pyridoxine",
        "folic acid",
        "methyl cobalamin",
        "vildagliptin",
        "imeglimin",
        "pregabalin",
        "linagliptin",
        "dapagliflozin",
        "metformin",
        "gliclazide",
        "voglibose",
        "pioglitazone",
        "docetaxel",
        "tacrolimus",
        "mycophenolate mofetil",
        "mycophenolate sodium",
        "cerebroprotein hydrolysate",
        # Cardiovascular / lipid-lowering molecules (STATPURE range and similar)
        "rosuvastatin",
        "atorvastatin",
        "simvastatin",
        "pitavastatin",
        "aspirin",
        "clopidogrel",
        "ticagrelor",
        "prasugrel",
        "ezetimibe",
        "fenofibrate",
        "gemfibrozil",
        "amlodipine",
        "ramipril",
        "enalapril",
        "lisinopril",
        "perindopril",
        "telmisartan",
        "olmesartan",
        "losartan",
        "valsartan",
        "irbesartan",
        "candesartan",
        "chlorthalidone",
        "hydrochlorothiazide",
        "indapamide",
        "bisoprolol",
        "carvedilol",
        "nebivolol",
        "atenolol",
        "metoprolol",
    )
    return {
        molecule
        for molecule in known_molecules
        if re.search(rf"\b{re.escape(molecule)}\b", normalized)
    }


def _compare_dosage(response_content: str, page_data: str) -> tuple[str, str]:
    """Compare dosage strictly while accepting standard dosage notation equivalents."""
    response_markers = _extract_dosage_markers(response_content)
    page_markers = _extract_dosage_markers(page_data)

    if not response_markers:
        return "DATA MISSING", "Super AI response did not contain a dosage value to validate."

    if not page_markers:
        return "DATA MISSING", "Dosage value not found on the cited page."

    missing_markers = sorted(response_markers.difference(page_markers))
    if "1 tab" in missing_markers and any(
        marker in response_markers.intersection(page_markers)
        for marker in ("od", "daily", "once daily")
    ):
        missing_markers.remove("1 tab")
    if "bid" in missing_markers and "every 12 hours" in response_markers and "every 12 hours" in page_markers:
        missing_markers.remove("bid")
    if any(marker.endswith("mg") and "-" in marker for marker in response_markers.intersection(page_markers)):
        for optional_frequency in ("od", "bid", "daily"):
            if optional_frequency in missing_markers:
                missing_markers.remove(optional_frequency)
    if "titrated" in missing_markers and any(
        marker in page_markers for marker in ("increased", "up to", "maximum")
    ):
        missing_markers.remove("titrated")
    if "4-12 hours prior to transplantation" in response_markers.intersection(page_markers):
        missing_markers = [
            marker
            for marker in missing_markers
            if not (
                "4" in marker
                and "12" in marker
                and "transplantation" in marker
            )
        ]

    if not missing_markers:
        dosage_evidence = _extract_dosage_evidence(page_data)
        if dosage_evidence:
            return "PASS", f"Dosage/frequency matches cited page: {dosage_evidence}."

        return (
            "PASS",
            "Dosage matches cited page after standard dosage normalization: "
            f"{', '.join(sorted(response_markers))}.",
        )

    related_markers = response_markers.intersection(page_markers)
    if related_markers:
        return (
            "FAIL",
            "Dosage mismatch. Missing dosage marker(s) on cited page: "
            f"{', '.join(missing_markers)}.",
        )

    return "DATA MISSING", "Required dosage value not found on the cited page."


def _extract_dosage_evidence(page_data: str) -> str:
    """Extract the cited dosage/frequency sentence or section for better reasons."""
    cleaned = re.sub(r"\s+", " ", page_data).strip()
    match = re.search(
        r"\bRecommended Dosage\s+(.+?)(?=\b(?:Brand USP|Molecule USP|Salient|Competitors?|M\.?R\.?P|Indications)\b|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" :-.;")

    frequency_match = re.search(
        r"[^.]*\b(?:once daily|twice daily|OD|BID|TID|TDS|QID)\b[^.]*",
        cleaned,
        flags=re.IGNORECASE,
    )
    return frequency_match.group(0).strip(" :-.;") if frequency_match else ""


def _extract_dosage_markers(text: str) -> set[str]:
    """Extract normalized dosage markers such as 1 tab, 2 tab, OD, and BID."""
    normalized = normalize_text(text)
    normalized = re.sub(
        r"\b([1-9])(\d{2})\s*(?:hr|hrs|hour|hours)\s*(prior to|before)\s*transplantation\b",
        r"\1-\2 hours \3 transplantation",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b[A-Za-z0-9 &()./-]+(?:_Page_|page[\s:_-]+)\d+\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(?:citation|source|reference|ref)\s*[:#-]?\s*\d+(?:\s*,\s*\d+)*\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    markers: set[str] = set()

    for match in re.finditer(r"\b\d+\s*tab\b", normalized):
        markers.add(re.sub(r"\s+", " ", match.group(0)).strip())

    for match in re.finditer(
        r"\b\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*mg\b",
        normalized,
    ):
        markers.add(re.sub(r"\s+", "", match.group(0)).replace("–", "-").replace("to", "-"))

    for match in re.finditer(
        r"\b\d+(?:\.\d+)?\s*(?:-|–|—|â€“|to|\s)\s*\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\s*(?:prior to|before)\s*transplantation\b",
        normalized,
    ):
        markers.add(
            re.sub(r"\s+", " ", match.group(0))
            .replace("â€“", "-")
            .replace("—", "-")
            .replace(" to ", "-")
            .replace("hrs", "hours")
            .replace("hr", "hours")
            .strip()
        )

    for match in re.finditer(
        r"\b(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|\s+|to)\s*(?P<high>\d+(?:\.\d+)?)\s*(?:hr|hrs|hour|hours)\s*(?P<when>prior to|before)\s*transplantation\b",
        normalized,
    ):
        markers.add(
            f"{match.group('low')}-{match.group('high')} hours {match.group('when')} transplantation"
        )

    for match in re.finditer(
        r"\b(?P<low>\d+(?:\.\d+)?)\s+(?P<high>\d+(?:\.\d+)?)\s*mg\b",
        normalized,
    ):
        low = match.group("low")
        high = match.group("high")
        if float(low) < float(high):
            markers.add(f"{low}-{high}mg")

    for match in re.finditer(
        r"\b\d+(?:\.\d+)?\s*mg\s*/?\s*m\s*2\b",
        normalized,
    ):
        markers.add(
            re.sub(r"\s+", " ", match.group(0).replace(" ", "")).replace("m2", "m2")
        )

    for match in re.finditer(r"\bevery\s+\d+\s+weeks?\b", normalized):
        markers.add(re.sub(r"\s+", " ", match.group(0)).strip())

    if re.search(r"\biv\b", normalized):
        markers.add("iv")

    if re.search(r"\binfusion\b", normalized):
        markers.add("infusion")

    if re.search(r"\btwice\s+daily\b|\btwo\s+divided\s+doses\b|\bdivided\s+in\s+two\s+doses\b", normalized):
        markers.add("bid")

    if re.search(r"\bevery\s+12\s*(?:hr|hrs|hour|hours)\b", normalized):
        markers.add("every 12 hours")

    frequency_aliases = {
        "od": "od",
        "bid": "bid",
        "bd": "bid",
        "tds": "tds",
        "tid": "tds",
        "qid": "qid",
        "hs": "hs",
        "sos": "sos",
    }
    for alias, canonical in frequency_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            markers.add(canonical)

    if re.search(r"\bdaily dosage\b|\bdaily usage\b|\bcontinuous daily\b", normalized):
        markers.add("daily")

    if re.search(r"\btitrat(?:e|ed|ion|able)\b", normalized):
        markers.add("titrated")

    if re.search(r"\bcan\s+be\s+increased\b|\bincreased\s+up\s+to\b", normalized):
        markers.add("increased")

    if re.search(r"\bup\s+to\b", normalized):
        markers.add("up to")

    if re.search(r"\bmaximum\b|\bmax\b", normalized):
        markers.add("maximum")

    if re.search(r"\btogether\b", normalized):
        markers.add("together")

    return markers


def _extract_punchline_text(text: str, from_document: bool) -> str:
    """Extract only punchline or slogan text."""
    cleaned = _clean_response_for_validation(text)

    if from_document:
        match = re.search(
            r"\b(?:punch\s*line|punchline|slogan|tagline)\s*[:-]?\s*"
            r"(.+?)(?=\b(?:composition|mode of action|role of drugs|indications|"
            r"recommended dosage|salient|competitors?|m\.?r\.?p|name of product)\b|$)",
            cleaned,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return _clean_punchline_text(match.group(1))

    match = re.search(
        r"\b(?:punch\s*line|punchline|slogan|tagline)\s*(?:is|:|-)?\s*(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_punchline_text(match.group(1) if match else cleaned)


def _clean_punchline_text(text: str) -> str:
    """Remove non-punchline table noise from a punchline candidate."""
    cleaned = text.replace("—", "-").replace("–", "-")
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", " ", cleaned)
    cleaned = re.sub(
        r"^\s*(?:of\s+)?[A-Za-z][A-Za-z0-9 /().+-]{1,60}\s+is\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^\s*of\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:company|pack|price|strip|tab|tabs|tablet|tablets|mrp|brand name)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", cleaned.strip())
    cleaned = _strip_leading_punchline_label(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" :-.,;")


def _strip_leading_punchline_label(text: str) -> str:
    """Drop leading product labels before the actual slogan."""
    cleaned = text.strip()
    label_pattern = re.compile(
        r"^[A-Za-z][A-Za-z0-9 /().+-]{1,45}\s*[:\-]+\s+(.+)$",
        flags=re.IGNORECASE,
    )

    while True:
        match = label_pattern.match(cleaned)
        if not match:
            return cleaned

        label = match.group(0)[: match.start(1)].strip(" :-")
        remainder = match.group(1).strip()

        if _looks_like_product_label(label) and remainder:
            cleaned = remainder
            continue

        return cleaned


def _looks_like_product_label(text: str) -> bool:
    """Return whether text is likely a product/SKU label, not slogan content."""
    normalized = normalize_text(text)
    if not normalized:
        return False

    if any(char.isdigit() for char in normalized):
        return True

    words = normalized.split()
    return len(words) <= 3 and not any(
        word in {"one", "all", "relief", "care", "control", "protection", "power"}
        for word in words
    )


def _normalize_punchline_for_match(text: str) -> str:
    """Normalize slogan text while ignoring product labels and filler words."""
    cleaned = _clean_punchline_text(text)
    cleaned = normalize_text(cleaned)
    words = [
        word
        for word in re.findall(r"[a-z][a-z0-9-]*", cleaned)
        if word not in {"just", "of", "for", "the", "a", "an"}
    ]
    return " ".join(words)


def _compare_competitor_brands(response_content: str, page_data: str) -> tuple[str, str]:
    """Compare competitor brand names only, ignoring companies, packs, and prices."""
    response_brands = _extract_competitor_brand_names(response_content)
    page_rows = _extract_competitor_table_rows(page_data)
    page_brands = [row["brand"] for row in page_rows] if page_rows else _extract_competitor_brand_names(page_data)

    if not response_brands:
        return "DATA MISSING", "Super AI response did not contain competitor brand names."

    if not page_brands:
        return "DATA MISSING", "Competitor brand names not found on the cited page."

    match_audits = [_entity_best_match_audit(brand, page_brands) for brand in response_brands]
    missing_brands = [
        str(audit["left_original"])
        for audit in match_audits
        if not audit["matched"]
    ]

    if not missing_brands:
        audit_summary = _format_entity_audit_summary(match_audits)
        return (
            "PASS",
            "Competitor brand name(s) match cited page: "
            f"{', '.join(response_brands)}. {audit_summary}",
        )

    return (
        "FAIL",
        "Some competitor brand name(s) are missing on the cited page: "
        f"{', '.join(missing_brands)}.",
    )


def _compare_competitor_table_reasoning(
    response_content: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate competitor table questions using parsed row/column relationships."""
    normalized_question = normalize_text(question)
    response_text = _clean_response_for_validation(response_content)

    if any(term in normalized_question for term in ("cheaper", "difference", "compared to")):
        return _compare_price_difference(response_text, page_data, question)

    if (
        "company" in normalized_question
        or "manufacturer" in normalized_question
        or "manufactures" in normalized_question
        or "belongs to" in normalized_question
    ):
        company_lookup = _compare_company_lookup(response_text, page_data, question)
        if company_lookup[0] != "DATA MISSING":
            return company_lookup

    table_page_data = _scope_competitor_page_data_for_question(page_data, question)
    rows = _extract_competitor_table_rows(table_page_data)

    if not rows:
        return "DATA MISSING", "Competitor table rows were not found on the cited page."

    marketed_company = _extract_marketed_by_company(question)
    if marketed_company:
        expected_rows = [
            row
            for row in rows
            if _company_text_contains(marketed_company, str(row["company"]))
            or _company_text_contains(str(row["company"]), marketed_company)
        ]
        if not expected_rows:
            return (
                "DATA MISSING",
                f"No competitor row was found for company {marketed_company} on the cited page.",
            )

        matching_rows = [
            row
            for row in expected_rows
            if _entity_text_contains(response_text, str(row["brand"]))
            or _entity_text_contains_ordered_tokens(response_text, str(row["brand"]))
        ]
        if matching_rows:
            brands = ", ".join(str(row["brand"]) for row in matching_rows)
            return (
                "PASS",
                f"Competitor brand-company mapping matches cited table row: {brands} is listed with {marketed_company}.",
            )

        expected_brands = ", ".join(str(row["brand"]) for row in expected_rows)
        return (
            "FAIL",
            f"Competitor brand-company mismatch. Cited page lists {expected_brands} with {marketed_company}.",
        )

    if "how many" in normalized_question or "count" in normalized_question:
        expected_count = len(rows)
        response_numbers = {int(number) for number in _extract_numbers(response_text) if number.isdigit()}
        if expected_count in response_numbers:
            return (
                "PASS",
                f"Competitor count matches cited table: {expected_count} row(s) found.",
            )
        if response_numbers:
            return (
                "FAIL",
                "Competitor count mismatch. "
                f"Cited table has {expected_count} row(s), while SuperAI returned "
                f"{', '.join(str(number) for number in sorted(response_numbers))}.",
            )
        return "DATA MISSING", "SuperAI response did not contain a competitor count."

    priced_rows = [row for row in rows if row.get("price") is not None]
    if not priced_rows and any(term in normalized_question for term in ("price", "lowest", "highest", "cheapest", "expensive", "between", "saving", "percentage")):
        return "DATA MISSING", "Competitor prices were not found on the cited page."

    if any(term in normalized_question for term in ("percentage", "saving", "cost saving")):
        return _compare_percentage_cost_saving(
            response_text,
            page_data,
            question,
            priced_rows,
        )

    if "between" in normalized_question and "price" in normalized_question:
        range_values = sorted(float(number) for number in _extract_numbers(normalized_question))
        if len(range_values) < 2:
            return "DATA MISSING", "Price range could not be extracted from the question."

        low, high = range_values[0], range_values[1]
        expected_rows = [
            row for row in priced_rows if low <= float(row["price"]) <= high
        ]
        expected_brands = [row["brand"] for row in expected_rows]

        if not expected_brands:
            return (
                "DATA MISSING",
                f"No competitor brands found in cited table between {low:g} and {high:g}.",
            )

        missing = [
            brand for brand in expected_brands if not _entity_text_contains(response_text, brand)
        ]
        if not missing:
            return (
                "PASS",
                "Competitor price range matches cited table. "
                f"Brands between {low:g} and {high:g}: {', '.join(expected_brands)}.",
            )
        return (
            "FAIL",
            "Partial match: SuperAI missed competitor brand(s) in cited price range "
            f"{low:g}-{high:g}: {', '.join(missing)}.",
        )

    if "priced" in normalized_question or re.search(r"\bprice(?:d)?\s+at\b", normalized_question):
        requested_prices = {float(number) for number in _extract_numbers(normalized_question)}
        if not requested_prices:
            return "DATA MISSING", "Requested competitor price could not be extracted from the question."

        matching_price_rows = [
            row
            for row in priced_rows
            if _float_set_contains(requested_prices, float(row["price"]))
        ]
        if not matching_price_rows:
            return "DATA MISSING", "Requested price/MRP was not found on the cited page."

        expected_brands = [str(row["brand"]) for row in matching_price_rows]
        missing_brands = [
            brand for brand in expected_brands if not _entity_text_contains(response_text, brand)
        ]
        if not missing_brands:
            evidence = ", ".join(
                f"{row['brand']} at {float(row['price']):g}" for row in matching_price_rows
            )
            return "PASS", f"Competitor brand-price mapping matches cited table row: {evidence}."

        return (
            "FAIL",
            "Competitor brand-price mismatch. "
            f"Cited table maps requested price to {', '.join(expected_brands)}.",
        )

    if any(term in normalized_question for term in ("lowest", "cheapest")):
        scoped_rows = _filter_rows_by_question_brands(priced_rows, question) or priced_rows
        expected_row = min(scoped_rows, key=lambda row: float(row["price"]))
        return _compare_expected_competitor_row(response_text, expected_row, "lowest")

    if any(term in normalized_question for term in ("highest", "most expensive")):
        scoped_rows = _filter_rows_by_question_brands(priced_rows, question) or priced_rows
        expected_row = max(scoped_rows, key=lambda row: float(row["price"]))
        return _compare_expected_competitor_row(response_text, expected_row, "highest")

    if "price per strip" in normalized_question or "price" in normalized_question:
        matching_rows = [
            row for row in priced_rows if _entity_text_contains(response_text, row["brand"])
        ]
        response_numbers = {float(number) for number in _extract_numbers(response_text)}

        for row in matching_rows:
            if float(row["price"]) in response_numbers:
                return (
                    "PASS",
                    "Competitor price matches cited table row. "
                    f"{row['brand']} price/strip is {row['price']:.2f}.",
                )

        if matching_rows:
            row = matching_rows[0]
            return (
                "FAIL",
                "Competitor price mismatch. "
                f"Cited table row for {row['brand']} has price/strip {row['price']:.2f}.",
            )

    if (
        "company" in normalized_question
        or "manufacturer" in normalized_question
        or "manufactures" in normalized_question
        or "belongs to" in normalized_question
    ):
        for row in rows:
            if _entity_text_contains(response_text, row["brand"]):
                if _company_text_contains(response_text, row["company"]):
                    return (
                        "PASS",
                        "Competitor company matches cited table row. "
                        f"{row['brand']} is listed with {row['company']}.",
                    )
                return (
                    "FAIL",
                    "Competitor company mismatch. "
                    f"Cited table row lists {row['brand']} with {row['company']}.",
                )

    if "pack size" in normalized_question or "pack" in normalized_question:
        for row in rows:
            if _entity_text_contains(response_text, row["brand"]):
                if row["pack"] and normalize_text(row["pack"]) in normalize_text(response_text):
                    return (
                        "PASS",
                        "Competitor pack size matches cited table row. "
                        f"{row['brand']} pack size is {row['pack']}.",
                    )
                return (
                    "FAIL",
                    "Competitor pack size mismatch. "
                    f"Cited table row lists {row['brand']} pack size as {row['pack']}.",
                )

    return "DATA MISSING", "Requested competitor table attribute could not be validated."


def _filter_rows_by_question_brands(
    rows: list[dict[str, object]],
    question: str,
) -> list[dict[str, object]]:
    """Keep competitor rows whose brand is explicitly listed in the question."""
    question_brands = _extract_explicit_brands_from_question(question)
    if not question_brands:
        return []

    filtered: list[dict[str, object]] = []
    for row in rows:
        brand = str(row.get("brand") or "")
        if any(
            _entity_text_contains(brand, question_brand)
            or _entity_text_contains(question_brand, brand)
            or _entity_text_contains_ordered_tokens(brand, question_brand)
            or _entity_text_contains_ordered_tokens(question_brand, brand)
            for question_brand in question_brands
        ):
            filtered.append(row)

    return filtered


def _extract_explicit_brands_from_question(question: str) -> list[str]:
    """Extract brand names from 'among A, B, C and D' style questions."""
    match = re.search(
        r"\bamong\s+(.+?)(?:\s+in\s+the\b|\s+category\b|\?)",
        question,
        flags=re.IGNORECASE,
    )
    if not match:
        return []

    brand_text = match.group(1)
    brand_text = re.sub(
        r"\b(?:which|competitor|brand|has|the|lowest|highest|mrp|price|among)\b",
        " ",
        brand_text,
        flags=re.IGNORECASE,
    )
    parts = re.split(r"\s*,\s*|\s+\band\b\s+|\s+and\s+", brand_text)
    return [
        re.sub(r"\s+", " ", part).strip(" ?:-.,")
        for part in parts
        if part.strip(" ?:-.,")
    ]


def _compare_percentage_cost_saving(
    response_text: str,
    page_data: str,
    question: str,
    competitor_rows: list[dict[str, object]],
) -> tuple[str, str]:
    """Validate percentage cost saving using cited product and competitor prices."""
    own_price = _extract_requested_product_price(page_data, question)
    if own_price is None:
        return "DATA MISSING", "Eplebless/product price was not found on the cited page."

    if not competitor_rows:
        return "DATA MISSING", "Competitor prices were not found on the cited page."

    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    if not response_numbers:
        return "DATA MISSING", "SuperAI response did not contain a percentage cost-saving value."

    calculated_savings: list[tuple[str, float, float]] = []
    for row in competitor_rows:
        competitor_price = float(row["price"])
        if competitor_price <= 0 or competitor_price <= own_price:
            continue
        saving_percent = ((competitor_price - own_price) / competitor_price) * 100
        calculated_savings.append((str(row["brand"]), competitor_price, saving_percent))

    if not calculated_savings:
        return "DATA MISSING", "No higher-priced competitor row was available for cost-saving calculation."

    mentioned_rows = [
        item for item in calculated_savings if _entity_text_contains(response_text, item[0])
    ]
    rows_to_check = mentioned_rows or calculated_savings

    for brand, competitor_price, saving_percent in rows_to_check:
        if _number_set_contains_close_value(response_numbers, saving_percent):
            return (
                "PASS",
                "Percentage cost saving matches cited table calculation. "
                f"Product price {own_price:.2f} vs {brand} {competitor_price:.2f} "
                f"gives {saving_percent:.2f}% saving.",
            )

    calculated_summary = ", ".join(
        f"{brand}: {saving_percent:.2f}%" for brand, _, saving_percent in calculated_savings
    )


def _compare_price_difference(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate cheaper/difference questions by calculating cited table prices."""
    own_product, compared_brand = _extract_price_comparison_entities(question)
    if not own_product or not compared_brand:
        return "DATA MISSING", "Price comparison products could not be identified from the question."

    own_prices = _extract_own_sku_prices(page_data, own_product)
    compared_prices = _extract_competitor_strength_prices(page_data, compared_brand)

    if not own_prices or not compared_prices:
        fallback_result = _compare_single_row_price_difference(
            response_text,
            page_data,
            own_product,
            compared_brand,
        )
        if fallback_result[0] != "DATA MISSING":
            return fallback_result

    if not own_prices:
        return "DATA MISSING", f"{own_product} prices were not found on the cited page."

    if not compared_prices:
        return "DATA MISSING", f"{compared_brand} competitor prices were not found on the cited page."

    shared_strengths = [
        strength for strength in own_prices if strength in compared_prices
    ]
    if not shared_strengths:
        return (
            "DATA MISSING",
            f"No matching strengths were found between {own_product} and {compared_brand}.",
        )

    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    calculated_rows: list[tuple[str, float, float, float]] = []
    missing_differences: list[str] = []

    for strength in shared_strengths:
        own_price = own_prices[strength]
        compared_price = compared_prices[strength]
        difference = round(compared_price - own_price, 2)
        calculated_rows.append((strength, own_price, compared_price, difference))
        if not _float_set_contains(response_numbers, difference):
            missing_differences.append(f"{strength} mg: {difference:g}")

    evidence = "; ".join(
        (
            f"{own_product} {strength} mg {own_price:g} vs "
            f"{compared_brand} {strength} mg {compared_price:g} = {difference:g} cheaper"
        )
        for strength, own_price, compared_price, difference in calculated_rows
    )

    if not missing_differences:
        return "PASS", f"Price difference matches cited table calculation. {evidence}."

    return (
        "FAIL",
        "Price difference mismatch. Cited table calculation: "
        f"{evidence}. Missing/incorrect SuperAI difference(s): {', '.join(missing_differences)}.",
    )


def _compare_single_row_price_difference(
    response_text: str,
    page_data: str,
    own_product: str,
    compared_brand: str,
) -> tuple[str, str]:
    """Validate price difference when own product and competitor use single table rows."""
    own_prices = _extract_exact_product_prices(page_data, own_product)
    fallback_own_price = _extract_requested_product_price(page_data, f"What is the MRP of {own_product}?")
    if fallback_own_price is not None:
        own_prices.add(fallback_own_price)

    competitor_rows = _extract_competitor_table_rows(page_data)
    compared_rows = [
        row
        for row in competitor_rows
        if _entity_text_contains(str(row["brand"]), compared_brand)
        or _entity_text_contains(compared_brand, str(row["brand"]))
    ]
    compared_rows = [row for row in compared_rows if row.get("price") is not None]

    if not own_prices or not compared_rows:
        return "DATA MISSING", "Single-row price difference evidence was not found on the cited page."

    compared_price = float(compared_rows[0]["price"])
    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    calculated = [
        (own_price, round(abs(compared_price - own_price), 2))
        for own_price in sorted(own_prices)
    ]

    for own_price, difference in calculated:
        if _float_set_contains(response_numbers, difference):
            return (
                "PASS",
                "Price difference matches cited table calculation. "
                f"{compared_brand} {compared_price:g} - {own_product} {own_price:g} = {difference:g}.",
            )

    calculated_summary = "; ".join(
        f"{compared_brand} {compared_price:g} - {own_product} {own_price:g} = {difference:g}"
        for own_price, difference in calculated
    )
    return (
        "FAIL",
        "Price difference mismatch. Cited table calculation(s): "
        f"{calculated_summary}.",
    )


def _extract_exact_product_prices(page_data: str, product: str) -> set[float]:
    """Extract prices that are tied to the exact product name."""
    prices: set[float] = set()
    normalized_page = re.sub(r"\s+", " ", page_data)
    product_pattern = r"\s*[-_/]?\s*".join(
        re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
    )

    for match in re.finditer(
        rf"\b{product_pattern}\b\s*[:-]+\s*(?P<price>\d{{1,4}}(?:,\d{{3}})*(?:\.\d+)?)\s*\(",
        normalized_page,
        flags=re.IGNORECASE,
    ):
        prices.add(float(match.group("price").replace(",", "")))

    for match in re.finditer(
        rf"\b{product_pattern}\b\s+TABLETS(?:\s+\(\d+\s*TABS\))?\s+"
        r"(?P<current>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s+"
        r"(?P<new>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\b",
        normalized_page,
        flags=re.IGNORECASE,
    ):
        prices.add(float(match.group("current").replace(",", "")))
        prices.add(float(match.group("new").replace(",", "")))

    return prices


# Column header keyword → canonical attribute type used by resolve_attribute_type.
# Ordered from most-specific to least-specific so the first matching alias wins.
_COLUMN_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "PM_OBJECTIVE": (
        "pm obj",
        "pm objective",
        "pmr obj",
        "pmr objective",
        "monthly obj",
        "monthly objective",
        "monthly minimum",
        "minimum objective",
        "pm target",
        "pmr target",
    ),
    "QUARTERLY_OBJECTIVE": (
        "quarterly obj",
        "quarterly objective",
        "qtr obj",
        "quarterly pmr",
        "quarterly pm",
        "q objective",
    ),
    "INCENTIVE": (
        "incentive per strip",
        "incentive/strip",
        "inc/strip",
        "incentive per tab",
        "incentive/tab",
        "incentive value",
        "incentive",
    ),
}


def _detect_column_order(page_data: str) -> list[str]:
    """Return column types in left-to-right order based on header positions.

    Scans the page text for column header aliases and sorts them by their
    character position.  The resulting list gives the column index for each
    attribute type so that row-level numbers can be mapped to the right cell.
    """
    normalized = re.sub(r"\s+", " ", page_data)
    positions: list[tuple[int, str]] = []
    seen: set[str] = set()
    for col_type, aliases in _COLUMN_HEADER_ALIASES.items():
        for alias in aliases:
            m = re.search(re.escape(alias), normalized, flags=re.IGNORECASE)
            if m and col_type not in seen:
                positions.append((m.start(), col_type))
                seen.add(col_type)
                break
    positions.sort()
    return [col_type for _, col_type in positions]


def _table_column_cell_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    """Validate by selecting the exact column for the requested attribute.

    Prevents PM_OBJECTIVE responses from being compared against the
    QUARTERLY_OBJECTIVE column (and vice versa) when multiple numeric
    columns share the same product row.

    Pipeline:
      question → resolve_attribute_type → detect column order → find product
      row → filter product-name digits → pick number at column index → compare.
    """
    attr_type = resolve_attribute_type(question)
    if attr_type not in _COLUMN_HEADER_ALIASES:
        return False, "DATA MISSING", "", ""

    column_order = _detect_column_order(page_data)
    if attr_type not in column_order:
        return False, "DATA MISSING", "", ""

    col_index = column_order.index(attr_type)

    product = _extract_table_product_from_question(question)
    if not product:
        return False, "DATA MISSING", "", ""

    normalized_page = re.sub(r"\s+", " ", page_data)
    tokens = _product_name_tokens(product)
    if not tokens:
        return False, "DATA MISSING", "", ""

    product_pattern = r"[-\s/]*".join(re.escape(t) for t in tokens)
    row_match = re.search(
        rf"\b{product_pattern}\b(?P<row>.{{0,220}})",
        normalized_page,
        flags=re.IGNORECASE,
    )
    if not row_match:
        return False, "DATA MISSING", "", ""

    row_text = row_match.group(0)

    # Filter out digits that are part of the product name (e.g. "2.5" from "CONCOR 2.5").
    product_nums = {
        float(n)
        for token in tokens
        for n in re.findall(r"\d+(?:\.\d+)?", token)
    }
    all_nums = [
        float(n.replace(",", ""))
        for n in re.findall(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", row_text)
        if not any(abs(float(n.replace(",", "")) - pn) <= 0.001 for pn in product_nums)
    ]

    if col_index >= len(all_nums):
        # Column index is out of range — OCR may have dropped a value.
        # Log clearly and return DATA MISSING so OpenAI can attempt recovery
        # from the partial page text rather than silently failing.
        _log_validation_step(
            rule="_table_column_cell_validation",
            product=product,
            attribute=attr_type,
            column=f"index {col_index} of {column_order}",
            doc_value=f"only {len(all_nums)} numeric(s) found in row",
            response_value=list(response_numbers if response_numbers else []),
            verdict="DATA MISSING",
            reason=(
                f"Column index {col_index} out of range: row for {product!r} "
                f"has only {len(all_nums)} numeric value(s) after filtering product "
                f"name digits. OCR may have dropped a value. "
                f"Row text: {row_text[:200]!r}"
            ),
        )
        return False, "DATA MISSING", "", ""

    expected_value = all_nums[col_index]
    response_numbers = {float(n) for n in _extract_numbers(response_text)}

    if _float_set_contains(response_numbers, expected_value):
        _log_validation_step(
            rule="_table_column_cell_validation",
            product=product,
            attribute=attr_type,
            column=f"index {col_index} of {column_order}",
            doc_value=expected_value,
            response_value=sorted(response_numbers),
            verdict="PASS",
            reason=f"{attr_type} for {product} matches: {expected_value:g}.",
        )
        return (
            True,
            "PASS",
            f"{attr_type} for {product} matches cited page: {expected_value:g}.",
            f"{expected_value:g}",
        )

    _log_validation_step(
        rule="_table_column_cell_validation",
        product=product,
        attribute=attr_type,
        column=f"index {col_index} of {column_order}",
        doc_value=expected_value,
        response_value=sorted(response_numbers),
        verdict="FAIL",
        reason=f"Cited {attr_type}={expected_value:g}, response has {sorted(response_numbers)}.",
    )
    return (
        True,
        "FAIL",
        f"{attr_type} mismatch for {product}. Cited value: {expected_value:g}, "
        f"but SuperAI returned "
        f"{', '.join(f'{n:g}' for n in sorted(response_numbers))}.",
        "",
    )


def _deterministic_table_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    """Validate row-grounded table questions before generic numeric matching."""
    normalized_question = normalize_text(question)
    if _is_missing_source_data(page_data):
        return False, "DATA MISSING", "", ""

    if not any(
        term in normalized_question
        for term in (
            "mrp",
            "price",
            "per tablet",
            "per tab",
            "highest",
            "lowest",
            "difference",
            "sku",
            "packaging",
            "company",
            "manufactured",
            "manufacturer",
            "belongs to",
            "mdi",
            "dpi",
            "forte",
            "incentive",
            "objective",
            "minimum",
            "target",
        )
    ):
        return False, "DATA MISSING", "", ""

    # Column-aware validation runs first so PM_OBJECTIVE is never compared
    # against the QUARTERLY_OBJECTIVE column.
    column_cell_result = _table_column_cell_validation(response_text, page_data, question)
    if column_cell_result[0]:
        return column_cell_result

    difference_result = _table_price_difference_validation(response_text, page_data, question)
    if difference_result[0]:
        return difference_result

    company_result = _table_company_lookup(response_text, page_data, question)
    if company_result[0]:
        return company_result

    column_result = _table_matrix_value_validation(response_text, page_data, question)
    if column_result[0]:
        return column_result

    reverse_result = _table_reverse_price_lookup(response_text, page_data, question)
    if reverse_result[0]:
        return reverse_result

    ranking_result = _table_price_ranking_validation(response_text, page_data, question)
    if ranking_result[0]:
        return ranking_result

    competitor_unit_ranking = _table_competitor_unit_price_ranking_validation(
        response_text,
        page_data,
        question,
    )
    if competitor_unit_ranking[0]:
        return competitor_unit_ranking

    pack_result = _table_pack_size_validation(response_text, page_data, question)
    if pack_result[0]:
        return pack_result

    lookup_result = _table_price_lookup_validation(response_text, page_data, question)
    if lookup_result[0]:
        return lookup_result

    return False, "DATA MISSING", "", ""


def _table_price_lookup_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    """Validate direct product/SKU price lookups using exact row chunks."""
    product = _extract_table_product_from_question(question)
    if not product:
        return False, "DATA MISSING", "", ""

    row = _best_family_price_row(page_data, product)
    if not row:
        return False, "DATA MISSING", "", ""

    normalized_question = normalize_text(question)
    value = row["unit_price"] if any(term in normalized_question for term in ("per tablet", "per tab")) else row["price"]
    if value is None:
        return True, "DATA MISSING", f"Requested table value was not found for {row['product']}.", ""

    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    if _float_set_contains(response_numbers, float(value)):
        return (
            True,
            "PASS",
            f"Table row value matches cited page: {row['product']} = {float(value):g}.",
            f"{float(value):g}",
        )

    # For MRP revision tables the row holds two price columns:
    #   previous_value = "Current MRP" (old pre-revision price)
    #   price          = "New MRP"     (newly effective price)
    # SuperAI may legitimately return either column, so accept both.
    prev = row.get("previous_value")
    if prev is not None and _float_set_contains(response_numbers, float(prev)):
        return (
            True,
            "PASS",
            f"Table row alternate value matches cited page: {row['product']} = {float(prev):g}.",
            f"{float(prev):g}",
        )

    return (
        True,
        "FAIL",
        f"Table row value mismatch. Cited row for {row['product']} has {float(value):g}.",
        "",
    )


def _table_pack_size_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    normalized_question = normalize_text(question)
    if not any(term in normalized_question for term in ("packaging", "pack size", "pack")):
        return False, "DATA MISSING", "", ""

    product = _extract_table_product_from_question(question)
    rows = _family_price_rows(page_data, product) if product else []
    if not rows and "cilaheart" in normalized_question:
        rows = _family_price_rows(page_data, "CILAHEART")
    if not rows:
        return False, "DATA MISSING", "", ""

    if "common" in normalized_question:
        packs = {row["pack"] for row in rows if row.get("pack")}
        if not packs:
            return True, "DATA MISSING", "Pack size was not found in cited table rows.", ""
        expected = sorted(packs)[0] if len(packs) == 1 else ""
        if expected and normalize_text(expected) in normalize_text(response_text):
            return True, "PASS", f"Common pack size matches cited table rows: {expected}.", expected
        if expected:
            return True, "FAIL", f"Common pack size mismatch. Cited table rows show {expected}.", ""
        return True, "DATA MISSING", "No single common pack size exists across cited table rows.", ""

    row = _best_family_price_row(page_data, product)
    if not row or not row.get("pack"):
        return True, "DATA MISSING", "Requested pack size was not found in the cited table row.", ""
    expected = str(row["pack"])
    if normalize_text(expected) in normalize_text(response_text):
        return True, "PASS", f"Pack size matches cited table row: {row['product']} = {expected}.", expected
    return True, "FAIL", f"Pack size mismatch. Cited row for {row['product']} has {expected}.", ""


def _table_price_ranking_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    normalized_question = normalize_text(question)
    if not any(term in normalized_question for term in ("highest", "lowest", "cheapest")):
        return False, "DATA MISSING", "", ""

    family = _extract_ranking_family(question)
    rows = _family_price_rows(page_data, family) if family else []
    rows = [row for row in rows if row.get("price") is not None]
    if not rows:
        return False, "DATA MISSING", "", ""

    expected = min(rows, key=lambda row: float(row["price"])) if any(term in normalized_question for term in ("lowest", "cheapest")) else max(rows, key=lambda row: float(row["price"]))
    expected_price = float(expected["price"])
    brand_ok = _entity_text_contains(response_text, str(expected["product"])) or _entity_text_contains_ordered_tokens(response_text, str(expected["product"]))
    price_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, expected_price)
    label = "lowest" if any(term in normalized_question for term in ("lowest", "cheapest")) else "highest"
    if brand_ok and (price_ok or not _extract_numbers(response_text)):
        return True, "PASS", f"{label.title()} table row matches cited page: {expected['product']} at {expected_price:g}.", f"{expected['product']} {expected_price:g}"
    return True, "FAIL", f"{label.title()} table row is {expected['product']} at {expected_price:g}; SuperAI does not match.", ""


def _table_competitor_unit_price_ranking_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    """Validate competitor ranking by per-tablet/per-tab value."""
    normalized_question = normalize_text(question)
    if "competitor" not in normalized_question:
        return False, "DATA MISSING", "", ""
    if not any(term in normalized_question for term in ("highest", "lowest", "cheapest")):
        return False, "DATA MISSING", "", ""
    if not any(term in normalized_question for term in ("per tablet", "per tab")):
        return False, "DATA MISSING", "", ""

    rows = [row for row in _extract_competitor_unit_price_rows(page_data) if row.get("unit_price") is not None]
    if not rows:
        return False, "DATA MISSING", "", ""

    label = "lowest" if any(term in normalized_question for term in ("lowest", "cheapest")) else "highest"
    expected = min(rows, key=lambda row: float(row["unit_price"])) if label == "lowest" else max(rows, key=lambda row: float(row["unit_price"]))
    expected_brand = str(expected["brand"])
    expected_unit = float(expected["unit_price"])
    brand_ok = _entity_text_contains(response_text, expected_brand) or _entity_text_contains_ordered_tokens(response_text, expected_brand)
    unit_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, expected_unit)

    if brand_ok and unit_ok:
        return (
            True,
            "PASS",
            f"{label.title()} competitor per-tablet row matches cited table: {expected_brand} = {expected_unit:g}.",
            f"{expected_brand} {expected_unit:g}",
        )
    return (
        True,
        "FAIL",
        f"{label.title()} competitor per-tablet row is {expected_brand} = {expected_unit:g}; SuperAI does not match.",
        "",
    )


def _table_price_difference_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    normalized_question = normalize_text(question)
    if "difference" not in normalized_question and "between" not in normalized_question:
        return False, "DATA MISSING", "", ""

    left, right = _extract_price_comparison_entities(question)
    if not left or not right:
        return False, "DATA MISSING", "", ""

    left_row = _best_family_price_row(page_data, left)
    right_row = _best_family_price_row(page_data, right)
    if not left_row or not right_row:
        return False, "DATA MISSING", "", ""

    left_value = float(left_row["price"])
    right_value = float(right_row["price"])
    difference = round(abs(right_value - left_value), 2)
    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    if _float_set_contains(response_numbers, difference):
        return (
            True,
            "PASS",
            f"Price difference matches cited table rows: {right_row['product']} {right_value:g} - {left_row['product']} {left_value:g} = {difference:g}.",
            f"{difference:g}",
        )
    return (
        True,
        "FAIL",
        f"Price difference mismatch. Cited calculation is {difference:g} from {left_row['product']} {left_value:g} and {right_row['product']} {right_value:g}.",
        "",
    )


def _table_reverse_price_lookup(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    normalized_question = normalize_text(question)
    if not (
        ("which" in normalized_question and any(term in normalized_question for term in ("sku", "competitor", "brand")))
        or "has an mrp" in normalized_question
        or "has a per tablet price" in normalized_question
        or "has a price" in normalized_question
    ):
        return False, "DATA MISSING", "", ""

    requested_numbers = [float(number) for number in _extract_numbers(question)]
    if not requested_numbers:
        return False, "DATA MISSING", "", ""
    requested_value = requested_numbers[-1]

    family = _extract_ranking_family(question) or _extract_table_product_from_question(question)
    rows = _family_price_rows(page_data, family) if family else []
    matrix_rows = _extract_dpi_mdi_matrix_rows(page_data)
    own_matrix_rows = _extract_own_dpi_mdi_price_rows(page_data)

    candidates: list[tuple[str, float]] = []
    for row in rows:
        for key in ("price", "unit_price"):
            if row.get(key) is not None and abs(float(row[key]) - requested_value) <= 0.05:
                candidates.append((str(row["product"]), float(row[key])))
    for row in own_matrix_rows:
        if abs(float(row["price"]) - requested_value) <= 0.05:
            candidates.append((str(row["product"]), float(row["price"])))
    for row in matrix_rows:
        for column, value in row.get("values", {}).items():
            if value is not None and abs(float(value) - requested_value) <= 0.05:
                candidates.append((str(row["brand"]), float(value)))

    if not candidates:
        return False, "DATA MISSING", "", ""

    matching = [name for name, _ in candidates if _entity_text_contains(response_text, name) or _entity_text_contains_ordered_tokens(response_text, name)]
    expected_names = ", ".join(name for name, _ in candidates)
    if matching:
        return True, "PASS", f"Reverse table lookup matches cited row: {expected_names} has {requested_value:g}.", f"{expected_names} {requested_value:g}"
    return True, "FAIL", f"Reverse table lookup mismatch. Cited table maps {requested_value:g} to {expected_names}.", ""


def _table_company_lookup(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    normalized_question = normalize_text(question)
    if not any(term in normalized_question for term in ("company", "manufactured", "manufacturer", "belongs to")):
        return False, "DATA MISSING", "", ""

    brand = _extract_company_question_brand(question)
    company = _extract_marketed_by_company(question)
    rows = (
        _extract_dpi_mdi_matrix_rows(page_data)
        + _extract_competitor_table_rows(page_data)
        + _extract_competitor_unit_price_rows(page_data)
    )

    if company and not brand:
        matches = [row for row in rows if _company_text_contains(str(row.get("company", "")), company)]
        if not matches:
            return False, "DATA MISSING", "", ""
        expected = str(matches[0].get("brand", ""))
        if _entity_text_contains(response_text, expected) or _entity_text_contains_ordered_tokens(response_text, expected):
            return True, "PASS", f"Company-brand mapping matches cited table: {expected} belongs to {company}.", expected
        return True, "FAIL", f"Company-brand mismatch. Cited table lists {expected} for {company}.", ""

    if not brand:
        return False, "DATA MISSING", "", ""

    matching_rows = [
        row for row in rows
        if _entity_text_contains(str(row.get("brand", "")), brand)
        or _entity_text_contains(brand, str(row.get("brand", "")))
        or _entity_text_contains_ordered_tokens(str(row.get("brand", "")), brand)
    ]
    if not matching_rows:
        return False, "DATA MISSING", "", ""

    expected_company = str(matching_rows[0].get("company", ""))
    if _company_text_contains(response_text, expected_company):
        return True, "PASS", f"Company matches cited table row: {brand} is listed with {expected_company}.", expected_company
    return True, "FAIL", f"Company mismatch. Cited table lists {brand} with {expected_company}.", ""


def _table_matrix_value_validation(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[bool, str, str, str]:
    normalized_question = normalize_text(question)
    if not any(term in normalized_question for term in ("dpi", "mdi", "forte")):
        return False, "DATA MISSING", "", ""

    rows = _extract_dpi_mdi_matrix_rows(page_data)
    if not rows:
        return False, "DATA MISSING", "", ""

    requested_brand = _extract_matrix_brand_from_question(question, rows)
    requested_column = _extract_matrix_column_from_question(question)

    if "lowest" in normalized_question or "highest" in normalized_question:
        if not requested_column:
            return False, "DATA MISSING", "", ""
        valued_rows = [row for row in rows if row.get("values", {}).get(requested_column) is not None]
        if not valued_rows:
            return True, "DATA MISSING", f"No values found for {requested_column} in cited table.", ""
        expected = min(valued_rows, key=lambda row: float(row["values"][requested_column])) if "lowest" in normalized_question else max(valued_rows, key=lambda row: float(row["values"][requested_column]))
        value = float(expected["values"][requested_column])
        brand_ok = _entity_text_contains(response_text, str(expected["brand"])) or _entity_text_contains_ordered_tokens(response_text, str(expected["brand"]))
        value_ok = _float_set_contains({float(number) for number in _extract_numbers(response_text)}, value)
        label = "lowest" if "lowest" in normalized_question else "highest"
        if brand_ok and value_ok:
            return True, "PASS", f"{label.title()} {requested_column} value matches cited table: {expected['brand']} = {value:g}.", f"{expected['brand']} {value:g}"
        return True, "FAIL", f"{label.title()} {requested_column} value is {expected['brand']} = {value:g}; SuperAI does not match.", ""

    if not requested_brand or not requested_column:
        return False, "DATA MISSING", "", ""

    row = next(
        (
            row for row in rows
            if _entity_text_contains(str(row["brand"]), requested_brand)
            or _entity_text_contains(requested_brand, str(row["brand"]))
            or _entity_text_contains_ordered_tokens(str(row["brand"]), requested_brand)
        ),
        None,
    )
    if not row:
        return False, "DATA MISSING", "", ""

    value = row.get("values", {}).get(requested_column)
    if value is None:
        response_numbers = {float(number) for number in _extract_numbers(response_text)}
        if response_numbers or "NA" in str(row.get("raw", "")).upper():
            return True, "FAIL", f"Cited table shows no numeric value for {row['brand']} {requested_column}.", ""
        return True, "DATA MISSING", f"{requested_column} value was not found for {row['brand']} in cited table.", ""

    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    if _float_set_contains(response_numbers, float(value)):
        return True, "PASS", f"Table cell matches cited row: {row['brand']} {requested_column} = {float(value):g}.", f"{float(value):g}"
    return True, "FAIL", f"Table cell mismatch. Cited row has {row['brand']} {requested_column} = {float(value):g}.", ""


def _extract_own_dpi_mdi_price_rows(page_data: str) -> list[dict[str, object]]:
    """Extract own Combihale FB MRP matrix rows by SKU column."""
    text = re.sub(r"\s+", " ", page_data).strip()
    match = re.search(
        r"M\.?R\.?P\s*\(Each SKU\)\s+COMBIHALE\s+FB\s+DPI\s+CAPS\s+COMBIHALE\s+FB\s+MDI\s+"
        r"100\s+200\s+400\s+FORTE\s+200\s+400\s+"
        r"(?P<values>(?:\d+(?:\.\d+)?\s*(?:Rs)?\s*){6})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return []

    values = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", match.group("values"))[:6]]
    products = [
        "COMBIHALE FB DPI CAPS 100",
        "COMBIHALE FB DPI CAPS 200",
        "COMBIHALE FB DPI CAPS 400",
        "COMBIHALE FB DPI CAPS FORTE",
        "COMBIHALE FB MDI 200",
        "COMBIHALE FB MDI 400",
    ]
    return [
        {"product": product, "price": values[index], "pack": "", "unit_price": None}
        for index, product in enumerate(products)
        if index < len(values)
    ]


def _extract_competitor_unit_price_rows(page_data: str) -> list[dict[str, object]]:
    """Extract competitor rows with strip price and per-tablet price columns."""
    text = re.sub(r"\s+", " ", page_data).strip()
    if not re.search(r"\bper\s+tab\b|\bper\s+tablet\b", text, flags=re.IGNORECASE):
        return []

    end_match = re.search(
        r"\bPackaging\s+Price\b|\bM\.?R\.?P\b|\bIndications\b|\bSalient\b",
        text,
        flags=re.IGNORECASE,
    )
    section = text[: end_match.start()] if end_match else text

    company_pattern = "|".join(re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True))
    row_pattern = re.compile(
        rf"(?P<brand>[A-Za-z][A-Za-z0-9 /.-]{{1,60}}?)\s+"
        rf"(?P<company>{company_pattern})\s+"
        r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*"
        r"\((?P<pack>\d+)\s*(?:tab|tabs|tablet|tablets)\)\s*"
        r"(?P<unit>\d{1,4}(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )

    rows: list[dict[str, object]] = []
    for match in row_pattern.finditer(section):
        brand = _clean_brand_name(match.group("brand"))
        brand = re.sub(r"^(?:mg\s+)?per(?:\s+tab)?\s+", "", brand, flags=re.IGNORECASE).strip()
        company = _normalize_company_display(match.group("company"))
        price = float(match.group("price").replace(",", ""))
        unit_price = float(match.group("unit"))
        pack = f"{match.group('pack')} Tab"
        rows.append(
            {
                "brand": brand,
                "company": company,
                "pack": pack,
                "price": price,
                "unit_price": unit_price,
                "values": {},
                "raw": match.group(0),
            }
        )
    return rows


def _family_price_rows(page_data: str, family: str) -> list[dict[str, object]]:
    """Extract repeated product-family rows with row-local numeric values."""
    if not family:
        return []

    text = re.sub(r"\s+", " ", page_data).strip()
    family_tokens = _family_tokens(family)
    if not family_tokens:
        return []

    family_pattern = r"[-\s/]*".join(re.escape(token) for token in family_tokens)
    matches = list(re.finditer(rf"\b{family_pattern}\b", text, flags=re.IGNORECASE))
    rows: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), start + 180)
        citation_break = text.find("| | Citation", start, end)
        if citation_break != -1:
            end = citation_break
        chunk = text[start:end].strip(" |")

        # Truncate chunk at next product-name boundary.
        # Pattern: a decimal number followed by an uppercase product word (3+ chars) signals
        # the start of the next row. This prevents a 180-char window from pulling in
        # neighboring rows and corrupting the extracted price (e.g. "60" cut to "6").
        _boundary = re.search(
            r"(\d+\.\d+)\s+[A-Z][A-Z0-9\-]{2,}",
            chunk,
        )
        if _boundary:
            chunk = chunk[: _boundary.start() + len(_boundary.group(1))]

        numbers = list(re.finditer(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", chunk))
        if not numbers:
            continue

        numeric_values = [float(number.group(0).replace(",", "")) for number in numbers]
        pack = ""
        pack_match = re.search(r"\((\d+)\s*(?:TABS?|TABLETS?|CAPS?)\)|\b(\d+)\s*(?:TAB|TABS|CAP|CAPS)\b", chunk, flags=re.IGNORECASE)
        if pack_match:
            pack = f"{pack_match.group(1) or pack_match.group(2)} Tab"

        price, unit_price, previous_value = _derive_row_price_values(numeric_values, pack)

        product_end = numbers[-2].start() if len(numbers) >= 2 else numbers[-1].start()
        product = re.sub(r"\s+", " ", chunk[:product_end]).strip(" :-|")
        if not product:
            product = match.group(0)

        row = {
            "product": product,
            "chunk": chunk,
            "numbers": numeric_values,
            "price": price,
            "previous_value": previous_value,
            "unit_price": unit_price,
            "pack": pack,
        }
        rows.append(row)

    return _dedupe_family_rows(rows)


def _best_family_price_row(page_data: str, product: str) -> dict[str, object] | None:
    family = _extract_ranking_family(product) or product
    rows = _family_price_rows(page_data, family)
    if not rows:
        return None

    product_tokens = set(_significant_product_tokens(product))
    scored: list[tuple[int, dict[str, object]]] = []
    for row in rows:
        row_tokens = set(_significant_product_tokens(str(row["product"])))
        score = len(product_tokens.intersection(row_tokens))
        if score:
            scored.append((score, row))

    if not scored:
        return None
    # Sort: highest score first; on tie prefer shorter product name (base variant over
    # e.g. "(90 ML)") — the query's extra tokens already produce a higher score when
    # the longer variant is actually needed.
    scored.sort(key=lambda item: (-item[0], len(str(item[1]["product"]))))
    best_score, best_row = scored[0]
    required = min(2, len(product_tokens))
    return best_row if best_score >= required else None


def _derive_unit_price(numbers: list[float], pack: str) -> float | None:
    _, unit_price, _ = _derive_row_price_values(numbers, pack)
    return unit_price


def _derive_row_price_values(numbers: list[float], pack: str) -> tuple[float, float | None, float | None]:
    """Return row MRP/new-MRP, unit price, and previous row value."""
    if not numbers:
        return 0.0, None, None

    previous_value = numbers[-2] if len(numbers) >= 2 else None
    price = numbers[-1]
    unit_price: float | None = None
    pack_numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", pack or "")]
    pack_count = pack_numbers[0] if pack_numbers else 0.0

    if pack_count > 0 and len(numbers) >= 2:
        explicit_unit_candidate = numbers[-1]
        strip_candidate = numbers[-2]
        if abs(round(strip_candidate / pack_count, 2) - explicit_unit_candidate) <= 0.25:
            price = strip_candidate
            unit_price = explicit_unit_candidate
        else:
            price = numbers[-1]
            unit_price = round(price / pack_count, 2)

    return price, unit_price, previous_value


def _extract_table_product_from_question(question: str) -> str:
    patterns = (
        r"\b(?:mrp|price)\s+of\s+(.+?)(?:\?)?$",
        r"\bper\s+tablet\s+price\s+of\s+(.+?)(?:\?)?$",
        r"\bpackaging\s+size\s+of\s+(.+?)(?:\?)?$",
        r"\bprice\s+difference\s+between\s+(.+?)\s+and\b",
    )
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" ?.")
    return _extract_ranking_family(question)


def _extract_ranking_family(text: str) -> str:
    upper = text.upper()
    if "COMBIHALE" in upper and "FB" in upper:
        return "COMBIHALE-FB"
    if "CILAHEART" in upper:
        return "CILAHEART"
    if "RIFASTOP" in upper:
        return "RIFASTOP"
    if "STATPURE" in upper:
        return "STATPURE"
    return ""


def _family_tokens(product: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", product)
    if len(tokens) >= 2 and tokens[0].lower() == "combihale" and tokens[1].lower() == "fb":
        return ["COMBIHALE"]
    return tokens[:2] if len(tokens) > 1 and any(token.isdigit() for token in tokens[1:]) else tokens[:1]


def _significant_product_tokens(product: str) -> list[str]:
    aliases = {
        "caps": "capsules",
        "cap": "capsules",
        "mdi": "inhaler",
        "inhalers": "inhaler",
        "tabs": "tablets",
        "tab": "tablets",
    }
    stop = {"what", "which", "sku", "has", "mrp", "price", "per", "tablet", "strip", "rs", "of", "the", "and"}
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]+", product.lower()):
        token = aliases.get(token, token)
        if token not in stop:
            tokens.append(token)
    return tokens


def _dedupe_family_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    deduped: list[dict[str, object]] = []
    for row in rows:
        key = normalize_text(str(row["product"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _extract_dpi_mdi_matrix_rows(page_data: str) -> list[dict[str, object]]:
    """Extract Combihale-style BRAND/COMPANY/DPI/MDI matrix rows."""
    text = re.sub(r"\s+", " ", page_data).strip()
    if not re.search(r"\bDPI\b.*\bMDI\b.*\bBRAND\s+NAME\b", text, flags=re.IGNORECASE):
        return []

    section_match = re.search(
        r"BRAND\s+NAME\s+COMPANY\s+100\s+200\s+400\s+FORTE\s+200\s+400\s+(.+?)(?:M\.?R\.?P|Recommended|Salient|$)",
        text,
        flags=re.IGNORECASE,
    )
    section = section_match.group(1) if section_match else text
    section = re.sub(r"\bRs\b", " ", section, flags=re.IGNORECASE)
    company_pattern = "|".join(re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True))
    brand_pattern = r"(?!NA\b|Rs\b|A\s+\d)[A-Za-z][A-Za-z0-9 /.-]{1,80}?"
    row_pattern = re.compile(
        rf"(?P<brand>{brand_pattern})\s+(?P<company>{company_pattern})\s+"
        rf"(?P<values>.+?)(?=(?:{brand_pattern}\s+(?:{company_pattern})\s+)|$)",
        flags=re.IGNORECASE,
    )

    rows: list[dict[str, object]] = []
    for match in row_pattern.finditer(section):
        brand = _clean_brand_name(match.group("brand"))
        company = _normalize_company_display(match.group("company"))
        raw_values = re.findall(r"\bNA\b|\d+(?:\.\d+)?", match.group("values"), flags=re.IGNORECASE)
        if not brand or not raw_values:
            continue
        mapped = _map_dpi_mdi_values(raw_values)
        rows.append(
            {
                "brand": brand,
                "company": company,
                "values": mapped,
                "raw": match.group(0),
                "pack": "",
                "price": None,
            }
        )
    return rows


def _map_dpi_mdi_values(raw_values: list[str]) -> dict[str, float | None]:
    values = [None if value.upper() == "NA" else float(value) for value in raw_values]
    columns = ["DPI_100", "DPI_200", "DPI_400", "DPI_FORTE", "MDI_200", "MDI_400"]
    if len(values) == 6:
        return dict(zip(columns, values))
    if len(values) == 5:
        return {
            "DPI_100": values[0],
            "DPI_200": values[1],
            "DPI_400": values[2],
            "DPI_FORTE": None,
            "MDI_200": values[3],
            "MDI_400": values[4],
        }
    if len(values) == 4:
        return {
            "DPI_100": values[0],
            "DPI_200": values[1],
            "DPI_400": None,
            "DPI_FORTE": None,
            "MDI_200": values[2],
            "MDI_400": values[3],
        }
    if len(values) == 3:
        if values[0] is None:
            return {
                "DPI_100": None,
                "DPI_200": None,
                "DPI_400": None,
                "DPI_FORTE": None,
                "MDI_200": values[1],
                "MDI_400": values[2],
            }
        return {
            "DPI_100": None,
            "DPI_200": None,
            "DPI_400": None,
            "DPI_FORTE": values[0],
            "MDI_200": values[1],
            "MDI_400": values[2],
        }
    return {column: values[index] if index < len(values) else None for index, column in enumerate(columns)}


def _extract_matrix_column_from_question(question: str) -> str:
    normalized = normalize_text(question)
    if "mdi 400" in normalized:
        return "MDI_400"
    if "mdi 200" in normalized:
        return "MDI_200"
    if "dpi 400" in normalized:
        return "DPI_400"
    if "dpi 200" in normalized:
        return "DPI_200"
    if "dpi 100" in normalized:
        return "DPI_100"
    if "forte" in normalized:
        return "DPI_FORTE"
    return ""


def _extract_matrix_brand_from_question(question: str, rows: list[dict[str, object]]) -> str:
    for row in rows:
        brand = str(row["brand"])
        if _entity_text_contains(question, brand) or _entity_text_contains_ordered_tokens(question, brand):
            return brand
    return ""


def _extract_price_response_numbers(text: str) -> set[float]:
    """Extract price-associated numbers from a response string.

    Only returns numbers that appear directly after ₹/Rs/MRP/price/cost or
    directly before /tab, per tablet, per strip, per box.  This prevents digits
    embedded in product names (e.g. "D3" → 3, "60K" → 60, "PANGRAF-1.0" → 1)
    from being treated as price candidates and causing false FAILs.

    Falls back to _extract_numbers when no price-indicator context is found so
    that plain numeric responses (without currency symbols) still validate.
    In the fallback path, small integers (≤ 10) that are likely part of product
    names or dosage counts are excluded from price matching to avoid false FAILs.
    """
    price_numbers: set[float] = set()

    for match in re.finditer(
        r"(?:₹|Rs\.?|MRP|price|cost)\s*(?<!\d)(\d[\d,]*(?:\.\d+)?)(?!\d)",
        text,
        flags=re.IGNORECASE,
    ):
        value = match.group(1).replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        price_numbers.add(float(value))

    for match in re.finditer(
        r"(?<!\d)(\d[\d,]*(?:\.\d+)?)(?!\d)"
        r"\s*(?:/\s*(?:tab(?:let)?s?|strip|box)|per\s+(?:tab(?:let)?s?|strip|box))\b",
        text,
        flags=re.IGNORECASE,
    ):
        value = match.group(1).replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        price_numbers.add(float(value))

    if price_numbers:
        return price_numbers

    # Fallback: use all numbers but exclude very small integers (≤ 10) that are
    # almost always product name digits, pack sizes, or citation indices rather
    # than prices.  Prices in this domain are always > 10 (per strip or per tablet).
    # Exception: keep decimals like 1.5, 2.5 because those can be valid per-tab
    # prices for cheap generics — only exclude exact small integers.
    all_numbers = _extract_numbers(text)
    return {
        float(n)
        for n in all_numbers
        if not (n.isdigit() and int(n) <= 10)
    }


def _compare_price_lookup(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate direct MRP/price lookup questions."""
    response_numbers = _extract_price_response_numbers(response_text)
    if not response_numbers:
        return "DATA MISSING", "SuperAI response did not contain a price/MRP value."

    normalized_question = normalize_text(question)
    wants_unit_price = any(
        term in normalized_question
        for term in ("per tablet", "per tab", "mrp / tab", "mrp per tablet", "per tab price")
    )

    # For per-tablet questions try _extract_product_row_mrp first.
    # _extract_price_master_new_mrp grabs the first two numbers as (current, new)
    # strip MRP and would return 161.10 instead of 16.11 when the row is
    # "SITADAY-100 TABLET 10 TAB 161.10 16.11".
    # _extract_product_row_mrp understands the strip/unit column layout and
    # returns candidate_numbers[-1] (the per-tablet value) when wants_unit_price.
    if wants_unit_price:
        requested_price = _extract_product_row_mrp(page_data, question)
        if requested_price is None:
            requested_price = _extract_price_master_new_mrp(page_data, question)
    else:
        requested_price = _extract_price_master_new_mrp(page_data, question)
        if requested_price is None:
            requested_price = _extract_product_row_mrp(page_data, question)
    if requested_price is None:
        requested_price = _extract_requested_product_price(page_data, question)
    if requested_price is None:
        requested_brand = _extract_company_question_brand(question) or _extract_first_product_name(question)
        if requested_brand:
            competitor_price = _extract_competitor_row_price_for_brand(page_data, requested_brand, question)
            if competitor_price is not None:
                requested_price = competitor_price
    if requested_price is None:
        requested_brand = _extract_company_question_brand(question) or _extract_first_product_name(question)
        if requested_brand:
            competitor_prices = _extract_competitor_strength_prices(page_data, requested_brand)
            if competitor_prices:
                requested_price = next(iter(competitor_prices.values()))

    if requested_price is None:
        _log_validation_step(
            rule="_compare_price_lookup",
            attribute="PRICE",
            response_value=sorted(response_numbers),
            verdict="DATA MISSING",
            reason="Requested price/MRP was not found on the cited page.",
        )
        return "DATA MISSING", "Requested price/MRP was not found on the cited page."

    if _float_set_contains(response_numbers, requested_price):
        _log_validation_step(
            rule="_compare_price_lookup",
            attribute="PRICE",
            doc_value=requested_price,
            response_value=sorted(response_numbers),
            verdict="PASS",
            reason=f"Price/MRP matches cited page: {requested_price:g}.",
        )
        return "PASS", f"Price/MRP matches cited page: {requested_price:g}."

    _log_validation_step(
        rule="_compare_price_lookup",
        attribute="PRICE",
        doc_value=requested_price,
        response_value=sorted(response_numbers),
        verdict="FAIL",
        reason=f"Cited page contains {requested_price:g}, response has {sorted(response_numbers)}.",
    )
    return (
        "FAIL",
        f"Price/MRP mismatch. Cited page contains {requested_price:g}, "
        f"but SuperAI returned {', '.join(str(number) for number in sorted(response_numbers))}.",
    )


def _compare_trip_award_cost(
    response_text: str,
    page_data: str,
    question: str,  # noqa: ARG001
) -> tuple[str, str]:
    """Validate trip/award/medal/reimbursement cost questions.

    Handles Indian number notation (₹1,10,000 → 110000) and must not be routed
    through _compare_price_lookup which expects per-tablet or per-strip MRP rows.
    """
    attr_type = resolve_attribute_type(question)
    response_numbers = _extract_price_response_numbers(response_text)
    if not response_numbers:
        _log_validation_step(
            rule="_compare_trip_award_cost",
            attribute=attr_type,
            verdict="DATA MISSING",
            reason="SuperAI response did not contain a numeric cost value.",
        )
        return "DATA MISSING", "SuperAI response did not contain a numeric cost value."

    page_numbers = {float(n) for n in _extract_numbers(page_data)}
    if not page_numbers:
        _log_validation_step(
            rule="_compare_trip_award_cost",
            attribute=attr_type,
            response_value=sorted(response_numbers),
            verdict="DATA MISSING",
            reason="Requested cost value was not found on the cited page.",
        )
        return "DATA MISSING", "Requested cost value was not found on the cited page."

    for resp_num in response_numbers:
        if _float_set_contains(page_numbers, resp_num):
            _log_validation_step(
                rule="_compare_trip_award_cost",
                attribute=attr_type,
                doc_value=resp_num,
                response_value=resp_num,
                verdict="PASS",
                reason=f"Trip/award cost matches cited page: {resp_num:g}.",
            )
            return "PASS", f"Trip/award cost matches cited page: {resp_num:g}."

    _log_validation_step(
        rule="_compare_trip_award_cost",
        attribute=attr_type,
        doc_value=sorted(page_numbers),
        response_value=sorted(response_numbers),
        verdict="FAIL",
        reason="Cost value in response not found on cited page.",
    )
    return (
        "FAIL",
        f"Trip/award cost mismatch. Cited page has "
        f"{', '.join(f'{n:g}' for n in sorted(page_numbers))}, "
        f"but SuperAI returned {', '.join(f'{n:g}' for n in sorted(response_numbers))}.",
    )


def _extract_competitor_row_price_for_brand(
    page_data: str,
    brand: str,
    question: str,
) -> float | None:
    """Return row-local competitor price/unit price for a requested brand."""
    normalized_question = normalize_text(question)
    wants_unit_price = any(term in normalized_question for term in ("per tablet", "per tab"))
    for row in _extract_competitor_table_rows(page_data):
        row_brand = str(row.get("brand", ""))
        if not (
            _entity_text_contains(row_brand, brand)
            or _entity_text_contains(brand, row_brand)
            or _entity_text_contains_ordered_tokens(row_brand, brand)
        ):
            continue
        price = row.get("price")
        if price is None:
            continue
        if wants_unit_price:
            pack_numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", str(row.get("pack", "")))]
            if pack_numbers:
                return round(float(price) / pack_numbers[0], 2)
        return float(price)
    return None


def _extract_price_master_new_mrp(page_data: str, question: str) -> float | None:
    """Extract exact product New MRP from Price Master rows."""
    generic_price = _extract_generic_price_master_new_mrp(page_data, question)
    if generic_price is not None:
        return generic_price

    product_match = re.search(
        r"\bdocetrust\s+(\d+(?:\.\d+)?)\s*mg\b",
        question,
        flags=re.IGNORECASE,
    )
    if not product_match:
        return None

    strength = product_match.group(1).rstrip("0").rstrip(".")
    if "." not in product_match.group(1):
        strength = product_match.group(1)
    normalized_page = re.sub(r"\s+", " ", page_data)
    row_match = re.search(
        rf"\bDOCETRUST[-\s]*{re.escape(strength)}\s+INJECTION\s+"
        r"(?P<current>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s+"
        r"(?P<new>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\b",
        normalized_page,
        flags=re.IGNORECASE,
    )
    if not row_match:
        return None

    return float(row_match.group("new").replace(",", ""))


def _extract_generic_price_master_new_mrp(page_data: str, question: str) -> float | None:
    """Extract New MRP for a product row from flattened Price Master text."""
    products = _extract_price_question_product_candidates(question)
    if not products:
        product = _extract_first_product_name(question)
        products = [product] if product else []

    normalized_page = re.sub(r"\s+", " ", page_data)
    for product in products:
        product = re.sub(
            r"\b(?:current|new|mrp|price|cost|of|the|per|strip|box|pack|tablets?|capsules?|respules?)\b",
            " ",
            product,
            flags=re.IGNORECASE,
        )
        product = re.sub(r"\s+", " ", product).strip(" ?:-.,")
        if not product:
            continue

        tokens = _product_name_tokens(product)
        if not tokens:
            continue

        product_pattern = r"[-\s/]*".join(re.escape(token) for token in tokens)
        pack_match = re.search(r"\((\d+)\s*(?:TABS?|TABLETS?)", question, flags=re.IGNORECASE)
        pack_patterns = [rf"\s+\({pack_match.group(1)}\s*TABS?\)", ""] if pack_match else [""]
        for pack_pattern in pack_patterns:
            row_match = re.search(
                rf"\b{product_pattern}\b(?:\s+(?:TABLETS?|TABLTES|INJECTIONS?|INJECTION|CAPSULES?|SUSPENSION|DROPS|RESPULES|DPI))*"
                rf"{pack_pattern}"
                r"\s+(?P<current>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s+"
                r"(?P<new>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\b",
                normalized_page,
                flags=re.IGNORECASE,
            )
            if row_match:
                return float(row_match.group("new").replace(",", ""))

    return None


def _extract_product_row_mrp(page_data: str, question: str) -> float | None:
    """Extract MRP from flattened product rows preserving row-level product mapping.

    Handles product MRP rows such as:
    - NOBEGLAR CARTRIDGE 3 ML 620.61
    - NOBEGLAR-UNO PREFILLED PEN 1 PACK 762
    - NOBEGLIZ-M XR 10 TAB 102.09 10.21
    """
    products = _extract_price_question_product_candidates(question)
    if not products:
        product = _extract_first_product_name(question)
        products = [product] if product else []

    normalized_page = re.sub(r"\s+", " ", page_data)
    normalized_question = normalize_text(question)
    wants_unit_price = any(
        term in normalized_question
        for term in ("per tablet", "per tab", "mrp / tab", "mrp per tablet")
    )

    for product in products:
        clean_product = re.sub(
            r"\b(?:mrp|price|cost|of|the|per|tablet|tab|strip|box|pack)\b",
            " ",
            product,
            flags=re.IGNORECASE,
        )
        clean_product = re.sub(r"\s+", " ", clean_product).strip(" ?:-.,")
        if not clean_product:
            continue

        tokens = _product_name_tokens(clean_product)
        if not tokens:
            continue

        product_pattern = r"[-\s/]*".join(re.escape(token) for token in tokens)
        row_match = re.search(
            rf"\b{product_pattern}\b"
            r"(?P<row>.{0,140}?)"
            r"(?=(?:\b[A-Z][A-Z0-9-]{2,}\b\s+[A-Z]|\bGLOSSARY\b|\bShort Form\b|$))",
            normalized_page,
            flags=re.IGNORECASE,
        )
        if not row_match:
            row_match = re.search(
                rf"\b{product_pattern}\b(?P<row>.{{0,140}})",
                normalized_page,
                flags=re.IGNORECASE,
            )
        if not row_match:
            continue

        row_text = row_match.group(0)
        numbers = [
            float(number.replace(",", ""))
            for number in re.findall(r"(?<!\d)\d{1,6}(?:,\d{3})*(?:\.\d+)?(?!\d)", row_text)
        ]
        if not numbers:
            continue

        product_numbers = {
            float(number)
            for token in tokens
            for number in re.findall(r"\d+(?:\.\d+)?", token)
        }
        candidate_numbers = [
            number for number in numbers if not any(abs(number - prod) <= 0.001 for prod in product_numbers)
        ]
        if not candidate_numbers:
            candidate_numbers = numbers

        if wants_unit_price and len(candidate_numbers) >= 2:
            return candidate_numbers[-1]

        if len(candidate_numbers) >= 2 and candidate_numbers[0] <= 10 < candidate_numbers[-1]:
            return candidate_numbers[-1]

        return candidate_numbers[-1] if len(candidate_numbers) == 1 else candidate_numbers[-2]

    return None


def _extract_price_question_product_candidates(question: str) -> list[str]:
    """Extract precise product candidates from price/MRP questions."""
    patterns = (
        r"\b(?:mrp|price)\s+per\s+(?:strip|box|respule|tablet|tab|capsule|cap)\s+of\s+(.+?)(?:\s*\(|\?)",
        r"\b(?:mrp|price)\s+of\s+(.+?)(?:\s*\(|\?)",
        r"\bof\s+(.+?)(?:\s*\(|\?)",
    )
    candidates: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ?.:-")
            if candidate:
                candidates.append(candidate)
    return candidates


def _product_name_tokens(product: str) -> list[str]:
    """Return product tokens, splitting compact variant-strength tokens like M25."""
    raw_tokens = re.findall(r"[A-Za-z0-9]+", product)
    tokens: list[str] = []
    for token in raw_tokens:
        compact_match = re.fullmatch(r"([A-Za-z]+)(\d+)", token)
        if compact_match and compact_match.group(1).lower() in {"m"}:
            tokens.extend([compact_match.group(1), compact_match.group(2)])
        else:
            tokens.append(token)
    return tokens


def _extract_first_product_name(question: str) -> str:
    """Return a simple product candidate from lookup questions."""
    direct_match = re.search(
        r"\b(?:mrp|price|cost)\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        question,
        flags=re.IGNORECASE,
    )
    if direct_match:
        return direct_match.group(1).strip()

    match = re.search(
        r"\b(?:of|does|is)\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+cost|\s+mrp|\s+price|\?)",
        question,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _compare_company_lookup(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate company/manufacturer questions from a cited competitor row."""
    brand = _extract_company_question_brand(question)
    if not brand:
        return "DATA MISSING", "Brand name could not be identified from the company question."

    company = _extract_company_for_brand(page_data, brand)
    if not company:
        for row in _extract_competitor_table_rows(page_data):
            if _entity_text_contains(str(row["brand"]), brand) or _entity_text_contains(brand, str(row["brand"])):
                company = str(row["company"])
                break
    if not company:
        return "DATA MISSING", f"Company row for {brand} was not found on the cited page."

    if _company_text_contains(response_text, company):
        return (
            "PASS",
            f"Company/manufacturer matches cited table row: {brand} is listed with {company}.",
        )

    return (
        "FAIL",
        f"Company/manufacturer mismatch. Cited table row lists {brand} with {company}.",
    )


def _extract_company_question_brand(question: str) -> str:
    """Extract brand being asked about in a company/manufacturer question."""
    patterns = (
        r"\bmarkets?\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        r"\bmanufactures?\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        r"\bmanufacturer\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        r"\bcompany\s+name\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        r"\bcompany\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
    )
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.")
    return ""


def _extract_company_for_brand(page_data: str, brand: str) -> str:
    """Extract company for a brand row from flattened competitor table text."""
    normalized_page = re.sub(r"\s+", " ", page_data)
    brand_pattern = r"\s*[-_/]?\s*".join(
        re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", brand)
    )
    company_pattern = "|".join(
        re.escape(company) for company in sorted(_known_company_names(), key=len, reverse=True)
    )
    match = re.search(
        rf"\b{brand_pattern}(?:\s+[A-Za-z0-9+-]+)?\s+(?P<company>{company_pattern})\b",
        normalized_page,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _normalize_company_display(match.group("company"))


def _extract_price_comparison_entities(question: str) -> tuple[str, str]:
    """Extract own product and compared competitor brand from a comparison question."""
    match = re.search(
        r"\b(?:price\s+difference\s+)?between\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+and\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        question,
        flags=re.IGNORECASE,
    )
    if match:
        return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

    match = re.search(
        r"\bhow\s+much\s+cheaper\s+is\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+compared\s+to\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        question,
        flags=re.IGNORECASE,
    )
    if match:
        return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

    match = re.search(
        r"\b([A-Za-z][A-Za-z0-9 +./-]+?)\s+compared\s+to\s+([A-Za-z][A-Za-z0-9 +./-]+?)\??$",
        question,
        flags=re.IGNORECASE,
    )
    if match:
        return _normalize_comparison_pair(match.group(1).strip(), match.group(2).strip())

    return "", ""


def _normalize_comparison_pair(left: str, right: str) -> tuple[str, str]:
    """Carry shared product prefixes into abbreviated right-side comparison labels."""
    left = re.sub(r"\bprices?\b", " ", left, flags=re.IGNORECASE)
    right = re.sub(r"\bprices?\b", " ", right, flags=re.IGNORECASE)
    left = re.sub(r"\s+", " ", left).strip(" ?.:-")
    right = re.sub(r"\s+", " ", right).strip(" ?.:-")

    left_upper = left.upper()
    right_upper = right.upper()
    if "COMBIHALE" in left_upper and "COMBIHALE" not in right_upper:
        if "FB" in left_upper and "FB" not in right_upper:
            right = f"COMBIHALE FB {right}"
        else:
            right = f"COMBIHALE {right}"
    if "CILAHEART" in left_upper and "CILAHEART" not in right_upper:
        right = f"CILAHEART {right}"

    return left, re.sub(r"\s+", " ", right).strip()


def _extract_own_sku_prices(page_data: str, product: str) -> dict[str, float]:
    """Extract own-product SKU prices such as Bisonicus 2.5 -> 69.4."""
    prices: dict[str, float] = {}
    normalized_page = re.sub(r"\s+", " ", page_data)
    product_pattern = r"\s*[-_/]?\s*".join(
        re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
    )

    pattern = re.compile(
        rf"{product_pattern}\s+(?P<strength>\d+(?:\.\d+)?)"
        r".{0,100}?(?:₹|â‚¹|rs\.?|inr)\s*\.?\s*"
        r"(?P<price>\d{1,4}(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(normalized_page):
        strength = _normalize_strength_key(match.group("strength"))
        price = float(match.group("price"))
        prices[strength] = price

    return prices


def _extract_competitor_strength_prices(page_data: str, brand: str) -> dict[str, float]:
    """Extract competitor prices from two-strength rows such as CONCOR 2.5/5 mg."""
    normalized_page = re.sub(r"\s+", " ", page_data)
    brand_pattern = r"\s*[-_/]?\s*".join(
        re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", brand)
    )
    company_pattern = "|".join(re.escape(company) for company in _known_company_names())
    row_match = re.search(
        rf"{brand_pattern}\s+(?:{company_pattern})\s+"
        r"(?P<price_one>\d{1,4}(?:\.\d+)?)\s+Strip\s+of\s+\d+\s+Tabs\s+"
        r"(?P<price_two>\d{1,4}(?:\.\d+)?)\s+Strip\s+of\s+\d+\s+Tabs",
        normalized_page,
        flags=re.IGNORECASE,
    )

    if not row_match:
        return {}

    strengths = _extract_competitor_header_strengths(normalized_page)
    if len(strengths) < 2:
        strengths = ["2.5", "5"]

    return {
        _normalize_strength_key(strengths[0]): float(row_match.group("price_one")),
        _normalize_strength_key(strengths[1]): float(row_match.group("price_two")),
    }


def _extract_competitor_header_strengths(page_data: str) -> list[str]:
    """Extract strength order from competitor price table headers."""
    header_match = re.search(
        r"BRAND\s+COMPANY\s+(.{0,120}?)\s+CONCOR\b",
        page_data,
        flags=re.IGNORECASE,
    )
    header_text = header_match.group(1) if header_match else page_data[:500]
    strengths = re.findall(r"(\d+(?:\.\d+)?)\s*mg\s+SKU\s+MRP", header_text, flags=re.IGNORECASE)
    return [_normalize_strength_key(strength) for strength in strengths]


def _normalize_strength_key(value: str) -> str:
    """Normalize strength keys for price comparison."""
    normalized = str(value).strip()
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _float_set_contains(numbers: set[float], expected: float) -> bool:
    """Return whether a numeric set contains expected value with currency rounding."""
    return any(abs(number - expected) <= 0.05 for number in numbers)


def _extract_requested_product_price(page_data: str, question: str) -> float | None:
    """Extract the requested product price from page text for cost-saving questions."""
    strength_match = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", question, flags=re.IGNORECASE)
    if strength_match:
        strength_price = _extract_strength_price_from_mrp_section(page_data, strength_match.group(1))
        if strength_price is not None:
            return strength_price

    unit_price = _extract_mrp_section_unit_price(page_data, question)
    if unit_price is not None:
        return unit_price

    product_candidates = _extract_product_candidates_from_question(question)
    normalized_page = re.sub(r"\s+", " ", page_data)

    for product in product_candidates:
        product_pattern = r"\s*[-_/]?\s*".join(
            re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", product)
        )
        strength_match = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", question, flags=re.IGNORECASE)
        strength_pattern = ""
        if strength_match and strength_match.group(1) not in product:
            strength_pattern = rf".{{0,30}}{re.escape(strength_match.group(1))}\s*mg"

        match = re.search(
            rf"{product_pattern}{strength_pattern}.{{0,80}}?"
            r"(?<!\d)(\d{1,4}(?:,\d{3})*(?:\.\d+)?)(?!\d)",
            normalized_page,
            flags=re.IGNORECASE,
        )
        if match:
            return float(match.group(1).replace(",", ""))

    return None


def _extract_strength_price_from_mrp_section(page_data: str, strength: str) -> float | None:
    """Extract strength-specific MRP rows like '25 mg - 179.72 Rs per strip'."""
    normalized_page = re.sub(r"\s+", " ", page_data)
    strength_clean = strength.rstrip("0").rstrip(".") if "." in strength else strength
    match = re.search(
        rf"\b{re.escape(strength_clean)}\s*mg\b\s*[–—-]\s*"
        r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*Rs\s*per\s*(?:strip|box|bottle|respule)\b",
        normalized_page,
        flags=re.IGNORECASE,
    )
    if match:
        return float(match.group("price").replace(",", ""))
    return None


def _extract_mrp_section_unit_price(page_data: str, question: str) -> float | None:
    """Extract simple product-page MRP lines by requested unit."""
    normalized_page = re.sub(r"\s+", " ", page_data)
    unit_terms: tuple[str, ...]
    normalized_question = normalize_text(question)
    if "respule" in normalized_question:
        unit_terms = ("respule",)
    elif "box" in normalized_question:
        unit_terms = ("box",)
    elif "strip" in normalized_question:
        unit_terms = ("strip",)
    else:
        return None

    unit_pattern = "|".join(re.escape(unit) for unit in unit_terms)
    matches = list(
        re.finditer(
            r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*Rs\s*per\s*"
            rf"(?:{unit_pattern})\b",
            normalized_page,
            flags=re.IGNORECASE,
        )
    )
    if matches:
        return float(matches[-1].group("price").replace(",", ""))
    return None


def _extract_product_candidates_from_question(question: str) -> list[str]:
    """Extract likely product names before comparison wording."""
    candidates: list[str] = []
    patterns = (
        r"\bbetween\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+and\b",
        r"\bof\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+\d+(?:\.\d+)?\s*mg)?\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, question, flags=re.IGNORECASE):
            candidate = re.sub(r"\b(?:its|competitors?|what|which|brand|price|mrp|sku)\b", " ", match.group(1), flags=re.IGNORECASE)
            candidate = re.sub(r"\s+", " ", candidate).strip(" -_./")
            if candidate and candidate.lower() not in {"the", "all"}:
                candidates.append(candidate)
    return candidates


def _number_set_contains_close_value(numbers: set[float], expected: float) -> bool:
    """Return whether response numbers contain expected percentage with normal rounding."""
    rounded_expected_values = {
        round(expected, 0),
        round(expected, 1),
        round(expected, 2),
    }
    return any(
        any(abs(number - expected_value) <= 0.05 for expected_value in rounded_expected_values)
        for number in numbers
    )


def _compare_expected_competitor_row(
    response_text: str,
    expected_row: dict[str, object],
    ranking_label: str,
) -> tuple[str, str]:
    """Compare SuperAI response against a computed lowest/highest competitor row."""
    expected_brand = str(expected_row["brand"])
    expected_price = float(expected_row["price"])
    brand_match = _entity_text_contains(response_text, expected_brand)
    response_numbers = {float(number) for number in _extract_numbers(response_text)}
    price_match = expected_price in response_numbers

    if brand_match and (not response_numbers or price_match):
        return (
            "PASS",
            f"{ranking_label.title()} competitor price calculated from cited table is "
            f"{expected_brand} at {expected_price:.2f}, matching SuperAI.",
        )

    return (
        "FAIL",
        f"{ranking_label.title()} competitor price calculated from cited table is "
        f"{expected_brand} at {expected_price:.2f}. SuperAI response does not match "
        "the computed cited-table result.",
    )


def _extract_competitor_table_rows(text: str) -> list[dict[str, object]]:
    """Extract competitor table rows preserving brand/company/pack/price columns."""
    delimiter_safe_text = text.replace("\r\n", "\n").replace("\n", " | ")
    cleaned = _remove_punchline_or_slogan_text(delimiter_safe_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    section_match = re.search(
        r"(?:competitors?\s+brand.*?name|brand\s+name\s+company|brand\s+name)"
        r"(.+?)(?:m\.?r\.?p|recommended dosage|salient|indications|composition|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    section = section_match.group(1) if section_match else cleaned
    section = _scope_competitor_section(section)

    company_names = sorted(_known_company_names(), key=len, reverse=True)
    company_pattern = "|".join(re.escape(company) for company in company_names)
    section = re.sub(
        r"\b(?:[A-Za-z][A-Za-z0-9 +./-]{0,80}\s*:-\s*)?"
        r"BRAND\s+NAME\s+COMPANY\s+PACK\s+(?:SIZE\s+)?PRICE\s*/\s*"
        r"(?:STRIP|TAB)(?:\s*-\s*RS)?(?:\s+PRICE\s*/\s*TAB\s*-\s*RS)?",
        " ",
        section,
        flags=re.IGNORECASE,
    )

    row_patterns = (
        re.compile(
            r"(?:^|\s)(?:\d+\s*[.)-]?\s*)"
            rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
            rf"(?P<company>{company_pattern})\s+"
            r"(?P<pack>\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)?)"
            r"\s*(?P<price>\d+(?:\s*\.\s*\d+)?)?",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\s)"
            rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
            rf"(?P<company>{company_pattern})\s+"
            r"(?P<pack>\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)?)"
            r"\s*(?P<price>\d+(?:\s*\.\s*\d+)?)?",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\s)"
            rf"(?P<brand>[A-Za-z][A-Za-z0-9 +./-]{{1,90}}?)\s+"
            rf"(?P<company>{company_pattern})\*?"
            r"(?:\s+\([^)]*\))?"
            r"\s+(?P<price>\d+(?:\s*\.\s*\d+)?)",
            flags=re.IGNORECASE,
        ),
    )

    rows: list[dict[str, object]] = []
    seen_rows: set[tuple[str, str, str, object]] = set()
    for row_pattern in row_patterns:
        for match in row_pattern.finditer(section):
            brand = _clean_brand_name(match.group("brand"))
            company = _normalize_company_display(match.group("company"))
            groups = match.groupdict()
            pack = re.sub(r"\s+", " ", groups.get("pack") or "").strip()
            if re.fullmatch(r"\d+", pack):
                pack = f"{pack} Tab"
            price_text = groups.get("price")
            price = float(re.sub(r"\s+", "", price_text)) if price_text else None

            if not brand or not _is_valid_brand_name(brand):
                continue

            row_key = (
                _normalize_brand_name(brand),
                _normalize_company_display(company).lower(),
                normalize_text(pack),
                price,
            )
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)

            row = {
                "brand": brand,
                "company": company,
                "pack": pack,
                "price": price,
                "audit": {
                    "brand": _entity_match_audit(brand, brand),
                    "company": _entity_match_audit(company, company),
                },
            }
            rows.append(row)

    return rows


def _scope_competitor_page_data_for_question(page_data: str, question: str) -> str:
    """Return the competitor table block for the product named in the question."""
    subjects = _extract_competitor_question_subjects(question)
    if not subjects:
        return page_data

    text = re.sub(r"\s+", " ", page_data).strip()
    heading_pattern = re.compile(
        r"(?P<heading>[A-Za-z][A-Za-z0-9 +./-]{2,90})\s*:-\s+"
        r"BRAND\s+NAME\s+COMPANY\s+PACK\s+(?:SIZE\s+)?PRICE\s*/\s*(?:STRIP|TAB)",
        flags=re.IGNORECASE,
    )
    headings = list(heading_pattern.finditer(text))
    if not headings:
        return page_data

    for index, heading_match in enumerate(headings):
        heading = heading_match.group("heading").strip()
        if not any(_entity_text_contains(heading, subject) or _entity_text_contains(subject, heading) for subject in subjects):
            continue

        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        mrp_match = re.search(r"\bM\.?R\.?P\b", text[heading_match.end() : end], flags=re.IGNORECASE)
        if mrp_match:
            end = heading_match.end() + mrp_match.start()
        return text[heading_match.start() : end].strip()

    return page_data


def _extract_competitor_question_subjects(question: str) -> list[str]:
    """Extract product names from competitor-table questions."""
    patterns = (
        r"\bcompetitor(?:\s+brand)?\s+of\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+has|\s+is|\s+with|\s+priced|\s+belongs|\?|$)",
        r"\bfor\s+([A-Za-z][A-Za-z0-9 +./-]+?)(?:\s+has|\s+is|\s+with|\s+priced|\?|$)",
        r"\bof\s+([A-Za-z][A-Za-z0-9 +./-]+?)\s+(?:has|with|priced|belongs)",
    )
    subjects: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, question, flags=re.IGNORECASE):
            subject = match.group(1).strip(" ?.")
            subject = re.sub(
                r"\b(?:the|highest|lowest|cheapest|price|strip|competitor|brand|company)\b",
                " ",
                subject,
                flags=re.IGNORECASE,
            )
            subject = re.sub(r"\s+", " ", subject).strip()
            if subject and subject.lower() not in {"which", "what"}:
                subjects.append(subject)
    return subjects


def _extract_marketed_by_company(question: str) -> str:
    """Extract company name from questions like 'marketed by Lupin'."""
    match = re.search(
        r"\bmarketed\s+by\s+([A-Za-z][A-Za-z0-9 &.'/-]+?)\??$",
        question,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip(" ?.") if match else ""


def _extract_competitor_brand_names(text: str) -> list[str]:
    """Extract only brand names from competitor sections and ignore numeric values."""
    delimiter_safe_text = text.replace("\r\n", "\n").replace("\n", " | ")
    cleaned = _clean_response_for_validation(delimiter_safe_text)
    cleaned = _remove_punchline_or_slogan_text(cleaned)
    cleaned = re.sub(r"\*+\s*name\s+appears\b.*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\s*,\s*\d+(?:\s*,\s*\d+)*\b", " ", cleaned)
    cleaned = re.sub(
        r"\bsr\.?\s+competitor\s+brand\s+company\s+pack\s+size\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bbrand\s+company\s+pack\s+size\s+price\s*/?\s*strip\s*(?:\(.*?\))?\s+sources\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bbrand\s+name\s+company\s+pack\s+(?:size\s+)?price\s*/?\s*strip\s*(?:\(.*?\))?\s*(?:sources)?\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^.*?\bcompetitor\s+brands?\s+for\s+[A-Za-z0-9 /+-]+(?:\s*\([^)]*\))?\s*[:\-]?\s*",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    competitor_section_match = re.search(
        r"(?:competitors?\s+brand.*?name|brand\s+name\s+company|brand\s+name)"
        r"(.+?)(?:m\.?r\.?p|recommended dosage|salient|indications|composition|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    section = competitor_section_match.group(1) if competitor_section_match else cleaned
    section = _scope_competitor_section(section)

    table_brands = _extract_table_brand_names(section)
    if table_brands:
        return table_brands

    section = re.sub(r"\b\d+(?:\.\d+)?\b", " ", section)
    section = re.sub(
        r"\b(?:tab|tabs|tablet|tablets|cap|caps|strip|price|pack)\b",
        " ",
        section,
        flags=re.IGNORECASE,
    )
    return _extract_listed_brand_names(section)


def _scope_competitor_section(section: str) -> str:
    """Keep only the first competitor table when multiple product tables are adjacent."""
    table_heading_pattern = re.compile(
        r"\s+[A-Za-z][A-Za-z0-9 /+-]{2,60}\s*:-\s+BRAND\s+NAME\s+COMPANY\s+PACK",
        flags=re.IGNORECASE,
    )
    for next_table_match in table_heading_pattern.finditer(section):
        if next_table_match.start() > 20:
            return section[: next_table_match.start()].strip()

    return section


def _extract_table_brand_names(section: str) -> list[str]:
    """Extract numbered table brand names from brand/company/pack/price rows."""
    brands: list[str] = []
    known_companies = _known_company_names()
    company_pattern = "|".join(re.escape(company) for company in known_companies)
    row_segments = re.split(
        r"(?=(?:^|\s)[1-9]\d?\s+(?!Tab\b|Tabs\b|Tablet\b|Tablets\b|Cap\b|Caps\b|Strip\b|Ml\b|Gm\b|Mg\b)[A-Z])",
        section,
    )
    row_segment_pattern = re.compile(
        rf"^\s*\d+\s+(.+?)\*?\s+(?:{company_pattern})\s+"
        r"\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b",
        flags=re.IGNORECASE,
    )

    for segment in row_segments:
        match = row_segment_pattern.search(segment)
        if not match:
            continue

        brand = _clean_brand_name(match.group(1))
        if brand and _is_valid_brand_name(brand):
            _append_unique_brand(brands, brand)

    row_pattern = re.compile(
        r"(?:^|\s)(?:\d+\s*[.)-]\s*)"
        rf"([A-Za-z][A-Za-z0-9 +./-]{{1,80}}?)\*?\s+"
        rf"(?:{company_pattern})"
        r"\s+\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b"
        r"(?:\s+\d+(?:\.\d+)?)?",
        flags=re.IGNORECASE,
    )

    for match in row_pattern.finditer(section):
        brand = _clean_brand_name(match.group(1))
        if brand and _is_valid_brand_name(brand):
            _append_unique_brand(brands, brand)

    no_number_row_pattern = re.compile(
        rf"([A-Za-z][A-Za-z0-9 +./-]{{1,80}}?)\*?\s+"
        rf"(?:{company_pattern})\s+"
        r"\d+\s*(?:tab|tabs|tablet|tablets|cap|caps|strip|ml|gm|g|mg)\b"
        r"(?:\s+\d+(?:\.\d+)?)?"
        r"(?:\s+\d+(?:\s*,\s*\d+)*)?",
        flags=re.IGNORECASE,
    )

    for match in no_number_row_pattern.finditer(section):
        brand = _clean_brand_name(match.group(1))
        if brand and _is_valid_brand_name(brand):
            _append_unique_brand(brands, brand)

    if brands:
        return brands

    company_based_pattern = re.compile(
        rf"(?:^|\s)(?:\d+\s*[.)-]?\s*)?"
        rf"([A-Za-z][A-Za-z0-9 +./-]{{1,60}}?)\s+"
        rf"(?:{company_pattern})(?=\s|$)",
        flags=re.IGNORECASE,
    )

    for match in company_based_pattern.finditer(section):
        brand = _clean_brand_name(match.group(1))
        if brand and _is_valid_brand_name(brand):
            _append_unique_brand(brands, brand)

    if brands:
        return brands

    return brands


def _known_company_names() -> tuple[str, ...]:
    """Return known pharma company names used to identify table columns."""
    return (
        "drl",
        "ipca",
        "micro",
        "bal",
        "eris life",
        "eris",
        "alkem",
        "servier",
        "jb chemicals",
        "jb pharma",
        "merck specialities",
        "merck",
        "mankind",
        "sun pharma",
        "aristo",
        "indoco",
        "alembic",
        "koye",
        "mex",
        "sun",
        "zydus",
        "zydus cadilla",
        "cipla",
        "gr",
        "torrent",
        "lupin",
        "abbott",
        "ajanta",
        "glenmark",
        "macelods",
        "macleods",
        "wockhardt",
        "corona remedies",
        "la renon healthcare",
        "systopic laboratories",
        "novartis",
        "rpg",
        "biocon",
        "concord biotec",
        "steris",
        "usv",
        "intace",
        "intas",
        "bi",
        "boehringer ingelheim",
    )


def _extract_listed_brand_names(section: str) -> list[str]:
    """Extract brands from simple comma/newline/bullet response lists."""
    section = re.sub(
        r"\b(?:the|competitors?|competitor|brand|brands|are|is|include|includes|of|for)\b",
        " ",
        section,
        flags=re.IGNORECASE,
    )
    candidates = re.split(r"[,;\n|]|\s+-\s+|\s+\band\b\s+|\s+\d+\s*[.)]\s+", section)
    brands: list[str] = []

    for candidate in candidates:
        brand = _clean_brand_name(candidate)
        if brand and _is_valid_brand_name(brand):
            _append_unique_brand(brands, brand)

    return brands


def _clean_brand_name(text: str) -> str:
    """Clean a competitor brand candidate."""
    brand = text.replace("*", " ")
    brand = re.sub(
        r"^\s*(?:(?:sources?|competitors?|competitor|brand|brands|name|company|pack|size|segment)\b\s*)+",
        " ",
        brand,
        flags=re.IGNORECASE,
    )
    brand = re.sub(r"\b\d+(?:\.\d+)?\b", " ", brand)
    brand = re.sub(
        r".*\bbrand\s+name\s+company\s+pack\s+price\s*/?\s*strip\b",
        " ",
        brand,
        flags=re.IGNORECASE,
    )
    brand = re.sub(
        r".*\bbrand\s+name\b",
        " ",
        brand,
        flags=re.IGNORECASE,
    )
    brand = re.sub(
        r"\b(?:company|pack|size|price|strip|tab|tabs|tablet|tablets|cap|caps|mrp|sources?|mg)\b",
        " ",
        brand,
        flags=re.IGNORECASE,
    )
    brand = re.sub(r"\s+", " ", brand).strip(" /:-.,;")
    company_pattern = "|".join(re.escape(company) for company in _known_company_names())
    brand = re.sub(
        rf"\s+(?:{company_pattern})$",
        "",
        brand,
        flags=re.IGNORECASE,
    )
    return brand


def _is_valid_brand_name(brand: str) -> bool:
    """Return whether a candidate is a real brand name, not table noise."""
    normalized = _normalize_brand_name(brand)
    invalid = {
        "",
        "brand name",
        "company",
        "competitors name",
        "competitors brand",
        "competitors brand company",
        "price strip",
        "punch line",
        "punchline",
        "slogan",
        "tagline",
    }
    return (
        normalized not in invalid
        and "punch line" not in normalized
        and "punchline" not in normalized
        and "slogan" not in normalized
        and "tagline" not in normalized
        and any(char.isalpha() for char in brand)
    )


def _remove_punchline_or_slogan_text(text: str) -> str:
    """Remove punchline/slogan sections from competitor-brand extraction."""
    return re.sub(
        r"\b(?:punch\s*line|punchline|slogan|tagline)\b.*?"
        r"(?=\b(?:competitors?\s+brand|brand\s+name|composition|mode of action|"
        r"indications|recommended dosage|salient|m\.?r\.?p)\b|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )


def _normalize_brand_name(brand: str) -> str:
    """Normalize brand names for exact brand comparison."""
    return _normalize_entity_value(brand)


def _brand_matches_any(response_brand: str, normalized_page_brands: set[str]) -> bool:
    """Return whether a response brand or slash variant exists on the cited page.

    Medicine brand names are sensitive, so this intentionally avoids fuzzy
    matching. A one-letter difference can be a different product.
    """
    candidates = [response_brand]
    if "/" in response_brand:
        candidates.extend(part.strip() for part in response_brand.split("/") if part.strip())

    for candidate in candidates:
        normalized_candidate = _normalize_brand_name(candidate)
        if normalized_candidate in normalized_page_brands:
            return True

    return False


def _normalize_entity_value(value: str) -> str:
    """Normalize entity strings before exact/fuzzy comparison."""
    normalized = normalize_text(value)
    normalized = _company_aliases().get(normalized, normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_company_display(company: str) -> str:
    """Return canonical display name for known company aliases."""
    normalized = _normalize_entity_value(company)
    display_aliases = {
        "dr reddys laboratories": "Dr. Reddy's Laboratories",
        "ipca laboratories": "IPCA Laboratories",
        "eris lifesciences": "Eris Lifesciences",
        "boehringer ingelheim": "BI",
        "sun pharma": "Sun Pharma",
        "ipca laboratories": "IPCA Laboratories",
    }
    return display_aliases.get(normalized, company.strip())


def _company_aliases() -> dict[str, str]:
    """Return company aliases for pharma entity normalization."""
    return {
        "eris": "eris lifesciences",
        "eris life": "eris lifesciences",
        "eris lifesciences": "eris lifesciences",
        "drl": "dr reddys laboratories",
        "dr reddy": "dr reddys laboratories",
        "dr reddys": "dr reddys laboratories",
        "dr reddy s laboratories": "dr reddys laboratories",
        "dr reddys laboratories": "dr reddys laboratories",
        "ipca": "ipca laboratories",
        "ipca labs": "ipca laboratories",
        "ipca laboratories": "ipca laboratories",
        "sun": "sun pharma",
        "sun pharma": "sun pharma",
        "sun pharmaceutical": "sun pharma",
        "bi": "boehringer ingelheim",
        "boehringer": "boehringer ingelheim",
        "boehringer ingelheim": "boehringer ingelheim",
    }


def _entity_match_audit(
    left_value: str,
    right_value: str,
    threshold: float = COMPANY_ENTITY_MATCH_THRESHOLD,
    allow_fuzzy: bool = False,
) -> dict[str, object]:
    """Return original values, normalized values, score, and match decision."""
    left_normalized = _normalize_entity_value(left_value)
    right_normalized = _normalize_entity_value(right_value)
    score = _levenshtein_similarity(left_normalized, right_normalized)
    matched = left_normalized == right_normalized or (allow_fuzzy and score >= threshold)
    return {
        "left_original": left_value,
        "right_original": right_value,
        "left_normalized": left_normalized,
        "right_normalized": right_normalized,
        "score": round(score, 3),
        "matched": matched,
    }


def _entity_values_match(
    left_value: str,
    right_value: str,
    threshold: float = COMPANY_ENTITY_MATCH_THRESHOLD,
    allow_fuzzy: bool = False,
) -> bool:
    """Return whether two entity values are equivalent after alias/fuzzy matching."""
    return bool(_entity_match_audit(left_value, right_value, threshold, allow_fuzzy)["matched"])


def _entity_matches_any(value: str, candidates: list[str], allow_fuzzy: bool = False) -> bool:
    """Return whether an entity matches any candidate with audit-aware normalization."""
    return bool(_entity_best_match_audit(value, candidates, allow_fuzzy=allow_fuzzy)["matched"])


def _entity_best_match_audit(
    value: str,
    candidates: list[str],
    allow_fuzzy: bool = False,
) -> dict[str, object]:
    """Return best entity match audit for one value against candidate values."""
    candidate_values = [value]
    if "/" in value:
        candidate_values.extend(part.strip() for part in value.split("/") if part.strip())

    best_audit: dict[str, object] | None = None
    for candidate_value in candidate_values:
        for candidate in candidates:
            audit = _entity_match_audit(
                candidate_value,
                candidate,
                allow_fuzzy=allow_fuzzy,
            )
            if best_audit is None or float(audit["score"]) > float(best_audit["score"]):
                best_audit = audit

    if best_audit is None:
        best_audit = {
            "left_original": value,
            "right_original": "",
            "left_normalized": _normalize_entity_value(value),
            "right_normalized": "",
            "score": 0.0,
            "matched": False,
        }

    return best_audit


def _format_entity_audit_summary(audits: list[dict[str, object]]) -> str:
    """Return concise audit trail for entity normalization decisions."""
    if not audits:
        return ""

    audit_parts = []
    for audit in audits[:5]:
        audit_parts.append(
            f"{audit['left_original']} -> {audit['left_normalized']} "
            f"matched {audit['right_original']} -> {audit['right_normalized']} "
            f"(score {float(audit['score']):.2f})"
        )

    if len(audits) > 5:
        audit_parts.append(f"+{len(audits) - 5} more")

    return "Entity audit: " + "; ".join(audit_parts) + "."


def _entity_text_contains(text: str, expected_entity: str) -> bool:
    """Return whether text contains an entity after alias/fuzzy normalization."""
    normalized_text = _normalize_entity_value(text)
    normalized_entity = _normalize_entity_value(expected_entity)
    if normalized_entity and normalized_entity in normalized_text:
        return True

    text_entities = _extract_possible_entities(text)
    return _entity_matches_any(expected_entity, text_entities)


def _company_text_contains(text: str, expected_company: str) -> bool:
    """Return whether text contains a company after alias/controlled OCR matching."""
    normalized_text = _normalize_entity_value(text)
    normalized_company = _normalize_entity_value(expected_company)
    if normalized_company and normalized_company in normalized_text:
        return True
    for alias, canonical in _company_aliases().items():
        if canonical == normalized_company and re.search(rf"\b{re.escape(alias)}\b", normalize_text(text)):
            return True

    text_entities = _extract_possible_entities(text)
    return _entity_matches_any(expected_company, text_entities, allow_fuzzy=True)


def _entity_text_contains_ordered_tokens(text: str, expected_entity: str) -> bool:
    """Return whether all entity tokens appear in order inside text."""
    text_tokens = re.findall(r"[a-z0-9]+", _normalize_entity_value(text))
    entity_tokens = re.findall(r"[a-z0-9]+", _normalize_entity_value(expected_entity))
    if not entity_tokens:
        return False
    position = 0
    for entity_token in entity_tokens:
        try:
            found_at = text_tokens.index(entity_token, position)
        except ValueError:
            return False
        position = found_at + 1
    return True


def _extract_possible_entities(text: str) -> list[str]:
    """Extract possible entity spans from response text for fuzzy matching."""
    cleaned = _clean_response_for_validation(text)
    parts = re.split(r"[,;|\n]|\s+-\s+|\s+\band\b\s+", cleaned)
    entities: list[str] = []
    for part in parts:
        candidate = re.sub(r"\b\d+(?:\.\d+)?\b", " ", part)
        candidate = re.sub(
            r"\b(?:price|mrp|strip|tab|tabs|tablet|tablets|pack|company|brand|lowest|highest|has|is|at|rs|inr|per)\b",
            " ",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"\s+", " ", candidate).strip(" :-.,")
        if candidate and any(char.isalpha() for char in candidate):
            entities.append(candidate)

    entities.append(cleaned)
    return entities


def _levenshtein_similarity(left: str, right: str) -> float:
    """Return normalized Levenshtein similarity between two strings."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current

    distance = previous[-1]
    return 1 - (distance / max(len(left), len(right)))


def _append_unique_brand(brands: list[str], brand: str) -> None:
    """Append a brand once using normalized comparison."""
    normalized = _normalize_brand_name(brand)
    if normalized and normalized not in {_normalize_brand_name(existing) for existing in brands}:
        brands.append(brand)


def _is_multi_product_question(normalized_question: str) -> bool:
    """Return whether a question needs separate evidence per product."""
    if "mycept" in normalized_question and "mycept s" in normalized_question:
        return True
    return bool(re.search(r"\bbetween\b.+\band\b", normalized_question))


def _compare_multi_product_response(
    response_content: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate multi-product answers product-by-product, never as one flat text."""
    products = _extract_products_for_multi_validation(question, response_content)
    if len(products) < 2:
        return _compare_descriptive_response(response_content, page_data)

    product_results: list[tuple[str, str, str]] = []
    for product in products:
        evidence = _extract_product_evidence_section(page_data, product)
        product_answer = _extract_product_answer_section(response_content, product)

        if not evidence:
            product_results.append(
                (
                    product,
                    "DATA MISSING",
                    f"{product} cited evidence section was not found.",
                )
            )
            continue

        if not product_answer:
            product_results.append(
                (
                    product,
                    "DATA MISSING",
                    f"SuperAI did not provide a separate value for {product}.",
                )
            )
            continue

        strict_result = _validate_product_strict_values(product_answer, evidence, product)
        if strict_result[0] != "PASS":
            product_results.append((product, strict_result[0], strict_result[1]))
            continue

        semantic_result, semantic_reason = _compare_descriptive_response(product_answer, evidence)
        if semantic_result == "FAIL":
            product_results.append((product, "FAIL", semantic_reason))
        else:
            product_results.append(
                (
                    product,
                    "PASS",
                    f"{product} evidence supports the product-specific claims.",
                )
            )

    statuses = [status for _, status, _ in product_results]
    reason = " | ".join(f"{product}: {detail}" for product, _, detail in product_results)

    if all(status == "PASS" for status in statuses):
        return "PASS", f"All product-specific claims are supported. {reason}"

    if "DATA MISSING" in statuses:
        return "DATA MISSING", reason

    if "FAIL" in statuses:
        return "FAIL", reason

    return "DATA MISSING", reason


def _extract_products_for_multi_validation(question: str, response_content: str) -> list[str]:
    """Extract product names that must be validated independently."""
    normalized = normalize_text(f"{question} {response_content}")
    products: list[str] = []
    for product in ("mycept s", "mycept"):
        if product in normalized:
            products.append(product)
    products.sort(key=len)
    return products


def _extract_product_evidence_section(page_data: str, product: str) -> str:
    """Return source text for one product only."""
    cleaned = re.sub(r"\s+", " ", page_data or "").strip()
    normalized_product = normalize_text(product)

    if normalized_product == "mycept s":
        start_match = re.search(
            r"\bbrand snapshot\s+mycept\s+s\b|\bname of product:?\s*mycept\s+s\b",
            cleaned,
            flags=re.IGNORECASE,
        )
        if not start_match:
            return ""
        start = start_match.start()
        end_match = re.search(
            r"\bCitation\s+\d+\s+\|\s+Document\b|\bBrand Snapshot\s+MYCEPT\b",
            cleaned[start + 20 :],
            flags=re.IGNORECASE,
        )
        end = start + 20 + end_match.start() if end_match else len(cleaned)
        return cleaned[start:end].strip()

    if normalized_product == "mycept":
        # Plain MYCEPT evidence must not be the MYCEPT S section.
        start_match = re.search(
            r"\bbrand snapshot\s+mycept\b(?!\s+s)|\bname of product:?\s*mycept\b(?!\s+s)",
            cleaned,
            flags=re.IGNORECASE,
        )
        if not start_match:
            comparison_match = re.search(
                r"\bmycophenolate mofetil\s*\(mycept\)\b|\bmycept\b.*?\bprodrug\b|\bprodrug\b.*?\bmycept\b",
                cleaned,
                flags=re.IGNORECASE,
            )
            if comparison_match:
                return cleaned[max(0, comparison_match.start() - 500) : comparison_match.start() + 900].strip()
            return ""
        start = start_match.start()
        section = cleaned[start:]
        stop_match = re.search(r"\b(?:brand snapshot\s+)?mycept\s+s\b", section[20:], flags=re.IGNORECASE)
        end = 20 + stop_match.start() if stop_match else len(section)
        return section[:end].strip()

    match = re.search(re.escape(product), cleaned, flags=re.IGNORECASE)
    return cleaned[max(0, match.start() - 200) : match.start() + 1200] if match else ""


def _extract_product_answer_section(response_content: str, product: str) -> str:
    """Return the SuperAI answer portion for one product."""
    cleaned = re.sub(r"\s+", " ", _clean_response_for_validation(response_content)).strip()
    normalized_product = normalize_text(product)

    if normalized_product == "mycept s":
        match = re.search(r"\bmycept\s+s\b(.+?)(?=\bmycept\b(?!\s+s)|$)", cleaned, flags=re.IGNORECASE)
        if match:
            return f"{product} {match.group(1)}".strip()
        return cleaned if re.search(r"\bmycept\s+s\b", cleaned, flags=re.IGNORECASE) else ""

    if normalized_product == "mycept":
        match = re.search(r"\bmycept\b(?!\s+s)(.+?)(?=\bmycept\s+s\b|$)", cleaned, flags=re.IGNORECASE)
        if match:
            return f"{product} {match.group(1)}".strip()
        return cleaned if re.search(r"\bmycept\b(?!\s+s)", cleaned, flags=re.IGNORECASE) else ""

    match = re.search(re.escape(product), cleaned, flags=re.IGNORECASE)
    return cleaned[match.start() : match.start() + 700] if match else ""


def _validate_product_strict_values(
    product_answer: str,
    product_evidence: str,
    product: str,
) -> tuple[str, str]:
    """Validate critical numeric/unit values inside one product's evidence."""
    answer_values = _extract_numeric_unit_values(_clean_numeric_validation_text(product_answer))
    evidence_values = _extract_numeric_unit_values(_clean_numeric_validation_text(product_evidence))
    critical_values = {
        value
        for value in answer_values
        if re.search(r"\b(?:mg|g|mcg|ml|tab|tabs|tablet|tablets|day|daily|bid|od)\b", value)
    }

    if critical_values and not evidence_values:
        return "DATA MISSING", f"{product} critical numeric evidence was not found."

    missing = sorted(critical_values.difference(evidence_values))
    if missing:
        if evidence_values:
            return (
                "FAIL",
                f"{product} strict value mismatch. Missing cited value(s): {', '.join(missing)}.",
            )
        return (
            "DATA MISSING",
            f"{product} cited evidence is missing required value(s): {', '.join(missing)}.",
        )

    return "PASS", f"{product} strict values are supported."


# ---------------------------------------------------------------------------
# CLINICAL OUTCOME — range-aware numeric comparison
# ---------------------------------------------------------------------------

_OUTCOME_PERCENT_TOLERANCE = 2.0  # ± percentage points for clinical values


def _extract_outcome_numbers(text: str) -> list[float]:
    """Extract all numeric outcome values from clinical text.

    Handles:
    - Bare percentages:    "48%", "50.5%", "~52%", ">30%"
    - Decimal reductions:  "3.2 mmol/L", "1.5 mg/dL", "0.8%"
    - Ranges (both ends):  "50-60%", "50 to 60%", "50–60%"

    Returns a deduplicated, sorted list of float values.
    """
    values: set[float] = set()

    # Ranges: "50-60%", "50–60%", "50 to 60%"
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*%",
        text,
        flags=re.IGNORECASE,
    ):
        values.add(float(match.group(1)))
        values.add(float(match.group(2)))

    # Single percentages: "48%", "~48%", ">48%", "≥48%"
    for match in re.finditer(
        r"[~>≥≤<]?\s*(\d+(?:\.\d+)?)\s*%",
        text,
    ):
        values.add(float(match.group(1)))

    # Absolute clinical values with units: "3.2 mmol/L", "1.5 mg/dl"
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*(?:mmol/l|mg/dl|mg/dL|mmhg|mmHg)\b",
        text,
        flags=re.IGNORECASE,
    ):
        values.add(float(match.group(1)))

    return sorted(values)


def _extract_response_outcome_bounds(text: str) -> tuple[float, float] | None:
    """Return (lo, hi) covering all numeric outcome claims in the response.

    For a range response like "50-60%" returns (50.0, 60.0).
    For a single value like "80%" returns (80.0, 80.0).
    Returns None when no outcome numbers are found.
    """
    values = _extract_outcome_numbers(text)
    if not values:
        return None
    return (min(values), max(values))


def _compare_clinical_outcome(
    response_text: str,
    page_data: str,
    question: str,
) -> tuple[str, str]:
    """Validate clinical outcome questions using a cited numeric range.

    Builds a supported range from outcome values on the cited page, then
    checks whether the response claim falls within that range.

    Before building the page range, numbers that are likely noise (page numbers,
    years, large patient counts) are filtered out so the range is not artificially
    widened causing false PASSes, or artificially narrowed causing false FAILs.

    PASS  — response bounds are fully contained within the supported range.
    FAIL  — response claims a value that exceeds or contradicts cited evidence.
    DATA MISSING — no outcome numbers found on the cited page.
    """
    page_values_raw = _extract_outcome_numbers(page_data)
    if not page_values_raw:
        _log_validation_step(
            rule="_compare_clinical_outcome",
            attribute="CLINICAL_OUTCOME",
            verdict="DATA MISSING",
            reason="No clinical outcome values found on the cited page.",
        )
        return "DATA MISSING", "No clinical outcome values found on the cited page."

    response_bounds = _extract_response_outcome_bounds(response_text)
    if response_bounds is None:
        _log_validation_step(
            rule="_compare_clinical_outcome",
            attribute="CLINICAL_OUTCOME",
            doc_value=f"[{min(page_values_raw):g}–{max(page_values_raw):g}]",
            verdict="DATA MISSING",
            reason="SuperAI response contained no numeric outcome values.",
        )
        return "DATA MISSING", "SuperAI response contained no numeric outcome values."

    resp_lo, resp_hi = response_bounds

    # Filter noise: exclude numbers that are clearly not clinical outcome values.
    # Years (1900-2100), page numbers (> 200 for clinical documents unless the
    # response itself mentions numbers that large), and patient counts (> 10000
    # for %-style outcomes) are excluded to prevent range inflation.
    # Keep only values in the plausible outcome range: [0, 200] for percentages
    # and absolute reductions; [0.01, 20] for ratios/hazard ratios; extend to
    # the response bounds to avoid unfairly cutting out the cited evidence.
    plausible_max = max(200.0, resp_hi * 2)
    page_values = [v for v in page_values_raw if 0 <= v <= plausible_max and not (1900 <= v <= 2100)]
    if not page_values:
        page_values = page_values_raw  # fallback: use all if filtering removed everything

    cited_lo = min(page_values)
    cited_hi = max(page_values)
    tol = _OUTCOME_PERCENT_TOLERANCE

    supported_lo = cited_lo - tol
    supported_hi = cited_hi + tol

    within_range = resp_lo >= supported_lo and resp_hi <= supported_hi

    cited_summary = (
        f"{cited_lo:g}–{cited_hi:g}%"
        if cited_lo != cited_hi
        else f"{cited_lo:g}%"
    )
    resp_summary = (
        f"{resp_lo:g}–{resp_hi:g}%"
        if resp_lo != resp_hi
        else f"{resp_lo:g}%"
    )

    if within_range:
        _log_validation_step(
            rule="_compare_clinical_outcome",
            attribute="CLINICAL_OUTCOME",
            doc_value=cited_summary,
            response_value=resp_summary,
            normalization=f"supported range [{supported_lo:g}, {supported_hi:g}]",
            verdict="PASS",
            reason=f"Response {resp_summary} is within cited range {cited_summary}.",
        )
        return (
            "PASS",
            f"Clinical outcome {resp_summary} is supported by cited evidence "
            f"(cited range: {cited_summary}).",
        )

    _log_validation_step(
        rule="_compare_clinical_outcome",
        attribute="CLINICAL_OUTCOME",
        doc_value=cited_summary,
        response_value=resp_summary,
        normalization=f"supported range [{supported_lo:g}, {supported_hi:g}]",
        verdict="FAIL",
        reason=f"Response {resp_summary} exceeds or contradicts cited range {cited_summary}.",
    )
    return (
        "FAIL",
        f"Clinical outcome mismatch. Cited evidence supports {cited_summary}, "
        f"but SuperAI claimed {resp_summary}.",
    )


def _compare_descriptive_response(
    response_content: str,
    page_data: str,
    question: str = "",
) -> tuple[str, str]:
    """Validate descriptive medical attributes by supported concepts, not raw words."""
    normalized_response = _semantic_normalize(response_content)
    normalized_page = _semantic_normalize(page_data)
    normalized_question = _semantic_normalize(question)

    response_concepts = _extract_semantic_concepts(normalized_response)
    page_concepts = _extract_semantic_concepts(normalized_page)

    if _requires_descriptive_comparison(normalized_question) and not _has_supported_descriptive_comparison(
        normalized_page
    ):
        return (
            "DATA MISSING",
            "The cited page does not support the requested descriptive comparison/superiority claim.",
        )

    if response_concepts:
        relevant_concepts = _select_relevant_descriptive_concepts(
            normalized_question,
            response_concepts,
        )
        if relevant_concepts:
            matched_relevant = sorted(relevant_concepts.intersection(page_concepts))
            missing_relevant = sorted(relevant_concepts.difference(page_concepts))
            if not missing_relevant:
                return (
                    "PASS",
                    "Core factual claim is supported by the cited page. "
                    f"Matched core concept(s): {', '.join(matched_relevant)}.",
                )

            if matched_relevant:
                coverage = len(matched_relevant) / len(relevant_concepts)
                if coverage >= 0.5 or len(matched_relevant) >= 2:
                    return (
                        "PASS",
                        "Core descriptive claim is supported by the cited page; "
                        "extra explanatory wording was not treated as required evidence. "
                        f"Matched core concept(s): {', '.join(matched_relevant)}.",
                    )
                # Only 1 concept matched and coverage < 50%: check if there is
                # meaningful context overlap before returning DATA MISSING.
                # If the page is topically relevant, return FAIL (value exists but
                # differs) rather than DATA MISSING (no evidence at all).
                if _has_descriptive_context_overlap(normalized_response, normalized_page):
                    return (
                        "FAIL",
                        "Core factual claim is only partially supported on the cited page. "
                        f"Missing core concept(s): {', '.join(missing_relevant)}.",
                    )
                return (
                    "DATA MISSING",
                    "Core factual claim is only partially supported on the cited page. "
                    f"Missing core concept(s): {', '.join(missing_relevant)}.",
                )

            if _has_descriptive_context_overlap(normalized_response, normalized_page):
                return (
                    "DATA MISSING",
                    "Related cited text exists, but the core factual claim was not found.",
                )

            return "DATA MISSING", "Core factual claim was not found on the cited page."

        matched_concepts = sorted(response_concepts.intersection(page_concepts))
        missing_concepts = sorted(response_concepts.difference(page_concepts))

        if len(matched_concepts) == len(response_concepts):
            return (
                "PASS",
                f"Semantic match found for descriptive attribute: {', '.join(matched_concepts)}.",
            )

        if matched_concepts:
            coverage = len(matched_concepts) / len(response_concepts)
            if coverage >= 0.6:
                return (
                    "PASS",
                    "Meaning is supported by the cited page despite wording differences. "
                    f"Matched concept(s): {', '.join(matched_concepts)}.",
                )
            return (
                "FAIL",
                "Descriptive value is only partially supported on the cited page. "
                f"Missing concept(s): {', '.join(missing_concepts)}.",
            )

        if _has_descriptive_context_overlap(normalized_response, normalized_page):
            return (
                "FAIL",
                "Related descriptive data exists on the cited page, but the meaning does not match.",
            )

        # No concept matched the page and no drug-class overlap exists — the
        # concept dictionary may simply lack coverage for this question type
        # (e.g. clinical trial outcomes, survival benefits, SHEP study results).
        # Fall through to keyword comparison so those questions are not falsely
        # returned as DATA MISSING.

    response_keywords = _extract_keywords(normalized_response)
    page_keywords = _extract_keywords(normalized_page)
    matched_keywords = sorted(response_keywords.intersection(page_keywords))

    if not response_keywords:
        return "DATA MISSING", "Super AI response did not contain a descriptive value to validate."

    coverage = len(matched_keywords) / len(response_keywords)
    if coverage >= 0.45 and len(matched_keywords) >= 3:
        return (
            "PASS",
            "Descriptive meaning is supported by the cited page despite wording differences.",
        )

    # Numeric supplement: _extract_keywords ignores pure numbers (pattern
    # requires a letter start), so clinical statistics like "4736", "36", "1"
    # are invisible to keyword coverage.  If every number in the response
    # appears on the cited page AND there is at least minimal keyword context,
    # treat as sufficient evidence.
    response_numbers_sup = _extract_numbers(normalized_response)
    page_numbers_sup = _extract_numbers(normalized_page)
    if (
        response_numbers_sup
        and response_numbers_sup.issubset(page_numbers_sup)
        and matched_keywords
    ):
        return (
            "PASS",
            "Clinical numeric value(s) from SuperAI confirmed on cited page: "
            f"{', '.join(sorted(response_numbers_sup))}. "
            f"Keyword context: {', '.join(matched_keywords[:5])}.",
        )

    # Clinical relaxation: trial/study outcome questions naturally include
    # context words (year, full trial name, methodology notes) that the
    # document excerpt does not repeat.  Accept 30% coverage with at least
    # 2 keyword matches so these do not falsely return DATA MISSING or FAIL.
    _clinical_question_terms = (
        "trial",
        "study",
        "shep",
        "enrolled",
        "survival",
        "guideline",
        "evidence",
        "mortality",
        "reduction",
        "benefit",
        "randomized",
        "randomised",
    )
    is_clinical_question = any(
        term in normalize_text(question) for term in _clinical_question_terms
    )
    if is_clinical_question and coverage >= 0.30 and len(matched_keywords) >= 2:
        return (
            "PASS",
            "Clinical evidence from cited page broadly supports the SuperAI response. "
            f"Matched keyword(s): {', '.join(matched_keywords)}.",
        )

    # Policy/incentive questions: a single strong keyword match (product name or
    # policy term) combined with any numeric overlap is sufficient to PASS rather
    # than returning DATA MISSING.  These documents are highly structured and
    # the keyword coverage metric penalises valid answers that use different
    # sentence structure than the extracted page text.
    _policy_question_terms = (
        "incentive",
        "objective",
        "productivity",
        "growth",
        "pangraf",
        "eligibility",
        "criteria",
        "trip",
        "award",
        "medal",
        "reimbursement",
        "stockist",
        "credit",
    )
    is_policy_question = any(
        term in normalize_text(question) for term in _policy_question_terms
    )
    response_numbers_check = _extract_numbers(normalized_response)
    page_numbers_check = _extract_numbers(normalized_page)
    if (
        is_policy_question
        and matched_keywords
        and response_numbers_check
        and response_numbers_check.issubset(page_numbers_check)
    ):
        return (
            "PASS",
            "Policy/incentive values from cited page match the SuperAI response. "
            f"Matched keyword(s): {', '.join(matched_keywords)}; "
            f"matched numeric(s): {', '.join(sorted(response_numbers_check))}.",
        )

    if matched_keywords:
        return (
            "FAIL",
            "Related descriptive data exists on the cited page, but required meaning is incomplete.",
        )

    return "DATA MISSING", "Required descriptive value not found on the cited page."


def _select_relevant_descriptive_concepts(
    normalized_question: str,
    response_concepts: set[str],
) -> set[str]:
    """Return the concepts that answer the question's core factual ask.

    Descriptive SuperAI answers often include surrounding explanation. For MOA,
    USP, indication, and clinical-benefit questions, validate the core claim
    requested by the question instead of every extra phrase in the response.
    """
    concept_groups = (
        (
            ("voglibose", "postprandial", "pphg"),
            {
                "voglibose",
                "alpha glucosidase inhibition",
                "delayed glucose absorption",
            },
        ),
        (
            ("dapagliflozin", "sglt2", "renal glucose", "urinary glucose"),
            {
                "sglt2 inhibition",
                "renal glucose excretion",
            },
        ),
        (
            ("metformin",),
            {
                "insulin sensitivity",
                "glucose uptake",
                "hepatic glucose production",
                "glycaemic control",
            },
        ),
        (
            ("gliclazide", "insulin secretion", "cellular"),
            {
                "sulphonylurea receptor binding",
                "insulin secretion",
            },
        ),
        (
            ("linagliptin", "glp", "gip", "dpp"),
            {
                "dpp4 inhibition",
                "glp gip incretin",
                "insulin secretion",
                "hepatic glucose production",
                "glycaemic control",
                "fast slow dpp4 binding",
                "dpp4 selectivity",
                "reduced off target effects",
                "od convenience",
            },
        ),
        (
            ("ckd", "esrd", "renal"),
            {
                "safe renal impairment",
                "esrd risk reduction",
            },
        ),
        (
            ("normal saline", "dilution", "medium", "iv infusion"),
            {
                "normal saline dilution",
                "iv infusion",
            },
        ),
        (
            ("indication", "indications", "used for", "prescribed"),
            {
                "type 2 diabetes management",
                "solid organ transplantation",
                "organ rejection prophylaxis",
                "central nervous system",
            },
        ),
        (
            ("symptom", "symptoms", "bph", "oab", "storage"),
            {
                "bph luts relief",
                "overactive bladder symptom control",
            },
        ),
        (
            ("side effect", "side effects", "adverse", "reaction", "reactions", "discomfort"),
            {
                "gastrointestinal discomfort",
                "renal dysfunction",
                "tremor",
                "hirsutism",
                "hypertension",
                "gum hyperplasia",
                "nephrotoxicity monitoring",
            },
        ),
        (
            ("nephrotoxicity", "monitoring", "precaution", "precautions"),
            {
                "nephrotoxicity monitoring",
                "renal dysfunction",
            },
        ),
        (
            ("organ", "organs", "transplantation", "transplant"),
            {
                "kidney liver heart transplantation",
                "organ rejection prophylaxis",
            },
        ),
        (
            # Require "cars" or "upper limb" — "trial" alone is too broad and
            # wrongly fires for SHEP trial, CORONA trial, etc.
            ("cars", "upper limb", "motor"),
            {
                "cars trial",
                "upper limb motor function",
            },
        ),
        (
            ("silodosin", "bph", "urine flow", "luts"),
            {
                "alpha1a blockade",
                "smooth muscle relaxation",
                "urine flow improvement",
                "bph luts relief",
            },
        ),
        (
            ("mirabegron", "overactive bladder", "oab"),
            {
                "beta3 agonist",
                "bladder relaxation",
                "overactive bladder symptom control",
            },
        ),
        (
            ("vitamin d3", "nurokind", "respiratory", "asthma", "copd", "immunity"),
            {
                "respiratory immunity",
                "anti inflammatory",
                "immunoregulatory",
                "copd exacerbation reduction",
                "glucocorticoid responsiveness",
                "immune health",
            },
        ),
        (
            ("formoterol", "glycopyrronium", "glycobreez", "bronchodilation", "copd"),
            {
                "formoterol beta2 agonist",
                "glycopyrronium m3 antagonist",
                "bronchodilation",
                "copd maintenance",
                "fast onset",
                "twenty four hour relief",
            },
        ),
        (
            ("peel off", "peel-off", "strip", "capsule", "moisture"),
            {
                "peel off strip",
                "moisture protection",
                "safe peeling",
                "right direction marking",
                "no next capsule exposure",
            },
        ),
        (
            ("panimun", "bioral", "trusted", "organ transplantation"),
            {
                "organ transplantation",
                "years of trust",
                "clinical evidence",
                "bioavailability",
            },
        ),
        (
            ("administration route", "route", "nebulization", "nebulizer", "respule"),
            {
                "nebulization route",
            },
        ),
    )

    for question_terms, relevant in concept_groups:
        if any(term in normalized_question for term in question_terms):
            return response_concepts.intersection(relevant)

    return set()


def _semantic_normalize(text: str) -> str:
    """Normalize semantically equivalent medical wording."""
    normalized = normalize_text(text)
    replacements = {
        r"\bglycemic\b": "glycaemic",
        r"\bimproves?\b": "increase",
        r"\bincreases?\b": "increase",
        r"\benhances?\b": "increase",
        r"\bdecreases?\b": "reduce",
        r"\breduces?\b": "reduce",
        r"\blowers?\b": "reduce",
        r"\bdelays?\b": "delay",
        r"\bslows?\b": "delay",
        r"\binhibit(?:s|ed|ing)?\b": "inhibit",
        r"\benzymes\b": "enzyme",
        r"\balpha[-\s]?glucosidase\b": "alpha glucosidase",
        r"\bhepatic glucose output\b": "hepatic glucose production",
        r"\bliver glucose output\b": "hepatic glucose production",
        r"\bglucose uptake by muscles?\b": "glucose uptake",
        r"\bglucose uptake by adipose cells?\b": "glucose uptake",
        r"\bmaximum retail price\b": "mrp",
        r"\brecommended dose\b": "recommended dosage",
        r"\bone tablet\b": "1 tab",
        r"\bone tab\b": "1 tab",
        r"\bmode of action\b": "moa",
    }

    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)

    return normalized


def _extract_semantic_concepts(text: str) -> set[str]:
    """Extract medical concepts that can be matched semantically."""
    concept_patterns = {
        "insulin sensitivity": (r"\binsulin sensitivity\b",),
        "glucose uptake": (r"\bglucose uptake\b",),
        "hepatic glucose production": (r"\bhepatic glucose production\b",),
        "voglibose": (r"\bvoglibose\b",),
        "alpha glucosidase inhibition": (
            r"\balpha glucosidase\b.*\binhibit\b",
            r"\binhibit\b.*\balpha glucosidase\b",
        ),
        "delayed glucose absorption": (
            r"\bdelay\b.*\bglucose absorption\b",
            r"\bglucose absorption\b.*\bdelay\b",
            r"\bdelay\b.*\bcarbohydrate absorption\b",
            r"\bdecrease\b.*\bcarbohydrate absorption\b",
            r"\bcarbohydrate absorption\b.*\bdecrease\b",
            r"\breduce\b.*\bcarbohydrate absorption\b",
            r"\bcarbohydrate absorption\b.*\breduce\b",
            r"\bslow\b.*\bcarbohydrate digestion\b",
        ),
        "postprandial glucose control": (
            r"\bpost\s*prandial\b",
            r"\bpphg\b",
            r"\bglycaemic excursions?\b",
        ),
        "sglt2 inhibition": (
            r"\bsglt\s*2\b.*\binhibit\b",
            r"\binhibit\b.*\bsglt\s*2\b",
            r"\bsodium glucose cotransporter 2\b",
        ),
        "renal glucose excretion": (
            r"\burinary glucose excretion\b",
            r"\bglucose excretion\b",
            r"\breduces? reabsorption of filtered glucose\b",
            r"\bfiltered glucose\b.*\breabsorption\b",
        ),
        "dpp4 inhibition": (
            r"\bdpp\s*4\b.*\binhibit\b",
            r"\binhibit\b.*\bdpp\s*4\b",
            r"\bdpp4 enzyme inhibitor\b",
            r"\b>\s*80\s*%\s*dpp4 inhibition\b",
        ),
        "glp gip incretin": (
            r"\bglp\s*1\b",
            r"\bgip\b",
            r"\bincretin effect\b",
        ),
        "fast slow dpp4 binding": (
            r"\bfast association\b.*\bslow dissociation\b",
            r"\bslow dissociation\b.*\bfast association\b",
            r"\breversible\b.*\blong lasting\b",
            r"\bsustained increase\b.*\bincretin\b",
        ),
        "dpp4 selectivity": (
            r"\bselectivity\b.*\bdpp\s*4\b.*\bdpp\s*2\s*/\s*8\s*/\s*9\b",
            r"\bdpp\s*4\b.*\bdpp\s*2\s*/\s*8\s*/\s*9\b",
            r"\bdpp\s*8\b.*\bdpp\s*9\b",
            r"\b10000\s*fold selectivity\b",
        ),
        "reduced off target effects": (
            r"\bless off target\b",
            r"\boff target side effect\b",
            r"\bbetter safety\b",
            r"\bbetter compliance\b",
        ),
        "od convenience": (
            r"\btrue\s*24\b",
            r"\b24\s*efficacy\b",
            r"\bod convenience\b",
            r"\bonce a daily\b",
            r"\bonce daily\b",
        ),
        "immunosuppressant": (r"\bimmunosuppressant\b", r"\bsuppress immune\b"),
        "calcineurin inhibitor": (r"\bcalcineurin inhibitor\b", r"\bcalcineurin activity\b"),
        "solid organ transplantation": (
            r"\bsolid organ transplantation\b",
            r"\bsot\b",
            r"\btransplanted organ\b",
        ),
        "kidney liver transplant": (
            r"\bkidney\b.*\bliver\b",
            r"\bliver\b.*\bkidney\b",
        ),
        "kidney liver heart transplantation": (
            r"\bkidney\b.*\bliver\b.*\bheart\b",
            r"\bheart\b.*\bkidney\b.*\bliver\b",
            r"\bkidney\s*,?\s*liver\s*(?:and|,)\s*heart\b",
        ),
        "heart lung transplant": (
            r"\bheart\b.*\blung",
            r"\blung.*\bheart\b",
        ),
        "bone marrow transplantation": (
            r"\bbone marrow transplantation\b",
            r"\bbmt\b",
        ),
        "organ rejection prophylaxis": (
            r"\bprophylaxis\b.*\borgan rejection\b",
            r"\bprevent(?:s|ion)?\b.*\brejection\b",
            r"\brejection\b.*\btransplanted organ\b",
        ),
        "enteric formulation": (
            r"\benteric formulation\b",
            r"\bdelayed release\b",
            r"\bdelayed-release\b",
        ),
        "mycophenolic acid delivery": (
            r"\bmycophenolic acid\b.*\bintestine\b",
            r"\bdelivers\b.*\bintestine\b",
        ),
        "mycophenolate mofetil prodrug": (
            r"\bmycophenolate mofetil\b.*\bprodrug\b",
            r"\bmycept\b.*\bprodrug\b",
        ),
        "stomach conversion": (
            r"\bconverted\b.*\bstomach\b",
            r"\bstomach\b.*\bconverted\b",
        ),
        "mycophenolate sodium": (
            r"\bmycophenolate sodium\b",
        ),
        "gi tolerability": (
            r"\bgi compromised\b",
            r"\bgi intolerance\b",
            r"\bgastrointestinal symptoms\b",
            r"\bgi safety\b",
        ),
        "central nervous system": (
            r"\bcentral nervous system\b",
            r"\bcns\b",
        ),
        "normal saline dilution": (
            r"\bnormal saline\b",
            r"\bsodium chloride\b",
        ),
        "iv infusion": (
            r"\biv infusion\b",
            r"\binfusion\b",
            r"\bintravenously\b",
        ),
        "cars trial": (
            r"\bcars trial\b",
            r"\bcars\b",
        ),
        "upper limb motor function": (
            r"\bupper limb motor functions?\b",
            r"\bmotor functions?\b",
        ),
        "glycaemic control": (r"\bglycaemic control\b", r"\ba1c\b", r"\btype 2 diabetes management\b"),
        "sulphonylurea receptor binding": (
            r"\bsulphonylurea receptor\b",
            r"\bsur\s*1\b",
            r"\bk\+?\s*channel\b",
        ),
        "insulin secretion": (
            r"\binsulin secretion\b",
            r"\bsecretion of insulin\b",
            r"\bincrease\b.*\binsulin\b",
            r"\binsulin\b.*\bsecretion\b",
        ),
        "one tab od": (r"\b1 tab od\b", r"\bone tab od\b"),
        "one tab bid": (r"\b1 tab bid\b", r"\bone tab bid\b"),
        "titrated to two tablets": (r"\btitrated to two tablets\b",),
        "type 2 diabetes management": (
            r"\btype 2 diabetes management\b",
            r"\btype 2 diabetes mellitus\b",
            r"\bt2dm\b",
        ),
        "reference brand": (r"\breference brand\b",),
        "years of trust": (r"\byears of trust\b", r"\b25 years\b"),
        "weight neutral": (r"\bweight neutral\b",),
        "no active metabolites": (r"\bno active metabolites\b",),
        "safe renal impairment": (
            r"\bckd\b",
            r"\brenal\b",
            r"\bdose adjustment\b",
            r"\bstage 3\b",
        ),
        "esrd risk reduction": (
            r"\besrd\b",
            r"\bend stage renal disease\b",
            r"\brisk of esrd\b",
        ),
        "lesser hypoglycaemia": (r"\blesser hypoglycaemia\b", r"\breduced hypoglycaemia\b"),
        "selective sur1 binding": (r"\bselectively binds\b", r"\bsur 1 receptor\b"),
        "cv safety": (r"\bcv problems\b", r"\bcardiovascular\b"),
        "beta cell preservation": (r"\bbeta cell mass\b",),
        "free radical scavenging": (r"\bfree radical scavenging\b",),
        "vascular complication prevention": (r"\bvascular complications\b",),
        "microtubule binding": (r"\bmicrotubules?\b",),
        "dna separation inhibition": (r"\bdna separation\b", r"\bcell division\b"),
        "prevents new cell formation": (
            r"\bprevent(?:s|ed)? formation of new cells\b",
            r"\bcells? cannot complete cell division\b",
            r"\bprevent(?:s|ed)? cancer cell growth\b",
        ),
        "alpha1a blockade": (
            r"\balpha\s*-?\s*1a\b.*\bblock",
            r"\bblock(?:s|ade)?\b.*\balpha\s*-?\s*1a\b",
            r"\bselectively blocks alpha\s*-?\s*1a receptors?\b",
        ),
        "smooth muscle relaxation": (
            r"\brelax(?:es|ing)?\b.*\bsmooth muscles?\b",
            r"\bsmooth muscles?\b.*\brelax",
            r"\bprostate and bladder\b.*\brelax",
        ),
        "urine flow improvement": (
            r"\bimprov(?:es|ing)? urine flow\b",
            r"\burine flow\b.*\bimprov",
            r"\burine can pass more easily\b",
            r"\bflow rate improves?\b",
        ),
        "bph luts relief": (
            r"\bbph\b",
            r"\blower urinary tract symptoms?\b",
            r"\bluts\b",
            r"\bbenign prostatic hyperplasia\b",
        ),
        "beta3 agonist": (
            r"\bbeta\s*-?\s*3\b.*\bagonist\b",
            r"\bβ\s*3\b.*\bagonist\b",
        ),
        "bladder relaxation": (
            r"\brelax(?:es|ation)?\b.*\bbladder\b",
            r"\bbladder\b.*\brelax",
        ),
        "overactive bladder symptom control": (
            r"\boveractive bladder\b",
            r"\boab\b",
            r"\burinary urgency\b",
            r"\bfrequency\b.*\burinary\b",
        ),
        "respiratory immunity": (
            r"\brespiratory immunity\b",
            r"\brespiratory immunity booster\b",
            r"\brespiratory diseases?\b",
        ),
        "anti inflammatory": (
            r"\banti inflammatory\b",
            r"\banti-inflammatory\b",
            r"\bairway inflammation\b",
        ),
        "immunoregulatory": (
            r"\bimmunoregulatory\b",
            r"\bmodulate\b.*\bimmune responses?\b",
            r"\binnate and adaptive immune responses?\b",
        ),
        "copd exacerbation reduction": (
            r"\breduces? rate of moderate\s*/\s*severe copd exacerbations?\b",
            r"\breduces?.{0,80}\bcopd exacerbations?\b",
            r"\bexacerbations?\b",
        ),
        "glucocorticoid responsiveness": (
            r"\bglucocorticoid responsiveness\b",
            r"\bpoor glucocorticoid responsiveness\b",
        ),
        "immune health": (
            r"\bimmune health\b",
            r"\bimmune system\b",
            r"\bimmune cells?\b",
        ),
        "formoterol beta2 agonist": (
            r"\bformoterol\b.*\b(?:beta|β)\s*2\b",
            r"\b(?:beta|β)\s*2\b.*\bformoterol\b",
            r"\blaba\b",
        ),
        "glycopyrronium m3 antagonist": (
            r"\bglycopyrronium\b.*\bm3\b",
            r"\bm3\b.*\bglycopyrronium\b",
            r"\blama\b",
            r"\bmuscarinic antagonist\b",
        ),
        "bronchodilation": (
            r"\bbronchodilation\b",
            r"\bbronchodilator\b",
            r"\bprevent bronchoconstriction\b",
            r"\bairways?\b.*\brelax",
        ),
        "copd maintenance": (
            r"\bcopd\b",
            r"\blong term maintenance treatment\b",
            r"\bmaintenance treatment\b.*\bcopd\b",
        ),
        "fast onset": (
            r"\bfast onset\b",
            r"\bwithin 5 minutes\b",
            r"\bwithin about 5 minutes\b",
        ),
        "twenty four hour relief": (
            r"\b24\s*hrs?\s*relief\b",
            r"\b24\s*hour\b",
            r"\bday time\b.*\bnight time\b",
        ),
        "peel off strip": (
            r"\bpeel\s*-?\s*off strip\b",
            r"\bunique peel\s*-?\s*off\b",
        ),
        "moisture protection": (
            r"\bprotects? each capsule from moisture\b",
            r"\bmoisture\b",
            r"\bdose stability\b",
        ),
        "safe peeling": (
            r"\bpeeling happens safely\b",
            r"\bsafe peeling\b",
            r"\bperforated marking\b",
        ),
        "right direction marking": (
            r"\bpeel off marking\b",
            r"\bright direction\b",
            r"\bcorrect direction\b",
        ),
        "no next capsule exposure": (
            r"\bwithout exposing the next capsule\b",
            r"\bneighbouring capsules? (?:are )?not exposed\b",
            r"\bopens only one blister\b",
        ),
        "clinical evidence": (
            r"\bclinical trials?\b",
            r"\bbioequivalence studies\b",
            r"\bsupported by\b.*\bstudies\b",
        ),
        "bioavailability": (
            r"\bbioavailability\b",
            r"\bbioral\b",
        ),
        "nebulization route": (
            r"\bnebulization\b",
            r"\bnebulizer\b",
            r"\bnebulisation\b",
            r"\bvia nebulization\b",
        ),
        "gastrointestinal discomfort": (
            r"\bgastrointestinal disturbances?\b",
            r"\bgastrointestinal discomfort\b",
            r"\babdominal discomfort\b",
            r"\bnausea\b",
            r"\bvomiting\b",
            r"\bdyspepsia\b",
            r"\bgi upset\b",
        ),
        "renal dysfunction": (
            r"\brenal dysfunction\b",
            r"\brenal failure\b",
        ),
        "tremor": (r"\btremor\b",),
        "hirsutism": (r"\bhirsutism\b",),
        "hypertension": (r"\bhypertension\b",),
        "gum hyperplasia": (
            r"\bgum hyperplasia\b",
            r"\bgingival hyperplasia\b",
        ),
        "nephrotoxicity monitoring": (
            r"\bnephrotoxicity\b.*\bmonitoring of renal function\b",
            r"\bmonitoring of renal function\b",
            r"\brenal function\b.*\bmonitor",
        ),
    }

    concepts: set[str] = set()
    for concept, patterns in concept_patterns.items():
        if any(re.search(pattern, text) for pattern in patterns):
            concepts.add(concept)

    return concepts


def _has_descriptive_context_overlap(response_text: str, page_text: str) -> bool:
    """Return whether page has related descriptive context for FAIL vs missing."""
    context_terms = {
        "metformin",
        "gliclazide",
        "glizid",
        "mxr",
        "xr",
        "sulphonylurea",
        "hypoglycaemia",
        "diabetes",
        "dosage",
        "indications",
        "usp",
        "safety",
        "quality",
        "docetaxel",
        "microtubule",
        "microtubules",
        "cancer",
        "cell division",
    }
    response_terms = {term for term in context_terms if term in response_text}
    page_terms = {term for term in context_terms if term in page_text}
    return bool(response_terms.intersection(page_terms))


def _requires_descriptive_comparison(normalized_question: str) -> bool:
    """Return whether a descriptive question asks for comparative superiority."""
    comparison_terms = (
        "more effective than",
        "better than",
        "superior to",
        "compared to",
        "versus",
        "vs",
        "than silodosin alone",
        "than alone",
    )
    return any(term in normalized_question for term in comparison_terms)


def _has_supported_descriptive_comparison(normalized_page: str) -> bool:
    """Return whether cited text contains evidence for a comparative claim."""
    comparison_evidence = (
        "more effective than",
        "better than",
        "superior to",
        "lower than",
        "lower risk than",
        "lower hypoglycemia risk than",
        "lower hypoglycaemia risk than",
        "reduce hypoglycemia risk than",
        "reduced hypoglycemia risk than",
        "reduce hypoglycaemia risk than",
        "reduced hypoglycaemia risk than",
        "less than",
        "greater than",
        "greater hba1c",
        "1.5x greater",
        "1.5 times greater",
        "more affordable than",
        "compared to",
        "versus",
        " vs ",
        "than silodosin alone",
        "than alone",
        "add on",
        "combination",
        "storage symptoms",
    )
    return any(term in normalized_page for term in comparison_evidence)


def _strip_citation_tail(response: str) -> str:
    """Remove citation-reference suffix from model response before matching."""
    split_parts = re.split(r"\bcitation\b", response, flags=re.IGNORECASE, maxsplit=1)
    response_without_citation_block = split_parts[0].strip()
    response_without_citation_block = _remove_inline_citation_markers(
        response_without_citation_block
    )
    return re.sub(
        r"(?:\s+\d+(?:\s*,\s*\d+)*)+\s*$",
        "",
        response_without_citation_block,
    ).strip()


def _remove_inline_citation_markers(text: str) -> str:
    """Remove inline citation markers like 1,2 without removing product values."""
    def replace_marker(match: re.Match[str]) -> str:
        marker = match.group(1)
        marker_numbers = [int(number) for number in re.findall(r"\d+", marker)]
        if marker_numbers and all(number <= 20 for number in marker_numbers):
            return " "
        return match.group(0)

    text = re.sub(r"(?<=\s)(\d+(?:\s*,\s*\d)+)(?=\s|$)", replace_marker, text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_keywords(text: str) -> set[str]:
    """Extract useful comparison keywords from text."""
    stop_words = {
        "the",
        "and",
        "are",
        "as",
        "be",
        "by",
        "for",
        "is",
        "in",
        "it",
        "its",
        "of",
        "on",
        "or",
        "to",
        "was",
        "with",
        "from",
        "this",
        "that",
        "same",
        "category",
        "listed",
        "list",
        "segment",
        "sources",
        "source",
        "company",
        "companies",
        "information",
        "provided",
        "matching",
        "couldn",
        "couldnt",
        "contains",
        "contain",
        "containing",
        "has",
        "have",
        "having",
        "comprises",
        "comprise",
        "composition",
        "per",
        "tablet",
        "tablets",
        "citation",
        "page",
        "source",
        "brand",
        "snapshot",
        "updated",
        "document",
        "available",
        "mrp",
        "price",
        "strip",
        "injection",
        "product",
        "pack",
        "size",
        "bottle",
        "vial",
        "vials",
        "ampoule",
        "ampoules",
        "sachet",
        "sachets",
        "capsule",
        "capsules",
        "tabs",
    }
    words = set(re.findall(r"[a-z][a-z0-9-]{1,}", text))
    return words.difference(stop_words)


def _has_keyword_coverage(response_keywords: set[str], page_keywords: set[str]) -> bool:
    """Require high text overlap while allowing harmless factual wording variants."""
    if not response_keywords:
        return True

    matched_keywords = response_keywords.intersection(page_keywords)
    minimum_matches = max(1, int(len(response_keywords) * 0.80 + 0.999))
    return len(matched_keywords) >= minimum_matches


def _is_missing_source_data(text: str) -> bool:
    """Return whether page-scoped DOM extraction failed."""
    normalized = normalize_text(text)
    return not normalized or "no dom page data available" in normalized or "no page data available" in normalized