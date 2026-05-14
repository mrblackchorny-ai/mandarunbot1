import logging
import os
from telebot import TeleBot, types
from database import Database, fmt
from piarflow import get_sponsors, check_sponsors, all_subscribed

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

bot = TeleBot(BOT_TOKEN)
db = Database("bot.db")

# Хранилище ссылок спонсоров для пользователя (в памяти)
# Формат: { user_id: ["https://t.me/channel1", ...] }
user_sponsor_links: dict[int, list[str]] = {}


def is_admin(user_id):
    return user_id in ADMIN_IDS


def parse_float(s: str):
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def main_menu(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        types.InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily"),
    )
    kb.add(
        types.InlineKeyboardButton("👥 Реферальная система", callback_data="referral"),
        types.InlineKeyboardButton("💸 Вывод звёзд", callback_data="withdraw"),
    )
    kb.add(types.InlineKeyboardButton("🏆 Топ игроков", callback_data="top"))
    return kb


def back_btn(callback="menu"):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data=callback))
    return kb


# ─── ПРОВЕРКА СПОНСОРОВ ───────────────────────────────────────────────────────

def sponsors_keyboard(sponsors: list, show_check=True):
    """Клавиатура со ссылками спонсоров + кнопка проверки."""
    kb = types.InlineKeyboardMarkup()
    for i, s in enumerate(sponsors, 1):
        status_icon = "✅" if s.get("status") == "subscribed" else "➡️"
        kb.add(types.InlineKeyboardButton(
            f"{status_icon} Спонсор {i}",
            url=s["link"]
        ))
    if show_check:
        kb.add(types.InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_sponsors"))
    return kb


def check_and_pass_sponsors(user_id: int, chat_id: int) -> bool:
    """
    Проверяет спонсоров. Если все подписки выполнены — возвращает True.
    Если нет — показывает задания и возвращает False.
    Вызывай перед любым действием, требующим доступа.
    """
    links = user_sponsor_links.get(user_id)

    # Если ссылок ещё нет — получаем их
    if not links:
        data = get_sponsors(user_id, chat_id)

        if data.get("status") == "register":
            reg_url = data.get("additional", {}).get("registration_url", "https://t.me/PiarFlowBot")
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🤖 Зарегистрироваться", url=reg_url))
            bot.send_message(
                chat_id,
                "⚠️ *Для использования бота* сначала запусти @PiarFlowBot",
                parse_mode="Markdown",
                reply_markup=kb
            )
            return False

        if data.get("status") != "ok":
            # Ошибка API — пропускаем, чтобы не блокировать пользователя из-за сбоя сервиса
            logger.warning(f"PiarFlow /sponsors error for {user_id}: {data}")
            return True

        sponsors = data.get("sponsors", [])
        if not sponsors:
            # Заданий нет — доступ открыт
            return True

        links = [s["link"] for s in sponsors]
        user_sponsor_links[user_id] = links

        kb = sponsors_keyboard(sponsors)
        bot.send_message(
            chat_id,
            "📋 *Для доступа к боту подпишись на наших спонсоров:*\n\n"
            "После подписки нажми «🔄 Проверить подписки»",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return False

    # Ссылки уже есть — проверяем выполнение
    result = check_sponsors(user_id, links)

    if result.get("status") == "register":
        reg_url = result.get("additional", {}).get("registration_url", "https://t.me/PiarFlowBot")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🤖 Зарегистрироваться", url=reg_url))
        bot.send_message(
            chat_id,
            "⚠️ *Сначала запусти @PiarFlowBot*",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return False

    if result.get("status") != "ok":
        # Ошибка при проверке — сообщаем, не сбрасываем ссылки
        logger.warning(f"PiarFlow /check error for {user_id}: {result}")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔄 Проверить снова", callback_data="check_sponsors"))
        bot.send_message(
            chat_id,
            "⚠️ *Не удалось проверить подписки*\n\n"
            "Сервис временно недоступен. Попробуй через несколько секунд.",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return False

    if all_subscribed(result):
        # Всё выполнено — очищаем кэш
        user_sponsor_links.pop(user_id, None)
        return True

    # Ещё не все подписаны — показываем обновлённый статус
    sponsors = result.get("sponsors", [])
    done = sum(1 for s in sponsors if s.get("status") == "subscribed")
    total = len(sponsors)
    kb = sponsors_keyboard(sponsors)
    bot.send_message(
        chat_id,
        f"⏳ *Выполнено {done}/{total} заданий*\n\n"
        "Подпишись на всех спонсоров и нажми «🔄 Проверить подписки»",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return False


# ─── ХЭНДЛЕРЫ ────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    user = message.from_user
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    db.register_user(user.id, user.username or "", user.full_name, referrer_id)

    # Проверяем спонсоров при старте
    if not check_and_pass_sponsors(user.id, message.chat.id):
        return

    bot.send_message(
        message.chat.id,
        f"👋 Привет, *{user.first_name}*!\n\n"
        f"Добро пожаловать в *Star Bot* ⭐️\n\n"
        f"Зарабатывай звёзды, приглашай друзей и выводи награды!\n\n"
        f"Выбери действие:",
        parse_mode="Markdown",
        reply_markup=main_menu(user.id)
    )



@bot.callback_query_handler(func=lambda c: c.data == "check_sponsors")
def cb_check_sponsors(call: types.CallbackQuery):
    """Пользователь нажал «Проверить подписки»."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id, "⏳ Проверяем...")

    links = user_sponsor_links.get(user_id)
    if not links:
        bot.send_message(chat_id, "✅ Все задания уже выполнены!", reply_markup=main_menu(user_id))
        return

    result = check_sponsors(user_id, links)

    if result.get("status") == "register":
        reg_url = result.get("additional", {}).get("registration_url", "https://t.me/PiarFlowBot")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🤖 Зарегистрироваться", url=reg_url))
        bot.send_message(chat_id, "⚠️ Сначала запусти @PiarFlowBot", reply_markup=kb)
        return

    if all_subscribed(result):
        user_sponsor_links.pop(user_id, None)
        bot.send_message(
            chat_id,
            "✅ *Отлично! Все задания выполнены.*\n\nДобро пожаловать!",
            parse_mode="Markdown",
            reply_markup=main_menu(user_id)
        )
        return

    sponsors = result.get("sponsors", [])
    done = sum(1 for s in sponsors if s.get("status") == "subscribed")
    total = len(sponsors)
    kb = sponsors_keyboard(sponsors)
    bot.send_message(
        chat_id,
        f"⏳ *Выполнено {done}/{total} заданий*\n\n"
        "Подпишись на всех и нажми «🔄 Проверить подписки»",
        parse_mode="Markdown",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data == "menu")
def cb_menu(call: types.CallbackQuery):
    bot.edit_message_text(
        "⭐️ *Star Bot* — главное меню\n\nЗарабатывай звёзды и выводи их!",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=main_menu(call.from_user.id)
    )


@bot.callback_query_handler(func=lambda c: c.data == "profile")
def cb_profile(call: types.CallbackQuery):
    if not check_and_pass_sponsors(call.from_user.id, call.message.chat.id):
        bot.answer_callback_query(call.id)
        return
    u = db.get_user(call.from_user.id)
    if not u:
        bot.answer_callback_query(call.id, "Сначала напишите /start")
        return
    bot.edit_message_text(
        f"👤 *Ваш профиль*\n\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"📛 Имя: {u['full_name']}\n"
        f"⭐️ Баланс: *{fmt(u['balance'])} звёзд*\n"
        f"👥 Рефералов: *{u['referral_count']}*\n"
        f"📅 Регистрация: {u['created_at'][:10]}",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=back_btn()
    )


@bot.callback_query_handler(func=lambda c: c.data == "daily")
def cb_daily(call: types.CallbackQuery):
    if not check_and_pass_sponsors(call.from_user.id, call.message.chat.id):
        bot.answer_callback_query(call.id)
        return
    user_id = call.from_user.id
    result = db.claim_daily(user_id)
    reward = db.get_setting("daily_reward", 1)

    if result[0] == "claimed":
        u = db.get_user(user_id)
        text = (
            f"🎁 *Ежедневный бонус получен!*\n\n"
            f"Начислено *{fmt(reward)} ⭐️*\n"
            f"Баланс: *{fmt(u['balance'])} ⭐️*\n\n"
            f"Возвращайтесь завтра!"
        )
        # Уведомляем реферера если его бонус только что начислен
        referrer_id = result[1]
        if referrer_id:
            ref_reward = db.get_setting("ref_reward", 3)
            try:
                bot.send_message(
                    referrer_id,
                    f"🌟 Ваш реферал получил ежедневный бонус!\n"
                    f"Начислено *{fmt(ref_reward)} ⭐️*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    else:
        text = (
            f"⏳ *Бонус уже получен сегодня*\n\n"
            f"Следующий бонус завтра.\n"
            f"Размер бонуса: *{fmt(reward)} ⭐️*"
        )

    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=back_btn()
    )


@bot.callback_query_handler(func=lambda c: c.data == "referral")
def cb_referral(call: types.CallbackQuery):
    if not check_and_pass_sponsors(call.from_user.id, call.message.chat.id):
        bot.answer_callback_query(call.id)
        return
    u = db.get_user(call.from_user.id)
    ref_reward = db.get_setting("ref_reward", 3)
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"

    bot.edit_message_text(
        f"👥 *Реферальная система*\n\n"
        f"За каждого приглашённого друга вы получаете *{fmt(ref_reward)} ⭐️*\n\n"
        f"⚠️ *Важно:* реферал засчитывается только после того, как приглашённый получит свой первый ежедневный бонус\n\n"
        f"Ваших рефералов: *{u['referral_count']}*\n\n"
        f"🔗 Ваша ссылка:\n`{ref_link}`",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=back_btn()
    )


@bot.callback_query_handler(func=lambda c: c.data == "withdraw")
def cb_withdraw(call: types.CallbackQuery):
    if not check_and_pass_sponsors(call.from_user.id, call.message.chat.id):
        bot.answer_callback_query(call.id)
        return
    u = db.get_user(call.from_user.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    for amount in [15, 25, 50, 100]:
        kb.add(types.InlineKeyboardButton(f"⭐️ {amount} звёзд", callback_data=f"withdraw_{amount}"))
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="menu"))

    bot.edit_message_text(
        f"💸 *Вывод звёзд*\n\n"
        f"Ваш баланс: *{fmt(u['balance'])} ⭐️*\n\n"
        f"Выберите сумму:",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("withdraw_"))
def cb_withdraw_amount(call: types.CallbackQuery):
    if not check_and_pass_sponsors(call.from_user.id, call.message.chat.id):
        bot.answer_callback_query(call.id)
        return
    amount = int(call.data.split("_")[1])
    user_id = call.from_user.id
    u = db.get_user(user_id)

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("◀️ К выводу", callback_data="withdraw"),
        types.InlineKeyboardButton("🏠 Меню", callback_data="menu"),
    )

    if u["balance"] < amount:
        bot.edit_message_text(
            f"❌ *Недостаточно звёзд!*\n\n"
            f"Нужно: *{amount} ⭐️*\n"
            f"У вас: *{fmt(u['balance'])} ⭐️*\n"
            f"Не хватает: *{fmt(amount - u['balance'])} ⭐️*",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=kb
        )
        return

    db.add_balance(user_id, -amount)
    db.log_withdrawal(user_id, amount)
    u = db.get_user(user_id)

    bot.edit_message_text(
        f"✅ *Заявка принята!*\n\n"
        f"Сумма: *{amount} ⭐️*\n"
        f"Остаток: *{fmt(u['balance'])} ⭐️*\n\n"
        f"Администратор обработает заявку в ближайшее время.",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )

    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"💸 *Заявка на вывод*\n\n"
                f"👤 {u['full_name']} (`{user_id}`)\n"
                f"⭐️ {amount} звёзд",
                parse_mode="Markdown"
            )
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data == "top")
def cb_top(call: types.CallbackQuery):
    _show_top(call, "balance")


@bot.callback_query_handler(func=lambda c: c.data in ("top_balance", "top_refs"))
def cb_top_tab(call: types.CallbackQuery):
    _show_top(call, "balance" if call.data == "top_balance" else "refs")


def _show_top(call, tab):
    kb = types.InlineKeyboardMarkup(row_width=2)
    if tab == "balance":
        users = db.get_top_balance(10)
        title = "🏆 Топ по балансу"
        rows = [f"{i+1}. {u['full_name']} — *{fmt(u['balance'])} ⭐️*" for i, u in enumerate(users)]
        kb.add(
            types.InlineKeyboardButton("⭐️ По балансу ✓", callback_data="top_balance"),
            types.InlineKeyboardButton("👥 По рефералам", callback_data="top_refs"),
        )
    else:
        users = db.get_top_refs(10)
        title = "🏆 Топ по рефералам"
        rows = [f"{i+1}. {u['full_name']} — *{u['referral_count']} 👥*" for i, u in enumerate(users)]
        kb.add(
            types.InlineKeyboardButton("⭐️ По балансу", callback_data="top_balance"),
            types.InlineKeyboardButton("👥 По рефералам ✓", callback_data="top_refs"),
        )
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="menu"))
    bot.edit_message_text(
        f"{title}\n\n" + ("\n".join(rows) if rows else "Пусто"),
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )


@bot.message_handler(commands=["admin"])
def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа.")
        return
    bot.reply_to(message,
        "🛠 *Админ панель*\n\n"
        "`/user_list` — список пользователей\n\n"
        "`/set_day_balance <число>` — дневной бонус\n"
        "Пример: `/set_day_balance 0.5`\n\n"
        "`/set_ref_balance <число>` — награда за реферала\n"
        "Пример: `/set_ref_balance 0.6`\n\n"
        "`/set_balance <user_id> <число>` — баланс игрока\n"
        "Пример: `/set_balance 123456789 0`\n\n"
        f"Дневной бонус: *{fmt(db.get_setting('daily_reward', 1))} ⭐️*\n"
        f"Реф. бонус: *{fmt(db.get_setting('ref_reward', 3))} ⭐️*\n"
        f"Пользователей: *{db.get_user_count()}*",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["user_list"])
def cmd_user_list(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа.")
        return
    users = db.get_all_users()
    if not users:
        bot.reply_to(message, "Пользователей пока нет.")
        return
    lines = ["👥 *Пользователи:*\n"]
    for u in users:
        uname = f"@{u['username']}" if u['username'] else "—"
        lines.append(
            f"• `{u['user_id']}` {u['full_name']} ({uname})\n"
            f"  ⭐️ {fmt(u['balance'])} | 👥 {u['referral_count']} реф."
        )
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 3800:
            bot.send_message(message.chat.id, chunk, parse_mode="Markdown")
            chunk = ""
        chunk += line + "\n"
    if chunk:
        bot.send_message(message.chat.id, chunk, parse_mode="Markdown")


@bot.message_handler(commands=["set_day_balance"])
def cmd_set_day_balance(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа.")
        return
    parts = message.text.split()
    value = parse_float(parts[1]) if len(parts) == 2 else None
    if value is None or value < 0:
        bot.reply_to(message, "Использование: `/set_day_balance 1`", parse_mode="Markdown")
        return
    db.set_setting("daily_reward", value)
    bot.reply_to(message, f"✅ Дневной бонус: *{fmt(value)} ⭐️*", parse_mode="Markdown")


@bot.message_handler(commands=["set_ref_balance"])
def cmd_set_ref_balance(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа.")
        return
    parts = message.text.split()
    value = parse_float(parts[1]) if len(parts) == 2 else None
    if value is None or value < 0:
        bot.reply_to(message, "Использование: `/set_ref_balance 3`", parse_mode="Markdown")
        return
    db.set_setting("ref_reward", value)
    bot.reply_to(message, f"✅ Реф. бонус: *{fmt(value)} ⭐️*", parse_mode="Markdown")


@bot.message_handler(commands=["set_balance"])
def cmd_set_balance(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа.")
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit():
        bot.reply_to(message, "Использование: `/set_balance 123456789 10`", parse_mode="Markdown")
        return
    value = parse_float(parts[2])
    if value is None or value < 0:
        bot.reply_to(message, "❌ Некорректное число.")
        return
    target_id = int(parts[1])
    u = db.get_user(target_id)
    if not u:
        bot.reply_to(message, f"❌ Пользователь `{target_id}` не найден.", parse_mode="Markdown")
        return
    db.set_balance(target_id, value)
    bot.reply_to(message, f"✅ Баланс *{u['full_name']}* (`{target_id}`): *{fmt(value)} ⭐️*", parse_mode="Markdown")
    try:
        bot.send_message(target_id, f"Ваш баланс изменён администратором.\nНовый баланс: *{fmt(value)} ⭐️*", parse_mode="Markdown")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: True)
def cb_unknown(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)


if __name__ == "__main__":
    logger.info("Bot started.")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)
