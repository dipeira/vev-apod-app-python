# Code Structure

## Top-level Files

### `run.py`
Entry point for local development. Calls `create_app()` from the `app` package and starts Flask's built-in server on `0.0.0.0:5000` with `debug=False`. In Docker, Gunicorn imports the `app` object from this module directly (`run:app`).

```
run.py
  └── create_app() → Flask app object
        └── Gunicorn / python run.py
```

### `init_db.py`
Run once on startup (called by `entrypoint.sh` in Docker, or manually in development). Uses SQLAlchemy's `db.create_all()` to create all tables if they do not exist, then inserts the default admin user (`admin / d1pe1712`) if no admin exists. Also ensures the `data/` directory is present.

### `requirements.txt`
Python package pins:
- `Flask==3.0.3` — web framework
- `Flask-SQLAlchemy==3.1.1` — ORM integration
- `Flask-Login==0.6.3` — session-based authentication
- `Werkzeug==3.0.3` — password hashing, request utilities
- `SQLAlchemy==2.0.30` — database engine
- `PyPDF2==3.0.1` — PDF reading and writing
- `openpyxl==3.1.2` — XLSX cell reading (used in step 3b of the pipeline)
- `gunicorn==22.0.0` — production WSGI server

---

## `app/` Package

### `app/__init__.py` — Application Factory
Creates the Flask app, loads configuration, initialises the SQLAlchemy `db` and `Flask-Login` `login_manager` extensions, registers the three blueprints, and ensures the data folder exists.

Exports two module-level singletons used by other modules: `db` and `login_manager`.

### `app/config.py` — Configuration
Single `Config` class. All settings are read from environment variables with fallbacks:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `change-this-secret-key-in-production` | Flask session signing |
| `DATABASE_URL` | `sqlite:///.../instance/app.db` | SQLAlchemy connection string |
| `DATA_FOLDER` | `<project_root>/data` | Root for uploaded files |
| `ORG_NAME` | `Διεύθυνση Π.Ε. Ηρακλείου` | Organisation name |
| `MAX_CONTENT_LENGTH` | 200 MB | Maximum upload size |
| `ALLOWED_EXCEL_EXTENSIONS` | `{xls, xlsx}` | Accepted upload types |

### `app/models.py` — Database Models
Defines two SQLAlchemy models:

**`User`** — application users (admins and non-admins).
- `set_password(password)` — hashes and stores a password using Werkzeug.
- `check_password(password)` — verifies a plaintext password against the stored hash.

**`YearData`** — one record per fiscal year.
- `year_dir(data_folder)` — returns `data/{year}/`
- `pdf_path(data_folder)` — returns path to the cleaned PDF
- `csv_path(data_folder)` — returns path to the CSV index

Also registers the `@login_manager.user_loader` callback so Flask-Login can retrieve `User` objects by ID from the session.

---

## Blueprints

### `app/auth/` — Authentication
**`routes.py`**:
- `GET /auth/login` — renders `auth/login.html`
- `POST /auth/login` — queries `User` by username, calls `check_password()`, calls `login_user()` on success, redirects to the page the user was trying to access
- `GET /auth/logout` — calls `logout_user()`, redirects to login

### `app/admin/` — Administration
**`routes.py`** — the largest route file. Key components:

- `admin_required` decorator — wraps any route to redirect non-admin users to the employee page.
- `no_cache()` helper — adds `Cache-Control: no-store` headers; applied to the dashboard so browser back-button always shows fresh status.
- `_allowed_excel()` — checks file extension against `ALLOWED_EXCEL_EXTENSIONS`.
- `dashboard()` — fetches all `YearData` records ordered by year descending; renders `admin/dashboard.html`.
- `upload()` — saves the uploaded file to `data/{year}/excel/{year}.ext`, creates or updates the `YearData` record.
- `process()` — calls `claim_processing_slot()`; if the slot is free, sets status to `processing` and calls `run_pipeline()`.
- `status()` — JSON endpoint polled every second by the dashboard JS; returns `{status, message, progress, detail, employee_count, any_processing}`.
- `abort()` — sets the abort flag via `request_abort()`.
- `delete_year()` — if processing, calls `wait_for_abort()` first; then removes the year directory with `shutil.rmtree` and deletes the DB record.
- User management routes — `users()`, `create_user()`, `delete_user()`, `change_password()`.

