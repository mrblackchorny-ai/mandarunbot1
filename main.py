import logging
import sys
import os

# ── Вставь свои данные сюда ──────────────────
BOT_TOKEN = "8215392600:AAEtp6ogh7sqKikqg8q1JE_f0H9wdFM9Oi8"
ADMIN_IDS_STR = "6737709054"
PIARFLOW_API_KEY = "huRRHCyvwJmqs7uJo6ZDcq6w_7XFmHEv"
# ─────────────────────────────────────────────

os.environ["BOT_TOKEN"] = BOT_TOKEN
os.environ["ADMIN_IDS"] = ADMIN_IDS_STR
os.environ["PIARFLOW_API_KEY"] = PIARFLOW_API_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

from bot import bot

print("✅ Бот запущен!")
bot.infinity_polling(timeout=55, long_polling_timeout=50)