import csv
import io

import PyPDF2
from flask import (
    render_template, request, flash, send_file, current_app
)

from app.employee import employee_bp
from app.models import YearData


def _search_csv(csv_path, afm, amka):
    """Return (page, num_pages) or None if not found.
    Supports both 3-column (XLS) and 4-column (XLSX) CSV formats."""
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader, None)  # skip header
            for row in reader:
                if len(row) < 3:
                    continue
                row_afm = row[0].strip().lstrip('0')
                row_amka = row[1].strip().lstrip('0')
                if row_afm == afm and row_amka == amka:
                    page = int(row[2])
                    num_pages = int(row[3]) if len(row) >= 4 and row[3].strip() else 1
                    return page, num_pages
    except Exception:
        pass
    return None


def _extract_page(pdf_path, page_number, num_pages=1):
    """Extract one or more consecutive pages (1-based) from a PDF and return bytes."""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        writer = PyPDF2.PdfWriter()
        for p in range(page_number - 1, min(page_number - 1 + num_pages, len(reader.pages))):
            writer.add_page(reader.pages[p])
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        return buf


@employee_bp.route('/', methods=['GET', 'POST'])
def index():
    years = (
        YearData.query
        .filter_by(processing_status='done')
        .order_by(YearData.year.desc())
        .all()
    )

    if request.method == 'POST':
        year_str = request.form.get('year', '').strip()
        afm = request.form.get('afm', '').strip().lstrip('0')
        amka = request.form.get('amka', '').strip().lstrip('0')

        if not year_str or not afm or not amka:
            flash('Παρακαλώ συμπληρώστε όλα τα πεδία.', 'danger')
            return render_template('employee/index.html', years=years)

        yd = YearData.query.filter_by(year=int(year_str), processing_status='done').first()
        if not yd:
            flash('Δεν υπάρχουν διαθέσιμα δεδομένα για το επιλεγμένο έτος.', 'danger')
            return render_template('employee/index.html', years=years)

        data_folder = current_app.config['DATA_FOLDER']
        csv_path = yd.csv_path(data_folder)
        result = _search_csv(csv_path, afm, amka)

        if not result:
            flash('Δεν βρέθηκαν στοιχεία για τα δεδομένα που εισάγατε.', 'danger')
            return render_template('employee/index.html', years=years)

        page_num, num_pages = result
        pdf_path = yd.pdf_path(data_folder)
        buf = _extract_page(pdf_path, page_num, num_pages)
        return send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'vevaiosi_{year_str}.pdf',
        )

    return render_template('employee/index.html', years=years)
