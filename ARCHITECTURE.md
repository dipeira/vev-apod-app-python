# Architecture

## Overview

The application follows a standard Flask Blueprint architecture. Three blueprints handle distinct concerns: authentication, admin management, and employee self-service. A fourth module (`processing/utils.py`) implements the file-processing pipeline that runs in a background thread.

```
Browser
  |
  | HTTP
  v
nginx  (Docker only — host port 8085 → container port 80)
  |
  v
Gunicorn / Flask dev server  (port 5000)
  |
  +-- auth blueprint      /auth/*
  +-- admin blueprint     /admin/*
  +-- employee blueprint  /
  |
  +-- SQLite DB (instance/app.db)
  +-- File storage (data/{year}/excel|pdf|csv)
  +-- Background thread (processing pipeline)
```

---

## Blueprints

### auth (`app/auth/`)
- `GET  /auth/login`  — renders login form
- `POST /auth/login`  — validates credentials, creates session
- `GET  /auth/logout` — clears session, redirects to login

### admin (`app/admin/`)
- `GET  /admin/`                          — dashboard (year list, upload form)
- `POST /admin/upload`                    — saves uploaded Excel, creates/updates `YearData` record
- `POST /admin/process/<id>`              — claims processing slot, spawns background thread
- `GET  /admin/status/<id>`              — JSON polling endpoint (progress, message, any_processing)
- `POST /admin/abort/<id>`               — sets abort flag on running job
- `POST /admin/delete/<id>`              — aborts if running, deletes files + DB record
- `GET  /admin/users`                    — user list
- `POST /admin/users/create`             — create new user
- `POST /admin/users/<id>/delete`        — delete user
- `POST /admin/users/<id>/password`      — change password

### employee (`app/employee/`)
- `GET  /`  — renders search form (shows available years with status='done')
- `POST /`  — looks up AFM + AMKA in CSV index, extracts matching PDF pages, returns as download

---

## Processing Pipeline

The pipeline runs in a `threading.Thread` (daemon). Steps:

```
Step 1: excel_to_pdf()
  - For .xlsx/.xlsm: inject <pageSetup orientation="landscape"/> into each
    sheet via ZIP/XML manipulation (preserves exact formatting)
  - Run LibreOffice headless: --convert-to pdf --outdir <pdf_dir>
  - Poll every 0.3s; abort if flag set; timeout after 600s
  - Output: data/{year}/pdf/{year}_raw.pdf

Step 2: clean_pdf()
  - Open raw PDF with PyPDF2
  - For each page: extract text, count words
  - Keep pages with more than 3 words (discard blank/header pages)
  - Output: data/{year}/pdf/{year}_clean.pdf

Step 3a: create_index()  [for .xls]
  - Scan each page of the clean PDF
  - Token scan: keep overwriting afm on every 9-digit match;
    record first 11-digit match as amka
  - Write CSV: afm;amka;page
  - Output: data/{year}/csv/{year}.csv

Step 3b: create_index_from_xlsx()  [for .xlsx/.xlsm]
  - Read AFM (9-digit) and AMKA (11-digit) directly from Excel
    cells using openpyxl (reliable; avoids PDF text extraction issues)
  - Count PDF pages; detect pages-per-certificate (1 or 2)
  - Write CSV: afm;amka;page;num_pages
  - Falls back to create_index() if page count does not match 1× or 2× records
  - Output: data/{year}/csv/{year}.csv
```

---

## Concurrency Model

```
HTTP request (admin.process)
  |
  +-- claim_processing_slot()  [threading.Lock, non-blocking acquire]
  |     returns False → 409 response (another job running)
  |     returns True  → lock held
  |
  +-- spawn Thread(_run)
        |
        +-- pipeline steps 1-3
        |
        +-- finally: release_processing_slot()
```

The `_state` dict stores `{progress, detail, abort}` per `year_data_id` and is read by the `/admin/status/<id>` polling endpoint.

The `_threads` dict stores the active `Thread` object so `wait_for_abort()` can join it before deleting files.

---

## Data Flow — Employee Certificate Download

```
POST /  (afm=..., amka=..., year=...)
  |
  +-- Strip leading zeros from afm, amka
  |
  +-- Query DB: YearData WHERE year=? AND status='done'
  |
  +-- Open data/{year}/csv/{year}.csv
  |     scan rows: afm;amka;page[;num_pages]
  |     match found → (page_number, num_pages)
  |
  +-- Open data/{year}/pdf/{year}_clean.pdf (PyPDF2)
  |     extract pages [page_number-1 .. page_number-1+num_pages)
  |     write to BytesIO buffer
  |
  +-- send_file(buffer, mimetype='application/pdf',
                download_name='vevaiosi_{year}.pdf')
```

---

## Database Schema

### `user`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| username | String(80) | unique |
| password_hash | String(256) | Werkzeug PBKDF2 |
| is_admin | Boolean | |
| created_at | DateTime | utcnow default |

### `year_data`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| year | Integer | unique |
| excel_filename | String(256) | e.g. `2024.xlsx` |
| pdf_filename | String(256) | e.g. `2024_clean.pdf` (set after processing) |
| csv_filename | String(256) | e.g. `2024.csv` (set after processing) |
| processing_status | String(20) | `idle` / `processing` / `done` / `error` |
| processing_message | Text | last step message |
| employee_count | Integer | matched AFM+AMKA records |
| uploaded_at | DateTime | |
| processed_at | DateTime | |
