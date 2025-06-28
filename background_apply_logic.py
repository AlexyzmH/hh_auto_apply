# background_apply_logic.py
from time import sleep

from auth_utils import get_valid_access_token, load_auth_data
from hh_logic import find_vacancies, respond_to_vacancy_internal
import json
from pathlib import Path

TASKS_FILE = Path("background_tasks.json")
# Загружаем карту городов
AREA_MAP_PATH = Path("area_map.json")
try:
    AREA_MAP = json.loads(AREA_MAP_PATH.read_text(encoding="utf-8"))
except Exception as e:
    print("❌ Ошибка чтения area_map.json:", e)
    AREA_MAP = {}

def apply_for_customer_resume(customer_id, resume_id, text=None, message=None,area=None):
    hh_area_id = AREA_MAP.get(area.strip()) if area else None
    print(f"🧪 DEBUG: apply_for_customer_resume получил text={text!r}, area={area!r}")

    # Проверка перед запуском
    try:
        tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        if not tasks.get(customer_id, {}).get(resume_id, {}).get("active", False):
            print("🛑 Задача неактивна, выход из apply_for_customer_resume")
            return
    except Exception as e:
        print("⚠️ Ошибка при проверке активности задачи:", e)


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
    vacancies = find_vacancies(customer_id, text=text,area=hh_area_id)
    print(f"📦 Найдено {len(vacancies)} вакансий")

    for v in vacancies:
        # ⛔ Проверка, активна ли задача — если нет, прерываем цикл
        try:
            tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
            if not tasks.get(customer_id, {}).get(resume_id, {}).get("active", False):
                print("🛑 Отклик остановлен во время цикла вакансий")
                break
        except Exception as e:
            print("⚠️ Ошибка при проверке задач:", e)
        vacancy_id = v["id"]
        try:
            result = respond_to_vacancy_internal(customer_id, resume_id, vacancy_id, message=message)
            print(f"📨 Отклик на {vacancy_id} → {result['status']} — {result.get('message', '')}")
        except Exception as e:
            print(f"❌ Ошибка при отклике на {vacancy_id}:", e)
