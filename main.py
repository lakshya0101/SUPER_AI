# """Question-answer validation test for Super AI."""

# import os
# import re

# from config.settings import OUTPUT_RESULTS_FILE, VALIDATION_QUESTIONS_FILE
# from pages.citation_page import CitationPage
# from utils.browser_manager import BrowserManager
# from utils.csv_handler import read_csv_rows, write_csv_rows
# from utils.helpers import capture_screenshot
# from utils.login_flow import login_to_super_ai
# from utils.logger import get_logger
# from utils.openai_validation_engine import (
#     get_openai_validation_status,
#     is_openai_validation_available,
#     validate_with_openai,
# )
# from utils.source_document_reader import is_weak_pdf_page_text
# from utils.validator import (
#     VALIDATION_LOG,
#     compare_ai_vs_pdf,
#     deterministic_numeric_validation,
#     explain_ai_vs_pdf,
#     extract_answer_values,
#     extract_citation_targets,
#     extract_citation_text,
#     extract_document_name,
#     extract_matching_values,
#     extract_page_number,
# )

# MAX_SUPER_AI_NO_MATCH_ATTEMPTS = 2
# MAX_KNOWLEDGE_CITATIONS_WITH_OPENAI = 6
# MAX_KNOWLEDGE_CITATIONS_WITH_FALLBACK = 6
# MIN_TOPIC_KEYWORD_MATCHES = 1


# def _result_row(
#     source_row: dict[str, str],
#     question: str,
#     response: str,
#     page_number: str | int,
#     document_data: str,
#     result: str,
#     reason: str,
#     citation_details: str = "",
#     matched_citation: str = "",
#     matched_document: str = "",
#     matched_page: str | int = "",
#     matched_evidence: str = "",
# ) -> dict[str, str | int]:
#     """Build the output CSV row using the requested report format."""
#     return {
#         "Product_Name": (
#             source_row.get("Product_Name")
#             or source_row.get("Product")
#             or source_row.get("Type")
#             or ""
#         ).strip(),
#         "Question": question,
#         "SuperAI_Response": response,
#         "Page_Number": page_number,
#         "Citation_Details": citation_details,
#         "Matched_Citation": matched_citation,
#         "Matched_Document": matched_document,
#         "Matched_Page": matched_page,
#         "Matched_Evidence": matched_evidence,
#         "Document_Data": document_data,
#         "Result": result,
#         "Reason": reason,
#     }


# def _citation_detail(citation_number: int, document_name: str, page_number: int) -> str:
#     """Return a compact citation audit record for output reports."""
#     return f"Citation {citation_number} | Document {document_name} | Page {page_number}"


# def _evidence_preview(text: str, limit: int = 1000) -> str:
#     """Keep matched evidence audit-friendly without making reports huge."""
#     cleaned = re.sub(r"\s+", " ", text or "").strip()
#     return cleaned[:limit]


# def _validation_reason(result: str, matched_values: str = "", detail: str = "") -> str:
#     """Return a short business-readable reason for the validation result."""
#     if result == "PASS":
#         return "Exact match found." if not matched_values else f"Matching value found: {matched_values}."
#     if result == "FAIL":
#         return detail or "Value found on cited page, but it does not match Super AI response."
#     return detail or "Required value not found in cited document/page."


# def _reason_contains_failure_contradiction(reason: str) -> bool:
#     """Detect unsafe PASS decisions where the explanation says the answer is wrong."""
#     normalized = (reason or "").lower()
#     failure_markers = (
#         "should be fail",
#         "should be fail, not pass",
#         "therefore this should be fail",
#         "contradicts the citation",
#         "contradicts the cited",
#         "superai answer does not match",
#         "does not match the computed",
#         "not matching superai",
#         "mismatch",
#     )
#     return any(marker in normalized for marker in failure_markers)


# def _validate_evidence_before_openai(
#     *,
#     document_opened: bool,
#     pdf_url: str,
#     page_number: int,
#     total_pages: int,
#     page_text: str,
#     product_name: str,
#     question: str,
# ) -> tuple[bool, str]:
#     """Return whether cited-page evidence is strong enough for validation."""
#     if not document_opened:
#         return False, "DOCUMENT_OPEN_FAILED: source document was not opened."

#     if not pdf_url.strip():
#         return False, "PDF_URL_NOT_CAPTURED: source PDF URL was not captured."

#     if page_number < 1 or page_number > total_pages:
#         return (
#             False,
#             f"INVALID_PAGE_NUMBER: requested {page_number}, total pages {total_pages}.",
#         )

#     if is_weak_pdf_page_text(page_text):
#         if not page_text.strip():
#             return (
#                 False,
#                 "PAGE_TEXT_EXTRACTION_FAILED: cited page text was empty — all extraction methods returned nothing.",
#             )
#         # Non-empty but short/sparse (image-based table with partial OCR or sparse layout).
#         # Pass to LLM for judgment rather than immediately returning DATA MISSING.
#         return (
#             True,
#             "WEAK_PAGE_TEXT_ACCEPTED: page may contain image-based tables; extracted text is partial.",
#         )

#     if not _page_text_matches_product_or_topic(page_text, product_name, question):
#         # Do not hard-stop — partial or image-based pages may still contain
#         # the answer in a table row, nearby row, or recoverable fragment.
#         # Pass to the LLM with a low-confidence flag instead of DATA MISSING.
#         return (
#             True,
#             "LOW_TOPIC_CONFIDENCE: cited page text does not clearly match product or topic — "
#             "attempting validation with partial evidence.",
#         )

#     return True, "EVIDENCE_OK"


# def _is_failed_citation_evidence(extracted_page: str) -> bool:
#     """Return whether a collected citation section is only an extraction/open failure."""
#     failure_markers = (
#         "DOCUMENT_OPEN_FAILED",
#         "PDF_NAVIGATION_FAILED",
#         "PAGE_TEXT_EXTRACTION_FAILED",
#         "INVALID_PAGE_NUMBER",
#         "PDF_URL_NOT_CAPTURED",
#         "WEAK_EVIDENCE",
#     )
#     return any(marker in extracted_page for marker in failure_markers)


# def _usable_citation_evidence_pages(extracted_pages: list[str]) -> list[str]:
#     """Return cited pages that contain meaningful text, ignoring hard failures.

#     Weak or partial pages (image-based tables, short OCR output) are included
#     rather than discarded — they may still hold recoverable table rows or
#     numeric values that the LLM can find via semantic recovery.
#     """
#     usable_pages: list[str] = []
#     for extracted_page in extracted_pages:
#         if _is_failed_citation_evidence(extracted_page):
#             continue
#         usable_pages.append(extracted_page)
#     return usable_pages


# def _page_text_matches_product_or_topic(
#     page_text: str,
#     product_name: str,
#     question: str,
# ) -> bool:
#     """Return whether page text is related to the product or question topic."""
#     normalized_page = _normalize_for_evidence_check(page_text)
#     product_tokens = _evidence_tokens(product_name)
#     question_tokens = _evidence_tokens(question)

#     if product_tokens and any(token in normalized_page for token in product_tokens):
#         return True

#     topic_matches = [token for token in question_tokens if token in normalized_page]
#     return len(topic_matches) >= MIN_TOPIC_KEYWORD_MATCHES


# def _evidence_tokens(text: str) -> list[str]:
#     """Return meaningful product/topic tokens for evidence relevance checks."""
#     stop_words = {
#         "what",
#         "which",
#         "why",
#         "how",
#         "does",
#         "with",
#         "from",
#         "that",
#         "this",
#         "were",
#         "was",
#         "and",
#         "the",
#         "for",
#         "according",
#         "compared",
#         "provide",
#         "provides",
#         "considered",
#         "patients",
#         "patient",
#         "therapy",
#         "treatment",
#     }
#     normalized = _normalize_for_evidence_check(text)
#     tokens = re.findall(r"[a-z0-9][a-z0-9-]{2,}", normalized)
#     return [token for token in tokens if token not in stop_words]


# def _normalize_for_evidence_check(text: str) -> str:
#     """Normalize text for lightweight evidence relevance checks."""
#     normalized = text.lower().replace("\u00a0", " ")
#     normalized = re.sub(r"[_./]+", " ", normalized)
#     normalized = re.sub(r"\s+", " ", normalized)
#     return normalized.strip()


# def _is_super_ai_no_match_response(response: str) -> bool:
#     """Return whether SuperAI gave an irrelevant or no-source answer."""
#     normalized_with_apostrophes = " ".join(
#         response.lower()
#         .replace("’", "'")
#         .replace("‘", "'")
#         .replace("`", "'")
#         .split()
#     )
#     normalized = normalized_with_apostrophes.replace("'", "")
#     normalized_loose = re.sub(r"[^a-z0-9]+", " ", response.lower()).strip()
#     no_match_phrases = (
#         "i can only help with queries regarding products and policies",
#         "can only help with queries regarding products and policies",
#         "only help with queries regarding products and policies",
#         "can only help with product and policy queries",
#         "outside the scope of products and policies",
#         "couldnt find any matching information",
#         "could not find any matching information",
#         "couldnt find the requested information",
#         "could not find the requested information",
#         "could not find any matching information in the provided sources",
#         "i could not find any matching information in the provided sources",
#         "i couldnt find any matching information in the provided sources",
#         "no matching information in the provided sources",
#         "no matching information was found",
#         "no matching source data",
#         "no relevant information was found",
#         "no information was found",
#         "i could not find",
#         "i couldnt find",
#         "i could not recognize",
#         "i couldnt recognize",
#         "could not recognize",
#         "couldnt recognize",
#         "unable to recognize",
#         "unable to find",
#         "not able to find",
#         "could not identify",
#         "couldnt identify",
#         "i do not have enough information",
#         "i don't have enough information",
#         "insufficient information",
#         "looks like something went wrong",
#         "something went wrong",
#         "please try again",
#         "error occurred",
#         "an error occurred",
#         "retry",
#     )
#     loose_no_match_phrases = (
#         "i couldn t find any matching information in the provided sources",
#         "couldn t find any matching information",
#         "looks like something went wrong retry",
#         "something went wrong retry",
#         "please try again",
#         "error occurred",
#     )
#     return any(phrase in normalized for phrase in no_match_phrases) or any(
#         phrase in normalized_loose for phrase in loose_no_match_phrases
#     )


# def _is_terminal_source_exhausted_response(response: str) -> bool:
#     """Return whether SuperAI says the provided sources have no matching data."""
#     normalized = re.sub(r"[^a-z0-9]+", " ", response.lower()).strip()
#     terminal_phrases = (
#         "i could not find any matching information in the provided sources",
#         "i couldn t find any matching information in the provided sources",
#         "i couldnt find any matching information in the provided sources",
#         "no matching information in the provided sources",
#         "no matching information was found",
#     )
#     return any(phrase in normalized for phrase in terminal_phrases)


# def _ask_question_with_limited_retries(super_ai_page, question: str, logger) -> tuple[str, int]:
#     """Ask a question up to two times if SuperAI returns no usable answer."""
#     response = ""
#     retry_source_exhausted = _should_retry_source_exhausted_response(question)

#     for attempt in range(1, MAX_SUPER_AI_NO_MATCH_ATTEMPTS + 1):
#         logger.info(
#             "Asking SuperAI attempt %s of %s",
#             attempt,
#             MAX_SUPER_AI_NO_MATCH_ATTEMPTS,
#         )
#         response = super_ai_page.ask_question(question)
#         logger.info("Super AI response attempt %s: %s", attempt, response)

#         if not _is_super_ai_no_match_response(response):
#             return response, attempt

#         if _is_terminal_source_exhausted_response(response) and not retry_source_exhausted:
#             logger.info(
#                 "SuperAI source-exhausted response detected; skipping retry and citation lookup."
#             )
#             return response, attempt

#         if attempt < MAX_SUPER_AI_NO_MATCH_ATTEMPTS:
#             logger.info(
#                 "SuperAI no-source/irrelevant response detected; retrying same question."
#             )
#         else:
#             logger.info(
#                 "SuperAI no-source/irrelevant response detected after final attempt."
#             )

#     return response, MAX_SUPER_AI_NO_MATCH_ATTEMPTS


# def _should_retry_source_exhausted_response(question: str) -> bool:
#     """Retry no-source responses for direct product price/MRP questions."""
#     normalized = question.lower()
#     retry_terms = (
#         "mrp",
#         "price",
#         "cost",
#         "per strip",
#         "strip",
#         "cheaper",
#         "saving",
#         "side effect",
#         "side effects",
#         "adverse",
#         "adverse effect",
#         "adverse effects",
#         "adverse reaction",
#         "adverse reactions",
#         "adverse event",
#         "adverse events",
#         "monitoring",
#         "precaution",
#         "precautions",
#         "nephrotoxicity",
#     )
#     return any(term in normalized for term in retry_terms)


# def _prioritize_citation_targets(
#     targets: list[dict[str, int | str]],
#     question: str,
#     product_name: str,
# ) -> list[dict[str, int | str]]:
#     """Try the most likely cited documents first without dropping any target."""
#     if _is_broad_knowledge_question(question):
#         return targets

#     normalized_question = question.lower()
#     normalized_product = product_name.lower()

#     def score(target: dict[str, int | str]) -> tuple[int, int]:
#         document_name = str(target.get("document_name") or "").lower()
#         citation_text = str(target.get("citation_text") or "").lower()
#         combined_text = f"{document_name} {citation_text}"
#         rank = 0

#         if any(term in normalized_question for term in ("mrp", "price")):
#             if "price master" in combined_text:
#                 rank -= 50
#             if "brand snapshot" in combined_text:
#                 rank += 20

#         for token in normalized_product.split():
#             if token and token in combined_text:
#                 rank -= 5

#         return rank, int(target.get("page_number") or 0)

#     return sorted(targets, key=score)


# def _dedupe_citation_targets(
#     targets: list[dict[str, int | str]],
# ) -> list[dict[str, int | str]]:
#     """Keep first occurrence of each document/page so duplicate citations are not reread."""
#     deduped_targets: list[dict[str, int | str]] = []
#     seen: set[tuple[str, int]] = set()

#     for target in targets:
#         try:
#             page_number = int(target.get("page_number") or 0)
#         except (TypeError, ValueError):
#             page_number = 0

#         document_name = str(target.get("document_name") or "").strip().lower()
#         citation_text = str(target.get("citation_text") or "").strip().lower()
#         document_key = document_name or citation_text
#         key = (document_key, page_number)

#         if key in seen:
#             continue

#         seen.add(key)
#         deduped_targets.append(target)

#     return deduped_targets


# def _is_competitor_brand_question(question: str) -> bool:
#     """Return whether the question needs brand-only competitor table validation."""
#     normalized = question.lower()
#     return "competitor" in normalized and "brand" in normalized


# def _is_dosage_question(question: str) -> bool:
#     """Return whether the question needs strict dosage normalization."""
#     normalized = question.lower()
#     return any(term in normalized for term in ("dosage", "dose", "recommended dosage"))


# def _is_rule_based_competitor_reasoning_question(question: str) -> bool:
#     """Return whether deterministic table math should be trusted before OpenAI."""
#     normalized = question.lower()
#     return "competitor" in normalized and any(
#         term in normalized
#         for term in (
#             "price",
#             "mrp",
#             "lowest",
#             "highest",
#             "cheapest",
#             "most expensive",
#             "between",
#             "how many",
#             "count",
#             "pack size",
#             "manufacturer",
#             "manufactures",
#             "company",
#             "percentage",
#             "saving",
#             "cost saving",
#         )
#     )


# def _should_use_numeric_first_validation(question: str) -> bool:
#     """Return whether numeric mismatch should decide before OpenAI review."""
#     normalized = question.lower()
#     strict_numeric_terms = (
#         "mrp",
#         "price",
#         "cost",
#         "cheaper",
#         "saving",
#         "percentage",
#         "difference",
#         "dosage",
#         "dose",
#         "strength",
#         "pack size",
#         "per strip",
#         "per tablet",
#         "per tab",
#         "per box",
#         "how many",
#         "composition",
#     )
#     descriptive_terms = (
#         "indicated",
#         "indication",
#         "conditions",
#         "why",
#         "how",
#         "mechanism",
#         "role",
#         "benefit",
#         "benefits",
#         "advantage",
#         "usp",
#         "range",
#         "molecules included",
#     )

#     if any(term in normalized for term in strict_numeric_terms):
#         return True

#     return not any(term in normalized for term in descriptive_terms)


# def _is_holistic_knowledge_question(question: str, response: str = "") -> bool:
#     """Return whether the answer needs claim-level validation across all citations."""
#     normalized_question = question.lower()
#     normalized_response = response.lower()
#     holistic_terms = (
#         "pitch",
#         "picth",
#         "positioning",
#         "position ",
#         "summary",
#         "summarize",
#         "overview",
#         "range",
#         "variants",
#         "variant",
#         "knowledge",
#         "talking point",
#         "call flow",
#         "key message",
#     )
#     if any(term in normalized_question for term in holistic_terms):
#         return True

#     citation_markers = len(re.findall(r"\(\s*\d+\s*\)|\b\d+\s*,\s*\d+\b", response))
#     bullet_like_lines = len(
#         [
#             line
#             for line in response.splitlines()
#             if line.strip().startswith(("-", "*", "•"))
#         ]
#     )
#     descriptive_terms = (
#         "brand trust",
#         "reference brand",
#         "weight neutral",
#         "hypoglycaemia",
#         "hypoglycemia",
#         "ckd",
#         "beta-cell",
#         "beta cell",
#         "salient",
#         "advantage",
#         "benefit",
#         "usp",
#     )
#     return (
#         bullet_like_lines >= 3
#         and citation_markers >= 2
#         and any(term in normalized_response for term in descriptive_terms)
#     )


# def _needs_multi_citation_claim_validation(question: str, response: str = "") -> bool:
#     """Return whether all cited pages should be merged before validation."""
#     normalized_question = question.lower()
#     normalized_response = response.lower()

#     if _is_holistic_knowledge_question(question, response):
#         return True

#     if not _is_broad_knowledge_question(question):
#         return False

