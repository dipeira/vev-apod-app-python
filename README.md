# Βεβαιώσεις Αποδοχών — Salary Certificate Portal

A Flask web application that allows employees to download their salary certificates (Βεβαιώσεις Αποδοχών) as PDF files by entering their AFM (tax number) and AMKA (social security number). Administrators upload and process annual Excel payroll files to generate the certificate archive.

---

## Key Features

- **Employee self-service**: employees enter AFM + AMKA to instantly download their personal salary certificate as a PDF
- **Multi-year support**: separate data set per fiscal year; employees select the year before searching
- **Excel ingestion**: administrators upload `.xls` or `.xlsx` payroll files (up to 200 MB)
- **Automated processing pipeline**: LibreOffice converts Excel to PDF, blank pages are stripped, and a searchable CSV index is built — all in a background thread with real-time progress displayed on the dashboard
- **Process locking**: only one processing job can run at a time; all Process buttons are disabled while a job is in progress
- **Safe delete**: deleting a year during processing automatically stops the running job before removing files
- **User management**: administrators can create, delete, and change passwords for other users
- **Docker-ready**: ships with `Dockerfile`, `docker-compose.yml`, and an nginx reverse proxy configuration

---

## Technologies

| Layer | Technology |
|---|---|
| Web framework | Flask 3.0 |
| ORM | Flask-SQLAlchemy 3.1 + SQLAlchemy 2.0 |
| Authentication | Flask-Login 0.6 |
| Password hashing | Werkzeug |
| PDF processing | PyPDF2 3.0 |
| Excel reading (XLSX) | openpyxl 3.1 |
| PDF generation | LibreOffice headless |
| Database | SQLite (file-based, no server required) |
| Frontend | Bootstrap 5.3 + Bootstrap Icons |
| Production server | Gunicorn 22 |
| Reverse proxy | nginx (Docker deployment) |
| Container runtime | Docker + Docker Compose |

---

## Folder Structure

```
vev-apod-python/
├── run.py                  # Application entry point
├── init_db.py              # Database initialisation + default admin creation
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build instructions
├── docker-compose.yml      # Multi-service Docker deployment
├── nginx.conf              # nginx reverse-proxy configuration
├── entrypoint.sh           # Docker container startup script
├── .env.example            # Environment variable template
│
├── app/
│   ├── __init__.py         # Flask application factory
│   ├── config.py           # Configuration class (reads env vars)
│   ├── models.py           # SQLAlchemy models: User, YearData
│   │
│   ├── auth/               # Authentication blueprint (/auth/login, /auth/logout)
│   ├── admin/              # Admin blueprint (/admin/*)
│   ├── employee/           # Employee blueprint (/)
│   ├── processing/         # Processing pipeline (utils.py)
│   │
│   └── templates/
│       ├── base.html
│       ├── auth/login.html
│       ├── admin/dashboard.html
│       ├── admin/users.html
│       └── employee/index.html
│
├── data/                   # Runtime data (created automatically)
│   └── {year}/
│       ├── excel/          # Uploaded Excel file
│       ├── pdf/            # Raw and cleaned PDFs
│       └── csv/            # CSV index (AFM;AMKA;page)
│
└── instance/
    └── app.db              # SQLite database
```

---

## Quick Start

### Local (Python)

```bash
cd vev-apod-python
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
python init_db.py
python run.py
```

Open `http://localhost:5000` in your browser.
Default admin credentials: **admin / d1pe1712**

### Docker

```bash
cd vev-apod-python
cp .env.example .env          # edit SECRET_KEY and ORG_NAME
docker compose up -d --build
```

Open `http://localhost:8085` in your browser.
