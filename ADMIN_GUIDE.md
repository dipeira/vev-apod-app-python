# Administrator Guide

---

## Accessing the Admin Area

Navigate to the application URL and click **Σύνδεση** (Login) in the top-right corner, or go directly to `/auth/login`.

Default credentials:

| Username | Password |
|---|---|
| admin | d1pe1712 |

**Change this password immediately** via **Χρήστες → Κωδικός** after first login.

After login, click **Dashboard** in the navigation bar to access the admin area.

---

## Annual Workflow — Processing Payroll Data

### Step 1: Upload the Excel File

1. In the Dashboard, find the **Ανέβασμα αρχείου Excel** (Upload Excel) section.
2. Click **Choose File** and select the payroll Excel file (`.xls` or `.xlsx`, up to 200 MB).
3. The **Έτος** (Year) field is filled automatically if the filename contains a 4-digit year (e.g. `payroll_2024.xlsx`). Correct it if needed.
4. Click **Ανέβασμα**.

The file is saved and a new row appears in the year table with status `idle`.

### Step 2: Process the File

1. In the year table, click the **Process** button for the year you just uploaded.
2. The button changes to a blinking **Processing…** label and a progress bar appears.
3. The pipeline runs three steps in the background:
   - **Step 1/3**: LibreOffice converts the Excel file to PDF (~1–10 minutes depending on file size)
   - **Step 2/3**: Blank pages are removed from the PDF
   - **Step 3/3**: An index is built (AFM + AMKA → PDF page number)
4. Progress updates every second automatically.
5. When complete, the status changes to `done` and the employee count is shown.

> **Note**: Only one file can be processed at a time. All Process buttons are disabled while a job is running.

### Step 3: Verify

Check that the **Εγγραφές** (Records) count matches the expected number of employees. If it is significantly lower, the Excel file may have a formatting issue.

---

## Deleting a Year's Data

1. Click the trash icon in the **Ενέργειες** column for the year you want to remove.
2. Confirm the deletion prompt.
3. If a processing job is running for that year, it is automatically stopped before the files are removed. The pipeline stops within a few seconds and all intermediate files (raw PDF, clean PDF, CSV) are deleted along with the database record.

> **Warning**: This permanently deletes the Excel file, all generated PDFs, and the CSV index for that year. Employees will no longer be able to download certificates for that year.

---

## User Management

Navigate to **Dashboard → Χρήστες** (or click "Χρήστες" in the navbar).

### Create a User

Fill in username, password, and optionally check **Διαχειριστής** to grant admin rights. Click **Δημιουργία**.

### Change a User's Password

Click **Κωδικός** next to the user, enter a new password in the modal, and click **Αποθήκευση**.

### Delete a User

Click the trash icon next to the user. You cannot delete your own account.

---

## Environment Variables

Set these before starting the application (see `.env.example`):

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes (production) | Long random string used to sign sessions. Never use the default in production. |
| `ORG_NAME` | No | Organisation name shown in the UI. Default: `Διεύθυνση Π.Ε. Ηρακλείου` |
| `DATABASE_URL` | No | SQLAlchemy connection string. Default: SQLite at `instance/app.db` |
| `DATA_FOLDER` | No | Path to the data directory. Default: `<project>/data` |

---

## Docker Management

### View application logs

```bash
docker compose logs -f web
```

### Restart the application

```bash
docker compose restart web
```

### Stop everything

```bash
docker compose down
```

### Deploy an update

```bash
git pull
docker compose up -d --build
```

### Check running containers

```bash
docker compose ps
```

---

## Backup

### Database

```bash
# Docker
docker compose exec web cp /app/instance/app.db /app/instance/app.db.bak
docker compose cp web:/app/instance/app.db ./backup_app.db

# Local
cp instance/app.db instance/app.db.bak
```

### Uploaded files and PDFs

```bash
# Docker — copy entire data volume
docker compose exec web tar czf /tmp/data_backup.tar.gz /app/data
docker compose cp web:/tmp/data_backup.tar.gz ./data_backup.tar.gz

# Local
cp -r data/ data_backup/
```
