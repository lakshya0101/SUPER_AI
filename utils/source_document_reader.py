# # """Parser-backed source PDF reader for page-level validation."""

# # from io import BytesIO
# # from functools import lru_cache
# # import os
# # import re
# # from shutil import which
# # from urllib.parse import urldefrag
# # from urllib.request import urlopen

# # from pypdf import PdfReader

# # from utils.logger import get_logger


# # MIN_USEFUL_PAGE_TEXT_LENGTH = 30
# # WEAK_PAGE_TEXTS = {
# #     "visual aid communication",
# #     "no page data available",
# # }


# # def _vision_extraction_enabled() -> bool:
# #     """Return whether GPT-4o Vision extraction is enabled via env var."""
# #     return os.getenv("VISION_EXTRACTION_ENABLED", "1").strip().lower() not in {
# #         "0", "false", "no", "off",
# #     }


# # def extract_pdf_page_text_from_url(
# #     url: str,
# #     page_number: int,
# #     document_name: str = "",
# # ) -> str:
# #     """Extract text from one PDF page only using parser fallbacks."""
# #     if page_number < 1:
# #         return ""

# #     logger = get_logger("source_document_reader")
# #     normalized_url = _normalize_pdf_url(url)
# #     pdf_bytes = _get_pdf_bytes(normalized_url)
# #     context = _log_context(document_name, normalized_url, page_number)

# #     logger.info("PDF_EXTRACTION_START %s", context)

# #     base_attempts = [
# #         ("pypdf", lambda: _extract_page_text_with_pypdf(pdf_bytes, page_number)),
# #         ("pymupdf", lambda: _extract_page_text_with_pymupdf(pdf_bytes, page_number)),
# #         ("ocr", lambda: _extract_page_text_with_ocr(pdf_bytes, page_number)),
# #     ]
# #     # Vision is the most expensive method — only run it when cheaper methods fail.
# #     if _vision_extraction_enabled():
# #         base_attempts.append(
# #             ("vision", lambda: _extract_page_text_with_vision(pdf_bytes, page_number))
# #         )
# #     extraction_attempts = tuple(base_attempts)

# #     best_text = ""
# #     best_method = ""

# #     for method_name, extractor in extraction_attempts:
# #         try:
# #             page_text = _normalize_text(extractor())
# #         except Exception as exc:
# #             logger.warning(
# #                 "PDF_EXTRACTION_METHOD_FAILED method=%s %s error=%s",
# #                 method_name,
# #                 context,
# #                 exc,
# #             )
# #             continue

# #         logger.info(
# #             "PDF_EXTRACTION_METHOD method=%s %s text_length=%s weak=%s preview=%s",
# #             method_name,
# #             context,
# #             len(page_text),
# #             is_weak_pdf_page_text(page_text),
# #             page_text[:200],
# #         )

# #         if len(page_text) > len(best_text):
# #             best_text = page_text
# #             best_method = method_name

# #         if not is_weak_pdf_page_text(page_text):
# #             logger.info(
# #                 "PDF_EXTRACTION_SELECTED method=%s %s text_length=%s",
# #                 method_name,
# #                 context,
# #                 len(page_text),
# #             )
# #             return page_text

# #     logger.warning(
# #         "PAGE_TEXT_EXTRACTION_FAILED %s best_method=%s best_length=%s best_preview=%s",
# #         context,
# #         best_method or "NONE",
# #         len(best_text),
# #         best_text[:200],
# #     )
# #     return best_text


# # def is_weak_pdf_page_text(text: str) -> bool:
# #     """Return whether extracted page text is too weak for validation."""
# #     cleaned = _normalize_text(text)

# #     if not cleaned:
# #         return True

# #     lowered = cleaned.lower().strip()

# #     if lowered in WEAK_PAGE_TEXTS:
# #         return True

# #     if re.fullmatch(r"\d+", lowered):
# #         return True

# #     if len(cleaned) < MIN_USEFUL_PAGE_TEXT_LENGTH:
# #         return True

# #     if not re.search(r"[a-zA-Z]", cleaned):
# #         return True

# #     return False


# # def get_pdf_page_count_from_url(url: str) -> int:
# #     """Return total number of pages in the source PDF."""
# #     reader = _get_pdf_reader(_normalize_pdf_url(url))
# #     return len(reader.pages)


# # def extract_pdf_text_from_url(url: str, page_hint: int | None = None) -> str:
# #     """Backward-compatible parser API.

# #     When page_hint is provided, only that page is parsed. Full-document parsing is
# #     intentionally unavailable for validation to prevent cross-page matching.
# #     """
# #     if page_hint is None:
# #         raise ValueError("page_hint is required for page-level PDF validation.")

# #     return extract_pdf_page_text_from_url(url, page_hint)


# # def _log_context(document_name: str, url: str, page_number: int) -> str:
# #     """Return stable context for extraction logs."""
# #     safe_document_name = _normalize_text(document_name) or "UNKNOWN_DOCUMENT"
# #     return (
# #         f"document={safe_document_name!r} "
# #         f"page={page_number} "
# #         f"url={url!r}"
# #     )


