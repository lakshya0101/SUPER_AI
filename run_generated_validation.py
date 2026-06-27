"""Generate questions from Azure Blob and then run SuperAI validation."""

from datetime import datetime
import os
from pathlib import Path
from shutil import copy2

from auto_question_generator import run as generate_questions
from config.settings import OUTPUT_RESULTS_FILE, VALIDATION_QUESTIONS_FILE
from main import test_ask_questions_and_save_responses


def _archive_file(file_path: Path, archive_dir: Path, timestamp: str) -> Path | None:
    """Copy an existing workflow file into the archive folder."""
    if not file_path.exists():
        return None

    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
    copy2(file_path, archive_path)
    print(f"WORKFLOW_ARCHIVED_FILE = {archive_path.resolve()}")
    return archive_path


def archive_previous_workflow_files() -> None:
    """Archive previous questions before generating a new run."""
    archive_dir = Path(
        os.getenv(
            "QUESTIONS_ARCHIVE_DIR",
            r"C:\Users\Khushi.rawat\Desktop\Questions Archive",
        )
    )
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M%S")

    _archive_file(VALIDATION_QUESTIONS_FILE, archive_dir, timestamp)


def run_pipeline() -> None:
    """Run the complete generated-question validation workflow."""
    archive_previous_workflow_files()
    generated = generate_questions()
    if not generated:
        print(
            "WORKFLOW_SKIPPED_VALIDATION = No new or updated Blob PDF files were found."
        )
        return
    test_ask_questions_and_save_responses()


if __name__ == "__main__":
    run_pipeline()
