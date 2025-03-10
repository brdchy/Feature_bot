import asyncio
import json
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message
from decouple import config
import aiosqlite  

from typing import List

logging.basicConfig(level=logging.INFO)

TOKEN = config("BOT_TOKEN")
ADMIN_CHAT_ID = -4695557724  

DB_FILE = "bot_state.db"

# Глобальные словари для хранения данных пользователей и состояния админов
active_users = {}  
# Структура: user_id: {
#     "nickname": <строка>,
#     "responses": [список ответов на рассылку],
#     "active": <True/False>,
#     "waiting_for_nick": <True/False>,
#     "pending_scenario": <True/False>,
#     "last_broadcast": <текст последней рассылки>
# }
admin_pending = {}  # структура: admin_id: <True/False>

def get_admin_ids() -> List[int]:
    admin_ids_str = config("ADMINS", default="")
    if not admin_ids_str:
        return []
    return [int(admin_id.strip()) for admin_id in admin_ids_str.split(",")]

ADMINS = get_admin_ids()

# ----------------- Функции для работы с БД -----------------

async def init_db():
    """Инициализировать базу данных и создать таблицы, если они отсутствуют."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_users (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT,
                responses TEXT,
                active INTEGER,
                waiting_for_nick INTEGER,
                pending_scenario INTEGER,
                last_broadcast TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_pending (
                admin_id INTEGER PRIMARY KEY,
                pending INTEGER
            )
        """)
        await db.commit()

async def load_state():
    """Загрузить состояние из базы данных в глобальные переменные."""
    global active_users, admin_pending
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, nickname, responses, active, waiting_for_nick, pending_scenario, last_broadcast FROM active_users") as cursor:
            async for row in cursor:
                user_id = row[0]
                active_users[user_id] = {
                    "nickname": row[1],
                    "responses": json.loads(row[2]) if row[2] else [],
                    "active": bool(row[3]),
                    "waiting_for_nick": bool(row[4]),
                    "pending_scenario": bool(row[5]),
                    "last_broadcast": row[6]
                }
        async with db.execute("SELECT admin_id, pending FROM admin_pending") as cursor:
            async for row in cursor:
                admin_pending[row[0]] = bool(row[1])
    logging.info("Состояние загружено из базы данных")

async def save_active_user(user_id: int):
    """Сохранить данные одного пользователя в БД."""
    user = active_users.get(user_id, {})
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT OR REPLACE INTO active_users
            (user_id, nickname, responses, active, waiting_for_nick, pending_scenario, last_broadcast)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            user.get("nickname"),
            json.dumps(user.get("responses", [])),
            int(user.get("active", False)),
            int(user.get("waiting_for_nick", False)),
            int(user.get("pending_scenario", False)),
            user.get("last_broadcast")
        ))
        await db.commit()

