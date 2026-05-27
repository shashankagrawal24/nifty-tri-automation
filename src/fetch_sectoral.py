"""
Stage 1 (monthly): Fetch TRI for 13 sectoral indices from niftyindices.com.

Self-filters to last day of the month. The workflow cron triggers on days
28-31, but this script only proceeds if tomorrow is the 1st of next month
(i.e. today is the actual last day of THIS month). Otherwise it exits 0.

Writes a snapshot to data/sectoral-<YYYY-MM-DD>.json.
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"

# 13 sectoral indices. If any returns 0 rows on first run, inspect a live
# request on niftyindices.com via DevTools → Network and copy the exact
# indexName string here.
SECTORAL_INDICES = [
    "NIFTY AUTO",
    "NIFTY BANK",
    "NIFTY CHEMICALS",
    "NIFTY CONSUMER DURABLES",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY FMCG",
    "NIFTY HEALTHCARE INDEX",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY OIL & GAS",
    "NIFTY PHARMA",
    "NIFTY REALTY",
]

# Fetch last 32 calendar days so we cover a full month with overlap buffer.
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
    resp.raise_for_status()
    outer = resp.json()
    return json.loads(outer.get("d", "[]"))


def main() -> None:
    today = date.today()

    # Self-filter: only proceed on the last day of the month
    if not is_last_day_of_month(today):
        print(f"{today} is not the last day of the month. Skipping monthly job.")
        sys.exit(0)

    start = today - timedelta(days=LOOKBACK_DAYS)
    end = today

    out: dict = {
        "fetched_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tri": {},
        "errors": [],
    }

    for name in SECTORAL_INDICES:
        try:
            rows = fetch_tri(name, start, end)
            out["tri"][name] = rows
            print(f"[TRI ] {name}: {len(rows)} rows")
            time.sleep(0.4)
        except Exception as e:
            msg = f"TRI fetch failed for {name}: {e}"
            print(msg, file=sys.stderr)
            out["errors"].append(msg)

    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"sectoral-{today.isoformat()}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote sectoral snapshot → {out_path}")

    total_ok = sum(1 for v in out["tri"].values() if v)
    if total_ok == 0:
        print("FATAL: no sectoral data fetched", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
