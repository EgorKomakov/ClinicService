# ==========================================
# 1. ИМПОРТЫ И НАСТРОЙКА ПРИЛОЖЕНИЯ
# ==========================================

import os
import re
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from config import Config
from models import User, Patient, Doctor, Appointment, ScheduleSlot, MedicalImage, PatientAchievement, Service, AssignedProcedure, Feedback
from extensions import db
import random
import string

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И МЕНЕДЖЕРА АВТОРИЗАЦИИ
# ==========================================

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (HELPERS)
# ==========================================

def generate_temp_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def add_points(patient_id, points_amount, reason=""):
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return

    patient.points += points_amount

    new_level = (patient.points // 50) + 1
    if new_level > patient.level:
        patient.level = new_level

    check_achievements(patient)
    db.session.commit()


def check_achievements(patient):
    existing = [a.name for a in patient.achievements]
    completed_apps = [app for app in patient.appointments if app.status == 'completed']

    if "Первый шаг" not in existing and len(completed_apps) >= 1:
        db.session.add(PatientAchievement(patient_id=patient.id, name="Первый шаг",
                                          description="Успешно посетил первый прием", icon="award"))

    if "Медкарта в порядке" not in existing and len(patient.images) >= 3:
        db.session.add(PatientAchievement(patient_id=patient.id, name="Медкарта в порядке",
                                          description="В карте собрано 3 и более снимка", icon="file-earmark-medical"))

    if "Дисциплинированный" not in existing and len(completed_apps) >= 3:
        db.session.add(PatientAchievement(patient_id=patient.id, name="Дисциплинированный",
                                          description="Посетил 3 приема", icon="calendar-check"))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def is_slot_available(doctor_id, date_time, exclude_appointment_id=None):
    dt_end = date_time + timedelta(minutes=30)
    day_of_week = date_time.weekday()

    slots = ScheduleSlot.query.filter_by(doctor_id=doctor_id, day_of_week=day_of_week).all()
    if not slots:
        return False, "В этот день врач не принимает."

    t = date_time.time()
    e = dt_end.time()

    in_slot = False
    for slot in slots:
        if slot.start_time <= t and slot.end_time >= e:
            start_minutes = slot.start_time.hour * 60 + slot.start_time.minute
            current_minutes = date_time.hour * 60 + date_time.minute
            if (current_minutes - start_minutes) % 30 == 0:
                in_slot = True
                break

    if not in_slot:
        return False, "Выбранное время не входит в рабочие часы врача или не кратно 30 минутам."

    overlapping = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status != 'cancelled',
        Appointment.date < dt_end,
        Appointment.date >= date_time
    )
    if exclude_appointment_id:
        overlapping = overlapping.filter(Appointment.id != exclude_appointment_id)
    if overlapping.first():
        return False, "На это время уже есть запись."

    return True, "OK"

# ==========================================
# 4. АУТЕНТИФИКАЦИЯ (ВХОД / ВЫХОД)
# ==========================================

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

# ==========================================
# 5. ГЛАВНАЯ СТРАНИЦА (ДАШБОРД)
# ==========================================

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return render_template('index.html')

    context = {}

    if current_user.role == 'patient':
        if current_user.patient:
            next_app = Appointment.query.filter_by(
                patient_id=current_user.patient.id,
                status='scheduled'
            ).filter(Appointment.date >= datetime.now()).order_by(Appointment.date).first()
            context['next_app'] = next_app

    elif current_user.role == 'doctor':
        if current_user.doctor:
            today = date.today()
            today_apps = Appointment.query.filter_by(
                doctor_id=current_user.doctor.id
            ).filter(db.func.date(Appointment.date) == today).order_by(Appointment.date).all()
            context['today_apps'] = today_apps

    elif current_user.role == 'admin':
        context['total_patients'] = Patient.query.count()
        context['total_doctors'] = Doctor.query.count()
        context['total_apps'] = Appointment.query.count()
        context['pending_apps'] = Appointment.query.filter_by(status='scheduled').count()

    return render_template('index.html', **context)

