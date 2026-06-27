"""Page object for Super AI citation panel and source-document interactions."""

import re
from time import monotonic, sleep
from urllib.parse import urldefrag

from playwright.sync_api import Locator, Page

from config.settings import (
    DEFAULT_TIMEOUT,
    PDF_VIEWER_NAVIGATION_ENABLED,
    PDF_VIEWER_READY_WAIT_MS,
    SOURCE_DOC_LOAD_TIMEOUT,
)
from utils.logger import get_logger
from utils.source_document_reader import (
    extract_pdf_page_text_from_url,
    get_pdf_page_count_from_url,
)
from utils.validator import extract_citation_targets, extract_document_name, extract_page_number


class CitationPageLocators:
    """Locators for citation links and the citation side panel."""

    CITATION_LINKS = (
        "xpath=.//*[contains(normalize-space(.), '_Page_') "
        "and not(.//*[contains(normalize-space(.), '_Page_')])]"
    )
    CITATION_PANEL = (
        "xpath=//*[normalize-space()='Access Source Document']"
        "/ancestor::div[contains(normalize-space(.), 'Citation')][1]"
    )
    ACCESS_SOURCE_BUTTON = "text=Access Source Document"
    RESPONSE_BLOCKS = ".received"
    PAGE_VIEWER_ROOT = (
        "[data-testid*='viewer' i], [class*='viewer' i], [id*='viewer' i], "
        "[class*='pdf' i], [id*='pdf' i], body"
    )
    PAGE_CONTAINERS = (
        "[data-page-number], [data-page], [aria-label*='Page' i], "
        "[id^='pageContainer'], [id*='page'][class*='page' i], "
        ".page, .pdf-page, .react-pdf__Page"
    )
    PDF_PAGE_INPUTS = (
        "pdf-viewer viewer-toolbar viewer-page-selector input, "
        "viewer-toolbar viewer-page-selector input, "
        "viewer-page-selector input, "
        "#pageselector, "
        "#pageSelector, "
        "input.pageNumber, "
        "input[type='number'], "
        "input[type='text'], "
        "input:not([type]), "
        "input[aria-label*='page' i], "
        "input[title*='page' i], "
        "input[aria-label*='current page' i]"
    )


