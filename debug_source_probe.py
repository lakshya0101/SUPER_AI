"""Temporary probe for Access Source Document behavior."""

from pages.citation_page import CitationPage
from utils.browser_manager import BrowserManager
from utils.login_flow import login_to_super_ai
from utils.validator import extract_citation_page_numbers, extract_matching_values


def safe_print(label: str, value: str) -> None:
    """Print text safely on Windows consoles."""
    encoded_value = value.encode("ascii", errors="ignore").decode("ascii")
    print(f"{label}: {encoded_value}")


def main() -> None:
    """Ask one question, open citation, click source document, and print state."""
    browser_manager = BrowserManager()
    page = browser_manager.launch_browser()

    try:
        super_ai_page = login_to_super_ai(page)
        citation_page = CitationPage(page)

        question = "What is the MRP of GLIZID-MV (15 tablets)?"
        super_ai_page.ask_question(question)
        response = super_ai_page.get_response(question)
        safe_print("RESPONSE", response)
        print(f"PAGE_HINTS_FROM_RESPONSE: {extract_citation_page_numbers(response)}")

        page_hints = extract_citation_page_numbers(response) or [None]
        citation_page.open_citation_by_page(page_hints[0])
        print(f"BEFORE_URL: {page.url}")
        print(f"PAGES_BEFORE: {len(page.context.pages)}")

        access_button = page.locator("text=Access Source Document").last
        access_button.wait_for(state="visible", timeout=60000)
        access_button.click()
        page.wait_for_timeout(10000)

        print(f"AFTER_URL: {page.url}")
        print(f"PAGES_AFTER: {len(page.context.pages)}")

        for index, context_page in enumerate(page.context.pages):
            print(f"PAGE_{index}_URL: {context_page.url}")
            print(f"PAGE_{index}_TITLE: {context_page.title()}")
            text = context_page.locator("body").inner_text(timeout=10000)
            safe_print(f"PAGE_{index}_BODY_START", " ".join(text.split())[:1000])

        source_text = citation_page.open_source_document_and_extract_text()
        safe_print("SOURCE_TEXT_START", " ".join(source_text.split())[:1500])
        safe_print("MATCHING_VALUES", extract_matching_values(response, source_text))

    finally:
        browser_manager.close_browser()


if __name__ == "__main__":
    main()
