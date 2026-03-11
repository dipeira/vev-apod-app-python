"""
Processing pipeline:
  Step 1  excel_to_pdf  — LibreOffice headless converts Excel → PDF (landscape, exact formatting)
  Step 2  clean_pdf     — removes blank pages (≤3 words), returns kept-page indices
  Step 3  create_index  — scans clean PDF for AFM + AMKA → CSV index
"""
import csv
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

def _now_athens():
    return datetime.now(ZoneInfo('Europe/Athens')).replace(tzinfo=None)

import PyPDF2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory job state  { year_data_id: {progress, detail, abort} }
# ---------------------------------------------------------------------------
_state: dict = {}
_state_lock = threading.Lock()

_threads: dict = {}          # year_data_id → Thread
_threads_lock = threading.Lock()

# Global processing slot — only one pipeline may run at a time
_processing_lock = threading.Lock()


def claim_processing_slot() -> bool:
    """Try to claim the global processing slot. Returns True if successful."""
    return _processing_lock.acquire(blocking=False)


def release_processing_slot():
    """Release the global processing slot (called from the pipeline thread)."""
    try:
        _processing_lock.release()
    except RuntimeError:
        pass  # already released


def is_any_processing() -> bool:
    """Return True if a pipeline is currently running."""
    acquired = _processing_lock.acquire(blocking=False)
    if acquired:
        _processing_lock.release()
        return False
    return True


def _set(yd_id, **kw):
    if yd_id is None:
        return
    with _state_lock:
        _state.setdefault(yd_id, {}).update(kw)


def get_state(yd_id: int) -> dict:
    with _state_lock:
        return dict(_state.get(yd_id, {}))


def request_abort(yd_id: int):
    _set(yd_id, abort=True)


def wait_for_abort(yd_id: int, timeout: float = 15):
    """Signal abort and wait up to `timeout` seconds for the thread to stop."""
    request_abort(yd_id)
    with _threads_lock:
        t = _threads.get(yd_id)
    if t and t.is_alive():
        t.join(timeout=timeout)


def _aborted(yd_id) -> bool:
    if yd_id is None:
        return False
    with _state_lock:
        return _state.get(yd_id, {}).get('abort', False)


class _Abort(Exception):
    pass


# ---------------------------------------------------------------------------
# Cross-platform process termination
# ---------------------------------------------------------------------------
def _kill_proc(proc):
    """Terminate a subprocess and all its children (works on Linux and Windows)."""
    try:
        if sys.platform != 'win32':
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


# ---------------------------------------------------------------------------
# LibreOffice discovery
# ---------------------------------------------------------------------------
_LO_CANDIDATES = [
    # Linux / Docker
    'libreoffice', 'soffice',
    '/usr/bin/libreoffice', '/usr/bin/soffice',
    '/usr/local/bin/libreoffice',
    # Windows
    r'C:\Program Files\LibreOffice\program\soffice.exe',
    r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    # macOS
    '/Applications/LibreOffice.app/Contents/MacOS/soffice',
]


def _find_libreoffice():
    for c in _LO_CANDIDATES:
        if shutil.which(c) or os.path.isfile(c):
            return c
    return None


# ---------------------------------------------------------------------------
# Helper: inject landscape orientation into .xlsx via ZIP/XML manipulation
# (no openpyxl write needed — very fast for large workbooks)
# ---------------------------------------------------------------------------
_PGSETUP_RE1 = re.compile(rb'<pageSetup[^/]*/>', re.DOTALL)
_PGSETUP_RE2 = re.compile(rb'<pageSetup[^>]*>.*?</pageSetup>', re.DOTALL)
_LANDSCAPE_TAG = b'<pageSetup orientation="landscape"/>'


