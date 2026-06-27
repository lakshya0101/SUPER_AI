"""Credential configuration.

Environment variables are preferred so the same framework can run safely in
local, CI, and enterprise secret-management environments.
"""

import os

EMAIL = os.getenv("SUPERAI_EMAIL")
PASSWORD = os.getenv("SUPERAI_PASSWORD")

