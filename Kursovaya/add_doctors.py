from werkzeug.security import generate_password_hash

from app import app, db
from models import Doctor, User

DEFAULT_PASSWORD = "123"

with app.app_context():
    doctors_data = [
        {"first_name": "Иван", "last_name": "Петров", "specialization": "Терапевт", "phone": "123-45-67", "email": "ivan.petrov@example.com"},
        {"first_name": "Мария", "last_name": "Сидорова", "specialization": "Хирург", "phone": "987-65-43", "email": "maria.sidorova@example.com"},
        {"first_name": "Алексей", "last_name": "Кузнецов", "specialization": "Кардиолог", "phone": "555-12-34", "email": "aleksey.k@example.com"},
        {"first_name": "Екатерина", "last_name": "Смирнова", "specialization": "Невролог", "phone": "444-56-78", "email": "ekaterina.s@example.com"},
        {"first_name": "Дмитрий", "last_name": "Федоров", "specialization": "Педиатр", "phone": "333-22-11", "email": "dmitry.f@example.com"}
    ]

    for data in doctors_data:
        doctor = Doctor(
            first_name=data["first_name"],
            last_name=data["last_name"],
            specialization=data["specialization"],
            phone=data["phone"],
            email=data["email"]
        )

        user = User(
            username=data["email"],
            password_hash=generate_password_hash(DEFAULT_PASSWORD),
            role="doctor"
        )

        doctor.user = user
        db.session.add(doctor)
        db.session.add(user)

    db.session.commit()
