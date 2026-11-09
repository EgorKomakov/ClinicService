import pytest
import io
from datetime import datetime, timedelta, time
from models import Appointment, Patient, Doctor, User, ScheduleSlot, Service
from extensions import db


# ==========================================
# 1. ДВОЙНАЯ ЗАПИСЬ НА ОДНО ВРЕМЯ
# ==========================================

def test_cannot_double_book_appointment(app, client, init_data):
    """Тест: Два пациента не могут записаться на одно и то же время."""
    with app.app_context():
        doc = db.session.get(Doctor, init_data['doctor_id'])
        target_date = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        slot = ScheduleSlot(doctor_id=doc.id, day_of_week=target_date.weekday(), start_time=time(9, 0),
                            end_time=time(17, 0))
        db.session.add(slot)

        pat2_user = User(username='pat2_test', role='patient')
        pat2_user.set_password('pass')
        pat2 = Patient(first_name='Петр', last_name='Петров', user=pat2_user)
        db.session.add(pat2_user)
        db.session.add(pat2)
        db.session.commit()

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})
    res1 = client.post('/appointments/add', data={
        'doctor_id': init_data['doctor_id'],
        'slot_datetime': target_date.strftime('%Y-%m-%dT%H:%M'),
        'notes': 'Первый'
    }, follow_redirects=True)
    assert 'Вы успешно записались' in res1.text

    client.get('/logout')
    client.post('/login', data={'username': 'pat2_test', 'password': 'pass', 'role': 'patient'})
    res2 = client.post('/appointments/add', data={
        'doctor_id': init_data['doctor_id'],
        'slot_datetime': target_date.strftime('%Y-%m-%dT%H:%M'),
        'notes': 'Второй'
    }, follow_redirects=True)

    assert 'На это время уже есть запись' in res2.text


# ==========================================
# 2. ВАЛИДАЦИЯ ВРЕМЕНИ (НЕ КРАТНО 30 МИНУТАМ)
# ==========================================

def test_admin_cannot_book_wrong_minutes(app, client, init_data):
    """Тест: Нельзя записать пациента на время, не кратное 30 минутам (например, 13:12)."""
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    with app.app_context():
        target_date = (datetime.now() + timedelta(days=1)).replace(hour=13, minute=12, second=0, microsecond=0)
        slot = ScheduleSlot(doctor_id=init_data['doctor_id'], day_of_week=target_date.weekday(), start_time=time(9, 0),
                            end_time=time(17, 0))
        db.session.add(slot)
        db.session.commit()

    response = client.post('/appointments/add', data={
        'patient_id': init_data['patient_id'],
        'doctor_id': init_data['doctor_id'],
        'slot_datetime': target_date.strftime('%Y-%m-%dT%H:%M')
    }, follow_redirects=True)

    assert 'не кратно 30 минутам' in response.text or 'не входит в рабочие часы' in response.text


# ==========================================
# 3. ДОСТУП К МУЛЬТИМЕДИА (СНИМКИ И АУДИО)
# ==========================================

def test_patient_cannot_upload_image(app, client, init_data):
    """Тест: Пациент не может загружать снимки."""
    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})

    data = {'image': (io.BytesIO(b"fake image data"), 'test.png')}
    response = client.post(f'/patients/{init_data["patient_id"]}/upload_image',
                           data=data, content_type='multipart/form-data', follow_redirects=True)

    assert 'Только медицинский персонал может загружать снимки' in response.text


def test_doctor_cannot_upload_audio_to_foreign_appointment(app, client, init_data):
    """Тест: Врач не может записать аудио к чужому приёму."""
    with app.app_context():
        doc2_user = User(username='doc2_test', role='doctor')
        doc2_user.set_password('pass')
        doctor2 = Doctor(first_name='Мария', last_name='Сидорова', user=doc2_user)
        db.session.add(doc2_user)
        db.session.add(doctor2)
        db.session.commit()

        appt = Appointment(patient_id=init_data['patient_id'], doctor_id=doctor2.id,
                           date=datetime.now() + timedelta(days=1))
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'doc_test', 'password': 'pass', 'role': 'doctor'})
    data = {'audio': (io.BytesIO(b"fake audio"), 'test.webm')}
    response = client.post(f'/appointments/{appt_id}/upload_audio',
                           data=data, content_type='multipart/form-data')

    assert response.status_code == 403
    assert response.get_json()['success'] is False


