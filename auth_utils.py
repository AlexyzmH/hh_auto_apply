import json
from pathlib import Path
from datetime import datetime, timedelta
import requests

AUTH_FILE = Path("auth_storage.json")


def load_auth_data():
    if AUTH_FILE.exists():
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_auth_data(data):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def add_customer_auto(client_id, client_secret, access_token,
                      refresh_token, expires_in, obtained_at=None,username=None):
    obtained_at = obtained_at or datetime.utcnow().isoformat()
    data = load_auth_data()

    # найти следующий свободный customerN
    existing_ids = [int(key[8:]) for key in data if key.startswith("customer") and key[8:].isdigit()]
    next_id = max(existing_ids, default=0) + 1
    customer_id = f"customer{next_id}"

    data[customer_id] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "obtained_at": obtained_at,
        "username": username or customer_id
    }

    save_auth_data(data)
    return customer_id  # можно вернуть, чтобы показывать в UI

def get_valid_access_token(customer_id):
    data = load_auth_data()
    customer = data.get(customer_id)
    if not customer:
        return None

    obtained = datetime.fromisoformat(customer["obtained_at"])
    expires_in = int(customer["expires_in"])
    expires_at = obtained + timedelta(seconds=expires_in)

    if datetime.utcnow() < expires_at:
        return customer["access_token"]  # токен ещё жив

    # 🔁 токен просрочен, обновляем
    print(f"♻️ Обновляем токен для {customer_id}")
    token_url = "https://hh.ru/oauth/token"
    response = requests.post(token_url, data={
        "grant_type": "refresh_token",
        "refresh_token": customer["refresh_token"],
        "client_id": customer["client_id"],
        "client_secret": customer["client_secret"]
    })

    if response.status_code != 200:
        print(f"❌ Ошибка обновления токена: {response.text}")
        return None

    token_data = response.json()
    customer["access_token"] = token_data["access_token"]
    customer["refresh_token"] = token_data.get("refresh_token", customer["refresh_token"])
    customer["expires_in"] = token_data["expires_in"]
    customer["obtained_at"] = datetime.utcnow().isoformat()
    save_auth_data(data)

    return customer["access_token"]