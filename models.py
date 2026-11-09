from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from datetime import datetime, timezone


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    doctor = db.relationship('Doctor', back_populates='user', uselist=False)
    patient = db.relationship('Patient', back_populates='user', uselist=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    specialization = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    user = db.relationship('User', back_populates='doctor')
    appointments = db.relationship('Appointment', back_populates='doctor', cascade="all, delete-orphan")
    schedule_slots = db.relationship('ScheduleSlot', back_populates='doctor', cascade="all, delete-orphan")

    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Doctor {self.full_name()}>"


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    birth_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)

    user = db.relationship('User', back_populates='patient')
    appointments = db.relationship('Appointment', back_populates='patient', cascade="all, delete-orphan")
    images = db.relationship('MedicalImage', back_populates='patient', cascade="all, delete-orphan")
    achievements = db.relationship('PatientAchievement', back_populates='patient', cascade="all, delete-orphan")

    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_level_progress(self):
        next_level_points = self.level * 50
        current_level_base = (self.level - 1) * 50
        progress = self.points - current_level_base
        total_needed = next_level_points - current_level_base
        percentage = min(100, int((progress / total_needed) * 100)) if total_needed > 0 else 100
        return {
            'current_points': progress,
            'needed_points': total_needed,
            'percentage': percentage,
            'next_level_total': next_level_points
        }

    def __repr__(self):
        return f"<Patient {self.full_name()} (Lvl {self.level})>"


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    audio_filename = db.Column(db.String(255))
    status = db.Column(db.String(20), default='scheduled', nullable=False)
    price = db.Column(db.Float, default=1500.0)
    payment_status = db.Column(db.String(20), default='unpaid')

    doctor = db.relationship('Doctor', back_populates='appointments')
    patient = db.relationship('Patient', back_populates='appointments')
    procedures = db.relationship('AssignedProcedure', back_populates='appointment', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Appointment {self.id} ({self.date.strftime('%Y-%m-%d %H:%M')})>"


class ScheduleSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    doctor = db.relationship('Doctor', back_populates='schedule_slots')

    def __repr__(self):
        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        return f"{days[self.day_of_week]} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"


class MedicalImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    description = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    patient = db.relationship('Patient', back_populates='images')


class PatientAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(50))
    date_earned = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    patient = db.relationship('Patient', back_populates='achievements')


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)

    def __repr__(self):
        return f"<Service {self.name} ({self.price} руб.)>"


class AssignedProcedure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    status = db.Column(db.String(20), default='unpaid')
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    appointment = db.relationship('Appointment', back_populates='procedures')
    service = db.relationship('Service')


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Feedback from {self.fullname}>"