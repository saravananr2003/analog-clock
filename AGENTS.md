# AGENTS.md

## Cursor Cloud specific instructions

### Product

Single desktop app: a Tkinter analog clock (`analog_clock.py`). No web server, database, Docker, or package-manager lockfiles.

### System dependency (not in repo)

Tkinter is **not** always bundled with the system Python on Linux. Install once per VM if `import tkinter` fails:

```bash
sudo apt-get install -y python3-tk
```

The Cloud VM display is available as `DISPLAY=:1`; no Xvfb is required when that display is running.

### Run

```bash
python3 analog_clock.py
```

Use a **tmux** session for the GUI process so it stays up across shell disconnects (see repo `README.md` for the same command).

### Lint / test / build

| Task | Status |
|------|--------|
| Lint | Not configured in repo |
| Tests | None |
| Build | N/A (interpreted script) |

Optional sanity check: `python3 -m py_compile analog_clock.py`

### Services

Only one process is required: the Python GUI. No auxiliary services.