# # @lru_cache(maxsize=16)
# # def _get_pdf_bytes(url: str) -> bytes:
# #     """Download PDF bytes once per source URL for faster repeated validation."""
# #     with urlopen(url, timeout=60) as response:  # nosec B310
# #         return response.read()


# # @lru_cache(maxsize=16)
# # def _get_pdf_reader(url: str) -> PdfReader:
# #     """Return a cached PdfReader for the source URL."""
# #     return PdfReader(BytesIO(_get_pdf_bytes(url)))


# # def _extract_page_text_with_pypdf(pdf_bytes: bytes, page_number: int) -> str:
# #     """Extract page text with pypdf."""
# #     reader = PdfReader(BytesIO(pdf_bytes))

# #     if not reader.pages or page_number > len(reader.pages):
# #         return ""

# #     return reader.pages[page_number - 1].extract_text() or ""


# # def _extract_page_text_with_pymupdf(pdf_bytes: bytes, page_number: int) -> str:
# #     """Extract page text with PyMuPDF when available."""
# #     try:
# #         import fitz
# #     except ImportError:
# #         return ""

# #     with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
# #         if page_number > document.page_count:
# #             return ""

# #         page = document.load_page(page_number - 1)
# #         return page.get_text("text") or ""


# # def _extract_page_text_with_ocr(pdf_bytes: bytes, page_number: int) -> str:
# #     """OCR one PDF page only when optional OCR dependencies are available."""
# #     logger = get_logger("source_document_reader")

# #     try:
# #         import fitz
# #         import pytesseract
# #         from PIL import Image
# #     except ImportError:
# #         logger.warning(
# #             "OCR extraction skipped because PyMuPDF, pytesseract, or Pillow is not installed."
# #         )
# #         return ""

# #     if not which("tesseract"):
# #         logger.warning(
# #             "OCR extraction skipped because the Tesseract OCR engine is not installed or not on PATH."
# #         )
# #         return ""

# #     with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
# #         if page_number > document.page_count:
# #             return ""

# #         page = document.load_page(page_number - 1)
# #         matrix = fitz.Matrix(2, 2)
# #         pixmap = page.get_pixmap(matrix=matrix, alpha=False)
# #         image = Image.open(BytesIO(pixmap.tobytes("png")))
# #         try:
# #             return pytesseract.image_to_string(image) or ""
# #         except pytesseract.TesseractNotFoundError:
# #             logger.warning(
# #                 "OCR extraction skipped because pytesseract could not find the Tesseract OCR engine."
# #             )
# #             return ""


# # def _extract_page_text_with_vision(pdf_bytes: bytes, page_number: int) -> str:
# #     """Extract page text using Azure OpenAI Vision when all text methods fail.

# #     Renders the PDF page as a high-resolution PNG and asks a vision model to
# #     transcribe every visible character, including image-embedded tables.
# #     Only runs when VISION_EXTRACTION_ENABLED is not disabled and Azure OpenAI
# #     Vision credentials are configured.
# #     """
# #     logger = get_logger("source_document_reader")

# #     try:
# #         import fitz
# #     except ImportError:
# #         logger.warning(
# #             "VISION_EXTRACTION_SKIPPED reason=PyMuPDF_not_installed "
# #             "fix='pip install pymupdf'"
# #         )
# #         return ""

# #     try:
# #         from openai import AzureOpenAI
# #     except ImportError:
# #         logger.warning(
# #             "VISION_EXTRACTION_SKIPPED reason=openai_package_not_installed "
# #             "fix='pip install openai'"
# #         )
# #         return ""

# #     import base64

# #     try:
# #         from dotenv import load_dotenv
# #         load_dotenv()
# #     except ImportError:
# #         pass

# #     api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
# #     endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
# #     # Prefer a dedicated vision deployment; fall back to the text deployment.
# #     # Set AZURE_OPENAI_VISION_DEPLOYMENT to a vision-capable model (e.g. gpt-4o).
# #     # If AZURE_OPENAI_DEPLOYMENT is already a vision-capable model, that works too.
# #     vision_deployment = (
# #         os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT")
# #         or os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
# #     ).strip()
# #     api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip()

# #     if not api_key:
# #         logger.warning("VISION_EXTRACTION_SKIPPED reason=AZURE_OPENAI_API_KEY_not_set")
# #         return ""
# #     if not endpoint:
# #         logger.warning("VISION_EXTRACTION_SKIPPED reason=AZURE_OPENAI_ENDPOINT_not_set")
# #         return ""
# #     if not vision_deployment:
# #         logger.warning(
# #             "VISION_EXTRACTION_SKIPPED reason=no_vision_deployment_configured "
# #             "fix='Set AZURE_OPENAI_VISION_DEPLOYMENT in .env to a vision-capable model "
# #             "(e.g. gpt-4o). If your AZURE_OPENAI_DEPLOYMENT already supports vision, "
# #             "set AZURE_OPENAI_VISION_DEPLOYMENT to the same value.'"
# #         )
# #         return ""

