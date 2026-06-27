"""Generate validation questions from new or updated source PDFs in Azure Blob.

Flow:
1. List PDFs from the configured Blob container/prefix.
2. Use a saved LastProcessedDateTime to select new/updated PDFs.
3. Extract PDF text from selected files.
4. Ask Azure OpenAI to generate validation-friendly questions.
5. Write data/validation_ques.csv in the existing automation format.
6. Save the latest scanned LastProcessedDateTime for the next run.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from azure.storage.blob import BlobServiceClient, ContainerClient
from dotenv import load_dotenv
from openai import AzureOpenAI
from pypdf import PdfReader

from utils.source_document_reader import is_weak_pdf_page_text


CSV_COLUMNS = [
    "Division Name",
    "Product",
    "Question Type",
    "Question",
    "Expected Answer",
    "SuperAI_Response",
    "Pass/Fail/DataMissing",
    "Reason",
]


@dataclass(frozen=True)
class GeneratorConfig:
    container_sas_url: str
    connection_string: str
    container_name: str
    blob_prefix: str
    output_csv: Path
    archive_dir: Path
    state_file: Path
    max_context_chars: int
    num_questions: int
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    azure_deployment: str


def load_config() -> GeneratorConfig:
    """Load generator settings from .env."""
    load_dotenv()

    return GeneratorConfig(
        container_sas_url=os.getenv("AZURE_BLOB_CONTAINER_SAS_URL", "").strip(),
        connection_string=os.getenv("AZURE_BLOB_CONNECTION_STRING", "").strip(),
        container_name=os.getenv("BLOB_CONTAINER_NAME", "gen-ai").strip(),
        blob_prefix=os.getenv("BLOB_PREFIX", "unstructured/Product Documents").strip(),
        output_csv=Path(
            os.getenv("QUESTION_OUTPUT_CSV", "data/validation_ques.csv").strip()
        ),
        archive_dir=Path(
            os.getenv("QUESTIONS_ARCHIVE_DIR", "Questions Archive").strip()
        ),
        state_file=Path(
            os.getenv("BLOB_PROCESSING_STATE_FILE", "data/blob_processing_state.json").strip()
        ),
        max_context_chars=int(
            os.getenv("QUESTION_GENERATOR_MAX_CONTEXT_CHARS", "120000").strip()
        ),
        num_questions=int(os.getenv("NUM_QUESTIONS", "20").strip()),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/"),
        azure_api_key=os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
        azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip(),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip(),
    )


def validate_config(config: GeneratorConfig) -> None:
    """Fail early with clear missing-setting errors."""
    missing = []

    if not (config.container_sas_url or config.connection_string):
        missing.append("AZURE_BLOB_CONTAINER_SAS_URL or AZURE_BLOB_CONNECTION_STRING")
    if config.connection_string and not config.container_name:
        missing.append("BLOB_CONTAINER_NAME")
    if not config.azure_endpoint:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not config.azure_api_key:
        missing.append("AZURE_OPENAI_API_KEY")
    if not config.azure_deployment:
        missing.append("AZURE_OPENAI_DEPLOYMENT")

    if missing:
        raise RuntimeError("Missing required settings: " + ", ".join(missing))


def get_container_client(config: GeneratorConfig) -> ContainerClient:
    """Create a Blob container client from SAS URL or connection string."""
    if config.container_sas_url:
        return ContainerClient.from_container_url(config.container_sas_url)

    service_client = BlobServiceClient.from_connection_string(config.connection_string)
    return service_client.get_container_client(config.container_name)


def list_pdf_blobs(container_client: ContainerClient, prefix: str) -> list[Any]:
    """Return all PDFs under the configured prefix."""
    normalized_prefix = prefix.strip("/")
    candidates = [
        blob
        for blob in container_client.list_blobs(name_starts_with=normalized_prefix)
        if blob.name.lower().endswith(".pdf")
    ]

    if not candidates:
        raise FileNotFoundError(f"No PDF files found under Blob prefix: {normalized_prefix}")

    return sorted(candidates, key=lambda blob: blob.last_modified)


def load_last_processed_datetime(state_file: Path) -> datetime | None:
    """Read the saved LastProcessedDateTime from disk."""
    if not state_file.exists():
        return None

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        value = str(state.get("LastProcessedDateTime") or "").strip()
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _as_utc(parsed)
    except Exception as exc:
        print(f"QUESTION_GENERATOR_STATE_READ_FAILED = {exc}")
        return None


def save_last_processed_datetime(state_file: Path, value: datetime) -> None:
    """Persist LastProcessedDateTime for future incremental runs."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "LastProcessedDateTime": _as_utc(value).isoformat().replace("+00:00", "Z"),
        "UpdatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"QUESTION_GENERATOR_LAST_PROCESSED_DATETIME = {state['LastProcessedDateTime']}")


