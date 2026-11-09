from app import app, db
from models import Service

with app.app_context():
    if Service.query.count() == 0:
        services = [
            Service(name="Консультация терапевта", price=1500.0, description="Первичный осмотр, постановка диагноза."),
            Service(name="Общий анализ крови", price=800.0, description="Забор крови из вены, лабораторное исследование."),
            Service(name="УЗИ брюшной полости", price=2200.0, description="Ультразвуковое исследование внутренних органов."),
            Service(name="ЭКГ", price=1100.0, description="Электрокардиограмма, расшифровка."),
            Service(name="Физиотерапия (1 сеанс)", price=900.0, description="Лечебная процедура.")
        ]
        db.session.add_all(services)
        db.session.commit()
        print("Прайс-лист успешно заполнен!")
    else:
        print("Услуги уже есть в базе.")