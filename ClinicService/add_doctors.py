from werkzeug.security import generate_password_hash
from app import app, db
from models import Doctor, User, Appointment, ScheduleSlot
from datetime import time

DEFAULT_PASSWORD = "123"

with app.app_context():
    Appointment.query.delete()
    ScheduleSlot.query.delete()
    Doctor.query.delete()
    User.query.filter_by(role='doctor').delete()
    db.session.commit()

    doctors_data = [
        {"first_name": "Иван",   "last_name": "Петров",    "specialization": "Терапевт", "phone": "123-45-67", "email": "ivan.petrov@example.com"},
        {"first_name": "Мария",  "last_name": "Сидорова",  "specialization": "Хирург",   "phone": "987-65-43", "email": "maria.sidorova@example.com"},
        {"first_name": "Алексей","last_name": "Кузнецов",  "specialization": "Кардиолог","phone": "555-12-34", "email": "aleksey.k@example.com"},
        {"first_name": "Екатерина","last_name": "Смирнова","specialization": "Невролог", "phone": "444-56-78", "email": "ekaterina.s@example.com"},
        {"first_name": "Дмитрий","last_name": "Федоров",   "specialization": "Педиатр",  "phone": "333-22-11", "email": "dmitry.f@example.com"}
    ]

    for data in doctors_data:
        doctor = Doctor(**data)
        user = User(username=data["email"], role="doctor")
        user.set_password(DEFAULT_PASSWORD)
        doctor.user = user
        db.session.add(doctor)
        db.session.add(user)
        db.session.flush()

        for day in range(0, 5):
            slot = ScheduleSlot(
                doctor_id=doctor.id,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(17, 0)
            )
            db.session.add(slot)

    db.session.commit()
    print("Врачи и слоты успешно добавлены.")