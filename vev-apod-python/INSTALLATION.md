# Installation

## Prerequisites

- Python 3.11 or later
- LibreOffice (required for the Excel-to-PDF conversion step)
- Git (optional)

### Install LibreOffice

**Windows**: Download from https://www.libreoffice.org/download/ and install.

**Ubuntu / Debian**:
```bash
sudo apt-get install libreoffice
```

**macOS**:
```bash
brew install --cask libreoffice
```

---

## Step 1 — Get the Code

```bash
git clone <repository-url>
cd vev-apod-app-python/vev-apod-python
```

Or copy the `vev-apod-python/` folder to your server.

---

## Step 2 — Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

```bash
# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

---

## Step 3 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, SQLAlchemy, Flask-Login, PyPDF2, openpyxl, Gunicorn, and Werkzeug.

---

## Step 4 — Configure Environment Variables (optional)

Copy the example file and edit it:

```bash
cp .env.example .env
```

Edit `.env`:

```
SECRET_KEY=your-long-random-secret-key-here
ORG_NAME=Διεύθυνση Π.Ε. Ηρακλείου
```

For local development the defaults work fine. For production, always set a strong `SECRET_KEY`.

The application reads configuration from environment variables. To load them from `.env` before starting, use:

```bash
# Linux / macOS
export $(cat .env | xargs)

# Windows (PowerShell)
Get-Content .env | ForEach-Object { $k,$v = $_ -split '=',2; [System.Environment]::SetEnvironmentVariable($k,$v) }
```

---

## Step 5 — Initialise the Database

```bash
python init_db.py
```

This creates:
- `instance/app.db` — SQLite database with all tables
- `data/` — directory for uploaded files
- Default admin user: **admin / d1pe1712**

---

## Directory Permissions

Ensure the application can write to:
- `instance/` — SQLite database file
- `data/` — uploaded Excel files, generated PDFs and CSV index files

On Linux:
```bash
mkdir -p instance data
chmod 755 instance data
```

---

## Verify Installation

```bash
python run.py
```

Open `http://localhost:5000`. The login page should appear.