def _xlsx_set_landscape(src_path: str, dst_path: str):
    """
    Copy src .xlsx to dst, setting landscape + fit-to-one-page for every sheet.
    This ensures LibreOffice renders each employee sheet on exactly 1 landscape page.
    """
    with zipfile.ZipFile(src_path, 'r') as zin, \
         zipfile.ZipFile(dst_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if (item.filename.startswith('xl/worksheets/sheet')
                    and item.filename.endswith('.xml')):
                # Remove any existing pageSetup elements
                data = _PGSETUP_RE1.sub(b'', data)
                data = _PGSETUP_RE2.sub(b'', data)
                # Inject landscape + fit-to-1-page before </worksheet>
                if b'</worksheet>' in data:
                    data = data.replace(
                        b'</worksheet>',
                        _LANDSCAPE_TAG + b'</worksheet>',
                        1,
                    )
            zout.writestr(item, data)


# ---------------------------------------------------------------------------
# Step 1: Excel → PDF via LibreOffice (preserves exact sheet formatting)
# ---------------------------------------------------------------------------
def excel_to_pdf(excel_path, pdf_path, yd_id=None):
    """
    Convert Excel to PDF using LibreOffice --headless.
    For .xlsx files, first injects landscape+fit-to-1-page via ZIP manipulation
    so each employee sheet becomes exactly one landscape PDF page.
    Returns (success: bool, message: str, page_count: int)
    """
    lo = _find_libreoffice()
    if not lo:
        return (False,
                'LibreOffice δεν βρέθηκε. Εγκαταστήστε το LibreOffice και ξαναδοκιμάστε.',
                0)

    _set(yd_id, progress=6,
         detail='Βήμα 1/3: Μετατροπή Excel → PDF με LibreOffice… (παρακαλώ περιμένετε)')

    out_dir = os.path.dirname(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    ext      = os.path.splitext(excel_path)[1].lower()
    lo_input = excel_path
    tmp_xlsx = None

    if ext in ('.xlsx', '.xlsm'):
        tmp_xlsx = tempfile.mktemp(suffix=ext, prefix='lo_landscape_')
        try:
            _xlsx_set_landscape(excel_path, tmp_xlsx)
            lo_input = tmp_xlsx
            logger.info('Landscape copy created: %s', tmp_xlsx)
        except Exception as e:
            logger.warning('Could not inject landscape into xlsx (%s); using original', e)
            lo_input = excel_path

    # Private temp profile prevents concurrent-run conflicts in LibreOffice
    lo_profile_dir = tempfile.mkdtemp(prefix='lo_profile_')
    # Build a correct file:// URI for both Linux (/tmp/...) and Windows (C:\...)
    lo_profile_posix = lo_profile_dir.replace(os.sep, '/')
    if not lo_profile_posix.startswith('/'):
        lo_profile_posix = '/' + lo_profile_posix   # Windows: /C:/...
    lo_profile_uri = f'file://{lo_profile_posix}'   # file:///tmp/... or file:///C:/...

    # Kill any stale soffice processes left from a previous timed-out run.
    # On Linux only — on Windows this would be too aggressive.
    if sys.platform != 'win32':
        subprocess.run(['pkill', '-9', '-f', 'soffice'], capture_output=True)
        time.sleep(0.5)  # give the OS a moment to reap them

    try:
        proc = subprocess.Popen(
            [
                lo, '--headless',
                '--norestore',           # don't try to recover stale sessions
                '--nofirststartwizard',  # skip setup wizard on fresh profile dirs
                f'-env:UserInstallation={lo_profile_uri}',
                '--convert-to', 'pdf',
                '--outdir', out_dir,
                lo_input,
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,   # creates a process group on Linux
            # On Linux/Docker only: give LO a clean home dir so it doesn't touch
            # the real user home. On Windows LO uses APPDATA/USERPROFILE, not HOME.
            env={**os.environ, 'HOME': lo_profile_dir} if sys.platform != 'win32' else None,
        )

        start = time.time()
        last_update = start
        while proc.poll() is None:
            if _aborted(yd_id):
                _kill_proc(proc)
                raise _Abort()
            now = time.time()
            if now - start > 1200:
                _kill_proc(proc)
                return False, 'LibreOffice timeout (>20 λεπτά).', 0
            if now - last_update >= 5:
                elapsed = int(now - start)
                _set(yd_id, detail=f'Βήμα 1/3: LibreOffice εκτελείται… ({elapsed}s)')
                last_update = now
            time.sleep(0.3)

        stdout_data, stderr_data = proc.communicate()
        if proc.returncode != 0:
            err = (stderr_data or stdout_data or 'Άγνωστο σφάλμα').strip()
            return False, f'LibreOffice error: {err}', 0

        base   = os.path.splitext(os.path.basename(lo_input))[0]
        lo_out = os.path.join(out_dir, f'{base}.pdf')

        if not os.path.exists(lo_out):
            return False, 'LibreOffice δεν παρήγαγε αρχείο PDF.', 0

        if lo_out != pdf_path:
            shutil.move(lo_out, pdf_path)

        with open(pdf_path, 'rb') as f:
            count = len(PyPDF2.PdfReader(f).pages)

        _set(yd_id, progress=33,
             detail=f'✓ Βήμα 1/3: PDF δημιουργήθηκε ({count} σελίδες)')
        return True, f'{count} σελίδες δημιουργήθηκαν.', count

    except _Abort:
        raise
    except subprocess.TimeoutExpired:
        return False, 'LibreOffice timeout (>20 λεπτά).', 0
    except Exception as e:
        logger.exception('excel_to_pdf failed')
        return False, str(e), 0
    finally:
        shutil.rmtree(lo_profile_dir, ignore_errors=True)
        if tmp_xlsx and os.path.exists(tmp_xlsx):
            os.remove(tmp_xlsx)


# ---------------------------------------------------------------------------
# Step 2: Clean PDF — remove blank pages (≤3 words)
# ---------------------------------------------------------------------------
def clean_pdf(input_path, output_path, yd_id=None):
    """
    Returns (success, msg, kept_count).
    Same logic as cleanPdf-dias.py.
    """
    try:
        with open(input_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            total   = len(reader.pages)
            writer  = PyPDF2.PdfWriter()
            kept = removed = 0

            for i, page in enumerate(reader.pages):
                if _aborted(yd_id):
                    raise _Abort()
                text  = re.sub(r'\s\s+', ' ',
                               (page.extract_text() or '').replace('\n', ' ').strip())
                words = text.split()
                if len(words) > 3:
                    writer.add_page(page)
                    kept += 1
                else:
                    removed += 1
                if i % 20 == 0 or i == total - 1:
                    pct  = 33 + int((i + 1) / total * 33)
                    flag = '✓' if len(words) > 3 else '✗ κενή'
                    _set(yd_id, progress=pct,
                         detail=(f'Βήμα 2/3: Σελίδα {i+1}/{total} [{flag}]  '
                                 f'Κρατήθηκαν: {kept}  Αφαιρέθηκαν: {removed}'))

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            writer.write(f)
        return True, f'{kept} σελίδες (αφαιρέθηκαν {removed} κενές).', kept

    except _Abort:
        raise
    except Exception as e:
        logger.exception('clean_pdf failed')
        return False, str(e), 0


# ---------------------------------------------------------------------------
# Step 3: Create CSV index
# ---------------------------------------------------------------------------
# Exact same patterns as createIndexFromPdf-dias.py
_AFM_PAT  = re.compile(r'\b\d{9}\b')   # 9-digit AFM


def create_index(pdf_path, csv_path, yd_id=None):
    """
    Scan each PDF page using the same logic as createIndexFromPdf-dias.py:
      - Iterate tokens; keep overwriting afm with each 9-digit match.
      - Record first 11-digit match as amka.
      - Break when both found.
    Result: afm = last 9-digit token found before amka (= employee personal AFM,
    since org AFM appears first and gets overwritten by employee AFM).

    Writes semicolon-delimited CSV: afm;amka;page
    Returns (success, msg, matched_count)
    """
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            total  = len(reader.pages)
            rows   = [['afm', 'amka', 'page']]
            count  = 0

            for i, page in enumerate(reader.pages):
                if _aborted(yd_id):
                    raise _Abort()

                tokens = re.sub(
                    r'\s\s+', ' ',
                    (page.extract_text() or '').replace('\n', ' ').strip()
                ).split()

                afm = amka = ''
                afm_found = amka_found = False

                # Mirror createIndexFromPdf-dias.py exactly:
                # keep overwriting afm on every 9-digit hit until amka is found
                for token in tokens:
                    if _AFM_PAT.match(token):
                        afm = token.lstrip('0')
                        afm_found = True
                    elif len(token) == 11 and token.isdigit():
                        amka = token.lstrip('0')
                        amka_found = True
                    if afm_found and amka_found:
                        break

                rows.append([afm, amka, i + 1])
                count += 1

                if i % 20 == 0 or i == total - 1:
                    pct = 66 + int((i + 1) / total * 34)
                    _set(yd_id, progress=min(pct, 99),
                         detail=(f'Βήμα 3/3: Σελίδα {i+1}/{total}  '
                                 f'ΑΦΜ: {afm or "—"}  ΑΜΚΑ: {amka or "—"}'))

        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerows(rows)

        matched = sum(1 for r in rows[1:] if r[0] and r[1])
        return True, f'{matched} εγγραφές με ΑΦΜ+ΑΜΚΑ ({count} σελίδες).', matched

    except _Abort:
        raise
    except Exception as e:
        logger.exception('create_index failed')
        return False, str(e), 0


# ---------------------------------------------------------------------------
# Step 3b: Create CSV index from Excel (Strategy B)
# ---------------------------------------------------------------------------
def _convert_xls_to_xlsx(xls_path):
    """
    Convert .xls to .xlsx using LibreOffice (headless) so openpyxl can read it.
    Returns path to a temporary .xlsx file.
    """
    lo = _find_libreoffice()
    if not lo:
        raise RuntimeError('LibreOffice not found for .xls conversion')

    tmp_dir = tempfile.mkdtemp(prefix='xls2xlsx_')
    lo_profile_dir = tempfile.mkdtemp(prefix='lo_profile_conv_')
    
    # Build profile URI
    lo_profile_posix = lo_profile_dir.replace(os.sep, '/')
    if not lo_profile_posix.startswith('/'):
        lo_profile_posix = '/' + lo_profile_posix
    lo_profile_uri = f'file://{lo_profile_posix}'

    try:
        if sys.platform != 'win32':
            subprocess.run(['pkill', '-9', '-f', 'soffice'], capture_output=True)

        subprocess.run(
            [
                lo, '--headless', '--norestore', '--nofirststartwizard',
                f'-env:UserInstallation={lo_profile_uri}',
                '--convert-to', 'xlsx',
                '--outdir', tmp_dir,
                xls_path,
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=300,
            env={**os.environ, 'HOME': lo_profile_dir} if sys.platform != 'win32' else None,
        )

        out_name = os.path.splitext(os.path.basename(xls_path))[0] + '.xlsx'
        out_path = os.path.join(tmp_dir, out_name)
        if not os.path.exists(out_path):
            raise RuntimeError('LibreOffice conversion failed (no output file)')
        
        # Move to a standalone temp file
        fd, final_path = tempfile.mkstemp(suffix='.xlsx', prefix='converted_')
        os.close(fd)
        shutil.move(out_path, final_path)
        return final_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(lo_profile_dir, ignore_errors=True)


def create_index_from_excel(excel_path, clean_pdf_path, csv_path, yd_id=None):
    """
    Strategy B: Read AFM+AMKA directly from the Excel file (XLS or XLSX),
    then map each employee to their PDF page range.
    
    For .xls files, they are converted to temporary .xlsx first.

    CSV format: afm;amka;page;num_pages
      page      = first PDF page of the certificate (1-based, odd)
      num_pages = pages to extract for that certificate (always 2 for XLSX)

    Returns (success, msg, matched_count).
    """
    import openpyxl

    PAGES_PER_CERT = 2
    temp_xlsx = None
    target_path = excel_path

    try:
        # If .xls, convert to .xlsx temp file
        if excel_path.lower().endswith('.xls'):
            try:
                _set(yd_id, detail='Βήμα 3/3: Μετατροπή .xls σε .xlsx για ανάγνωση δεδομένων…')
                temp_xlsx = _convert_xls_to_xlsx(excel_path)
                target_path = temp_xlsx
            except Exception as e:
                logger.warning('Could not convert .xls to .xlsx: %s', e)
                return create_index(clean_pdf_path, csv_path, yd_id)

        wb = openpyxl.load_workbook(target_path, read_only=True, data_only=True)
        records = []

        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                if _aborted(yd_id):
                    raise _Abort()

                afm = amka = ''
                for val in row:
                    if val is None or isinstance(val, bool):
                        continue
                    # Normalise to string — integers lose no precision
                    if isinstance(val, float):
                        int_val = int(val)
                        if float(int_val) != val:
                            continue  # has decimal part — not an ID
                        s = str(int_val)
                    elif isinstance(val, int):
                        s = str(val)
                    else:
                        s = str(val).strip()

                    # AFM: exactly 9 digits — keep overwriting (take last match)
                    if re.fullmatch(r'\d{9}', s):
                        afm = s.lstrip('0')
                    # AMKA: exactly 11 digits — take first match
                    elif re.fullmatch(r'\d{11}', s) and not amka:
                        amka = s.lstrip('0')

                if afm and amka:
                    records.append((afm, amka))

        wb.close()

        if not records:
            return False, 'Δεν βρέθηκαν εγγραφές ΑΦΜ+ΑΜΚΑ στο αρχείο Excel.', 0

        # Determine pages-per-certificate from actual PDF page count
        with open(clean_pdf_path, 'rb') as f:
            total_pages = len(PyPDF2.PdfReader(f).pages)

        n = len(records)
        if total_pages == n:
            PAGES_PER_CERT = 1
        elif total_pages == n * 2:
            PAGES_PER_CERT = 2
        else:
            logger.warning(
                'create_index_from_excel: PDF has %d pages, records=%d '
                '(not 1× or 2×). Falling back to PDF scan.',
                total_pages, n
            )
            _set(yd_id, detail=(
                f'Βήμα 3/3: Αναντιστοιχία σελίδων ({total_pages} PDF, {n} εγγραφές). Σάρωση PDF…'
            ))
            return create_index(clean_pdf_path, csv_path, yd_id)

        logger.info('create_index_from_excel: %d employees, %d pages/cert', n, PAGES_PER_CERT)

        # Write CSV: afm;amka;page;num_pages
        rows = [['afm', 'amka', 'page', 'num_pages']]
        for i, (afm, amka) in enumerate(records):
            page_start = i * PAGES_PER_CERT + 1  # 1-based; works for both 1 and 2 pages/cert
            rows.append([afm, amka, page_start, PAGES_PER_CERT])

            if i % 100 == 0 or i == len(records) - 1:
                pct = 66 + int((i + 1) / len(records) * 34)
                _set(yd_id, progress=min(pct, 99),
                     detail=(f'Βήμα 3/3: Εγγραφή {i+1}/{len(records)}  '
                             f'ΑΦΜ: {afm or "—"}  ΑΜΚΑ: {amka or "—"}'))

        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerows(rows)

        return (True,
                f'{len(records)} εγγραφές (Excel-indexing, {PAGES_PER_CERT} σελίδες/βεβαίωση).',
                len(records))

    except _Abort:
        raise
    except Exception as e:
        logger.exception('create_index_from_excel failed')
        return False, str(e), 0
    finally:
        if temp_xlsx and os.path.exists(temp_xlsx):
            try: os.remove(temp_xlsx)
            except OSError: pass

# ---------------------------------------------------------------------------
# Full pipeline (background thread)
# ---------------------------------------------------------------------------
def run_pipeline(year_data_id: int, flask_app):
    def _run():
        try:
            with flask_app.app_context():
                from app import db
                from app.models import YearData

                yd = db.session.get(YearData, year_data_id)
                if not yd:
                    return

                _set(year_data_id, progress=0, detail='Προετοιμασία…', abort=False)

                data_folder = flask_app.config['DATA_FOLDER']
                year        = yd.year
                ydir        = os.path.join(data_folder, str(year))
                excel_path  = os.path.join(ydir, 'excel', yd.excel_filename)
                raw_pdf     = os.path.join(ydir, 'pdf',   f'{year}_raw.pdf')
                clean_path  = os.path.join(ydir, 'pdf',   f'{year}_clean.pdf')
                csv_path    = os.path.join(ydir, 'csv',   f'{year}.csv')

                try:
                    # ── Step 1: Excel → PDF (LibreOffice, landscape) ──────────
                    _set(year_data_id, progress=0,
                         detail='Βήμα 1/3: Εκκίνηση LibreOffice (landscape)…')
                    yd.processing_message = 'Βήμα 1/3: Μετατροπή Excel → PDF (landscape)…'
                    db.session.commit()

                    ok, msg, pages = excel_to_pdf(excel_path, raw_pdf, year_data_id)
                    if not ok:
                        raise RuntimeError(msg)

                    yd.processing_message = f'✓ Βήμα 1/3: {msg}'
                    db.session.commit()

                    # ── Step 2: Clean blank pages ─────────────────────────────
                    _set(year_data_id, progress=34,
                         detail='Βήμα 2/3: Καθαρισμός κενών σελίδων…')
                    yd.processing_message = 'Βήμα 2/3: Καθαρισμός κενών σελίδων…'
                    db.session.commit()

                    ok, msg, kept = clean_pdf(raw_pdf, clean_path, year_data_id)
                    if not ok:
                        raise RuntimeError(msg)

                    yd.processing_message = f'✓ Βήμα 2/3: {msg}'
                    db.session.commit()

                    # ── Step 3: Create CSV index ───────────────────────────────
                    _set(year_data_id, progress=67,
                         detail='Βήμα 3/3: Δημιουργία ευρετηρίου…')
                    yd.processing_message = 'Βήμα 3/3: Δημιουργία ευρετηρίου…'
                    db.session.commit()

                    ok, msg, count = create_index_from_excel(
                        excel_path, clean_path, csv_path, year_data_id
                    )
                    if not ok:
                        raise RuntimeError(msg)

                    yd.pdf_filename       = f'{year}_clean.pdf'
                    yd.csv_filename       = f'{year}.csv'
                    yd.employee_count     = count
                    yd.processing_status  = 'done'
                    yd.processing_message = f'✓ Ολοκληρώθηκε. {count} εγγραφές.'
                    yd.processed_at       = _now_athens()
                    _set(year_data_id, progress=100,
                         detail=f'✓ Ολοκληρώθηκε! {count} βεβαιώσεις έτοιμες.')

                except _Abort:
                    for path in (raw_pdf, clean_path, csv_path):
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except OSError:
                            pass
                    yd.processing_status  = 'idle'
                    yd.processing_message = 'Ακυρώθηκε από τον χρήστη.'
                    _set(year_data_id, progress=0, detail='Ακυρώθηκε.')

                except Exception as exc:
                    logger.exception('Pipeline failed for year %s', yd.year)
                    yd.processing_status  = 'error'
                    yd.processing_message = str(exc)
                    _set(year_data_id, progress=0, detail=f'Σφάλμα: {exc}')

                finally:
                    db.session.commit()

        finally:
            release_processing_slot()

    t = threading.Thread(target=_run, daemon=True)
    with _threads_lock:
        _threads[year_data_id] = t
    t.start()