### `app/employee/` — Employee Self-Service
**`routes.py`**:
- `_search_csv(csv_path, afm, amka)` — opens the CSV index, strips leading zeros from AFM and AMKA for comparison, returns `(page, num_pages)` tuple or `None`. Supports both 3-column (XLS) and 4-column (XLSX) CSV formats.
- `_extract_page(pdf_path, page_number, num_pages)` — opens the clean PDF, copies the specified page range into a `BytesIO` buffer using `PyPDF2.PdfWriter`, returns the buffer.
- `index()` — on `GET`: renders the search form with available years. On `POST`: searches the CSV, extracts the PDF pages, returns the file as an attachment.

---

## `app/processing/utils.py` — Processing Pipeline

The most complex module. Contains:

### State Management
- `_state` dict — `{yd_id: {progress, detail, abort}}` — in-memory, thread-safe via `_state_lock`
- `_threads` dict — `{yd_id: Thread}` — tracks active threads for join support
- `_processing_lock` — `threading.Lock`; claimed non-blocking in `claim_processing_slot()`
- `get_state()`, `request_abort()`, `wait_for_abort()`, `is_any_processing()` — public API used by admin routes

### Helper Functions
- `_kill_proc(proc)` — cross-platform subprocess termination: `os.killpg(SIGTERM)` on Linux (kills whole process group), `proc.terminate()` on Windows
- `_find_libreoffice()` — searches a list of known paths and uses `shutil.which()` to locate the LibreOffice executable
- `_xlsx_set_landscape(src, dst)` — copies an XLSX (which is a ZIP) file, injecting `<pageSetup orientation="landscape"/>` into every worksheet XML before the `</worksheet>` tag

### Pipeline Functions
- `excel_to_pdf(excel_path, pdf_path, yd_id)` — runs LibreOffice headless; polls every 0.3s; aborts if flag set; 600s timeout; renames LibreOffice's output to the expected path
- `clean_pdf(input_path, output_path, yd_id)` — removes pages with 3 or fewer words
- `create_index(pdf_path, csv_path, yd_id)` — scans PDF pages; writes `afm;amka;page` CSV
- `create_index_from_xlsx(xlsx_path, clean_pdf_path, csv_path, yd_id)` — reads AFM/AMKA from Excel cells directly; detects pages-per-cert by comparing PDF page count to record count; writes `afm;amka;page;num_pages` CSV; falls back to `create_index()` on mismatch
- `run_pipeline(year_data_id, flask_app)` — spawns the background thread; the thread runs all steps inside a Flask app context; `finally` always releases the processing slot

---

## Templates

### `base.html`
Bootstrap 5.3 layout. Dark-blue brand theme (`#1a3a5c`). Navbar shows different links for authenticated vs. anonymous users, and admin-only links for admin users. Flash messages displayed below navbar. Footer with organisation copyright.

### `auth/login.html`
Minimal card with username and password fields. No JS.

### `admin/dashboard.html`
Most complex template. Contains:
- Upload form with JS that auto-fills the year field by extracting a 4-digit year from the filename
- Year table: one row per `YearData` with status badge, progress bar, and real-time detail text
- JS polling loop (`poll()`) that calls `/admin/status/<id>` every second while a job is processing
- `setAllProcessButtons(disabled)` — enables/disables all Process buttons globally when any job is running
- Auto-starts polling on page load if any row already has `processing` status

### `admin/users.html`
User list table with create form and Bootstrap modal for changing passwords. The modal's form `action` is dynamically set via JavaScript using `data-user-id` attributes.

### `employee/index.html`
Simple search form: year dropdown (only `done` years shown), AFM text input, AMKA text input. Privacy notice: "Data is used only for search and is not stored."
