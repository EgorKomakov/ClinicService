import re
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from config import Config
from models import User, Patient, Doctor, Appointment, ScheduleSlot
from extensions import db
import random
import string

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def generate_temp_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def is_slot_available(doctor_id, date_time, exclude_appointment_id=None):
    dt_end = date_time + timedelta(minutes=30)
    day_of_week = date_time.weekday()

    slots = ScheduleSlot.query.filter_by(doctor_id=doctor_id, day_of_week=day_of_week).all()
    if not slots:
        return False, "В этот день врач не принимает."

    t = date_time.time()
    e = dt_end.time()
    in_slot = any(slot.start_time <= t and slot.end_time >= e for slot in slots)
    if not in_slot:
        return False, "Выбранное время не входит в рабочие часы врача."

    overlapping = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.date < dt_end,
        Appointment.date >= date_time
    )
    if exclude_appointment_id:
        overlapping = overlapping.filter(Appointment.id != exclude_appointment_id)
    if overlapping.first():
        return False, "На это время уже есть запись."

    return True, "OK"


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip().lower()

        user = User.query.filter_by(username=username, role=role).first()
        if not user:
            flash('Пользователь не найден или неверная роль.', 'danger')
            return render_template('login.html')
        if not user.check_password(password):
            flash('Неверный пароль.', 'danger')
            return render_template('login.html')

        login_user(user)
        flash(f'Добро пожаловать, {user.username}!', 'success')

        if user.role == 'admin':
            return redirect(url_for('patients_list'))
        elif user.role == 'doctor':
            return redirect(url_for('appointments_list'))
        elif user.role == 'patient':
            if user.patient:
                return redirect(url_for('patient_detail', patient_id=user.patient.id))
            else:
                return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы успешно вышли из системы.", "info")
    return redirect(url_for('login'))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return render_template('index.html')
    return redirect(url_for('login'))


@app.route('/patients')
@login_required
def patients_list():
    if current_user.role not in ('admin', 'doctor'):
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))
    patients = Patient.query.order_by(Patient.last_name).all()
    return render_template('patients_list.html', patients=patients)


