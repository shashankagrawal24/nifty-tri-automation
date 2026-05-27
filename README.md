# nifty-tri-automation

Daily automation that pulls Historical Index values + TRI from niftyindices.com and writes them into the **Indices** tab of the Novelty Wealth indices tracking sheet.

Runs Mon–Fri at 9:00 PM IST via GitHub Actions.

## Architecture

Two-stage, same pattern as `cams-wbr33-automation`:

```
   ┌────────────────────┐       ┌──────────────────────┐
   │ Stage 1: fetch     │       │ Stage 2: write       │
   │ niftyindices.com   │  →    │ → Google Sheets API  │
   │ → data/YYYY-MM-DD  │       │   (gspread)          │
   └────────────────────┘       └──────────────────────┘
```

If Stage 1 fails (endpoint change, network blip), Stage 2 doesn't run and the sheet stays clean. Snapshot is committed to `data/` so failures are debuggable historically.

## Indices covered

| Sheet column | Index                              | Type       |
| ------------ | ---------------------------------- | ---------- |
| B            | NIFTY 50                           | TRI        |
| C            | NIFTY 100                          | TRI        |
| D            | NIFTY 500                          | TRI        |
| E            | NIFTY MIDCAP 150                   | TRI        |
| F            | NIFTY SMALLCAP 250                 | TRI        |
| Z            | NIFTY500 MULTICAP 50:25:25         | TRI        |
| AA           | NIFTY LARGEMIDCAP 250              | TRI        |
| AB           | NIFTY REITS & INVITS               | TRI        |
| AG           | NIFTY MIDSMALLCAP 400              | Price (close) |

## One-time setup

### 1. Create a service account

1. Go to [Google Cloud Console → IAM → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts).
2. Create a new SA (e.g. `nifty-tri-bot`). Skip role assignment.
3. On the SA, **Keys → Add key → JSON**. Download the JSON file.
4. Open the [target sheet](https://docs.google.com/spreadsheets/d/1Cf06j1pQKrHfjv48Rkh2lZpElZDlqE7hD3M3NZP9iQE) and share it with the SA's email (`nifty-tri-bot@<project>.iam.gserviceaccount.com`) as **Editor**.

### 2. Add the GitHub secret

Base64-encode the JSON key, then add it as a repo secret named `GCP_SA_KEY_B64`:

```bash
# Mac
base64 -i service_account.json | pbcopy

# Windows PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service_account.json")) | Set-Clipboard
```

Then: GitHub → Settings → Secrets and variables → Actions → New repository secret.

### 3. Push and enable

```bash
git init
git add .
git commit -m "init"
git remote add origin git@github.com:shashankagrawal24/nifty-tri-automation.git
git push -u origin main
```

The cron starts running automatically. To test before waiting for 9 PM, trigger manually: **Actions → Nifty TRI Daily Update → Run workflow**.

## Local testing

```bash
# Place service_account.json in credentials/
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python src/fetch_niftyindices.py    # writes data/<today>.json
python src/write_to_sheets.py        # writes to sheet
```

## Forward-fill behaviour

niftyindices only returns rows for trading days. The script writes the **last 3 calendar days** (today, today-1, today-2). For any of those days that isn't a trading day (weekend/holiday), it uses the most recent prior trading day's value for every column. This matches the manual prompt's "repeat the previous trading day's value" rule.

## Failure modes to watch for

1. **Endpoint changes on niftyindices.com.** If a stage prints `0 rows` for every index, open the live page with DevTools → Network, replay a request, and update the `cinfo` payload structure in `fetch_niftyindices.py`.
2. **Index name changes.** Same fix — copy the exact `indexName` string from a live request.
3. **Sheet structure changes.** If someone inserts/deletes rows above row 6, the `BASE_ROW = 6` constant in `write_to_sheets.py` needs updating.
4. **Service account loses access.** Re-share the sheet with the SA email.

## Cost

GitHub Actions free tier covers this easily — ~30 seconds per run × ~22 runs/month = 11 minutes. Well under the 2,000-minute limit.