#     citation_labels = re.findall(r"_page_\d+", response, flags=re.IGNORECASE)
#     cited_numbers = re.findall(r"\b\d+\s*,\s*\d+\b", response)
#     has_multiple_citations = len(citation_labels) >= 2 or bool(cited_numbers)
#     complex_terms = (
#         " and ",
#         "trial",
#         "trials",
#         "study",
#         "studies",
#         "evidence",
#         "according to",
#         "benefits",
#         "mechanism",
#         "combination",
#         "range",
#         "variant",
#         "variants",
#         "molecules included",
#         "molecules are included",
#         "guideline",
#         "protection",
#     )
#     named_evidence_terms = (
#         "dapa-hf",
#         "dapa hf",
#         "dapa-ckd",
#         "dapa ckd",
#         "cibis",
#         "additions",
#         "emphasis",
#         "ephesus",
#         "deliver",
#     )

#     return (
#         has_multiple_citations
#         and any(term in normalized_question for term in complex_terms)
#     ) or any(term in normalized_question or term in normalized_response for term in named_evidence_terms)


# def _is_broad_knowledge_question(question: str) -> bool:
#     """Return whether a question can be validated from enough cited support, not all cites."""
#     normalized = question.lower()
#     broad_terms = (
#         "why",
#         "how",
#         "benefit",
#         "benefits",
#         "evidence",
#         "supports",
#         "study",
#         "trial",
#         "guideline",
#         "different",
#         "preferred",
#         "protection",
#         "control",
#     )
#     strict_terms = (
#         "mrp",
#         "price",
#         "dosage",
#         "dose",
#         "composition",
#         "strength",
#         "pack size",
#         "lowest",
#         "highest",
#         "competitor",
#         "sku",
#     )
#     return any(term in normalized for term in broad_terms) and not any(
#         term in normalized for term in strict_terms
#     )


# def _should_combine_non_holistic_citations(question: str) -> bool:
#     """Return whether multiple cited pages should be evaluated together."""
#     normalized = question.lower()
#     combined_terms = (
#         "range",
#         "portfolio",
#         "variants",
#         "available",
#         "covered",
#         "categories",
#         "basket",
#         "included",
#         "which products",
#         "what products",
#         "competitor brands",
#         "all cited",
#     )
#     return _is_broad_knowledge_question(question) or any(
#         term in normalized for term in combined_terms
#     )


# def test_ask_questions_and_save_responses() -> None:
#     """Ask CSV questions one by one and save Super AI responses to CSV."""
#     logger = get_logger("test_ask_questions_and_save_responses")
#     browser_manager = BrowserManager()
#     page = None

#     try:
#         rows = [
#             row
#             for row in read_csv_rows(VALIDATION_QUESTIONS_FILE)
#             if (row.get("Question") or "").strip()
#         ]
#         question_limit = int(os.getenv("QUESTION_LIMIT", "0") or "0")
#         if question_limit > 0:
#             rows = rows[:question_limit]
#         results = []
#         page = browser_manager.launch_browser()
#         super_ai_page = login_to_super_ai(page)
#         citation_page = CitationPage(page)
#         openai_status = get_openai_validation_status()
#         use_openai_validation = is_openai_validation_available()
#         logger.info("OPENAI_VALIDATION_ACTIVE = %s", use_openai_validation)
#         logger.info("OPENAI_API_KEY_SET = %s", openai_status["api_key_set"])
#         logger.info("OPENAI_VALIDATION_MODEL = %s", openai_status["model"])
#         logger.info("OPENAI_VALIDATION_SCOPE = ALL_PRODUCTS")
#         logger.info("OPENAI_VALIDATION_STATUS = %s", openai_status["reason"])

#         for index, row in enumerate(rows, start=1):
#             question = (row.get("Question") or "").strip()
#             product_name = (
#                 row.get("Product_Name")
#                 or row.get("Product")
#                 or row.get("Type")
#                 or ""
#             ).strip()

#             if not question:
#                 logger.warning("Skipping row %s because Question is blank", index)
#                 results.append(
#                     _result_row(
#                         row,
#                         "",
#                         "QUESTION BLANK",
#                         "",
#                         "",
#                         "DATA MISSING",
#                         "Question is blank.",
#                     )
#                 )
#                 continue

#             logger.info("Processing question %s of %s", index, len(rows))
#             citation_page.close_citation_panel()
#             try:
#                 response, response_attempts = _ask_question_with_limited_retries(
#                     super_ai_page,
#                     question,
#                     logger,
#                 )
#             except TimeoutError as ask_exc:
#                 logger.exception("SuperAI response timed out for question %s: %s", index, ask_exc)
#                 results.append(
#                     _result_row(
#                         row,
#                         question,
#                         "SUPERAI_RESPONSE_TIMEOUT",
#                         "",
#                         "",
#                         "DATA MISSING",
#                         f"Timed out waiting for SuperAI response: {question}",
#                     )
#                 )
#                 continue
#             logger.info(
#                 "Super AI final response after %s attempt(s): %s",
#                 response_attempts,
#                 response,
#             )
#             page_number = ""
#             pdf_data = ""
#             validation_result = "DATA MISSING"
#             reason = "Required value not found in cited document/page."
#             citation_details = ""
#             matched_citation = ""
#             matched_document = ""
#             matched_page: str | int = ""
#             matched_evidence = ""

#             if _is_super_ai_no_match_response(response):
#                 logger.info(
#                     "SuperAI reported no matching source data; skipping citation fallback."
#                 )
#                 results.append(
#                     _result_row(
#                         row,
#                         question,
#                         response,
#                         "",
#                         "SUPERAI_NO_MATCH_RESPONSE",
#                         "DATA MISSING",
#                         (
#                             "SuperAI reported no matching/recognizable information "
#                             f"after {response_attempts} attempt(s)."
#                         ),
#                     )
#                 )
#                 continue

#             holistic_validation = (
#                 use_openai_validation
#                 and _needs_multi_citation_claim_validation(question, response)
#             )
#             if holistic_validation:
#                 logger.info(
#                     "MULTI_CITATION_CLAIM_VALIDATION_ENABLED: collecting all cited pages before final validation."
#                 )

#             try:
#                 citation_text = extract_citation_text(response)
#                 logger.info("Citation text: %s", citation_text or "NOT FOUND")

#                 citation_targets = extract_citation_targets(response)
#                 if not citation_targets:
#                     try:
#                         page_number = extract_page_number(response)
#                         citation_targets = [
#                             {
#                                 "citation_number": 1,
#                                 "page_number": page_number,
#                                 "document_name": extract_document_name(citation_text),
#                                 "citation_text": citation_text or f"Page_{page_number}",
#                             }
#                         ]
#                     except ValueError:
#                         citation_targets = citation_page.get_visible_citation_targets()
#                         if not citation_targets:
#                             citation_targets = citation_page.get_citation_targets_from_panels()

#                 if not citation_targets:
#                     logger.error("PAGE_NUMBER_EXTRACTION_FAILED")
#                     results.append(
#                         _result_row(
#                             row,
#                             question,
#                             response,
#                             "",
#                             "PAGE_NUMBER_EXTRACTION_FAILED",
#                             "DATA MISSING",
#                             "Citation page number could not be extracted.",
#                         )
#                     )
#                     continue

#                 citation_targets = _prioritize_citation_targets(
#                     citation_targets,
#                     question,
#                     product_name,
#                 )
#                 citation_targets = _dedupe_citation_targets(citation_targets)
#                 if _is_broad_knowledge_question(question):
#                     citation_limit = (
#                         MAX_KNOWLEDGE_CITATIONS_WITH_OPENAI
#                         if holistic_validation
#                         else MAX_KNOWLEDGE_CITATIONS_WITH_FALLBACK
#                     )
#                     if len(citation_targets) > citation_limit:
#                         logger.info(
#                             "Limiting broad knowledge validation citations from %s to %s for speed.",
#                             len(citation_targets),
#                             citation_limit,
#                         )
#                         citation_targets = citation_targets[:citation_limit]

#                 page_numbers_checked: list[str] = []
#                 extracted_pages: list[str] = []
#                 page_results: list[str] = []
#                 page_reasons: list[str] = []
#                 citation_details_checked: list[str] = []
#                 citation_audit_rows: list[dict[str, str | int]] = []
#                 first_pass_audit: dict[str, str | int] | None = None
#                 matched_citation = ""
#                 matched_document = ""
#                 VALIDATION_LOG.clear()
#                 matched_page: str | int = ""
#                 matched_evidence = ""

#                 logger.info("Extracted citation targets: %s", citation_targets)

#                 for audit_citation_number, target in enumerate(citation_targets, start=1):
#                     citation_number = int(target["citation_number"])
#                     page_number = int(target["page_number"])
#                     document_name = str(target.get("document_name") or "UNKNOWN DOCUMENT")
#                     target_citation_text = str(target["citation_text"])
#                     logger.info("Citation selected: %s", audit_citation_number)
#                     logger.info("Raw UI citation index used for click: %s", citation_number)
#                     logger.info("Citation text: %s", target_citation_text)
#                     logger.info("Document name: %s", document_name)
#                     logger.info("Extracted page number: %s", page_number)
#                     logger.info(
#                         "Searching citation %s page number %s",
#                         audit_citation_number,
#                         page_number,
#                     )

#                     page_numbers_checked.append(str(page_number))
#                     citation_details_checked.append(
#                         _citation_detail(audit_citation_number, document_name, page_number)
#                     )
#                     citation_page.target_page_number = page_number

#                     try:
#                         citation_page.open_citation_by_index(citation_number - 1)
#                         try:
#                             citation_page.open_source_document()
#                         except Exception as open_exc:
#                             logger.exception(
#                                 "DOCUMENT_OPEN_FAILED citation=%s document=%s error=%s",
#                                 citation_number,
#                                 document_name,
#                                 open_exc,
#                             )
#                             page_pdf_data = f"DOCUMENT_OPEN_FAILED: {open_exc}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("DATA MISSING")
#                             continue

#                         pdf_total_pages = citation_page.get_pdf_total_page_count()
#                         logger.info("PDF total page count: %s", pdf_total_pages)

#                         if page_number < 1 or page_number > pdf_total_pages:
#                             logger.error(
#                                 "INVALID_PAGE_NUMBER document=%s requested=%s total_pages=%s url=%s",
#                                 document_name,
#                                 page_number,
#                                 pdf_total_pages,
#                                 citation_page.source_url,
#                             )
#                             page_pdf_data = (
#                                 "INVALID_PAGE_NUMBER: "
#                                 f"requested {page_number}, total pages {pdf_total_pages}"
#                             )
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("INVALID_PAGE_NUMBER")
#                             continue

#                         logger.info("Page number requested for navigation: %s", page_number)

#                         try:
#                             citation_page.navigate_to_page(page_number)
#                         except Exception as nav_exc:
#                             logger.exception(
#                                 "PDF_NAVIGATION_FAILED citation=%s document=%s page=%s url=%s error=%s",
#                                 citation_number,
#                                 document_name,
#                                 page_number,
#                                 citation_page.source_url,
#                                 nav_exc,
#                             )
#                             page_pdf_data = f"PDF_NAVIGATION_FAILED: {nav_exc}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PDF_NAVIGATION_FAILED")
#                             continue

#                         current_pdf_page = citation_page.get_current_pdf_page_number()
#                         logger.info("Page navigation succeeded: %s", current_pdf_page == page_number)
#                         logger.info("Actual page opened after navigation: %s", current_pdf_page)

#                         if current_pdf_page != page_number:
#                             logger.error(
#                                 "PDF_NAVIGATION_FAILED document=%s expected=%s actual=%s url=%s",
#                                 document_name,
#                                 page_number,
#                                 current_pdf_page,
#                                 citation_page.source_url,
#                             )
#                             page_pdf_data = (
#                                 "PDF_NAVIGATION_FAILED: "
#                                 f"expected {page_number}, current {current_pdf_page}"
#                             )
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PDF_NAVIGATION_FAILED")
#                             continue

#                         try:
#                             page_pdf_data = citation_page.extract_page_data_from_pdf()
#                         except Exception as extract_exc:
#                             logger.exception(
#                                 "PAGE_TEXT_EXTRACTION_FAILED citation=%s document=%s page=%s url=%s error=%s",
#                                 citation_number,
#                                 document_name,
#                                 page_number,
#                                 citation_page.source_url,
#                                 extract_exc,
#                             )
#                             page_pdf_data = f"PAGE_TEXT_EXTRACTION_FAILED: {extract_exc}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PAGE_TEXT_EXTRACTION_FAILED")
#                             continue

#                         if not page_pdf_data.strip() or page_pdf_data == "NO PAGE DATA AVAILABLE":
#                             logger.error(
#                                 "PAGE_TEXT_EXTRACTION_FAILED document=%s page=%s url=%s preview=%s",
#                                 document_name,
#                                 page_number,
#                                 citation_page.source_url,
#                                 page_pdf_data[:200],
#                             )
#                             page_pdf_data = "PAGE_TEXT_EXTRACTION_FAILED"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PAGE_TEXT_EXTRACTION_FAILED")
#                             continue

#                         evidence_ok, evidence_reason = _validate_evidence_before_openai(
#                             document_opened=citation_page.source_page is not None,
#                             pdf_url=citation_page.source_url,
#                             page_number=page_number,
#                             total_pages=pdf_total_pages,
#                             page_text=page_pdf_data,
#                             product_name=product_name,
#                             question=question,
#                         )
#                         logger.info("Evidence quality status: %s", evidence_reason)

#                         if evidence_ok and (
#                             evidence_reason.startswith("WEAK_PAGE_TEXT_ACCEPTED")
#                             or evidence_reason.startswith("LOW_TOPIC_CONFIDENCE")
#                         ):
#                             logger.warning(
#                                 "PARTIAL_EVIDENCE citation=%s page=%s text_len=%s reason=%s — "
#                                 "searching all text for attribute before accepting DATA MISSING",
#                                 citation_number,
#                                 page_number,
#                                 len(page_pdf_data),
#                                 evidence_reason,
#                             )
#                             page_pdf_data = (
#                                 "[NOTE: OCR extraction of this PDF page is partial or incomplete "
#                                 "(likely an image-based table). "
#                                 "Do NOT immediately return DATA MISSING. Instead: "
#                                 "1) Search all available text for the requested attribute. "
#                                 "2) Search nearby rows and table structures for the value. "
#                                 "3) Look for numeric values, product names, or keywords in any form. "
#                                 "4) Attempt semantic recovery from partial or fragmented content. "
#                                 "Only return DATA MISSING if the attribute is truly absent from "
#                                 "all available text after exhausting all recovery attempts.]\n"
#                                 + page_pdf_data
#                             )

#                         if not evidence_ok:
#                             logger.error(
#                                 "EVIDENCE_QUALITY_FAILED citation=%s page=%s reason=%s",
#                                 citation_number,
#                                 page_number,
#                                 evidence_reason,
#                             )
#                             page_pdf_data = f"{evidence_reason} Extracted preview: {page_pdf_data[:300]}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("DATA MISSING")
#                             page_reasons.append(evidence_reason)
#                             continue

#                         answer_values = extract_answer_values(response)
#                         matched_values = extract_matching_values(response, page_pdf_data)
#                         logger.info("Cited page number used for validation: %s", page_number)
#                         logger.info("Extracted text from cited page %s: %s", page_number, page_pdf_data)
#                         logger.info("First 500 characters extracted from the page: %s", page_pdf_data[:500])
#                         logger.info("SuperAI values checked: %s", answer_values)
#                         logger.info("Final value found on the page: %s", matched_values or "NONE")
#                         logger.info("Value extracted from page: %s", matched_values or "NONE")
#                         logger.info("Super AI value: %s", answer_values or "NONE")

#                         if holistic_validation:
#                             logger.info(
#                                 "Citation %s collected for multi-citation claim-level validation.",
#                                 citation_number,
#                             )
#                             page_results.append("COLLECTED")
#                             page_reasons.append(
#                                 "Cited page collected for multi-citation claim-level validation."
#                             )
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "COLLECTED",
#                                 }
#                             )
#                             continue

#                         (
#                             numeric_applicable,
#                             numeric_result,
#                             numeric_reason,
#                             numeric_matched_values,
#                         ) = deterministic_numeric_validation(
#                             response,
#                             page_pdf_data,
#                             question,
#                         )
#                         fallback_page_result = compare_ai_vs_pdf(response, page_pdf_data, question)
#                         fallback_page_reason = explain_ai_vs_pdf(response, page_pdf_data, question)

