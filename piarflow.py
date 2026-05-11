import requests
import os

PIARFLOW_API_KEY = os.getenv("PIARFLOW_API_KEY", "huRRHCyvwJmqs7uJo6ZDcq6w_7XFmHEv")
PIARFLOW_BASE_URL = "https://piarflow.ru/v1"

HEADERS = {
    "Authorization": f"Bearer {PIARFLOW_API_KEY}",
    "Content-Type": "application/json",
}


def get_sponsors(user_id: int, chat_id: int, max_sponsors: int = 5):
    """Получить список заданий для пользователя."""
    try:
        resp = requests.post(
            f"{PIARFLOW_BASE_URL}/sponsors",
            headers=HEADERS,
            json={"user_id": user_id, "chat_id": chat_id, "max_sponsors": max_sponsors},
            timeout=10,
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_sponsors(user_id: int, links: list):
    """Проверить выполнение заданий."""
    try:
        resp = requests.post(
            f"{PIARFLOW_BASE_URL}/sponsors/check",
            headers=HEADERS,
            json={"user_id": user_id, "links": links},
            timeout=10,
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def all_subscribed(check_result: dict) -> bool:
    """True — все задания выполнены."""
    if check_result.get("status") != "ok":
        return False
    sponsors = check_result.get("sponsors", [])
    return all(s.get("status") == "subscribed" for s in sponsors)