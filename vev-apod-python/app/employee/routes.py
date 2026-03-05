import csv
import io
import os

import PyPDF2
from flask import (
    render_template, request, flash, send_file, current_app
)

from app.employee import employee_bp
from app.models import YearData


def _search_csv(csv_path, afm, amka):
    """Return page number (1-based) or None if not found."""
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
                    return int(row[2])
    except Exception:
        pass
    return None


def _extract_page(pdf_path, page_number):
    """Extract a single page (1-based) from a PDF and return bytes."""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        writer = PyPDF2.PdfWriter()
        writer.add_page(reader.pages[page_number - 1])
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
        page_num = _search_csv(csv_path, afm, amka)

        if not page_num:
            flash('Δεν βρέθηκαν στοιχεία για τα δεδομένα που εισάγατε.', 'danger')
            return render_template('employee/index.html', years=years)

        pdf_path = yd.pdf_path(data_folder)
        buf = _extract_page(pdf_path, page_num)
        return send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'vevaiosi_{year_str}.pdf',
        )

    return render_template('employee/index.html', years=years)