# ==========================================
# 6. УПРАВЛЕНИЕ ПАЦИЕНТАМИ (CRUD + RBAC)
# ==========================================

@app.route('/patients')
@login_required
def patients_list():
    if current_user.role not in ('admin', 'doctor'):
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    query = Patient.query

    if current_user.role == 'doctor':
        query = query.join(Appointment).filter(
            Appointment.doctor_id == current_user.doctor.id
        ).distinct()

    if search:
        query = query.filter(db.or_(
            Patient.first_name.ilike(f'%{search}%'),
            Patient.last_name.ilike(f'%{search}%')
        ))

    query = query.order_by(Patient.last_name)
    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template('patients_list.html', patients=pagination.items, pagination=pagination, search=search)

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
    patient = db.get_or_404(Patient, patient_id)
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

    patient = db.get_or_404(Patient, patient_id)
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
    patient = db.get_or_404(Patient, patient_id)

    if current_user.role == 'patient' and current_user.patient.id != patient.id:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for('index'))

    if current_user.role == 'doctor':
        has_access = Appointment.query.filter_by(
            doctor_id=current_user.doctor.id,
            patient_id=patient.id
        ).first()
        if not has_access:
            flash("У вас нет доступа к карточке этого пациента (нет общих приёмов).", "danger")
            return redirect(url_for('patients_list'))

    return render_template('patient_detail.html', patient=patient)

# ==========================================
# 8. СПРАВОЧНИК ВРАЧЕЙ
# ==========================================

@app.route('/doctors')
@login_required
def doctors_list():
    doctors = Doctor.query.all()
    return render_template('doctors_list.html', doctors=doctors)

# ==========================================
# 9. УПРАВЛЕНИЕ ПРИЁМАМИ (ЗАПИСЬ, ПРОСМОТР, ОТМЕНА)
# ==========================================

@app.route('/appointments')
@login_required
def appointments_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'all')

    query = Appointment.query

    if current_user.role == 'doctor':
        query = query.filter_by(doctor_id=current_user.doctor.id)
    elif current_user.role == 'patient':
        query = query.filter_by(patient_id=current_user.patient.id)

    if search:
        query = query.join(Patient).filter(
            db.or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%')
            )
        )

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    query = query.order_by(Appointment.date.desc())
    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template('appointments_list.html',
                           appointments=pagination.items,
                           pagination=pagination,
                           search=search,
                           status_filter=status_filter,
                           now=datetime.now(),
                           timedelta=timedelta)

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
        doctor = db.session.get(Doctor, doctor_id)
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

        grouped_slots = {}
        days_map = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
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
                            date_key = f"{current.strftime('%d.%m.%Y')} ({days_map[current.weekday()]})"
                            if date_key not in grouped_slots:
                                grouped_slots[date_key] = []
                            grouped_slots[date_key].append(current)
                    current += timedelta(minutes=30)

        return render_template('appointment_form.html',
                               doctor=doctor,
                               grouped_slots=grouped_slots,
                               for_patient=True)

    if current_user.role != 'admin':
        flash("Только администратор может добавлять приёмы.", "danger")
        return redirect(url_for('appointments_list'))

    patients = Patient.query.all()
    doctors = Doctor.query.all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        slot_str = request.form.get('slot_datetime')
        notes = request.form.get('notes', '').strip()

        if not patient_id or not doctor_id or not slot_str:
            flash("Все обязательные поля должны быть заполнены!", "danger")
            return redirect(request.url)

        patient = db.session.get(Patient, patient_id)
        doctor = db.session.get(Doctor, doctor_id)
        if not patient or not doctor:
            flash("Пациент или врач не найден!", "danger")
            return redirect(request.url)

        try:
            date = datetime.strptime(slot_str, '%Y-%m-%dT%H:%M')
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
    appointment = db.get_or_404(Appointment, appointment_id)
    if current_user.role != 'admin':
        flash("Недостаточно прав для редактирования/удаления приёма.", "danger")
        return redirect(url_for('appointments_list'))

    patients = Patient.query.all()
    doctors = Doctor.query.all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        slot_str = request.form.get('slot_datetime', '').strip()
        notes = request.form.get('notes', '').strip()

        if not patient_id or not doctor_id or not slot_str:
            flash("Все обязательные поля должны быть заполнены!", "danger")
            return redirect(request.url)

        patient = db.session.get(Patient, patient_id)
        doctor = db.session.get(Doctor, doctor_id)
        if not patient or not doctor:
            flash("Пациент или врач не найден!", "danger")
            return redirect(request.url)

        try:
            date = datetime.strptime(slot_str, '%Y-%m-%dT%H:%M')
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
    appointment = db.get_or_404(Appointment, appointment_id)
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
    appointment = db.get_or_404(Appointment, appointment_id)

    if current_user.role == 'patient':
        if not current_user.patient or current_user.patient.id != appointment.patient_id:
            flash('У вас нет прав для просмотра этого приёма.', 'danger')
            return redirect(url_for('appointments_list'))

    if current_user.role == 'doctor':
        if appointment.doctor_id != current_user.doctor.id:
            flash('Вы не можете просматривать приёмы других врачей.', 'danger')
            return redirect(url_for('appointments_list'))

    services = Service.query.all()
    return render_template('appointment_detail.html',
                           appointment=appointment,
                           now=datetime.now(),
                           timedelta=timedelta,
                           services=services)