def select_blobs_for_processing(blobs: list[Any], last_processed: datetime | None) -> list[Any]:
    """Apply initial/subsequent run selection rules."""
    if last_processed is None:
        print("QUESTION_GENERATOR_INCREMENTAL_MODE = INITIAL_RUN")
        return blobs

    print(f"QUESTION_GENERATOR_INCREMENTAL_MODE = SUBSEQUENT_RUN")
    print(f"QUESTION_GENERATOR_PREVIOUS_LAST_PROCESSED = {last_processed.isoformat()}")
    return [
        blob
        for blob in blobs
        if _as_utc(blob.last_modified) > last_processed
    ]


def download_blob_bytes(container_client: ContainerClient, blob_name: str) -> bytes:
    """Download one Blob by name."""
    blob_client = container_client.get_blob_client(blob_name)
    return blob_client.download_blob().readall()


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def extract_division_name(blob_name: str, blob_prefix: str) -> str:
    """Return the first word of the folder that directly contains the file.

    Examples
    --------
    blob_name = ".../Aspiris Mankind Product Knockout/file.pdf"
    → "Aspiris"

    blob_name = ".../Brand Snap Shot - VA/Victrix Brand Snapshot 2026-27/file.pdf"
    → "Victrix"   (the folder immediately containing the file, not the top folder)

    Returns an empty string when the blob sits directly inside the prefix.
    """
    prefix = blob_prefix.strip("/")
    name = blob_name.strip("/")

    # Strip the known prefix so we work with the relative path only
    if name.startswith(prefix + "/"):
        relative = name[len(prefix) + 1:]
    else:
        relative = name

    # parts[-1] = filename, parts[-2] = immediate parent folder
    parts = relative.split("/")
    folder_name = parts[-2] if len(parts) >= 2 else ""

    if not folder_name:
        return ""

    tokens = folder_name.split()
    return tokens[0] if tokens else folder_name


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 60000) -> tuple[str, int]:
    """Extract text from all pages, bounded for model input speed/cost."""
    reader = PdfReader(BytesIO(pdf_bytes))
    page_texts = []
    page_count = len(reader.pages)

    for page_number in range(1, page_count + 1):
        text = _extract_generator_page_text(pdf_bytes, reader, page_number)
        if text:
            page_texts.append(f"[PAGE {page_number}] {text}")
        if sum(len(item) for item in page_texts) >= max_chars:
            break

    document_text = "\n\n".join(page_texts).strip()
    if not document_text:
        raise RuntimeError("PDF text extraction returned no usable text.")

    print(
        "QUESTION_GENERATOR_EXTRACTION_SUMMARY = "
        f"pages={page_count} extracted_pages={len(page_texts)} chars={len(document_text)}"
    )

    return document_text[:max_chars], page_count


def _extract_generator_page_text(
    pdf_bytes: bytes,
    reader: PdfReader,
    page_number: int,
) -> str:
    """Extract one page for question generation with parser fallback."""
    text = " ".join((reader.pages[page_number - 1].extract_text() or "").split())
    method = "pypdf"

    if is_weak_pdf_page_text(text):
        pymupdf_text = _extract_generator_page_text_with_pymupdf(pdf_bytes, page_number)
        if len(pymupdf_text) > len(text):
            text = pymupdf_text
            method = "pymupdf"

    weak = is_weak_pdf_page_text(text)
    print(
        "QUESTION_GENERATOR_PAGE_EXTRACTION = "
        f"page={page_number} method={method} text_length={len(text)} "
        f"weak={weak} preview={text[:160]}"
    )
    return "" if weak else text


def _extract_generator_page_text_with_pymupdf(pdf_bytes: bytes, page_number: int) -> str:
    """Extract one page with PyMuPDF if installed."""
    try:
        import fitz
    except ImportError:
        return ""

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if page_number > document.page_count:
            return ""
        page = document.load_page(page_number - 1)
        return " ".join((page.get_text("text") or "").split())


def determine_question_count(page_count: int, document_text: str) -> int:
    """Choose a quality-focused question count from document size."""
    useful_chars = len(document_text.strip())

    if page_count <= 2:
        if useful_chars < 1200:
            return 3
        if useful_chars < 3000:
            return 5
        return 8

    if page_count <= 5:
        if useful_chars < 4000:
            return 8
        if useful_chars < 8000:
            return 12
        return 15

    if page_count <= 10:
        if useful_chars < 9000:
            return 15
        if useful_chars < 18000:
            return 20
        return 25

    if useful_chars < 20000:
        return 25
    if useful_chars < 50000:
        return 35
    return 50


