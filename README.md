# Drive Dedup

Find duplicate images on Google Drive, **visually compare them in a web app**, recommend what to remove, and trash only after you confirm.

## Web app (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m drive_dedup web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

- **Try a visual demo** — review sample duplicate groups with thumbnails (no Google account needed)
- **Connect Google Drive** — scan your real images, toggle Keep/Remove on each photo, then confirm trash

### Google OAuth setup (for real Drive scans)

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project and enable the **Google Drive API**
3. Configure the **OAuth consent screen** (add yourself as a test user while in Testing)
4. Create an OAuth client:
   - **Web application** is best for the web UI
   - Authorized redirect URI: `http://127.0.0.1:8000/auth/callback`
   - (Desktop clients can also work for the CLI)
5. Download the JSON and save it as `credentials/credentials.json`

Then click **Connect Google Drive** in the web app.

## Features

- Visual side-by-side review of duplicate groups with thumbnails
- Exact duplicates (content hash / Drive `md5Checksum`)
- Visually similar images (perceptual `pHash`)
- Keeper recommendations you can override with a click
- Confirmed removal → Google Drive Trash (restorable)
- CLI available for scripting / headless scans

## CLI

```bash
python -m drive_dedup scan
python -m drive_dedup scan --remove
python -m drive_dedup remove-from-report
python -m drive_dedup web --port 8000
```

| Flag | Description |
|------|-------------|
| `--folder-id ID` | Limit scan to one Drive folder |
| `--exact-only` | Skip perceptual matching |
| `--threshold 5` | Max pHash distance for similar images |
| `--skip-download` | Use Drive md5 only (CLI) |
| `--report PATH` | JSON report path |

## How keeper selection works

1. Highest resolution  
2. Largest file size  
3. Cleaner filename (avoids `Copy of …`)  
4. Older `createdTime`  
5. Stable file id tie-breaker  

## Project layout

```text
drive_dedup/
  web/              # FastAPI UI + static assets
  auth.py           # OAuth (CLI + browser)
  drive_client.py   # List / download / trash / thumbnails
  duplicates.py     # Matching + recommendations
  scan_service.py   # Background scan jobs
  cli.py            # Click CLI
tests/
credentials/        # OAuth secrets (gitignored)
```

## Tests

```bash
pytest -q
```

## Security notes

- Never commit `credentials/credentials.json` or `credentials/token.json`
- Removals require an explicit confirmation step
- Prefer the web review UI before bulk deletion