#                         use_numeric_first = _should_use_numeric_first_validation(question)
#                         if numeric_applicable and use_numeric_first:
#                             logger.info(
#                                 "Using deterministic numeric validation result before OpenAI: %s",
#                                 numeric_result,
#                             )
#                             page_result = numeric_result
#                             page_reason = numeric_reason
#                             matched_values = numeric_matched_values or matched_values
#                         elif (
#                             fallback_page_result == "PASS"
#                             and (
#                                 _is_rule_based_competitor_reasoning_question(question)
#                                 or (numeric_applicable and use_numeric_first)
#                             )
#                         ):
#                             logger.info(
#                                 "Using deterministic validation PASS; skipping OpenAI for speed."
#                             )
#                             page_result = fallback_page_result
#                             page_reason = (
#                                 numeric_reason if numeric_applicable else fallback_page_reason
#                             )
#                             matched_values = numeric_matched_values or matched_values
#                         elif use_openai_validation:
#                             openai_decision = validate_with_openai(
#                                 question=question,
#                                 super_ai_response=response,
#                                 cited_page_text=page_pdf_data,
#                                 product_name=product_name,
#                                 page_number=page_number,
#                                 document_name=document_name,
#                             )
#                             if openai_decision.get("engine") == "openai":
#                                 page_result = str(openai_decision["result"])
#                                 page_reason = str(openai_decision["reason"])
#                                 if page_result == "PASS" and _reason_contains_failure_contradiction(page_reason):
#                                     logger.warning(
#                                         "OpenAI returned PASS but reason contains contradiction/failure wording. "
#                                         "Overriding to FAIL. Reason=%s",
#                                         page_reason,
#                                     )
#                                     page_result = "FAIL"
#                                 matched_values = str(
#                                     openai_decision.get("matched_value") or matched_values
#                                 )
#                                 logger.info(
#                                     "OpenAI requested attribute: %s",
#                                     openai_decision.get("requested_attribute") or "UNKNOWN",
#                                 )
#                                 logger.info(
#                                     "OpenAI SuperAI values: %s",
#                                     openai_decision.get("super_ai_values") or [],
#                                 )
#                                 logger.info(
#                                     "OpenAI document values: %s",
#                                     openai_decision.get("document_values") or [],
#                                 )
#                                 if (
#                                     (
#                                         _is_competitor_brand_question(question)
#                                         or _is_dosage_question(question)
#                                     )
#                                     and fallback_page_result == "PASS"
#                                     and page_result != "PASS"
#                                 ):
#                                     logger.warning(
#                                         "OpenAI/deterministic validator disagreement. "
#                                         "Using deterministic page-scoped PASS. OpenAI result=%s reason=%s",
#                                         page_result,
#                                         page_reason,
#                                     )
#                                     page_result = fallback_page_result
#                                     page_reason = fallback_page_reason
#                                     matched_values = extract_matching_values(
#                                         response,
#                                         page_pdf_data,
#                                     )
#                             else:
#                                 logger.warning(
#                                     "OpenAI validation unavailable; using rule-based fallback: %s",
#                                     openai_decision.get("reason"),
#                                 )
#                                 page_result = fallback_page_result
#                                 page_reason = fallback_page_reason
#                         else:
#                             page_result = fallback_page_result
#                             page_reason = fallback_page_reason
#                         logger.info(
#                             "Validation result for citation %s: %s",
#                             citation_number,
#                             page_result,
#                         )
#                         logger.info(
#                             "Validation reason for citation %s: %s",
#                             citation_number,
#                             page_reason,
#                         )
#                         page_results.append(page_result)
#                         page_reasons.append(page_reason)
#                         extracted_pages.append(
#                             (
#                                 f"Citation {audit_citation_number} | Document {document_name} | "
#                                 f"Page {page_number}: {page_pdf_data}"
#                             )
#                         )
#                         citation_audit_rows.append(
#                             {
#                                 "citation": audit_citation_number,
#                                 "document": document_name,
#                                 "page": page_number,
#                                 "evidence": page_pdf_data,
#                                 "result": page_result,
#                             }
#                         )

#                         if page_result == "PASS":
#                             validation_result = "PASS"
#                             reason = page_reason
#                             if first_pass_audit is None:
#                                 first_pass_audit = {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "reason": page_reason,
#                                 }
#                     finally:
#                         citation_page.close_source_document()
#                         citation_page.close_citation_panel()

#                 page_number = "; ".join(page_numbers_checked)
#                 citation_details = "\n".join(citation_details_checked)
#                 logger.info(
#                     "CITATION_AUDIT_SUMMARY processed=%s pass=%s fail=%s data_missing=%s",
#                     len(citation_audit_rows),
#                     page_results.count("PASS"),
#                     page_results.count("FAIL"),
#                     len(
#                         [
#                             result
#                             for result in page_results
#                             if result not in ("PASS", "FAIL", "COLLECTED")
#                         ]
#                     ),
#                 )
#                 if holistic_validation:
#                     all_pdf_data = "\n\n".join(extracted_pages)
#                     usable_extracted_pages = _usable_citation_evidence_pages(extracted_pages)
#                     usable_pdf_data = "\n\n".join(usable_extracted_pages)
#                     pdf_data = all_pdf_data
#                     logger.info(
#                         "HOLISTIC_USABLE_CITATIONS = %s of %s",
#                         len(usable_extracted_pages),
#                         len(extracted_pages),
#                     )
#                     if not extracted_pages:
#                         validation_result = "DATA MISSING"
#                         reason = "No cited page text was available for multi-citation claim-level validation."
#                     elif not usable_extracted_pages:
#                         validation_result = "DATA MISSING"
#                         reason = (
#                             "No usable cited page text was available; all cited sources failed "
#                             "to open, navigate, or extract meaningful text."
#                         )
#                     elif use_openai_validation:
#                         (
#                             numeric_applicable,
#                             numeric_result,
#                             numeric_reason,
#                             numeric_matched_values,
#                         ) = deterministic_numeric_validation(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         use_numeric_first = _should_use_numeric_first_validation(question)
#                         if numeric_applicable and use_numeric_first:
#                             validation_result = numeric_result
#                             reason = numeric_reason
#                             matched_citation = "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                             logger.info(
#                                 "Holistic deterministic numeric validation result before OpenAI: %s",
#                                 numeric_result,
#                             )
#                             logger.info(
#                                 "Holistic deterministic numeric matched values: %s",
#                                 numeric_matched_values or "NONE",
#                             )
#                             results.append(
#                                 _result_row(
#                                     row,
#                                     question,
#                                     response,
#                                     page_number,
#                                     all_pdf_data,
#                                     validation_result,
#                                     reason,
#                                     citation_details,
#                                     matched_citation,
#                                     matched_document,
#                                     matched_page,
#                                     matched_evidence,
#                                 )
#                             )
#                             continue
#                         holistic_decision = validate_with_openai(
#                             question=question,
#                             super_ai_response=response,
#                             cited_page_text=usable_pdf_data,
#                             product_name=product_name,
#                             page_number=page_number,
#                             document_name="MULTIPLE CITED SOURCES",
#                         )
#                         if holistic_decision.get("engine") == "openai":
#                             validation_result = str(holistic_decision["result"])
#                             reason = str(holistic_decision["reason"])
#                             if validation_result == "PASS" and _reason_contains_failure_contradiction(reason):
#                                 logger.warning(
#                                     "OpenAI returned holistic PASS but reason contains contradiction/failure wording. "
#                                     "Overriding to FAIL. Reason=%s",
#                                     reason,
#                                 )
#                                 validation_result = "FAIL"
#                             matched_citation = "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(
#                                 str(holistic_decision.get("matched_value") or "")
#                                 or usable_pdf_data
#                             )
#                             logger.info(
#                                 "Holistic OpenAI requested attribute: %s",
#                                 holistic_decision.get("requested_attribute") or "KNOWLEDGE_MODE",
#                             )
#                             logger.info(
#                                 "Holistic OpenAI SuperAI values/claims: %s",
#                                 holistic_decision.get("super_ai_values") or [],
#                             )
#                             logger.info(
#                                 "Holistic OpenAI document values/evidence: %s",
#                                 holistic_decision.get("document_values") or [],
#                             )
#                         else:
#                             fallback_result = compare_ai_vs_pdf(
#                                 response,
#                                 usable_pdf_data,
#                                 question,
#                             )
#                             validation_result = fallback_result
#                             reason = explain_ai_vs_pdf(
#                                 response,
#                                 usable_pdf_data,
#                                 question,
#                             )
#                             if validation_result == "DATA MISSING":
#                                 reason = (
#                                     "Multi-citation OpenAI validation could not run: "
#                                     f"{holistic_decision.get('reason')}. "
#                                     f"Rule-based fallback result: {reason}"
#                                 )
#                             matched_citation = (
#                                 "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                             )
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                     else:
#                         validation_result = compare_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         reason = explain_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         if validation_result == "DATA MISSING":
#                             reason = (
#                                 "OpenAI validation is unavailable; rule-based fallback "
#                                 f"could not fully validate the cited evidence. {reason}"
#                             )
#                         matched_citation = (
#                             "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                         )
#                         matched_document = "MULTIPLE CITED SOURCES"
#                         matched_page = page_number
#                         matched_evidence = _evidence_preview(usable_pdf_data)
#                 elif validation_result == "PASS" and first_pass_audit is not None:
#                     pdf_data = "\n\n".join(extracted_pages)
#                     matched_citation = f"Citation {first_pass_audit['citation']}"
#                     matched_document = str(first_pass_audit["document"])
#                     matched_page = first_pass_audit["page"]
#                     matched_evidence = _evidence_preview(str(first_pass_audit["evidence"]))
#                     reason = str(first_pass_audit["reason"])
#                 elif validation_result != "PASS":
#                     pdf_data = "\n\n".join(extracted_pages)
#                     usable_extracted_pages = _usable_citation_evidence_pages(extracted_pages)
#                     usable_pdf_data = "\n\n".join(usable_extracted_pages)
#                     if len(usable_extracted_pages) > 1 and _should_combine_non_holistic_citations(
#                         question
#                     ):
#                         logger.info(
#                             "Running combined-citation validation for non-holistic question using %s cited pages.",
#                             len(usable_extracted_pages),
#                         )
#                         combined_result = compare_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         combined_reason = explain_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         logger.info(
#                             "Combined-citation validation result: %s | reason: %s",
#                             combined_result,
#                             combined_reason,
#                         )
#                         if combined_result == "PASS":
#                             validation_result = "PASS"
#                             reason = combined_reason
#                             matched_citation = "MULTIPLE"
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                         elif combined_result == "FAIL":
#                             validation_result = "FAIL"
#                             reason = combined_reason
#                             matched_citation = "MULTIPLE"
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                         else:
#                             validation_result = "DATA MISSING"
#                             reason = combined_reason
#                             matched_citation = "MULTIPLE"
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                     elif "FAIL" in page_results:
#                         validation_result = "FAIL"
#                         fail_index = page_results.index("FAIL")
#                         reason = page_reasons[fail_index] if fail_index < len(page_reasons) else _validation_reason("FAIL")
#                         if fail_index < len(citation_audit_rows):
#                             failed_audit = citation_audit_rows[fail_index]
#                             matched_citation = f"Citation {failed_audit['citation']}"
#                             matched_document = str(failed_audit["document"])
#                             matched_page = failed_audit["page"]
#                             matched_evidence = _evidence_preview(str(failed_audit["evidence"]))
#                     elif page_results:
#                         validation_result = "DATA MISSING"
#                         reason = page_reasons[-1] if page_reasons else _validation_reason("DATA MISSING")
#                         if citation_audit_rows:
#                             last_audit = citation_audit_rows[-1]
#                             matched_citation = f"Citation {last_audit['citation']}"
#                             matched_document = str(last_audit["document"])
#                             matched_page = last_audit["page"]
#                             matched_evidence = _evidence_preview(str(last_audit["evidence"]))
#                     else:
#                         validation_result = "DATA MISSING"
#                         reason = "Citation page number could not be extracted."

#             except Exception as question_exc:
#                 logger.exception(
#                     "Validation failed for question %s: %s",
#                     index,
#                     question_exc,
#                 )
#                 pdf_data = f"VALIDATION ERROR: {question_exc}"
#                 validation_result = "DATA MISSING"
#                 reason = f"Validation error: {question_exc}"
#                 citation_page.close_source_document()

#             results.append(
#                 _result_row(
#                     row,
#                     question,
#                     response,
#                     page_number,
#                     pdf_data,
#                     validation_result,
#                     reason,
#                     citation_details,
#                     matched_citation,
#                     matched_document,
#                     matched_page,
#                     matched_evidence,
#                 )
#             )

#         output_report_path = write_csv_rows(OUTPUT_RESULTS_FILE, results)
#         if output_report_path:
#             logger.info("Responses saved to %s", output_report_path)

#     except Exception as exc:
#         logger.exception("Question validation test failed: %s", exc)

#         if page:
#             screenshot_path = capture_screenshot(page, "question_failure")
#             logger.error("Failure screenshot captured: %s", screenshot_path)

#         raise

#     finally:
#         browser_manager.close_browser()


# if __name__ == "__main__":
#     test_ask_questions_and_save_responses()

#####################  =======================


# """Question-answer validation test for Super AI."""

# import os
# import re

# from config.settings import OUTPUT_RESULTS_FILE, VALIDATION_QUESTIONS_FILE
# from pages.citation_page import CitationPage
# from utils.browser_manager import BrowserManager
# from utils.csv_handler import read_csv_rows, write_csv_rows
# from utils.helpers import capture_screenshot
# from utils.login_flow import login_to_super_ai
# from utils.logger import get_logger
# from utils.openai_validation_engine import (
#     get_openai_validation_status,
#     is_openai_validation_available,
#     validate_with_openai,
# )
# from utils.source_document_reader import is_weak_pdf_page_text
# from utils.validator import (
#     VALIDATION_LOG,
#     compare_ai_vs_pdf,
#     deterministic_numeric_validation,
#     explain_ai_vs_pdf,
#     extract_answer_values,
#     extract_citation_targets,
#     extract_citation_text,
#     extract_document_name,
#     extract_matching_values,
#     extract_page_number,
# )

# MAX_SUPER_AI_NO_MATCH_ATTEMPTS = 2
# MAX_KNOWLEDGE_CITATIONS_WITH_OPENAI = 6
# MAX_KNOWLEDGE_CITATIONS_WITH_FALLBACK = 6
# MIN_TOPIC_KEYWORD_MATCHES = 1


# def _result_row(
#     source_row: dict[str, str],
#     question: str,
#     response: str,
#     page_number: str | int,
#     document_data: str,
#     result: str,
#     reason: str,
#     citation_details: str = "",
#     matched_citation: str = "",
#     matched_document: str = "",
#     matched_page: str | int = "",
#     matched_evidence: str = "",
# ) -> dict[str, str | int]:
#     """Build the output CSV row using the requested report format."""
#     return {
#         "Product_Name": (
#             source_row.get("Product_Name")
#             or source_row.get("Product")
#             or source_row.get("Type")
#             or ""
#         ).strip(),
#         "Question": question,
#         "SuperAI_Response": response,
#         "Page_Number": page_number,
#         "Citation_Details": citation_details,
#         "Matched_Citation": matched_citation,
#         "Matched_Document": matched_document,
#         "Matched_Page": matched_page,
#         "Matched_Evidence": matched_evidence,
#         "Document_Data": document_data,
#         "Result": result,
#         "Reason": reason,
#     }


# def _citation_detail(citation_number: int, document_name: str, page_number: int) -> str:
#     """Return a compact citation audit record for output reports."""
#     return f"Citation {citation_number} | Document {document_name} | Page {page_number}"


# def _evidence_preview(text: str, limit: int = 1000) -> str:
#     """Keep matched evidence audit-friendly without making reports huge."""
#     cleaned = re.sub(r"\s+", " ", text or "").strip()
#     return cleaned[:limit]


# def _validation_reason(result: str, matched_values: str = "", detail: str = "") -> str:
#     """Return a short business-readable reason for the validation result."""
#     if result == "PASS":
#         return "Exact match found." if not matched_values else f"Matching value found: {matched_values}."
#     if result == "FAIL":
#         return detail or "Value found on cited page, but it does not match Super AI response."
#     return detail or "Required value not found in cited document/page."


# def _reason_contains_failure_contradiction(reason: str) -> bool:
#     """Detect unsafe PASS decisions where the explanation says the answer is wrong."""
#     normalized = (reason or "").lower()
#     failure_markers = (
#         "should be fail",
#         "should be fail, not pass",
#         "therefore this should be fail",
#         "contradicts the citation",
#         "contradicts the cited",
#         "superai answer does not match",
#         "does not match the computed",
#         "not matching superai",
#         "mismatch",
#     )
#     return any(marker in normalized for marker in failure_markers)


# def _validate_evidence_before_openai(
#     *,
#     document_opened: bool,
#     pdf_url: str,
#     page_number: int,
#     total_pages: int,
#     page_text: str,
#     product_name: str,
#     question: str,
# ) -> tuple[bool, str]:
#     """Return whether cited-page evidence is strong enough for validation."""
#     if not document_opened:
#         return False, "DOCUMENT_OPEN_FAILED: source document was not opened."

#     if not pdf_url.strip():
#         return False, "PDF_URL_NOT_CAPTURED: source PDF URL was not captured."

#     if page_number < 1 or page_number > total_pages:
#         return (
#             False,
#             f"INVALID_PAGE_NUMBER: requested {page_number}, total pages {total_pages}.",
#         )

#     if is_weak_pdf_page_text(page_text):
#         if not page_text.strip():
#             return (
#                 False,
#                 "PAGE_TEXT_EXTRACTION_FAILED: cited page text was empty — all extraction methods returned nothing.",
#             )
#         # Non-empty but short/sparse (image-based table with partial OCR or sparse layout).
#         # Pass to LLM for judgment rather than immediately returning DATA MISSING.
#         return (
#             True,
#             "WEAK_PAGE_TEXT_ACCEPTED: page may contain image-based tables; extracted text is partial.",
#         )

#     if not _page_text_matches_product_or_topic(page_text, product_name, question):
#         # Do not hard-stop — partial or image-based pages may still contain
#         # the answer in a table row, nearby row, or recoverable fragment.
#         # Pass to the LLM with a low-confidence flag instead of DATA MISSING.
#         return (
#             True,
#             "LOW_TOPIC_CONFIDENCE: cited page text does not clearly match product or topic — "
#             "attempting validation with partial evidence.",
#         )

#     return True, "EVIDENCE_OK"


# def _is_failed_citation_evidence(extracted_page: str) -> bool:
#     """Return whether a collected citation section is only an extraction/open failure."""
#     failure_markers = (
#         "DOCUMENT_OPEN_FAILED",
#         "PDF_NAVIGATION_FAILED",
#         "PAGE_TEXT_EXTRACTION_FAILED",
#         "INVALID_PAGE_NUMBER",
#         "PDF_URL_NOT_CAPTURED",
#         "WEAK_EVIDENCE",
#     )
#     return any(marker in extracted_page for marker in failure_markers)


# def _usable_citation_evidence_pages(extracted_pages: list[str]) -> list[str]:
#     """Return cited pages that contain meaningful text, ignoring hard failures.

#     Weak or partial pages (image-based tables, short OCR output) are included
#     rather than discarded — they may still hold recoverable table rows or
#     numeric values that the LLM can find via semantic recovery.
#     """
#     usable_pages: list[str] = []
#     for extracted_page in extracted_pages:
#         if _is_failed_citation_evidence(extracted_page):
#             continue
#         usable_pages.append(extracted_page)
#     return usable_pages


# def _page_text_matches_product_or_topic(
#     page_text: str,
#     product_name: str,
#     question: str,
# ) -> bool:
#     """Return whether page text is related to the product or question topic."""
#     normalized_page = _normalize_for_evidence_check(page_text)
#     product_tokens = _evidence_tokens(product_name)
#     question_tokens = _evidence_tokens(question)

