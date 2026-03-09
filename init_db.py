"""Initialize the database and create the default admin user."""
import os
from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    db.create_all()

    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', is_admin=True)
        admin.set_password('d1pe1712')
        db.session.add(admin)
        db.session.commit()
        print('Admin user created: admin / d1pe1712')
    else:
        print('Admin user already exists.')

    # Ensure data directory exists
    data_dir = app.config['DATA_FOLDER']
    os.makedirs(data_dir, exist_ok=True)
    print(f'Data directory: {data_dir}')
    print('Database initialized successfully.')