# #     logger.info(
# #         "VISION_EXTRACTION_START page=%s deployment=%s endpoint=%s",
# #         page_number, vision_deployment, endpoint,
# #     )

# #     # Render the page at 2\u00d7 resolution for crisp OCR of small table text.
# #     try:
# #         with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
# #             if page_number > document.page_count:
# #                 return ""
# #             pdf_page = document.load_page(page_number - 1)
# #             pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
# #             image_b64 = base64.b64encode(pixmap.tobytes("png")).decode("utf-8")
# #             image_size_kb = round(len(image_b64) * 3 / 4 / 1024)
# #     except Exception as exc:
# #         logger.error(
# #             "VISION_EXTRACTION_RENDER_FAILED page=%s error=%s", page_number, exc,
# #             exc_info=True,
# #         )
# #         return ""

# #     logger.info(
# #         "VISION_EXTRACTION_IMAGE_READY page=%s size_kb=%s",
# #         page_number, image_size_kb,
# #     )

# #     system_prompt = (
# #         "You are a document text extractor. "
# #         "Your sole task is to faithfully transcribe ALL visible text from the image, "
# #         "especially the contents of tables. "
# #         "For every table row output the cells separated by ' | ' on a single line. "
# #         "Include every header row, every data row, every number, label, and symbol "
# #         "exactly as written \u2014 do not omit, summarise, or paraphrase anything. "
# #         "Output plain text only; no markdown, no bullet points, no extra commentary."
# #     )
# #     user_prompt = (
# #         "Extract every piece of text from this PDF page, "
# #         "including all table rows and individual cell values:"
# #     )

# #     try:
# #         client = AzureOpenAI(
# #             api_key=api_key,
# #             azure_endpoint=endpoint,
# #             api_version=api_version,
# #             timeout=60,
# #         )
# #         completion = client.chat.completions.create(
# #             model=vision_deployment,
# #             temperature=0,
# #             max_tokens=2000,
# #             messages=[
# #                 {"role": "system", "content": system_prompt},
# #                 {
# #                     "role": "user",
# #                     "content": [
# #                         {"type": "text", "text": user_prompt},
# #                         {
# #                             "type": "image_url",
# #                             "image_url": {
# #                                 "url": f"data:image/png;base64,{image_b64}",
# #                                 "detail": "high",
# #                             },
# #                         },
# #                     ],
# #                 },
# #             ],
# #         )
# #         extracted = (completion.choices[0].message.content or "").strip()
# #         logger.info(
# #             "VISION_EXTRACTION_SUCCESS page=%s deployment=%s length=%s preview=%r",
# #             page_number, vision_deployment, len(extracted), extracted[:300],
# #         )
# #         return extracted
# #     except Exception as exc:
# #         # Log at ERROR so the failure is visible in the console.
# #         # Common causes:
# #         #   - "model does not support image inputs" \u2192 AZURE_OPENAI_VISION_DEPLOYMENT
# #         #     must point to a vision-capable model (gpt-4o, gpt-4-turbo, etc.)
# #         #   - 404 DeploymentNotFound \u2192 deployment name is wrong
# #         #   - 401 Unauthorized \u2192 API key expired or wrong endpoint
# #         logger.error(
# #             "VISION_EXTRACTION_API_FAILED page=%s deployment=%s endpoint=%s "
# #             "error_type=%s error=%s | "
# #             "If you see 'model does not support image inputs', set "
# #             "AZURE_OPENAI_VISION_DEPLOYMENT in .env to a vision-capable deployment "
# #             "(e.g. gpt-4o). Current deployment: %s",
# #             page_number, vision_deployment, endpoint,
# #             type(exc).__name__, exc,
# #             vision_deployment,
# #         )
# #         return ""


# # def _normalize_pdf_url(url: str) -> str:
# #     """Remove viewer fragments such as #page=12 before downloading the PDF."""
# #     normalized_url, _ = urldefrag(url)
# #     return normalized_url


# # def _normalize_text(text: str) -> str:
# #     """Normalize parser output for stable CSV and validation matching."""
# #     return " ".join(text.replace("\u00a0", " ").split())


# """Parser-backed source PDF reader for page-level validation."""

# from io import BytesIO
# from functools import lru_cache
# import os
# import re
# from shutil import which
# from urllib.parse import urldefrag
# from urllib.request import urlopen

# from pypdf import PdfReader

# from utils.logger import get_logger


# MIN_USEFUL_PAGE_TEXT_LENGTH = 30
# WEAK_PAGE_TEXTS = {
#     "visual aid communication",
#     "no page data available",
# }


# def _vision_extraction_enabled() -> bool:
#     """Return whether GPT-4o Vision extraction is enabled via env var."""
#     return os.getenv("VISION_EXTRACTION_ENABLED", "1").strip().lower() not in {
#         "0", "false", "no", "off",
#     }


