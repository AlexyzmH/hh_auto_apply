import os

from flask import Flask, redirect, request, render_template, jsonify
from auth_utils import add_customer_auto, load_auth_data, get_valid_access_token
from datetime import datetime
import requests
import json
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")


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
    return redirect(f"/search?customer_id={customer_id}")

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
    return render_template("customer.html", customer_id=customer_id, resumes=resumes)



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

    # Формируем параметры для запроса
    params = {}
    for key in [
        "text", "area", "not_word", "specialization", "experience",
        "employment", "schedule", "salary"
    ]:
        val = request.args.get(key)
        if val:
            params[key] = val

    # Обработка множественных полей search_field
    search_fields = request.args.getlist("search_field")
    for field in search_fields:
        params.setdefault("search_field", []).append(field)

    # Обработка чекбокса only_with_salary
    if request.args.get("only_with_salary") == "true":
        params["only_with_salary"] = "true"

    # Преобразуем массив search_field → множественные query params
    search_query = []
    for k, v in params.items():
        if isinstance(v, list):
            for item in v:
                search_query.append((k, item))
        else:
            search_query.append((k, v))

    search_query.append(("per_page", 50))

    resp = requests.get("https://api.hh.ru/vacancies", headers=headers, params=search_query)
    return jsonify(resp.json())


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


    # 3. Получаем резюме
    resumes_resp = requests.get("https://api.hh.ru/resumes/mine", headers=headers)
    resumes = resumes_resp.json().get("items", [])
    if not resumes:
        return jsonify({"error": "Нет доступных резюме"}), 400

    resume_id = resumes[0]["id"]

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
    if vacancy.get("response_letter_required"):
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
        return jsonify({"message": "✅ Отклик успешно отправлен!"}), 201

    elif apply_resp.status_code == 303:
        return jsonify({
            "error": "🔀 Вакансия требует прямого отклика. Используйте сайт.",
            "manual_url": vacancy.get("apply_alternate_url")
        }), 303


    elif apply_resp.status_code == 403:
        error_json = apply_resp.json()
        error_value = error_json.get("errors", [{}])[0].get("value", "")
        return jsonify({
            "error": "⛔ Отклик запрещён",
            "details": error_json,
            "reason": error_value  # вот эта строка
        }), 403



    elif apply_resp.status_code == 400:
        print("❌ Ошибка 400. Ответ от сервера:")
        print(apply_resp.text)
        return jsonify({"error": apply_resp.json()}), 400




    elif apply_resp.status_code == 409:
        try:
            _ = apply_resp.json()  # Пытаемся убедиться, что тело - JSON
        except:
            pass  # просто молча продолжаем
        return jsonify({
            "error": "⚠️ Вы уже откликались на эту вакансию",
            "reason": "already_applied"
        }), 403  #попал в нужный блок


    else:
        return jsonify({
            "error": "❌ Неизвестная ошибка",
            "status": apply_resp.status_code,
            "body": apply_resp.text
        }), 500




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
