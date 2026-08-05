# Google Drive Image Deduplicator

Python CLI that scans images on Google Drive, finds exact and visually similar duplicates, recommends which copies to remove, and trashes them only after you confirm.

## Features

- Lists images from your Google Drive (optionally limited to a folder)
- Detects **exact** duplicates via Drive `md5Checksum` / content hash
- Detects **visually similar** duplicates via perceptual hashing (`pHash`)
- Recommends a keeper per group (higher resolution → larger size → cleaner name → older file)
- Writes a JSON report you can review
- Moves recommended files to **Drive Trash** only after explicit confirmation

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create Google Cloud OAuth credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Google Drive API**
4. Configure the **OAuth consent screen** (External is fine for personal use; add your Google account as a test user while in Testing)
5. Create credentials → **OAuth client ID** → Application type **Desktop app**
6. Download the JSON file and save it as:

```text
credentials/credentials.json
```

### 3. Authenticate (first run)

```bash
python -m drive_dedup scan
```

A browser window opens for Google sign-in. After consent, a token is cached at `credentials/token.json`.

## Usage

### Scan and review recommendations

```bash
python -m drive_dedup scan
```

Optional flags:

| Flag | Description |
|------|-------------|
| `--folder-id ID` | Limit scan to one Drive folder |
| `--exact-only` | Skip perceptual (visual) matching |
| `--threshold 5` | Max pHash distance for similar images (default 5) |
| `--skip-download` | Use Drive md5 only; no downloads |
| `--report PATH` | JSON report path (default `reports/duplicates.json`) |

### Scan and remove after confirmation

```bash
python -m drive_dedup scan --remove
```

You will be prompted before anything is trashed. To skip the prompt (automation):

```bash
python -m drive_dedup scan --remove --yes
```

### Remove from a previous report

Edit `reports/duplicates.json` if you want to drop some recommendations, then:

```bash
python -m drive_dedup remove-from-report
```

Or only specific groups:

```bash
python -m drive_dedup remove-from-report --group 1 --group 3
```

## How keeper selection works

For each duplicate group the app keeps one file and recommends the rest for removal:

1. Highest resolution (width × height)
2. Largest file size
3. Cleaner filename (avoids names like `Copy of …` or `photo (1).jpg`)
4. Older `createdTime` (likely the original)
5. Stable file id as a final tie-breaker

Deleted items go to Google Drive Trash so they can be restored if needed.

## Project layout

```text
drive_dedup/
  auth.py           # OAuth2 + Drive service
  drive_client.py   # List / download / trash
  duplicates.py     # Matching + recommendations
  cli.py            # Click + Rich CLI
  models.py         # Data models
tests/
  test_duplicates.py
credentials/        # Your OAuth secrets (gitignored)
reports/            # Scan reports (gitignored)
```

## Tests

```bash
pytest -q
```

## Security notes

- Never commit `credentials/credentials.json` or `credentials/token.json`
- The app requests the Drive scope so it can trash files you confirm
- Prefer reviewing the report before using `--remove --yes`
