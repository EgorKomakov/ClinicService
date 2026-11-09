import pytest
from models import Feedback
from extensions import db


def test_contact_form_saves_to_db(app, client):
    """Тест: Форма обратной связи сохраняет данные в БД."""
    response = client.post('/contacts', json={
        'fullname': 'Иван Иванов',
        'phone': '+79991234567',
        'email': 'test@mail.ru',
        'message': 'Тестовое сообщение'
    })

    assert response.status_code == 200
    assert response.get_json()['success'] is True

    with app.app_context():
        feedback = Feedback.query.first()
        assert feedback is not None
        assert feedback.fullname == 'Иван Иванов'
        assert feedback.email == 'test@mail.ru'
        assert feedback.is_read is False


def test_patient_cannot_access_feedbacks(app, client, init_data):
    """Тест: Пациент не может зайти в раздел обращений."""
    client.post('/login', data={'username': 'pat_test', 'password': 'pass', 'role': 'patient'})
    response = client.get('/feedbacks')

    assert response.status_code == 302