"""
Stage 1 (monthly): Fetch TRI for 13 sectoral indices from niftyindices.com.
Index names below are VERIFIED against the actual dropdown on
https://www.niftyindices.com/reports/historical-data (verified 2026-08-03).
Do not modify without re-checking the live dropdown.
Self-filters to last day of the month. Writes snapshot to
data/sectoral-<YYYY-MM-DD>.json.
"""
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

# NOTE: niftyindices.com migrated this endpoint from /Backpage.aspx/<method>
# to /BackPage/<method> — verified via browser Network tab 2026-08-03.
# If this fails again with "Expecting value: line 1 column 2 (char 1)" the
# endpoint has likely moved again; check /reports/historical-data Network tab.
TRI_URL = "https://www.niftyindices.com/BackPage/getTotalReturnIndexString"

# Exact names from the live niftyindices.com dropdown (verified 2026-08-03).
# These are also the keys used by write_sectoral_to_sheets.py SECTORAL_COLUMNS.
SECTORAL_INDICES = [
    "NIFTY AUTO",
    "NIFTY BANK",
    "NIFTY CHEMICALS",
    "NIFTY CONSUMER DURABLES",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY FMCG",
    "NIFTY HEALTHCARE",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY OIL & GAS",
    "NIFTY PHARMA",
    "NIFTY REALTY",
]

LOOKBACK_DAYS = 32

HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.niftyindices.com/reports/historical-data",
    "Origin": "https://www.niftyindices.com",
}


def fmt_date(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def is_last_day_of_month(d: date) -> bool:
    return (d + timedelta(days=1)).day == 1


def fetch_tri(index_name: str, start: date, end: date) -> list[dict]:
    payload = {
        "cinfo": json.dumps({
            "name": index_name,
            "startDate": fmt_date(start),
            "endDate": fmt_date(end),
            "indexName": index_name,
        })
    }
    resp = requests.post(TRI_URL, json=payload, headers=HEADERS, timeout=30)
    # Debug line — cheap insurance for the next endpoint migration.
    # On failure, shows whether we got HTML, empty body, redirect, or auth wall.
    print(f"[DEBUG] {index_name} status={resp.status_code} body[:200]={resp.text[:200]!r}")
    resp.raise_for_status()
    outer = resp.json()
    return json.loads(outer.get("d", "[]"))


def main() -> None:
    today = date.today()
#    if not is_last_day_of_month(today):
 #       print(f"{today} is not the last day of the month. Skipping monthly job.")
  #      sys.exit(0)
    start = today - timedelta(days=LOOKBACK_DAYS)
    end = today
    out = {
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tri": {},
        "errors": [],
    }
    for name in SECTORAL_INDICES:
        try:
            rows = fetch_tri(name, start, end)
            out["tri"][name] = rows
            if rows:
                print(f"[OK  ] {name}: {len(rows)} rows")
                print(f"       sample row: {rows[0]}")
            else:
                msg = f"{name}: API returned 0 rows -- check name against live dropdown"
                print(f"[FAIL] {msg}", file=sys.stderr)
                out["errors"].append(msg)
            time.sleep(0.4)
        except Exception as e:
            msg = f"TRI fetch failed for {name}: {e}"
            print(f"[ERR ] {msg}", file=sys.stderr)
            out["errors"].append(msg)
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"sectoral-{today.isoformat()}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote sectoral snapshot -> {out_path}")
    total_ok = sum(1 for v in out["tri"].values() if v)
    print(f"Summary: {total_ok}/{len(SECTORAL_INDICES)} indices returned data")
    if total_ok == 0:
        print("FATAL: no sectoral data fetched", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
