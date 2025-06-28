# hh_logic.py

import requests
from auth_utils import get_valid_access_token, load_auth_data

def find_vacancies(customer_id, text=None, area=None):
    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        print("❌ Клиент не найден")
        return []

    access_token = get_valid_access_token(customer_id)
    if not access_token:
        print("❌ Не удалось получить access_token")
        return []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "HH-User-Agent": "SmartApply/1.0"
    }

    params = {"per_page": 50, "page": 0}
    if text:
        params["text"] = text
    if area:
        params["area"] = area

    resume_id = customer.get("selected_resume_id")
    applied_ids = set()  # ← сначала объявляем

    # Учитываем локальные отклики из responses.json
    if RESPONSES_FILE.exists():
        all_data = json.loads(RESPONSES_FILE.read_text(encoding="utf-8"))
        customer_block = all_data.get(customer_id, {})
        resume_block = customer_block.get(resume_id, [])
        for entry in resume_block:
            applied_ids.add(entry["vacancy_id"])

    # Добавляем отклики из HH API
    if resume_id:
        resp = requests.get(f"https://api.hh.ru/resume/{resume_id}/negotiations", headers=headers)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            applied_ids.update(item["vacancy"]["id"] for item in items)

    collected = []
    print(f"📡 [find_vacancies] Запрос к HH с параметрами: {params}")

    while len(collected) < 50:
        resp = requests.get("https://api.hh.ru/vacancies", headers=headers, params=params)
        if resp.status_code != 200:
            print("❌ Ошибка поиска:", resp.status_code, resp.text)
            break
        vacancies = resp.json().get("items", [])
        if not vacancies:
            break

        filtered = [v for v in vacancies if v["id"] not in applied_ids]
        collected.extend(filtered)
        if len(vacancies) < 50:
            break
        params["page"] += 1

    return collected[:50]



from datetime import datetime
import json
from pathlib import Path

RESPONSES_FILE = Path("responses.json")
COVER_LETTERS_FILE = Path("cover_letters.json")

def format_salary(salary):
    if not salary:
        return "Не указана"
    _from = salary.get("from", "")
    _to = salary.get("to", "")
    currency = salary.get("currency", "")
    return f"{_from} – { _to} {currency}".strip(" –")

def respond_to_vacancy_internal(customer_id, resume_id, vacancy_id, message=None):
    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        return {"status": "fail", "message": "Клиент не найден"}

    access_token = get_valid_access_token(customer_id)
    if not access_token:
        return {"status": "fail", "message": "Не удалось получить access_token"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "HH-User-Agent": "SmartApply/1.0"
    }

    vacancy_resp = requests.get(f"https://api.hh.ru/vacancies/{vacancy_id}", headers=headers)
    if vacancy_resp.status_code != 200:
        return {"status": "fail", "message": "Не удалось получить вакансию"}

    vacancy = vacancy_resp.json()

    suitable_resp = requests.get(vacancy.get("suitable_resumes_url"), headers=headers)
    suitable_ids = [r["id"] for r in suitable_resp.json().get("items", [])]

    if resume_id not in suitable_ids:
        return {"status": "fail", "message": "Резюме не подходит"}

    if not message:
        if COVER_LETTERS_FILE.exists():
            all_letters = json.loads(COVER_LETTERS_FILE.read_text(encoding="utf-8"))
            message = all_letters.get(customer_id, {}).get(resume_id, "")
        if not message and vacancy.get("response_letter_required"):
            message = "Здравствуйте! Заинтересовала ваша вакансия. Готов обсудить детали."

    form_data = {
        "resume_id": resume_id,
        "vacancy_id": vacancy_id,
        "message": message
    }

    apply_resp = requests.post("https://api.hh.ru/negotiations", headers=headers, data=form_data, allow_redirects=False)

    if apply_resp.status_code == 201:
        status = "success"
        reason = ""
    elif apply_resp.status_code == 303:
        status = "manual"
        reason = ""
    else:
        try:
            reason = apply_resp.json().get("description", "Неизвестная ошибка")
        except Exception:
            reason = "Неизвестная ошибка"
        status = "fail"

    response_entry = {
        "vacancy_id": vacancy_id,
        "name": vacancy.get("name"),
        "company": vacancy.get("employer", {}).get("name", "Не указано"),
        "city": vacancy.get("area", {}).get("name", "Не указано"),
        "salary": format_salary(vacancy.get("salary")),
        "url": vacancy.get("alternate_url"),
        "applied_at": datetime.utcnow().isoformat(),
        "status": status
    }

    if RESPONSES_FILE.exists():
        all_data = json.loads(RESPONSES_FILE.read_text(encoding="utf-8"))
    else:
        all_data = {}

    customer_block = all_data.get(customer_id, {})
    resume_block = customer_block.get(resume_id, [])
    if not any(r["vacancy_id"] == vacancy_id for r in resume_block):
        resume_block.append(response_entry)
        customer_block[resume_id] = resume_block
        all_data[customer_id] = customer_block
        RESPONSES_FILE.write_text(json.dumps(all_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": status, "entry": response_entry if status != "fail" else None, "message": reason}

