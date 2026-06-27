"""Page object for the authenticated Super AI application."""

import re
from time import monotonic, sleep

from playwright.sync_api import Page

from config.settings import (
    AI_RESPONSE_SETTLE_TIME,
    AI_RESPONSE_TIMEOUT,
    DEFAULT_TIMEOUT,
)
from utils.logger import get_logger


class SuperAIPageLocators:
    """Locators for authenticated Super AI application pages."""

    CHAT_INPUT = "//textarea[@placeholder='Ask SuperAI anything...']"
    APP_ROOT = "body"
    RESPONSE_BLOCKS = ".received"
    SUBMIT_BUTTON = ".chat-input-container .senticon"


class SuperAIPage:
    """Actions and assertions for the Super AI application."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.logger = get_logger(self.__class__.__name__)
        self.previous_response_count = 0

    def verify_login(self) -> bool:
        """Verify that the user reached the authenticated application."""
        self.logger.info("Verifying Super AI login")
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
        except Exception as exc:
            self.logger.info("Continuing login verification after load-state wait: %s", exc)

        self.page.wait_for_selector(
            SuperAIPageLocators.CHAT_INPUT,
            timeout=DEFAULT_TIMEOUT,
        )

        current_url = self.page.url.lower()
        is_login_page = "/auth/login" in current_url or "login.microsoftonline" in current_url

        if is_login_page:
            raise AssertionError(f"Login verification failed. Current URL: {self.page.url}")

        self.logger.info("Login verified successfully. Current URL: %s", self.page.url)
        return True

    def ask_question(self, question: str) -> str:
        """Ask one question in Super AI using DOM locators and return response."""
        self.logger.info("Asking question: %s", question)
        self.previous_response_count = self.page.locator(
            SuperAIPageLocators.RESPONSE_BLOCKS
        ).count()

        self.page.wait_for_selector(
            SuperAIPageLocators.CHAT_INPUT,
            timeout=DEFAULT_TIMEOUT,
        )
        self.page.fill(SuperAIPageLocators.CHAT_INPUT, question)
        self.page.click(SuperAIPageLocators.SUBMIT_BUTTON)
        return self.get_response(question)

    def get_response(self, question: str = "") -> str:
        """Wait for and extract the latest Super AI response text from the DOM."""
        self._wait_for_response(self.previous_response_count, question)
        response = self._extract_latest_response(question)
        self.logger.info("Response captured for question")
        return response

    def _wait_for_response(self, previous_response_count: int, question: str) -> None:
        """Wait until a real response block appears after the submitted question."""
        deadline = monotonic() + (AI_RESPONSE_TIMEOUT / 1000)
        response_locator = self.page.locator(SuperAIPageLocators.RESPONSE_BLOCKS)

        while monotonic() < deadline:
            response_count = response_locator.count()

            if response_count <= previous_response_count:
                sleep(0.5)
                continue

            response = self._normalize_text(response_locator.nth(response_count - 1).inner_text())

            if self._is_response_candidate(response, self._normalize_text(question)):
                self._wait_for_response_to_stabilize(response_count - 1)
                return

            sleep(0.5)

        raise TimeoutError(f"Timed out waiting for Super AI response: {question}")

    def _wait_for_response_to_stabilize(self, response_index: int) -> None:
        """Wait until the latest response stops changing before reading it."""
        locator = self.page.locator(SuperAIPageLocators.RESPONSE_BLOCKS).nth(response_index)
        deadline = monotonic() + max(8, (AI_RESPONSE_SETTLE_TIME / 1000) * 4)
        stable_deadline = monotonic() + (AI_RESPONSE_SETTLE_TIME / 1000)
        previous_text = ""

        while monotonic() < deadline:
            current_text = self._normalize_text(locator.inner_text())

            if self._is_terminal_no_match_response(current_text):
                sleep(0.2)
                return

            if current_text != previous_text:
                previous_text = current_text
                stable_deadline = monotonic() + (AI_RESPONSE_SETTLE_TIME / 1000)
            elif monotonic() >= stable_deadline:
                return

            sleep(0.5)

    def _extract_latest_response(self, question: str) -> str:
        """Extract the latest non-empty response text visible on the page."""
        all_texts = self.page.locator(SuperAIPageLocators.RESPONSE_BLOCKS).all_inner_texts()
        cleaned_texts = [self._normalize_text(text) for text in all_texts if text.strip()]
        question_text = self._normalize_text(question)

        fallback_texts = [
            text for text in cleaned_texts if self._is_response_candidate(text, question_text)
        ]

        if fallback_texts:
            return fallback_texts[-1]

        return "NO RESPONSE"

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize visible text for comparison and CSV output."""
        return " ".join(text.split())

    @staticmethod
    def _is_terminal_no_match_response(text: str) -> bool:
        """Return whether the response is a final no-source/irrelevant message."""
        normalized_with_apostrophes = " ".join(
            text.lower()
            .replace("’", "'")
            .replace("‘", "'")
            .replace("`", "'")
            .split()
        )
        normalized = normalized_with_apostrophes.replace("'", "")
        normalized_loose = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        terminal_phrases = (
            "i couldnt find any matching information in the provided sources",
            "i could not find any matching information in the provided sources",
            "couldnt find any matching information",
            "could not find any matching information",
            "i can only help with queries regarding products and policies",
            "can only help with queries regarding products and policies",
            "no matching information was found",
        )
        loose_terminal_phrases = (
            "i couldn t find any matching information in the provided sources",
            "couldn t find any matching information",
        )
        return any(phrase in normalized for phrase in terminal_phrases) or any(
            phrase in normalized_loose for phrase in loose_terminal_phrases
        )

    @staticmethod
    def _is_response_candidate(text: str, question: str) -> bool:
        """Return whether a text block looks like an AI response."""
        ignored_phrases = (
            "Product/Policy Query",
            "Toggle back to Super Coach",
            "HISTORY",
            "Mankind Pharma",
            "All Rights Reserved",
            "Access Source Document",
        )

        if not text or text == question:
            return False

        if len(text) < 25:
            return False

        if text.startswith("Citation"):
            return False

        return not any(phrase in text for phrase in ignored_phrases)
