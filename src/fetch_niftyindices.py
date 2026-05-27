"""
Stage 1: Fetch historical index values and TRI from niftyindices.com.

Hits two endpoints on niftyindices.com:
  - getHistoricaldatatabletoString (price/close data)
  - getTotalReturnIndexString (TRI data)

Writes a single dated JSON snapshot to data/<YYYY-MM-DD>.json so Stage 2
can read it independently. If this stage fails, the failure is isolated
(no half-written sheet).
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# Endpoints
PRICE_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"

# Indices to fetch
# Note: niftyindices.com uses specific naming. If a request returns empty,
# inspect the request on the live page (DevTools → Network) and copy the
# exact "indexName" string into this dict.
TRI_INDICES = [
    "NIFTY 50",
    "NIFTY 100",
    "NIFTY 500",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250",
    "NIFTY LARGEMIDCAP 250",
    "NIFTY500 MULTICAP 50:25:25",   # No space between NIFTY and 500 on the API side
    "NIFTY REITS & INVITS",
]

PRICE_INDICES = [
    "NIFTY MIDSMALLCAP 400",
]

# Lookback window: fetch the last N days so we cover long weekends.
LOOKBACK_DAYS = 5

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
    """niftyindices.com expects dates as 'DD-MMM-YYYY' (e.g. 27-May-2026)."""
    return d.strftime("%d-%b-%Y")


def _post(url: str, index_name: str, start: date, end: date) -> list[dict]:
    """POST to a niftyindices endpoint and unwrap the doubly-encoded JSON."""
    payload = {
        "cinfo": json.dumps({
            "name": index_name,
            "startDate": fmt_date(start),
            "endDate": fmt_date(end),
            "indexName": index_name,
        })
    }
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    outer = resp.json()
    # The response wraps the actual payload in a "d" field as a JSON string.
    inner_raw = outer.get("d", "[]")
    return json.loads(inner_raw)


def fetch_tri(index_name: str, start: date, end: date) -> list[dict]:
    rows = _post(TRI_URL, index_name, start, end)
    return rows


def fetch_price(index_name: str, start: date, end: date) -> list[dict]:
    rows = _post(PRICE_URL, index_name, start, end)
    return rows


def main() -> None:
    today = date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    end = today

    out: dict = {
        "fetched_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tri": {},
        "price": {},
        "errors": [],
    }

    for name in TRI_INDICES:
        try:
            rows = fetch_tri(name, start, end)
            out["tri"][name] = rows
            print(f"[TRI ] {name}: {len(rows)} rows")
            time.sleep(0.4)  # Be polite — small gap between calls
        except Exception as e:
            msg = f"TRI fetch failed for {name}: {e}"
            print(msg, file=sys.stderr)
            out["errors"].append(msg)

    for name in PRICE_INDICES:
        try:
            rows = fetch_price(name, start, end)
            out["price"][name] = rows
            print(f"[PRC ] {name}: {len(rows)} rows")
            time.sleep(0.4)
        except Exception as e:
            msg = f"Price fetch failed for {name}: {e}"
            print(msg, file=sys.stderr)
            out["errors"].append(msg)

    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"{today.isoformat()}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote snapshot → {out_path}")

    # Fail the job if every index failed — likely an endpoint change.
    total_ok = sum(1 for v in out["tri"].values() if v) + sum(1 for v in out["price"].values() if v)
    if total_ok == 0:
        print("FATAL: no data fetched for any index", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
