import os
from datetime import datetime
from functools import wraps

from flask import (
    render_template, redirect, url_for, request,
    flash, jsonify, current_app, make_response
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.admin import admin_bp
from app.models import User, YearData
from app.processing.utils import run_pipeline, request_abort, get_state


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Δεν έχετε δικαίωμα πρόσβασης.', 'danger')
            return redirect(url_for('employee.index'))
        return f(*args, **kwargs)
    return decorated


def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _allowed_excel(filename):
    exts = current_app.config['ALLOWED_EXCEL_EXTENSIONS']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in exts


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    years = YearData.query.order_by(YearData.year.desc()).all()
    return no_cache(make_response(render_template('admin/dashboard.html', years=years)))


# ---------------------------------------------------------------------------
# Upload Excel for a year
# ---------------------------------------------------------------------------

@admin_bp.route('/upload', methods=['POST'])
@login_required
@admin_required
def upload():
    year_str = request.form.get('year', '').strip()
    file = request.files.get('excel_file')

    # Fallback: extract year from filename if field is empty
    if not year_str and file and file.filename:
        import re as _re
        m = _re.search(r'(20\d{2})', file.filename)
        if m:
            year_str = m.group(1)

    if not year_str.isdigit() or not (2000 <= int(year_str) <= 2100):
        flash('Μη έγκυρο έτος.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if not file or file.filename == '':
        flash('Δεν επιλέχθηκε αρχείο.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if not _allowed_excel(file.filename):
        flash('Επιτρέπονται μόνο αρχεία .xls και .xlsx.', 'danger')
        return redirect(url_for('admin.dashboard'))

    year = int(year_str)
    data_folder = current_app.config['DATA_FOLDER']
    excel_dir = os.path.join(data_folder, str(year), 'excel')
    os.makedirs(excel_dir, exist_ok=True)

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f'{year}.{ext}')
    file.save(os.path.join(excel_dir, filename))

    yd = YearData.query.filter_by(year=year).first()
    if yd:
        yd.excel_filename = filename
        yd.processing_status = 'idle'
        yd.processing_message = None
        yd.uploaded_at = datetime.utcnow()
    else:
        yd = YearData(
            year=year,
            excel_filename=filename,
            processing_status='idle',
            uploaded_at=datetime.utcnow(),
        )
        db.session.add(yd)

    db.session.commit()
    flash(f'Το αρχείο για το έτος {year} ανέβηκε επιτυχώς.', 'success')
    return redirect(url_for('admin.dashboard'))


# ---------------------------------------------------------------------------
# Trigger processing
# ---------------------------------------------------------------------------

@admin_bp.route('/process/<int:year_id>', methods=['POST'])
@login_required
@admin_required
def process(year_id):
    yd = db.session.get(YearData, year_id)
    if not yd:
        return jsonify({'error': 'Not found'}), 404

    if yd.processing_status == 'processing':
        return jsonify({'error': 'Η επεξεργασία είναι ήδη σε εξέλιξη.'}), 409

    if not yd.excel_filename:
        return jsonify({'error': 'Δεν υπάρχει αρχείο Excel.'}), 400

    yd.processing_status = 'processing'
    yd.processing_message = 'Έναρξη επεξεργασίας…'
    db.session.commit()

    run_pipeline(year_id, current_app._get_current_object())
    return jsonify({'status': 'processing'})


# ---------------------------------------------------------------------------
# Status polling endpoint
# ---------------------------------------------------------------------------

@admin_bp.route('/status/<int:year_id>')
@login_required
@admin_required
def status(year_id):
    yd = db.session.get(YearData, year_id)
    if not yd:
        return jsonify({'error': 'Not found'}), 404
    state = get_state(year_id)
    return jsonify({
        'status':         yd.processing_status,
        'message':        yd.processing_message or '',
        'progress':       state.get('progress', 0),
        'detail':         state.get('detail', ''),
        'employee_count': yd.employee_count,
    })


# ---------------------------------------------------------------------------
# Abort processing
# ---------------------------------------------------------------------------

@admin_bp.route('/abort/<int:year_id>', methods=['POST'])
@login_required
@admin_required
def abort(year_id):
    request_abort(year_id)
    return jsonify({'status': 'abort_requested'})


# ---------------------------------------------------------------------------
# Delete a year record + its files
# ---------------------------------------------------------------------------

@admin_bp.route('/delete/<int:year_id>', methods=['POST'])
@login_required
@admin_required
def delete_year(year_id):
    yd = db.session.get(YearData, year_id)
    if not yd:
        flash('Δεν βρέθηκε εγγραφή.', 'danger')
        return redirect(url_for('admin.dashboard'))

    import shutil
    year_dir = os.path.join(current_app.config['DATA_FOLDER'], str(yd.year))
    if os.path.isdir(year_dir):
        shutil.rmtree(year_dir)

    db.session.delete(yd)
    db.session.commit()
    flash(f'Τα δεδομένα για το έτος {yd.year} διαγράφηκαν.', 'success')
    return redirect(url_for('admin.dashboard'))


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    is_admin = request.form.get('is_admin') == '1'

    if not username or not password:
        flash('Το όνομα χρήστη και ο κωδικός είναι υποχρεωτικά.', 'danger')
        return redirect(url_for('admin.users'))

    if User.query.filter_by(username=username).first():
        flash(f'Ο χρήστης "{username}" υπάρχει ήδη.', 'danger')
        return redirect(url_for('admin.users'))

    user = User(username=username, is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'Ο χρήστης "{username}" δημιουργήθηκε.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('Ο χρήστης δεν βρέθηκε.', 'danger')
        return redirect(url_for('admin.users'))

    if user.id == current_user.id:
        flash('Δεν μπορείτε να διαγράψετε τον εαυτό σας.', 'danger')
        return redirect(url_for('admin.users'))

    db.session.delete(user)
    db.session.commit()
    flash(f'Ο χρήστης "{user.username}" διαγράφηκε.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/password', methods=['POST'])
@login_required
@admin_required
def change_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('Ο χρήστης δεν βρέθηκε.', 'danger')
        return redirect(url_for('admin.users'))

    new_password = request.form.get('new_password', '')
    if not new_password:
        flash('Ο νέος κωδικός δεν μπορεί να είναι κενός.', 'danger')
        return redirect(url_for('admin.users'))

    user.set_password(new_password)
    db.session.commit()
    flash(f'Ο κωδικός του "{user.username}" άλλαξε.', 'success')
    return redirect(url_for('admin.users'))
