import json
from pathlib import Path
from datetime import datetime

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
                      refresh_token, expires_in, obtained_at=None):
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
        "obtained_at": obtained_at
    }

    save_auth_data(data)
    return customer_id  # можно вернуть, чтобы показывать в UI
