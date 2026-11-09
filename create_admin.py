from app import app, db
from models import User

with app.app_context():
    if not User.query.filter_by(username='admin', role='admin').first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin')
        db.session.add(admin)
        db.session.commit()
        print("Админ создан успешно!")
    else:
        print("Админ уже существует")