# def extract_pdf_page_text_from_url(
#     url: str,
#     page_number: int,
#     document_name: str = "",
# ) -> str:
#     """Extract text from one PDF page only using parser fallbacks."""
#     if page_number < 1:
#         return ""

#     logger = get_logger("source_document_reader")
#     normalized_url = _normalize_pdf_url(url)
#     pdf_bytes = _get_pdf_bytes(normalized_url)
#     context = _log_context(document_name, normalized_url, page_number)

#     logger.info("PDF_EXTRACTION_START %s", context)

#     base_attempts = [
#         ("pypdf", lambda: _extract_page_text_with_pypdf(pdf_bytes, page_number)),
#         ("pymupdf", lambda: _extract_page_text_with_pymupdf(pdf_bytes, page_number)),
#         ("ocr", lambda: _extract_page_text_with_ocr(pdf_bytes, page_number)),
#     ]
#     # Vision is the most expensive method — only run it when cheaper methods fail.
#     if _vision_extraction_enabled():
#         base_attempts.append(
#             ("vision", lambda: _extract_page_text_with_vision(pdf_bytes, page_number))
#         )
#     extraction_attempts = tuple(base_attempts)

#     best_text = ""
#     best_method = ""

#     for method_name, extractor in extraction_attempts:
#         try:
#             page_text = _normalize_text(extractor())
#         except Exception as exc:
#             logger.warning(
#                 "PDF_EXTRACTION_METHOD_FAILED method=%s %s error=%s",
#                 method_name,
#                 context,
#                 exc,
#             )
#             continue

#         logger.info(
#             "PDF_EXTRACTION_METHOD method=%s %s text_length=%s weak=%s preview=%s",
#             method_name,
#             context,
#             len(page_text),
#             is_weak_pdf_page_text(page_text),
#             page_text[:200],
#         )

#         if len(page_text) > len(best_text):
#             best_text = page_text
#             best_method = method_name

#         if not is_weak_pdf_page_text(page_text):
#             logger.info(
#                 "PDF_EXTRACTION_SELECTED method=%s %s text_length=%s",
#                 method_name,
#                 context,
#                 len(page_text),
#             )
#             return page_text

#     logger.warning(
#         "PAGE_TEXT_EXTRACTION_FAILED %s best_method=%s best_length=%s best_preview=%s | "
#         "DIAGNOSIS: All extraction methods returned weak/empty text. "
#         "Possible causes: (1) image-only PDF page - enable VISION_EXTRACTION_ENABLED=1 "
#         "and set AZURE_OPENAI_VISION_DEPLOYMENT; (2) encrypted PDF; (3) page index "
#         "off-by-one (check if page_number=%s is correct); (4) table with no selectable "
#         "text. Validator will fall back to OpenAI with partial text.",
#         context,
#         best_method or "NONE",
#         len(best_text),
#         best_text[:200],
#         page_number,
#     )
#     return best_text


# def is_weak_pdf_page_text(text: str) -> bool:
#     """Return whether extracted page text is too weak for validation."""
#     cleaned = _normalize_text(text)

#     if not cleaned:
#         return True

#     lowered = cleaned.lower().strip()

#     if lowered in WEAK_PAGE_TEXTS:
#         return True

#     if re.fullmatch(r"\d+", lowered):
#         return True

#     if len(cleaned) < MIN_USEFUL_PAGE_TEXT_LENGTH:
#         return True

#     if not re.search(r"[a-zA-Z]", cleaned):
#         return True

#     return False


# def get_pdf_page_count_from_url(url: str) -> int:
#     """Return total number of pages in the source PDF."""
#     reader = _get_pdf_reader(_normalize_pdf_url(url))
#     return len(reader.pages)


# def extract_pdf_text_from_url(url: str, page_hint: int | None = None) -> str:
#     """Backward-compatible parser API.

#     When page_hint is provided, only that page is parsed. Full-document parsing is
#     intentionally unavailable for validation to prevent cross-page matching.
#     """
#     if page_hint is None:
#         raise ValueError("page_hint is required for page-level PDF validation.")

#     return extract_pdf_page_text_from_url(url, page_hint)


# def _log_context(document_name: str, url: str, page_number: int) -> str:
#     """Return stable context for extraction logs."""
#     safe_document_name = _normalize_text(document_name) or "UNKNOWN_DOCUMENT"
#     return (
#         f"document={safe_document_name!r} "
#         f"page={page_number} "
#         f"url={url!r}"
#     )


# @lru_cache(maxsize=16)
# def _get_pdf_bytes(url: str) -> bytes:
#     """Download PDF bytes once per source URL for faster repeated validation."""
#     with urlopen(url, timeout=60) as response:  # nosec B310
#         return response.read()


# @lru_cache(maxsize=16)
# def _get_pdf_reader(url: str) -> PdfReader:
#     """Return a cached PdfReader for the source URL."""
#     return PdfReader(BytesIO(_get_pdf_bytes(url)))


