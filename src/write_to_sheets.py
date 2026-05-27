"""
Stage 2: Read today's snapshot from data/<YYYY-MM-DD>.json and write
the values to the Indices tab of the target sheet.

Row math:
  Cell A6 = 2015-12-31, so row(d) = 6 + (d - 2015-12-31).days
  (sheet has every calendar day pre-filled in column A)

Forward-fill: if a calendar day is a holiday/weekend, niftyindices has
no row for it. We use the most recent prior trading day's value for
every column on that calendar row, matching the manual prompt's rule.

Writes are batched via worksheet.batch_update so we hit the Sheets API
once per run instead of 27 times (3 days × 9 columns).
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1Cf06j1pQKrHfjv48Rkh2lZpElZDlqE7hD3M3NZP9iQE"
WORKSHEET_NAME = "Indices"

BASE_DATE = date(2015, 12, 31)  # Sheet row 6
BASE_ROW = 6

# Number of calendar days back from today to write (inclusive of today).
# Covers a Friday-Monday weekend with one buffer day.
WRITE_WINDOW_DAYS = 3

# Column targets per index. Keys must exactly match the index names used
# in fetch_niftyindices.py.
TRI_COLUMNS = {
    "NIFTY 50": "B",
    "NIFTY 100": "C",
    "NIFTY 500": "D",
    "NIFTY MIDCAP 150": "E",
    "NIFTY SMALLCAP 250": "F",
    "NIFTY500 MULTICAP 50:25:25": "Z",
    "NIFTY LARGEMIDCAP 250": "AA",
    "NIFTY REITS & INVITS": "AB",
}
PRICE_COLUMNS = {
    "NIFTY MIDSMALLCAP 400": "AG",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def row_for_date(d: date) -> int:
    return BASE_ROW + (d - BASE_DATE).days


def parse_niftydate(s: str) -> date:
    """niftyindices returns dates like '27 May 2026' or '27-May-2026'."""
    s = s.strip().replace("-", " ")
    return datetime.strptime(s, "%d %b %Y").date()


def clean_number(s) -> float:
    """Strip commas and parse to float. Returns None if unparseable."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    cleaned = str(s).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def build_value_map(snapshot: dict) -> dict[str, dict[date, float]]:
    """
    Return {index_name: {trading_date: value, ...}, ...}.
    For TRI rows: look for 'TotalReturnsIndex' (also tries 'TR' fallbacks).
    For Price rows: look for 'CLOSE'.
    """
    value_map: dict[str, dict[date, float]] = {}

    for name, rows in snapshot.get("tri", {}).items():
        per_date: dict[date, float] = {}
        for r in rows:
            # niftyindices uses different field names in different responses.
            date_str = r.get("Date") or r.get("HistoricalDate") or r.get("TradeDate")
            val = (
                r.get("TotalReturnsIndex")
                or r.get("TRI")
                or r.get("TotalReturnIndex")
            )
            if not date_str or val is None:
                continue
            try:
                per_date[parse_niftydate(date_str)] = clean_number(val)
            except ValueError:
                continue
        value_map[name] = per_date

    for name, rows in snapshot.get("price", {}).items():
        per_date = {}
        for r in rows:
            date_str = r.get("HistoricalDate") or r.get("Date") or r.get("TradeDate")
            val = r.get("CLOSE") or r.get("Close")
            if not date_str or val is None:
                continue
            try:
                per_date[parse_niftydate(date_str)] = clean_number(val)
            except ValueError:
                continue
        value_map[name] = per_date

    return value_map


def value_with_forward_fill(per_date: dict[date, float], target: date) -> float | None:
    """Return per_date[target] if present, else the most recent prior date's value."""
    if target in per_date:
        return per_date[target]
    candidates = [d for d in per_date.keys() if d <= target]
    if not candidates:
        return None
    return per_date[max(candidates)]


def main() -> None:
    today = date.today()
    snapshot_path = Path(__file__).resolve().parent.parent / "data" / f"{today.isoformat()}.json"
    if not snapshot_path.exists():
        print(f"FATAL: snapshot not found at {snapshot_path}", file=sys.stderr)
        sys.exit(1)

    snapshot = json.loads(snapshot_path.read_text())
    value_map = build_value_map(snapshot)

    # Auth
    sa_path = os.environ.get("GCP_SA_PATH", "credentials/service_account.json")
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)

    # Build batch updates for last N calendar days
    updates: list[dict] = []
    days_to_write = [today - timedelta(days=i) for i in range(WRITE_WINDOW_DAYS)]

    for d in days_to_write:
        row = row_for_date(d)
        for name, col in {**TRI_COLUMNS, **PRICE_COLUMNS}.items():
            per_date = value_map.get(name, {})
            val = value_with_forward_fill(per_date, d)
            if val is None:
                print(f"  skip {d} {col}{row} {name}: no value", file=sys.stderr)
                continue
            updates.append({
                "range": f"{col}{row}",
                "values": [[val]],
            })
            print(f"  queue {d} {col}{row} {name} = {val}")

    if not updates:
        print("Nothing to write.", file=sys.stderr)
        sys.exit(1)

    # value_input_option='USER_ENTERED' so Sheets parses it as a number
    ws.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"\nWrote {len(updates)} cells to '{WORKSHEET_NAME}'.")


if __name__ == "__main__":
    main()