@app.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    if current_user.role != 'patient':
        flash('Только пациент может отменить свою запись.', 'danger')
        return redirect(url_for('index'))

    appointment = db.get_or_404(Appointment, appointment_id)

    if appointment.patient_id != current_user.patient.id:
        flash('Вы не можете отменить чужую запись.', 'danger')
        return redirect(url_for('appointments_list'))

    if appointment.status != 'scheduled':
        flash('Можно отменить только запланированный приём.', 'warning')
        return redirect(url_for('view_appointment', appointment_id=appointment.id))

    if appointment.date < datetime.now() + timedelta(hours=2):
        flash('Отмена невозможна: до приёма осталось менее 2 часов. Пожалуйста, свяжитесь с клиникой.', 'danger')
        return redirect(url_for('view_appointment', appointment_id=appointment.id))

    appointment.status = 'cancelled'
    db.session.commit()
    flash('Запись успешно отменена. Слот освобожден для других пациентов.', 'info')
    return redirect(url_for('appointments_list'))

@app.route('/appointments/<int:appointment_id>/set_status', methods=['POST'])
@login_required
def set_appointment_status(appointment_id):
    if current_user.role not in ('admin', 'doctor'):
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('appointments_list'))

    appointment = db.get_or_404(Appointment, appointment_id)

    if current_user.role == 'doctor' and appointment.doctor_id != current_user.doctor.id:
        flash('Вы не можете изменять статус чужих приёмов.', 'danger')
        return redirect(url_for('appointments_list'))

    new_status = request.form.get('status')

    if new_status not in ('completed', 'no-show'):
        flash('Неверный статус.', 'danger')
        return redirect(url_for('view_appointment', appointment_id=appointment.id))

    if appointment.status != 'scheduled':
        flash('Статус этого приема уже был зафиксирован. Изменения невозможны.', 'warning')
        return redirect(url_for('view_appointment', appointment_id=appointment.id))

    appointment.status = new_status
    db.session.commit()

    if new_status == 'completed':
        add_points(appointment.patient_id, 20, "Посещение врача")
        flash('Статус изменен на "Завершен". Пациенту начислено 20 XP!', 'success')
    elif new_status == 'no-show':
        patient = Patient.query.get(appointment.patient_id)
        patient.points = max(0, patient.points - 10)
        db.session.commit()
        flash('Статус изменен на "Неявка". С пациента списано 10 XP.', 'warning')

    return redirect(url_for('view_appointment', appointment_id=appointment.id))

@app.route('/my_appointments')
@login_required
def my_appointments():
    return redirect(url_for('appointments_list'))

