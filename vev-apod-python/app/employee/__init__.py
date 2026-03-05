from flask import Blueprint

employee_bp = Blueprint('employee', __name__, url_prefix='/')

from app.employee import routes  # noqa: E402, F401
