from flask import Flask, redirect, request, render_template, jsonify
from auth_utils import add_customer_auto, load_auth_data
from datetime import datetime
import requests
import json

app = Flask(__name__)

CLIENT_ID = "VL9NCGOGJDT668M9MALKFO2VAUJCDE948AJ5CO6DQV3D5TRMBOK5S5O9CVER58NA"
CLIENT_SECRET = "NU2SKUJUU4NGBT4KDBVU7C588PO00KUDE110GOR194JBGJPB43JU72FC9DU3J8JM"
REDIRECT_URI = "http://localhost:5000/auth"



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
        return "Ошибка: нет кода авторизации", 400

    token_url = "https://hh.ru/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Ошибка получения токена: {response.text}", 500

    token_data = response.json()
    customer_id = add_customer_auto(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_in=token_data["expires_in"],
        obtained_at=datetime.utcnow().isoformat()
    )

    return redirect(f"/search?customer_id={customer_id}")


@app.route("/search")
def search():
    customer_id = request.args.get("customer_id")
    return render_template("search.html", customer_id=customer_id)


@app.route("/vacancies")
def get_vacancies():
    from auth_utils import load_auth_data
    customer_id = request.args.get("customer_id")
    keyword = request.args.get("text", "")
    area = request.args.get("area")

    customers = load_auth_data()
    customer = customers.get(customer_id)
    if not customer:
        return jsonify({"error": "Клиент не найден"}), 404

    headers = {"Authorization": f"Bearer {customer['access_token']}"}
    params = {"text": keyword, "area": area, "per_page": 50}
    resp = requests.get("https://api.hh.ru/vacancies", headers=headers, params=params)
    return jsonify(resp.json())


@app.route("/respond", methods=["POST"])
def respond_to_vacancy():
    from auth_utils import load_auth_data
    data = request.json
    customer_id = data.get("customer_id")
    vacancy_id = data.get("vacancy_id")

    auth_data = load_auth_data()
    customer = auth_data.get(customer_id)
    if not customer:
        return jsonify({"error": "Клиент не найден"}), 404

    headers = {"Authorization": f"Bearer {customer['access_token']}"}

    # 1. Получаем вакансию
    vacancy_resp = requests.get(f"https://api.hh.ru/vacancies/{vacancy_id}", headers=headers)
    if vacancy_resp.status_code != 200:
        return jsonify({"error": "Не удалось получить вакансию"}), 500
    vacancy = vacancy_resp.json()

    print(json.dumps(vacancy, indent=2, ensure_ascii=False))  # читаемо и по-русски
    if vacancy.get("response_url") is None:
        return jsonify({
            "error": "Отклик невозможен через API. Только вручную на сайте.",
            "manual_url": vacancy.get("apply_alternate_url")
        }), 400

    # 2. Получаем резюме
    resumes_resp = requests.get("https://api.hh.ru/resumes/mine", headers=headers)
    resumes = resumes_resp.json().get("items", [])
    if not resumes:
        return jsonify({"error": "Нет доступных резюме"}), 400

    resume_id = resumes[0]["id"]

    # 3. Формируем отклик
    payload = {
        "resume_id": resume_id
    }

    if vacancy.get("response_letter_required"):
        payload["message"] = "Здравствуйте! Заинтересовала ваша вакансия. Готов обсудить детали."

    print("resume_id "  + resume_id)

    apply_resp = requests.post(
        f"https://api.hh.ru/vacancies/{vacancy_id}/send",
        headers=headers,
        json=payload
    )

    if apply_resp.status_code != 204:
        return jsonify({"error": apply_resp.json()}), 500

    return jsonify({"message": "Отклик успешно отправлен!"})



if __name__ == "__main__":
    app.run(debug=True)