# def _extract_page_text_with_pypdf(pdf_bytes: bytes, page_number: int) -> str:
#     """Extract page text with pypdf."""
#     reader = PdfReader(BytesIO(pdf_bytes))

#     if not reader.pages or page_number > len(reader.pages):
#         return ""

#     return reader.pages[page_number - 1].extract_text() or ""


# def _extract_page_text_with_pymupdf(pdf_bytes: bytes, page_number: int) -> str:
#     """Extract page text with PyMuPDF when available."""
#     try:
#         import fitz
#     except ImportError:
#         return ""

#     with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
#         if page_number > document.page_count:
#             return ""

#         page = document.load_page(page_number - 1)
#         return page.get_text("text") or ""


# def _extract_page_text_with_ocr(pdf_bytes: bytes, page_number: int) -> str:
#     """OCR one PDF page only when optional OCR dependencies are available."""
#     logger = get_logger("source_document_reader")

#     try:
#         import fitz
#         import pytesseract
#         from PIL import Image
#     except ImportError:
#         logger.warning(
#             "OCR extraction skipped because PyMuPDF, pytesseract, or Pillow is not installed."
#         )
#         return ""

#     if not which("tesseract"):
#         logger.warning(
#             "OCR extraction skipped because the Tesseract OCR engine is not installed or not on PATH."
#         )
#         return ""

#     with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
#         if page_number > document.page_count:
#             return ""

#         page = document.load_page(page_number - 1)
#         matrix = fitz.Matrix(2, 2)
#         pixmap = page.get_pixmap(matrix=matrix, alpha=False)
#         image = Image.open(BytesIO(pixmap.tobytes("png")))
#         try:
#             return pytesseract.image_to_string(image) or ""
#         except pytesseract.TesseractNotFoundError:
#             logger.warning(
#                 "OCR extraction skipped because pytesseract could not find the Tesseract OCR engine."
#             )
#             return ""


# def _extract_page_text_with_vision(pdf_bytes: bytes, page_number: int) -> str:
#     """Extract page text using Azure OpenAI Vision when all text methods fail.

#     Renders the PDF page as a high-resolution PNG and asks a vision model to
#     transcribe every visible character, including image-embedded tables.
#     Only runs when VISION_EXTRACTION_ENABLED is not disabled and Azure OpenAI
#     Vision credentials are configured.
#     """
#     logger = get_logger("source_document_reader")

#     try:
#         import fitz
#     except ImportError:
#         logger.warning(
#             "VISION_EXTRACTION_SKIPPED reason=PyMuPDF_not_installed "
#             "fix='pip install pymupdf'"
#         )
#         return ""

#     try:
#         from openai import AzureOpenAI
#     except ImportError:
#         logger.warning(
#             "VISION_EXTRACTION_SKIPPED reason=openai_package_not_installed "
#             "fix='pip install openai'"
#         )
#         return ""

#     import base64

#     try:
#         from dotenv import load_dotenv
#         load_dotenv()
#     except ImportError:
#         pass

#     api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
#     endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
#     # Prefer a dedicated vision deployment; fall back to the text deployment.
#     # Set AZURE_OPENAI_VISION_DEPLOYMENT to a vision-capable model (e.g. gpt-4o).
#     # If AZURE_OPENAI_DEPLOYMENT is already a vision-capable model, that works too.
#     vision_deployment = (
#         os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT")
#         or os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
#     ).strip()
#     api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip()

#     if not api_key:
#         logger.warning("VISION_EXTRACTION_SKIPPED reason=AZURE_OPENAI_API_KEY_not_set")
#         return ""
#     if not endpoint:
#         logger.warning("VISION_EXTRACTION_SKIPPED reason=AZURE_OPENAI_ENDPOINT_not_set")
#         return ""
#     if not vision_deployment:
#         logger.warning(
#             "VISION_EXTRACTION_SKIPPED reason=no_vision_deployment_configured "
#             "fix='Set AZURE_OPENAI_VISION_DEPLOYMENT in .env to a vision-capable model "
#             "(e.g. gpt-4o). If your AZURE_OPENAI_DEPLOYMENT already supports vision, "
#             "set AZURE_OPENAI_VISION_DEPLOYMENT to the same value.'"
#         )
#         return ""

#     logger.info(
#         "VISION_EXTRACTION_START page=%s deployment=%s endpoint=%s",
#         page_number, vision_deployment, endpoint,
#     )

#     # Render the page at 2\u00d7 resolution for crisp OCR of small table text.
#     try:
#         with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
#             if page_number > document.page_count:
#                 return ""
#             pdf_page = document.load_page(page_number - 1)
#             pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
#             image_b64 = base64.b64encode(pixmap.tobytes("png")).decode("utf-8")
#             image_size_kb = round(len(image_b64) * 3 / 4 / 1024)
#     except Exception as exc:
#         logger.error(
#             "VISION_EXTRACTION_RENDER_FAILED page=%s error=%s", page_number, exc,
#             exc_info=True,
#         )
#         return ""

