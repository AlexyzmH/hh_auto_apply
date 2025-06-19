import os

from flask import Flask, redirect, request, render_template, jsonify
from auth_utils import add_customer_auto, load_auth_data, get_valid_access_token
from datetime import datetime
import requests
import json
from dotenv import load_dotenv
from pathlib import Path

app = Flask(__name__)

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
RESPONSES_FILE = Path("responses.json")


@app.route("/")
def index():
    customers = load_auth_data()
    return render_template("index.html", customers=customers)


@app.route("/login")
def login():
    return redirect(
        f"https://hh.ru/oauth/authorize?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

def format_salary(salary):
    if not salary:
        return "Не указана"
    _from = salary.get("from", "")
    _to = salary.get("to", "")
    currency = salary.get("currency", "")
    return f"{_from} – { _to} {currency}".strip(" –")

@app.route("/auth")
def auth():
    code = request.args.get("code")
    if not code:
        return "❌ Ошибка: нет кода авторизации", 400

    print("🔁 Получен code:", code)

    token_url = "https://hh.ru/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    }

    print("📡 Отправляем POST на /oauth/token")
    response = requests.post(token_url, data=data)
    print("🔢 Статус:", response.status_code)
    print("📦 Тело:", response.text)

    if response.status_code != 200:
        return f"❌ Ошибка получения токена: {response.text}", 500

    token_data = response.json()
    print("✅ Получен access_token:", token_data.get("access_token"))

    try:
        print("👤 Пытаемся получить /me")
        me_resp = requests.get("https://api.hh.ru/me", headers={
            "Authorization": f"Bearer {token_data['access_token']}",
            "HH-User-Agent": "SmartApply/1.0"
        })

        print("📡 /me статус:", me_resp.status_code)
        print("📃 /me тело:", me_resp.text)

        if me_resp.status_code != 200:
            return f"❌ Ошибка получения имени пользователя: {me_resp.text}", 500

        me_data = me_resp.json()
        username = me_data.get("first_name", "") + " " + me_data.get("last_name", "")
        print("📛 Имя пользователя:", username)

    except Exception as e:
        print("🔥 Ошибка при получении /me:", e)
        return f"❌ Ошибка при обработке данных пользователя: {str(e)}", 500

    print("📥 Добавляем нового клиента...")
    customer_id = add_customer_auto(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_in=token_data["expires_in"],
        obtained_at=datetime.utcnow().isoformat(),
        username=username
    )

    print("✅ Клиент сохранён под ID:", customer_id)
    return redirect(f"/customer/{customer_id}")

@app.route("/customer/<customer_id>")
def customer_dashboard(customer_id):
    from auth_utils import load_auth_data
    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        return f"Клиент {customer_id} не найден", 404

    headers = {
        "Authorization": f"Bearer {customer['access_token']}",
        "HH-User-Agent": "SmartApply/1.0 (joopsasakomarov37@yahoo.com)"
    }

    resumes_resp = requests.get("https://api.hh.ru/resumes/mine", headers=headers)
    if resumes_resp.status_code != 200:
        return f"Не удалось получить резюме: {resumes_resp.text}", 500

    resumes = resumes_resp.json().get("items", [])

    if RESPONSES_FILE.exists() and RESPONSES_FILE.stat().st_size > 0:
        try:
            with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
                all_responses = json.load(f)
        except json.JSONDecodeError:
            print("⚠️ responses.json повреждён — используем пустой словарь")
            all_responses = {}
    else:
        all_responses = {}

    responses_by_resume = all_responses.get(customer_id, {})

    return render_template(
        "customer.html",
        customer_id=customer_id,
        resumes=resumes,
        username=customer.get("username"),
        responses=responses_by_resume
    )


@app.route("/search")
def search():
    customer_id = request.args.get("customer_id")
    return render_template("search.html", customer_id=customer_id)


@app.route("/vacancies")
def get_vacancies():
    from auth_utils import load_auth_data
    customer_id = request.args.get("customer_id")
    customers = load_auth_data()
    customer = customers.get(customer_id)

    if not customer:
        return jsonify({"error": "Клиент не найден"}), 404

    access_token = get_valid_access_token(customer_id)
    if not access_token:
        return jsonify({"error": "Не удалось получить access_token"}), 401

    headers = {
        "Authorization": f"Bearer {access_token}",
        "HH-User-Agent": "SmartApply/1.0 (joopsasakomarov37@yahoo.com)"
    }

    allowed_keys = [
        "text", "area", "not_word", "specialization", "experience",
        "employment", "schedule", "salary"
    ]

    params = {}
    for key in allowed_keys:
        val = request.args.get(key)
        if val:
            params[key] = val

    search_fields = request.args.getlist("search_field")
    if search_fields:
        params["search_field"] = search_fields[0]

    if request.args.get("only_with_salary") == "true":
        params["only_with_salary"] = "true"

    per_page = 50
    target_results = 50
    page = 0
    collected = []

    # Получим список уже откликнутых ID
    if RESPONSES_FILE.exists():
        try:
            with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
                all_responses = json.load(f)
        except json.JSONDecodeError:
            all_responses = {}
    else:
        all_responses = {}

    resume_id = customer.get("selected_resume_id")
    applied_ids = set()
    if resume_id:
        customer_block = all_responses.get(customer_id, {})
        applied_ids = set(item["vacancy_id"] for item in customer_block.get(resume_id, []))

    # Загружаем вакансии постранично
    while len(collected) < target_results:
        params["page"] = page
        params["per_page"] = per_page
        resp = requests.get("https://api.hh.ru/vacancies", headers=headers, params=params)
        if resp.status_code != 200:
            print("❌ Ошибка поиска:", resp.status_code, resp.text)
            return jsonify({"error": "Ошибка при поиске", "status": resp.status_code}), resp.status_code

        vacancies = resp.json().get("items", [])
        if not vacancies:
            break

        filtered = [v for v in vacancies if v["id"] not in applied_ids]
        collected.extend(filtered)

        if len(vacancies) < per_page:
            break

        page += 1

    return jsonify({"items": collected[:target_results]})




@app.route("/delete/<customer_id>", methods=["POST"])
def delete_customer(customer_id):
    from auth_utils import load_auth_data, save_auth_data
    data = load_auth_data()

    if customer_id in data:
        del data[customer_id]
        save_auth_data(data)
        print(f"🗑 Удалён клиент: {customer_id}")
    else:
        print(f"⚠️ Попытка удалить несуществующего клиента: {customer_id}")

    return redirect("/")


@app.route("/respond", methods=["POST"])
def respond_to_vacancy():
    data = request.json
    customer_id = data.get("customer_id")
    vacancy_id = data.get("vacancy_id")

    print(f"🚨 /respond: customer_id={customer_id}, vacancy_id={vacancy_id}")

    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        return jsonify({"error": "Клиент не найден"}), 404

    access_token = get_valid_access_token(customer_id)
    if not access_token:
        return jsonify({"error": "Не удалось получить access_token"}), 401

    headers = {
        "Authorization": f"Bearer {access_token}",
        "HH-User-Agent": "SmartApply/1.0 (joopsasakomarov37@yahoo.com)"
    }

    # 1. Получаем вакансию
    vacancy_resp = requests.get(f"https://api.hh.ru/vacancies/{vacancy_id}", headers=headers)
    if vacancy_resp.status_code != 200:
        return jsonify({"error": "Не удалось получить вакансию"}), 500
    vacancy = vacancy_resp.json()

    # 2. Проверка доступности отклика

    # 3. Получаем выбранное резюме из сохранённых данных
    resume_id = customer.get("selected_resume_id")
    if not resume_id:
        return jsonify({"error": "Резюме не выбрано. Выберите его на странице клиента."}), 400

    # (необязательно, но желательно: проверим, что такое резюме всё ещё существует)
    resumes_resp = requests.get("https://api.hh.ru/resumes/mine", headers=headers)
    if resumes_resp.status_code != 200:
        return jsonify({"error": "Не удалось проверить список резюме"}), 500

    resumes = resumes_resp.json().get("items", [])
    resume_ids = [r["id"] for r in resumes]
    if resume_id not in resume_ids:
        return jsonify({"error": "Сохранённое резюме больше не существует. Выберите заново."}), 400

    # 4. Проверка подходящих резюме
    suitable_resp = requests.get(vacancy.get("suitable_resumes_url"), headers=headers)
    suitable_ids = [r["id"] for r in suitable_resp.json().get("items", [])]
    if resume_id not in suitable_ids:
        return jsonify({"error": "Резюме не подходит для отклика на эту вакансию"}), 403

    # 5. Формируем тело запроса — multipart/form-data
    form_data = {
        "resume_id": resume_id,
        "vacancy_id": vacancy_id
    }

    # Новое: если message передан — используем его
    message = data.get("message", "").strip()
    if message:
        form_data["message"] = message
    # Иначе — если HH требует письмо, а мы его не дали — вставим шаблон
    elif vacancy.get("response_letter_required"):
        form_data["message"] = "Здравствуйте! Заинтересовала ваша вакансия. Готов обсудить детали."

    # 6. Отправляем отклик
    print("📄 Отправляем отклик с данными:")
    print("📌 form_data:", json.dumps(form_data, ensure_ascii=False, indent=2))
    print("🧾 headers:", json.dumps(headers, ensure_ascii=False, indent=2))
    print("📎 suitable resume_ids:", suitable_ids)
    print("✅ Используемое resume_id:", resume_id)

    apply_resp = requests.post(
        "https://api.hh.ru/negotiations",
        headers=headers,
        files={key: (None, value) for key, value in form_data.items()}
    )

    print("📥 Ответ от API:")
    print("📌 Статус:", apply_resp.status_code)
    print("📃 Тело:", apply_resp.text)

    # 7. Обработка ответа
    if apply_resp.status_code == 201:
        # ✅ Сохраняем отклик
        response_entry = {
            "vacancy_id": vacancy_id,
            "name": vacancy.get("name"),
            "company": vacancy.get("employer", {}).get("name", "Не указано"),
            "city": vacancy.get("area", {}).get("name", "Не указано"),
            "salary": format_salary(vacancy.get("salary")),
            "url": vacancy.get("alternate_url"),
            "applied_at": datetime.utcnow().isoformat()
        }

        if RESPONSES_FILE.exists():
            with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        else:
            all_data = {}

        customer_block = all_data.get(customer_id, {})
        resume_block = customer_block.get(resume_id, [])

        # Защита от дубликатов
        if not any(r["vacancy_id"] == vacancy_id for r in resume_block):
            resume_block.append(response_entry)
            customer_block[resume_id] = resume_block
            all_data[customer_id] = customer_block

            with open(RESPONSES_FILE, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

        return jsonify({"message": "✅ Отклик успешно отправлен!"}), 201

    elif apply_resp.status_code == 303:
        return jsonify({
            "error": "🔀 Вакансия требует прямого отклика. Используйте сайт.",
            "manual_url": vacancy.get("apply_alternate_url")
        }), 303


    elif apply_resp.status_code == 400:
        print("❌ Ошибка 400. Ответ от сервера:")
        print(apply_resp.text)
        return jsonify({"error": apply_resp.json()}), 400



    elif apply_resp.status_code == 403:
        error_json = apply_resp.json()
        error_value = error_json.get("errors", [{}])[0].get("value", "")
        error_text = error_json.get("error", "").lower()
        if error_value == "test_required":
            return jsonify({
                "error": "📋 Для этой вакансии нужно пройти тест",
                "reason": "test_required"
            }), 403
        else:
            return jsonify({
            "error": "⚠️ Вы уже откликались на эту вакансию",
            "reason": "already_applied"
        }), 403
        #else:
            #return jsonify({
                #"error": "⛔ Отклик запрещён",
                #"reason": error_value or "unknown",
                #"details": error_json
            #}), 403



    else:
        return jsonify({
            "error": "❌ Неизвестная ошибка",
            "status": apply_resp.status_code,
            "body": apply_resp.text
        }), 500


@app.route("/select_resume", methods=["POST"])
def select_resume():
    from auth_utils import load_auth_data, save_auth_data
    customer_id = request.form.get("customer_id")
    resume_id = request.form.get("resume_id")

    if not customer_id or not resume_id:
        return "❌ Отсутствует customer_id или resume_id", 400

    data = load_auth_data()
    if customer_id not in data:
        return f"❌ Клиент {customer_id} не найден", 404

    data[customer_id]["selected_resume_id"] = resume_id
    save_auth_data(data)

    print(f"✅ Сохранён выбор резюме {resume_id} для клиента {customer_id}")
    return redirect(f"/search?customer_id={customer_id}")




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
