"""Application and browser configuration."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SUPER_AI_URL = "https://mnk-genai-uat.azurewebsites.net/auth/login"

BROWSER_NAME = "msedge"
EDGE_USER_DATA_DIR = BASE_DIR / ".edge_user_data"
HEADLESS_MODE = False
SLOW_MO = int(os.getenv("SLOW_MO", "150"))

DEFAULT_TIMEOUT = 60000
SHORT_TIMEOUT = 3000
AI_RESPONSE_TIMEOUT = 90000
AI_RESPONSE_SETTLE_TIME = int(os.getenv("AI_RESPONSE_SETTLE_TIME", "1500"))
SOURCE_DOC_LOAD_TIMEOUT = 30000
PDF_VIEWER_NAVIGATION_ENABLED = False
PDF_VIEWER_READY_WAIT_MS = 800

SCREENSHOT_DIR = BASE_DIR / "screenshots"
REPORTS_DIR = BASE_DIR / "reports"
DATA_DIR = BASE_DIR / "data"

VALIDATION_QUESTIONS_FILE = Path(
    os.getenv("VALIDATION_QUESTIONS_FILE", str(DATA_DIR / "validation_ques.csv"))
)
OUTPUT_RESULTS_FILE = Path(
    os.getenv("OUTPUT_RESULTS_FILE", str(BASE_DIR / "output_results.csv"))
)

OPENAI_VALIDATION_ENABLED = (
    os.getenv("OPENAI_VALIDATION_ENABLED", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
OPENAI_VALIDATION_MODEL = os.getenv("OPENAI_VALIDATION_MODEL", "gpt-5.4")
OPENAI_VALIDATION_TIMEOUT = int(os.getenv("OPENAI_VALIDATION_TIMEOUT", "45"))

# Vision extraction uses GPT-4o to read image-based PDF tables as a last resort.
# Set AZURE_OPENAI_VISION_DEPLOYMENT to a vision-capable deployment (e.g. gpt-4o).
# Falls back to AZURE_OPENAI_DEPLOYMENT when this is not set.
# Disable with VISION_EXTRACTION_ENABLED=0 if you want to avoid the extra API cost.
VISION_EXTRACTION_ENABLED = (
    os.getenv("VISION_EXTRACTION_ENABLED", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
CENTRAL_WORKSPACE_FILE = Path(
    os.getenv(
        "CENTRAL_WORKSPACE_FILE",
        str(Path.home() / "Downloads" / "central.workspace.json"),
    )
)