async def save_admin_pending(admin_id: int):
    """Сохранить состояние ожидания администратора в БД."""
    pending = admin_pending.get(admin_id, False)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT OR REPLACE INTO admin_pending (admin_id, pending)
            VALUES (?, ?)
        """, (admin_id, int(pending)))
        await db.commit()

# ----------------- Инициализация бота и диспетчера -----------------
bot = Bot(token=TOKEN)
router = Router()
dp = Dispatcher()
dp.include_router(router)

# -------------- Хэндлеры для команд пользователей ----------------

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if user_id not in active_users or active_users[user_id].get("nickname") is None:
        active_users.setdefault(user_id, {})
        active_users[user_id].update({
            "nickname": None,
            "responses": [],
            "active": True,
            "waiting_for_nick": True,
            "pending_scenario": False,
            "last_broadcast": None
        })
        await save_active_user(user_id)
        await message.answer("Привет! Для регистрации укажи ник")
    else:
        active_users[user_id]["waiting_for_nick"] = True
        await save_active_user(user_id)
        await message.answer("Для изменения ника укажите новый")

@router.message(Command("end"))
async def cmd_end(message: Message):
    user_id = message.from_user.id
    if user_id in active_users and active_users[user_id].get("active", False):
        active_users[user_id]["active"] = False
        await save_active_user(user_id)
        await message.answer("Сессия завершена")
        log_msg = (
            f"Пользователь {message.from_user.username or user_id} "
            f"{active_users[user_id]['nickname']} завершил сессию"
        )
        await log_to_admin(log_msg)
    else:
        await message.answer("Сессия уже завершена")

# -------------- Хэндлеры для команд администратора ----------------

@router.message(Command("message"), F.from_user.id.in_(ADMINS))
async def admin_message_command(message: Message):
    # Админ инициирует рассылку, после чего ожидается ввод текста
    admin_pending[message.from_user.id] = True
    await save_admin_pending(message.from_user.id)
    await message.answer("Введите текст для рассылки")

@router.message(Command("status"), F.from_user.id.in_(ADMINS))
async def admin_status_command(message: Message):
    # Формирование статуса активных пользователей
    status_lines = []
    for user_id, data in active_users.items():
        if data.get("active", False):
            responses = data.get("responses", [])
            responses_str = "\n".join(f"{i}. {resp}" for i, resp in enumerate(responses, 1)) if responses else "Нет ответов"
            status_lines.append(f"{user_id} {data.get('nickname', 'не указан')}:\n{responses_str}")
    status_text = "\n\n".join(status_lines) if status_lines else "Нет активных пользователей"
    await message.answer(status_text)

@router.message(Command("id"))
async def id_command(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    await message.answer(f"ID пользователя: {user_id}\nID чата: {chat_id}")

@router.message(Command("add_admin"), F.from_user.id.in_(ADMINS))
async def add_admin_command(message: Message):
    if not message.reply_to_message:
        await message.answer("Команда должна быть отправлена в ответ на сообщение пользователя.")
        return

    new_admin_id = message.reply_to_message.from_user.id

    if new_admin_id in ADMINS:
        await message.answer("Пользователь уже является администратором.")
        return

    ADMINS.append(new_admin_id)
    await message.answer(f"Пользователь {new_admin_id} теперь является администратором.")

# -------------- Общий хэндлер для входящих сообщений ----------------

@router.message()
async def handle_messages(message: Message):
    user_id = message.from_user.id
    text = message.text

    # Если сообщение от администратора и ожидается текст для рассылки
    if message.from_user.id in ADMINS and admin_pending.get(message.from_user.id, False):
        broadcast_text = text
        for uid, data in active_users.items():
            if data.get("active", False):
                try:
                    await bot.send_message(uid, broadcast_text)
                    # Помечаем, что от пользователя ожидается ответ на сценарное сообщение
                    data["pending_scenario"] = True
                    data["last_broadcast"] = broadcast_text
                    await save_active_user(uid)
                except Exception as e:
                    logging.error(f"Ошибка при рассылке пользователю {uid}: {e}")
        admin_pending[message.from_user.id] = False
        await save_admin_pending(message.from_user.id)
        await message.answer("Рассылка отправлена")
        return

    # Если пользователь ожидает ввода ника (при регистрации или изменении)
    if user_id in active_users and active_users[user_id].get("waiting_for_nick", False):
        previous_nick = active_users[user_id].get("nickname")
        active_users[user_id]["nickname"] = text
        active_users[user_id]["waiting_for_nick"] = False
        await save_active_user(user_id)
        if previous_nick is None:
            reply = "Зарегистрировано"
            log_msg = (
                f"Пользователь {message.from_user.username or user_id} зарегистрировался под ником: {text}"
            )
        else:
            reply = "Зарегистрировано"
            log_msg = (
                f"Пользователь {message.from_user.username or user_id} изменил свой ник c {previous_nick} на: {text}"
            )
        await message.answer(reply)
        await log_to_admin(log_msg)
        return

    # Если сообщение является ответом на сценарное сообщение (рассылку)
    if user_id in active_users and active_users[user_id].get("pending_scenario", False):
        active_users[user_id]["responses"].append(text)
        active_users[user_id]["pending_scenario"] = False
        await save_active_user(user_id)
        await message.answer("Спасибо за ответ :)")
        log_msg = (
            f"Пользователь {message.from_user.username or user_id} {active_users[user_id]['nickname']} "
            f"ответил:\n{text}"
        )
        await log_to_admin(log_msg)
        return

    # Если сообщение не попадает ни под один из сценариев
    await message.answer("не знаю что ответить, введите команду или ждите указаний")

# -------------- Функция логирования действий пользователя ----------------

async def log_to_admin(text: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(ADMIN_CHAT_ID, text)
        except Exception as e:
            logging.error(f"Ошибка отправки лога админу: {e}")
    else:
        for admin_id in ADMINS:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logging.error(f"Ошибка отправки лога админу {admin_id}: {e}")

# -------------- Основной запуск бота ----------------

async def main():
    await init_db()
    await load_state()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