#     if product_tokens and any(token in normalized_page for token in product_tokens):
#         return True

#     topic_matches = [token for token in question_tokens if token in normalized_page]
#     return len(topic_matches) >= MIN_TOPIC_KEYWORD_MATCHES


# def _evidence_tokens(text: str) -> list[str]:
#     """Return meaningful product/topic tokens for evidence relevance checks."""
#     stop_words = {
#         "what",
#         "which",
#         "why",
#         "how",
#         "does",
#         "with",
#         "from",
#         "that",
#         "this",
#         "were",
#         "was",
#         "and",
#         "the",
#         "for",
#         "according",
#         "compared",
#         "provide",
#         "provides",
#         "considered",
#         "patients",
#         "patient",
#         "therapy",
#         "treatment",
#     }
#     normalized = _normalize_for_evidence_check(text)
#     tokens = re.findall(r"[a-z0-9][a-z0-9-]{2,}", normalized)
#     return [token for token in tokens if token not in stop_words]


# def _normalize_for_evidence_check(text: str) -> str:
#     """Normalize text for lightweight evidence relevance checks."""
#     normalized = text.lower().replace("\u00a0", " ")
#     normalized = re.sub(r"[_./]+", " ", normalized)
#     normalized = re.sub(r"\s+", " ", normalized)
#     return normalized.strip()


# def _is_super_ai_no_match_response(response: str) -> bool:
#     """Return whether SuperAI gave an irrelevant or no-source answer."""
#     normalized_with_apostrophes = " ".join(
#         response.lower()
#         .replace("’", "'")
#         .replace("‘", "'")
#         .replace("`", "'")
#         .split()
#     )
#     normalized = normalized_with_apostrophes.replace("'", "")
#     normalized_loose = re.sub(r"[^a-z0-9]+", " ", response.lower()).strip()
#     no_match_phrases = (
#         "i can only help with queries regarding products and policies",
#         "can only help with queries regarding products and policies",
#         "only help with queries regarding products and policies",
#         "can only help with product and policy queries",
#         "outside the scope of products and policies",
#         "couldnt find any matching information",
#         "could not find any matching information",
#         "couldnt find the requested information",
#         "could not find the requested information",
#         "could not find any matching information in the provided sources",
#         "i could not find any matching information in the provided sources",
#         "i couldnt find any matching information in the provided sources",
#         "no matching information in the provided sources",
#         "no matching information was found",
#         "no matching source data",
#         "no relevant information was found",
#         "no information was found",
#         "i could not find",
#         "i couldnt find",
#         "i could not recognize",
#         "i couldnt recognize",
#         "could not recognize",
#         "couldnt recognize",
#         "unable to recognize",
#         "unable to find",
#         "not able to find",
#         "could not identify",
#         "couldnt identify",
#         "i do not have enough information",
#         "i don't have enough information",
#         "insufficient information",
#         "looks like something went wrong",
#         "something went wrong",
#         "please try again",
#         "error occurred",
#         "an error occurred",
#         "retry",
#     )
#     loose_no_match_phrases = (
#         "i couldn t find any matching information in the provided sources",
#         "couldn t find any matching information",
#         "looks like something went wrong retry",
#         "something went wrong retry",
#         "please try again",
#         "error occurred",
#     )
#     return any(phrase in normalized for phrase in no_match_phrases) or any(
#         phrase in normalized_loose for phrase in loose_no_match_phrases
#     )


# def _is_terminal_source_exhausted_response(response: str) -> bool:
#     """Return whether SuperAI says the provided sources have no matching data."""
#     normalized = re.sub(r"[^a-z0-9]+", " ", response.lower()).strip()
#     terminal_phrases = (
#         "i could not find any matching information in the provided sources",
#         "i couldn t find any matching information in the provided sources",
#         "i couldnt find any matching information in the provided sources",
#         "no matching information in the provided sources",
#         "no matching information was found",
#     )
#     return any(phrase in normalized for phrase in terminal_phrases)


# def _ask_question_with_limited_retries(super_ai_page, question: str, logger) -> tuple[str, int]:
#     """Ask a question up to two times if SuperAI returns no usable answer."""
#     response = ""
#     retry_source_exhausted = _should_retry_source_exhausted_response(question)

#     for attempt in range(1, MAX_SUPER_AI_NO_MATCH_ATTEMPTS + 1):
#         logger.info(
#             "Asking SuperAI attempt %s of %s",
#             attempt,
#             MAX_SUPER_AI_NO_MATCH_ATTEMPTS,
#         )
#         response = super_ai_page.ask_question(question)
#         logger.info("Super AI response attempt %s: %s", attempt, response)

#         if not _is_super_ai_no_match_response(response):
#             return response, attempt

#         if _is_terminal_source_exhausted_response(response) and not retry_source_exhausted:
#             logger.info(
#                 "SuperAI source-exhausted response detected; skipping retry and citation lookup."
#             )
#             return response, attempt

#         if attempt < MAX_SUPER_AI_NO_MATCH_ATTEMPTS:
#             logger.info(
#                 "SuperAI no-source/irrelevant response detected; retrying same question."
#             )
#         else:
#             logger.info(
#                 "SuperAI no-source/irrelevant response detected after final attempt."
#             )

#     return response, MAX_SUPER_AI_NO_MATCH_ATTEMPTS


# def _should_retry_source_exhausted_response(question: str) -> bool:
#     """Retry no-source responses for direct product price/MRP questions."""
#     normalized = question.lower()
#     retry_terms = (
#         "mrp",
#         "price",
#         "cost",
#         "per strip",
#         "strip",
#         "cheaper",
#         "saving",
#         "side effect",
#         "side effects",
#         "adverse",
#         "adverse effect",
#         "adverse effects",
#         "adverse reaction",
#         "adverse reactions",
#         "adverse event",
#         "adverse events",
#         "monitoring",
#         "precaution",
#         "precautions",
#         "nephrotoxicity",
#     )
#     return any(term in normalized for term in retry_terms)


# def _prioritize_citation_targets(
#     targets: list[dict[str, int | str]],
#     question: str,
#     product_name: str,
# ) -> list[dict[str, int | str]]:
#     """Try the most likely cited documents first without dropping any target."""
#     if _is_broad_knowledge_question(question):
#         return targets

#     normalized_question = question.lower()
#     normalized_product = product_name.lower()

#     def score(target: dict[str, int | str]) -> tuple[int, int]:
#         document_name = str(target.get("document_name") or "").lower()
#         citation_text = str(target.get("citation_text") or "").lower()
#         combined_text = f"{document_name} {citation_text}"
#         rank = 0

#         if any(term in normalized_question for term in ("mrp", "price")):
#             if "price master" in combined_text:
#                 rank -= 50
#             if "brand snapshot" in combined_text:
#                 rank += 20

#         for token in normalized_product.split():
#             if token and token in combined_text:
#                 rank -= 5

#         return rank, int(target.get("page_number") or 0)

#     return sorted(targets, key=score)


# def _dedupe_citation_targets(
#     targets: list[dict[str, int | str]],
# ) -> list[dict[str, int | str]]:
#     """Keep first occurrence of each document/page so duplicate citations are not reread."""
#     deduped_targets: list[dict[str, int | str]] = []
#     seen: set[tuple[str, int]] = set()

#     for target in targets:
#         try:
#             page_number = int(target.get("page_number") or 0)
#         except (TypeError, ValueError):
#             page_number = 0

#         document_name = str(target.get("document_name") or "").strip().lower()
#         citation_text = str(target.get("citation_text") or "").strip().lower()
#         document_key = document_name or citation_text
#         key = (document_key, page_number)

#         if key in seen:
#             continue

#         seen.add(key)
#         deduped_targets.append(target)

#     return deduped_targets


# def _is_competitor_brand_question(question: str) -> bool:
#     """Return whether the question needs brand-only competitor table validation."""
#     normalized = question.lower()
#     return "competitor" in normalized and "brand" in normalized


# def _is_dosage_question(question: str) -> bool:
#     """Return whether the question needs strict dosage normalization."""
#     normalized = question.lower()
#     return any(term in normalized for term in ("dosage", "dose", "recommended dosage"))


# def _is_rule_based_competitor_reasoning_question(question: str) -> bool:
#     """Return whether deterministic table math should be trusted before OpenAI."""
#     normalized = question.lower()
#     return "competitor" in normalized and any(
#         term in normalized
#         for term in (
#             "price",
#             "mrp",
#             "lowest",
#             "highest",
#             "cheapest",
#             "most expensive",
#             "between",
#             "how many",
#             "count",
#             "pack size",
#             "manufacturer",
#             "manufactures",
#             "company",
#             "percentage",
#             "saving",
#             "cost saving",
#         )
#     )


# def _should_use_numeric_first_validation(question: str) -> bool:
#     """Return whether numeric mismatch should decide before OpenAI review."""
#     normalized = question.lower()
#     strict_numeric_terms = (
#         "mrp",
#         "price",
#         "cost",
#         "cheaper",
#         "saving",
#         "percentage",
#         "difference",
#         "dosage",
#         "dose",
#         "strength",
#         "pack size",
#         "per strip",
#         "per tablet",
#         "per tab",
#         "per box",
#         "how many",
#         "composition",
#     )
#     descriptive_terms = (
#         "indicated",
#         "indication",
#         "conditions",
#         "why",
#         "how",
#         "mechanism",
#         "role",
#         "benefit",
#         "benefits",
#         "advantage",
#         "usp",
#         "range",
#         "molecules included",
#     )

#     if any(term in normalized for term in strict_numeric_terms):
#         return True

#     return not any(term in normalized for term in descriptive_terms)


# def _is_holistic_knowledge_question(question: str, response: str = "") -> bool:
#     """Return whether the answer needs claim-level validation across all citations."""
#     normalized_question = question.lower()
#     normalized_response = response.lower()
#     holistic_terms = (
#         "pitch",
#         "picth",
#         "positioning",
#         "position ",
#         "summary",
#         "summarize",
#         "overview",
#         "range",
#         "variants",
#         "variant",
#         "knowledge",
#         "talking point",
#         "call flow",
#         "key message",
#     )
#     if any(term in normalized_question for term in holistic_terms):
#         return True

#     citation_markers = len(re.findall(r"\(\s*\d+\s*\)|\b\d+\s*,\s*\d+\b", response))
#     bullet_like_lines = len(
#         [
#             line
#             for line in response.splitlines()
#             if line.strip().startswith(("-", "*", "•"))
#         ]
#     )
#     descriptive_terms = (
#         "brand trust",
#         "reference brand",
#         "weight neutral",
#         "hypoglycaemia",
#         "hypoglycemia",
#         "ckd",
#         "beta-cell",
#         "beta cell",
#         "salient",
#         "advantage",
#         "benefit",
#         "usp",
#     )
#     return (
#         bullet_like_lines >= 3
#         and citation_markers >= 2
#         and any(term in normalized_response for term in descriptive_terms)
#     )


# def _needs_multi_citation_claim_validation(question: str, response: str = "") -> bool:
#     """Return whether all cited pages should be merged before validation."""
#     normalized_question = question.lower()
#     normalized_response = response.lower()

#     if _is_holistic_knowledge_question(question, response):
#         return True

#     if not _is_broad_knowledge_question(question):
#         return False

#     citation_labels = re.findall(r"_page_\d+", response, flags=re.IGNORECASE)
#     cited_numbers = re.findall(r"\b\d+\s*,\s*\d+\b", response)
#     has_multiple_citations = len(citation_labels) >= 2 or bool(cited_numbers)
#     complex_terms = (
#         " and ",
#         "trial",
#         "trials",
#         "study",
#         "studies",
#         "evidence",
#         "according to",
#         "benefits",
#         "mechanism",
#         "combination",
#         "range",
#         "variant",
#         "variants",
#         "molecules included",
#         "molecules are included",
#         "guideline",
#         "protection",
#     )
#     named_evidence_terms = (
#         "dapa-hf",
#         "dapa hf",
#         "dapa-ckd",
#         "dapa ckd",
#         "cibis",
#         "additions",
#         "emphasis",
#         "ephesus",
#         "deliver",
#     )

#     return (
#         has_multiple_citations
#         and any(term in normalized_question for term in complex_terms)
#     ) or any(term in normalized_question or term in normalized_response for term in named_evidence_terms)


# def _is_broad_knowledge_question(question: str) -> bool:
#     """Return whether a question can be validated from enough cited support, not all cites."""
#     normalized = question.lower()
#     broad_terms = (
#         "why",
#         "how",
#         "benefit",
#         "benefits",
#         "evidence",
#         "supports",
#         "study",
#         "trial",
#         "guideline",
#         "different",
#         "preferred",
#         "protection",
#         "control",
#     )
#     strict_terms = (
#         "mrp",
#         "price",
#         "dosage",
#         "dose",
#         "composition",
#         "strength",
#         "pack size",
#         "lowest",
#         "highest",
#         "competitor",
#         "sku",
#     )
#     return any(term in normalized for term in broad_terms) and not any(
#         term in normalized for term in strict_terms
#     )


# def _should_combine_non_holistic_citations(question: str) -> bool:
#     """Return whether multiple cited pages should be evaluated together."""
#     normalized = question.lower()
#     combined_terms = (
#         "range",
#         "portfolio",
#         "variants",
#         "available",
#         "covered",
#         "categories",
#         "basket",
#         "included",
#         "which products",
#         "what products",
#         "competitor brands",
#         "all cited",
#     )
#     return _is_broad_knowledge_question(question) or any(
#         term in normalized for term in combined_terms
#     )


# def test_ask_questions_and_save_responses() -> None:
#     """Ask CSV questions one by one and save Super AI responses to CSV."""
#     logger = get_logger("test_ask_questions_and_save_responses")
#     browser_manager = BrowserManager()
#     page = None

#     try:
#         rows = [
#             row
#             for row in read_csv_rows(VALIDATION_QUESTIONS_FILE)
#             if (row.get("Question") or "").strip()
#         ]
#         question_limit = int(os.getenv("QUESTION_LIMIT", "0") or "0")
#         if question_limit > 0:
#             rows = rows[:question_limit]
#         results = []
#         page = browser_manager.launch_browser()
#         super_ai_page = login_to_super_ai(page)
#         citation_page = CitationPage(page)
#         openai_status = get_openai_validation_status()
#         use_openai_validation = is_openai_validation_available()
#         logger.info("OPENAI_VALIDATION_ACTIVE = %s", use_openai_validation)
#         logger.info("OPENAI_API_KEY_SET = %s", openai_status["api_key_set"])
#         logger.info("OPENAI_VALIDATION_MODEL = %s", openai_status["model"])
#         logger.info("OPENAI_VALIDATION_SCOPE = ALL_PRODUCTS")
#         logger.info("OPENAI_VALIDATION_STATUS = %s", openai_status["reason"])

#         for index, row in enumerate(rows, start=1):
#             question = (row.get("Question") or "").strip()
#             product_name = (
#                 row.get("Product_Name")
#                 or row.get("Product")
#                 or row.get("Type")
#                 or ""
#             ).strip()

#             if not question:
#                 logger.warning("Skipping row %s because Question is blank", index)
#                 results.append(
#                     _result_row(
#                         row,
#                         "",
#                         "QUESTION BLANK",
#                         "",
#                         "",
#                         "DATA MISSING",
#                         "Question is blank.",
#                     )
#                 )
#                 continue

#             logger.info("Processing question %s of %s", index, len(rows))
#             citation_page.close_citation_panel()
#             try:
#                 response, response_attempts = _ask_question_with_limited_retries(
#                     super_ai_page,
#                     question,
#                     logger,
#                 )
#             except TimeoutError as ask_exc:
#                 logger.exception("SuperAI response timed out for question %s: %s", index, ask_exc)
#                 results.append(
#                     _result_row(
#                         row,
#                         question,
#                         "SUPERAI_RESPONSE_TIMEOUT",
#                         "",
#                         "",
#                         "DATA MISSING",
#                         f"Timed out waiting for SuperAI response: {question}",
#                     )
#                 )
#                 continue
#             logger.info(
#                 "Super AI final response after %s attempt(s): %s",
#                 response_attempts,
#                 response,
#             )
#             page_number = ""
#             pdf_data = ""
#             validation_result = "DATA MISSING"
#             reason = "Required value not found in cited document/page."
#             citation_details = ""
#             matched_citation = ""
#             matched_document = ""
#             matched_page: str | int = ""
#             matched_evidence = ""

#             if _is_super_ai_no_match_response(response):
#                 logger.info(
#                     "SuperAI reported no matching source data; skipping citation fallback."
#                 )
#                 results.append(
#                     _result_row(
#                         row,
#                         question,
#                         response,
#                         "",
#                         "SUPERAI_NO_MATCH_RESPONSE",
#                         "DATA MISSING",
#                         (
#                             "SuperAI reported no matching/recognizable information "
#                             f"after {response_attempts} attempt(s)."
#                         ),
#                     )
#                 )
#                 continue

#             holistic_validation = (
#                 use_openai_validation
#                 and _needs_multi_citation_claim_validation(question, response)
#             )
#             if holistic_validation:
#                 logger.info(
#                     "MULTI_CITATION_CLAIM_VALIDATION_ENABLED: collecting all cited pages before final validation."
#                 )

#             try:
#                 citation_text = extract_citation_text(response)
#                 logger.info("Citation text: %s", citation_text or "NOT FOUND")

#                 citation_targets = extract_citation_targets(response)
#                 if not citation_targets:
#                     try:
#                         page_number = extract_page_number(response)
#                         citation_targets = [
#                             {
#                                 "citation_number": 1,
#                                 "page_number": page_number,
#                                 "document_name": extract_document_name(citation_text),
#                                 "citation_text": citation_text or f"Page_{page_number}",
#                             }
#                         ]
#                     except ValueError:
#                         citation_targets = citation_page.get_visible_citation_targets()
#                         if not citation_targets:
#                             citation_targets = citation_page.get_citation_targets_from_panels()

