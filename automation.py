"""Backward-compatible entry point for the Super AI automation framework."""

from main import test_ask_questions_and_save_responses


def run_pipeline() -> None:
    """Run the CSV-driven Super AI question workflow."""
    test_ask_questions_and_save_responses()



if __name__ == "__main__":
    run_pipeline()
