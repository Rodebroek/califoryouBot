import os
import json

from aiogram.contrib.fsm_storage.memory import MemoryStorage
from telethon import TelegramClient, events
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor


# --- Aiogram Config ---
API_TOKEN = '6984306442:AAFUxEhLUHs9EJ1u9uX_ZSjIa2HBKobX8Dk'
bot = Bot(token=API_TOKEN)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())
# --- Telethon Config ---
api_id = '28287530'
api_hash = '3f0c822bc2d922b6e8a64fc275867d56'
client = TelegramClient('session_name', api_id, api_hash)

# Проверка существования файла и инициализация, если он отсутствует
if not os.path.exists("config.json"):
    with open("config.json", "w") as f:
        json.dump({"routes": []}, f)


# --- States for Aiogram ---
class Form(StatesGroup):
    source = State()
    target = State()
# --- Aiogram Handlers ---
@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Напиши /set чтобы установить группы для пересылки.")
# --- Aiogram Handlers ---
@dp.message_handler(commands=['set'])
async def set_groups(message: types.Message):
    await Form.source.set()
    await message.reply("Введите ID или @username исходной группы:")


@dp.message_handler(commands=['delete_route'])
async def delete_route_menu(message: types.Message):
    with open("config.json", "r") as f:
        config = json.load(f)
    routes = config.get("routes", [])

    if not routes:
        await message.reply("Нет активных путей пересылки.")
        return

    markup = InlineKeyboardMarkup()
    for idx, route in enumerate(routes, 1):
        btn_text = f"Из {route['source_group']} в {route['target_group']}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"delete_route_{idx}"))

    await message.reply("Выберите путь для удаления:", reply_markup=markup)

@dp.message_handler(commands=['routes'])
async def show_routes(message: types.Message):
    with open("config.json", "r") as f:
        config = json.load(f)
    routes = config.get("routes", [])
    if not routes:
        await message.reply("Нет активных путей пересылки.")
        return

    text = "Текущие пути пересылки:\n"
    for idx, route in enumerate(routes, 1):
        text += f"{idx}. Из {route['source_group']} в {route['target_group']}\n"
    await message.reply(text)

@dp.callback_query_handler(lambda c: c.data.startswith('delete_route_'))
async def process_delete_route(callback_query: types.CallbackQuery):
    idx_to_delete = int(callback_query.data.split('_')[-1]) - 1

    with open("config.json", "r") as f:
        config = json.load(f)
    routes = config.get("routes", [])

    if 0 <= idx_to_delete < len(routes):
        deleted_route = routes.pop(idx_to_delete)
        with open("config.json", "w") as f:
            json.dump({"routes": routes}, f)
        await callback_query.message.edit_text(
            f"Путь пересылки из {deleted_route['source_group']} в {deleted_route['target_group']} удален.")
    else:
        await callback_query.message.edit_text("Ошибка при удалении пути.")

@dp.message_handler(lambda message: not message.text.startswith('@'), state=Form.source)
async def process_source_invalid(message: types.Message):
    return await message.reply("Введите корректный @username группы.")

@dp.message_handler(lambda message: message.text.startswith('@'), state=Form.source)
async def process_source_valid(message: types.Message, state: FSMContext):
    await Form.next()
    await state.update_data(source_group=message.text)
    await message.reply("Введите ID или @username целевой группы:")

@dp.message_handler(lambda message: not message.text.startswith('@'), state=Form.target)
async def process_target_invalid(message: types.Message):
    return await message.reply("Введите корректный @username группы.")

@dp.message_handler(lambda message: message.text.startswith('@'), state=Form.target)
async def process_target_valid(message: types.Message, state: FSMContext):
    target_group = message.text
    user_data = await state.get_data()
    source_group = user_data['source_group']

    # Загрузка текущих путей пересылки из JSON файла
    with open("config.json", "r") as f:
        config = json.load(f)
    routes = config.get("routes", [])

    # Добавляем новый путь к списку
    routes.append({"source_group": source_group, "target_group": target_group})

    # Сохраняем обновленный список в JSON файл
    with open("config.json", "w") as f:
        json.dump({"routes": routes}, f)

    await message.reply(f"Установлено пересылка из {source_group} в {target_group}.")
    await state.finish()


# --- Telethon Handlers ---
@client.on(events.NewMessage())
async def copy_and_send_message(event):
    # Загружаем конфигурацию из JSON
    with open("config.json", "r") as f:
        config = json.load(f)
    routes = config.get("routes", [])
    if not routes:
        return  # Нет активных путей пересылки

    source_group = routes[0].get("source_group")
    target_group = routes[0].get("target_group")

    if event.chat.username == source_group[1:]:  # Убираем символ '@'
        # Если сообщение содержит медиа
        if event.message.media:
            # Скачиваем медиа
            media = await client.download_media(event.message)
            # Отправляем медиа в целевую группу с оригинальным текстом
            await client.send_file(target_group, media, caption=event.message.text)
            # Удаляем файл после отправки
            os.remove(media)
        else:
            # Если сообщение не содержит медиа, просто отправляем текст
            await client.send_message(target_group, event.message.text)

# --- Running both in separate threads ---
if __name__ == '__main__':
    with client:
        executor.start_polling(dp, skip_updates=True)
        client.run_until_disconnected()