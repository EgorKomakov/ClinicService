import pytest
from models import Appointment, Patient, Doctor, User, AssignedProcedure
from datetime import datetime, timedelta
from extensions import db


# ==========================================
# 1. ТЕСТЫ БЕЗОПАСНОСТИ (Права доступа)
# ==========================================

def test_patient_cannot_access_admin_panel(auth_client, init_data):
    """Тест: Пациент не может зайти в раздел управления пациентами."""
    auth_client.login('pat_test', 'pass', 'patient')
    response = auth_client.client.get('/patients')

    assert response.status_code == 302
    assert response.location in ('/', 'http://localhost/')


def test_doctor_cannot_see_other_doctor_appointments(app, client, init_data):
    """Тест: Врач не может просмотреть карточку приема другого врача."""
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

    response = client.get(f'/appointments/{appt_id}', follow_redirects=True)

    assert response.status_code == 200
    assert 'Вы не можете просматривать приёмы других врачей' in response.text


# ==========================================
# 2. ТЕСТЫ БИЗНЕС-ЛОГИКИ (Геймификация)
# ==========================================

def test_gamification_points_on_completed(app, client, init_data):
    """Тест: За завершенный прием начисляется 20 XP и защита от повторного изменения."""
    with app.app_context():
        pat = db.session.get(Patient, init_data['patient_id'])
        doc = db.session.get(Doctor, init_data['doctor_id'])
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, date=datetime.now() + timedelta(days=1),
                           status='scheduled')
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id
        pat_id = pat.id

    client.post('/login', data={'username': 'doc_test', 'password': 'pass', 'role': 'doctor'})

    client.post(f'/appointments/{appt_id}/set_status', data={'status': 'completed'})

    with app.app_context():
        patient = db.session.get(Patient, pat_id)
        assert patient.points == 20

        client.post(f'/appointments/{appt_id}/set_status', data={'status': 'no-show'})
        patient_after = db.session.get(Patient, pat_id)
        assert patient_after.points == 20


# ==========================================
# 3. ТЕСТЫ ВАЛИДАЦИИ (Запись на прием)
# ==========================================

def test_cannot_book_past_appointment(app, client, init_data):
    """Тест: Нельзя записаться на прошедшее время (через админа)."""
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    past_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')

    response = client.post('/appointments/add', data={
        'patient_id': init_data['patient_id'],
        'doctor_id': init_data['doctor_id'],
        'slot_datetime': past_date
    }, follow_redirects=True)

    assert 'Дата приёма не может быть в прошлом' in response.text


# ==========================================
# 4. ТЕСТЫ БИЛЛИНГА (Оплата)
# ==========================================

def test_payment_flow(app, client, init_data):
    """Тест: Пациент может оплатить прием, статус меняется на 'paid'."""
    with app.app_context():
        pat = db.session.get(Patient, init_data['patient_id'])
        doc = db.session.get(Doctor, init_data['doctor_id'])
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, date=datetime.now() + timedelta(days=1), price=1500.0)
        db.session.add(appt)
        db.session.commit()
        appt_id = appt.id

    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})

    response = client.post(f'/appointments/{appt_id}/pay')
    data = response.get_json()

    assert data['success'] is True

    with app.app_context():
        updated_appt = db.session.get(Appointment, appt_id)
        assert updated_appt.payment_status == 'paid'

    response_again = client.post(f'/appointments/{appt_id}/pay')
    assert response_again.status_code == 400