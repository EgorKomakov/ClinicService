import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from config import Config
from models import User, Patient, Doctor, Appointment
from extensions import db
import re
import random, string
import secrets


app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'

with app.app_context():
    db.create_all()

def validate_name(name):
    return bool(re.fullmatch(r"[A-Za-zА-Яа-яЁё\-]{1,50}", name.strip()))

def validate_phone(phone):
    return bool(re.fullmatch(r"\+?\d{6,15}", phone.strip()))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы успешно вышли из системы.", "info")
    return redirect(url_for('login'))


@app.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        return render_template('index.html')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip().lower()

        user = User.query.filter_by(username=username, role=role).first()
        if not user:
            flash('Пользователь не найден или неверная роль.', 'danger')
            return render_template('login.html')

        if not check_password_hash(user.password_hash, password):
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
                return redirect(url_for('patients_list'))

    return render_template('login.html')


@app.route('/patients')
@login_required
def patients_list():
    if current_user.role not in ('admin', 'doctor'):
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))
    patients = Patient.query.order_by(Patient.last_name).all()
    return render_template('patients_list.html', patients=patients)


def generate_temp_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

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

        if not first_name or not last_name or not email:
            flash('Имя, фамилия и email обязательны.', 'danger')
            return render_template('patient_form.html', patient=None)

        dob = None
        if dob_raw:
            try:
                dob = datetime.strptime(dob_raw, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты рождения. Используйте YYYY-MM-DD.', 'danger')
                return render_template('patient_form.html', patient=None)

        temp_password = generate_temp_password()

        user = User(
            username=email,
            role='patient'
        )
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
        first_name = request.form.get('first_name', patient.first_name).strip()
        last_name = request.form.get('last_name', patient.last_name).strip()
        dob_raw = request.form.get('dob')
        if dob_raw:
            try:
                patient.dob = datetime.strptime(dob_raw, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты рождения. Используйте YYYY-MM-DD.', 'danger')
                return render_template('patient_form.html', patient=patient)
        else:
            patient.dob = None

        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        notes = request.form.get('notes')

        if not first_name or not last_name:
            flash('Имя и фамилия обязательны.', 'danger')
            return render_template('patient_form.html', patient=patient)

        patient.first_name = first_name
        patient.last_name = last_name
        patient.phone = phone
        patient.email = email
        patient.notes = notes

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
    db.session.delete(patient)
    db.session.commit()
    flash('Пациент удалён.', 'success')
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
    if current_user.role == 'admin' or current_user.role == 'doctor':
        appointments = Appointment.query.order_by(Appointment.date.desc()).all()
    elif current_user.role == 'patient':
        appointments = Appointment.query.filter_by(patient_id=current_user.patient.id).order_by(Appointment.date.desc()).all()
    else:
        appointments = []
    return render_template('appointments_list.html', appointments=appointments)


@app.route('/appointments/add', methods=['GET', 'POST'])
@login_required
def add_appointment():
    if current_user.role not in ['admin', 'doctor']:
        flash("Только администратор или врач могут добавлять приёмы.", "danger")
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

    return render_template('appointment_form.html', patients=patients, doctors=doctors, appointment=None)


@app.route('/appointments/<int:appointment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if current_user.role not in ['admin', 'doctor']:
        flash("Недостаточно прав для редактирования приёма.", "danger")
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

        appointment.patient_id = patient.id
        appointment.doctor_id = doctor.id
        appointment.date = date
        appointment.notes = notes
        db.session.commit()
        flash("Приём обновлён.", "success")
        return redirect(url_for('appointments_list'))

    return render_template('appointment_form.html', appointment=appointment, patients=patients, doctors=doctors)


@app.route('/appointments/<int:appointment_id>/delete', methods=['POST'])
@login_required
def delete_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if current_user.role not in ['admin', 'doctor']:
        flash("Недостаточно прав для удаления приёма.", "danger")
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
        if not current_user.patient or f"{current_user.patient.first_name} {current_user.patient.last_name}" != appointment.patient_name:
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