#                 if not citation_targets:
#                     logger.error("PAGE_NUMBER_EXTRACTION_FAILED")
#                     results.append(
#                         _result_row(
#                             row,
#                             question,
#                             response,
#                             "",
#                             "PAGE_NUMBER_EXTRACTION_FAILED",
#                             "DATA MISSING",
#                             "Citation page number could not be extracted.",
#                         )
#                     )
#                     continue

#                 citation_targets = _prioritize_citation_targets(
#                     citation_targets,
#                     question,
#                     product_name,
#                 )
#                 citation_targets = _dedupe_citation_targets(citation_targets)
#                 if _is_broad_knowledge_question(question):
#                     citation_limit = (
#                         MAX_KNOWLEDGE_CITATIONS_WITH_OPENAI
#                         if holistic_validation
#                         else MAX_KNOWLEDGE_CITATIONS_WITH_FALLBACK
#                     )
#                     if len(citation_targets) > citation_limit:
#                         logger.info(
#                             "Limiting broad knowledge validation citations from %s to %s for speed.",
#                             len(citation_targets),
#                             citation_limit,
#                         )
#                         citation_targets = citation_targets[:citation_limit]

#                 page_numbers_checked: list[str] = []
#                 extracted_pages: list[str] = []
#                 page_results: list[str] = []
#                 page_reasons: list[str] = []
#                 citation_details_checked: list[str] = []
#                 citation_audit_rows: list[dict[str, str | int]] = []
#                 first_pass_audit: dict[str, str | int] | None = None
#                 matched_citation = ""
#                 matched_document = ""
#                 VALIDATION_LOG.clear()
#                 matched_page: str | int = ""
#                 matched_evidence = ""

#                 logger.info("Extracted citation targets: %s", citation_targets)

#                 for audit_citation_number, target in enumerate(citation_targets, start=1):
#                     citation_number = int(target["citation_number"])
#                     page_number = int(target["page_number"])
#                     document_name = str(target.get("document_name") or "UNKNOWN DOCUMENT")
#                     target_citation_text = str(target["citation_text"])
#                     logger.info("Citation selected: %s", audit_citation_number)
#                     logger.info("Raw UI citation index used for click: %s", citation_number)
#                     logger.info("Citation text: %s", target_citation_text)
#                     logger.info("Document name: %s", document_name)
#                     logger.info("Extracted page number: %s", page_number)
#                     logger.info(
#                         "Searching citation %s page number %s",
#                         audit_citation_number,
#                         page_number,
#                     )

#                     page_numbers_checked.append(str(page_number))
#                     citation_details_checked.append(
#                         _citation_detail(audit_citation_number, document_name, page_number)
#                     )
#                     citation_page.target_page_number = page_number

#                     try:
#                         citation_page.open_citation_by_index(citation_number - 1)
#                         try:
#                             citation_page.open_source_document()
#                         except Exception as open_exc:
#                             logger.exception(
#                                 "DOCUMENT_OPEN_FAILED citation=%s document=%s error=%s",
#                                 citation_number,
#                                 document_name,
#                                 open_exc,
#                             )
#                             page_pdf_data = f"DOCUMENT_OPEN_FAILED: {open_exc}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("DATA MISSING")
#                             continue

#                         pdf_total_pages = citation_page.get_pdf_total_page_count()
#                         logger.info("PDF total page count: %s", pdf_total_pages)

#                         if page_number < 1 or page_number > pdf_total_pages:
#                             logger.error(
#                                 "INVALID_PAGE_NUMBER document=%s requested=%s total_pages=%s url=%s",
#                                 document_name,
#                                 page_number,
#                                 pdf_total_pages,
#                                 citation_page.source_url,
#                             )
#                             page_pdf_data = (
#                                 "INVALID_PAGE_NUMBER: "
#                                 f"requested {page_number}, total pages {pdf_total_pages}"
#                             )
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("INVALID_PAGE_NUMBER")
#                             continue

#                         logger.info("Page number requested for navigation: %s", page_number)

#                         try:
#                             citation_page.navigate_to_page(page_number)
#                         except Exception as nav_exc:
#                             logger.exception(
#                                 "PDF_NAVIGATION_FAILED citation=%s document=%s page=%s url=%s error=%s",
#                                 citation_number,
#                                 document_name,
#                                 page_number,
#                                 citation_page.source_url,
#                                 nav_exc,
#                             )
#                             page_pdf_data = f"PDF_NAVIGATION_FAILED: {nav_exc}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PDF_NAVIGATION_FAILED")
#                             continue

#                         current_pdf_page = citation_page.get_current_pdf_page_number()
#                         logger.info("Page navigation succeeded: %s", current_pdf_page == page_number)
#                         logger.info("Actual page opened after navigation: %s", current_pdf_page)

#                         if current_pdf_page != page_number:
#                             logger.error(
#                                 "PDF_NAVIGATION_FAILED document=%s expected=%s actual=%s url=%s",
#                                 document_name,
#                                 page_number,
#                                 current_pdf_page,
#                                 citation_page.source_url,
#                             )
#                             page_pdf_data = (
#                                 "PDF_NAVIGATION_FAILED: "
#                                 f"expected {page_number}, current {current_pdf_page}"
#                             )
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PDF_NAVIGATION_FAILED")
#                             continue

#                         try:
#                             page_pdf_data = citation_page.extract_page_data_from_pdf()
#                         except Exception as extract_exc:
#                             logger.exception(
#                                 "PAGE_TEXT_EXTRACTION_FAILED citation=%s document=%s page=%s url=%s error=%s",
#                                 citation_number,
#                                 document_name,
#                                 page_number,
#                                 citation_page.source_url,
#                                 extract_exc,
#                             )
#                             page_pdf_data = f"PAGE_TEXT_EXTRACTION_FAILED: {extract_exc}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PAGE_TEXT_EXTRACTION_FAILED")
#                             continue

#                         if not page_pdf_data.strip() or page_pdf_data == "NO PAGE DATA AVAILABLE":
#                             logger.error(
#                                 "PAGE_TEXT_EXTRACTION_FAILED document=%s page=%s url=%s preview=%s",
#                                 document_name,
#                                 page_number,
#                                 citation_page.source_url,
#                                 page_pdf_data[:200],
#                             )
#                             page_pdf_data = "PAGE_TEXT_EXTRACTION_FAILED"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("PAGE_TEXT_EXTRACTION_FAILED")
#                             continue

#                         evidence_ok, evidence_reason = _validate_evidence_before_openai(
#                             document_opened=citation_page.source_page is not None,
#                             pdf_url=citation_page.source_url,
#                             page_number=page_number,
#                             total_pages=pdf_total_pages,
#                             page_text=page_pdf_data,
#                             product_name=product_name,
#                             question=question,
#                         )
#                         logger.info("Evidence quality status: %s", evidence_reason)

#                         if evidence_ok and (
#                             evidence_reason.startswith("WEAK_PAGE_TEXT_ACCEPTED")
#                             or evidence_reason.startswith("LOW_TOPIC_CONFIDENCE")
#                         ):
#                             logger.warning(
#                                 "PARTIAL_EVIDENCE citation=%s page=%s text_len=%s reason=%s — "
#                                 "searching all text for attribute before accepting DATA MISSING",
#                                 citation_number,
#                                 page_number,
#                                 len(page_pdf_data),
#                                 evidence_reason,
#                             )
#                             page_pdf_data = (
#                                 "[NOTE: OCR extraction of this PDF page is partial or incomplete "
#                                 "(likely an image-based table). "
#                                 "Do NOT immediately return DATA MISSING. Instead: "
#                                 "1) Search all available text for the requested attribute. "
#                                 "2) Search nearby rows and table structures for the value. "
#                                 "3) Look for numeric values, product names, or keywords in any form. "
#                                 "4) Attempt semantic recovery from partial or fragmented content. "
#                                 "Only return DATA MISSING if the attribute is truly absent from "
#                                 "all available text after exhausting all recovery attempts.]\n"
#                                 + page_pdf_data
#                             )

#                         if not evidence_ok:
#                             logger.error(
#                                 "EVIDENCE_QUALITY_FAILED citation=%s page=%s reason=%s",
#                                 citation_number,
#                                 page_number,
#                                 evidence_reason,
#                             )
#                             page_pdf_data = f"{evidence_reason} Extracted preview: {page_pdf_data[:300]}"
#                             logger.info("Validation result for citation %s: DATA MISSING", citation_number)
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "DATA MISSING",
#                                 }
#                             )
#                             page_results.append("DATA MISSING")
#                             page_reasons.append(evidence_reason)
#                             continue

#                         answer_values = extract_answer_values(response)
#                         matched_values = extract_matching_values(response, page_pdf_data)
#                         logger.info("Cited page number used for validation: %s", page_number)
#                         logger.info("Extracted text from cited page %s: %s", page_number, page_pdf_data)
#                         logger.info("First 500 characters extracted from the page: %s", page_pdf_data[:500])
#                         logger.info("SuperAI values checked: %s", answer_values)
#                         logger.info("Final value found on the page: %s", matched_values or "NONE")
#                         logger.info("Value extracted from page: %s", matched_values or "NONE")
#                         logger.info("Super AI value: %s", answer_values or "NONE")

#                         if holistic_validation:
#                             logger.info(
#                                 "Citation %s collected for multi-citation claim-level validation.",
#                                 citation_number,
#                             )
#                             page_results.append("COLLECTED")
#                             page_reasons.append(
#                                 "Cited page collected for multi-citation claim-level validation."
#                             )
#                             extracted_pages.append(
#                                 (
#                                     f"Citation {audit_citation_number} | Document {document_name} | "
#                                     f"Page {page_number}: {page_pdf_data}"
#                                 )
#                             )
#                             citation_audit_rows.append(
#                                 {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "result": "COLLECTED",
#                                 }
#                             )
#                             continue

#                         (
#                             numeric_applicable,
#                             numeric_result,
#                             numeric_reason,
#                             numeric_matched_values,
#                         ) = deterministic_numeric_validation(
#                             response,
#                             page_pdf_data,
#                             question,
#                         )
#                         fallback_page_result = compare_ai_vs_pdf(response, page_pdf_data, question)
#                         fallback_page_reason = explain_ai_vs_pdf(response, page_pdf_data, question)

#                         use_numeric_first = _should_use_numeric_first_validation(question)
#                         if numeric_applicable and use_numeric_first:
#                             logger.info(
#                                 "Using deterministic numeric validation result before OpenAI: %s",
#                                 numeric_result,
#                             )
#                             page_result = numeric_result
#                             page_reason = numeric_reason
#                             matched_values = numeric_matched_values or matched_values
#                         elif (
#                             fallback_page_result == "PASS"
#                             and (
#                                 _is_rule_based_competitor_reasoning_question(question)
#                                 or (numeric_applicable and use_numeric_first)
#                             )
#                         ):
#                             logger.info(
#                                 "Using deterministic validation PASS; skipping OpenAI for speed."
#                             )
#                             page_result = fallback_page_result
#                             page_reason = (
#                                 numeric_reason if numeric_applicable else fallback_page_reason
#                             )
#                             matched_values = numeric_matched_values or matched_values
#                         elif use_openai_validation:
#                             openai_decision = validate_with_openai(
#                                 question=question,
#                                 super_ai_response=response,
#                                 cited_page_text=page_pdf_data,
#                                 product_name=product_name,
#                                 page_number=page_number,
#                                 document_name=document_name,
#                             )
#                             if openai_decision.get("engine") == "openai":
#                                 page_result = str(openai_decision["result"])
#                                 page_reason = str(openai_decision["reason"])
#                                 if page_result == "PASS" and _reason_contains_failure_contradiction(page_reason):
#                                     logger.warning(
#                                         "OpenAI returned PASS but reason contains contradiction/failure wording. "
#                                         "Overriding to FAIL. Reason=%s",
#                                         page_reason,
#                                     )
#                                     page_result = "FAIL"
#                                 matched_values = str(
#                                     openai_decision.get("matched_value") or matched_values
#                                 )
#                                 logger.info(
#                                     "OpenAI requested attribute: %s",
#                                     openai_decision.get("requested_attribute") or "UNKNOWN",
#                                 )
#                                 logger.info(
#                                     "OpenAI SuperAI values: %s",
#                                     openai_decision.get("super_ai_values") or [],
#                                 )
#                                 logger.info(
#                                     "OpenAI document values: %s",
#                                     openai_decision.get("document_values") or [],
#                                 )
#                                 if (
#                                     (
#                                         _is_competitor_brand_question(question)
#                                         or _is_dosage_question(question)
#                                     )
#                                     and fallback_page_result == "PASS"
#                                     and page_result != "PASS"
#                                 ):
#                                     logger.warning(
#                                         "OpenAI/deterministic validator disagreement. "
#                                         "Using deterministic page-scoped PASS. OpenAI result=%s reason=%s",
#                                         page_result,
#                                         page_reason,
#                                     )
#                                     page_result = fallback_page_result
#                                     page_reason = fallback_page_reason
#                                     matched_values = extract_matching_values(
#                                         response,
#                                         page_pdf_data,
#                                     )
#                             else:
#                                 logger.warning(
#                                     "OpenAI validation unavailable; using rule-based fallback: %s",
#                                     openai_decision.get("reason"),
#                                 )
#                                 page_result = fallback_page_result
#                                 page_reason = fallback_page_reason
#                         else:
#                             page_result = fallback_page_result
#                             page_reason = fallback_page_reason
#                         logger.info(
#                             "Validation result for citation %s: %s",
#                             citation_number,
#                             page_result,
#                         )
#                         logger.info(
#                             "Validation reason for citation %s: %s",
#                             citation_number,
#                             page_reason,
#                         )
#                         page_results.append(page_result)
#                         page_reasons.append(page_reason)
#                         extracted_pages.append(
#                             (
#                                 f"Citation {audit_citation_number} | Document {document_name} | "
#                                 f"Page {page_number}: {page_pdf_data}"
#                             )
#                         )
#                         citation_audit_rows.append(
#                             {
#                                 "citation": audit_citation_number,
#                                 "document": document_name,
#                                 "page": page_number,
#                                 "evidence": page_pdf_data,
#                                 "result": page_result,
#                             }
#                         )

#                         if page_result == "PASS":
#                             validation_result = "PASS"
#                             reason = page_reason
#                             if first_pass_audit is None:
#                                 first_pass_audit = {
#                                     "citation": audit_citation_number,
#                                     "document": document_name,
#                                     "page": page_number,
#                                     "evidence": page_pdf_data,
#                                     "reason": page_reason,
#                                 }
#                     finally:
#                         citation_page.close_source_document()
#                         citation_page.close_citation_panel()

