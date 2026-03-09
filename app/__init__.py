import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object('app.config.Config')

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Παρακαλώ συνδεθείτε για να συνεχίσετε.'
    login_manager.login_message_category = 'warning'

    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.employee import employee_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(employee_bp)

    with app.app_context():
        os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)

    return app
