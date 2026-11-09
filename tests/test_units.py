import pytest
from datetime import time
from models import Patient, Doctor, ScheduleSlot, User
from app import allowed_file, generate_temp_password


# ==========================================
# 1. ТЕСТЫ МОДЕЛЕЙ (Логика и математика)
# ==========================================

def test_patient_full_name():
    """Юнит-тест: Формирование полного имени пациента."""
    p = Patient(first_name="Иван", last_name="Иванов")
    assert p.full_name() == "Иван Иванов"

    p2 = Patient(first_name="Анна-Мария", last_name="Петрова")
    assert p2.full_name() == "Анна-Мария Петрова"


def test_doctor_full_name():
    """Юнит-тест: Формирование полного имени врача."""
    d = Doctor(first_name="Петр", last_name="Сидоров")
    assert d.full_name() == "Петр Сидоров"


@pytest.mark.parametrize("points, level, expected_percentage, expected_current", [
    (0, 1, 0, 0),
    (25, 1, 50, 25),
    (49, 1, 98, 49),
    (50, 2, 0, 0),
    (75, 2, 50, 25),
    (100, 3, 0, 0),
    (120, 3, 40, 20),
])
def test_patient_level_progress(points, level, expected_percentage, expected_current):
    """Юнит-тест: Математика расчета прогресс-бара (параметризованный)."""
    p = Patient(points=points, level=level)
    progress = p.get_level_progress()

    assert progress['percentage'] == expected_percentage
    assert progress['current_points'] == expected_current
    assert progress['needed_points'] == 50


def test_user_password_hashing():
    """Юнит-тест: Хеширование и проверка пароля."""
    user = User(username="test_user", role="patient")
    user.set_password("SuperSecret123")

    assert user.password_hash != "SuperSecret123"
    assert len(user.password_hash) > 20

    assert user.check_password("SuperSecret123") is True
    assert user.check_password("WrongPassword") is False


def test_schedule_slot_repr():
    """Юнит-тест: Строковое представление слота расписания."""
    slot = ScheduleSlot(day_of_week=0, start_time=time(9, 0), end_time=time(17, 30))
    assert repr(slot) == "Пн 09:00-17:30"

    slot2 = ScheduleSlot(day_of_week=6, start_time=time(10, 15), end_time=time(14, 0))
    assert repr(slot2) == "Вс 10:15-14:00"


# ==========================================
# 2. ТЕСТЫ ХЕЛПЕРОВ (Валидация файлов и пароли)
# ==========================================

@pytest.mark.parametrize("filename, expected", [
    ("photo.jpg", True),
    ("scan.PNG", True),
    ("xray.jpeg", True),
    ("document.pdf", True),
    ("audio.webm", True),
    ("track.mp3", True),
    ("virus.exe", False),
    ("script.js", False),
    ("no_extension", False),
    ("", False),
    (".hidden", False),
])
def test_allowed_file(filename, expected):
    """Юнит-тест: Валидация расширений файлов (параметризованный)."""
    assert allowed_file(filename) == expected


def test_generate_temp_password():
    """Юнит-тест: Генерация временного пароля."""
    p1 = generate_temp_password()
    p2 = generate_temp_password()
    assert p1 != p2
    assert len(p1) == 8
    p3 = generate_temp_password(length=12)
    assert len(p3) == 12
    assert p1.isalnum() is True