#     logger.info(
#         "VISION_EXTRACTION_IMAGE_READY page=%s size_kb=%s",
#         page_number, image_size_kb,
#     )

#     system_prompt = (
#         "You are a document text extractor. "
#         "Your sole task is to faithfully transcribe ALL visible text from the image, "
#         "especially the contents of tables. "
#         "For every table row output the cells separated by ' | ' on a single line. "
#         "Include every header row, every data row, every number, label, and symbol "
#         "exactly as written \u2014 do not omit, summarise, or paraphrase anything. "
#         "Output plain text only; no markdown, no bullet points, no extra commentary."
#     )
#     user_prompt = (
#         "Extract every piece of text from this PDF page, "
#         "including all table rows and individual cell values:"
#     )

#     try:
#         client = AzureOpenAI(
#             api_key=api_key,
#             azure_endpoint=endpoint,
#             api_version=api_version,
#             timeout=60,
#         )
#         completion = client.chat.completions.create(
#             model=vision_deployment,
#             temperature=0,
#             max_tokens=2000,
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {
#                     "role": "user",
#                     "content": [
#                         {"type": "text", "text": user_prompt},
#                         {
#                             "type": "image_url",
#                             "image_url": {
#                                 "url": f"data:image/png;base64,{image_b64}",
#                                 "detail": "high",
#                             },
#                         },
#                     ],
#                 },
#             ],
#         )
#         extracted = (completion.choices[0].message.content or "").strip()
#         logger.info(
#             "VISION_EXTRACTION_SUCCESS page=%s deployment=%s length=%s preview=%r",
#             page_number, vision_deployment, len(extracted), extracted[:300],
#         )
#         return extracted
#     except Exception as exc:
#         # Log at ERROR so the failure is visible in the console.
#         # Common causes:
#         #   - "model does not support image inputs" \u2192 AZURE_OPENAI_VISION_DEPLOYMENT
#         #     must point to a vision-capable model (gpt-4o, gpt-4-turbo, etc.)
#         #   - 404 DeploymentNotFound \u2192 deployment name is wrong
#         #   - 401 Unauthorized \u2192 API key expired or wrong endpoint
#         logger.error(
#             "VISION_EXTRACTION_API_FAILED page=%s deployment=%s endpoint=%s "
#             "error_type=%s error=%s | "
#             "If you see 'model does not support image inputs', set "
#             "AZURE_OPENAI_VISION_DEPLOYMENT in .env to a vision-capable deployment "
#             "(e.g. gpt-4o). Current deployment: %s",
#             page_number, vision_deployment, endpoint,
#             type(exc).__name__, exc,
#             vision_deployment,
#         )
#         return ""


# def _normalize_pdf_url(url: str) -> str:
#     """Remove viewer fragments such as #page=12 before downloading the PDF."""
#     normalized_url, _ = urldefrag(url)
#     return normalized_url


# def _normalize_text(text: str) -> str:
#     """Normalize parser output for stable CSV and validation matching."""
#     return " ".join(text.replace("\u00a0", " ").split()) 


"""Parser-backed source PDF reader for page-level validation."""

from io import BytesIO
from functools import lru_cache
import os
import re
from shutil import which
from urllib.parse import urldefrag
from urllib.request import urlopen

from pypdf import PdfReader

from utils.logger import get_logger


MIN_USEFUL_PAGE_TEXT_LENGTH = 30
WEAK_PAGE_TEXTS = {
    "visual aid communication",
    "no page data available",
}


def _vision_extraction_enabled() -> bool:
    """Return whether GPT-4o Vision extraction is enabled via env var."""
    return os.getenv("VISION_EXTRACTION_ENABLED", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def extract_pdf_page_text_from_url(
    url: str,
    page_number: int,
    document_name: str = "",
) -> str:
    """Extract text from one PDF page only using parser fallbacks."""
    if page_number < 1:
        return ""

    logger = get_logger("source_document_reader")
    normalized_url = _normalize_pdf_url(url)
    pdf_bytes = _get_pdf_bytes(normalized_url)
    context = _log_context(document_name, normalized_url, page_number)

    logger.info("PDF_EXTRACTION_START %s", context)

    base_attempts = [
        ("pypdf", lambda: _extract_page_text_with_pypdf(pdf_bytes, page_number)),
        ("pymupdf", lambda: _extract_page_text_with_pymupdf(pdf_bytes, page_number)),
        ("ocr", lambda: _extract_page_text_with_ocr(pdf_bytes, page_number)),
    ]
    # Vision is the most expensive method — only run it when cheaper methods fail.
    if _vision_extraction_enabled():
        base_attempts.append(
            ("vision", lambda: _extract_page_text_with_vision(pdf_bytes, page_number))
        )
    extraction_attempts = tuple(base_attempts)

    best_text = ""
    best_method = ""

    for method_name, extractor in extraction_attempts:
        try:
            page_text = _normalize_text(extractor())
        except Exception as exc:
            logger.warning(
                "PDF_EXTRACTION_METHOD_FAILED method=%s %s error=%s",
                method_name,
                context,
                exc,
            )
            continue

        logger.info(
            "PDF_EXTRACTION_METHOD method=%s %s text_length=%s weak=%s preview=%s",
            method_name,
            context,
            len(page_text),
            is_weak_pdf_page_text(page_text),
            page_text[:200],
        )

        if len(page_text) > len(best_text):
            best_text = page_text
            best_method = method_name

        if not is_weak_pdf_page_text(page_text):
            logger.info(
                "PDF_EXTRACTION_SELECTED method=%s %s text_length=%s",
                method_name,
                context,
                len(page_text),
            )
            return page_text

    logger.warning(
        "PAGE_TEXT_EXTRACTION_FAILED %s best_method=%s best_length=%s best_preview=%s | "
        "DIAGNOSIS: All extraction methods returned weak/empty text. "
        "Possible causes: (1) image-only PDF page - enable VISION_EXTRACTION_ENABLED=1 "
        "and set AZURE_OPENAI_VISION_DEPLOYMENT; (2) encrypted PDF; (3) page index "
        "off-by-one (check if page_number=%s is correct); (4) table with no selectable "
        "text. Validator will fall back to OpenAI with partial text.",
        context,
        best_method or "NONE",
        len(best_text),
        best_text[:200],
        page_number,
    )
    return best_text


def is_weak_pdf_page_text(text: str) -> bool:
    """Return whether extracted page text is too weak for validation."""
    cleaned = _normalize_text(text)

    if not cleaned:
        return True

    lowered = cleaned.lower().strip()

    if lowered in WEAK_PAGE_TEXTS:
        return True

    if re.fullmatch(r"\d+", lowered):
        return True

    if len(cleaned) < MIN_USEFUL_PAGE_TEXT_LENGTH:
        return True

    if not re.search(r"[a-zA-Z]", cleaned):
        return True

    return False


def get_pdf_page_count_from_url(url: str) -> int:
    """Return total number of pages in the source PDF."""
    reader = _get_pdf_reader(_normalize_pdf_url(url))
    return len(reader.pages)


def extract_pdf_text_from_url(url: str, page_hint: int | None = None) -> str:
    """Backward-compatible parser API.

    When page_hint is provided, only that page is parsed. Full-document parsing is
    intentionally unavailable for validation to prevent cross-page matching.
    """
    if page_hint is None:
        raise ValueError("page_hint is required for page-level PDF validation.")

    return extract_pdf_page_text_from_url(url, page_hint)


def _log_context(document_name: str, url: str, page_number: int) -> str:
    """Return stable context for extraction logs."""
    safe_document_name = _normalize_text(document_name) or "UNKNOWN_DOCUMENT"
    return (
        f"document={safe_document_name!r} "
        f"page={page_number} "
        f"url={url!r}"
    )


@lru_cache(maxsize=16)
def _get_pdf_bytes(url: str) -> bytes:
    """Download PDF bytes once per source URL for faster repeated validation."""
    with urlopen(url, timeout=60) as response:  # nosec B310
        return response.read()


@lru_cache(maxsize=16)
def _get_pdf_reader(url: str) -> PdfReader:
    """Return a cached PdfReader for the source URL."""
    return PdfReader(BytesIO(_get_pdf_bytes(url)))


def _extract_page_text_with_pypdf(pdf_bytes: bytes, page_number: int) -> str:
    """Extract page text with pypdf."""
    reader = PdfReader(BytesIO(pdf_bytes))

    if not reader.pages or page_number > len(reader.pages):
        return ""

    return reader.pages[page_number - 1].extract_text() or ""


def _extract_page_text_with_pymupdf(pdf_bytes: bytes, page_number: int) -> str:
    """Extract page text with PyMuPDF when available."""
    try:
        import fitz
    except ImportError:
        return ""

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if page_number > document.page_count:
            return ""

        page = document.load_page(page_number - 1)
        return page.get_text("text") or ""


def _extract_page_text_with_ocr(pdf_bytes: bytes, page_number: int) -> str:
    """OCR one PDF page only when optional OCR dependencies are available."""
    logger = get_logger("source_document_reader")

    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning(
            "OCR extraction skipped because PyMuPDF, pytesseract, or Pillow is not installed."
        )
        return ""

    if not which("tesseract"):
        logger.warning(
            "OCR extraction skipped because the Tesseract OCR engine is not installed or not on PATH."
        )
        return ""

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if page_number > document.page_count:
            return ""

        page = document.load_page(page_number - 1)
        matrix = fitz.Matrix(2, 2)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        try:
            return pytesseract.image_to_string(image) or ""
        except pytesseract.TesseractNotFoundError:
            logger.warning(
                "OCR extraction skipped because pytesseract could not find the Tesseract OCR engine."
            )
            return ""


def _extract_page_text_with_vision(pdf_bytes: bytes, page_number: int) -> str:
    """Extract page text using Azure OpenAI Vision when all text methods fail.

    Renders the PDF page as a high-resolution PNG and asks a vision model to
    transcribe every visible character, including image-embedded tables.
    Only runs when VISION_EXTRACTION_ENABLED is not disabled and Azure OpenAI
    Vision credentials are configured.
    """
    logger = get_logger("source_document_reader")

    try:
        import fitz
    except ImportError:
        logger.warning(
            "VISION_EXTRACTION_SKIPPED reason=PyMuPDF_not_installed "
            "fix='pip install pymupdf'"
        )
        return ""

    try:
        from openai import AzureOpenAI
    except ImportError:
        logger.warning(
            "VISION_EXTRACTION_SKIPPED reason=openai_package_not_installed "
            "fix='pip install openai'"
        )
        return ""

    import base64

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
    # Prefer a dedicated vision deployment; fall back to the text deployment.
    # Set AZURE_OPENAI_VISION_DEPLOYMENT to a vision-capable model (e.g. gpt-4o).
    # If AZURE_OPENAI_DEPLOYMENT is already a vision-capable model, that works too.
    vision_deployment = (
        os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    ).strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip()

    if not api_key:
        logger.warning("VISION_EXTRACTION_SKIPPED reason=AZURE_OPENAI_API_KEY_not_set")
        return ""
    if not endpoint:
        logger.warning("VISION_EXTRACTION_SKIPPED reason=AZURE_OPENAI_ENDPOINT_not_set")
        return ""
    if not vision_deployment:
        logger.warning(
            "VISION_EXTRACTION_SKIPPED reason=no_vision_deployment_configured "
            "fix='Set AZURE_OPENAI_VISION_DEPLOYMENT in .env to a vision-capable model "
            "(e.g. gpt-4o). If your AZURE_OPENAI_DEPLOYMENT already supports vision, "
            "set AZURE_OPENAI_VISION_DEPLOYMENT to the same value.'"
        )
        return ""

    logger.info(
        "VISION_EXTRACTION_START page=%s deployment=%s endpoint=%s",
        page_number, vision_deployment, endpoint,
    )

    # Render the page at 2\u00d7 resolution for crisp OCR of small table text.
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            if page_number > document.page_count:
                return ""
            pdf_page = document.load_page(page_number - 1)
            pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image_b64 = base64.b64encode(pixmap.tobytes("png")).decode("utf-8")
            image_size_kb = round(len(image_b64) * 3 / 4 / 1024)
    except Exception as exc:
        logger.error(
            "VISION_EXTRACTION_RENDER_FAILED page=%s error=%s", page_number, exc,
            exc_info=True,
        )
        return ""

    logger.info(
        "VISION_EXTRACTION_IMAGE_READY page=%s size_kb=%s",
        page_number, image_size_kb,
    )

    system_prompt = (
        "You are a document text extractor. "
        "Your sole task is to faithfully transcribe ALL visible text from the image, "
        "especially the contents of tables. "
        "For every table row output the cells separated by ' | ' on a single line. "
        "Include every header row, every data row, every number, label, and symbol "
        "exactly as written \u2014 do not omit, summarise, or paraphrase anything. "
        "Output plain text only; no markdown, no bullet points, no extra commentary."
    )
    user_prompt = (
        "Extract every piece of text from this PDF page, "
        "including all table rows and individual cell values:"
    )

    try:
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            timeout=60,
        )
        completion = client.chat.completions.create(
            model=vision_deployment,
            temperature=0,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
        )
        extracted = (completion.choices[0].message.content or "").strip()
        logger.info(
            "VISION_EXTRACTION_SUCCESS page=%s deployment=%s length=%s preview=%r",
            page_number, vision_deployment, len(extracted), extracted[:300],
        )
        return extracted
    except Exception as exc:
        # Log at ERROR so the failure is visible in the console.
        # Common causes:
        #   - "model does not support image inputs" \u2192 AZURE_OPENAI_VISION_DEPLOYMENT
        #     must point to a vision-capable model (gpt-4o, gpt-4-turbo, etc.)
        #   - 404 DeploymentNotFound \u2192 deployment name is wrong
        #   - 401 Unauthorized \u2192 API key expired or wrong endpoint
        logger.error(
            "VISION_EXTRACTION_API_FAILED page=%s deployment=%s endpoint=%s "
            "error_type=%s error=%s | "
            "If you see 'model does not support image inputs', set "
            "AZURE_OPENAI_VISION_DEPLOYMENT in .env to a vision-capable deployment "
            "(e.g. gpt-4o). Current deployment: %s",
            page_number, vision_deployment, endpoint,
            type(exc).__name__, exc,
            vision_deployment,
        )
        return ""


def _normalize_pdf_url(url: str) -> str:
    """Remove viewer fragments such as #page=12 before downloading the PDF."""
    normalized_url, _ = urldefrag(url)
    return normalized_url


def _normalize_text(text: str) -> str:
    """Normalize parser output for stable CSV and validation matching."""
    return " ".join(text.replace("\u00a0", " ").split())