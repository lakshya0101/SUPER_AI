"""Run automation in parallel -- one incognito browser process per Division Name.

Usage
-----
    python run_parallel_divisions.py
    python run_parallel_divisions.py --csv data/validation_ques.csv
    python run_parallel_divisions.py --logins C:/Users/.../UserLogin.xlsx
    python run_parallel_divisions.py --divisions Diacar Victrix
    python run_parallel_divisions.py --max-parallel 3

How it works
------------
1. Reads the main validation_ques.csv and groups rows by Division Name.
2. Reads per-division credentials from UserLogin.xlsx (columns: UserName, Password, Division).
3. Writes a temporary per-division CSV to data/temp_divisions/.
4. Spawns one 'python main.py' subprocess per division with:
     VALIDATION_QUESTIONS_FILE  -- path to the division's temp CSV
     OUTPUT_RESULTS_FILE        -- division-specific output path
     SUPER_AI_USERNAME          -- division's login email
     SUPER_AI_PASSWORD          -- division's password
     INCOGNITO_MODE=1           -- launches Edge in InPrivate (no shared session)
5. Waits for all subprocesses to finish and prints a summary table.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = DATA_DIR / "temp_divisions"
DEFAULT_CSV = DATA_DIR / "validation_ques.csv"
DEFAULT_LOGINS = Path(r"C:\Users\lakshya.dogra\Downloads\UserLogin.xlsx")
DEFAULT_MAX_PARALLEL = 3


# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_logins(path: Path) -> dict[str, tuple[str, str]]:
    """Return {Division: (username, password)} from UserLogin.xlsx."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is required: pip install openpyxl")

    wb = openpyxl.load_workbook(path)
    ws = wb.active
    logins: dict[str, tuple[str, str]] = {}
    headers = None
    for row in ws.iter_rows(values_only=True):
        if headers is None:
            headers = [str(c).strip() if c else "" for c in row]
            continue
        if not any(row):
            continue
        row_dict = dict(zip(headers, [str(c).strip() if c is not None else "" for c in row]))
        division = row_dict.get("Division", "").strip()
        username = row_dict.get("UserName", "").strip()
        password = row_dict.get("Password", "").strip()
        if division and username:
            logins[division] = (username, password)
    return logins


def group_by_division(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        division = (row.get("Division Name") or "").strip() or "Unknown"
        groups.setdefault(division, []).append(row)
    return groups


def write_division_csv(division: str, rows: list[dict[str, str]], temp_dir: Path) -> Path:
    safe_name = division.replace(" ", "_").replace("/", "-")
    path = temp_dir / f"division_{safe_name}.csv"
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def spawn_division(
    division: str,
    csv_path: Path,
    output_path: Path,
    log_path: Path,
    username: str,
    password: str,
) -> tuple[subprocess.Popen, object]:
    env = os.environ.copy()
    env["VALIDATION_QUESTIONS_FILE"] = str(csv_path)
    env["OUTPUT_RESULTS_FILE"] = str(output_path)
    env["SUPER_AI_USERNAME"] = username
    env["SUPER_AI_PASSWORD"] = password
    env["INCOGNITO_MODE"] = "1"

    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "main.py")],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(BASE_DIR),
    )
    print(f"  STARTED  [{division:20s}]  user={username}  PID={proc.pid}")
    return proc, log_file


# ---------------------------------------------------------------------------

