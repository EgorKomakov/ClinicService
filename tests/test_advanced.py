import pytest
from models import Appointment, Patient, Doctor, User, ScheduleSlot, Service
from datetime import datetime, timedelta, time
from extensions import db


# ==========================================
# 1. ТЕСТЫ ОТМЕНЫ ПРИЕМА (Бизнес-логика)
# ==========================================

def test_patient_can_cancel_appointment_more_than_2_hours(app, client, init_data):
    """Тест: Пациент может отменить запись, если до нее > 2 часов."""
    with app.app_context():
        appt = Appointment(
            patient_id=init_data['patient_id'],
            doctor_id=init_data['doctor_id'],
            date=datetime.now() + timedelta(hours=3),
            status='scheduled'
        )
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})

    response = client.post(f'/appointments/{appt_id}/cancel', follow_redirects=True)

    with app.app_context():
        updated_appt = db.session.get(Appointment, appt_id)
        assert updated_appt.status == 'cancelled'
        assert 'Запись успешно отменена' in response.text


def test_patient_cannot_cancel_appointment_less_than_2_hours(app, client, init_data):
    """Тест: Пациент НЕ может отменить запись, если до нее < 2 часов."""
    with app.app_context():
        appt = Appointment(
            patient_id=init_data['patient_id'],
            doctor_id=init_data['doctor_id'],
            date=datetime.now() + timedelta(hours=1),
            status='scheduled'
        )
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})
    response = client.post(f'/appointments/{appt_id}/cancel', follow_redirects=True)

    with app.app_context():
        updated_appt = db.session.get(Appointment, appt_id)
        assert updated_appt.status == 'scheduled'
        assert 'Отмена невозможна: до приёма осталось менее 2 часов' in response.text


# ==========================================
# 2. ТЕСТЫ РАСПИСАНИЯ (Защита от удаления)
# ==========================================

def test_admin_cannot_delete_slot_with_active_appointment(app, client, init_data):
    """Тест: Нельзя удалить слот расписания, если на него есть запись."""
    with app.app_context():
        slot = ScheduleSlot(doctor_id=init_data['doctor_id'], day_of_week=0, start_time=time(9, 0),
                            end_time=time(12, 0))
        db.session.add(slot)
        db.session.commit()
        slot_id = slot.id

        days_ahead = 0 - datetime.now().weekday()
        if days_ahead <= 0: days_ahead += 7
        next_monday = (datetime.now() + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)

        appt = Appointment(patient_id=init_data['patient_id'], doctor_id=init_data['doctor_id'], date=next_monday,
                           status='scheduled')
        db.session.add(appt)
        db.session.commit()

    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})
    response = client.post(f'/delete_slot/{slot_id}', follow_redirects=True)

    with app.app_context():
        assert db.session.get(ScheduleSlot, slot_id) is not None
        assert 'Нельзя удалить слот: на это время уже записано' in response.text


def test_admin_can_delete_empty_slot(app, client, init_data):
    """Тест: Можно удалить слот, если на него нет записей."""
    with app.app_context():
        slot = ScheduleSlot(doctor_id=init_data['doctor_id'], day_of_week=1, start_time=time(14, 0),
                            end_time=time(18, 0))
        db.session.add(slot)
        db.session.commit()
        slot_id = slot.id

    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})
    response = client.post(f'/delete_slot/{slot_id}', follow_redirects=True)

    with app.app_context():
        assert db.session.get(ScheduleSlot, slot_id) is None
        assert 'Слот успешно удалён' in response.text


# ==========================================
# 3. ТЕСТЫ CRUD ПАЦИЕНТОВ (Валидация)
# ==========================================

def test_admin_cannot_create_patient_with_invalid_email(app, client, init_data):
    """Тест: Админ не может создать пациента с некорректным email."""
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    response = client.post('/patients/new', data={
        'first_name': 'Новый',
        'last_name': 'Пациент',
        'dob': '1990-01-01',
        'phone': '+79991234567',
        'email': 'invalid-email',
        'notes': ''
    }, follow_redirects=True)

    with app.app_context():
        patient = Patient.query.filter_by(last_name='Пациент').first()
        assert patient is None
        assert 'Введите корректный email' in response.text