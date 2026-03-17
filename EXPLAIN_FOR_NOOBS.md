# How This App Works — Plain English Explanation

## What Does This App Do?

Every year, employees receive a **salary certificate** (Βεβαίωση Αποδοχών) — a PDF document
that shows their annual income, needed for tax filing. This app lets employees download their
own certificate by entering their tax number (ΑΦΜ) and social security number (ΑΜΚΑ).

---

## The Two Types of Users

### Admin (the accountant / IT person)
- Logs in at `/auth/login`
- Uploads the Excel file that contains all employee certificates for a given year
- Clicks "Process" to convert it into a PDF and build a searchable index
- Manages years and users

### Employee (everyone else)
- Goes to the home page `/`
- Selects the year, types their ΑΦΜ and ΑΜΚΑ
- Downloads their personal PDF certificate

No employee account is needed. The app never stores what the employee typed.

---

## What Is the Excel File?

The accountant receives an Excel file (e.g. `2024.xls`) from the payroll system.
This file contains **one sheet per employee** — so a 2847-employee organization
has 2847 sheets in one Excel file. Each sheet is one employee's certificate,
formatted for printing (landscape, fit-to-one-page).

---

## The Processing Pipeline (What Happens When You Click "Process")

When the admin clicks **Process**, the app runs 3 steps in the background:

### Step 1 — Excel → PDF
LibreOffice (a free open-source office suite, like Microsoft Office) is run in
"headless" mode (no visible window) to convert the Excel file into a PDF.

- On **Windows**: LibreOffice reads the file directly — print settings are preserved.
- On **Linux/Docker**: An extra preparation step is needed first because Linux
  fonts and rendering differ from Windows:
  1. Convert `.xls` → `.xlsx` (LibreOffice recalculates all formulas)
  2. Patch the `.xlsx` file: widen columns, force landscape orientation, convert
     numbers to text (prevents `###` symbols that appear when a column is too narrow)
  3. Convert the patched `.xlsx` → PDF

Result: `{year}_raw.pdf` — one big PDF with all employee certificates, one per page.

### Step 2 — Clean the PDF
PyPDF2 (a Python library) scans each page. Pages with 3 words or fewer are
considered **blank** (e.g. separator pages) and are removed.

Result: `{year}_clean.pdf` — only real content pages.

### Step 3 — Build the Index (CSV)
PyPDF2 reads each page of the clean PDF and extracts the text. It looks for:
- A **9-digit number** = the employee's ΑΦΜ
- An **11-digit number** = the employee's ΑΜΚΑ

It records: `ΑΦΜ ; ΑΜΚΑ ; page_number` for every page.

Result: `{year}.csv` — a lookup table like:
```
afm;amka;page
123456789;12345678901;1
987654321;98765432101;2
...
```

---

## How Employee Search Works

When an employee enters their ΑΦΜ + ΑΜΚΑ and clicks download:

1. The app opens the CSV index file for the selected year
2. It scans line by line for a matching ΑΦΜ + ΑΜΚΑ
3. If found, it reads the page number from the CSV
4. It extracts just that page (or multiple pages) from `{year}_clean.pdf`
5. It sends that single-page PDF to the employee's browser as a download

The employee gets only their own certificate — no one else's.

---

## File Storage Layout

```
data/
  2024/
    excel/  2024.xls          ← the original file uploaded by admin
    pdf/    2024_raw.pdf       ← full PDF after Step 1
            2024_clean.pdf     ← PDF after Step 2 (blank pages removed)
    csv/    2024.csv           ← index built in Step 3
  2025/
    ...
instance/
  app.db                       ← SQLite database (users, year records, processing status)
```

---

## The Progress Bar

Because the conversion can take a long time (20–60+ minutes for 2847 sheets on
a server), the admin dashboard shows a live progress bar. The browser polls
`/admin/status/<id>` every second and updates the display. There are 3 visible
stages: Βήμα 1/3, Βήμα 2/3, Βήμα 3/3.

---

## The Abort / Delete System

If the admin clicks Delete while processing is running:
1. The app signals the background thread to stop (sets an "abort" flag)
2. The running LibreOffice process is killed immediately (within 0.3 seconds)
3. The openpyxl preprocessing loop checks the flag at the start of each sheet
4. The thread cleans up any half-finished files and exits
5. The year folder is deleted from disk and the database record is removed

---

## Docker vs Windows

| | Windows (dev) | Docker/Linux (production) |
|---|---|---|
| Server | Flask dev server (port 5000) | gunicorn + nginx (port 8085) |
| Excel preprocessing | None — LibreOffice handles it natively | openpyxl patches columns/orientation |
| Workers | N/A | **1 worker only** (progress state is in-memory; 2 workers would break the progress bar) |
| Fonts | Windows fonts | DejaVu, Liberation, Carlito, Caladea, Microsoft core fonts |

---

## Key Numbers (for the 2024/2025 file)

- **2847** sheets in the Excel file = 2847 employee certificates
- **Step 1** takes the longest: 20–60+ minutes on Docker
- **Step 2 + 3** are fast: a few minutes each
- Total processing time on Docker: up to ~2 hours (timeout set to 2 hours)
