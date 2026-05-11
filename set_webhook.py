"""
set_webhook.py — запустите один раз для установки webhook.

python set_webhook.py
"""

import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "8215392600:AAEtp6ogh7sqKikqg8q1JE_f0H9wdFM9Oi8")
PYTHONANYWHERE_USERNAME = os.getenv("PA_USERNAME", "yourusername")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecrettoken")

WEBHOOK_URL = (
    f"https://{PYTHONANYWHERE_USERNAME}.pythonanywhere.com"
    f"/webhook/{WEBHOOK_SECRET}"
)

resp = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={"url": WEBHOOK_URL},
)
print(resp.json())