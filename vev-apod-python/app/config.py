import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "instance", "app.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATA_FOLDER = os.environ.get('DATA_FOLDER', os.path.join(BASE_DIR, 'data'))
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB max upload
    ORG_NAME = os.environ.get('ORG_NAME', 'Διεύθυνση Π.Ε. Ηρακλείου')
    ALLOWED_EXCEL_EXTENSIONS = {'xls', 'xlsx'}