# ==========================================
# 11. РАСПИСАНИЕ ВРАЧЕЙ
# ==========================================

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

    doctor = db.get_or_404(Doctor, doctor_id)

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

        overlapping_slots = ScheduleSlot.query.filter(
            ScheduleSlot.doctor_id == doctor.id,
            ScheduleSlot.day_of_week == day,
            ScheduleSlot.start_time < end_time,
            ScheduleSlot.end_time > start_time
        ).first()

        if overlapping_slots:
            flash('Этот слот пересекается с уже существующим расписанием врача.', 'danger')
            return redirect(request.url)

        slot = ScheduleSlot(doctor_id=doctor.id, day_of_week=day,
                            start_time=start_time, end_time=end_time)
        db.session.add(slot)
        db.session.commit()
        flash('Слот добавлен.', 'success')
        return redirect(url_for('doctor_schedule', doctor_id=doctor.id))

    slots = ScheduleSlot.query.filter_by(doctor_id=doctor.id) \
        .order_by(ScheduleSlot.day_of_week, ScheduleSlot.start_time).all()
    return render_template('schedule.html', slots=slots, editable=True, doctor=doctor)


@app.route('/delete_slot/<int:slot_id>', methods=['POST'])
@login_required
def delete_slot(slot_id):
    if current_user.role != 'admin':
        flash('Только администратор может удалять слоты.', 'danger')
        return redirect(url_for('index'))

    slot = db.get_or_404(ScheduleSlot, slot_id)
    doctor_id = slot.doctor_id

    future_appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status == 'scheduled',
        Appointment.date >= datetime.now()
    ).all()

    conflicting_appointments = []
    for appt in future_appointments:
        if appt.date.weekday() == slot.day_of_week:
            if slot.start_time <= appt.date.time() < slot.end_time:
                conflicting_appointments.append(appt)

    if conflicting_appointments:
        flash(
            f'Нельзя удалить слот: на это время уже записано {len(conflicting_appointments)} пациент(ов). Сначала перенесите или отмените эти приёмы.',
            'danger')
        return redirect(url_for('doctor_schedule', doctor_id=doctor_id))

    db.session.delete(slot)
    db.session.commit()
    flash('Слот успешно удалён.', 'info')
    return redirect(url_for('doctor_schedule', doctor_id=doctor_id))

# ==========================================
# 14. ПУБЛИЧНЫЕ СТРАНИЦЫ (ПРАЙС, КОНТАКТЫ, FAQ)
# ==========================================

@app.route('/contacts', methods=['GET', 'POST'])
def contacts():
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify(success=False, message='Неверный запрос'), 400

        try:
            new_feedback = Feedback(
                fullname=data.get('fullname'),
                phone=data.get('phone'),
                email=data.get('email'),
                message=data.get('message')
            )
            db.session.add(new_feedback)
            db.session.commit()
            return jsonify(success=True, message='Сообщение отправлено!', data=data)
        except Exception as e:
            db.session.rollback()
            return jsonify(success=False, message='Ошибка сервера при сохранении'), 500

    return render_template('contacts.html')


@app.route('/faq')
def faq():
    return render_template('faq.html')

# ==========================================
# 7. МЕДИЦИНСКИЕ СНИМКИ (МУЛЬТИМЕДИА)
# ==========================================

@app.route('/patients/<int:patient_id>/upload_image', methods=['POST'])
@login_required
def upload_image(patient_id):
    patient = db.get_or_404(Patient, patient_id)

    if current_user.role == 'patient':
        flash('Только медицинский персонал может загружать снимки.', 'danger')
        return redirect(url_for('patient_detail', patient_id=patient.id))

    if current_user.role == 'doctor':
        has_access = Appointment.query.filter_by(
            doctor_id=current_user.doctor.id,
            patient_id=patient.id
        ).first()
        if not has_access:
            flash('Вы не можете загружать снимки пациенту без общего приёма.', 'danger')
            return redirect(url_for('index'))

    if 'image' not in request.files:
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('patient_detail', patient_id=patient.id))

    file = request.files['image']
    if file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('patient_detail', patient_id=patient.id))

    if file and allowed_file(file.filename):
        original_name = file.filename
        ext = original_name.rsplit('.', 1)[1].lower()
        filename = f"{patient_id}_{int(datetime.now().timestamp())}.{ext}"

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        description = request.form.get('description', '').strip()
        new_image = MedicalImage(
            patient_id=patient.id,
            filename=filename,
            original_name=original_name,
            description=description
        )
        db.session.add(new_image)
        db.session.commit()

        flash('Снимок успешно загружен.', 'success')
    else:
        flash('Недопустимый формат файла. Разрешены: png, jpg, jpeg, gif.', 'danger')

    return redirect(url_for('patient_detail', patient_id=patient.id))


