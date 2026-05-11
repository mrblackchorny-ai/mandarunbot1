import os
import telebot
from flask import Flask, request, abort
from database import Database

BOT_TOKEN = os.getenv("BOT_TOKEN", "8215392600:AAEtp6ogh7sqKikqg8q1JE_f0H9wdFM9Oi8")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecrettoken")

# Импортируем бота из bot.py (там уже зарегистрированы все хэндлеры)
import bot as bot_module

app = Flask(__name__)


@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)
    json_data = request.get_data(as_text=True)
    update = telebot.types.Update.de_json(json_data)
    bot_module.bot.process_new_updates([update])
    return "OK", 200


@app.route("/")
def index():
    return "Bot is running!", 200


# PythonAnywhere WSGI entry point
application = app