# ==========================================
# 4. ОТМЕНА ОСВОБОЖДАЕТ СЛОТ
# ==========================================

def test_cancellation_frees_the_slot(app, client, init_data):
    """Тест: После отмены приёма на это время можно записаться снова."""
    with app.app_context():
        target_date = (datetime.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        slot = ScheduleSlot(doctor_id=init_data['doctor_id'], day_of_week=target_date.weekday(), start_time=time(9, 0),
                            end_time=time(17, 0))
        db.session.add(slot)

        appt = Appointment(patient_id=init_data['patient_id'], doctor_id=init_data['doctor_id'], date=target_date,
                           status='scheduled')
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})
    client.post(f'/appointments/{appt_id}/cancel')

    with app.app_context():
        from app import is_slot_available
        available, msg = is_slot_available(init_data['doctor_id'], target_date)
        assert available is True
        assert msg == "OK"


# ==========================================
# 5. ОПЛАТА (БЕЗОПАСНОСТЬ И ЛОГИКА)
# ==========================================

def test_cannot_pay_for_cancelled_appointment(app, client, init_data):
    """Тест: Нельзя оплатить отменённый приём."""
    with app.app_context():
        appt = Appointment(
            patient_id=init_data['patient_id'],
            doctor_id=init_data['doctor_id'],
            date=datetime.now() + timedelta(days=1),
            status='cancelled'
        )
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})
    response = client.post(f'/appointments/{appt_id}/pay')

    assert response.status_code == 400
    assert 'Нельзя оплатить отмененный прием' in response.get_json()['message']


def test_cannot_pay_for_someone_elses_appointment(app, client, init_data):
    """Тест: Пациент не может оплатить чужой приём."""
    with app.app_context():
        pat2_user = User(username='pat2_test', role='patient')
        pat2_user.set_password('pass')
        pat2 = Patient(first_name='Петр', last_name='Петров', user=pat2_user)
        db.session.add(pat2_user)
        db.session.add(pat2)
        db.session.commit()

        appt = Appointment(patient_id=pat2.id, doctor_id=init_data['doctor_id'],
                           date=datetime.now() + timedelta(days=1))
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})
    response = client.post(f'/appointments/{appt_id}/pay')

    assert response.status_code == 403


# ==========================================
# 6. РАСПИСАНИЕ И ВАЛИДАЦИЯ
# ==========================================

def test_cannot_create_overlapping_slots(app, client, init_data):
    """Тест: Нельзя создать слот, который пересекается с существующим."""
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    client.post(f'/doctor/{init_data["doctor_id"]}/schedule', data={
        'day_of_week': '0', 'start_time': '09:00', 'end_time': '12:00'
    })

    response = client.post(f'/doctor/{init_data["doctor_id"]}/schedule', data={
        'day_of_week': '0', 'start_time': '10:00', 'end_time': '14:00'
    }, follow_redirects=True)

    assert 'Этот слот пересекается с уже существующим расписанием' in response.text


def test_patient_phone_validation(app, client, init_data):
    """Тест: Нельзя создать пациента с коротким номером телефона."""
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    response = client.post('/patients/new', data={
        'first_name': 'Тест',
        'last_name': 'Тестов',
        'dob': '1990-01-01',
        'phone': '123',
        'email': 'test_valid@mail.ru',
        'notes': ''
    }, follow_redirects=True)

    assert 'Телефон должен содержать минимум 10 цифр' in response.text


# ==========================================
# 7. ПОИСК И ПАГИНАЦИЯ
# ==========================================

def test_patients_search_and_pagination(app, client, init_data):
    """Тест: Поиск по фамилии и пагинация в списке пациентов."""
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    with app.app_context():
        for i in range(12):
            u = User(username=f'user{i}@test.ru', role='patient')
            u.set_password('pass')
            p = Patient(first_name='Поиск', last_name=f'Тестов_{i}', user=u)
            db.session.add(u)
            db.session.add(p)
        db.session.commit()

    response_search = client.get('/patients?search=Тестов_5')
    assert 'Тестов_5' in response_search.text
    assert 'Тестов_0' not in response_search.text

    response_page2 = client.get('/patients?page=2')
    assert response_page2.status_code == 200
    assert 'page=2' in response_page2.text or 'Вперед' in response_page2.text