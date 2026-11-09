import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import pytest
from app import app as flask_app
from extensions import db
from models import User, Doctor, Patient, Appointment, Service, AssignedProcedure, Feedback
from datetime import datetime, timedelta


@pytest.fixture(scope='session')
def app():
    """Настройка тестового приложения."""
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret"
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


@pytest.fixture(scope='function')
def init_data(app):
    """Создает базовых пользователей и данные для тестов."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(username='admin_test', role='admin')
        admin.set_password('pass')
        db.session.add(admin)

        doc_user = User(username='doc_test', role='doctor')
        doc_user.set_password('pass')
        doctor = Doctor(first_name='Иван', last_name='Петров', user=doc_user)
        db.session.add(doc_user)
        db.session.add(doctor)

        pat_user = User(username='pat_test', role='patient')
        pat_user.set_password('pass')
        patient = Patient(first_name='Иван', last_name='Иванов', user=pat_user, points=0, level=1)
        db.session.add(pat_user)
        db.session.add(patient)

        service = Service(name='Тестовая услуга', price=1000.0)
        db.session.add(service)

        db.session.commit()

        return {
            'admin_id': admin.id,
            'doctor_id': doctor.id,
            'patient_id': patient.id,
            'service_id': service.id
        }


@pytest.fixture(scope='function')
def auth_client(client):
    class AuthActions:
        def __init__(self, client):
            self.client = client

        def login(self, username, password, role):
            return self.client.post('/login', data={
                'username': username,
                'password': password,
                'role': role
            }, follow_redirects=True)

        def logout(self):
            return self.client.get('/logout', follow_redirects=True)

    return AuthActions(client)