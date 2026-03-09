# Troubleshooting

---

## Server / Startup Issues

### Port 5000 already in use

**Symptom**: `OSError: [Errno 98] Address already in use` or `Only one usage of each socket address is normally permitted`

**Cause**: A previous Python/Flask process is still running.

**Fix (Windows)**:
```bash
taskkill /F /IM python.exe /T
python run.py
```

**Fix (Linux)**:
```bash
pkill -f "python run.py"
# or find and kill by port
fuser -k 5000/tcp
python run.py
```

---

### Template changes not showing

**Symptom**: You edited an HTML file but the browser still shows the old version.

**Cause**: `debug=False` enables Jinja2 template caching. Templates are not reloaded without a restart.

**Fix**: Restart the server, then hard-refresh the browser (`Ctrl+Shift+R`).

---

### `ModuleNotFoundError` on startup

**Symptom**: `ModuleNotFoundError: No module named 'flask'` or similar.

**Cause**: Virtual environment is not activated, or `pip install -r requirements.txt` was not run.

**Fix**:
```bash
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
```

---

## Processing Pipeline Issues

### LibreOffice not found

**Symptom**: Processing fails immediately with message `LibreOffice δεν βρέθηκε`.

**Cause**: LibreOffice is not installed or not on the system PATH.

**Fix**:
- Install LibreOffice from https://www.libreoffice.org/download/
- Verify: `libreoffice --version` (Linux/macOS) or check `C:\Program Files\LibreOffice\program\soffice.exe` (Windows)

In Docker, LibreOffice is installed automatically via the Dockerfile.

---

### LibreOffice timeout

**Symptom**: Processing fails with `LibreOffice timeout (>10 λεπτά)`.

**Cause**: The Excel file is very large or the system is under heavy load.

**Fix**: Try processing again. If it consistently times out, split the Excel file into smaller chunks.

---

### Employee count is 0 or much lower than expected

**Symptom**: Processing completes as `done` but the employee count is 0 or very low.

**Cause (XLS)**: PyPDF2 could not extract text from the generated PDF — likely because LibreOffice rendered some pages as bitmaps. This can happen if the Excel sheet has complex formatting.

**Cause (XLSX)**: `create_index_from_xlsx` could not find AFM (9-digit) and AMKA (11-digit) values in the same row. Check that the Excel file has these columns and that the values are stored as numbers, not text with extra characters.

**Fix**: Open the CSV file at `data/{year}/csv/{year}.csv` and inspect its contents. Each row should have a valid AFM and AMKA.

---

### PDF page count mismatch (XLSX fallback)

**Symptom**: Logs show `create_index_from_xlsx: PDF has X pages, records=Y (not 1× or 2×). Falling back to PDF scan.`

**Cause**: The number of PDF pages does not equal the number of Excel records or twice the number of records. This can happen if the Excel sheet has extra blank sheets, header rows counted as records, or the PDF has unexpected extra pages.

**Fix**: Check the Excel file for extra sheets or header rows that might be picked up as employee records. Also verify the PDF was generated correctly (check page count matches employee count).

---

### Processing stuck / never completes

**Symptom**: The progress bar stays frozen and the status never changes from `processing`.

**Cause**: The background thread may have crashed silently, or LibreOffice is hung.

**Fix**:
1. Click the Abort button on the dashboard, or restart the server
2. Check server logs for errors
3. The processing slot is released when the thread exits (including on crash via the `finally` block)

---

## Upload Issues

### File upload fails (413 error)

**Symptom**: Browser shows a `413 Request Entity Too Large` error.

**Cause**: The file exceeds the 200 MB limit.

**Fix**: The limit is set in `app/config.py` (`MAX_CONTENT_LENGTH = 200 * 1024 * 1024`). In Docker, nginx also has `client_max_body_size 200M` in `nginx.conf`. If you need a larger limit, update both.

---

### "Επιτρέπονται μόνο αρχεία .xls και .xlsx"

**Symptom**: Upload rejected with this message.

**Cause**: The uploaded file has an extension other than `.xls` or `.xlsx`.

**Fix**: Ensure the file is a valid Excel file with the correct extension. The allowed extensions are configured in `app/config.py` (`ALLOWED_EXCEL_EXTENSIONS`).

---

## Employee Search Issues

### "Δεν βρέθηκαν στοιχεία" — no certificate found

**Symptom**: Employee enters AFM and AMKA but gets "not found".

**Possible causes**:
1. Wrong AFM or AMKA entered
2. The year selected does not have this employee's data
3. The CSV index was built incorrectly (check employee count on the dashboard)
4. The employee's AFM/AMKA contains leading zeros — the system strips them, so `012345678` and `12345678` are treated the same

**Fix**: Check the CSV file directly (`data/{year}/csv/{year}.csv`) to verify the employee's row exists.

---

## Docker Issues

### Cannot connect to port 8085

**Symptom**: Browser times out connecting to `http://<server>:8085`.

**Possible causes**:
- Containers are not running (`docker compose ps` to check)
- Firewall blocking port 8085

**Fix**:
```bash
docker compose ps
docker compose up -d
# Check firewall (Ubuntu)
sudo ufw allow 8085/tcp
```

---

### nginx 502 Bad Gateway

**Symptom**: nginx returns 502 when accessing the application.

**Cause**: The `web` container is not running or has crashed.

**Fix**:
```bash
docker compose logs web
docker compose restart web
```

---

### Changes not reflected after rebuild

**Symptom**: You ran `docker compose up -d --build` but old code is still running.

**Fix**:
```bash
docker compose down
docker compose up -d --build
```

Using `down` first ensures containers are fully stopped and recreated.

---

### Data lost after `docker compose down -v`

**Cause**: The `-v` flag removes named volumes (`app_data` and `app_instance`), which contain all uploaded files and the database.

**Fix**: Do not use `-v` unless you intentionally want to wipe all data. Use `docker compose down` (without `-v`) to stop containers while preserving data.

---

## Database Issues

### `OperationalError: no such table`

**Symptom**: Server starts but crashes with a SQLAlchemy table error.

**Cause**: `init_db.py` was not run, or the database file is missing.

**Fix**:
```bash
python init_db.py
```

In Docker, `init_db.py` is run automatically by `entrypoint.sh` on every container start.

---

### Cannot log in with default credentials

**Symptom**: `admin / d1pe1712` does not work.

**Cause**: The admin password was changed, or the database was deleted and re-created.

**Fix**: Run `python init_db.py` — if no admin user exists, it creates one with the default password.
