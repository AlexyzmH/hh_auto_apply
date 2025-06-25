# background_apply_logic.py
from time import sleep

from auth_utils import get_valid_access_token, load_auth_data
from hh_logic import find_vacancies, respond_to_vacancy_internal

def apply_for_customer_resume(customer_id, resume_id, text=None, message=None,area=None):
    print(f"📡 apply_for_customer_resume: {customer_id=} {resume_id=}")
    print(f"📝 text = '{text}', message длина = {len(message or '')}")

    sleep(5)

    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        print("❌ Клиент не найден")
        return

    access_token = get_valid_access_token(customer_id)
    if not access_token:
        print("❌ Не удалось получить токен")
        return

    print("🔍 Получаем вакансии...")
    vacancies = find_vacancies(customer_id, text=text,area=area)
    print(f"📦 Найдено {len(vacancies)} вакансий")

    for v in vacancies:
        vacancy_id = v["id"]
        try:
            result = respond_to_vacancy_internal(customer_id, resume_id, vacancy_id, message=message)
            print(f"📨 Отклик на {vacancy_id} → {result['status']} — {result.get('message', '')}")
        except Exception as e:
            print(f"❌ Ошибка при отклике на {vacancy_id}:", e)