@app.route('/images/<int:image_id>/delete', methods=['POST'])
@login_required
def delete_image(image_id):
    image = db.get_or_404(MedicalImage, image_id)
    patient_id = image.patient_id

    if current_user.role == 'patient':
        flash('Только медицинский персонал может удалять снимки.', 'danger')
        return redirect(url_for('patient_detail', patient_id=patient_id))

    if current_user.role == 'doctor':
        has_access = Appointment.query.filter_by(
            doctor_id=current_user.doctor.id,
            patient_id=patient_id
        ).first()
        if not has_access:
            flash('Вы не можете удалять снимки пациента без общего приёма.', 'danger')
            return redirect(url_for('index'))

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    db.session.delete(image)
    db.session.commit()
    flash('Снимок удален.', 'info')
    return redirect(url_for('patient_detail', patient_id=patient_id))

# ==========================================
# 10. АУДИОЗАМЕТКИ ВРАЧА (МУЛЬТИМЕДИА)
# ==========================================

@app.route('/appointments/<int:appointment_id>/upload_audio', methods=['POST'])
@login_required
def upload_audio(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)

    if current_user.role not in ('admin', 'doctor'):
        return jsonify({'success': False, 'message': 'Доступ запрещён'}), 403

    if current_user.role == 'doctor' and appointment.doctor_id != current_user.doctor.id:
        return jsonify({'success': False, 'message': 'Вы не можете изменять чужие приёмы'}), 403

    if 'audio' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не найден'}), 400

    file = request.files['audio']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Пустой файл'}), 400

    if file:
        ext = 'webm'
        if file.filename and '.' in file.filename:
            ext = file.filename.rsplit('.', 1)[1].lower()
        elif file.content_type:
            if 'mp4' in file.content_type:
                ext = 'mp4'
            elif 'ogg' in file.content_type:
                ext = 'ogg'

        filename = f"appt_{appointment.id}_audio.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        if appointment.audio_filename and appointment.audio_filename != filename:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], appointment.audio_filename)
            if os.path.exists(old_path):
                os.remove(old_path)

        appointment.audio_filename = filename
        db.session.commit()

        return jsonify({'success': True, 'message': 'Аудио сохранено!', 'filename': filename})

    return jsonify({'success': False, 'message': 'Ошибка'}), 400


@app.route('/appointments/<int:appointment_id>/delete_audio', methods=['POST'])
@login_required
def delete_audio(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)

    if current_user.role not in ('admin', 'doctor'):
        return jsonify({'success': False}), 403

    if current_user.role == 'doctor' and appointment.doctor_id != current_user.doctor.id:
        return jsonify({'success': False, 'message': 'Вы не можете изменять чужие приёмы'}), 403

    if appointment.audio_filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], appointment.audio_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        appointment.audio_filename = None
        db.session.commit()

    return jsonify({'success': True})

# ==========================================
# 13. ВНУТРЕННЕЕ API ДЛЯ AJAX (СЛОТЫ)
# ==========================================