def extract_blob_document_text(
    container_client: ContainerClient,
    blob: Any,
    max_context_chars: int,
) -> tuple[str, int]:
    """Extract text from one selected PDF."""
    print(f"QUESTION_GENERATOR_SOURCE_BLOB = {blob.name}")
    pdf_bytes = download_blob_bytes(container_client, blob.name)
    text, page_count = extract_pdf_text(pdf_bytes, max_chars=max_context_chars)
    return (
        f"[SOURCE_BLOB] {blob.name}\n"
        f"[LAST_MODIFIED] {_as_utc(blob.last_modified).isoformat()}\n"
        f"{text}"
    ), page_count


def generate_questions(
    config: GeneratorConfig,
    *,
    blob_name: str,
    document_text: str,
    num_questions: int,
    page_count: int,
    division_name: str = "",
) -> list[dict[str, str]]:
    """Use Azure OpenAI to generate structured validation questions."""
    client = AzureOpenAI(
        api_key=config.azure_api_key,
        azure_endpoint=config.azure_endpoint,
        api_version=config.azure_api_version,
        timeout=90,
    )

    system_prompt = (
        "You generate validation questions for a pharma document automation system. "
        "Use only the provided document text. Prefer factual, exact, citation-friendly "
        "questions over broad reasoning questions. Create questions that can be validated "
        "from a specific PDF page: composition, MRP, dosage, active ingredient, indication, "
        "pack size, company, mechanism, definition, USP, and table lookup. Avoid questions "
        "that need external knowledge. Do not generate redundant or repetitive questions. "
        "Generate only as many questions as can be supported by the available information. "
        "Prioritize quality over quantity. "
        "Use a product-first process for every document. First identify every distinct "
        "product, SKU, brand variant, or competitor product that has usable evidence. Then "
        "create a separate evidence block mentally for each product. Generate questions for "
        "one product only from that product's block. Every identified product with usable "
        "information must receive at least one question unless maximum_question_count is "
        "smaller than the number of products; in that case prioritize products with richer "
        "evidence. Products with more evidence should receive more questions, and products "
        "with limited evidence should receive fewer questions. Do not mix composition, MRP, "
        "dosage, indications, competitor data, pack size, company, USP, or mechanism from "
        "one product into another product's questions. The Product field must contain the "
        "exact product name for the evidence used by that question. Return JSON only, using "
        "a top-level 'questions' array."
    )

    user_payload = {
        "source_blob": blob_name,
        "page_count": page_count,
        "maximum_question_count": num_questions,
        "question_count_guidelines": [
            "Very short documents (1-2 pages): 2-4 questions",
            "Small documents (3-5 pages): 3-8 questions",
            "Medium documents (6-10 pages): 8-15 questions",
            "Large documents (10+ pages): 15-25 questions",
        ],
        "instruction": (
            "Generate up to maximum_question_count high-quality questions. "
            "Return fewer questions if the document cannot support more without repetition. "
            "Before writing questions, identify distinct products/SKUs/brand variants and group "
            "the source evidence by product. For each product, use only directly related nearby "
            "text, table rows, headings, SKU lines, MRP lines, dosage lines, indication lines, "
            "composition lines, mechanism lines, and competitor rows. Every product with usable "
            "evidence should have at least one question when the maximum question count allows it. "
            "If a product has rich evidence such as composition, dosage, MRP, indication, mechanism, "
            "USP, competitor rows, company, or pack size, generate multiple questions for that "
            "product. If a product has only one or two facts, generate only one or two questions. "
            "Never ask a question whose answer requires facts from different product blocks. "
            "Never assign one product's MRP, composition, dosage, indication, company, or pack size "
            "to another product. For table data, keep row relationships intact: Product/Brand, "
            "Company, Pack, Price, Strength, and SKU values must stay in the same row."
        ),
        "output_schema": {
            "questions": [
                {
                    "Product": "exact product/SKU/brand name from the evidence block",
                    "Question Type": "short category",
                    "Question": "question text",
                }
            ]
        },
        "product_mapping_rules": [
            "One generated row must map to exactly one Product value.",
            "Use the Product column to store the exact product name used as evidence.",
            "For multi-product tables, generate row-level questions only from the matching row.",
            "For combined products or variants, keep the variant name in the Product field.",
            "Do not create generic document-level questions when product-specific questions are possible.",
        ],
        "document_text": document_text,
    }

    completion = client.chat.completions.create(
        model=config.azure_deployment,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    )

    content = completion.choices[0].message.content or "{}"
    parsed = json.loads(content)
    raw_questions = parsed.get("questions", [])

    if not isinstance(raw_questions, list):
        raise RuntimeError("Azure OpenAI response did not contain a questions list.")

    rows = []
    for item in raw_questions[:num_questions]:
        if not isinstance(item, dict):
            continue

        question = str(item.get("Question") or "").strip()
        if not question:
            continue

        rows.append(
            {
                "Division Name": division_name,
                "Product": str(item.get("Product") or "Document").strip() or "Document",
                "Question Type": str(item.get("Question Type") or "Factual").strip()
                or "Factual",
                "Question": question,
                "Expected Answer": "",
                "SuperAI_Response": "",
                "Pass/Fail/DataMissing": "",
                "Reason": "",
            }
        )

    if not rows:
        raise RuntimeError("No valid questions were generated.")

    return rows