@app.route('/patients/new', methods=['GET', 'POST'])
@login_required
def patient_create():
    if current_user.role != 'admin':
        flash('Только администратор может добавлять пациентов.', 'danger')
        return redirect(url_for('patients_list'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        dob_raw = request.form.get('dob')
        notes = request.form.get('notes', '').strip()

        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{1,50}", first_name):
            flash('Имя должно содержать только буквы или дефис (до 50 символов).', 'danger')
            return render_template('patient_form.html', patient=None)

        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{1,50}", last_name):
            flash('Фамилия должна содержать только буквы или дефис (до 50 символов).', 'danger')
            return render_template('patient_form.html', patient=None)

        if not email or '@' not in email or '.' not in email:
            flash('Введите корректный email.', 'danger')
            return render_template('patient_form.html', patient=None)

        if User.query.filter_by(username=email).first():
            flash('Пользователь с таким email уже существует.', 'danger')
            return render_template('patient_form.html', patient=None)

        if not phone:
            flash('Телефон обязателен.', 'danger')
            return render_template('patient_form.html', patient=None)
        clean_phone = re.sub(r'[^\d]', '', phone)
        if len(clean_phone) < 10:
            flash('Телефон должен содержать минимум 10 цифр.', 'danger')
            return render_template('patient_form.html', patient=None)

        if not dob_raw:
            flash('Дата рождения обязательна.', 'danger')
            return render_template('patient_form.html', patient=None)
        try:
            dob = datetime.strptime(dob_raw, '%Y-%m-%d').date()
            if dob > date.today():
                flash('Дата рождения не может быть в будущем.', 'danger')
                return render_template('patient_form.html', patient=None)
        except ValueError:
            flash('Неверный формат даты рождения. Используйте YYYY-MM-DD.', 'danger')
            return render_template('patient_form.html', patient=None)

        temp_password = generate_temp_password()
        user = User(username=email, role='patient')
        user.set_password(temp_password)
        db.session.add(user)
        db.session.commit()

        new_patient = Patient(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            birth_date=dob,
            notes=notes,
            user_id=user.id
        )
        db.session.add(new_patient)
        db.session.commit()

        flash(f'Пациент добавлен. Временный пароль: {temp_password}', 'success')
        return redirect(url_for('patients_list'))

    return render_template('patient_form.html', patient=None)


@app.route('/patients/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def patient_edit(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if current_user.role != 'admin':
        flash('Редактирование карточки пациента доступно только администратору.', 'danger')
        return redirect(url_for('patient_detail', patient_id=patient.id))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        dob_raw = request.form.get('dob')
        notes = request.form.get('notes', '').strip()

        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{1,50}", first_name):
            flash('Имя должно содержать только буквы или дефис (до 50 символов).', 'danger')
            return render_template('patient_form.html', patient=patient)

        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{1,50}", last_name):
            flash('Фамилия должна содержать только буквы или дефис (до 50 символов).', 'danger')
            return render_template('patient_form.html', patient=patient)

        if not email or '@' not in email or '.' not in email:
            flash('Введите корректный email.', 'danger')
            return render_template('patient_form.html', patient=patient)

        existing_user = User.query.filter(User.username == email, User.id != patient.user_id).first()
        if existing_user:
            flash('Пользователь с таким email уже существует.', 'danger')
            return render_template('patient_form.html', patient=patient)

        if not phone:
            flash('Телефон обязателен.', 'danger')
            return render_template('patient_form.html', patient=patient)
        clean_phone = re.sub(r'[^\d]', '', phone)
        if len(clean_phone) < 10:
            flash('Телефон должен содержать минимум 10 цифр.', 'danger')
            return render_template('patient_form.html', patient=patient)

        if not dob_raw:
            flash('Дата рождения обязательна.', 'danger')
            return render_template('patient_form.html', patient=patient)
        try:
            new_dob = datetime.strptime(dob_raw, '%Y-%m-%d').date()
            if new_dob > date.today():
                flash('Дата рождения не может быть в будущем.', 'danger')
                return render_template('patient_form.html', patient=patient)
            patient.birth_date = new_dob
        except ValueError:
            flash('Неверный формат даты рождения. Используйте YYYY-MM-DD.', 'danger')
            return render_template('patient_form.html', patient=patient)

        patient.first_name = first_name
        patient.last_name = last_name
        patient.phone = phone
        patient.email = email
        patient.notes = notes
        if patient.user:
            patient.user.username = email

        db.session.commit()
        flash('Данные пациента обновлены.', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))

    return render_template('patient_form.html', patient=patient)


@app.route('/patients/<int:patient_id>/delete', methods=['POST'])
@login_required
def patient_delete(patient_id):
    if current_user.role != 'admin':
        flash('Только администратор может удалять пациентов.', 'danger')
        return redirect(url_for('patients_list'))

    patient = Patient.query.get_or_404(patient_id)
    user = patient.user
    db.session.delete(patient)
    if user:
        db.session.delete(user)
    db.session.commit()
    flash('Пациент и его учётная запись удалены.', 'success')
    return redirect(url_for('patients_list'))


@app.route('/patients/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if current_user.role == 'patient' and current_user.patient.id != patient.id:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for('index'))
    return render_template('patient_detail.html', patient=patient)


@app.route('/doctors')
@login_required
def doctors_list():
    doctors = Doctor.query.all()
    return render_template('doctors_list.html', doctors=doctors)


@app.route('/appointments')
@login_required
def appointments_list():
    if current_user.role == 'admin':
        appointments = Appointment.query.order_by(Appointment.date.desc()).all()
    elif current_user.role == 'doctor':
        appointments = Appointment.query.filter_by(doctor_id=current_user.doctor.id).order_by(Appointment.date.desc()).all()
    elif current_user.role == 'patient':
        appointments = Appointment.query.filter_by(patient_id=current_user.patient.id).order_by(Appointment.date.desc()).all()
    else:
        appointments = []
    return render_template('appointments_list.html', appointments=appointments)


@app.route('/appointments/add', methods=['GET', 'POST'])
@login_required
def add_appointment():
    if current_user.role == 'patient':
        if not current_user.patient:
            flash("У вас нет карточки пациента.", "warning")
            return redirect(url_for('index'))

        doctor_id = request.args.get('doctor_id') or request.form.get('doctor_id')
        if not doctor_id:
            flash("Выберите врача из списка.", "danger")
            return redirect(url_for('doctors_list'))
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            flash("Врач не найден.", "danger")
            return redirect(url_for('doctors_list'))

        if request.method == 'POST':
            slot_str = request.form.get('slot_datetime')
            notes = request.form.get('notes', '').strip()
            if not slot_str:
                flash("Выберите время приёма.", "danger")
                return redirect(url_for('add_appointment', doctor_id=doctor.id))
            try:
                dt = datetime.strptime(slot_str, '%Y-%m-%dT%H:%M')
                if dt < datetime.now():
                    flash("Нельзя записаться на прошедшее время.", "danger")
                    return redirect(url_for('add_appointment', doctor_id=doctor.id))
            except ValueError:
                flash("Некорректный формат времени.", "danger")
                return redirect(url_for('add_appointment', doctor_id=doctor.id))

            available, msg = is_slot_available(doctor.id, dt)
            if not available:
                flash(msg, 'danger')
                return redirect(url_for('add_appointment', doctor_id=doctor.id))

            new_app = Appointment(
                patient_id=current_user.patient.id,
                doctor_id=doctor.id,
                date=dt,
                notes=notes
            )
            db.session.add(new_app)
            db.session.commit()
            flash('Вы успешно записались на приём.', 'success')
            return redirect(url_for('my_appointments'))

        available_slots = []
        today = datetime.now().date()
        for offset in range(14):
            day = today + timedelta(days=offset)
            dow = day.weekday()
            slots = ScheduleSlot.query.filter_by(doctor_id=doctor.id, day_of_week=dow).all()
            for slot in slots:
                start_dt = datetime.combine(day, slot.start_time)
                end_dt = datetime.combine(day, slot.end_time)
                current = start_dt
                while current + timedelta(minutes=30) <= end_dt:
                    if current > datetime.now():
                        conflict = Appointment.query.filter_by(doctor_id=doctor.id, date=current).first()
                        if not conflict:
                            available_slots.append(current)
                    current += timedelta(minutes=30)

        return render_template('appointment_form.html',
                               doctor=doctor,
                               available_slots=available_slots,
                               for_patient=True)

    if current_user.role != 'admin':
        flash("Только администратор может добавлять приёмы.", "danger")
        return redirect(url_for('appointments_list'))

    patients = Patient.query.all()
    doctors = Doctor.query.all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        date_str = request.form.get('date', '').strip()
        notes = request.form.get('notes', '').strip()

        if not patient_id or not doctor_id or not date_str:
            flash("Все обязательные поля должны быть заполнены!", "danger")
            return redirect(request.url)

        patient = Patient.query.get(patient_id)
        doctor = Doctor.query.get(doctor_id)
        if not patient or not doctor:
            flash("Пациент или врач не найден!", "danger")
            return redirect(request.url)

        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
            if date < datetime.now():
                flash("Дата приёма не может быть в прошлом!", "danger")
                return redirect(request.url)
        except ValueError:
            flash("Некорректный формат даты!", "danger")
            return redirect(request.url)

        available, msg = is_slot_available(doctor.id, date)
        if not available:
            flash(msg, 'danger')
            return redirect(request.url)

        new_appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            date=date,
            notes=notes
        )
        db.session.add(new_appointment)
        db.session.commit()
        flash('Приём успешно добавлен.', 'success')
        return redirect(url_for('appointments_list'))

    return render_template('appointment_form.html',
                           patients=patients,
                           doctors=doctors,
                           appointment=None,
                           for_patient=False)


@app.route('/appointments/<int:appointment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if current_user.role != 'admin':
        flash("Недостаточно прав для редактирования/удаления приёма.", "danger")
        return redirect(url_for('appointments_list'))

    patients = Patient.query.all()
    doctors = Doctor.query.all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        date_str = request.form.get('date', '').strip()
        notes = request.form.get('notes', '').strip()

        if not patient_id or not doctor_id or not date_str:
            flash("Все обязательные поля должны быть заполнены!", "danger")
            return redirect(request.url)

        patient = Patient.query.get(patient_id)
        doctor = Doctor.query.get(doctor_id)
        if not patient or not doctor:
            flash("Пациент или врач не найден!", "danger")
            return redirect(request.url)

        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
            if date < datetime.now():
                flash("Дата приёма не может быть в прошлом!", "danger")
                return redirect(request.url)
        except ValueError:
            flash("Некорректный формат даты!", "danger")
            return redirect(request.url)

        available, msg = is_slot_available(doctor.id, date, exclude_appointment_id=appointment.id)
        if not available:
            flash(msg, 'danger')
            return redirect(request.url)

        appointment.patient_id = patient.id
        appointment.doctor_id = doctor.id
        appointment.date = date
        appointment.notes = notes
        db.session.commit()
        flash("Приём обновлён.", "success")
        return redirect(url_for('appointments_list'))

    return render_template('appointment_form.html',
                           appointment=appointment,
                           patients=patients,
                           doctors=doctors)


@app.route('/appointments/<int:appointment_id>/delete', methods=['POST'])
@login_required
def delete_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if current_user.role != 'admin':
        flash("Недостаточно прав для редактирования/удаления приёма.", "danger")
        return redirect(url_for('appointments_list'))
    db.session.delete(appointment)
    db.session.commit()
    flash('Приём удалён.', 'info')
    return redirect(url_for('appointments_list'))


@app.route('/appointments/<int:appointment_id>')
@login_required
def view_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if current_user.role == 'patient':
        if not current_user.patient or current_user.patient.id != appointment.patient_id:
            flash('У вас нет прав для просмотра этого приёма.', 'danger')
            return redirect(url_for('appointments_list'))
    return render_template('appointment_detail.html', appointment=appointment)


@app.route('/my_appointments')
@login_required
def my_appointments():
    if current_user.role == 'patient':
        patient = current_user.patient
        if not patient:
            flash("У этого пользователя нет карточки пациента.", "warning")
            return redirect(url_for('patients_list'))
        appointments = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.date).all()
        return render_template('appointments_list.html', appointments=appointments)
    elif current_user.role == 'doctor':
        doctor = current_user.doctor
        if not doctor:
            flash("У этого пользователя нет карточки врача.", "warning")
            return redirect(url_for('doctors_list'))
        appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(Appointment.date).all()
        return render_template('appointments_list.html', appointments=appointments)
    elif current_user.role == 'admin':
        appointments = Appointment.query.order_by(Appointment.date).all()
        return render_template('appointments_list.html', appointments=appointments)
    else:
        flash("Роль пользователя не определена.", "danger")
        return redirect(url_for('login'))


@app.route('/my_schedule')
@login_required
def my_schedule():
    if current_user.role != 'doctor':
        flash('Только врач может просматривать своё расписание.', 'danger')
        return redirect(url_for('index'))
    doctor = current_user.doctor
    if not doctor:
        flash('У вас нет карточки врача.', 'warning')
        return redirect(url_for('index'))

    slots = ScheduleSlot.query.filter_by(doctor_id=doctor.id)\
        .order_by(ScheduleSlot.day_of_week, ScheduleSlot.start_time).all()
    return render_template('schedule.html', slots=slots, editable=False, doctor=doctor)


@app.route('/doctor/<int:doctor_id>/schedule', methods=['GET', 'POST'])
@login_required
def doctor_schedule(doctor_id):
    if current_user.role != 'admin':
        flash('Только администратор может управлять расписанием.', 'danger')
        return redirect(url_for('index'))
    doctor = Doctor.query.get_or_404(doctor_id)

    if request.method == 'POST':
        day = int(request.form.get('day_of_week'))
        start_str = request.form.get('start_time')
        end_str = request.form.get('end_time')
        if not start_str or not end_str:
            flash('Укажите время начала и окончания.', 'danger')
            return redirect(request.url)
        try:
            start_time = datetime.strptime(start_str, '%H:%M').time()
            end_time = datetime.strptime(end_str, '%H:%M').time()
            if start_time >= end_time:
                flash('Время начала должно быть раньше окончания.', 'danger')
                return redirect(request.url)
        except ValueError:
            flash('Неверный формат времени.', 'danger')
            return redirect(request.url)

        slot = ScheduleSlot(doctor_id=doctor.id, day_of_week=day,
                            start_time=start_time, end_time=end_time)
        db.session.add(slot)
        db.session.commit()
        flash('Слот добавлен.', 'success')
        return redirect(url_for('doctor_schedule', doctor_id=doctor.id))

    slots = ScheduleSlot.query.filter_by(doctor_id=doctor.id)\
        .order_by(ScheduleSlot.day_of_week, ScheduleSlot.start_time).all()
    return render_template('schedule.html', slots=slots, editable=True, doctor=doctor)


@app.route('/delete_slot/<int:slot_id>', methods=['POST'])
@login_required
def delete_slot(slot_id):
    if current_user.role != 'admin':
        flash('Только администратор может удалять слоты.', 'danger')
        return redirect(url_for('index'))
    slot = ScheduleSlot.query.get_or_404(slot_id)
    doctor_id = slot.doctor_id
    db.session.delete(slot)
    db.session.commit()
    flash('Слот удалён.', 'info')
    return redirect(url_for('doctor_schedule', doctor_id=doctor_id))


@app.route('/contacts', methods=['GET', 'POST'])
def contacts():
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify(success=False, message='Неверный запрос'), 400
        print(f"Новое сообщение от {data.get('fullname')}: {data.get('email')}, {data.get('phone')}, {data.get('message')}")
        return jsonify(success=True, message='Сообщение отправлено!', data=data)
    return render_template('contacts.html')


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)