class CitationPage:
    """Actions for opening and reading Super AI citation content."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.logger = get_logger(self.__class__.__name__)
        self.selected_citation_text = ""
        self.source_page: Page | None = None
        self.source_url = ""
        self.current_page_number: int | None = None
        self.current_page_locator: Locator | None = None
        self.target_page_number: int | None = None

    def extract_page_number_from_citation(self, response: str) -> int:
        """Extract mandatory citation page number from response or visible citation DOM."""
        self.logger.info("Extracting page number from response citation")
        self.selected_citation_text = ""

        try:
            self.target_page_number = extract_page_number(response)
            return self.target_page_number
        except ValueError:
            page_number = None

        self.logger.warning(
            "Response text did not contain page metadata. Falling back to citation DOM."
        )
        self.open_first_citation()

        citation_links = self._latest_response_citation_links()
        for index in range(citation_links.count()):
            citation_text = citation_links.nth(index).inner_text(timeout=DEFAULT_TIMEOUT)
            page_number = self._extract_page_hint(citation_text)
            if page_number is not None:
                self.selected_citation_text = citation_text.strip()
                return page_number

        panel_text = self.extract_citation_text()
        page_number = self._extract_page_hint(panel_text)
        if page_number is not None:
            self.selected_citation_text = panel_text.strip()
            self.target_page_number = page_number
            return page_number

        raise ValueError("No mandatory citation page number found in response or citation DOM.")

    def extract_page_number(self, text: str | None = None) -> int:
        """Extract the mandatory page number from response text or the open citation."""
        if text:
            self.target_page_number = extract_page_number(text)
            return self.target_page_number

        self.target_page_number = self.extract_page_number_from_open_citation()
        return self.target_page_number

    def get_first_citation_text(self) -> str:
        """Return the first visible citation text for diagnostics and CSV output."""
        citation_links = self._latest_response_citation_links()
        citation_links.first.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        return citation_links.first.inner_text(timeout=DEFAULT_TIMEOUT).strip()

    def get_citation_count(self) -> int:
        """Return count of citation references available for the latest answer."""
        visible_citation_numbers = self._extract_visible_citation_numbers()
        if visible_citation_numbers:
            return len(visible_citation_numbers)

        metadata_count = self._latest_response_citation_links().count()
        numeric_count = self._get_numbered_citation_references().count()
        return max(metadata_count, numeric_count, 1)

    def get_visible_citation_targets(self) -> list[dict[str, int | str]]:
        """Return every visible citation target from the latest SuperAI answer."""
        targets: list[dict[str, int | str]] = []
        citation_links = self._latest_response_citation_links()

        for index in range(citation_links.count()):
            citation_el = citation_links.nth(index)
            citation_text = citation_el.inner_text(timeout=DEFAULT_TIMEOUT).strip()

            # Guard: when the browser DOM splits a document name that contains an
            # apostrophe across sibling <span> elements, the XPath "innermost
            # element with _Page_" selector captures only the trailing fragment
            # (e.g. "S)_Page_17" instead of "Transplant Policy 2025-26 (Mr'S)_Page_17").
            # Detect this by checking whether the text before "_Page_" is suspiciously
            # short, and if so, fetch the parent element's full innerText instead.
            pre_page = re.sub(
                r"(?:_Page_|page[\s:_-]+)\d+.*", "", citation_text, flags=re.IGNORECASE
            ).strip()
            if len(pre_page) <= 5:
                try:
                    parent_text = citation_el.evaluate(
                        "el => (el.parentElement && el.parentElement.innerText) || ''"
                    )
                    parent_text = (parent_text or "").strip()
                    if parent_text and "_Page_" in parent_text:
                        self.logger.debug(
                            "Citation link text too short (%r); using parent innerText: %r",
                            citation_text,
                            parent_text[:120],
                        )
                        citation_text = parent_text
                except Exception as exc:
                    self.logger.debug("Parent element fallback failed: %s", exc)

            page_number = self._extract_page_hint(citation_text)

            if page_number is None:
                continue

            targets.append(
                {
                    "citation_number": index + 1,
                    "page_number": page_number,
                    "document_name": extract_document_name(citation_text),
                    "citation_text": citation_text,
                }
            )

        return targets

    def get_citation_targets_from_panels(self) -> list[dict[str, int | str]]:
        """Open each numbered citation panel and extract its document/page target."""
        targets: list[dict[str, int | str]] = []
        citation_count = self.get_citation_count()

        for index in range(citation_count):
            citation_number = index + 1
            self.logger.info("Opening citation panel for citation %s", citation_number)
            self.open_citation_by_index(index)
            panel_text = self.extract_citation_text()
            panel_targets = extract_citation_targets(f"Citation {citation_number} {panel_text}")

            if panel_targets:
                for target in panel_targets:
                    target["citation_number"] = citation_number
                    targets.append(target)
                continue

            page_number = self._extract_page_hint(panel_text)
            if page_number is None:
                self.logger.warning(
                    "Citation panel %s did not contain a page number: %s",
                    citation_number,
                    panel_text,
                )
                self.logger.info(
                    "Visible citation page metadata after panel %s: %s",
                    citation_number,
                    self._extract_visible_citation_page_text() or "NOT FOUND",
                )
                continue

            targets.append(
                {
                    "citation_number": citation_number,
                    "page_number": page_number,
                    "document_name": extract_document_name(panel_text),
                    "citation_text": panel_text,
                }
            )

        return targets

    def open_first_citation(self) -> None:
        """Open the first relevant citation link found in the SuperAI response area."""
        if self.target_page_number is not None:
            self.open_citation_by_page(self.target_page_number)
            return

        self.open_citation_by_index(0)

    def open_citation_by_index(self, citation_index: int) -> None:
        """Open citation by zero-based index from the latest answer."""
        self.logger.info("Opening citation index %s", citation_index + 1)

        if self._extract_visible_citation_numbers():
            self._open_numbered_citation_reference(citation_index)
            self._wait_for_citation_panel_ready()
            return

        citation_links = self._latest_response_citation_links()

        try:
            citation_links.first.wait_for(state="visible", timeout=5000)
            target_index = min(citation_index, citation_links.count() - 1)
            citation = citation_links.nth(target_index)
            self.selected_citation_text = citation.inner_text().strip()
            citation.click()
        except Exception:
            self._open_numbered_citation_reference(citation_index)

        self._wait_for_citation_panel_ready()

    def extract_page_number_from_open_citation(self) -> int:
        """Extract page number from the currently open citation panel."""
        panel_text = self.extract_citation_text()

        try:
            page_number = extract_page_number(panel_text)
        except ValueError as exc:
            raise ValueError("No mandatory page number found in the open citation panel.")

        self.selected_citation_text = panel_text
        return page_number

    def open_source_document(self) -> None:
        """Click Access Source Document and keep the opened PDF page."""
        self.logger.info("Opening source document from citation panel")
        access_button = self.page.locator(CitationPageLocators.ACCESS_SOURCE_BUTTON).last
        access_button.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)

        pages_before = len(self.page.context.pages)
        current_url = self.page.url
        access_button.click()

        self.source_page = self._wait_for_source_document(pages_before, current_url)
        self.source_page.bring_to_front()
        self.source_url = self.source_page.url
        self.source_page.wait_for_load_state("domcontentloaded", timeout=SOURCE_DOC_LOAD_TIMEOUT)
        self._wait_for_viewer_ready(self.source_page)

    def navigate_to_page(self, page_number: int) -> None:
        """Navigate the source PDF viewer to the requested page before parsing."""
        if self.source_page is None:
            raise RuntimeError("Source document is not open. Call open_source_document() first.")

        self.logger.info("Navigating source document to page %s", page_number)
        self.current_page_number = page_number
        self.current_page_locator = None

        if not PDF_VIEWER_NAVIGATION_ENABLED:
            self.logger.info(
                "Skipping slow visual PDF viewer navigation; parser will read cited page %s directly.",
                page_number,
            )
            if self.source_url:
                self.source_url = urldefrag(self.source_url)[0]
            return

        if self._navigate_pdf_viewer_to_page(page_number):
            return

        raise TimeoutError(f"Page {page_number} was not reached in the source PDF viewer.")

    def extract_page_data(self) -> str:
        """Extract parser-backed data only from the currently navigated PDF page."""
        if self.source_page is None:
            raise RuntimeError("Source document is not open. Call open_source_document() first.")

        if self.current_page_number is None:
            raise RuntimeError("PDF page is not selected. Call navigate_to_page(page_number) first.")

        if not self.source_url:
            raise RuntimeError("Source PDF URL was not captured from Access Source Document.")

        self.logger.info("Parsing source PDF page %s", self.current_page_number)
        document_name = extract_document_name(self.selected_citation_text or self.source_url)
        self.logger.info(
            "PDF_EXTRACTION_CONTEXT document=%s page=%s url=%s citation=%s",
            document_name or "UNKNOWN_DOCUMENT",
            self.current_page_number,
            self.source_url,
            self.selected_citation_text,
        )
        pdf_text = extract_pdf_page_text_from_url(
            self.source_url,
            self.current_page_number,
            document_name=document_name,
        )
        return pdf_text or "NO PAGE DATA AVAILABLE"

    def extract_page_data_from_pdf(self) -> str:
        """Extract source-truth data from the selected PDF page using PDF parsing."""
        return self.extract_page_data()

    def get_pdf_total_page_count(self) -> int:
        """Return total pages in the opened source PDF."""
        if not self.source_url:
            raise RuntimeError("Source PDF URL was not captured from Access Source Document.")
        return get_pdf_page_count_from_url(self.source_url)

    def get_current_pdf_page_number(self) -> int | None:
        """Return the page number currently selected for PDF validation."""
        return self.current_page_number

    def close_source_document(self) -> None:
        """Close source document tab and return to the SuperAI chat page."""
        if self.source_page is None:
            return

        try:
            if self.source_page != self.page:
                if not self.source_page.is_closed():
                    self.source_page.close()
                if not self.page.is_closed():
                    self.page.bring_to_front()
            elif not self.page.is_closed():
                self.page.go_back(wait_until="domcontentloaded", timeout=SOURCE_DOC_LOAD_TIMEOUT)
        except Exception as exc:
            self.logger.warning("Source document cleanup skipped because a tab was closed: %s", exc)

        self.source_page = None
        self.source_url = ""
        self.current_page_number = None
        self.current_page_locator = None

    def close_citation_panel(self) -> None:
        """Close the visible citation side panel if it is open."""
        panel = self.page.locator(CitationPageLocators.CITATION_PANEL).last

        try:
            if panel.count() == 0 or not panel.is_visible(timeout=1000):
                return
        except Exception:
            return

        close_buttons = (
            panel.get_by_role("button", name=re.compile(r"close|dismiss|×|x", re.IGNORECASE)),
            panel.locator("button").filter(has_text=re.compile(r"^\s*(×|x)\s*$", re.IGNORECASE)),
            panel.locator("button").last,
        )

        for close_button in close_buttons:
            try:
                close_button.click(timeout=750)
                panel.wait_for(state="hidden", timeout=750)
                return
            except Exception:
                continue

        try:
            self.page.keyboard.press("Escape")
            panel.wait_for(state="hidden", timeout=750)
        except Exception as exc:
            self.logger.warning("Citation panel cleanup skipped: %s", exc)

    def open_citation_by_page(self, page_number: int | None = None) -> None:
        """Open citation chip that matches page number, else fallback to first."""
        self.logger.info("Opening citation for page: %s", page_number)
        citation_links = self._latest_response_citation_links()
        try:
            citation_links.first.wait_for(state="visible", timeout=5000)
        except Exception:
            self.logger.warning("Page metadata citation link not visible; opening first citation reference.")
            self.open_citation_by_index(0)
            return

        link_to_click = citation_links.first

        if page_number is not None:
            page_pattern = re.compile(rf"_Page_{page_number}\b", flags=re.IGNORECASE)
            for index in range(citation_links.count()):
                candidate = citation_links.nth(index)
                candidate_text = candidate.inner_text().strip()
                if page_pattern.search(candidate_text):
                    link_to_click = candidate
                    break

        self.selected_citation_text = link_to_click.inner_text().strip()
        link_to_click.click()

        self._wait_for_citation_panel_ready()

    def _wait_for_citation_panel_ready(self) -> None:
        """Wait until citation source controls or metadata are visible."""
        try:
            self.page.locator(CitationPageLocators.ACCESS_SOURCE_BUTTON).last.wait_for(
                state="visible",
                timeout=DEFAULT_TIMEOUT,
            )
            return
        except Exception:
            self.logger.warning(
                "Access Source Document button was not visible; checking citation metadata."
            )

        visible_metadata = self._extract_visible_citation_page_text()
        if visible_metadata:
            return

        self.page.locator(CitationPageLocators.CITATION_PANEL).last.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

    def _latest_response_citation_links(self) -> Locator:
        """Return page metadata citation links only from the latest SuperAI answer."""
        latest_response = self.page.locator(CitationPageLocators.RESPONSE_BLOCKS).last
        latest_response.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        return latest_response.locator(CitationPageLocators.CITATION_LINKS)

    def _open_numbered_citation_reference(self, citation_index: int) -> None:
        """Open citation when the response only renders clickable numeric references."""
        visible_citation_numbers = self._extract_visible_citation_numbers()
        if visible_citation_numbers:
            target_number = visible_citation_numbers[min(citation_index, len(visible_citation_numbers) - 1)]
            latest_response = self.page.locator(CitationPageLocators.RESPONSE_BLOCKS).last
            try:
                latest_response.get_by_text(
                    re.compile(rf"^\s*{target_number}\s*$")
                ).last.click(timeout=5000)
                return
            except Exception:
                self.logger.warning("Exact citation number click failed; trying generic refs.")

        numeric_references = self._get_numbered_citation_references()

        if numeric_references.count() > 0:
            target_index = min(citation_index, numeric_references.count() - 1)
            numeric_references.nth(target_index).click(timeout=DEFAULT_TIMEOUT)
            return

        latest_response = self.page.locator(CitationPageLocators.RESPONSE_BLOCKS).last
        latest_response.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        latest_response.get_by_text(re.compile(r"\b1\b")).last.click(timeout=DEFAULT_TIMEOUT)

    def _get_numbered_citation_references(self) -> Locator:
        """Return clickable numeric citation references from the latest response."""
        latest_response = self.page.locator(CitationPageLocators.RESPONSE_BLOCKS).last
        latest_response.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        return latest_response.locator(
            "a, button, [role='button'], sup"
        ).filter(has_text=re.compile(r"^\s*\d+\s*$"))

    def _extract_visible_citation_numbers(self) -> list[int]:
        """Extract trailing citation reference numbers from the latest response text."""
        latest_response = self.page.locator(CitationPageLocators.RESPONSE_BLOCKS).last
        latest_response.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        response_text = latest_response.inner_text(timeout=DEFAULT_TIMEOUT).strip()
        match = re.search(r"(?:^|\s)(\d+(?:\s*,\s*\d+)*)\s*$", response_text)

        if not match:
            return []

        return [int(number) for number in re.findall(r"\d+", match.group(1))]

    def extract_citation_text(self) -> str:
        """Extract visible citation panel text using DOM inner_text()."""
        self.logger.info("Extracting citation text")
        panel_text = ""
        panel = self.page.locator(CitationPageLocators.CITATION_PANEL).last

        try:
            panel.wait_for(state="visible", timeout=5000)
            panel_text = panel.inner_text()
        except Exception:
            self.logger.warning("Visible citation panel text not available; using metadata fallback.")

        cleaned_text = self._remove_panel_headers(panel_text)

        if cleaned_text and self._extract_page_hint(cleaned_text) is not None:
            return cleaned_text

        fallback_text = self._extract_visible_citation_page_text()
        fallback_cleaned_text = self._remove_panel_headers(fallback_text)
        if fallback_cleaned_text:
            return fallback_cleaned_text

        return cleaned_text or "NO DOM SOURCE TEXT AVAILABLE"

    def open_source_document_and_extract_text(self) -> str:
        """Backward-compatible wrapper for page-scoped parser extraction."""
        self.open_source_document()
        page_hint = self._extract_page_hint(self.selected_citation_text)
        if page_hint is None:
            return self.extract_page_data()
        self.navigate_to_page(page_hint)
        return self.extract_page_data()

    @staticmethod
    def _remove_panel_headers(text: str) -> str:
        """Remove citation panel controls from extracted DOM text."""
        ignored_lines = {
            "citation",
            "access source document",
        }
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and line.strip().lower() not in ignored_lines
        ]
        return " ".join(lines)

    def _wait_for_source_document(self, pages_before: int, current_url: str) -> Page:
        """Wait for source document to open in a new tab or current page."""
        deadline_ms = SOURCE_DOC_LOAD_TIMEOUT
        elapsed = 0
        while elapsed < deadline_ms:
            if len(self.page.context.pages) > pages_before:
                return self.page.context.pages[-1]
            if self.page.url != current_url:
                return self.page
            self.page.wait_for_timeout(500)
            elapsed += 500
        raise TimeoutError("Source document did not open in time.")

    @staticmethod
    def _extract_page_hint(citation_text: str) -> int | None:
        """Extract page number from citation text such as *_Page_12."""
        matches = re.findall(
            r"(?:_Page_|page[\s:_-]+)(\d+)",
            citation_text,
            flags=re.IGNORECASE,
        )
        return int(matches[-1]) if matches else None

    def _wait_for_viewer_ready(self, source_page: Page) -> None:
        """Wait until the document viewer has visible DOM content."""
        if self._looks_like_pdf_source(source_page.url):
            source_page.wait_for_timeout(PDF_VIEWER_READY_WAIT_MS)
            return

        try:
            source_page.locator(CitationPageLocators.PAGE_VIEWER_ROOT).first.wait_for(
                state="attached",
                timeout=SOURCE_DOC_LOAD_TIMEOUT,
            )
        except Exception:
            self.logger.warning("Viewer root was not visible; continuing with fallback.")

        source_page.wait_for_timeout(2000)

    def _navigate_pdf_viewer_to_page(self, page_number: int) -> bool:
        """Navigate PDF viewer by entering the page number in the viewer page box."""
        if self.source_page is None or not self._looks_like_pdf_source(self.source_page.url):
            return False

        base_url, _ = urldefrag(self.source_page.url)
        self.source_url = base_url

        if self._enter_page_number_in_exact_selector(page_number):
            return True

        if self._enter_page_number_in_pdf_viewer(page_number):
            return True

        if self._enter_page_number_using_toolbar_coordinates(page_number):
            return True

        self.logger.info(
            "Searching cited page %s in PDF viewer by scrolling up/down.",
            page_number,
        )
        if self._scroll_pdf_viewer_to_page(page_number):
            return True

        self.logger.warning(
            "PDF page box was not controllable. Trying page URL fragment for page %s.",
            page_number,
        )
        if self._open_pdf_url_at_page(page_number):
            return True

        raise TimeoutError(f"Unable to navigate PDF viewer to page {page_number}.")

    def _enter_page_number_in_exact_selector(self, page_number: int) -> bool:
        """Enter target page number in Edge PDF viewer's exact page selector input."""
        if self.source_page is None:
            return False

        selector_candidates = (
            "xpath=//input[@id='pageselector']",
            "input#pageselector",
            "#pageselector",
        )

        for selector in selector_candidates:
            page_selector = self.source_page.locator(selector).first

            try:
                page_selector.wait_for(state="visible", timeout=5000)
                page_selector.click(timeout=DEFAULT_TIMEOUT)
                page_selector.press("Control+A", timeout=DEFAULT_TIMEOUT)
                page_selector.fill(str(page_number), timeout=DEFAULT_TIMEOUT)
                page_selector.press("Enter", timeout=DEFAULT_TIMEOUT)
                self.source_page.wait_for_timeout(2500)

                if self._wait_until_pdf_page_selector_matches(page_number):
                    self.logger.info(
                        "Entered cited page %s using selector %s.",
                        page_number,
                        selector,
                    )
                    return True
            except Exception as exc:
                self.logger.debug("Page selector candidate failed (%s): %s", selector, exc)

        if self._enter_page_number_using_shadow_dom_selector(page_number):
            return True

        self.logger.warning(
            "#pageselector did not confirm page %s after entry.",
            page_number,
        )
        return False

    def _enter_page_number_using_shadow_dom_selector(self, page_number: int) -> bool:
        """Find #pageselector through shadow roots and enter the cited page."""
        if self.source_page is None:
            return False

        try:
            selector_found = self.source_page.evaluate(
                """(pageNumber) => {
                    const findInRoot = (root) => {
                        const direct = root.querySelector?.("input#pageselector");
                        if (direct) {
                            return direct;
                        }

                        for (const element of root.querySelectorAll?.("*") || []) {
                            if (element.shadowRoot) {
                                const found = findInRoot(element.shadowRoot);
                                if (found) {
                                    return found;
                                }
                            }
                        }

                        return null;
                    };

                    const input = findInRoot(document);
                    if (!input) {
                        return false;
                    }

                    input.focus();
                    input.value = String(pageNumber);
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                    input.dispatchEvent(new Event("change", { bubbles: true }));
                    return true;
                }""",
                page_number,
            )

            if not selector_found:
                return False

            self.source_page.keyboard.press("Enter")
            self.source_page.wait_for_timeout(2500)

            if self._wait_until_pdf_page_selector_matches(page_number):
                self.logger.info("Entered cited page %s using shadow DOM #pageselector.", page_number)
                return True
        except Exception as exc:
            self.logger.debug("Shadow DOM #pageselector entry failed: %s", exc)

        return False

    def _open_pdf_url_at_page(self, page_number: int) -> bool:
        """Open direct PDF URLs at the requested page fragment when supported."""
        if self.source_page is None or not self.source_url:
            return False

        try:
            self.source_page.goto(
                f"{self.source_url}#page={page_number}",
                wait_until="domcontentloaded",
                timeout=SOURCE_DOC_LOAD_TIMEOUT,
            )
            self.source_page.wait_for_timeout(2500)

            page_inputs = self.source_page.locator(CitationPageLocators.PDF_PAGE_INPUTS)
            if page_inputs.count() == 0:
                return False

            return self._wait_until_pdf_page_selector_matches(page_number)
        except Exception as exc:
            self.logger.debug("PDF page-fragment navigation failed: %s", exc)
            return False

    def _enter_page_number_in_pdf_viewer(self, page_number: int) -> bool:
        """Enter target page number into Microsoft Edge PDF viewer page selector."""
        if self.source_page is None:
            return False

        deadline = monotonic() + (SOURCE_DOC_LOAD_TIMEOUT / 1000)

        while monotonic() < deadline:
            page_inputs = self.source_page.locator(CitationPageLocators.PDF_PAGE_INPUTS)

            for index in range(page_inputs.count()):
                page_input = page_inputs.nth(index)

                try:
                    if not page_input.is_visible():
                        continue

                    if not self._looks_like_page_selector_input(page_input):
                        continue

                    page_input.click(timeout=5000)
                    page_input.press("Control+A", timeout=5000)
                    page_input.type(str(page_number), timeout=5000)
                    page_input.press("Enter", timeout=5000)
                    self.source_page.wait_for_timeout(3000)
                    if self._wait_until_pdf_page_selector_matches(page_number):
                        self.logger.info("Entered cited page %s in PDF page box.", page_number)
                        return True
                except Exception as exc:
                    self.logger.debug("PDF page input candidate failed: %s", exc)

            self.source_page.wait_for_timeout(500)

        return False

    def _enter_page_number_using_toolbar_coordinates(self, page_number: int) -> bool:
        """Click the visible PDF toolbar page box and enter the target page number."""
        if self.source_page is None:
            return False

        try:
            self.source_page.bring_to_front()
            self.source_page.wait_for_timeout(1000)
            viewport_size = self.source_page.viewport_size or {"width": 1280, "height": 720}
            page_box_x = int(viewport_size["width"] * 0.54)
            page_box_y = 100

            self.source_page.mouse.click(page_box_x, page_box_y, click_count=3)
            self.source_page.keyboard.press("Control+A")
            self.source_page.keyboard.type(str(page_number))
            self.source_page.keyboard.press("Enter")
            self.source_page.wait_for_timeout(2500)
            self.logger.info("Entered cited page %s in visible PDF page box.", page_number)
            return True
        except Exception as exc:
            self.logger.debug("Coordinate PDF page-box entry failed: %s", exc)
            return False

    @staticmethod
    def _looks_like_page_selector_input(page_input: Locator) -> bool:
        """Return whether an input is the PDF viewer page-number box."""
        descriptor_parts = []
        for attribute_name in ("aria-label", "title", "id", "class", "placeholder"):
            try:
                descriptor_parts.append(page_input.get_attribute(attribute_name) or "")
            except Exception:
                continue

        descriptor = " ".join(descriptor_parts).lower()
        if "page" in descriptor:
            return True

        try:
            value = page_input.input_value(timeout=1000).strip()
            return bool(re.fullmatch(r"\d+", value))
        except Exception:
            return False

    def _wait_until_pdf_page_selector_matches(self, page_number: int) -> bool:
        """Wait until the PDF toolbar page selector reflects the requested page."""
        if self.source_page is None:
            return False

        deadline = monotonic() + 10

        while monotonic() < deadline:
            page_inputs = self.source_page.locator(CitationPageLocators.PDF_PAGE_INPUTS)

            for index in range(page_inputs.count()):
                page_input = page_inputs.nth(index)

                try:
                    value = page_input.input_value(timeout=2000).strip()
                    if value == str(page_number):
                        return True
                except Exception:
                    continue

            self.source_page.wait_for_timeout(500)

        return False

    def _scroll_pdf_viewer_to_page(self, page_number: int) -> bool:
        """Scroll up/down inside the PDF viewer to reach the requested page."""
        if self.source_page is None:
            return False

        try:
            self.source_page.bring_to_front()
            self.source_page.mouse.click(800, 400)

            self.logger.info("Scrolling up to the first PDF page.")
            self.source_page.keyboard.press("Home")
            self.source_page.wait_for_timeout(1000)

            if page_number == 1:
                self.logger.info("Reached requested PDF page 1 by scrolling.")
                return True

            self.logger.info("Scrolling down to requested PDF page %s.", page_number)
            for current_page in range(2, page_number + 1):
                self.source_page.keyboard.press("PageDown")
                self.source_page.wait_for_timeout(450)
                self.logger.info("Scrolled PDF viewer to page candidate %s.", current_page)

            self.source_page.wait_for_timeout(1500)
            self.logger.info("Finished scroll search for requested PDF page %s.", page_number)
            return True
        except Exception as exc:
            self.logger.debug("PDF scroll navigation failed: %s", exc)
            return False

    def _get_page_locator(self, page_number: int) -> Locator | None:
        """Return a locator for a page-specific DOM container when available."""
        if self.source_page is None:
            return None

        selectors = [
            f"[data-page-number='{page_number}']",
            f"[data-page='{page_number}']",
            f"[aria-label='Page {page_number}']",
            f"[aria-label*='Page {page_number} ' i]",
            f"#pageContainer{page_number}",
            f"#page{page_number}",
        ]

        for selector in selectors:
            locator = self.source_page.locator(selector)
            if locator.count() > 0:
                return locator

        return None

    def _use_page_number_input(self, page_number: int) -> bool:
        """Try viewer page-number inputs before slower scroll scanning."""
        if self.source_page is None:
            return False

        inputs = self.source_page.locator(
            "input[aria-label*='page' i], input[title*='page' i], "
            "input[type='number'], input[placeholder*='page' i]"
        )

        for index in range(inputs.count()):
            candidate = inputs.nth(index)
            if not candidate.is_visible():
                continue
            candidate.fill(str(page_number))
            candidate.press("Enter")
            self.source_page.wait_for_timeout(2500)
            return True

        return False

    def _find_visible_page_locator(self, page_number: int) -> Locator | None:
        """Find a visible page container for the requested page."""
        direct_locator = self._get_page_locator(page_number)
        if direct_locator and direct_locator.count() > 0 and direct_locator.first.is_visible():
            return direct_locator.first

        if self.source_page is None:
            return None

        containers = self.source_page.locator(CitationPageLocators.PAGE_CONTAINERS)
        for index in range(containers.count()):
            container = containers.nth(index)
            if not container.is_visible():
                continue

            descriptor = " ".join(
                value or ""
                for value in (
                    container.get_attribute("data-page-number"),
                    container.get_attribute("data-page"),
                    container.get_attribute("aria-label"),
                    container.get_attribute("id"),
                    container.inner_text(timeout=3000)[:80],
                )
            )

            if self._descriptor_matches_page(descriptor, page_number):
                return container

        return None

    def _scroll_until_page_visible(self, page_number: int) -> Locator | None:
        """Scroll down and up through the viewer until the requested page appears."""
        if self.source_page is None:
            return None

        located_page = self._scroll_in_direction_until_page_visible(page_number, "down")
        if located_page is not None:
            return located_page

        return self._scroll_in_direction_until_page_visible(page_number, "up")

    def _scroll_in_direction_until_page_visible(
        self,
        page_number: int,
        direction: str,
    ) -> Locator | None:
        """Scroll one direction in the document viewer until the page appears."""
        if self.source_page is None:
            return None

        deadline = monotonic() + (SOURCE_DOC_LOAD_TIMEOUT / 1000)
        last_scroll_top = -1
        direction_multiplier = 1 if direction == "down" else -1

        while monotonic() < deadline:
            located_page = self._find_visible_page_locator(page_number)
            if located_page is not None:
                located_page.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT)
                return located_page

            scroll_top = self.source_page.evaluate(
                """() => {
                    const roots = [...document.querySelectorAll(
                        '[class*="viewer" i], [id*="viewer" i], [class*="pdf" i], body'
                    )];
                    const scrollRoot = roots.find((el) => el.scrollHeight > el.clientHeight) || document.scrollingElement;
                    scrollRoot.scrollBy(0, %s * Math.max(700, scrollRoot.clientHeight * 0.85));
                    return scrollRoot.scrollTop;
                }""" % direction_multiplier
            )

            if scroll_top == last_scroll_top:
                return None

            last_scroll_top = scroll_top
            sleep(0.75)

        return None

    def _wait_for_page_text(self, page_locator: Locator) -> None:
        """Wait until the target page container has extractable text."""
        deadline = monotonic() + (DEFAULT_TIMEOUT / 1000)

        while monotonic() < deadline:
            text = page_locator.inner_text(timeout=5000).strip()
            if text:
                return
            sleep(0.5)

        raise TimeoutError("Correct page was visible but no DOM text was available.")

    def _extract_visible_viewport_text(self) -> str:
        """Extract only text from elements visible in the current source viewport."""
        if self.source_page is None:
            return ""

        text = self.source_page.evaluate(
            """() => {
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                const visibleTexts = [];

                for (const el of document.body.querySelectorAll('table, [role="table"], canvas + .textLayer, .textLayer, p, span, div')) {
                    const rect = el.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0 &&
                        rect.bottom >= 0 && rect.right >= 0 &&
                        rect.top <= viewportHeight && rect.left <= viewportWidth;
                    const text = (el.innerText || el.textContent || '').trim();

                    if (visible && text) {
                        visibleTexts.push(text);
                    }
                }

                return visibleTexts.join('\\n');
            }"""
        )

        return self._normalize_dom_text(text)

    def _extract_visible_citation_page_text(self) -> str:
        """Extract visible citation metadata text from the current answer/panel only."""
        text = self.page.evaluate(
            """() => {
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                const visibleTexts = [];
                const roots = [];
                const responses = Array.from(document.querySelectorAll('.received'));
                const latestResponse = responses[responses.length - 1];
                if (latestResponse) {
                    roots.push(latestResponse);
                }

                const panel = Array.from(document.querySelectorAll(
                    'aside, section, dialog, [role="dialog"], [class*="citation" i], [class*="drawer" i], [class*="panel" i]'
                )).find((el) => {
                    const rect = el.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0 &&
                        rect.bottom >= 0 && rect.right >= 0 &&
                        rect.top <= viewportHeight && rect.left <= viewportWidth;
                    const text = (el.innerText || el.textContent || '').trim();
                    return visible && text && /(_Page_|page[\\s:_-]+\\d+)/i.test(text);
                });
                if (panel) {
                    roots.push(panel);
                }

                for (const root of roots) {
                    for (const el of [root, ...root.querySelectorAll('*')]) {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0 &&
                            rect.bottom >= 0 && rect.right >= 0 &&
                            rect.top <= viewportHeight && rect.left <= viewportWidth;
                        const text = (el.innerText || el.textContent || '').trim();

                        if (visible && text && /(_Page_|page[\\s:_-]+\\d+)/i.test(text)) {
                            const matches = text.match(/[A-Za-z0-9 &()',./-]{2,80}(?:_Page_|page[\\s:_-]+)\\d+/gi) || [];
                            visibleTexts.push(...matches);
                        }
                    }
                }

                return visibleTexts.join('\\n');
            }"""
        )

        return self._normalize_dom_text(text)

    @staticmethod
    def _descriptor_matches_page(descriptor: str, page_number: int) -> bool:
        """Return whether a DOM descriptor points at the requested page."""
        patterns = (
            rf"\bpage\s*{page_number}\b",
            rf"\bpageContainer{page_number}\b",
            rf"\b{page_number}\b",
        )
        return any(re.search(pattern, descriptor, flags=re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _normalize_dom_text(text: str) -> str:
        """Normalize DOM text while preserving page-scoped content."""
        return " ".join(text.split())

    @staticmethod
    def _looks_like_pdf_source(url: str) -> bool:
        """Return whether source document is likely handled by Microsoft Edge PDF viewer."""
        normalized_url = url.lower()
        return ".pdf" in normalized_url or "blob.core.windows.net" in normalized_url