#                 page_number = "; ".join(page_numbers_checked)
#                 citation_details = "\n".join(citation_details_checked)
#                 logger.info(
#                     "CITATION_AUDIT_SUMMARY processed=%s pass=%s fail=%s data_missing=%s",
#                     len(citation_audit_rows),
#                     page_results.count("PASS"),
#                     page_results.count("FAIL"),
#                     len(
#                         [
#                             result
#                             for result in page_results
#                             if result not in ("PASS", "FAIL", "COLLECTED")
#                         ]
#                     ),
#                 )
#                 if holistic_validation:
#                     all_pdf_data = "\n\n".join(extracted_pages)
#                     usable_extracted_pages = _usable_citation_evidence_pages(extracted_pages)
#                     usable_pdf_data = "\n\n".join(usable_extracted_pages)
#                     pdf_data = all_pdf_data
#                     logger.info(
#                         "HOLISTIC_USABLE_CITATIONS = %s of %s",
#                         len(usable_extracted_pages),
#                         len(extracted_pages),
#                     )
#                     if not extracted_pages:
#                         validation_result = "DATA MISSING"
#                         reason = "No cited page text was available for multi-citation claim-level validation."
#                     elif not usable_extracted_pages:
#                         validation_result = "DATA MISSING"
#                         reason = (
#                             "No usable cited page text was available; all cited sources failed "
#                             "to open, navigate, or extract meaningful text."
#                         )
#                     elif use_openai_validation:
#                         (
#                             numeric_applicable,
#                             numeric_result,
#                             numeric_reason,
#                             numeric_matched_values,
#                         ) = deterministic_numeric_validation(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         use_numeric_first = _should_use_numeric_first_validation(question)
#                         if numeric_applicable and use_numeric_first:
#                             validation_result = numeric_result
#                             reason = numeric_reason
#                             matched_citation = "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                             logger.info(
#                                 "Holistic deterministic numeric validation result before OpenAI: %s",
#                                 numeric_result,
#                             )
#                             logger.info(
#                                 "Holistic deterministic numeric matched values: %s",
#                                 numeric_matched_values or "NONE",
#                             )
#                             results.append(
#                                 _result_row(
#                                     row,
#                                     question,
#                                     response,
#                                     page_number,
#                                     all_pdf_data,
#                                     validation_result,
#                                     reason,
#                                     citation_details,
#                                     matched_citation,
#                                     matched_document,
#                                     matched_page,
#                                     matched_evidence,
#                                 )
#                             )
#                             continue
#                         holistic_decision = validate_with_openai(
#                             question=question,
#                             super_ai_response=response,
#                             cited_page_text=usable_pdf_data,
#                             product_name=product_name,
#                             page_number=page_number,
#                             document_name="MULTIPLE CITED SOURCES",
#                         )
#                         if holistic_decision.get("engine") == "openai":
#                             validation_result = str(holistic_decision["result"])
#                             reason = str(holistic_decision["reason"])
#                             if validation_result == "PASS" and _reason_contains_failure_contradiction(reason):
#                                 logger.warning(
#                                     "OpenAI returned holistic PASS but reason contains contradiction/failure wording. "
#                                     "Overriding to FAIL. Reason=%s",
#                                     reason,
#                                 )
#                                 validation_result = "FAIL"
#                             matched_citation = "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(
#                                 str(holistic_decision.get("matched_value") or "")
#                                 or usable_pdf_data
#                             )
#                             logger.info(
#                                 "Holistic OpenAI requested attribute: %s",
#                                 holistic_decision.get("requested_attribute") or "KNOWLEDGE_MODE",
#                             )
#                             logger.info(
#                                 "Holistic OpenAI SuperAI values/claims: %s",
#                                 holistic_decision.get("super_ai_values") or [],
#                             )
#                             logger.info(
#                                 "Holistic OpenAI document values/evidence: %s",
#                                 holistic_decision.get("document_values") or [],
#                             )
#                         else:
#                             fallback_result = compare_ai_vs_pdf(
#                                 response,
#                                 usable_pdf_data,
#                                 question,
#                             )
#                             validation_result = fallback_result
#                             reason = explain_ai_vs_pdf(
#                                 response,
#                                 usable_pdf_data,
#                                 question,
#                             )
#                             if validation_result == "DATA MISSING":
#                                 reason = (
#                                     "Multi-citation OpenAI validation could not run: "
#                                     f"{holistic_decision.get('reason')}. "
#                                     f"Rule-based fallback result: {reason}"
#                                 )
#                             matched_citation = (
#                                 "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                             )
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                     else:
#                         validation_result = compare_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         reason = explain_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         if validation_result == "DATA MISSING":
#                             reason = (
#                                 "OpenAI validation is unavailable; rule-based fallback "
#                                 f"could not fully validate the cited evidence. {reason}"
#                             )
#                         matched_citation = (
#                             "MULTIPLE" if len(usable_extracted_pages) > 1 else ""
#                         )
#                         matched_document = "MULTIPLE CITED SOURCES"
#                         matched_page = page_number
#                         matched_evidence = _evidence_preview(usable_pdf_data)
#                 elif validation_result == "PASS" and first_pass_audit is not None:
#                     pdf_data = "\n\n".join(extracted_pages)
#                     matched_citation = f"Citation {first_pass_audit['citation']}"
#                     matched_document = str(first_pass_audit["document"])
#                     matched_page = first_pass_audit["page"]
#                     matched_evidence = _evidence_preview(str(first_pass_audit["evidence"]))
#                     reason = str(first_pass_audit["reason"])
#                 elif validation_result != "PASS":
#                     pdf_data = "\n\n".join(extracted_pages)
#                     usable_extracted_pages = _usable_citation_evidence_pages(extracted_pages)
#                     usable_pdf_data = "\n\n".join(usable_extracted_pages)
#                     if len(usable_extracted_pages) > 1 and _should_combine_non_holistic_citations(
#                         question
#                     ):
#                         logger.info(
#                             "Running combined-citation validation for non-holistic question using %s cited pages.",
#                             len(usable_extracted_pages),
#                         )
#                         combined_result = compare_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         combined_reason = explain_ai_vs_pdf(
#                             response,
#                             usable_pdf_data,
#                             question,
#                         )
#                         logger.info(
#                             "Combined-citation validation result: %s | reason: %s",
#                             combined_result,
#                             combined_reason,
#                         )
#                         if combined_result == "PASS":
#                             validation_result = "PASS"
#                             reason = combined_reason
#                             matched_citation = "MULTIPLE"
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                         elif combined_result == "FAIL":
#                             validation_result = "FAIL"
#                             reason = combined_reason
#                             matched_citation = "MULTIPLE"
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                         else:
#                             validation_result = "DATA MISSING"
#                             reason = combined_reason
#                             matched_citation = "MULTIPLE"
#                             matched_document = "MULTIPLE CITED SOURCES"
#                             matched_page = page_number
#                             matched_evidence = _evidence_preview(usable_pdf_data)
#                     elif "FAIL" in page_results:
#                         validation_result = "FAIL"
#                         fail_index = page_results.index("FAIL")
#                         reason = page_reasons[fail_index] if fail_index < len(page_reasons) else _validation_reason("FAIL")
#                         if fail_index < len(citation_audit_rows):
#                             failed_audit = citation_audit_rows[fail_index]
#                             matched_citation = f"Citation {failed_audit['citation']}"
#                             matched_document = str(failed_audit["document"])
#                             matched_page = failed_audit["page"]
#                             matched_evidence = _evidence_preview(str(failed_audit["evidence"]))
#                     elif page_results:
#                         validation_result = "DATA MISSING"
#                         reason = page_reasons[-1] if page_reasons else _validation_reason("DATA MISSING")
#                         if citation_audit_rows:
#                             last_audit = citation_audit_rows[-1]
#                             matched_citation = f"Citation {last_audit['citation']}"
#                             matched_document = str(last_audit["document"])
#                             matched_page = last_audit["page"]
#                             matched_evidence = _evidence_preview(str(last_audit["evidence"]))
#                     else:
#                         validation_result = "DATA MISSING"
#                         reason = "Citation page number could not be extracted."

#             except Exception as question_exc:
#                 logger.exception(
#                     "Validation failed for question %s: %s",
#                     index,
#                     question_exc,
#                 )
#                 pdf_data = f"VALIDATION ERROR: {question_exc}"
#                 validation_result = "DATA MISSING"
#                 reason = f"Validation error: {question_exc}"
#                 citation_page.close_source_document()

#             results.append(
#                 _result_row(
#                     row,
#                     question,
#                     response,
#                     page_number,
#                     pdf_data,
#                     validation_result,
#                     reason,
#                     citation_details,
#                     matched_citation,
#                     matched_document,
#                     matched_page,
#                     matched_evidence,
#                 )
#             )

#         output_report_path = write_csv_rows(OUTPUT_RESULTS_FILE, results)
#         if output_report_path:
#             logger.info("Responses saved to %s", output_report_path)

#     except Exception as exc:
#         logger.exception("Question validation test failed: %s", exc)

#         if page:
#             screenshot_path = capture_screenshot(page, "question_failure")
#             logger.error("Failure screenshot captured: %s", screenshot_path)

#         raise

#     finally:
#         browser_manager.close_browser()


# if __name__ == "__main__":
#     test_ask_questions_and_save_responses()


##### =================


"""Question-answer validation test for Super AI."""

import os
import re

from config.settings import OUTPUT_RESULTS_FILE, VALIDATION_QUESTIONS_FILE
from pages.citation_page import CitationPage
from utils.browser_manager import BrowserManager
from utils.csv_handler import read_csv_rows, write_csv_rows
from utils.helpers import capture_screenshot
from utils.login_flow import login_to_super_ai
from utils.logger import get_logger
from utils.openai_validation_engine import (
    get_openai_validation_status,
    is_openai_validation_available,
    validate_with_openai,
)
from utils.source_document_reader import is_weak_pdf_page_text
from utils.validator import (
    VALIDATION_LOG,
    compare_ai_vs_pdf,
    deterministic_numeric_validation,
    explain_ai_vs_pdf,
    extract_answer_values,
    extract_citation_targets,
    extract_citation_text,
    extract_document_name,
    extract_matching_values,
    extract_page_number,
)

MAX_SUPER_AI_NO_MATCH_ATTEMPTS = 2
MAX_KNOWLEDGE_CITATIONS_WITH_OPENAI = 6
MAX_KNOWLEDGE_CITATIONS_WITH_FALLBACK = 6
MIN_TOPIC_KEYWORD_MATCHES = 1


# def _result_row(
#     source_row: dict[str, str],
#     question: str,
#     response: str,
#     page_number: str | int,
#     document_data: str,
#     result: str,
#     reason: str,
#     citation_details: str = "",
#     matched_citation: str = "",
#     matched_document: str = "",
#     matched_page: str | int = "",
#     matched_evidence: str = "",
# ) -> dict[str, str | int]:

def _result_row(
    source_row: dict[str, str],
    question: str,
    response: str,
    page_number: str | int,
    document_data: str,
    result: str,
    reason: str,
    failure_source: str = "",
    citation_details: str = "",
    matched_citation: str = "",
    matched_document: str = "",
    matched_page: str | int = "",
    matched_evidence: str = "",
) -> dict[str, str | int]:
    """Build the output CSV row using the requested report format."""
    return {
        "Product_Name": (
            source_row.get("Product_Name")
            or source_row.get("Product")
            or source_row.get("Type")
            or ""
        ).strip(),
        "Question": question,
        "SuperAI_Response": response,
        "Page_Number": page_number,
        "Citation_Details": citation_details,
        "Matched_Citation": matched_citation,
        "Matched_Document": matched_document,
        "Matched_Page": matched_page,
        "Matched_Evidence": matched_evidence,
        "Document_Data": document_data,
        "Result": result,
        "Failure_Source": failure_source,
        "Reason": reason,
    }


def _citation_detail(citation_number: int, document_name: str, page_number: int) -> str:
    """Return a compact citation audit record for output reports."""
    return f"Citation {citation_number} | Document {document_name} | Page {page_number}"


def _evidence_preview(text: str, limit: int = 1000) -> str:
    """Keep matched evidence audit-friendly without making reports huge."""
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned[:limit]

def _failure_source(
    result: str,
    reason: str,
    response: str,
) -> str:
    """
    Identify whether the failure came from SuperAI,
    documentation, or validation logic.
    """

    if result == "PASS":
        return "VALIDATED"

    if result == "DATA MISSING":

        reason_lower = (reason or "").lower()

        if (
            "validation error" in reason_lower
            or "pdf navigation failed" in reason_lower
            or "page extraction failed" in reason_lower
            or "citation page number could not be extracted" in reason_lower
        ):
            return "VALIDATOR_ERROR"

        return "DOCUMENTATION_MISSING"

    if result == "FAIL":

        reason_lower = (reason or "").lower()

        validator_indicators = (
            "wrong row",
            "wrong product",
            "variant mismatch",
            "pack size mismatch",
            "current mrp",
            "new mrp",
            "citation matching",
            "validator selected",
            "product matching error",
        )

        if any(x in reason_lower for x in validator_indicators):
            return "VALIDATOR_ERROR"

        return "SUPERAI_ERROR"

    return ""

def _validation_reason(result: str, matched_values: str = "", detail: str = "") -> str:
    """Return a short business-readable reason for the validation result."""
    if result == "PASS":
        return "Exact match found." if not matched_values else f"Matching value found: {matched_values}."
    if result == "FAIL":
        return detail or "Value found on cited page, but it does not match Super AI response."
    return detail or "Required value not found in cited document/page."


def _reason_contains_failure_contradiction(reason: str) -> bool:
    """Detect unsafe PASS decisions where the explanation says the answer is wrong."""
    normalized = (reason or "").lower()
    failure_markers = (
        "should be fail",
        "should be fail, not pass",
        "therefore this should be fail",
        "contradicts the citation",
        "contradicts the cited",
        "superai answer does not match",
        "does not match the computed",
        "not matching superai",
        "mismatch",
    )
    return any(marker in normalized for marker in failure_markers)


def _validate_evidence_before_openai(
    *,
    document_opened: bool,
    pdf_url: str,
    page_number: int,
    total_pages: int,
    page_text: str,
    product_name: str,
    question: str,
) -> tuple[bool, str]:
    """Return whether cited-page evidence is strong enough for validation."""
    if not document_opened:
        return False, "DOCUMENT_OPEN_FAILED: source document was not opened."

    if not pdf_url.strip():
        return False, "PDF_URL_NOT_CAPTURED: source PDF URL was not captured."

    if page_number < 1 or page_number > total_pages:
        return (
            False,
            f"INVALID_PAGE_NUMBER: requested {page_number}, total pages {total_pages}.",
        )

    if is_weak_pdf_page_text(page_text):
        if not page_text.strip():
            return (
                False,
                "PAGE_TEXT_EXTRACTION_FAILED: cited page text was empty — all extraction methods returned nothing.",
            )
        # Non-empty but short/sparse (image-based table with partial OCR or sparse layout).
        # Pass to LLM for judgment rather than immediately returning DATA MISSING.
        return (
            True,
            "WEAK_PAGE_TEXT_ACCEPTED: page may contain image-based tables; extracted text is partial.",
        )

    if not _page_text_matches_product_or_topic(page_text, product_name, question):
        # Do not hard-stop — partial or image-based pages may still contain
        # the answer in a table row, nearby row, or recoverable fragment.
        # Pass to the LLM with a low-confidence flag instead of DATA MISSING.
        return (
            True,
            "LOW_TOPIC_CONFIDENCE: cited page text does not clearly match product or topic — "
            "attempting validation with partial evidence.",
        )

    return True, "EVIDENCE_OK"


def _is_failed_citation_evidence(extracted_page: str) -> bool:
    """Return whether a collected citation section is only an extraction/open failure."""
    failure_markers = (
        "DOCUMENT_OPEN_FAILED",
        "PDF_NAVIGATION_FAILED",
        "PAGE_TEXT_EXTRACTION_FAILED",
        "INVALID_PAGE_NUMBER",
        "PDF_URL_NOT_CAPTURED",
        "WEAK_EVIDENCE",
    )
    return any(marker in extracted_page for marker in failure_markers)


def _usable_citation_evidence_pages(extracted_pages: list[str]) -> list[str]:
    """Return cited pages that contain meaningful text, ignoring hard failures.

    Weak or partial pages (image-based tables, short OCR output) are included
    rather than discarded — they may still hold recoverable table rows or
    numeric values that the LLM can find via semantic recovery.
    """
    usable_pages: list[str] = []
    for extracted_page in extracted_pages:
        if _is_failed_citation_evidence(extracted_page):
            continue
        usable_pages.append(extracted_page)
    return usable_pages


def _page_text_matches_product_or_topic(
    page_text: str,
    product_name: str,
    question: str,
) -> bool:
    """Return whether page text is related to the product or question topic."""
    normalized_page = _normalize_for_evidence_check(page_text)
    product_tokens = _evidence_tokens(product_name)
    question_tokens = _evidence_tokens(question)

    if product_tokens and any(token in normalized_page for token in product_tokens):
        return True

    topic_matches = [token for token in question_tokens if token in normalized_page]
    return len(topic_matches) >= MIN_TOPIC_KEYWORD_MATCHES


def _evidence_tokens(text: str) -> list[str]:
    """Return meaningful product/topic tokens for evidence relevance checks."""
    stop_words = {
        "what",
        "which",
        "why",
        "how",
        "does",
        "with",
        "from",
        "that",
        "this",
        "were",
        "was",
        "and",
        "the",
        "for",
        "according",
        "compared",
        "provide",
        "provides",
        "considered",
        "patients",
        "patient",
        "therapy",
        "treatment",
    }
    normalized = _normalize_for_evidence_check(text)
    tokens = re.findall(r"[a-z0-9][a-z0-9-]{2,}", normalized)
    return [token for token in tokens if token not in stop_words]