@app.route('/api/available_slots/<int:doctor_id>')
@login_required
def get_available_slots(doctor_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Доступ запрещён'}), 403

    exclude_id = request.args.get('exclude_appointment_id', type=int)

    grouped_slots = {}
    days_map = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    today = datetime.now().date()

    for offset in range(14):
        day = today + timedelta(days=offset)
        dow = day.weekday()
        slots = ScheduleSlot.query.filter_by(doctor_id=doctor_id, day_of_week=dow).all()

        for slot in slots:
            start_dt = datetime.combine(day, slot.start_time)
            end_dt = datetime.combine(day, slot.end_time)
            current = start_dt

            while current + timedelta(minutes=30) <= end_dt:
                if current > datetime.now():
                    conflict_query = Appointment.query.filter_by(doctor_id=doctor_id, date=current)
                    if exclude_id:
                        conflict_query = conflict_query.filter(Appointment.id != exclude_id)
                    conflict = conflict_query.first()

                    if not conflict:
                        date_key = f"{current.strftime('%d.%m.%Y')} ({days_map[current.weekday()]})"
                        if date_key not in grouped_slots:
                            grouped_slots[date_key] = []
                        grouped_slots[date_key].append({
                            'value': current.strftime('%Y-%m-%dT%H:%M'),
                            'time': current.strftime('%H:%M')
                        })
                current += timedelta(minutes=30)

    return jsonify(grouped_slots)

@app.route('/prices')
def prices():
    services = Service.query.all()
    return render_template('prices.html', services=services)


@app.route('/feedbacks')
@login_required
def feedbacks_list():
    if current_user.role != 'admin':
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')

    query = Feedback.query
    if status_filter == 'unread':
        query = query.filter_by(is_read=False)

    query = query.order_by(Feedback.created_at.desc())
    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template('feedbacks_list.html',
                           feedbacks=pagination.items,
                           pagination=pagination,
                           status_filter=status_filter)


@app.route('/feedbacks/<int:feedback_id>/toggle_read', methods=['POST'])
@login_required
def toggle_feedback_read(feedback_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Доступ запрещён'}), 403

    feedback = db.get_or_404(Feedback, feedback_id)

    feedback.is_read = not feedback.is_read
    db.session.commit()

    return jsonify({'success': True, 'is_read': feedback.is_read})

@app.route('/appointments/<int:appointment_id>/assign_procedure', methods=['POST'])
@login_required
def assign_procedure(appointment_id):
    if current_user.role not in ('admin', 'doctor'):
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))

    appointment = db.get_or_404(Appointment, appointment_id)
    service_id = request.form.get('service_id')

    if service_id:
        new_proc = AssignedProcedure(appointment_id=appointment.id, service_id=service_id)
        db.session.add(new_proc)
        db.session.commit()
        flash('Процедура назначена и добавлена в счет.', 'success')

    return redirect(url_for('view_appointment', appointment_id=appointment.id))

# ==========================================
# 12. БИЛЛИНГ И ОПЛАТА УСЛУГ (MOCK PAYMENT)
# ==========================================

@app.route('/appointments/<int:appointment_id>/pay', methods=['POST'])
@login_required
def pay_appointment(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)

    if current_user.role != 'patient' or appointment.patient_id != current_user.patient.id:
        return jsonify({'success': False, 'message': 'Доступ запрещён'}), 403

    if appointment.payment_status == 'paid':
        return jsonify({'success': False, 'message': 'Уже оплачено'}), 400

    if appointment.status in ('cancelled', 'no-show'):
        return jsonify({'success': False, 'message': 'Нельзя оплатить отмененный или пропущенный прием'}), 400

    appointment.payment_status = 'paid'
    db.session.commit()

    return jsonify({'success': True, 'message': 'Оплата прошла успешно!'})


@app.route('/procedures/<int:procedure_id>/pay', methods=['POST'])
@login_required
def pay_procedure(procedure_id):
    proc = db.get_or_404(AssignedProcedure, procedure_id)

    if current_user.role != 'patient' or proc.appointment.patient_id != current_user.patient.id:
        return jsonify({'success': False, 'message': 'Доступ запрещён'}), 403

    if proc.appointment.status in ('cancelled', 'no-show'):
        return jsonify(
            {'success': False, 'message': 'Нельзя оплатить процедуры по отмененному или пропущенному приему'}), 400

    proc.status = 'paid'
    db.session.commit()

    return jsonify({'success': True, 'message': 'Процедура оплачена!'})

# ==========================================
# 15. ОБРАБОТЧИКИ ОШИБОК (404, 500)
# ==========================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==========================================
# 16. ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ
# ==========================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)