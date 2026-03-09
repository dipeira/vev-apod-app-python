# Running Locally with Python

## Prerequisites

- Python virtual environment created and dependencies installed (see [INSTALLATION.md](INSTALLATION.md))
- Database initialised (`python init_db.py`)
- LibreOffice installed

---

## Start the Server

```bash
cd vev-apod-python

# Activate virtual environment
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux / macOS

# Start
python run.py
```

The server starts on `http://0.0.0.0:5000` (accessible as `http://localhost:5000`).

Output:
```
 * Serving Flask app 'app'
 * Debug mode: off
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
```

---

## Stop the Server

Press `Ctrl+C` in the terminal where the server is running.

If the server is running in the background and you need to stop it forcefully:

```bash
# Windows
taskkill /F /IM python.exe /T

# Linux / macOS
pkill -f "python run.py"
```

---

## Restart the Server

Because `debug=False`, Flask does **not** auto-reload when code changes. You must restart manually after any Python file change.

```bash
# Windows — kill all Python processes, then restart
taskkill //F //IM python.exe //T
python run.py

# Linux / macOS
pkill -f "python run.py"
python run.py
```

> **Note:** Template (HTML) changes also require a server restart because Jinja2 template caching is enabled in non-debug mode.

---

## Running with Gunicorn (Linux / macOS)

For a more production-like local setup:

```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 600 run:app
```

- `--workers 2` — one worker is free while the other runs a long LibreOffice conversion
- `--timeout 600` — keeps connections alive during long processing jobs

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| admin | d1pe1712 | Administrator |

Change the admin password immediately after first login via the Users management page.

---

## File Locations

| Path | Contents |
|---|---|
| `instance/app.db` | SQLite database |
| `data/{year}/excel/` | Uploaded Excel files |
| `data/{year}/pdf/` | Raw and cleaned PDFs |
| `data/{year}/csv/` | CSV index files |