def _normalize_for_evidence_check(text: str) -> str:
    """Normalize text for lightweight evidence relevance checks."""
    normalized = text.lower().replace("\u00a0", " ")
    normalized = re.sub(r"[_./]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _is_super_ai_no_match_response(response: str) -> bool:
    """Return whether SuperAI gave an irrelevant or no-source answer."""
    normalized_with_apostrophes = " ".join(
        response.lower()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .split()
    )
    normalized = normalized_with_apostrophes.replace("'", "")
    normalized_loose = re.sub(r"[^a-z0-9]+", " ", response.lower()).strip()
    no_match_phrases = (
        "i can only help with queries regarding products and policies",
        "can only help with queries regarding products and policies",
        "only help with queries regarding products and policies",
        "can only help with product and policy queries",
        "outside the scope of products and policies",
        "couldnt find any matching information",
        "could not find any matching information",
        "couldnt find the requested information",
        "could not find the requested information",
        "could not find any matching information in the provided sources",
        "i could not find any matching information in the provided sources",
        "i couldnt find any matching information in the provided sources",
        "no matching information in the provided sources",
        "no matching information was found",
        "no matching source data",
        "no relevant information was found",
        "no information was found",
        "i could not find",
        "i couldnt find",
        "i could not recognize",
        "i couldnt recognize",
        "could not recognize",
        "couldnt recognize",
        "unable to recognize",
        "unable to find",
        "not able to find",
        "could not identify",
        "couldnt identify",
        "i do not have enough information",
        "i don't have enough information",
        "insufficient information",
        "looks like something went wrong",
        "something went wrong",
        "please try again",
        "error occurred",
        "an error occurred",
        "retry",
    )
    loose_no_match_phrases = (
        "i couldn t find any matching information in the provided sources",
        "couldn t find any matching information",
        "looks like something went wrong retry",
        "something went wrong retry",
        "please try again",
        "error occurred",
    )
    return any(phrase in normalized for phrase in no_match_phrases) or any(
        phrase in normalized_loose for phrase in loose_no_match_phrases
    )


def _is_terminal_source_exhausted_response(response: str) -> bool:
    """Return whether SuperAI says the provided sources have no matching data."""
    normalized = re.sub(r"[^a-z0-9]+", " ", response.lower()).strip()
    terminal_phrases = (
        "i could not find any matching information in the provided sources",
        "i couldn t find any matching information in the provided sources",
        "i couldnt find any matching information in the provided sources",
        "no matching information in the provided sources",
        "no matching information was found",
    )
    return any(phrase in normalized for phrase in terminal_phrases)


def _ask_question_with_limited_retries(super_ai_page, question: str, logger) -> tuple[str, int]:
    """Ask a question up to two times if SuperAI returns no usable answer."""
    response = ""
    retry_source_exhausted = _should_retry_source_exhausted_response(question)

    for attempt in range(1, MAX_SUPER_AI_NO_MATCH_ATTEMPTS + 1):
        logger.info(
            "Asking SuperAI attempt %s of %s",
            attempt,
            MAX_SUPER_AI_NO_MATCH_ATTEMPTS,
        )
        response = super_ai_page.ask_question(question)
        logger.info("Super AI response attempt %s: %s", attempt, response)

        if "looks like something went wrong" in response.lower():
            validation_result = "FAIL"
            reason = "SuperAI returned platform error after retry attempts."
        
        if not _is_super_ai_no_match_response(response):
            return response, attempt

        if _is_terminal_source_exhausted_response(response) and not retry_source_exhausted:
            logger.info(
                "SuperAI source-exhausted response detected; skipping retry and citation lookup."
            )
            return response, attempt

        if attempt < MAX_SUPER_AI_NO_MATCH_ATTEMPTS:
            logger.info(
                "SuperAI no-source/irrelevant response detected; retrying same question."
            )
        else:
            logger.info(
                "SuperAI no-source/irrelevant response detected after final attempt."
            )

    return response, MAX_SUPER_AI_NO_MATCH_ATTEMPTS


def _should_retry_source_exhausted_response(question: str) -> bool:
    """Retry no-source responses for direct product price/MRP questions."""
    normalized = question.lower()
    retry_terms = (
        "mrp",
        "price",
        "cost",
        "per strip",
        "strip",
        "cheaper",
        "saving",
        "side effect",
        "side effects",
        "adverse",
        "adverse effect",
        "adverse effects",
        "adverse reaction",
        "adverse reactions",
        "adverse event",
        "adverse events",
        "monitoring",
        "precaution",
        "precautions",
        "nephrotoxicity",
    )
    return any(term in normalized for term in retry_terms)


def _prioritize_citation_targets(
    targets: list[dict[str, int | str]],
    question: str,
    product_name: str,
) -> list[dict[str, int | str]]:
    """Try the most likely cited documents first without dropping any target."""
    if _is_broad_knowledge_question(question):
        return targets

    normalized_question = question.lower()
    normalized_product = product_name.lower()

    def score(target: dict[str, int | str]) -> tuple[int, int]:
        document_name = str(target.get("document_name") or "").lower()
        citation_text = str(target.get("citation_text") or "").lower()
        combined_text = f"{document_name} {citation_text}"
        rank = 0

        if any(term in normalized_question for term in ("mrp", "price")):
            if "price master" in combined_text:
                rank -= 50
            if "brand snapshot" in combined_text:
                rank += 20

        for token in normalized_product.split():
            if token and token in combined_text:
                rank -= 5

        return rank, int(target.get("page_number") or 0)

    return sorted(targets, key=score)


def _dedupe_citation_targets(
    targets: list[dict[str, int | str]],
) -> list[dict[str, int | str]]:
    """Keep first occurrence of each document/page so duplicate citations are not reread."""
    deduped_targets: list[dict[str, int | str]] = []
    seen: set[tuple[str, int]] = set()

    for target in targets:
        try:
            page_number = int(target.get("page_number") or 0)
        except (TypeError, ValueError):
            page_number = 0

        document_name = str(target.get("document_name") or "").strip().lower()
        citation_text = str(target.get("citation_text") or "").strip().lower()
        document_key = document_name or citation_text
        key = (document_key, page_number)

        if key in seen:
            continue

        seen.add(key)
        deduped_targets.append(target)

    return deduped_targets


def _is_competitor_brand_question(question: str) -> bool:
    """Return whether the question needs brand-only competitor table validation."""
    normalized = question.lower()
    return "competitor" in normalized and "brand" in normalized


def _is_dosage_question(question: str) -> bool:
    """Return whether the question needs strict dosage normalization."""
    normalized = question.lower()
    return any(term in normalized for term in ("dosage", "dose", "recommended dosage"))


def _is_rule_based_competitor_reasoning_question(question: str) -> bool:
    """Return whether deterministic table math should be trusted before OpenAI."""
    normalized = question.lower()
    return "competitor" in normalized and any(
        term in normalized
        for term in (
            "price",
            "mrp",
            "lowest",
            "highest",
            "cheapest",
            "most expensive",
            "between",
            "how many",
            "count",
            "pack size",
            "manufacturer",
            "manufactures",
            "company",
            "percentage",
            "saving",
            "cost saving",
        )
    )


def _should_use_numeric_first_validation(question: str) -> bool:
    """Return whether numeric mismatch should decide before OpenAI review."""
    normalized = question.lower()
    strict_numeric_terms = (
        "mrp",
        "price",
        "cost",
        "cheaper",
        "saving",
        "percentage",
        "difference",
        "dosage",
        "dose",
        "strength",
        "pack size",
        "per strip",
        "per tablet",
        "per tab",
        "per box",
        "how many",
        "composition",
    )
    descriptive_terms = (
        "indicated",
        "indication",
        "conditions",
        "why",
        "how",
        "mechanism",
        "role",
        "benefit",
        "benefits",
        "advantage",
        "usp",
        "range",
        "molecules included",
    )

    if any(term in normalized for term in strict_numeric_terms):
        return True

    return not any(term in normalized for term in descriptive_terms)


def _is_holistic_knowledge_question(question: str, response: str = "") -> bool:
    """Return whether the answer needs claim-level validation across all citations."""
    normalized_question = question.lower()
    normalized_response = response.lower()
    holistic_terms = (
        "pitch",
        "picth",
        "positioning",
        "position ",
        "summary",
        "summarize",
        "overview",
        "range",
        "variants",
        "variant",
        "knowledge",
        "talking point",
        "call flow",
        "key message",
    )
    if any(term in normalized_question for term in holistic_terms):
        return True

    citation_markers = len(re.findall(r"\(\s*\d+\s*\)|\b\d+\s*,\s*\d+\b", response))
    bullet_like_lines = len(
        [
            line
            for line in response.splitlines()
            if line.strip().startswith(("-", "*", "•"))
        ]
    )
    descriptive_terms = (
        "brand trust",
        "reference brand",
        "weight neutral",
        "hypoglycaemia",
        "hypoglycemia",
        "ckd",
        "beta-cell",
        "beta cell",
        "salient",
        "advantage",
        "benefit",
        "usp",
    )
    return (
        bullet_like_lines >= 3
        and citation_markers >= 2
        and any(term in normalized_response for term in descriptive_terms)
    )


def _needs_multi_citation_claim_validation(question: str, response: str = "") -> bool:
    """Return whether all cited pages should be merged before validation."""
    normalized_question = question.lower()
    normalized_response = response.lower()

    if _is_holistic_knowledge_question(question, response):
        return True

    if not _is_broad_knowledge_question(question):
        return False

    citation_labels = re.findall(r"_page_\d+", response, flags=re.IGNORECASE)
    cited_numbers = re.findall(r"\b\d+\s*,\s*\d+\b", response)
    has_multiple_citations = len(citation_labels) >= 2 or bool(cited_numbers)
    complex_terms = (
        " and ",
        "trial",
        "trials",
        "study",
        "studies",
        "evidence",
        "according to",
        "benefits",
        "mechanism",
        "combination",
        "range",
        "variant",
        "variants",
        "molecules included",
        "molecules are included",
        "guideline",
        "protection",
    )
    named_evidence_terms = (
        "dapa-hf",
        "dapa hf",
        "dapa-ckd",
        "dapa ckd",
        "cibis",
        "additions",
        "emphasis",
        "ephesus",
        "deliver",
    )

    return (
        has_multiple_citations
        and any(term in normalized_question for term in complex_terms)
    ) or any(term in normalized_question or term in normalized_response for term in named_evidence_terms)


def _is_broad_knowledge_question(question: str) -> bool:
    """Return whether a question can be validated from enough cited support, not all cites."""
    normalized = question.lower()
    broad_terms = (
        "why",
        "how",
        "benefit",
        "benefits",
        "evidence",
        "supports",
        "study",
        "trial",
        "guideline",
        "different",
        "preferred",
        "protection",
        "control",
    )
    strict_terms = (
        "mrp",
        "price",
        "dosage",
        "dose",
        "composition",
        "strength",
        "pack size",
        "lowest",
        "highest",
        "competitor",
        "sku",
    )
    return any(term in normalized for term in broad_terms) and not any(
        term in normalized for term in strict_terms
    )


def _should_combine_non_holistic_citations(question: str) -> bool:
    """Return whether multiple cited pages should be evaluated together."""
    normalized = question.lower()
    combined_terms = (
        "range",
        "portfolio",
        "variants",
        "available",
        "covered",
        "categories",
        "basket",
        "included",
        "which products",
        "what products",
        "competitor brands",
        "all cited",
    )
    return _is_broad_knowledge_question(question) or any(
        term in normalized for term in combined_terms
    )


def _citation_list_str(audits: list[dict[str, str | int]], field: str, prefix: str = "") -> str:
    """Return a ' | '-joined string of a field across all citation audit rows."""
    parts = []
    for a in audits:
        val = str(a.get(field, ""))
        parts.append(f"{prefix}{val}" if prefix else val)
    return " | ".join(parts)


def test_ask_questions_and_save_responses() -> None:
    """Ask CSV questions one by one and save Super AI responses to CSV."""
    logger = get_logger("test_ask_questions_and_save_responses")
    browser_manager = BrowserManager()
    page = None

    try:
        rows = [
            row
            for row in read_csv_rows(VALIDATION_QUESTIONS_FILE)
            if (row.get("Question") or "").strip()
        ]
        question_limit = int(os.getenv("QUESTION_LIMIT", "0") or "0")
        if question_limit > 0:
            rows = rows[:question_limit]
        results = []
        page = browser_manager.launch_browser()
        super_ai_page = login_to_super_ai(page)
        citation_page = CitationPage(page)
        openai_status = get_openai_validation_status()
        use_openai_validation = is_openai_validation_available()
        logger.info("OPENAI_VALIDATION_ACTIVE = %s", use_openai_validation)
        logger.info("OPENAI_API_KEY_SET = %s", openai_status["api_key_set"])
        logger.info("OPENAI_VALIDATION_MODEL = %s", openai_status["model"])
        logger.info("OPENAI_VALIDATION_SCOPE = ALL_PRODUCTS")
        logger.info("OPENAI_VALIDATION_STATUS = %s", openai_status["reason"])

        for index, row in enumerate(rows, start=1):
            question = (row.get("Question") or "").strip()
            product_name = (
                row.get("Product_Name")
                or row.get("Product")
                or row.get("Type")
                or ""
            ).strip()

            if not question:
                logger.warning("Skipping row %s because Question is blank", index)
                results.append(
                    _result_row(
                        row,
                        "",
                        "QUESTION BLANK",
                        "",
                        "",
                        "DATA MISSING",
                        "Question is blank.",
                    )
                )
                continue

            logger.info("Processing question %s of %s", index, len(rows))
            citation_page.close_citation_panel()
            try:
                response, response_attempts = _ask_question_with_limited_retries(
                    super_ai_page,
                    question,
                    logger,
                )
            except TimeoutError as ask_exc:
                logger.exception("SuperAI response timed out for question %s: %s", index, ask_exc)
                results.append(
                    _result_row(
                        row,
                        question,
                        "SUPERAI_RESPONSE_TIMEOUT",
                        "",
                        "",
                        "DATA MISSING",
                        f"Timed out waiting for SuperAI response: {question}",
                    )
                )
                continue
            logger.info(
                "Super AI final response after %s attempt(s): %s",
                response_attempts,
                response,
            )
            page_number = ""
            pdf_data = ""
            validation_result = "DATA MISSING"
            reason = "Required value not found in cited document/page."
            citation_details = ""
            matched_citation = ""
            matched_document = ""
            matched_page: str | int = ""
            matched_evidence = ""

            if _is_super_ai_no_match_response(response):
                logger.info(
                    "SuperAI reported no matching source data; skipping citation fallback."
                )
                results.append(
                    _result_row(
                        row,
                        question,
                        response,
                        "",
                        "SUPERAI_NO_MATCH_RESPONSE",
                        "DATA MISSING",
                        (
                            "SuperAI reported no matching/recognizable information "
                            f"after {response_attempts} attempt(s)."
                        ),
                    )
                )
                continue

            holistic_validation = (
                use_openai_validation
                and _needs_multi_citation_claim_validation(question, response)
            )
            if holistic_validation:
                logger.info(
                    "MULTI_CITATION_CLAIM_VALIDATION_ENABLED: collecting all cited pages before final validation."
                )

            try:
                citation_text = extract_citation_text(response)
                logger.info("Citation text: %s", citation_text or "NOT FOUND")

                citation_targets = extract_citation_targets(response)
                if not citation_targets:
                    try:
                        page_number = extract_page_number(response)
                        citation_targets = [
                            {
                                "citation_number": 1,
                                "page_number": page_number,
                                "document_name": extract_document_name(citation_text),
                                "citation_text": citation_text or f"Page_{page_number}",
                            }
                        ]
                    except ValueError:
                        citation_targets = citation_page.get_visible_citation_targets()
                        if not citation_targets:
                            citation_targets = citation_page.get_citation_targets_from_panels()

                if not citation_targets:
                    logger.error("PAGE_NUMBER_EXTRACTION_FAILED")
                    results.append(
                        _result_row(
                            row,
                            question,
                            response,
                            "",
                            "PAGE_NUMBER_EXTRACTION_FAILED",
                            "DATA MISSING",
                            "Citation page number could not be extracted.",
                        )
                    )
                    continue

                citation_targets = _prioritize_citation_targets(
                    citation_targets,
                    question,
                    product_name,
                )
                citation_targets = _dedupe_citation_targets(citation_targets)
                if _is_broad_knowledge_question(question):
                    citation_limit = (
                        MAX_KNOWLEDGE_CITATIONS_WITH_OPENAI
                        if holistic_validation
                        else MAX_KNOWLEDGE_CITATIONS_WITH_FALLBACK
                    )
                    if len(citation_targets) > citation_limit:
                        logger.info(
                            "Limiting broad knowledge validation citations from %s to %s for speed.",
                            len(citation_targets),
                            citation_limit,
                        )
                        citation_targets = citation_targets[:citation_limit]

                page_numbers_checked: list[str] = []
                extracted_pages: list[str] = []
                page_results: list[str] = []
                page_reasons: list[str] = []
                citation_details_checked: list[str] = []
                citation_audit_rows: list[dict[str, str | int]] = []
                pass_audits: list[dict[str, str | int]] = []
                matched_citations_list: list[str] = []
                matched_documents_list: list[str] = []
                matched_pages_list: list[str] = []
                matched_evidences_list: list[str] = []
                matched_citation = ""
                matched_document = ""
                VALIDATION_LOG.clear()
                matched_page: str | int = ""
                matched_evidence = ""

                logger.info("Extracted citation targets: %s", citation_targets)

                for audit_citation_number, target in enumerate(citation_targets, start=1):
                    citation_number = int(target["citation_number"])
                    page_number = int(target["page_number"])
                    document_name = str(target.get("document_name") or "UNKNOWN DOCUMENT")
                    target_citation_text = str(target["citation_text"])
                    logger.info("Citation selected: %s", audit_citation_number)
                    logger.info("Raw UI citation index used for click: %s", citation_number)
                    logger.info("Citation text: %s", target_citation_text)
                    logger.info("Document name: %s", document_name)
                    logger.info("Extracted page number: %s", page_number)
                    logger.info(
                        "Searching citation %s page number %s",
                        audit_citation_number,
                        page_number,
                    )

                    page_numbers_checked.append(str(page_number))
                    citation_details_checked.append(
                        _citation_detail(audit_citation_number, document_name, page_number)
                    )
                    citation_page.target_page_number = page_number

                    try:
                        citation_page.open_citation_by_index(citation_number - 1)
                        try:
                            citation_page.open_source_document()
                        except Exception as open_exc:
                            logger.exception(
                                "DOCUMENT_OPEN_FAILED citation=%s document=%s error=%s",
                                citation_number,
                                document_name,
                                open_exc,
                            )
                            page_pdf_data = f"DOCUMENT_OPEN_FAILED: {open_exc}"
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("DATA MISSING")
                            continue

                        pdf_total_pages = citation_page.get_pdf_total_page_count()
                        logger.info("PDF total page count: %s", pdf_total_pages)

                        if page_number < 1 or page_number > pdf_total_pages:
                            logger.error(
                                "INVALID_PAGE_NUMBER document=%s requested=%s total_pages=%s url=%s",
                                document_name,
                                page_number,
                                pdf_total_pages,
                                citation_page.source_url,
                            )
                            page_pdf_data = (
                                "INVALID_PAGE_NUMBER: "
                                f"requested {page_number}, total pages {pdf_total_pages}"
                            )
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("INVALID_PAGE_NUMBER")
                            continue

                        logger.info("Page number requested for navigation: %s", page_number)

                        try:
                            citation_page.navigate_to_page(page_number)
                        except Exception as nav_exc:
                            logger.exception(
                                "PDF_NAVIGATION_FAILED citation=%s document=%s page=%s url=%s error=%s",
                                citation_number,
                                document_name,
                                page_number,
                                citation_page.source_url,
                                nav_exc,
                            )
                            page_pdf_data = f"PDF_NAVIGATION_FAILED: {nav_exc}"
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("PDF_NAVIGATION_FAILED")
                            continue

                        current_pdf_page = citation_page.get_current_pdf_page_number()
                        logger.info("Page navigation succeeded: %s", current_pdf_page == page_number)
                        logger.info("Actual page opened after navigation: %s", current_pdf_page)

                        if current_pdf_page != page_number:
                            logger.error(
                                "PDF_NAVIGATION_FAILED document=%s expected=%s actual=%s url=%s",
                                document_name,
                                page_number,
                                current_pdf_page,
                                citation_page.source_url,
                            )
                            page_pdf_data = (
                                "PDF_NAVIGATION_FAILED: "
                                f"expected {page_number}, current {current_pdf_page}"
                            )
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("PDF_NAVIGATION_FAILED")
                            continue

                        try:
                            page_pdf_data = citation_page.extract_page_data_from_pdf()
                        except Exception as extract_exc:
                            logger.exception(
                                "PAGE_TEXT_EXTRACTION_FAILED citation=%s document=%s page=%s url=%s error=%s",
                                citation_number,
                                document_name,
                                page_number,
                                citation_page.source_url,
                                extract_exc,
                            )
                            page_pdf_data = f"PAGE_TEXT_EXTRACTION_FAILED: {extract_exc}"
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("PAGE_TEXT_EXTRACTION_FAILED")
                            continue

                        if not page_pdf_data.strip() or page_pdf_data == "NO PAGE DATA AVAILABLE":
                            logger.error(
                                "PAGE_TEXT_EXTRACTION_FAILED document=%s page=%s url=%s preview=%s",
                                document_name,
                                page_number,
                                citation_page.source_url,
                                page_pdf_data[:200],
                            )
                            page_pdf_data = "PAGE_TEXT_EXTRACTION_FAILED"
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("PAGE_TEXT_EXTRACTION_FAILED")
                            continue

                        evidence_ok, evidence_reason = _validate_evidence_before_openai(
                            document_opened=citation_page.source_page is not None,
                            pdf_url=citation_page.source_url,
                            page_number=page_number,
                            total_pages=pdf_total_pages,
                            page_text=page_pdf_data,
                            product_name=product_name,
                            question=question,
                        )
                        logger.info("Evidence quality status: %s", evidence_reason)

                        if evidence_ok and (
                            evidence_reason.startswith("WEAK_PAGE_TEXT_ACCEPTED")
                            or evidence_reason.startswith("LOW_TOPIC_CONFIDENCE")
                        ):
                            logger.warning(
                                "PARTIAL_EVIDENCE citation=%s page=%s text_len=%s reason=%s — "
                                "searching all text for attribute before accepting DATA MISSING",
                                citation_number,
                                page_number,
                                len(page_pdf_data),
                                evidence_reason,
                            )
                            page_pdf_data = (
                                "[NOTE: OCR extraction of this PDF page is partial or incomplete "
                                "(likely an image-based table). "
                                "Do NOT immediately return DATA MISSING. Instead: "
                                "1) Search all available text for the requested attribute. "
                                "2) Search nearby rows and table structures for the value. "
                                "3) Look for numeric values, product names, or keywords in any form. "
                                "4) Attempt semantic recovery from partial or fragmented content. "
                                "Only return DATA MISSING if the attribute is truly absent from "
                                "all available text after exhausting all recovery attempts.]\n"
                                + page_pdf_data
                            )

                        if not evidence_ok:
                            logger.error(
                                "EVIDENCE_QUALITY_FAILED citation=%s page=%s reason=%s",
                                citation_number,
                                page_number,
                                evidence_reason,
                            )
                            page_pdf_data = f"{evidence_reason} Extracted preview: {page_pdf_data[:300]}"
                            logger.info("Validation result for citation %s: DATA MISSING", citation_number)
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "DATA MISSING",
                                }
                            )
                            page_results.append("DATA MISSING")
                            page_reasons.append(evidence_reason)
                            continue

                        answer_values = extract_answer_values(response)
                        matched_values = extract_matching_values(response, page_pdf_data)
                        logger.info("Cited page number used for validation: %s", page_number)
                        logger.info("Extracted text from cited page %s: %s", page_number, page_pdf_data)
                        logger.info("First 500 characters extracted from the page: %s", page_pdf_data[:500])
                        logger.info("SuperAI values checked: %s", answer_values)
                        logger.info("Final value found on the page: %s", matched_values or "NONE")
                        logger.info("Value extracted from page: %s", matched_values or "NONE")
                        logger.info("Super AI value: %s", answer_values or "NONE")

                        if holistic_validation:
                            logger.info(
                                "Citation %s collected for multi-citation claim-level validation.",
                                citation_number,
                            )
                            page_results.append("COLLECTED")
                            page_reasons.append(
                                "Cited page collected for multi-citation claim-level validation."
                            )
                            extracted_pages.append(
                                (
                                    f"Citation {audit_citation_number} | Document {document_name} | "
                                    f"Page {page_number}: {page_pdf_data}"
                                )
                            )
                            citation_audit_rows.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "result": "COLLECTED",
                                }
                            )
                            continue

                        (
                            numeric_applicable,
                            numeric_result,
                            numeric_reason,
                            numeric_matched_values,
                        ) = deterministic_numeric_validation(
                            response,
                            page_pdf_data,
                            question,
                        )
                        fallback_page_result = compare_ai_vs_pdf(response, page_pdf_data, question)
                        fallback_page_reason = explain_ai_vs_pdf(response, page_pdf_data, question)

                        use_numeric_first = _should_use_numeric_first_validation(question)
                        if numeric_applicable and use_numeric_first:
                            logger.info(
                                "Using deterministic numeric validation result before OpenAI: %s",
                                numeric_result,
                            )
                            page_result = numeric_result
                            page_reason = numeric_reason
                            matched_values = numeric_matched_values or matched_values
                        elif (
                            fallback_page_result == "PASS"
                            and (
                                _is_rule_based_competitor_reasoning_question(question)
                                or (numeric_applicable and use_numeric_first)
                            )
                        ):
                            logger.info(
                                "Using deterministic validation PASS; skipping OpenAI for speed."
                            )
                            page_result = fallback_page_result
                            page_reason = (
                                numeric_reason if numeric_applicable else fallback_page_reason
                            )
                            matched_values = numeric_matched_values or matched_values
                        elif use_openai_validation:
                            openai_decision = validate_with_openai(
                                question=question,
                                super_ai_response=response,
                                cited_page_text=page_pdf_data,
                                product_name=product_name,
                                page_number=page_number,
                                document_name=document_name,
                            )
                            if openai_decision.get("engine") == "openai":
                                page_result = str(openai_decision["result"])
                                page_reason = str(openai_decision["reason"])
                                if page_result == "PASS" and _reason_contains_failure_contradiction(page_reason):
                                    logger.warning(
                                        "OpenAI returned PASS but reason contains contradiction/failure wording. "
                                        "Overriding to FAIL. Reason=%s",
                                        page_reason,
                                    )
                                    page_result = "FAIL"
                                matched_values = str(
                                    openai_decision.get("matched_value") or matched_values
                                )
                                logger.info(
                                    "OpenAI requested attribute: %s",
                                    openai_decision.get("requested_attribute") or "UNKNOWN",
                                )
                                logger.info(
                                    "OpenAI SuperAI values: %s",
                                    openai_decision.get("super_ai_values") or [],
                                )
                                logger.info(
                                    "OpenAI document values: %s",
                                    openai_decision.get("document_values") or [],
                                )
                                if (
                                    (
                                        _is_competitor_brand_question(question)
                                        or _is_dosage_question(question)
                                    )
                                    and fallback_page_result == "PASS"
                                    and page_result != "PASS"
                                ):
                                    logger.warning(
                                        "OpenAI/deterministic validator disagreement. "
                                        "Using deterministic page-scoped PASS. OpenAI result=%s reason=%s",
                                        page_result,
                                        page_reason,
                                    )
                                    page_result = fallback_page_result
                                    page_reason = fallback_page_reason
                                    matched_values = extract_matching_values(
                                        response,
                                        page_pdf_data,
                                    )
                            else:
                                logger.warning(
                                    "OpenAI validation unavailable; using rule-based fallback: %s",
                                    openai_decision.get("reason"),
                                )
                                page_result = fallback_page_result
                                page_reason = fallback_page_reason
                        else:
                            page_result = fallback_page_result
                            page_reason = fallback_page_reason
                        logger.info(
                            "Validation result for citation %s: %s",
                            citation_number,
                            page_result,
                        )
                        logger.info(
                            "Validation reason for citation %s: %s",
                            citation_number,
                            page_reason,
                        )
                        page_results.append(page_result)
                        page_reasons.append(page_reason)
                        extracted_pages.append(
                            (
                                f"Citation {audit_citation_number} | Document {document_name} | "
                                f"Page {page_number}: {page_pdf_data}"
                            )
                        )
                        citation_audit_rows.append(
                            {
                                "citation": audit_citation_number,
                                "document": document_name,
                                "page": page_number,
                                "evidence": page_pdf_data,
                                "result": page_result,
                            }
                        )

                        if page_result == "PASS":
                            validation_result = "PASS"
                            reason = page_reason
                            pass_audits.append(
                                {
                                    "citation": audit_citation_number,
                                    "document": document_name,
                                    "page": page_number,
                                    "evidence": page_pdf_data,
                                    "reason": page_reason,
                                }
                            )
                    finally:
                        citation_page.close_source_document()
                        citation_page.close_citation_panel()

                page_number = "; ".join(page_numbers_checked)
                citation_details = "\n".join(citation_details_checked)
                logger.info(
                    "CITATION_AUDIT_SUMMARY processed=%s pass=%s fail=%s data_missing=%s",
                    len(citation_audit_rows),
                    page_results.count("PASS"),
                    page_results.count("FAIL"),
                    len(
                        [
                            result
                            for result in page_results
                            if result not in ("PASS", "FAIL", "COLLECTED")
                        ]
                    ),
                )
                if holistic_validation:
                    all_pdf_data = "\n\n".join(extracted_pages)
                    usable_extracted_pages = _usable_citation_evidence_pages(extracted_pages)
                    usable_pdf_data = "\n\n".join(usable_extracted_pages)
                    pdf_data = all_pdf_data
                    logger.info(
                        "HOLISTIC_USABLE_CITATIONS = %s of %s",
                        len(usable_extracted_pages),
                        len(extracted_pages),
                    )
                    if not extracted_pages:
                        validation_result = "DATA MISSING"
                        reason = "No cited page text was available for multi-citation claim-level validation."
                    elif not usable_extracted_pages:
                        validation_result = "DATA MISSING"
                        reason = (
                            "No usable cited page text was available; all cited sources failed "
                            "to open, navigate, or extract meaningful text."
                        )
                    elif use_openai_validation:
                        (
                            numeric_applicable,
                            numeric_result,
                            numeric_reason,
                            numeric_matched_values,
                        ) = deterministic_numeric_validation(
                            response,
                            usable_pdf_data,
                            question,
                        )
                        use_numeric_first = _should_use_numeric_first_validation(question)
                        if numeric_applicable and use_numeric_first:
                            validation_result = numeric_result
                            reason = numeric_reason
                            matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                            matched_document = _citation_list_str(citation_audit_rows, "document")
                            matched_page = _citation_list_str(citation_audit_rows, "page")
                            matched_evidence = " | ".join(
                                _evidence_preview(str(a["evidence"])) for a in citation_audit_rows
                            )
                            logger.info(
                                "Holistic deterministic numeric validation result before OpenAI: %s",
                                numeric_result,
                            )
                            logger.info(
                                "Holistic deterministic numeric matched values: %s",
                                numeric_matched_values or "NONE",
                            )
                            # results.append(
                            #     _result_row(
                            #         row,
                            #         question,
                            #         response,
                            #         page_number,
                            #         all_pdf_data,
                            #         validation_result,
                            #         reason,
                            #         citation_details,
                            #         matched_citation,
                            #         matched_document,
                            #         matched_page,
                            #         matched_evidence,
                            #     )
                            # )
                            results.append(
                                _result_row(
                                    row,
                                    question,
                                    response,
                                    page_number,
                                    pdf_data,
                                    validation_result,
                                    reason,
                                    _failure_source(
                                        validation_result,
                                        reason,
                                        response,
                                    ),
                                    citation_details,
                                    matched_citation,
                                    matched_document,
                                    matched_page,
                                    matched_evidence,
                                )
                            )
                            continue
                        holistic_decision = validate_with_openai(
                            question=question,
                            super_ai_response=response,
                            cited_page_text=usable_pdf_data,
                            product_name=product_name,
                            page_number=page_number,
                            document_name="MULTIPLE CITED SOURCES",
                        )
                        if holistic_decision.get("engine") == "openai":
                            validation_result = str(holistic_decision["result"])
                            reason = str(holistic_decision["reason"])
                            if validation_result == "PASS" and _reason_contains_failure_contradiction(reason):
                                logger.warning(
                                    "OpenAI returned holistic PASS but reason contains contradiction/failure wording. "
                                    "Overriding to FAIL. Reason=%s",
                                    reason,
                                )
                                validation_result = "FAIL"
                            matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                            matched_document = _citation_list_str(citation_audit_rows, "document")
                            matched_page = _citation_list_str(citation_audit_rows, "page")
                            matched_evidence = _evidence_preview(
                                str(holistic_decision.get("matched_value") or "")
                                or usable_pdf_data
                            )
                            logger.info(
                                "Holistic OpenAI requested attribute: %s",
                                holistic_decision.get("requested_attribute") or "KNOWLEDGE_MODE",
                            )
                            logger.info(
                                "Holistic OpenAI SuperAI values/claims: %s",
                                holistic_decision.get("super_ai_values") or [],
                            )
                            logger.info(
                                "Holistic OpenAI document values/evidence: %s",
                                holistic_decision.get("document_values") or [],
                            )
                        else:
                            fallback_result = compare_ai_vs_pdf(
                                response,
                                usable_pdf_data,
                                question,
                            )
                            validation_result = fallback_result
                            reason = explain_ai_vs_pdf(
                                response,
                                usable_pdf_data,
                                question,
                            )
                            if validation_result == "DATA MISSING":
                                reason = (
                                    "Multi-citation OpenAI validation could not run: "
                                    f"{holistic_decision.get('reason')}. "
                                    f"Rule-based fallback result: {reason}"
                                )
                            matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                            matched_document = _citation_list_str(citation_audit_rows, "document")
                            matched_page = _citation_list_str(citation_audit_rows, "page")
                            matched_evidence = _evidence_preview(usable_pdf_data)
                    else:
                        validation_result = compare_ai_vs_pdf(
                            response,
                            usable_pdf_data,
                            question,
                        )
                        reason = explain_ai_vs_pdf(
                            response,
                            usable_pdf_data,
                            question,
                        )
                        if validation_result == "DATA MISSING":
                            reason = (
                                "OpenAI validation is unavailable; rule-based fallback "
                                f"could not fully validate the cited evidence. {reason}"
                            )
                        matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                        matched_document = _citation_list_str(citation_audit_rows, "document")
                        matched_page = _citation_list_str(citation_audit_rows, "page")
                        matched_evidence = _evidence_preview(usable_pdf_data)
                elif validation_result == "PASS" and pass_audits:
                    pdf_data = "\n\n".join(extracted_pages)
                    matched_citation = " | ".join(
                        f"Citation {a['citation']}" for a in pass_audits
                    )
                    matched_document = " | ".join(
                        str(a["document"]) for a in pass_audits
                    )
                    matched_page = " | ".join(
                        str(a["page"]) for a in pass_audits
                    )
                    matched_evidence = " | ".join(
                        _evidence_preview(str(a["evidence"])) for a in pass_audits
                    )
                    reason = str(pass_audits[-1]["reason"])
                elif validation_result != "PASS":
                    pdf_data = "\n\n".join(extracted_pages)
                    usable_extracted_pages = _usable_citation_evidence_pages(extracted_pages)
                    usable_pdf_data = "\n\n".join(usable_extracted_pages)
                    if len(usable_extracted_pages) > 1 and _should_combine_non_holistic_citations(
                        question
                    ):
                        logger.info(
                            "Running combined-citation validation for non-holistic question using %s cited pages.",
                            len(usable_extracted_pages),
                        )
                        combined_result = compare_ai_vs_pdf(
                            response,
                            usable_pdf_data,
                            question,
                        )
                        combined_reason = explain_ai_vs_pdf(
                            response,
                            usable_pdf_data,
                            question,
                        )
                        logger.info(
                            "Combined-citation validation result: %s | reason: %s",
                            combined_result,
                            combined_reason,
                        )
                        if combined_result == "PASS":
                            validation_result = "PASS"
                            reason = combined_reason
                            matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                            matched_document = _citation_list_str(citation_audit_rows, "document")
                            matched_page = _citation_list_str(citation_audit_rows, "page")
                            matched_evidence = _evidence_preview(usable_pdf_data)
                        elif combined_result == "FAIL":
                            validation_result = "FAIL"
                            reason = combined_reason
                            matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                            matched_document = _citation_list_str(citation_audit_rows, "document")
                            matched_page = _citation_list_str(citation_audit_rows, "page")
                            matched_evidence = _evidence_preview(usable_pdf_data)
                        else:
                            validation_result = "DATA MISSING"
                            reason = combined_reason
                            matched_citation = _citation_list_str(citation_audit_rows, "citation", "Citation ")
                            matched_document = _citation_list_str(citation_audit_rows, "document")
                            matched_page = _citation_list_str(citation_audit_rows, "page")
                            matched_evidence = _evidence_preview(usable_pdf_data)
                    elif "FAIL" in page_results:
                        validation_result = "FAIL"
                        fail_audits = [
                            citation_audit_rows[i]
                            for i, r in enumerate(page_results)
                            if r == "FAIL" and i < len(citation_audit_rows)
                        ]
                        fail_index = page_results.index("FAIL")
                        reason = page_reasons[fail_index] if fail_index < len(page_reasons) else _validation_reason("FAIL")
                        if fail_audits:
                            matched_citation = " | ".join(
                                f"Citation {a['citation']}" for a in fail_audits
                            )
                            matched_document = " | ".join(
                                str(a["document"]) for a in fail_audits
                            )
                            matched_page = " | ".join(
                                str(a["page"]) for a in fail_audits
                            )
                            matched_evidence = " | ".join(
                                _evidence_preview(str(a["evidence"])) for a in fail_audits
                            )
                    elif page_results:
                        validation_result = "DATA MISSING"
                        reason = page_reasons[-1] if page_reasons else _validation_reason("DATA MISSING")
                        if citation_audit_rows:
                            matched_citation = " | ".join(
                                f"Citation {a['citation']}" for a in citation_audit_rows
                            )
                            matched_document = " | ".join(
                                str(a["document"]) for a in citation_audit_rows
                            )
                            matched_page = " | ".join(
                                str(a["page"]) for a in citation_audit_rows
                            )
                            matched_evidence = " | ".join(
                                _evidence_preview(str(a["evidence"])) for a in citation_audit_rows
                            )
                    else:
                        validation_result = "DATA MISSING"
                        reason = "Citation page number could not be extracted."

            except Exception as question_exc:
                logger.exception(
                    "Validation failed for question %s: %s",
                    index,
                    question_exc,
                )
                pdf_data = f"VALIDATION ERROR: {question_exc}"
                validation_result = "DATA MISSING"
                reason = f"Validation error: {question_exc}"
                citation_page.close_source_document()

            results.append(
                _result_row(
                    row,
                    question,
                    response,
                    page_number,
                    pdf_data,
                    validation_result,
                    reason,
                    citation_details,
                    matched_citation,
                    matched_document,
                    matched_page,
                    matched_evidence,
                )
            )

        output_report_path = write_csv_rows(OUTPUT_RESULTS_FILE, results)
        if output_report_path:
            logger.info("Responses saved to %s", output_report_path)

    except Exception as exc:
        logger.exception("Question validation test failed: %s", exc)

        if page:
            screenshot_path = capture_screenshot(page, "question_failure")
            logger.error("Failure screenshot captured: %s", screenshot_path)

        raise

    finally:
        browser_manager.close_browser()


if __name__ == "__main__":
    test_ask_questions_and_save_responses()