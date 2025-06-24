# background_apply_logic.py

import requests
from auth_utils import get_valid_access_token, load_auth_data

def apply_for_customer_resume(customer_id, resume_id, text=None, message=None):
    print(f"📡 apply_for_customer_resume: {customer_id=} {resume_id=}")
    print(f"📝 text = '{text}', message длина = {len(message or '')}")

    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        print("❌ Клиент не найден")
        return

    access_token = get_valid_access_token(customer_id)
    if not access_token:
        print("❌ Не удалось получить токен")
        return

    # Ищем вакансии
    params = {"customer_id": customer_id}
    if text:
        params["text"] = text

    print("🔍 Получаем вакансии...")
    resp = requests.get("http://localhost:5000/vacancies", params=params)
    if resp.status_code != 200:
        print("❌ Ошибка при поиске:", resp.status_code, resp.text)
        return

    data = resp.json()
    vacancies = data.get("items", [])
    print(f"📦 Найдено {len(vacancies)} вакансий")

    for v in vacancies:
        vacancy_id = v["id"]

        respond_data = {
            "customer_id": customer_id,
            "vacancy_id": vacancy_id,
            "message": message or ""
        }

        try:
            res = requests.post("http://localhost:5000/respond", json=respond_data)
            print(f"📨 Отклик на {vacancy_id} →", res.status_code)
        except Exception as e:
            print("❌ Ошибка при отклике:", e)
