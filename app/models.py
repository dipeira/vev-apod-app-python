from datetime import datetime
from zoneinfo import ZoneInfo

def _now_athens():
    return datetime.now(ZoneInfo('Europe/Athens')).replace(tzinfo=None)
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_now_athens)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class YearData(db.Model):
    __tablename__ = 'year_data'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)
    excel_filename = db.Column(db.String(256))
    pdf_filename = db.Column(db.String(256))        # cleaned PDF used for downloads
    csv_filename = db.Column(db.String(256))        # index CSV
    processing_status = db.Column(db.String(20), default='idle')
    # idle | processing | done | error
    processing_message = db.Column(db.Text)
    employee_count = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime)
    processed_at = db.Column(db.DateTime)

    def year_dir(self, data_folder):
        import os
        return os.path.join(data_folder, str(self.year))

    def excel_path(self, data_folder):
        import os
        return os.path.join(self.year_dir(data_folder), 'excel', self.excel_filename)

    def pdf_path(self, data_folder):
        import os
        return os.path.join(self.year_dir(data_folder), 'pdf', self.pdf_filename)

    def csv_path(self, data_folder):
        import os
        return os.path.join(self.year_dir(data_folder), 'csv', self.csv_filename)

    def __repr__(self):
        return f'<YearData {self.year}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
