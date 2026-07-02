"""
Stage 2 (monthly): Read sectoral snapshot from data/sectoral-<YYYY-MM-DD>.json
and write TRI values to columns M-Y of the Indices tab.

Writes the full 32-day calendar window (today + 31 days back), forward-filling
weekend/holiday rows with the previous trading day's value.
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

BASE_DATE = date(2015, 12, 31)
BASE_ROW = 6

WRITE_WINDOW_DAYS = 32

SECTORAL_COLUMNS = {
    "NIFTY AUTO": "M",
    "NIFTY BANK": "N",
    "NIFTY CHEMICALS": "O",
    "NIFTY CONSUMER DURABLES": "P",
    "NIFTY FINANCIAL SERVICES": "Q",
    "NIFTY FMCG": "R",
    "NIFTY HEALTHCARE": "S",   # was "NIFTY HEALTHCARE INDEX"
    "NIFTY IT": "T",
    "NIFTY MEDIA": "U",
    "NIFTY METAL": "V",
    "NIFTY OIL & GAS": "W",
    "NIFTY PHARMA": "X",
    "NIFTY REALTY": "Y",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def row_for_date(d: date) -> int:
    return BASE_ROW + (d - BASE_DATE).days


def parse_niftydate(s: str) -> date:
    s = s.strip().replace("-", " ")
    return datetime.strptime(s, "%d %b %Y").date()


def clean_number(s):
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


def build_value_map(snapshot: dict) -> dict:
    value_map = {}
    for name, rows in snapshot.get("tri", {}).items():
        per_date = {}
        for r in rows:
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
    return value_map


def value_with_forward_fill(per_date: dict, target: date):
    if target in per_date:
        return per_date[target]
    candidates = [d for d in per_date.keys() if d <= target]
    if not candidates:
        return None
    return per_date[max(candidates)]


def main() -> None:
    today = date.today()
    snapshot_path = (
        Path(__file__).resolve().parent.parent / "data" / f"sectoral-{today.isoformat()}.json"
    )
    if not snapshot_path.exists():
        print(f"No sectoral snapshot at {snapshot_path}. Stage 1 likely skipped (not last day of month).")
        sys.exit(0)

    snapshot = json.loads(snapshot_path.read_text())
    value_map = build_value_map(snapshot)

    sa_path = os.environ.get("GCP_SA_PATH", "credentials/service_account.json")
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)

    updates = []
    days_to_write = [today - timedelta(days=i) for i in range(WRITE_WINDOW_DAYS)]

    for d in days_to_write:
        row = row_for_date(d)
        for name, col in SECTORAL_COLUMNS.items():
            per_date = value_map.get(name, {})
            val = value_with_forward_fill(per_date, d)
            if val is None:
                print(f"  skip {d} {col}{row} {name}: no value", file=sys.stderr)
                continue
            updates.append({
                "range": f"{col}{row}",
                "values": [[val]],
            })

    if not updates:
        print("Nothing to write.", file=sys.stderr)
        sys.exit(1)

    ws.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"Wrote {len(updates)} cells across {WRITE_WINDOW_DAYS} days × {len(SECTORAL_COLUMNS)} indices.")


if __name__ == "__main__":
    main()