def run(
    csv_path: Path = DEFAULT_CSV,
    logins_path: Path = DEFAULT_LOGINS,
    selected_divisions: list[str] | None = None,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*65}")
    print(f"  Parallel Division Runner  --  {timestamp}")
    print(f"  Source CSV  : {csv_path}")
    print(f"  Logins file : {logins_path}")
    print(f"  Mode        : INCOGNITO (InPrivate Edge, isolated sessions)")
    print(f"{'='*65}\n")

    # Load questions
    all_rows = read_csv(csv_path)
    if not all_rows:
        print("ERROR: CSV is empty.")
        return

    # Load credentials
    if logins_path.exists():
        logins = read_logins(logins_path)
        print(f"Credentials loaded for divisions: {sorted(logins.keys())}")
    else:
        print(f"WARNING: Logins file not found at {logins_path}. Will use default credentials for all divisions.")
        logins = {}

    groups = group_by_division(all_rows)

    if selected_divisions:
        missing = [d for d in selected_divisions if d not in groups]
        if missing:
            print(f"WARNING: Divisions not found in CSV: {missing}")
        groups = {d: rows for d, rows in groups.items() if d in selected_divisions}

    if not groups:
        print("No divisions to process.")
        return

    print(f"\nDivisions to run  : {sorted(groups.keys())}")
    print(f"Questions total   : {sum(len(r) for r in groups.values())}")
    print(f"Max parallel      : {max_parallel}\n")

    # Build work queue
    queue = []
    no_creds = []
    for division, rows in sorted(groups.items()):
        safe = division.replace(" ", "_").replace("/", "-")
        div_csv = write_division_csv(division, rows, TEMP_DIR)
        output_file = BASE_DIR / f"output_results_{safe}_{timestamp}.csv"
        log_file = TEMP_DIR / f"log_{safe}_{timestamp}.txt"

        if division in logins:
            username, password = logins[division]
        else:
            # Fall back to env/default credentials
            username = os.getenv("SUPER_AI_USERNAME", "")
            password = os.getenv("SUPER_AI_PASSWORD", "")
            no_creds.append(division)

        queue.append((division, div_csv, output_file, log_file, username, password))
        print(f"  Queued  [{division:20s}]  {len(rows):3d} questions  user={username}")

    if no_creds:
        print(f"\nWARNING: No dedicated credentials for: {no_creds}. Using default account.")

    print(f"\nLaunching {len(queue)} division(s), max {max_parallel} browsers at a time...\n")

    active: list[tuple[str, subprocess.Popen, object, Path]] = []
    results: list[dict] = []

    def _wait_for_one() -> None:
        while True:
            for i, (div, proc, log_fh, out_path) in enumerate(active):
                rc = proc.poll()
                if rc is not None:
                    log_fh.close()
                    status = "DONE" if rc == 0 else f"FAILED (exit {rc})"
                    out_xlsx = out_path.with_suffix(".xlsx")
                    results.append({
                        "division": div,
                        "status": status,
                        "output": str(out_xlsx) if out_xlsx.exists() else "(no output yet)",
                    })
                    print(f"  FINISHED [{div:20s}]  {status}")
                    active.pop(i)
                    return
            time.sleep(1)

    for division, div_csv, output_file, log_file, username, password in queue:
        while len(active) >= max_parallel:
            _wait_for_one()
        proc, log_fh = spawn_division(division, div_csv, output_file, log_file, username, password)
        active.append((division, proc, log_fh, output_file))

    while active:
        _wait_for_one()

    # Summary
    print(f"\n{'='*65}")
    print("  SUMMARY")
    print(f"{'='*65}")
    for r in results:
        print(f"  [{r['status']:25s}]  {r['division']:20s}  ->  {r['output']}")

    passed = sum(1 for r in results if r["status"] == "DONE")
    print(f"\n  {passed}/{len(results)} divisions completed successfully.")
    print(f"  Logs: {TEMP_DIR}")
    print(f"{'='*65}\n")


# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run main.py in parallel -- one incognito Edge process per Division."
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV),
        help=f"Path to validation_ques.csv (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--logins",
        default=str(DEFAULT_LOGINS),
        help=f"Path to UserLogin.xlsx with UserName/Password/Division columns (default: {DEFAULT_LOGINS})",
    )
    parser.add_argument(
        "--divisions",
        nargs="+",
        default=None,
        metavar="DIVISION",
        help="Run only specific divisions. Example: --divisions Diacar Victrix",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=DEFAULT_MAX_PARALLEL,
        help=f"Max simultaneous browser processes (default: {DEFAULT_MAX_PARALLEL})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        csv_path=Path(args.csv),
        logins_path=Path(args.logins),
        selected_divisions=args.divisions,
        max_parallel=args.max_parallel,
    )
