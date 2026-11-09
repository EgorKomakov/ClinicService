import pytest


@pytest.mark.parametrize("url", [
    "/",
    "/login",
    "/prices",
    "/contacts",
    "/faq",
    "/404_test",
])
def test_public_pages_load(client, url):
    """Smoke-тест: публичные страницы должны возвращать 200 (или 404 для несуществующих)."""
    response = client.get(url)
    assert response.status_code in (200, 404)


def test_admin_get_pages(client, init_data):
    client.post('/login', data={'username': 'admin_test', 'password': 'pass', 'role': 'admin'})

    urls = [
        "/patients",
        "/patients/new",
        "/doctors",
        "/appointments",
        "/appointments/add",
        f"/doctor/{init_data['doctor_id']}/schedule",
        f"/patients/{init_data['patient_id']}"
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200


def test_doctor_get_pages(client, init_data):
    client.post('/login', data={'username': 'doc_test', 'password': 'pass', 'role': 'doctor'})

    urls = [
        "/appointments",
        "/my_schedule"
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200