def archive_generated_questions(
    rows: list[dict[str, str]],
    archive_dir: Path,
) -> Path:
    """Save the newly generated questions into the archive folder."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M%S")
    archive_path = archive_dir / f"validation_ques_{timestamp}.csv"

    with archive_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"QUESTION_GENERATOR_ARCHIVE_CSV = {archive_path.resolve()}")
    return archive_path


def write_questions_csv(
    output_csv: Path,
    rows: list[dict[str, str]],
    archive_dir: Path,
) -> None:
    """Overwrite the validation question CSV with generated rows."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    archive_generated_questions(rows, archive_dir)
    print(f"QUESTION_GENERATOR_OUTPUT_CSV = {output_csv.resolve()}")
    print(f"QUESTION_GENERATOR_ROWS = {len(rows)}")


def run(output_csv: Path | None = None, num_questions: int | None = None) -> bool:
    """Run the question generation workflow."""
    config = load_config()
    validate_config(config)

    final_output_csv = output_csv or config.output_csv
    final_num_questions = num_questions or config.num_questions

    container_client = get_container_client(config)
    all_pdf_blobs = list_pdf_blobs(container_client, config.blob_prefix)
    latest_scanned_datetime = max(
        _as_utc(blob.last_modified) for blob in all_pdf_blobs
    )
    last_processed_datetime = load_last_processed_datetime(config.state_file)
    selected_blobs = select_blobs_for_processing(all_pdf_blobs, last_processed_datetime)

    print(f"QUESTION_GENERATOR_TOTAL_PDFS_SCANNED = {len(all_pdf_blobs)}")
    print(f"QUESTION_GENERATOR_NEW_OR_UPDATED_PDFS = {len(selected_blobs)}")

    if not selected_blobs:
        print("QUESTION_GENERATOR_NO_NEW_FILES = True")
        return False

    rows = []
    for blob_index, blob in enumerate(selected_blobs, start=1):
        print(
            "QUESTION_GENERATOR_PROCESSING_PDF = "
            f"{blob_index}/{len(selected_blobs)} | {blob.name}"
        )
        division_name = extract_division_name(blob.name, config.blob_prefix)
        print(f"QUESTION_GENERATOR_DIVISION_NAME = {division_name!r} | {blob.name}")

        try:
            document_text, page_count = extract_blob_document_text(
                container_client,
                blob,
                config.max_context_chars,
            )
        except Exception as exc:
            print(f"QUESTION_GENERATOR_PDF_EXTRACTION_FAILED = {blob.name} | {exc}")
            continue

        dynamic_question_count = determine_question_count(page_count, document_text)
        if num_questions is not None:
            dynamic_question_count = min(dynamic_question_count, final_num_questions)

        print(
            "QUESTION_GENERATOR_DYNAMIC_COUNT = "
            f"{dynamic_question_count} | pages={page_count} | {blob.name}"
        )

        file_rows = generate_questions(
            config,
            blob_name=blob.name,
            document_text=document_text,
            num_questions=dynamic_question_count,
            page_count=page_count,
            division_name=division_name,
        )
        rows.extend(file_rows)
        print(
            "QUESTION_GENERATOR_ROWS_FOR_PDF = "
            f"{len(file_rows)} | {blob.name}"
        )

    if not rows:
        raise RuntimeError("No questions were generated from selected Blob files.")

    write_questions_csv(final_output_csv, rows, config.archive_dir)
    save_last_processed_datetime(config.state_file, latest_scanned_datetime)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate validation_ques.csv from the latest PDF in Azure Blob."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV output path. Defaults to QUESTION_OUTPUT_CSV from .env.",
    )
    parser.add_argument(
        "--num-questions",
        type=int,
        default=None,
        help=(
            "Optional maximum questions per new/updated PDF. "
            "By default the generator chooses a suitable count from document length."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        output_csv=Path(args.output) if args.output else None,
        num_questions=args.num_questions,
    )
